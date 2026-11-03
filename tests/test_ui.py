# -*- coding: utf-8 -*-
"""tests/test_ui.py：玩家外壳 UI 状态机验收（纯逻辑，无 pygame，可 headless 跑）。

覆盖：初始状态 / 标题→新游戏 / Esc 开关菜单 / 存档流程 /
读档流程（空位灰置）/ 回标题 / 设置落盘 / 继续灰置 / 回看 / 数字键选位 / 退出 / 红线回归。
"""
import json
import sys
from pathlib import Path

import pytest

from engine import data as data_api
from engine import save as save_api
from engine.runtime import Runtime
from engine.ui import UI, TITLE_ITEMS, next_value

pytestmark = [pytest.mark.unit]

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(autouse=True)
def _in_tmp(tmp_path, monkeypatch):
    """saves/ 与 settings.json 都写当前目录，用例之间完全隔离。"""
    monkeypatch.chdir(tmp_path)
    return tmp_path


def make_save(slot=3, label="测试进度"):
    """造一个最小可读存档（label 由锚点栈里的 label 名生成）。"""
    state = {
        "script": "test.gal", "stack": [[0, 0]], "bg": None, "music": None,
        "sprites": [], "vars": {}, "characters": {}, "history": [],
        "pending_choice": None, "finished": False,
    }
    save_api.save(state, slot, [{"kind": "label", "name": label, "offset": 0}])


def open_menu(ui):
    """playing → Esc → menu（光标回到 0）。"""
    ui.handle("back")


def open_slots(ui, index):
    """menu 里把光标移到第 index 项并确认（0 存档 / 1 读档）。"""
    ui.handle("back")  # playing → menu
    for _ in range(index):
        ui.handle("down")
    ui.handle("confirm")


# ---------- 1. 初始状态 ----------

def test_初始状态_标题菜单():
    ui = UI()
    v = ui.view()
    assert v["mode"] == "title"
    assert [i["label"] for i in v["items"]] == list(TITLE_ITEMS)
    assert v["cursor"] == 0
    assert v["slots"] is None  # 不在存档列表模式


# ---------- 2. 标题 → 新游戏 ----------

def test_标题确认新游戏返回start_game并进入playing():
    ui = UI()
    act = ui.handle("confirm")
    assert act == {"action": "start_game"}
    assert ui.view()["mode"] == "playing"


# ---------- 3. Esc 开菜单 / 关菜单 ----------

def test_Esc开关菜单():
    ui = UI()
    ui.mode = "playing"
    assert ui.handle("back") is None
    assert ui.view()["mode"] == "menu"
    assert ui.handle("back") is None
    assert ui.view()["mode"] == "playing"


# ---------- 4. 存档流程 ----------

def test_存档流程_进入列表并选3号位():
    make_save(3)
    ui = UI()
    ui.mode = "playing"
    open_slots(ui, 0)  # 菜单 → 存档

    v = ui.view()
    assert v["mode"] == "slots" and v["slots_mode"] == "save"
    rows = v["slots"]
    assert len(rows) == 10  # 2026-11-02：补齐第 10 格（与 save.SLOT_COUNT / 文档一致）
    assert rows[0]["slot"] == 1 and rows[9]["slot"] == 10
    assert rows[2]["label"] == "测试进度"  # 列表数据来自 save.list_slots()

    for _ in range(2):
        ui.handle("right")  # 九宫格：光标 0 → 2 号位（存档 3）
    act = ui.handle("confirm")
    assert act == {"action": "save_slot", "slot": 3}


def test_十格存档_上下按五行移动():
    """10 格是 5×2 布局：↓ 一次应跳 5 格，与画面网格一致。"""
    ui = UI()
    ui.mode = "playing"
    open_slots(ui, 0)
    assert ui._cursor == 0
    ui.handle("down")
    assert ui._cursor == 5
    ui.handle("up")
    assert ui._cursor == 0


def test_快存写入独立quick槽():
    """F5 快存不能覆盖普通存档 1，而是写 slot_quick。"""
    ui = UI()
    ui.mode = "playing"
    open_slots(ui, 0)
    act = ui.handle("quicksave")
    assert act == {"action": "save_slot", "slot": "quick"}


def test_游戏中F5快存直接写quick槽():
    ui = UI()
    ui.mode = "playing"
    assert ui.handle("quicksave") == {"action": "save_slot", "slot": "quick"}


def test_英文设置与标题菜单翻译():
    """lang=en-US 后标题菜单与设置项/分组/选项都要翻译。"""
    ui = UI()
    ui.set_settings({"lang": "en-US"})
    ui.mode = "title"
    labels = [i["label"] for i in ui.view()["items"]]
    assert "New Game" in labels and "Settings" in labels
    assert "开始新游戏" not in labels

    ui.mode = "settings"
    v = ui.view()
    item_labels = [i["label"] for i in v["items"]]
    assert "Text Speed" in item_labels
    assert "Advanced" in v["settings_groups"] and "Key Bindings" in v["settings_groups"]
    lang_item = next(i for i in v["items"] if i["key"] == "lang")
    assert lang_item["labels"] == ["Chinese", "English"]


