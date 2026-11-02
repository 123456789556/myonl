# -*- coding: utf-8 -*-
"""tests/test_p34_window.py：P34 窗口自检验收（屏幕外/最小化特征坐标强制还原居中）。

背景：Windows 多显示器/DPI 环境下 SDL 居中计算偶发异常，窗口被放到
-32000（Windows 最小化窗口的典型坐标），表现为"进程在跑但看不到窗口"。
引擎启动/切全屏后自检：命中特征坐标 → set_window_position 强制居中，
Windows 下再走 WinAPI IsIconic/SW_RESTORE 兜底（无头测试不覆盖该分支）。
"""
from __future__ import annotations

import os

import pygame
import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from engine.renderer import Renderer  # noqa: E402

pytestmark = [pytest.mark.ui]


def _make_renderer(monkeypatch, pos, moved):
    """构造 Renderer 并注入假的窗口位置读取/写入。返回 (renderer, moved)。"""
    monkeypatch.setattr(pygame.display, "get_window_position", lambda: pos, raising=False)

    def fake_set(pos2):
        moved.append(tuple(pos2))

    monkeypatch.setattr(pygame.display, "set_window_position", fake_set, raising=False)
    return Renderer((1280, 720), "."), moved


def test_最小化特征坐标_32000_强制居中(monkeypatch):
    moved: list = []
    monkeypatch.setattr(pygame.display, "get_window_position",
                        lambda: (-32000, -32000), raising=False)
    monkeypatch.setattr(pygame.display, "set_window_position",
                        lambda p: moved.append(tuple(p)), raising=False)
    r = Renderer((1280, 720), ".")
    r._ensure_window_sane()
    assert moved, "屏幕外特征坐标必须触发纠偏"
    nx, ny = moved[0]
    assert nx >= 0 and ny >= 0, "纠偏后的窗口位置必须在主屏内"


def test_正常坐标不动(monkeypatch):
    moved: list = []
    monkeypatch.setattr(pygame.display, "get_window_position",
                        lambda: (100, 80), raising=False)
    monkeypatch.setattr(pygame.display, "set_window_position",
                        lambda p: moved.append(tuple(p)), raising=False)
    r = Renderer((1280, 720), ".")
    r._ensure_window_sane()
    assert moved == [], "正常窗口位置不得被移动"


def test_副屏合法负坐标不动(monkeypatch):
    moved: list = []
    monkeypatch.setattr(pygame.display, "get_window_position",
                        lambda: (-1920, 0), raising=False)
    monkeypatch.setattr(pygame.display, "set_window_position",
                        lambda p: moved.append(tuple(p)), raising=False)
    r = Renderer((1280, 720), ".")
    r._ensure_window_sane()
    assert moved == [], "多显示器副屏的合法负坐标不得被误伤"


def test_切全屏后同样自检(monkeypatch):
    seq = {"calls": 0}

    def fake_pos():
        seq["calls"] += 1
        return (-32000, -32000)

    moved: list = []
    monkeypatch.setattr(pygame.display, "get_window_position", fake_pos, raising=False)
    monkeypatch.setattr(pygame.display, "set_window_position",
                        lambda p: moved.append(tuple(p)), raising=False)
    r = Renderer((1280, 720), ".")
    before = seq["calls"]
    r.toggle_fullscreen()
    assert seq["calls"] > before, "toggle_fullscreen 后应再跑一次窗口自检"
    assert moved, "切全屏后命中特征坐标也应纠偏"


def test_API缺失安全跳过(monkeypatch):
    # 模拟旧 pygame 无 get_window_position API：自检必须静默跳过不崩
    monkeypatch.delattr(pygame.display, "get_window_position", raising=False)
    monkeypatch.delattr(pygame.display, "set_window_position", raising=False)
    r = Renderer((1280, 720), ".")  # __init__ 内的自检不应抛错
    r._ensure_window_sane()  # 直接调用也应安全
