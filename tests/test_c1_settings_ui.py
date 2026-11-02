# -*- coding: utf-8 -*-
"""C1：游戏设置页视觉——内容卡片 + 分组标题 + 上下文提示。"""
from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

from engine.renderer import Renderer
from engine.ui import UI

pytestmark = [pytest.mark.ui]


def test_提示按页变化(tmp_path):
    ren = Renderer(size=(1280, 720), assets_root=str(tmp_path))
    try:
        assert "滑条可拖动" in ren._settings_hint(
            [{"kind": "volume"}, {"kind": "switch"}])
        assert "滑条可拖动" not in ren._settings_hint(
            [{"kind": "switch"}, {"kind": "choice"}])
    finally:
        ren.close()


def test_设置页可渲染且分页正常(tmp_path):
    ren = Renderer(size=(1280, 720), assets_root=str(tmp_path))
    ui = UI()
    ui.mode = "settings"
    try:
        view = ui.view()
        assert view["mode"] == "settings"
        assert len(view.get("settings_groups") or []) >= 3
        ren.render({}, view)          # 第一页
        ui.handle("down")
        ui.handle("down")
        ren.render({}, ui.view())     # 第二页
    finally:
        ren.close()