def test_第10格可用0键直选():
    ui = UI()
    ui.mode = "playing"
    open_slots(ui, 0)
    act = ui.handle("slot10")
    assert act == {"action": "save_slot", "slot": 10}


# ---------- 5. 读档流程（空位灰置不可选） ----------

def test_读档流程_空位灰置且落到有存档位():
    make_save(3)
    ui = UI()
    ui.mode = "playing"
    open_slots(ui, 1)  # 菜单 → 读档

    v = ui.view()
    assert v["slots_mode"] == "load"
    assert v["slots"][0]["enabled"] is False   # 1 号位空
    assert v["slots"][1]["enabled"] is False   # 2 号位空
    assert v["slots"][2]["enabled"] is True    # 3 号位有存档
    assert v["cursor"] == 2                    # 光标自动落到第一个有存档的位

    act = ui.handle("confirm")
    assert act == {"action": "load_slot", "slot": 3}
    assert ui.view()["mode"] == "playing"      # 乐观切换；失败由 demo 回退 menu


def test_读档流程_确认空位无动作():
    make_save(3)
    ui = UI()
    ui.mode = "playing"
    open_slots(ui, 1)
    ui.handle("down")  # 3 → 4（空位）
    assert ui.handle("confirm") is None
    assert ui.view()["mode"] == "slots"  # 停在列表里


# ---------- 6. 回标题 ----------

def test_回标题返回to_title动作():
    ui = UI()
    ui.mode = "playing"
    ui.handle("back")
    for _ in range(3):
        ui.handle("down")  # 菜单第 4 项（存档/读档/画廊/回标题）
    act = ui.handle("confirm")
    assert act == {"action": "to_title"}
    assert ui.view()["mode"] == "title"


# ---------- 7. 设置（修改即写、落盘后重建 UI 读回一致） ----------

def test_设置_调整打字速度并落盘():
    ui = UI()
    ui.mode = "playing"
    ui.handle("back")
    for _ in range(4):
        ui.handle("down")
    ui.handle("confirm")  # 菜单 → 设置
    assert ui.view()["mode"] == "settings"

    before = ui.view()["settings"]["text_speed"]
    act = ui.handle("confirm")
    assert act == {"action": "settings_change", "key": "text_speed", "delta": 5}

    # 模拟 demo 执行业务动作：取下一档 → 落盘
    # P30-S2-1：打字速度档位化，30 属"慢"档（20），下一档 45（中）
    settings = dict(ui.view()["settings"])
    settings["text_speed"] = next_value("text_speed", before)
    data_api.save_settings(settings)

    ui2 = UI()
    ui2.mode = "playing"
    ui2.handle("back")
    for _ in range(4):
        ui2.handle("down")
    ui2.handle("confirm")
    assert ui2.view()["settings"]["text_speed"] == next_value("text_speed", before)


def test_设置_音量步进0点1():
    ui = UI()
    ui.mode = "playing"
    ui.handle("back")
    for _ in range(4):
        ui.handle("down")
    ui.handle("confirm")
    ui.handle("down")  # 第二项：音乐音量
    act = ui.handle("confirm")
    assert act == {"action": "settings_change", "key": "bgm_volume", "delta": 0.1}
    assert next_value("bgm_volume", 0.7) == 0.8  # 无浮点噪声


def test_设置_滑条点击按比例定值():
    """P49：点滑条任意位置 = 按比例直接定值（0~100%），不再整行调一档。"""
    ui = UI()
    ui.mode = "settings"
    bar = (400, 200)  # 条子 x=400, 宽=200 → 左端 400=0%，右端 600=100%
    act = ui.click({"kind": "settings_slider", "key": "bgm_volume", "bar": bar},
                   pos=(400, 300))
    assert act == {"action": "settings_set", "key": "bgm_volume", "value": 0.0}
    act = ui.click({"kind": "settings_slider", "key": "bgm_volume", "bar": bar},
                   pos=(600, 300))
    assert act == {"action": "settings_set", "key": "bgm_volume", "value": 1.0}
    act = ui.click({"kind": "settings_slider", "key": "bgm_volume", "bar": bar},
                   pos=(500, 300))
    assert act == {"action": "settings_set", "key": "bgm_volume", "value": 0.5}
    # 点条子左侧 = 左侧值（修正"点左往右"）：x=450 → 0.25
    act = ui.click({"kind": "settings_slider", "key": "sfx_volume", "bar": bar},
                   pos=(450, 300))
    assert act == {"action": "settings_set", "key": "sfx_volume", "value": 0.25}


