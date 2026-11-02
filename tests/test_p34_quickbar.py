"""P34-T1：游戏内快捷栏（SAVE/LOAD/LOG/AUTO/SKIP/CONFIG）测试。

快捷栏是 playing 态常驻的 6 个按钮，语义由 ui.click 分发：
SAVE→存盘列表、LOAD→读档列表、LOG→回看、AUTO→自动播放开关、
SKIP→快进开关、CONFIG→设置。AUTO/SKIP 是开关（再点一次关闭）。
"""
from engine.ui import QUICKBAR_ITEMS, UI

import pytest

pytestmark = [pytest.mark.unit]


def test_快捷栏常量_六个按钮():
    assert list(QUICKBAR_ITEMS) == ["SAVE", "LOAD", "LOG", "AUTO", "SKIP", "CONFIG"]


def test_playing视图_导出快捷栏数据():
    ui = UI()
    ui.mode = "playing"
    v = ui.view(now_ms=0)
    qb = v.get("quickbar")
    assert qb is not None
    assert list(qb["labels"]) == list(QUICKBAR_ITEMS)
    assert qb["auto"] is False and qb["skip"] is False


def test_点SAVE_进存档列表():
    ui = UI()
    ui.mode = "playing"
    ui.click({"kind": "quickbar", "index": 0})
    assert ui.mode == "slots"
    assert ui._slots_purpose == "save"


def test_点LOAD_进读档列表():
    ui = UI()
    ui.mode = "playing"
    ui.click({"kind": "quickbar", "index": 1})
    assert ui.mode == "slots"
    assert ui._slots_purpose == "load"


def test_点LOG_进回看():
    ui = UI()
    ui.mode = "playing"
    ui.click({"kind": "quickbar", "index": 2})
    assert ui.mode == "backlog"


def test_点AUTO_开关切换():
    ui = UI()
    ui.mode = "playing"
    assert ui.auto_on is False
    ui.click({"kind": "quickbar", "index": 3})
    assert ui.auto_on is True
    ui.click({"kind": "quickbar", "index": 3})
    assert ui.auto_on is False


def test_点SKIP_开关切换():
    # P44-C：skip 默认禁（无 config 或未开启 skip_enabled 时点 SKIP 无效）
    ui = UI()
    ui.mode = "playing"
    assert ui.skip_on is False
    ui.click({"kind": "quickbar", "index": 4})
    assert ui.skip_on is False  # 默认禁：点击不生效
    # 开发者 config.ui.quickbar.skip_enabled=true 后生效
    from engine.config import Config
    ui2 = UI(config=Config({"ui": {"quickbar": {"skip_enabled": True}}}))
    ui2.mode = "playing"
    ui2.click({"kind": "quickbar", "index": 4})
    assert ui2.skip_on is True
    ui2.click({"kind": "quickbar", "index": 4})
    assert ui2.skip_on is False


def test_点CONFIG_进设置():
    ui = UI()
    ui.mode = "playing"
    ui.click({"kind": "quickbar", "index": 5})
    assert ui.mode == "settings"


def test_激活状态进视图():
    ui = UI()
    ui.mode = "playing"
    ui.click({"kind": "quickbar", "index": 3})  # AUTO 开
    qb = ui.view(now_ms=0)["quickbar"]
    assert qb["auto"] is True and qb["skip"] is False  # skip 默认禁
    assert qb["skip_allowed"] is False


def test_非法索引_无副作用():
    ui = UI()
    ui.mode = "playing"
    assert ui.click({"kind": "quickbar", "index": 99}) is None
    assert ui.mode == "playing"
