# -*- coding: utf-8 -*-
"""P51：1080p 视觉比例（T10 待裁决项的落地——路线 A「按画布高度等比放大」）。

口径：
- UI 尺寸（字号 / 对话框几何 / UI 布局整数 / 立绘贴边）以 720p 为基准书写，
  运行时乘 ui_scale = 画布高 / 720（1080p → 1.5），保证 1080p 下对话框仍占 ~25% 画面高度；
- config.json 写 "ui_scale": 1.0 可关掉等比缩放（等价于「只出 1080 专用预设」那条路）；
- alpha / 纯计数（快捷栏星星数）/ 颜色 / 字符串不缩放。
"""
import json
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")  # 无头模式，须在 import pygame 前生效
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402
import pytest  # noqa: E402

from engine import config as cfgapi  # noqa: E402
from engine.renderer import Renderer  # noqa: E402

pytestmark = [pytest.mark.ui]


def _cfg(canvas=None, **extra) -> cfgapi.Config:
    data = dict(extra)
    if canvas is not None:
        data["canvas_size"] = list(canvas)
    return cfgapi.Config(data)


@pytest.fixture()
def make_renderer(tmp_path):
    opened = []

    def _make(canvas=None, config=None):
        if config is not None:
            (tmp_path / "config.json").write_text(
                json.dumps(config, ensure_ascii=False), encoding="utf-8")
        ren = Renderer(assets_root=str(tmp_path))
        opened.append(ren)
        return ren

    yield _make
    for ren in opened:
        ren.close()


# ==================== 1. 比例系数 ====================

def test_默认720p比例为1():
    cfg = _cfg((1280, 720))
    assert cfg.ui_scale() == 1.0
    assert cfg.font("body") == 28
    assert cfg.dialogue()["height"] == 180


def test_1080p比例为1_5且字号等比():
    cfg = _cfg((1920, 1080))
    assert cfg.ui_scale() == 1.5
    assert cfg.font("body") == 42          # 28 × 1.5
    assert cfg.font("title") == 108        # 72 × 1.5
    assert cfg.font("small") == 33         # 22 × 1.5


def test_1080p对话框几何等比():
    cfg = _cfg((1920, 1080))
    dlg = cfg.dialogue()
    assert dlg["height"] == 270            # 180 × 1.5：1080p 下仍占 25% 画面高
    assert dlg["margin"] == 36             # 24 × 1.5
    assert dlg["name_y"] == 18             # 12 × 1.5
    curtain = dlg["curtain"]
    assert curtain["capture_height"] == 36  # 24 × 1.5
    assert curtain["symbol_size"] == 15     # 10 × 1.5
    # 非几何量不缩放
    assert dlg["bg_alpha"] == 150
    assert dlg["align"] == "left"
    assert curtain["symbol"] == "."


def test_显式ui_scale_1关闭缩放():
    cfg = _cfg((1920, 1080), ui_scale=1.0)
    assert cfg.ui_scale() == 1.0
    assert cfg.font("body") == 28
    assert cfg.dialogue()["height"] == 180


def test_非法ui_scale回落自动并夹到范围():
    assert _cfg((1920, 1080), ui_scale="大").ui_scale() == 1.5
    assert _cfg((1920, 1080), ui_scale=100).ui_scale() == 4.0
    assert _cfg((1920, 1080), ui_scale=0.01).ui_scale() == 0.5


# ==================== 2. 渲染层布局跟随比例 ====================

def test_1080p的UI布局整数按比例放大(make_renderer):
    ren = make_renderer(config={"canvas_size": [1920, 1080]})
    assert ren.size == (1920, 1080)
    assert ren._ui_scale == 1.5
    assert ren._ui_int("quickbar", "button_width", 64, 40, 180) == 96          # 64 × 1.5
    assert ren._ui_int("choices", "width", 420, 240, 1840) == 630              # 420 × 1.5
    # 非长度参数不缩放
    assert ren._ui_int("quickbar", "alpha", 185, 0, 255, scale=False) == 185
    assert ren._ui_int("title", "stars", 36, scale=False) == 36


def test_720p的UI布局整数不变(make_renderer):
    ren = make_renderer()
    assert ren._ui_scale == 1.0
    assert ren._ui_int("quickbar", "button_width", 64, 40, 180) == 64


def test_1080p对话框顶边与余量按比例(make_renderer):
    ren = make_renderer(config={"canvas_size": [1920, 1080]})
    height = int(ren.config.dialogue("default")["height"])
    assert height == 270
    assert ren._dialog_top() == 1080 - height       # 810：对话框仍占画面下方 25%
    layout = ren._dialog_layout(
        [{"char": "林晚", "text": "1080p 的对话框高度应该占画面约四分之一。"}],
        {"林晚": {"color": "#aaccff", "kind": "default"}}, False)
    assert layout["margin"] == 36
    ren._draw_dialog([{"char": "林晚", "text": "1080p 排版冒烟。"}],
                     {"林晚": {"color": "#aaccff", "kind": "default"}}, False)
    assert ren._screen.get_size() == (1920, 1080)


def test_1080p立绘贴边留白按比例(make_renderer):
    ren = make_renderer(config={"canvas_size": [1920, 1080]})
    rect = ren._sprite_rect((400, 800), {"pos": "左"}, 0, 1)
    assert rect.x == 30                                # SPRITE_MARGIN 20 × 1.5


def test_配置热重载切换ui_scale后布局跟着变(make_renderer, tmp_path):
    ren = make_renderer()
    assert ren._ui_int("quickbar", "button_width", 64, 40, 180) == 64
    (tmp_path / "config.json").write_text(
        json.dumps({"canvas_size": [1920, 1080]}), encoding="utf-8")
    new_cfg = cfgapi.load(str(tmp_path))
    # 画布变了：热应用返回 False（需重启），但显式指定 ui_scale 的场景必须能热应用
    assert ren.apply_config(new_cfg) is False
    (tmp_path / "config.json").write_text(
        json.dumps({"ui_scale": 1.5}), encoding="utf-8")
    assert ren.apply_config(cfgapi.load(str(tmp_path))) is True
    assert ren._ui_scale == 1.5
    assert ren._ui_int("quickbar", "button_width", 64, 40, 180) == 96
