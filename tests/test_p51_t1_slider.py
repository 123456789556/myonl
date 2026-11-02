"""P51-T1 音量滑条交互回归测试：点击/拖动定值链路（引擎默认→项目→玩家三层之后）。

覆盖：
1. 设置页"音频"组渲染后，两个音量滑条 hit 的 bar 几何与绘制一致
2. 点滑条左/中/右 → settings_set value = 0.0 / 0.5 / 1.0（点左不会往右跳）
3. 真实 handle_input 事件：MOUSEBUTTONDOWN 点滑条左端 → click 命中 settings_slider
4. demo._apply_business 应用 settings_set 写回 settings.json（0.0~1.0 钳制）
"""

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")  # 无头，须在 import pygame 前
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402
import pytest  # noqa: E402

from engine import data as data_api  # noqa: E402
from engine.demo import _apply_business  # noqa: E402
from engine.renderer import Renderer  # noqa: E402
from engine.ui import UI  # noqa: E402

pytestmark = [pytest.mark.ui]

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT = os.path.join(REPO, "games", "新游戏")


@pytest.fixture()
def audio_settings_page():
    """渲染到"音频"组并收集音量滑条 hit，返回 (ren, ui, sliders)。"""
    ren = Renderer(assets_root=PROJECT)
    ui = UI()
    ui.mode = "settings"
    view = ui.view()
    # 切到音频组（settings_nav 点击）
    for i, it in enumerate(view.get("items") or []):
        if (it.get("group") or "基础") == "音频":
            ui.click({"kind": "settings_nav", "index": i})
            break
    view = ui.view()
    ren.render({}, view)
    sliders = [(r, p) for r, p in ren._ui_hits
               if p.get("kind") == "settings_slider"]
    return ren, ui, sliders


def test_t1_音频页渲染出两个音量滑条(audio_settings_page):
    """音频组页面上必须有 bgm_volume 和 sfx_volume 两个滑条（可点可拖）。"""
    _, _, sliders = audio_settings_page
    keys = sorted(p["key"] for _, p in sliders)
    assert keys == ["bgm_volume", "sfx_volume"]
    for rect, hit in sliders:
        bx, bw = hit["bar"]
        assert bw > 0
        assert bx >= 0
        # bar 几何与命中 rect 左端一致（可点击区域覆盖滑条本体）
        assert rect.x <= bx and rect.right >= bx + bw


def test_t1_点滑条左中右按比例定值(audio_settings_page):
    """点左端=0、中间=0.5、右端=1.0——点左不会往右跳（用户点名 bug 回归）。"""
    _, ui, sliders = audio_settings_page
    for rect, hit in sliders:
        bx, bw = hit["bar"]
        for frac, expect in ((0.0, 0.0), (0.5, 0.5), (1.0, 1.0)):
            pos = (int(bx + bw * frac), rect.centery)
            act = ui.click(hit, pos=pos)
            assert act == {"action": "settings_set", "key": hit["key"],
                           "value": expect}, f"{hit['key']} 点{frac}位置错"


def test_t1_真实事件链路点击命中滑条(audio_settings_page):
    """MOUSEBUTTONDOWN 点滑条左端 → handle_input 返回 click + 命中 settings_slider。"""
    ren, _, sliders = audio_settings_page
    bgm = next((r, p) for r, p in sliders if p["key"] == "bgm_volume")
    rect, hit = bgm
    bx, _bw = hit["bar"]
    pygame.event.clear()
    pygame.event.post(pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, button=1, pos=(bx + 2, rect.centery)))
    act = ren.handle_input()
    assert act["action"] == "click"
    assert act["hit"]["kind"] == "settings_slider"
    assert act["hit"]["key"] == "bgm_volume"
    assert act["pos"][0] <= bx + 3  # 换算后仍在左端附近


def test_t1_应用settings_set写回并钳制(tmp_path):
    """_apply_business 应用 settings_set：写回 settings.json 且值钳制 0~1。"""
    settings_path = os.path.join(str(tmp_path), "settings.json")
    data_api.save_settings({"bgm_volume": 0.7}, settings_path)
    ren = Renderer(assets_root=PROJECT)
    ui = UI()
    ui.mode = "settings"
    business = {"action": "settings_set", "key": "bgm_volume", "value": 0.05}
    _apply_business(business, None, ren, ui, "", settings_path)
    back = data_api.load_settings(settings_path)
    assert abs(back["bgm_volume"] - 0.05) < 1e-9
    # 越界钳制
    business2 = {"action": "settings_set", "key": "bgm_volume", "value": 1.7}
    _apply_business(business2, None, ren, ui, "", settings_path)
    back2 = data_api.load_settings(settings_path)
    assert abs(back2["bgm_volume"] - 1.0) < 1e-9


def test_u7_对话框位置滑条按像素换算(tmp_path):
    """U7：位置滑条传 0~1 比例，落盘是 -80~80 像素（0.5=默认位置）。"""
    settings_path = os.path.join(str(tmp_path), "settings.json")
    data_api.save_settings({}, settings_path)
    ren = Renderer(assets_root=PROJECT)
    ui = UI()
    ui.mode = "settings"

    def set_ratio(r):
        _apply_business({"action": "settings_set", "key": "dialog_offset_y", "value": r},
                        None, ren, ui, "", settings_path)
        return data_api.load_settings(settings_path)["dialog_offset_y"]

    assert set_ratio(0.5) == 0        # 中间 = 项目默认位置
    assert set_ratio(1.0) == 80       # 最右 = 下移 80
    assert set_ratio(0.0) == -80      # 最左 = 上移 80
    assert set_ratio(0.75) == 40
