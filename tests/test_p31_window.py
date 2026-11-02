"""tests/test_p31_window.py：P31-a 窗口可缩放验收（无头 dummy 模式）。

覆盖：
1. 逻辑画布恒为 1280×720，窗口尺寸独立可变（缩放不改构图）
2. 拖拽缩放：窗口跟随、等比 letterbox、黑边居中
3. 窗口尺寸/全屏状态写入 settings.json，下次启动沿用
4. 非法/过小尺寸回落（下限 640×360，非法值回 1280×720）
5. 缩放后鼠标坐标换算回逻辑画布，选项点击仍命中
"""

import json
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")  # 无头模式，须在 import pygame 前生效
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402
import pytest  # noqa: E402

from engine import data  # noqa: E402
from engine.renderer import Renderer  # noqa: E402

pytestmark = [pytest.mark.ui]


@pytest.fixture()
def ren(tmp_path):
    r = Renderer((1280, 720), str(tmp_path))
    yield r
    r.close()


def test_逻辑画布固定_窗口可变(ren):
    """缩放只改窗口，不改逻辑画布——所有既有构图常量继续生效。"""
    assert ren.size == (1280, 720)
    ren.resize(1920, 1080)
    assert ren.size == (1280, 720)
    assert ren._screen.get_size() == (1280, 720)
    assert ren._window.get_size() == (1920, 1080)


def test_等比letterbox与黑边居中(ren):
    """1920×1080 满幅；1000×1000 上下留黑边且水平居中。"""
    ren.resize(1920, 1080)
    ren._present()
    assert tuple(ren._view) == (0, 0, 1920, 1080)

    ren.resize(1000, 1000)
    ren._present()
    v = ren._view
    assert (v.width, v.height) == (1000, 562)  # 1000 * 720/1280 = 562.5 → 562
    assert v.x == 0
    assert v.y == (1000 - 562) // 2  # 上下黑边等分


def test_窗口尺寸写入设置_下次启动沿用(tmp_path):
    """resize 后 settings.json 落下 window_size，下次构造 Renderer 直接沿用。"""
    r = Renderer((1280, 720), str(tmp_path))
    try:
        r.resize(1600, 900)
    finally:
        r.close()
    with open(os.path.join(str(tmp_path), "settings.json"), "r", encoding="utf-8") as f:
        saved = json.load(f)
    assert saved["window_size"] == [1600, 900]
    assert saved["fullscreen"] is False

    r2 = Renderer((1280, 720), str(tmp_path))
    try:
        assert r2._window.get_size() == (1600, 900)
    finally:
        r2.close()


def test_过小与非法尺寸回落(ren):
    """下限 640×360；非数值回落默认 1280×720。"""
    ren.resize(100, 100)
    assert ren._window.get_size() == (640, 360)
    assert ren._clamp_window_size("abc") == (1280, 720)
    assert ren._clamp_window_size([None, 300]) == (1280, 720)
    assert ren._clamp_window_size([2000, 10]) == (2000, 360)


def test_缩放后鼠标坐标换算(ren):
    """窗口坐标 → 逻辑画布坐标（letterbox 偏移要扣掉）。"""
    ren.resize(1920, 1080)
    ren._present()
    assert ren._to_canvas((960, 540)) == (640, 360)
    assert ren._to_canvas((0, 0)) == (0, 0)


def test_缩放窗口下选项点击仍命中(ren):
    """1920×1080 窗口里点逻辑 (200,120)，应命中该选项。"""
    ren._ui_mode = "playing"
    ren._options = [{"text": "选项一", "enabled": True}]
    ren._choice_rects = [(pygame.Rect(100, 100, 200, 40), 0, True)]
    ren._choice_index = 0
    ren._choice_lock_t0 = None
    ren.resize(1920, 1080)
    ren._present()  # 建立缩放映射
    pygame.event.post(pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, {"pos": (300, 180), "button": 1}))
    assert ren.handle_input() == {"action": "choose", "index": 0}


def test_全屏切换不崩且不改画布(ren):
    """无头环境下切换全屏：逻辑画布不变（失败则静默回退）。"""
    ren.toggle_fullscreen()
    assert ren.size == (1280, 720)
    ren.toggle_fullscreen()
    assert ren.size == (1280, 720)


def test_存设置不丢引擎未知键(tmp_path):
    """P31-c：save_settings 不能把 title 这类项目自定义键丢掉（改一次设置就抹掉是真事故）。"""
    p = os.path.join(str(tmp_path), "settings.json")
    data.save_settings({"title": "月光漫步", "text_speed": 42, "title_text_y": 96}, p)
    s = data.load_settings(p)
    assert s["title"] == "月光漫步"
    assert s["title_text_y"] == 96
    assert s["text_speed"] == 42


def test_缩放窗口后自定义键仍在(tmp_path):
    """拖一次窗口只应新增 window_size，不能顺带改掉游戏标题。"""
    p = os.path.join(str(tmp_path), "settings.json")
    data.save_settings({"title": "月光漫步"}, p)
    r = Renderer((1280, 720), str(tmp_path))
    try:
        r.resize(1600, 900)
    finally:
        r.close()
    s = data.load_settings(p)
    assert s["title"] == "月光漫步"
    assert s["window_size"] == [1600, 900]
