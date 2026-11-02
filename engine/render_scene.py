"""MYONL 渲染层 · 场景/转场/镜头（renderer.py 模块化拆分）。

SceneMixin 的方法原样迁自 engine/renderer.py：方法体与签名不变，
经 self 访问实例状态（__init__ 中初始化）与其他 Mixin 方法；
常量与纯函数统一来自 render_utils（engine.renderer 再导出，命名空间不变）。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import pygame
import random
from .render_utils import (
    _scale_to_fit,
    CAM_PAN_RATIO,
    CAM_ZOOM_SECONDS,
    CAM_SHAKE_PX,
)


class SceneMixin:
    """场景/转场/镜头方法集（经多继承组合进 Renderer，见 engine/renderer.py）。"""

    if TYPE_CHECKING:  # pragma: no cover - 仅供 pyright：宿主 Renderer 属性 / 跨 Mixin 方法
        from . import timeline as tlapi

        size: tuple[int, int]
        timeline: tlapi.Timeline
        _screen: pygame.Surface
        _scene: pygame.Surface
        _small_font: pygame.font.Font
        _fade_t0: int | None
        _bg_fade_seconds: float
        _title_font: pygame.font.Font
        _chapter: dict | None

        def _t(self, text: str) -> str: ...
        def _now_ms(self) -> int: ...
        def _reduce_effects(self) -> bool: ...
        def _pacing(self, name: str, default: float) -> float: ...
        def _load_image(self, name) -> pygame.Surface | None: ...
        def _video_frame(self, video: dict) -> pygame.Surface | None: ...
        def _cached_font_surface(self, font, text, antialias, color) -> pygame.Surface: ...

    def _draw_ending_fade(self, now: int) -> None:
        """⑩ 结尾淡出：0.8s 内 alpha 从 0→255 的全屏黑罩。"""
        t0 = self._ending_fade_t0
        if t0 is None:
            return
        dur = 800
        elapsed = now - t0
        t = min(1.0, elapsed / dur)
        alpha = int(255 * t)
        overlay = pygame.Surface(self.size, pygame.SRCALPHA)
        overlay.fill((0, 0, 0, alpha))
        self._screen.blit(overlay, (0, 0))
        if t >= 1.0:
            self._ending_fade_done = True

    def play_cg(self, name: str) -> None:
        """展示一张 CG 全屏图（images/{name}.png 优先，images/cg_{name}.png 兜底），
        点空格/点击关闭。缺失走占位。"""
        self._cg_showing = str(name)

    def play_camera(self, kind: str, args) -> None:
        """触发镜头动画（pan/zoom/shake/reset）。纯展示层，不进 GameState。

        P30-C-a：动画挂在 Timeline 的 camera 轨上，每帧由 _update_camera 取当前值应用；
        播完停在目标值（pan/zoom 保留偏移，reset 归零，shake 归零）。
        """
        args = list(args or [])
        now = self._now_ms()
        sx, sy, ss = self._cam_dx, self._cam_dy, self._cam_scale
        meta = {"kind": kind}
        if kind == "pan":
            direction, secs = args[0], float(args[1])
            w, h = self.size
            tx, ty = {
                "左": (-w * CAM_PAN_RATIO, 0.0), "右": (w * CAM_PAN_RATIO, 0.0),
                "上": (0.0, -h * CAM_PAN_RATIO), "下": (0.0, h * CAM_PAN_RATIO),
            }[direction]
            self.timeline.play("camera", secs * 1000,
                               lambda t: (sx + (tx - sx) * t, sy + (ty - sy) * t, ss),
                               t0=now, meta=meta)
        elif kind == "zoom":
            from_s, to_s = float(args[0]), float(args[1])
            self.timeline.play("camera", CAM_ZOOM_SECONDS * 1000,
                               lambda t: (sx, sy, from_s + (to_s - from_s) * t),
                               t0=now, meta=meta)
        elif kind == "shake":
            if self._reduce_effects():
                return  # 低配/玩家要求：跳过震动，不排时间轴
            secs, amp = float(args[0]), float(args[1])
            self.timeline.play("camera", secs * 1000,
                               lambda t: (random.uniform(-1, 1) * CAM_SHAKE_PX * amp * (1.0 - t),
                                          random.uniform(-1, 1) * CAM_SHAKE_PX * amp * (1.0 - t)),
                               t0=now, meta=meta)
            # 震动开始前清零，结束后 _update_camera 归零
            self._shake_dx = 0.0
            self._shake_dy = 0.0
        elif kind == "reset":
            secs = float(args[0])
            self.timeline.play("camera", secs * 1000,
                               lambda t: (sx * (1.0 - t), sy * (1.0 - t),
                                          1.0 + (ss - 1.0) * (1.0 - t)),
                               t0=now, meta=meta)

    def play_fg(self, name, x=0, y=0, alpha=1.0) -> None:
        """P30-C-b：设置前景/特效贴图（名称 无/none = 清除）。纯展示层，不进 GameState、不进存档。"""
        if name in (None, "", "无", "none"):
            self._fg = None
            return
        self._fg = {"name": str(name), "x": int(x or 0), "y": int(y or 0),
                    "alpha": 1.0 if alpha is None else float(alpha)}

    def _draw_fg(self, target=None) -> None:
        """画前景层（立绘之上、UI 遮罩之下）。素材缺失静默跳过，不画占位以免糊住画面。"""
        fg = self._fg
        if not fg:
            return
        target = target if target is not None else self._screen
        img = self._load_image(fg["name"])
        if img is None:
            return
        alpha = fg.get("alpha", 1.0)
        if alpha < 1.0:
            img = img.copy()          # 缓存里的 Surface 不能就地改 alpha
            img.set_alpha(int(255 * max(0.0, alpha)))
        target.blit(img, (fg.get("x", 0), fg.get("y", 0)))

    def play_transition(self, kind: str, args) -> None:
        """登记待用转场（dissolve/wipe/slide），作用于下一次背景切换。"""
        self._pending_transition = (kind, list(args or []))

    # ---- U12：章节 / 幕间演出卡（黑场 + 标题渐显渐隐）----

    def play_chapter(self, title: str, secs=None) -> None:
        """登记一张章节卡；时长缺省取 pacing.chapter_fade，播完自动消失。"""
        try:
            dur = float(secs) if secs else max(0.6, float(self._pacing("chapter_fade", 0.9)))
        except (TypeError, ValueError):
            dur = 0.9
        self._chapter = {"title": str(title or ""), "t0": self._now_ms(), "dur": dur}

    def _draw_chapter(self) -> bool:
        """画章节卡；返回 True 表示仍在播（调用方提前返回，本帧不画对话框）。"""
        ch = getattr(self, "_chapter", None)
        if not ch:
            return False
        elapsed = (self._now_ms() - ch["t0"]) / 1000.0
        dur = max(0.4, float(ch["dur"]))
        if elapsed >= dur:
            self._chapter = None
            return False
        fade = min(0.35, dur / 3.0)
        if elapsed < fade:
            k = elapsed / fade
        elif elapsed > dur - fade:
            k = max(0.0, (dur - elapsed) / fade)
        else:
            k = 1.0
        w, h = self.size
        veil = pygame.Surface((w, h), pygame.SRCALPHA)
        veil.fill((0, 0, 0, int(232 * k)))
        self._screen.blit(veil, (0, 0))
        title = ch["title"]
        if title:
            img = self._title_font.render(title, True, (255, 255, 255))
            img.set_alpha(int(255 * k))
            tx = (w - img.get_width()) // 2
            ty = (h - img.get_height()) // 2
            self._screen.blit(img, (tx, ty))
            line_w = min(360, img.get_width() + 80)
            deco = pygame.Surface((line_w, 2), pygame.SRCALPHA)
            deco.fill((255, 255, 255, int(120 * k)))
            self._screen.blit(deco, ((w - line_w) // 2, ty + img.get_height() + 18))
        return True

    # ---- 音乐切换（P26 T3：fadein / fadeout，由 demo 收到 music 事件后调用）----

    def play_bg(self, fadein=None) -> None:
        """P33：@bg fadein=秒 —— 设置下一次背景切换的淡入时长（一次性，缺省回引擎默认 0.3s）。"""
        self._next_bg_fade = None if fadein is None else max(0.0, float(fadein))

    def trigger_ending_fade(self) -> None:
        """⑩ 触发 0.8s 结尾淡出。render 每帧自动推进；淡出完成时 _ending_fade_done=True。"""
        if self._ending_fade_t0 is None:
            self._ending_fade_t0 = self._now_ms()
            self._ending_fade_done = False

    # ==================== ⑮ 全屏切换 ====================

    def _draw_background(self, bg, video=None, target=None) -> None:
        target = target if target is not None else self._screen
        w, h = self.size
        if video:
            img = self._video_frame(video)
            if img is None:
                # 占位：深色渐变（缺帧序列不崩）
                self._draw_bg_placeholder((0, 0, w, h), target)
                return
            scaled = _scale_to_fit(img, w, h)
            target.fill((0, 0, 0))
            target.blit(scaled, ((w - scaled.get_width()) // 2,
                                 (h - scaled.get_height()) // 2))
            return
        if bg is None:
            target.fill((0, 0, 0))
            return
        img = self._load_image(str(bg))
        if img is None:
            # ④ 占位改为深色渐变（画面上不写文件名，开发者侧日志已有）
            self._draw_bg_placeholder((0, 0, w, h), target)
            return
        scaled = _scale_to_fit(img, w, h)
        target.fill((0, 0, 0))
        target.blit(scaled, ((w - scaled.get_width()) // 2,
                             (h - scaled.get_height()) // 2))

    def _draw_bg_placeholder(self, rect, target) -> None:
        """④ 背景占位：深色对角线渐变（不写文件名到画面上）。"""
        x0, y0, rw, rh = rect
        # 深紫蓝渐变
        for y in range(rh):
            t = y / max(1, rh - 1)
            c = (int(18 + 32 * t), int(16 + 24 * t), int(45 + 45 * t))
            pygame.draw.line(target, c, (x0, y0 + y), (x0 + rw, y0 + y))

    def _load_cg(self, name):
        """CG 图双查：images/{name}.png 优先（新名），缺失再试 images/cg_{name}.png（旧名兜底）。"""
        img = self._load_image(str(name))
        if img is not None:
            return img
        return self._load_image(f"cg_{name}")

    def _draw_cg(self, name: str, show_hint: bool = True) -> None:
        """CG 全屏展示：images/{name}.png 优先，images/cg_{name}.png 兜底；等比铺满，缺失走渐变占位。

        show_hint=False 时不再画「空格 / 点击 继续」（终幕停留期由收尾引导替代）。
        """
        w, h = self.size
        img = self._load_cg(name)
        self._screen.fill((0, 0, 0))
        if img is None:
            # ④ CG 占位：深色渐变，不写文件名
            self._draw_bg_placeholder((0, 0, w, h), self._screen)
        else:
            scaled = _scale_to_fit(img, w, h)
            self._screen.blit(scaled, ((w - scaled.get_width()) // 2,
                                       (h - scaled.get_height()) // 2))
        if show_hint:
            hint = self._cached_font_surface(self._small_font, self._t("空格 / 点击 继续"), True, (200, 200, 200))
            self._screen.blit(hint, ((w - hint.get_width()) // 2, h - 36))

    def _update_camera(self, now: int) -> None:
        """镜头动画推进：取 Timeline camera 轨本帧的值应用到持久偏移/震动偏移。

        按时长线性插值（不按帧数，60/30fps 表现一致）；播完定到目标值并收轨。
        """
        track = self.timeline.track("camera")
        if track is None:
            return
        kind = track.meta.get("kind")
        value = self.timeline.value("camera")
        if value is not None:
            if kind == "shake":
                self._shake_dx, self._shake_dy = value
            else:
                self._cam_dx, self._cam_dy, self._cam_scale = value
        if track.done(now):
            if kind == "shake":
                self._shake_dx = self._shake_dy = 0.0
            elif kind == "reset":
                self._cam_dx = self._cam_dy = 0.0
                self._cam_scale = 1.0
            self.timeline.cancel("camera")

    def _blit_scene_to_screen(self) -> None:
        """把 _scene 经镜头变换（缩放+平移+震动偏移）blit 到 screen；缩放露边用黑色填充。"""
        w, h = self.size
        self._screen.fill((0, 0, 0))
        scale = max(0.01, self._cam_scale)
        if abs(scale - 1.0) > 1e-3:
            sw, sh = max(1, int(w * scale)), max(1, int(h * scale))
            view = pygame.transform.scale(self._scene, (sw, sh))
        else:
            view = self._scene
        x = int((w - view.get_width()) // 2 + self._cam_dx + self._shake_dx)
        y = int((h - view.get_height()) // 2 + self._cam_dy + self._shake_dy)
        self._screen.blit(view, (x, y))

    def _draw_transition(self, now: int) -> None:
        """转场叠加：dissolve 交叉溶解 / wipe 方向擦除 / slide 新画面滑入。播完复位。

        P30-C-a：进度来自 Timeline 的 transition 轨（t 0~1），播完即收轨并清旧画面。
        """
        track = self.timeline.track("transition")
        if track is None or self._trans_old is None:
            return
        kind = track.meta.get("kind")
        args = track.meta.get("args") or []
        t = self.timeline.value("transition") or 0.0
        w, h = self.size
        old, new = self._trans_old, self._screen.copy()
        if kind == "dissolve":
            self._screen.blit(old, (0, 0))
            new.set_alpha(int(255 * t))
            self._screen.blit(new, (0, 0))
        elif kind == "wipe":
            # 旧画面在下，新画面按方向用矩形裁剪逐渐露出
            direction = args[0]
            self._screen.blit(old, (0, 0))
            if direction == "左":
                clip = pygame.Rect(0, 0, int(w * (1.0 - t)), h)  # 从右往左擦
            elif direction == "右":
                clip = pygame.Rect(w - int(w * t), 0, int(w * t), h)
            elif direction == "上":
                clip = pygame.Rect(0, 0, w, int(h * (1.0 - t)))
            else:  # 下
                clip = pygame.Rect(0, h - int(h * t), w, int(h * t))
            if clip.width > 0 and clip.height > 0:
                sub = new.subsurface(clip)
                self._screen.blit(sub, clip.topleft)
        elif kind == "slide":
            # 旧画面在下静止，新画面从指定方向滑入
            direction = args[0]
            self._screen.blit(old, (0, 0))
            dx, dy = {"左": (int(w * (1.0 - t)), 0), "右": (-int(w * (1.0 - t)), 0),
                      "上": (0, int(h * (1.0 - t))), "下": (0, -int(h * (1.0 - t)))}[direction]
            self._screen.blit(new, (dx, dy))
        if track.done(now):
            self.timeline.cancel("transition")
            self._trans_old = None  # 播完复位：下次 bg 切换回默认淡入

    def _draw_fade_overlay(self, now: int) -> None:
        """默认淡入（无 @transition 时的向后兼容行为）：黑→画面，时长随 @bg fadein=（P33，缺省 0.3s）。"""
        if self._fade_t0 is None:
            return
        elapsed = (now - self._fade_t0) / 1000.0
        total = self._bg_fade_seconds
        if elapsed >= total:
            return
        alpha = int(255 * (1.0 - elapsed / total))
        overlay = pygame.Surface(self.size, pygame.SRCALPHA)
        overlay.fill((0, 0, 0, alpha))
        self._screen.blit(overlay, (0, 0))

    # ==================== P35 UI 布局助手 ====================
