# -*- coding: utf-8 -*-
"""C2：选项与对话框间距（ui.choices.dialog_gap）参数化 + 旧配置兼容。"""
from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest
import pygame

from engine.renderer import Renderer
from engine.render_utils import DIALOG_TOP

pytestmark = [pytest.mark.ui]


def _render_choices(ren):
    ren._options = [{"text": "选项一"}, {"text": "选项二"}]
    ren._choice_index = 0
    ren.render({"history": [], "pending_choice": {"options": ren._options}}, {"mode": "playing"})
    return max(r.bottom for r, _, _ in ren._choice_rects)


def test_默认间距40(tmp_path):
    ren = Renderer(size=(1280, 720), assets_root=str(tmp_path))
    try:
        bottom = _render_choices(ren)
        assert bottom == DIALOG_TOP - 40 - 6
    finally:
        ren.close()


def test_可配置间距(tmp_path):
    ren = Renderer(size=(1280, 720), assets_root=str(tmp_path))
    try:
        ren.config.data["ui"] = {"choices": {"dialog_gap": 80}}
        bottom = _render_choices(ren)
        assert bottom == DIALOG_TOP - 80 - 6
    finally:
        ren.close()


def test_旧配置gap仍兼容(tmp_path):
    ren = Renderer(size=(1280, 720), assets_root=str(tmp_path))
    try:
        ren.config.data["ui"] = {"choices": {"gap": 24}}
        bottom = _render_choices(ren)
        assert bottom == DIALOG_TOP - 24 - 6
    finally:
        ren.close()


def test_间距随ui_scale放大(tmp_path):
    from engine import config as cfgapi

    ren = Renderer(size=(1920, 1080), assets_root=str(tmp_path))
    try:
        # 画布尺寸来自 config（默认 1280×720）；改成 1920×1080 后 ui_scale=1.5
        ren.config.data["canvas_size"] = [1920, 1080]
        ren._ui_scale = 1.5  # 模拟 config.ui_scale()（Renderer 初始化时缓存）
        bottom = _render_choices(ren)
        expected = ren._dialog_top() - int(40 * 1.5) - 6
        assert abs(bottom - expected) <= 2
    finally:
        ren.close()
