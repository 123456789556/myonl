"""编辑器预览渲染、内容哈希缓存与取消标记。

从 `engine.editor` 拆出的独立模块，保持原有函数名与行为不变；
`engine.editor` 仍按原名重新导出，历史引用（含测试 monkeypatch）无需改动。
"""

from __future__ import annotations

import hashlib
import os
import re
import threading
from collections import OrderedDict

from .sdl_env import dummy_video

# 全部支持的指令名（自动补全候选）
_DIRECTIVES = [
    "@character", "@bg", "@music", "@sfx", "@voice", "@video", "@show", "@hide",
    "@choice:", "@label", "@jump", "@if", "@elif", "@else:", "@set", "@end", "@include",
    "@chapter",
]

# 扫描剧本提取角色/标签/变量名
_RE_CHARACTER = re.compile(r"^@character\s+(\S+)", re.MULTILINE)
_RE_LABEL = re.compile(r"^@label\s+(\S+)", re.MULTILINE)
_RE_SET_VAR = re.compile(r"^@set\s+(\S+)\s*[+\-]?=", re.MULTILINE)

# 最近预览结果缓存：同一「文件目录 + 素材根 + 帧数 + 剧本内容哈希」直接复用，
# 避免连续输入时对已渲染过的旧文本重复跑 600ms 渲染。
_PREVIEW_CACHE_MAX = 4
_preview_cache: "OrderedDict[tuple, bytes]" = OrderedDict()
_preview_cache_lock = threading.Lock()
# 每个编辑器标签页最近一次请求序号：新请求一到，旧请求在帧间自行放弃。
_preview_latest: dict = {}
_preview_latest_lock = threading.Lock()


class _PreviewCancelled(Exception):
    """用户已继续编辑，旧预览在渲染途中被放弃。"""


class _FastForwardClock:
    """预览专用时钟：按真实 60FPS 的节奏产出帧间隔，但不真的睡眠。

    Renderer.render 内部用 pygame.time.Clock.tick(60) 限帧；预览是离屏渲染，
    没必要为 30 帧白等约 500ms。这里只推进等价的虚拟时间，画面结果不变。
    """

    def __init__(self) -> None:
        self.now = 0

    def tick(self, fps: int = 0) -> int:
        self.now += 16
        return 16


def _preview_cache_key(text: str, base_dir: str, assets_root: str, frames: int) -> tuple:
    digest = hashlib.sha256((text or "").encode("utf-8")).hexdigest()
    try:
        frame_count = int(frames)
    except (TypeError, ValueError):
        frame_count = -1
    return (os.path.realpath(base_dir), os.path.realpath(assets_root),
            frame_count, digest)


def _preview_cache_get(key: tuple):
    with _preview_cache_lock:
        png = _preview_cache.get(key)
        if png is not None:
            _preview_cache.move_to_end(key)
        return png


def _preview_cache_put(key: tuple, png: bytes) -> None:
    with _preview_cache_lock:
        _preview_cache[key] = png
        _preview_cache.move_to_end(key)
        while len(_preview_cache) > _PREVIEW_CACHE_MAX:
            _preview_cache.popitem(last=False)


def _preview_cache_clear() -> None:
    with _preview_cache_lock:
        _preview_cache.clear()


def _preview_note_seq(client, seq) -> None:
    """记录某标签页的最新请求序号；非法值忽略。"""
    if not isinstance(client, str) or not client:
        return
    if isinstance(seq, bool) or not isinstance(seq, int):
        return
    with _preview_latest_lock:
        if seq > _preview_latest.get(client, 0):
            _preview_latest[client] = seq
        while len(_preview_latest) > 64:
            _preview_latest.pop(next(iter(_preview_latest)))


def _preview_is_stale(client, seq) -> bool:
    if not isinstance(client, str) or not client:
        return False
    if isinstance(seq, bool) or not isinstance(seq, int):
        return False
    with _preview_latest_lock:
        return _preview_latest.get(client, 0) > seq


def _collect_symbols(text: str) -> dict:
    """从剧本文本扫描已定义的角色名 / 标签名 / 变量名。"""
    return {
        "characters": _RE_CHARACTER.findall(text or ""),
        "labels": _RE_LABEL.findall(text or ""),
        "vars": _RE_SET_VAR.findall(text or ""),
    }


def _completions(line: str, full_text: str = "") -> list:
    """根据当前行 + 全文给出补全候选（前缀匹配，不区分大小写）。"""
    line = line or ""
    # 当前正在输入的 token：取最后一段非空白
    token = ""
    parts = line.rsplit(None, 1)
    if parts:
        token = parts[-1].lstrip("@")
    syms = _collect_symbols(full_text or line)
    candidates: list = []
    # 指令名：去掉前缀 @ 后做匹配
    for d in _DIRECTIVES:
        name = d[1:]
        if not token or name.lower().startswith(token.lower()):
            candidates.append(d)
    # 角色名 / 标签名 / 变量名
    for n in syms["characters"] + syms["labels"] + syms["vars"]:
        if not token or n.lower().startswith(token.lower()):
            candidates.append(n)
    # 去重保序
    seen = set()
    out = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


@dummy_video
def _preview_png(script_path: str, assets_root: str, max_frames: int = 30,
                 cancel=None) -> bytes:
    """无窗口跑剧本 auto 钩子，返回当前帧 PNG bytes。

    用 dummy 视频驱动，复用 Runtime + Renderer（demo.run 内部会关闭 Renderer，
    无法取到截图，故在此自行实现 auto 循环）。pygame 非线程安全，调用方需持锁。
    dummy_video 只在本函数内生效，退出即恢复环境——否则「运行」子进程会继承 dummy。
    """
    from .renderer import Renderer
    from .runtime import Runtime

    rt = Runtime()
    # 预览离屏跑：注入虚拟时钟替代 60FPS 限帧，避免每帧真实睡眠（画面结果不变）
    clock = _FastForwardClock()
    ren = Renderer(assets_root=assets_root,          # T10：画布尺寸从 config.json 读取
                   clock=clock, now_ms=lambda: clock.now)
    png_path = ""
    try:
        rt.load(script_path)
        frames = 0
        while True:
            if cancel is not None and cancel():
                raise _PreviewCancelled()
            state = rt.snapshot()
            ren.render(state)
            if state.get("finished"):
                break
            pc = state.get("pending_choice")
            if pc:
                chosen = False
                for i, o in enumerate(pc.get("options") or []):
                    if o.get("available"):
                        rt.choose(i)
                        chosen = True
                        break
                if not chosen:
                    break  # 全不可选：停在当前帧
            else:
                ren.reveal_all()
                ev = rt.step()
                if ev and ev.get("type") == "sfx":
                    sound = ev.get("sound")
                    if sound:  # 剧本漏写音效名时跳过，避免把 None 传给播放器
                        ren.play_sfx(sound)
            frames += 1
            if max_frames is not None and frames >= max_frames:
                break
        # 最后再画一帧确保画面与状态一致
        ren.render(rt.snapshot())
        png_path = ren.screenshot()
        with open(png_path, "rb") as f:
            return f.read()
    finally:
        ren.close()
        # 清理截图临时文件
        if png_path and os.path.exists(png_path):
            try:
                os.remove(png_path)
            except OSError:
                pass
