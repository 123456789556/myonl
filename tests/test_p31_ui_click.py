"""tests/test_p31_ui_click.py：P31-b 菜单鼠标点击验收（无头 dummy 模式）。

覆盖：
1. 标题页点击行 → 命中该行 → 与回车同一条业务逻辑（开始游戏/退出）
2. 灰置项点击无效（无存档的「继续」）
3. 设置行点击 = 选到该行并调整一档
4. 画廊缩略图格点击 → 打开大图；页签点击 → 切页签
5. 回看态点击任意位置 = 关闭回看
6. 缩放后的窗口点击仍能命中（窗口坐标换算）
"""

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")  # 无头模式，须在 import pygame 前生效
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402
import pytest  # noqa: E402

from engine import data  # noqa: E402
from engine.renderer import Renderer  # noqa: E402
from engine.ui import UI, TITLE_ITEMS  # noqa: E402

pytestmark = [pytest.mark.ui]


@pytest.fixture()
def rig(tmp_path):
    ren = Renderer((1280, 720), str(tmp_path))
    ui = UI()
    yield ren, ui
    ren.close()


def _click_at(ren, ui, pos):
    """渲染一帧（重建可点区域）→ 点一下 → 交给 ui 处理，返回业务动作。"""
    ren.render({"bg": None, "sprites": [], "history": [], "pending_choice": None,
                "characters": {}, "gallery": [], "music": None}, ui.view())
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"pos": pos, "button": 1}))
    act = ren.handle_input()
    assert act.get("action") == "click", f"未命中任何可点区域: {act}"
    return ui.click(act.get("hit"))


def test_标题页点击开始新游戏(rig):
    ren, ui = rig
    assert _click_at(ren, ui, (640, 320)) == {"action": "start_game"}


def test_标题页点击退出(rig):
    ren, ui = rig
    idx = TITLE_ITEMS.index("退出")
    assert _click_at(ren, ui, (640, 300 + idx * 54 + 20)) == {"action": "quit"}


def test_标题页灰置的继续不可点(rig):
    """无存档时「继续」灰置：点它既不改光标也不产生动作。"""
    ren, ui = rig
    idx = TITLE_ITEMS.index("继续")
    ui._has_save = False
    ren.render({"bg": None, "sprites": [], "history": [], "pending_choice": None,
                "characters": {}, "gallery": [], "music": None}, ui.view())
    pygame.event.post(pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, {"pos": (640, 300 + idx * 54 + 20), "button": 1}))
    act = ren.handle_input()
    assert act.get("action") == "click"
    assert ui.click(act.get("hit")) is None
    assert ui._cursor == 0  # 光标没被灰置项带走


def test_设置页点击行即发出调整动作(rig):
    """设置行的数值变更由 demo 落地（修改即写），UI 只发 settings_change 动作。"""
    ren, ui = rig
    ui.set_settings(dict(data.DEFAULT_SETTINGS))
    ui._mode = "settings"
    item = ui.view()["items"][0]
    # 行位置由布局决定（卡片垂直居中会随组内项数变化），从命中区取而不是写死坐标
    ren.render({"bg": None, "sprites": [], "history": [], "pending_choice": None,
                "characters": {}, "gallery": [], "music": None}, ui.view())
    row = next(rect for rect, p in ren._ui_hits
               if p.get("kind") == "item" and p.get("index") == 0)
    biz = _click_at(ren, ui, row.center)
    assert ui._cursor == 0
    assert biz["action"] == "settings_change"
    assert biz["key"] == item["key"]
    assert isinstance(biz["delta"], int)


def test_画廊格点击打开大图_页签点击切换(rig):
    ren, ui = rig
    ui.set_gallery([{"name": "cg_test", "kind": "cg"}], [])
    ui.set_gallery_config([])
    ui._mode = "gallery"
    ui._gallery_tab = 0
    ui._gallery_page = 0
    items = ui.view()["gallery"]["items"]
    assert items, "画廊应有可点格"
    # 网格首格中心：left=(1280-4*220-3*24)//2=104，cell 220×150，top=120
    _click_at(ren, ui, (104 + 110, 120 + 75))
    assert ui._gallery_detail is not None
    # 大图页点任意位置 → 返回网格
    _click_at(ren, ui, (640, 360))
    assert ui._gallery_detail is None


def test_回看态点击即关闭(rig):
    ren, ui = rig
    ui._mode = "playing"
    ui.handle("backlog")
    assert ui.mode == "backlog"
    _click_at(ren, ui, (640, 400))
    assert ui.mode == "playing"


def test_缩放窗口下点击仍命中(rig):
    ren, ui = rig
    ren.resize(1920, 1080)
    # 逻辑 (640,320) → 窗口 (960,480)
    assert _click_at(ren, ui, (960, 480)) == {"action": "start_game"}


def test_存档十格全部画出且可点(rig, tmp_path):
    """存档页 10 格必须全部落在画面内（5×2），不能只画出前 3 格。"""
    from engine import save as save_api

    save_api.set_saves_dir(str(tmp_path / "saves"))
    try:
        ren, ui = rig
        ui.mode = "playing"
        ui._enter_slots("save", "playing")
        ren.render({"bg": None, "sprites": [], "history": [], "pending_choice": None,
                    "characters": {}, "gallery": [], "music": None}, ui.view())
        items = [p for _r, p in ren._ui_hits if p.get("kind") == "item"]
        assert [p["index"] for p in items] == list(range(10))
        # 每格都在逻辑画布内
        rects = [r for r, p in ren._ui_hits if p.get("kind") == "item"]
        assert all(0 <= r.x and r.right <= 1280 and r.bottom <= 720 for r in rects)
    finally:
        save_api.reset_saves_dir()


def test_playing态快捷栏按钮可点击(rig, monkeypatch):
    """playing 下的快捷栏看得见也必须点得动（之前鼠标只会推进剧情）。"""
    ren, ui = rig
    state = {"bg": None, "sprites": [], "history": [{"char": None, "text": "一句话"}],
             "pending_choice": None, "characters": {}, "gallery": [], "music": None}
    ui.mode = "playing"
    lay = ren._quickbar_layout(6)
    total = 6 * (lay["bw"] + lay["gap"]) - lay["gap"]
    hover = (lay["x0"] + total - 4, lay["y0"] + lay["bh"] // 2)
    monkeypatch.setattr(pygame.mouse, "get_pos", lambda: hover)  # 悬停让快捷栏显现
    ren.render(state, ui.view())
    rect = next(rect for rect, p in ren._ui_hits
                if p.get("kind") == "quickbar" and p.get("index") == 0)
    v = ren._view
    pos = (v.x + rect.centerx * v.width // ren.size[0],
           v.y + rect.centery * v.height // ren.size[1])
    pygame.event.post(pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, {"pos": pos, "button": 1}))
    act = ren.handle_input()
    assert act.get("action") == "click"
    ui.click(act.get("hit"))
    assert ui.mode == "slots"
    assert ui._slots_purpose == "save"
