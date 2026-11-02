"""tests/test_p30_interaction.py：P30-S1 互动规则优化验收（无头 dummy 模式）。

覆盖：
1. 出选项时保留上一句全文并压暗（不再留空白大框）
2. 选中项高对比配色（选中 vs 未选中可辨、白字可读）
3. 菜单/设置等 UI 覆盖态不画对话框与选项（避免白边与提示语透出）
4. 标题页引擎版本号开关（默认关）
5. 终幕停留时长可配 + 收尾引导提示
"""

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")  # 无头模式，须在 import pygame 前生效
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402
import pytest  # noqa: E402

from engine import renderer as R  # noqa: E402
from engine.renderer import Renderer  # noqa: E402

pytestmark = [pytest.mark.ui]


@pytest.fixture(scope="module")
def ren(tmp_path_factory):
    root = tmp_path_factory.mktemp("p30")
    r = Renderer((1280, 720), str(root))
    yield r
    r.close()


def test_选项态保留上一句全文并压暗(ren):
    """P30-S1-1：pending 时用全文（不走打字机）并压暗；非 pending 仍按已写字数。"""
    chars = {"玛丽": {"color": "#ffcc00"}}
    history = [{"char": "玛丽", "text": "她轻轻笑了，像是想起了什么。"}]
    ren._tw_text = "她轻轻笑了，像是想起了什么。"
    ren._tw_shown = 2.0  # 打字机只出了两个字

    plain = ren._dialog_layout(history, chars, False)
    pending = ren._dialog_layout(history, chars, True)

    assert "".join(plain["lines"]) == "她轻"
    assert "".join(pending["lines"]) == "她轻轻笑了，像是想起了什么。"
    assert plain["color"] == R.DIALOG_FG
    assert pending["color"] == R.DIALOG_FG_DIM


def test_选项态旁白也保留全文(ren):
    """旁白（char=None）出选项时同样保留全文，不留空框。"""
    ren._tw_text = "海风停了一拍。"
    ren._tw_shown = 1.0
    layout = ren._dialog_layout([{"char": None, "text": "海风停了一拍。"}], {}, True)
    assert "".join(layout["lines"]) == "海风停了一拍。"
    assert layout["color"] == R.DIALOG_FG_DIM


def test_空历史返回None(ren):
    """没有台词时不出布局（不崩）。"""
    assert ren._dialog_layout([], {}, True) is None


def test_选中项高对比(ren):
    """P30-S1-2：白字压在选中底色上可读，且选中底色与未选中底色明显不同。"""

    def lum(c):
        return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]

    assert lum(R.UI_SELECTED_FG) - lum(R.UI_SELECTED_BG) > 128
    assert lum(R.UI_SELECTED_BG) - lum(R.UI_IDLE_BG) > 32


def test_菜单态不画对话框与选项(ren, monkeypatch):
    """P30-S1-3：UI 覆盖态跳过对话框/选项，playing 时正常绘制。"""
    calls = []
    monkeypatch.setattr(ren, "_draw_dialog", lambda *a, **k: calls.append("dialog"))
    monkeypatch.setattr(ren, "_draw_choices", lambda *a, **k: calls.append("choices"))
    state = {"history": [{"char": None, "text": "海风停了一拍。"}],
             "pending_choice": {"options": [{"text": "走向她"}]}}
    ren._options = state["pending_choice"]["options"]

    ren.render(state, {"mode": "menu", "items": [{"text": "存档"}], "cursor": 0})
    assert calls == []
    assert ren._choice_rects == []

    ren.render(state, {"mode": "playing"})
    assert calls == ["dialog", "choices"]


def test_标题版本号开关默认关(ren):
    """P30-S1-4：默认不显示引擎版本号，settings.json 显式开启才显示。"""
    ren.settings.pop("show_engine_version", None)
    assert ren._show_engine_version() is False
    ren.settings["show_engine_version"] = True
    assert ren._show_engine_version() is True
    ren.settings.pop("show_engine_version", None)

    # 两种设置下画标题都不崩
    ren.render({}, {"mode": "title", "title": "月光漫步", "items": [], "cursor": 0})
    ren.settings["show_engine_version"] = True
    try:
        ren.render({}, {"mode": "title", "title": "月光漫步", "items": [], "cursor": 0})
    finally:
        ren.settings.pop("show_engine_version", None)


def test_终幕停留时长可配(ren):
    """P30-S2-3：ending_hold_ms 默认 1500，可被 settings 覆盖，非法值回落默认。"""
    ren.settings.pop("ending_hold_ms", None)
    assert ren.ending_hold_ms() == 1500
    ren.settings["ending_hold_ms"] = 800
    assert ren.ending_hold_ms() == 800
    ren.settings["ending_hold_ms"] = "坏值"
    assert ren.ending_hold_ms() == 1500
    ren.settings.pop("ending_hold_ms", None)


