"""MYONL 渲染层 · 音视频与素材加载（renderer.py 模块化拆分）。

MediaMixin 的方法原样迁自 engine/renderer.py：方法体与签名不变，
经 self 访问实例状态（__init__ 中初始化）与其他 Mixin 方法；
常量与纯函数统一来自 render_utils（engine.renderer 再导出，命名空间不变）。
"""
from __future__ import annotations

import pygame
import os
import sys
from . import data
from . import profiling  # 迭代-01 任务2：真实读盘计时（未开 --profile 时零开销）
from .render_utils import (
    FRAME_WINDOW,
    SFX_CACHE_MAX,
    _FRAME_EXTS,
)
from typing import TYPE_CHECKING, Any


class MediaMixin:
    """音视频与素材加载方法集（经多继承组合进 Renderer，见 engine/renderer.py）。"""

    # B1：宿主注入属性 / 其他 Mixin 方法——仅静态检查声明。
    if TYPE_CHECKING:  # pragma: no cover
        config: Any
        settings: Any
        assets_root: Any
        _screen: pygame.Surface
        _audio_ok: Any
        _now_ms: Any
        _voice_channel: Any
        _img_cache: Any
        _img_cache_max: Any
        _img_cache_max_bytes: Any
        _sfx_cache: Any
        _seq_index: Any
        _video_warned: Any
        _load_fonts: Any

    # ---- M1.5：音量与静音（玩家设置层）----

    def _muted(self) -> bool:
        return bool(self.settings.get("muted", False))

    def _volume_of(self, key: str, default: float) -> float:
        if self._muted():
            return 0.0
        try:
            return max(0.0, min(1.0, float(self.settings.get(key, default))))
        except (TypeError, ValueError):
            return float(default)

    def _bgm_volume(self) -> float:
        return self._volume_of("bgm_volume", 0.7)

    def _sfx_volume(self) -> float:
        return self._volume_of("sfx_volume", 0.8)

    def _voice_volume(self) -> float:
        return self._volume_of("voice_volume", 0.9)

    def play_sfx(self, sound: str) -> None:
        """播一次音效。由 demo 层收到 sfx 事件后调用。缺失 → 静音不崩。"""
        if not self._audio_ok:
            return
        try:
            path = data.resolve_audio(self.assets_root, sound)
        except data.DataError as e:
            print(f"[音频警告] {e}", file=sys.stderr)
            return
        try:
            snd = self._load_sound(path)
            if hasattr(snd, "set_volume"):
                snd.set_volume(self._sfx_volume())
            snd.play()
        except pygame.error as e:
            print(f"[音频警告] 音效 “{sound}” 播放失败：{e}", file=sys.stderr)

    # ---- 演出系统：CG / 镜头 / 转场（由 demo 收到对应事件后调用）----

    def play_music(self, track, fadein=None, fadeout=None) -> None:
        """切曲。fadeout>0 时先让旧曲淡出，到点再加载新曲淡入（缺省=立即切换，旧行为）。"""
        track = str(track) if track else None
        old = self._music
        self._music = track          # 与 _update_music 缓存对齐，避免每帧重复切歌
        self._pending_music = None   # 新指令取消上一段未完成的待切
        if not self._audio_ok:
            if track is not None:
                print(f"[音频警告] 无音频设备，音乐 “{track}” 静音", file=sys.stderr)
            return
        if fadeout and old is not None:
            try:
                pygame.mixer.music.fadeout(int(float(fadeout) * 1000))
            except pygame.error:
                pass
            else:
                # pygame 音乐是单通道，无法真正交叉淡化：先淡出旧曲，到点再起新曲
                self._pending_music = {"track": track, "fadein": fadein,
                                       "due": self._now_ms() + float(fadeout) * 1000}
                return
        self._start_music(track, fadein)

    def _start_music(self, track, fadein=None) -> None:
        """加载并播放（循环）。fadein>0 走 pygame 的 fade_ms 淡入。缺失 → 静音不崩。"""
        if not self._audio_ok:
            return
        try:
            if not track:
                pygame.mixer.music.stop()
                return
            path = data.resolve_audio(self.assets_root, track)
            pygame.mixer.music.load(path)
            pygame.mixer.music.set_volume(self._bgm_volume())
            if fadein:
                pygame.mixer.music.play(-1, fade_ms=int(float(fadein) * 1000))
            else:
                pygame.mixer.music.play(-1)  # 循环播放
        except (data.DataError, pygame.error) as e:
            print(f"[音频警告] 音乐 “{track}” 无法播放：{e}", file=sys.stderr)

    def _update_pending_music(self) -> None:
        """淡出到点后执行待切音乐（每帧调用，无待切时是空操作）。"""
        p = self._pending_music
        if p is None or self._now_ms() < p["due"]:
            return
        self._pending_music = None
        self._start_music(p["track"], p.get("fadein"))

    # ==================== U10：玩家改键 ====================

    def begin_key_capture(self, key: str | None) -> None:
        """设置页按回车改键：进入捕获态，下一个按键即写入该设置项（None=退出捕获）。"""
        self._key_capture = str(key) if key else None

    def _capture_key_event(self, ev):
        """捕获态下把按键转成 settings_set_key 动作（Esc/Delete/退格 = 恢复默认）。"""
        if not getattr(self, "_key_capture", None) or ev.type != pygame.KEYDOWN:
            return None
        key = self._key_capture
        self._key_capture = None
        if ev.key in (pygame.K_ESCAPE, pygame.K_DELETE, pygame.K_BACKSPACE):
            return {"action": "settings_set_key", "key": key, "code": ""}
        try:
            name = pygame.key.name(ev.key)
        except Exception:  # noqa: BLE001 — 极端键码取不到名字时视为取消
            name = ""
        return {"action": "settings_set_key", "key": key, "code": name}

    def update_settings(self, settings) -> None:
        """demo 修改设置后同步；音量/打字速度下一帧即生效（音乐音量立即调整）。"""
        if not isinstance(settings, dict):
            return
        _font_before = self.settings.get("font_scale")
        self.settings.update(settings)
        # U10：玩家改键后立即重建键位表（不用重启游戏）
        if any(k.startswith("key_") for k in settings):
            from . import config as cfgapi

            self._keymap = cfgapi.keymap(self.config, self.settings)
        # M1.5-B：字号档位切换 → 重建字体（对话/名字/选项/菜单/标题一起变）
        if self.settings.get("font_scale") != _font_before and hasattr(self, "_load_fonts"):
            try:
                self._load_fonts()
            except Exception as e:  # noqa: BLE001 — 换字号失败不应打断游玩
                print(f"[设置警告] 字号重建失败：{e}", file=sys.stderr)
        if self._audio_ok:
            try:
                pygame.mixer.music.set_volume(self._bgm_volume())
            except pygame.error:
                pass

    # ==================== ⑩ 结尾淡出 ====================

    def _update_music(self, music) -> None:
        """音乐切换：与缓存不同才动作。缺失 → 静音不崩。"""
        if music == self._music:
            return
        self._music = music
        if not self._audio_ok:
            if music is not None:
                print(f"[音频警告] 无音频设备，音乐 “{music}” 静音", file=sys.stderr)
            return
        try:
            if music is None:
                pygame.mixer.music.stop()
                return
            path = data.resolve_audio(self.assets_root, music)
            pygame.mixer.music.load(path)
            pygame.mixer.music.set_volume(self._bgm_volume())
            pygame.mixer.music.play(-1)  # 循环播放
        except (data.DataError, pygame.error) as e:
            print(f"[音频警告] 音乐 “{music}” 无法播放：{e}", file=sys.stderr)

    def _update_voice(self, history) -> None:
        """台词配音：history 末条带 voice 字段且是新的一句 → 专用声道播放。

        voice_enabled 关闭时不播；换句时停掉上一句配音；缺失 → 静音不崩。
        """
        last = history[-1] if history else {}
        key = (len(history), last.get("char"), last.get("text"))
        if key == self._voice_key:
            return
        self._voice_key = key
        self._voice_done_pending = False
        if self._voice_busy():
            try:
                self._voice_channel.stop()
            except pygame.error:
                pass
        voice = last.get("voice")
        if not voice or not self.settings.get("voice_enabled", 1):
            # 无语音 → 唇形时钟回退到共享动画时钟
            self._voice_t0 = None
            self._voice_length = 0.0
            return
        self._play_voice(str(voice))

    def _play_voice(self, name: str) -> None:
        """播放一条配音（audio/{name}.wav/.ogg/.mp3）。缺失/失败 → 中文警告，不崩。"""
        if not self._audio_ok or self._voice_channel is None:
            return
        try:
            path = data.resolve_audio(self.assets_root, name)
        except data.DataError as e:
            print(f"[音频警告] {e}", file=sys.stderr)
            return
        try:
            snd = self._load_sound(path)
            if hasattr(snd, "set_volume"):
                snd.set_volume(self._voice_volume())
            self._voice_channel.play(snd)
            self._voice_done_pending = True
            # 记录语音起始时刻与总时长，供唇形随语音循环
            self._voice_t0 = self._now_ms()
            try:
                self._voice_length = float(snd.get_length())
            except (pygame.error, TypeError, ValueError, AttributeError):
                self._voice_length = 0.0
        except pygame.error as e:
            print(f"[音频警告] 配音 “{name}” 播放失败：{e}", file=sys.stderr)

    def _voice_busy(self) -> bool:
        """配音是否正在播放（语音等待 / 自动推进的判定依据）。"""
        ch = self._voice_channel
        if ch is None:
            return False
        try:
            return bool(ch.get_busy())
        except pygame.error:
            return False

    def _load_sound(self, path: str):
        """音效/配音按需加载 + LRU（上限 SFX_CACHE_MAX 条，超限释放最久未用）。

        素材热重载：同名文件被替换（mtime 变化）时丢弃旧缓存重新读盘。
        """
        cache = self._sfx_cache
        mtimes = getattr(self, "_sfx_mtime", None)
        if mtimes is None:
            mtimes = self._sfx_mtime = {}
        snd = cache.get(path)
        if snd is not None:
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                mtime = None
            if mtime == mtimes.get(path):
                cache.move_to_end(path)
                return snd
            cache.pop(path, None)   # 文件已变 → 重新加载
        with profiling.track_io():
            snd = pygame.mixer.Sound(path)
        try:
            mtimes[path] = os.path.getmtime(path)
        except OSError:
            pass
        cache[path] = snd
        while len(cache) > SFX_CACHE_MAX:
            cache.popitem(last=False)
        return snd

    def _load_image(self, name):
        """按名字加载 images/{name}.png；缺失/损坏返回 None（调用方画占位块）。"""
        try:
            path = data.resolve_image(self.assets_root, name)
        except data.DataError:
            return None
        return self._load_image_path(path)

    def _load_image_path(self, path):
        """按需加载 + LRU 缓存：命中只更新热度；超过张数/字节上限释放最久未用。

        正在显示的图片每帧都会被取用（命中即变最新），不会被 LRU 释放。
        素材热重载：同名文件被替换（mtime 变化）时丢弃旧缓存重新读盘。
        """
        cache = self._img_cache
        mtimes = getattr(self, "_img_mtime", None)
        if mtimes is None:
            mtimes = self._img_mtime = {}
        hit = cache.get(path)
        if hit is not None:
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                mtime = None
            if mtime == mtimes.get(path):
                cache.move_to_end(path)
                return hit
            self._evict_image(path)   # 文件已变 → 重新读盘
        try:
            with profiling.track_io():
                img = pygame.image.load(path).convert_alpha()
        except (pygame.error, OSError):
            return None
        try:
            mtimes[path] = os.path.getmtime(path)
        except OSError:
            pass
        cache[path] = img
        self._img_bytes += img.get_width() * img.get_height() * 4
        while cache and (len(cache) > self._img_cache_max
                         or self._img_bytes > self._img_cache_max_bytes):
            _old_path, old_img = cache.popitem(last=False)
            self._img_bytes -= old_img.get_width() * old_img.get_height() * 4
        return img

    def _evict_image(self, path) -> None:
        """从图片缓存移除指定路径（帧序列窗口裁剪用）。"""
        img = self._img_cache.pop(path, None)
        if img is not None:
            self._img_bytes -= img.get_width() * img.get_height() * 4

    def _sequence_index(self, subdir: str, prefix: str) -> list:
        """帧序列索引：images/<subdir>/<prefix>_001.<png|webp> 起连续编号。

        启动/首次用到时只 stat 文件名建索引（不加载内容），结果缓存；
        无帧 → 空列表（调用方走回退逻辑）。
        """
        key = (subdir, prefix)
        cached = self._seq_index.get(key)
        if cached is not None:
            return cached
        base = os.path.join(self.assets_root, "images", subdir)
        frames = []
        n = 1
        while True:
            hit = None
            for ext in _FRAME_EXTS:
                p = os.path.join(base, f"{prefix}_{n:03d}{ext}")
                if os.path.isfile(p):
                    hit = p
                    break
            if hit is None:
                break
            frames.append(hit)
            n += 1
        self._seq_index[key] = frames
        return frames

    def _load_window(self, frames: list, idx: int) -> None:
        """帧序列滑动窗口：驻留当前帧 ±FRAME_WINDOW，窗口外的本序列帧立即释放。

        总帧数任意大（如 1800 帧），内存只占窗口内最多 2*FRAME_WINDOW+1 张。
        """
        total = len(frames)
        if total <= 2 * FRAME_WINDOW + 1:
            keep = set(range(total))
        else:
            keep = {(idx + d) % total for d in range(-FRAME_WINDOW, FRAME_WINDOW + 1)}
        for k in keep:
            self._load_image_path(frames[k])
        keep_paths = {frames[k] for k in keep}
        seq_paths = set(frames)
        for path in list(self._img_cache):
            if path in seq_paths and path not in keep_paths:
                self._evict_image(path)

    def _video_frame(self, video: dict):
        """视频背景当前帧 Surface；无帧序列返回 None（调用方画占位）。"""
        name = str(video.get("name") or "")
        try:
            fps = int(video.get("fps") or 30)
        except (TypeError, ValueError):
            fps = 30
        if fps <= 0:
            fps = 30
        frames = self._sequence_index("videos", name)
        if not frames:
            if name not in self._video_warned:
                self._video_warned.add(name)
                print(f"[资源警告] 视频 “{name}” 没有帧序列："
                      f"images/videos/{name}_001.png 起按 %03d 连续编号", file=sys.stderr)
            return None
        key = (name, fps)
        if key != self._video_key:
            self._video_key = key
            self._video_t0 = self._now_ms()
        idx = int((self._now_ms() - self._video_t0) / 1000.0 * fps) % len(frames)
        self._load_window(frames, idx)
        return self._load_image_path(frames[idx])
