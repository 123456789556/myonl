"""MYONL 渲染层 · 窗口管理（缩放/全屏/落盘/坐标换算）（renderer.py 模块化拆分）。

WindowMixin 的方法原样迁自 engine/renderer.py：方法体与签名不变，
经 self 访问实例状态（__init__ 中初始化）与其他 Mixin 方法；
常量与纯函数统一来自 render_utils（engine.renderer 再导出，命名空间不变）。
"""
from __future__ import annotations

import pygame
import os
import sys
import time
from typing import TYPE_CHECKING, Any
from . import data


class WindowMixin:
    """窗口管理（缩放/全屏/落盘/坐标换算）方法集（经多继承组合进 Renderer，见 engine/renderer.py）。"""

    if TYPE_CHECKING:  # pragma: no cover - 仅供 pyright：宿主 Renderer 提供的属性
        size: tuple[int, int]
        settings: dict
        assets_root: str
        _screen: pygame.Surface
        _ui_hits: list[tuple[pygame.Rect, dict]]
        _ui_mode: str | None
        _options: list | None
        _choice_lock_t0: int | None
        _advance_or_reveal: Any
        _choice_at: Any
        _now_ms: Any

    _DISPLAY_MODES = ("window", "borderless", "fullscreen")

    def toggle_fullscreen(self) -> None:
        """⑮ 切换全屏/窗口化（无头环境失败则静默回退）。逻辑画布尺寸不变（T10 可配）。"""
        want = not self._fullscreen
        self._borderless = False  # F11 从任何模式切回「全屏 ↔ 窗口」，不保留无边框
        try:
            self._window = self._open_window(fullscreen=want)
            self._ensure_window_sane()  # P34：切全屏后同样自检
            self._fullscreen = want
        except pygame.error:
            self._fullscreen = False
        self.settings["display_mode"] = "fullscreen" if self._fullscreen else "window"
        self._persist_window_throttled()

    def apply_display_mode(self, mode) -> bool:
        """M1.5：应用玩家选择的显示模式（窗口 / 无边框全屏 / 全屏）。

        失败（无头环境、SDL 拒绝）保留原状态并返回 False，不崩。
        """
        mode = str(mode or "window").strip().lower()
        if mode not in self._DISPLAY_MODES:
            return False
        old_fs, old_borderless = self._fullscreen, getattr(self, "_borderless", False)
        self._fullscreen = mode == "fullscreen"
        self._borderless = mode == "borderless"
        try:
            self._window = self._open_window()
            self._ensure_window_sane()
        except pygame.error:
            self._fullscreen, self._borderless = old_fs, old_borderless
            return False
        self.settings["display_mode"] = mode
        self.settings["fullscreen"] = bool(self._fullscreen)
        self._persist_window()
        return True

    def resize(self, w: int, h: int) -> None:
        """P31-a：窗口拖拽缩放。逻辑画布不变，等比缩放进窗口（多余区域留黑边）。"""
        if self._fullscreen:
            return
        w, h = self._clamp_window_size((w, h))
        if (w, h) == tuple(self._window.get_size()):
            return
        try:
            self._window = pygame.display.set_mode((w, h), pygame.RESIZABLE)
        except pygame.error:
            return
        self._window_size = (w, h)
        self._persist_window_throttled()

    def _open_window(self, fullscreen=None):
        """创建真实窗口；fullscreen 省略时沿用当前状态。"""
        fs = self._fullscreen if fullscreen is None else fullscreen
        if fs:
            info = pygame.display.Info()
            w = info.current_w or self.size[0]
            h = info.current_h or self.size[1]
            return pygame.display.set_mode((w, h), pygame.FULLSCREEN)
        if getattr(self, "_borderless", False):
            info = pygame.display.Info()
            w = info.current_w or self.size[0]
            h = info.current_h or self.size[1]
            return pygame.display.set_mode((w, h), pygame.NOFRAME)
        return pygame.display.set_mode(tuple(self._window_size), pygame.RESIZABLE)

    def _ensure_window_sane(self) -> None:
        """P34：窗口创建后自检——屏幕外/最小化特征坐标（如 -32000）强制还原居中。

        背景：Windows 多显示器/DPI 环境下，SDL 居中计算偶发异常，窗口被放到
        -32000（Windows 最小化窗口的典型坐标），表现为"进程在跑但看不到窗口"。
        引擎不保存窗口位置（只存尺寸/全屏），故该状态必然来自系统侧，这里兜底。
        多显示器副屏的合法负坐标（如 -1920）远大于 -20000，不会被误伤。
        """
        try:
            pos = pygame.display.get_window_position()
        except (pygame.error, AttributeError):
            return  # 无头 dummy 或旧 API：跳过
        try:
            x, y = int(pos[0]), int(pos[1])
        except (TypeError, ValueError, IndexError):
            return
        if -20000 < x < 20000 and -20000 < y < 20000:
            return  # 正常范围（含多屏负坐标），不动
        try:
            info = pygame.display.Info()
            nx = max(0, (info.current_w or self.size[0]) - self._window_size[0]) // 2
            ny = max(0, (info.current_h or self.size[1]) - self._window_size[1]) // 2
            pygame.display.set_window_position((nx, ny))
        except (pygame.error, AttributeError):
            pass
        if sys.platform == "win32":
            try:
                import ctypes
                user32 = ctypes.windll.user32
                hwnd = user32.GetActiveWindow()
                if hwnd and user32.IsIconic(hwnd):
                    user32.ShowWindow(hwnd, 9)  # SW_RESTORE：最小化则还原
            except Exception:
                pass  # WinAPI 不可用不影响运行（SDL 层已纠偏）

    def _clamp_window_size(self, value) -> tuple:
        """窗口尺寸：非法值回落 1280×720，下限 640×360（再小字看不清）。"""
        try:
            w, h = int(value[0]), int(value[1])
        except (TypeError, ValueError, IndexError, KeyError):
            w, h = self.size
        return max(640, min(w, 7680)), max(360, min(h, 4320))

    def _persist_window(self) -> None:
        """窗口尺寸/全屏状态写回 settings.json（下次启动沿用）。"""
        self.settings["window_size"] = [int(self._window_size[0]), int(self._window_size[1])]
        self.settings["fullscreen"] = bool(self._fullscreen)
        if self._fullscreen:
            self.settings["display_mode"] = "fullscreen"
        elif getattr(self, "_borderless", False):
            self.settings["display_mode"] = "borderless"
        else:
            self.settings["display_mode"] = "window"
        try:
            data.save_settings(self.settings, os.path.join(self.assets_root, "settings.json"))
        except OSError:
            pass
        self._window_dirty = False

    def _persist_window_throttled(self) -> None:
        """拖拽缩放会连发大量 resize 事件：最多每 500ms 落盘一次，退出时再补写一次。"""
        self._window_dirty = True
        now = pygame.time.get_ticks()
        if now - self._window_persist_t0 < 500:
            return
        self._window_persist_t0 = now
        self._persist_window()

    def _ensure_window_visible(self) -> None:
        """P33-b：Windows 下强制游戏窗口可见可交互。

        部分机型（联想/双显卡等）pygame 窗口创建后可能落在最小化/屏幕外
        （坐标 -32000/-32000 或 IsIconic=True），玩家完全看不到窗口。
        这里用 Win32 检测异常位置/最小化态并恢复置前；非 Windows 或失败静默跳过。
        """
        if os.name != "nt":
            return
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            hwnd = pygame.display.get_wm_info().get("window")
            if not hwnd:
                return
            rect = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            if rect.left <= -10000 or rect.top <= -10000 or user32.IsIconic(hwnd):
                user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                user32.SetForegroundWindow(hwnd)
                user32.GetWindowRect(hwnd, ctypes.byref(rect))
                if rect.left < 0 or rect.top < 0 or rect.left >= 5000:
                    # 仍停在屏幕外 → 搬回主屏左上（不改变用户手动摆放）
                    user32.MoveWindow(hwnd, 40, 40, self.size[0], self.size[1], True)
        except Exception:
            pass  # 窗口管理失败不影响游戏运行

    def _present(self) -> None:
        """P31-a：把逻辑画布等比缩放居中到窗口（黑边 letterbox）后 flip。

        性能优化：窗口尺寸与逻辑画布不同时使用 pygame.transform.scale（快速最近邻）
        而非 smoothscale（高质量但慢），保证 60fps 下不卡顿。视觉小说画面变化频率低，
        画质差异在正常观看距离下几乎不可感知。
        """
        ww, wh = self._window.get_size()
        lw, lh = self.size
        if (ww, wh) == (lw, lh):
            self._window.blit(self._screen, (0, 0))
            self._view = pygame.Rect(0, 0, lw, lh)
        else:
            scale = min(ww / lw, wh / lh)
            dw, dh = max(1, int(round(lw * scale))), max(1, int(round(lh * scale)))
            x, y = (ww - dw) // 2, (wh - dh) // 2
            self._window.fill((0, 0, 0))
            self._window.blit(pygame.transform.scale(self._screen, (dw, dh)), (x, y))
            self._view = pygame.Rect(x, y, dw, dh)
        pygame.display.flip()

    def _ui_hit_at(self, pos):
        """P31-b：UI 层命中检测（后画者优先，即上层覆盖下层）。"""
        for rect, payload in reversed(self._ui_hits):
            if rect.collidepoint(pos):
                return payload
        return None

    def _set_window_icon(self) -> None:
        """用工程根/ images 下的 icon.png 覆盖窗口与任务栏图标。

        发行版用通用玩家模板打包游戏，exe 文件图标改不了；窗口图标能改，
        至少让玩家在任务栏看到自己作品的图标。
        """
        for rel in ("icon.png", os.path.join("images", "icon.png")):
            path = os.path.join(self.assets_root, rel)
            if not os.path.isfile(path):
                continue
            try:
                pygame.display.set_icon(pygame.image.load(path))
            except (pygame.error, OSError):
                pass
            return

    def _mouse_down_action(self, ev):
        """鼠标左键按下 → 统一动作（UI 点击 / 选项 / 推进 / None）。

        - UI 覆盖态：命中可点区域就交 ui 判定语义；
        - playing：快捷栏 / ◀ 回看 / ▼ 推进等控件优先（之前鼠标只会推进剧情，
          看得见却点不动）；未命中控件再按选项或推进处理。
        """
        pos = self._to_canvas(ev.pos)
        hit = self._ui_hit_at(pos)
        kind = (hit or {}).get("kind")
        if self._ui_mode not in (None, "playing"):
            return ({"action": "click", "hit": hit, "pos": pos}
                    if hit is not None else None)
        if kind in ("quickbar", "prev_arrow", "toggle_subtitles"):
            return {"action": "click", "hit": hit, "pos": pos}
        if kind == "next_arrow" and self._options is None:
            return self._advance_or_reveal()
        if self._options is not None:
            t0 = self._choice_lock_t0
            if t0 is None or not (t0 <= self._now_ms() < t0 + 250):
                idx = self._choice_at(pos)
                if idx is not None:
                    return {"action": "choose", "index": idx}
            return None
        return self._advance_or_reveal()

    def _to_canvas(self, pos) -> tuple:
        """窗口坐标 → 逻辑画布坐标（鼠标命中判定用）。"""
        v = self._view
        if v.width <= 0 or v.height <= 0:
            return tuple(pos)
        x = int((pos[0] - v.x) * self.size[0] / v.width)
        y = int((pos[1] - v.y) * self.size[1] / v.height)
        return (x, y)