def test_终幕提示在淡出前绘制(ren):
    """P30-S2-3：finished 且未淡出时右下角给收尾引导；淡出开始后不画，且都不崩。"""
    state = {"history": [], "finished": True}
    ren.render(state)
    ren.trigger_ending_fade()
    assert ren._ending_fade_t0 is not None
    ren.render(state)
    ren._ending_fade_t0 = None
    ren._ending_fade_done = False


def test_结束停留字段进默认设置():
    """P30-S2-3：ending_hold_ms 必须进 DEFAULT_SETTINGS，否则 settings.json 里的值读不进来。"""
    from engine.data import DEFAULT_SETTINGS

    assert DEFAULT_SETTINGS.get("ending_hold_ms") == 4000


def test_标题页有画廊入口():
    """P30-S2-3 收尾引导闭环：标题页菜单项包含画廊，且无存档也能进（enable=True）。"""
    from engine.ui import TITLE_ITEMS, UI

    assert "画廊" in TITLE_ITEMS
    # 画廊应在"设置"和"退出"之间（idx=4）
    idx_settings = TITLE_ITEMS.index("设置")
    idx_gallery = TITLE_ITEMS.index("画廊")
    idx_quit = TITLE_ITEMS.index("退出")
    assert idx_settings < idx_gallery < idx_quit

    # UI.view 标题模式下画廊项 enabled=True（无存档也能进，走 persistent 解锁）
    ui = UI()
    ui._mode = "title"
    ui._has_save = False
    v = ui.view()
    gallery_item = v["items"][idx_gallery]
    assert gallery_item["enabled"] is True
    quit_item = v["items"][idx_quit]
    assert quit_item["enabled"] is True


def test_标题回车选画廊进入gallery模式():
    """P30-S2-3 闭环：标题页光标在画廊时按回车，UI 切到 gallery 模式。"""
    from engine.ui import UI, TITLE_ITEMS

    ui = UI()
    ui._mode = "title"
    gallery_idx = TITLE_ITEMS.index("画廊")
    ui._cursor = gallery_idx
    business = ui.handle("confirm")
    assert business is None  # 切模式无 business
    assert ui._mode == "gallery"
    assert ui._gallery_tab == 0
    assert ui._gallery_detail is None


def test_标题进画廊后返回标题():
    """从标题进画廊，Esc 应回标题（不是钻进游戏内菜单）。"""
    from engine.ui import UI, TITLE_ITEMS

    ui = UI()
    ui._mode = "title"
    ui._cursor = TITLE_ITEMS.index("画廊")
    ui.handle("confirm")
    assert ui._mode == "gallery"
    ui.handle("back")
    assert ui._mode == "title"


def test_游戏内菜单进画廊后返回菜单():
    """从游戏内菜单进画廊，Esc 仍回菜单。"""
    from engine.ui import UI, MENU_ITEMS

    ui = UI()
    ui._mode = "menu"
    ui._cursor = MENU_ITEMS.index("画廊")
    ui.handle("confirm")
    assert ui._mode == "gallery"
    ui.handle("back")
    assert ui._mode == "menu"


def test_选中配色可用Surface绘制(ren):
    """选中底色/描边能直接喂 pygame（防元组长度写错）。"""
    surf = pygame.Surface((10, 10), pygame.SRCALPHA)
    surf.fill((*R.UI_SELECTED_BG, R.UI_SELECTED_BG_ALPHA))
    pygame.draw.rect(surf, R.UI_SELECTED_BORDER, pygame.Rect(0, 0, 10, 10), 2)
    assert surf.get_at((5, 5))[:3] == R.UI_SELECTED_BG


# ---------- P30-S1-5：长段落翻页 ----------

def test_长段落分页拼接等于原文(ren):
    """超长台词按可用行数分页，逐页拼接 == 原文（不丢字）。"""
    long_text = "这是一个非常非常长的段落。" * 30  # 远超一屏
    ren._tw_text = long_text
    ren._tw_shown = float(len(long_text))
    layout = ren._dialog_layout([{"char": "林晚", "text": long_text}], {}, False)
    assert len(layout["pages"]) > 1
    assert "".join("".join(p) for p in layout["pages"]) == long_text
    # 每页行数 ≤ 可用行数（对话框内放得下）
    line_h = layout["line_h"]
    per_page_max = (R.DIALOG_HEIGHT - (layout["start_y"] - R.DIALOG_TOP) - line_h) // line_h
    assert all(len(p) <= per_page_max for p in layout["pages"])