def test_设置_发行版隐藏桌宠开关(monkeypatch):
    """桌宠不随游戏包分发：frozen 下设置页不显示该项，快捷栏开关照常可见。"""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    ui = UI()
    ui.mode = "settings"
    keys = [it.get("key") for it in ui.view()["items"]]
    assert "pet_enabled" not in keys
    assert "quickbar_enabled" in keys


def test_设置_分页方向键跨组():
    """P49：设置分三页（基础/音频/语音），方向键到底跨到相邻组并切换高亮。"""
    ui = UI()
    ui.mode = "settings"
    assert ui.view()["settings_groups"] == ["基础", "音频", "语音", "高级", "键位", "界面"]
    assert ui.view()["settings_tab"] == 0
    # 基础页只有打字速度：down → 跨到音频页首（音乐音量）
    ui.handle("down")
    assert ui.view()["settings_tab"] == 1
    v = ui.view()
    assert v["items"][v["cursor"]]["key"] == "bgm_volume"
    # 音频页内 down → 音效音量（仍在音频页）
    ui.handle("down")
    assert ui.view()["settings_tab"] == 1
    assert ui.view()["items"][ui.view()["cursor"]]["key"] == "sfx_volume"
    # 到底再 down → 语音页首（配音）
    ui.handle("down")
    assert ui.view()["settings_tab"] == 2
    assert ui.view()["items"][ui.view()["cursor"]]["key"] == "voice_enabled"
    # 点击左侧导航切回基础页
    ui.click({"kind": "settings_nav", "index": 0})
    assert ui.view()["settings_tab"] == 0
    assert ui.view()["items"][ui.view()["cursor"]]["key"] == "text_speed"


# ---------- 8. 继续灰置 ----------

def test_继续_无存档时灰置且确认无效():
    ui = UI()
    v = ui.view()
    assert v["items"][1]["enabled"] is False
    ui.handle("down")  # 光标移到"继续"
    assert ui.handle("confirm") is None
    assert ui.view()["mode"] == "title"


# ---------- 9. 回看 ----------

def test_回看_打开翻页与关闭():
    ui = UI()
    ui.mode = "playing"
    history = [{"char": None, "text": f"第{i}句"} for i in range(45)]
    ui.set_history(history)

    assert ui.handle("backlog") is None
    v = ui.view()
    assert v["mode"] == "backlog"
    assert len(v["history"]) == 20
    assert v["history"][-1]["text"] == "第44句"  # 默认最新一屏

    ui.handle("up")  # 往过去翻一页
    v = ui.view()
    assert v["history"][0]["text"] == "第5句"
    assert v["history"][-1]["text"] == "第24句"

    ui.handle("down")  # 翻回最新
    assert ui.view()["history"][-1]["text"] == "第44句"

    ui.handle("back")
    assert ui.view()["mode"] == "playing"


def test_回看_最新一屏按down直接关闭():
    ui = UI()
    ui.mode = "playing"
    ui.set_history([{"char": "甲", "text": "你好。"}])
    ui.handle("backlog")
    ui.handle("down")
    assert ui.view()["mode"] == "playing"


# ---------- 10. 数字键选位 ----------

def test_数字键选位_存档与读档():
    make_save(3)
    ui = UI()
    ui.mode = "playing"
    open_slots(ui, 0)
    assert ui.handle("slot3") == {"action": "save_slot", "slot": 3}

    ui = UI()
    ui.mode = "playing"
    open_slots(ui, 1)
    assert ui.handle("slot3") == {"action": "load_slot", "slot": 3}


# ---------- 11. 退出 ----------

def test_退出_标题与菜单():
    ui = UI()
    for _ in range(TITLE_ITEMS.index("退出")):
        ui.handle("down")
    assert ui.handle("confirm") == {"action": "quit"}

    ui = UI()
    ui.mode = "playing"
    ui.handle("back")
    for _ in range(5):  # MENU_ITEMS 仍未变，退出在 idx=5
        ui.handle("down")
    assert ui.handle("confirm") == {"action": "quit"}


# ---------- 12. 红线回归 ----------

def test_存档内容不含任何UI状态():
    """UI 状态绝不进 GameState：存档 state 字段只能是脚本状态本身。"""
    rt = Runtime()
    rt.load(str(FIXTURES / "基础流程.gal"))
    rt.save(1)
    payload = json.loads((Path("saves") / "slot_1.json").read_text(encoding="utf-8"))
    assert set(payload["state"]) == {
        "script", "stack", "bg", "music", "video", "sprites", "vars",
        "characters", "history", "pending_choice", "pending_wait", "finished", "gallery",
        "fg", "camera_zoom", "anim_final",
    }
    assert "mode" not in payload["state"] and "cursor" not in payload["state"]
