# -*- coding: utf-8 -*-
"""P51-T10 验收：逻辑画布分辨率可配（路线图·平台基础，默认 1280×720，预留 1920×1080）。

覆盖：
1. `Config.canvas_size()`：默认值 / 合法自定义 / 非法值（类型、长度、越界）回落默认
2. Renderer 不传 size 时读 config.json 的 canvas_size；显式 size 仍优先（旧调用零变化）
3. 1080p 下布局跟随画布：对话框顶边、对齐基准、全屏遮罩尺寸都按画布算
4. 物理窗口 ≠ 逻辑画布时等比 letterbox（不拉伸），鼠标坐标换算回逻辑画布
5. 默认配置下行为与旧版完全一致（1280×720）
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

DIALOG = [{"char": "林晚", "text": "分辨率改成 1920×1080 之后，这句台词的排版仍然正确。"}]
CHARACTERS = {"林晚": {"color": "#aaccff", "kind": "default"}}


def _write_config(root, data):
    (root / "config.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


@pytest.fixture()
def make_renderer(tmp_path):
    """按需写 config.json/settings.json 再建 Renderer；用例结束统一 close。"""
    opened = []

    def _make(canvas=None, size=None, settings=None):
        if canvas is not None:
            _write_config(tmp_path, {"canvas_size": canvas})
        if settings is not None:
            (tmp_path / "settings.json").write_text(
                json.dumps(settings, ensure_ascii=False), encoding="utf-8")
        ren = Renderer(size=size, assets_root=str(tmp_path))
        opened.append(ren)
        return ren

    yield _make
    for ren in opened:
        ren.close()


# ==================== 1. 配置读取 ====================

def test_未配置时默认1280x720(tmp_path):
    assert cfgapi.load(str(tmp_path)).canvas_size() == (1280, 720)


@pytest.mark.parametrize("raw,expected", [
    ([1920, 1080], (1920, 1080)),
    ([1366, 768], (1366, 768)),
    ([640, 360], (640, 360)),        # 下限（含边界）
    ([7680, 4320], (7680, 4320)),    # 上限（含边界）
    ([1920.0, 1080.0], (1920, 1080)),  # JSON 里的浮点写法宽容转换
])
def test_合法画布尺寸(tmp_path, raw, expected):
    _write_config(tmp_path, {"canvas_size": raw})
    assert cfgapi.load(str(tmp_path)).canvas_size() == expected


@pytest.mark.parametrize("raw", [
    None, "1920x1080", [1920], [1920, 1080, 720], [639, 360], [1920, 359],
    [7681, 1080], [1920, 4321], ["宽", "高"], [True, False],
])
def test_非法画布尺寸回落默认(tmp_path, raw):
    _write_config(tmp_path, {"canvas_size": raw})
    assert cfgapi.load(str(tmp_path)).canvas_size() == (1280, 720)


# ==================== 2. Renderer 读取画布 ====================

def test_不传size时读配置画布(make_renderer):
    ren = make_renderer(canvas=[1920, 1080])
    assert ren.size == (1920, 1080)
    assert ren._screen.get_size() == (1920, 1080)
    assert ren._view.size == (1920, 1080)


def test_显式size优先于配置(make_renderer):
    ren = make_renderer(canvas=[1920, 1080], size=(1280, 720))
    assert ren.size == (1280, 720)
    assert ren._screen.get_size() == (1280, 720)


def test_默认画布行为不变(make_renderer):
    ren = make_renderer()
    assert ren.size == (1280, 720)


def test_窗口尺寸非法时回落到画布尺寸(make_renderer):
    ren = make_renderer(canvas=[1920, 1080], settings={"window_size": ["坏", "值"]})
    assert ren._window_size == (1920, 1080)


# ==================== 3. 布局跟随画布 ====================

def test_1080p对话框顶边与对齐按画布计算(make_renderer):
    ren = make_renderer(canvas=[1920, 1080])
    height = int(ren.config.dialogue("default").get("height", 180))
    assert ren._dialog_top() == 1080 - height
    assert ren._rich_line_x("center", 400, 24) == (1920 - 400) // 2
    assert ren._rich_line_x("right", 400, 24) == 1920 - 24 - 400
    assert ren._rich_line_x("left", 400, 24) == 24


def test_1080p对话绘制不越界(make_renderer):
    ren = make_renderer(canvas=[1920, 1080])
    ren._tw_text = DIALOG[0]["text"]
    ren._tw_shown = float(len(DIALOG[0]["text"]))
    layout = ren._dialog_layout(DIALOG, CHARACTERS, False)
    assert 0 < layout["start_y"] < 1080
    assert layout["margin"] == int(ren.config.dialogue("default").get("margin", 24))
    ren._draw_dialog(DIALOG, CHARACTERS, False)  # 冒烟：整屏 1080p 绘制不崩
    assert ren._screen.get_size() == (1920, 1080)


# ==================== 4. letterbox 与坐标换算（不拉伸） ====================

def test_不等比窗口按等比letterbox且不拉伸(make_renderer):
    ren = make_renderer(canvas=[1920, 1080], settings={"window_size": [1000, 1000]})
    ren._present()
    view = ren._view
    # 等比缩放：宽高比仍为 16:9（允许 1px 取整误差）
    assert abs(view.width / view.height - 1920 / 1080) < 0.01
    assert view.center == (500, 500)          # 居中，左右/上下黑边对称


def test_窗口坐标换算回1080p画布(make_renderer):
    ren = make_renderer(canvas=[1920, 1080], settings={"window_size": [1280, 720]})
    ren._present()
    assert ren._to_canvas((ren._view.centerx, ren._view.centery)) == (960, 540)
    assert ren._to_canvas((ren._view.x, ren._view.y)) == (0, 0)


def test_画布与窗口同尺寸时直出(make_renderer):
    ren = make_renderer(canvas=[1920, 1080], settings={"window_size": [1920, 1080]})
    ren._present()
    assert ren._view.size == (1920, 1080)
    assert ren._to_canvas((960, 540)) == (960, 540)


# ==================== 5. 编辑器/演示入口走同一配置 ====================

def test_编辑器预览与演示入口不再硬编码1280x720():
    """静态检查：两处入口必须用 Renderer(assets_root=...) 让 config 生效。"""
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    for rel in ("engine/demo.py", "engine/editor.py"):
        text = (root / rel).read_text(encoding="utf-8")
        assert "Renderer(assets_root=" in text, f"{rel} 未走 config 画布"
        assert "Renderer((1280, 720)" not in text, f"{rel} 仍硬编码 1280×720"