def test_选项态不分页显示全文(ren):
    """pending 时返回单页全文（玩家优先看选项，不分页）。"""
    ren._tw_text = "她轻轻笑了，像是想起了什么。" * 5
    ren._tw_shown = 1.0
    layout = ren._dialog_layout([{"char": "玛丽", "text": "她轻轻笑了，像是想起了什么。" * 5}], {}, True)
    assert layout["pages"] == [layout["lines"]]


def test_翻页语义_未到末页不推进(ren):
    """P30-S1-5：打字机完成后还有下一页 → 空格翻页（action none）；末页才 advance。"""
    long_text = "这是一个非常非常长的段落。" * 30
    # 直接设状态（不依赖 render 的打字机重置）：满打字机 + 多页
    ren._tw_text = long_text
    ren._tw_shown = float(len(long_text))
    ren._page_index = 0
    ren._page_count = 4
    assert ren._has_next_page()

    act = ren._advance_or_reveal()  # 第一页 → 翻页
    assert act == {"action": "none"}
    assert ren._page_index == 1

    for _ in range(2):
        ren._advance_or_reveal()
    assert ren._page_index == 3
    act_last = ren._advance_or_reveal()  # 已到末页 → advance
    assert act_last == {"action": "advance"}
    assert not ren._has_next_page()


def test_短台词不分页直接推进(ren):
    ren._tw_text = "你好。"
    ren._tw_shown = float(len("你好。"))
    ren._page_index = 0
    ren._page_count = 1
    assert not ren._has_next_page()
    assert ren._advance_or_reveal() == {"action": "advance"}


# ---------- P30-S1-6/7：标题双层可配置 + 选项偏移 ----------

def test_标题文本配置读取(ren):
    """title_text_visible/title_text_y 可配置；未配置时用默认（有背景图隐藏由渲染核对）。"""
    ren.settings.pop("title_text_visible", None)
    ren.settings.pop("title_text_y", None)
    assert ren.settings.get("title_text_visible") is None  # 未显式配置
    assert int(ren.settings.get("title_text_y", 120)) == 120
    ren.settings["title_text_visible"] = True
    ren.settings["title_text_y"] = 200
    assert bool(ren.settings.get("title_text_visible")) is True
    assert int(ren.settings.get("title_text_y", 120)) == 200
    ren.render({}, {"mode": "title", "title": "月光漫步", "items": [], "cursor": 0})  # 不崩
    ren.settings.pop("title_text_visible", None)
    ren.settings.pop("title_text_y", None)


def test_选项偏移配置生效(ren):
    """choice_offset_y 改变选项组底边位置（默认 0）。行高 34，最底行 rect 底 = bottom-6。

    C2：默认与对话框间距改为 40（ui.choices.dialog_gap）；老配置只写 gap 的兼容见单独用例。
    """
    ren.settings.pop("choice_offset_y", None)
    ren._options = [{"text": "走向她"}, {"text": "转身离开"}]
    ren._choice_index = 0
    ren.render({"history": [], "pending_choice": {"options": ren._options}}, {"mode": "playing"})
    default_bottom = R.DIALOG_TOP - 40 - 6  # C2 默认间距 40；行高 40-6=34，最底行 rect 底再 -6
    assert len(ren._choice_rects) == 2
    last_rect_default = max(r.bottom for r, _, _ in ren._choice_rects)
    assert last_rect_default == default_bottom

    ren.settings["choice_offset_y"] = -80
    ren.render({"history": [], "pending_choice": {"options": ren._options}}, {"mode": "playing"})
    last_rect_moved = max(r.bottom for r, _, _ in ren._choice_rects)
    assert last_rect_moved == default_bottom - 80
    ren.settings.pop("choice_offset_y", None)


# ---------- P30-S2-1：设置档位化 ----------

def test_打字速度三档循环():
    """30 属"慢"档（最近 20），下一档 45；45→90→20 循环。"""
    from engine.ui import next_value, TEXT_SPEED_LEVELS
    assert TEXT_SPEED_LEVELS == (20, 45, 90)
    assert next_value("text_speed", 30) == 45
    assert next_value("text_speed", 45) == 90
    assert next_value("text_speed", 90) == 20
    assert next_value("text_speed", 20) == 45


def test_打字速度档位显示(ren):
    from engine.renderer import _format_setting
    assert _format_setting(20, "speed") == "慢"
    assert _format_setting(45, "speed") == "中"
    assert _format_setting(90, "speed") == "快"
    assert _format_setting(30, "speed") == "慢"
    assert _format_setting(60, "speed") == "中"
    assert _format_setting(61, "speed") == "快"


# ---------- P30-S2-2：settings_hidden 设置项过滤 ----------

