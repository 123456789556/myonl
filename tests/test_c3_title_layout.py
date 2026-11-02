# -*- coding: utf-8 -*-
"""C3：标题排版配置——对齐/字号/字距/菜单间距/上下留白全部走 config。"""
from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

from engine.renderer import Renderer

pytestmark = [pytest.mark.ui]


def test_左列标题走配置坐标(tmp_path):
    ren = Renderer(size=(1280, 720), assets_root=str(tmp_path))
    try:
        ren.config.data["ui"] = {"title": {"align": "left", "left_x": 120, "logo_y": 88}}
        ren.settings["title_text_visible"] = True
        ren.settings["title_text_y"] = 200
        layout = ren._title_layout(has_bg=False)
        assert layout["left"] is True
        assert layout["x"] == 120
        assert layout["y"] == 200  # title_text_y 优先于 logo_y（左列不再写死 70）
    finally:
        ren.close()


def test_居中标题用logo_y(tmp_path):
    ren = Renderer(size=(1280, 720), assets_root=str(tmp_path))
    try:
        ren.config.data["ui"] = {"title": {"align": "center", "logo_y": 132}}
        ren.settings.pop("title_text_y", None)
        ren.settings["title_text_visible"] = True
        layout = ren._title_layout(has_bg=False)
        assert layout["left"] is False
        assert layout["y"] == 132
    finally:
        ren.close()


def test_菜单几何来自配置(tmp_path):
    ren = Renderer(size=(1280, 720), assets_root=str(tmp_path))
    try:
        ren.config.data["ui"] = {"title": {"menu_top": 260, "menu_row_height": 60, "menu_width": 300}}
        layout = ren._title_layout(has_bg=True)
        assert layout["menu_top"] == 260
        assert layout["menu_row_height"] == 60
        assert layout["menu_width"] == 300
    finally:
        ren.close()