def test_settings_hidden过滤设置项(tmp_path):
    """settings.json 声明隐藏配音项 → 设置页 items 不含该键，光标范围同步。"""
    from engine.ui import UI, SETTINGS_ITEMS
    ui = UI()
    ui.settings_path = str(tmp_path / "settings.json")
    import json
    (tmp_path / "settings.json").write_text(
        json.dumps({"settings_hidden": ["voice_enabled", "voice_auto_advance"]}),
        encoding="utf-8")
    ui.refresh()
    ui.mode = "playing"
    ui.handle("back")
    for _ in range(4):
        ui.handle("down")
    ui.handle("confirm")
    assert ui.view()["mode"] == "settings"
    items = ui.view()["items"]
    keys = [it["key"] for it in items]
    assert "voice_enabled" not in keys and "voice_auto_advance" not in keys
    assert len(items) == len(SETTINGS_ITEMS) - 2
    # 光标在可见项范围内移动
    for _ in range(3):
        ui.handle("down")
    assert ui.view()["cursor"] < len(items)

# ---------- P0-1：对话框 DSL（config dialogue 几何 + @character kind=） ----------

def test_config_dialogue默认几何():
    """不写 config.json → dialogue 布局取默认（= 原硬编码），零变化。"""
    from engine import config as C
    cfg = C.Config()
    d = cfg.dialogue("default")
    assert d["height"] == 180
    assert d["margin"] == 24
    assert d["border_width"] == 2
    # P50：默认半透明圆角（他人世界末式），radius 10 / bg_alpha 150
    assert d["bg_alpha"] == 150
    assert d["radius"] == 10
    assert cfg.dialogue("nvl")["bg_alpha"] == 90
    # 未知布局名：回落默认布局
    assert cfg.dialogue("不存在") == cfg.dialogue("default")


def test_config_dialogue覆盖几何():
    """config.json 覆盖 dialogue.default.height 生效，非法值回落默认。"""
    from engine import config as C
    cfg = C.Config({"dialogue": {"default": {"height": 220, "margin": "abc"}}})
    d = cfg.dialogue("default")
    assert d["height"] == 220
    assert d["margin"] == 24  # 非法字符串被跳过，保留默认


def test_parser_character_kind绑定布局():
    """@character 可追加 kind=布局名；缺省 kind=default。"""
    from engine.parser import parse_text
    ins = parse_text("@character 玛丽 #ffcc00 kind=nvl\n")[0]
    assert ins["op"] == "character"
    assert ins["name"] == "玛丽"
    assert ins["kind"] == "nvl"
    ins2 = parse_text("@character 丽 #ffcc00\n")[0]
    assert ins2["kind"] == "default"
    with pytest.raises(Exception):
        parse_text("@character 坏 #ffcc00 乱写\n")


def test_runtime_character存kind(tmp_path):
    """runtime 登记角色时保留 kind，供 renderer 选布局。"""
    from engine.runtime import Runtime
    gal = tmp_path / "t.gal"
    gal.write_text("@character 玛丽 #ffcc00 kind=nvl\n@ 玛丽 你好\n", encoding="utf-8")
    rt = Runtime()
    rt.load(str(gal))
    for _ in range(2):  # 推进 character + say 两行
        rt.step()
    st = rt.snapshot()
    assert st["characters"]["玛丽"]["kind"] == "nvl"
    assert st["characters"]["玛丽"]["color"] == "#ffcc00"


def test_dialog_layout_kind传递(ren):
    """_dialog_layout 按角色 kind 返回布局参数：nvl 整屏、default 底部条。"""
    chars = {"玛丽": {"color": "#ffcc00", "kind": "nvl"},
             "丽": {"color": "#ffcc00", "kind": "default"}}
    nvl = ren._dialog_layout([{"char": "玛丽", "text": "月光下，海风轻轻吹过。"}], chars, False)
    normal = ren._dialog_layout([{"char": "丽", "text": "月光下，海风轻轻吹过。"}], chars, False)
    assert nvl["kind"] == "nvl"
    assert normal["kind"] == "default"
    # nvl 不分页（整屏显示），default 按对话框高度分页
    assert len(nvl["pages"]) == 1
    assert normal["start_y"] > nvl["start_y"]


def test_nvl渲染不崩(ren):
    """kind=nvl 角色台词渲染：全屏底、无白边、整屏文字，不抛异常。"""
    chars = {"玛丽": {"color": "#ffcc00", "kind": "nvl"}}
    ren._tw_text = "月光下，海风轻轻吹过。"
    ren._tw_shown = 100.0
    ren.render({"history": [{"char": "玛丽", "text": "月光下，海风轻轻吹过。"}],
                "characters": chars},
               {"mode": "playing"})
    # 默认布局渲染照旧（回归）
    chars2 = {"丽": {"color": "#ffcc00", "kind": "default"}}
    ren.render({"history": [{"char": "丽", "text": "月光下，海风轻轻吹过。"}],
                "characters": chars2},
               {"mode": "playing"})
