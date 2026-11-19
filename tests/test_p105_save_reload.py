"""P105：存档链路的源码契约（H5 播放器）。

背景：`myonl-core.js` 的 save() 原来写的是 `pc: state.pc`，而 `state.pc` 从来没有被维护，
永远是 undefined，于是 JSON 里没有 pc，`load()` 拿到 0 —— **读档一律回到剧本第一句**。
验收脚本一跑就抓到（存到 3 号档、"读档"读出来是开场那句）。

这批契约守住四件事：
1. 存档里必须带真实的指令位置（frame.pc - 1，回到"存档当时那一句"）；
2. 读档后不能停在 @wait 的静默里（否则玩家一进来是空画面）；
3. 菜单键 / 右侧竖列在 @wait、章节卡期间也要能点（界面入口不该被演出节奏吃掉）；
4. 存档码的导出/导入要能被脚本直接调用（验收不依赖系统文件选择器）。
"""
import os
import re

import pytest

pytestmark = [pytest.mark.unit]

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


def test_存档里带真实指令位置():
    src = _read(os.path.join("web", "myonl-core.js"))
    save_fn = src[src.index("function save()"):src.index("function load(json)")]
    assert "frame.pc - 1" in save_fn, "存档必须存 frame.pc - 1，才能回到存档当时那一句"
    assert not re.search(r"pc:\s*state\.pc", save_fn), "不能再存 state.pc（那个字段没被维护，永远是 undefined）"


def test_读档不留在没有台词的静默里():
    src = _read(os.path.join("web", "myonl-player.js"))
    body = src[src.index("function loadSlot(i)"):src.index("function openMenu()")]
    assert "settleAfterLoad()" in body, "读档要把 @wait 的剩余时间抹平，并继续走到出现台词"
    assert "d.say" in body, "实在走不到台词（作者结尾只放了 @end）时，要把存档那句补上"
    settle = src[src.index("function settleAfterLoad()"):src.index("function latestSlot()")]
    assert "state.waitUntil = 0" in settle, "@wait 的剩余时间要抹平"
    assert re.search(r"!state\.say", settle), "要继续走到出现台词为止"
    assert "vm.state.pc === lastPc" in settle, "要防死循环"


def test_界面入口不被演出节奏吃掉():
    """菜单 / 喇叭 / 存回设 现在统一走 gameCtrlHit（命中区放大到 44 CSS，
    五个键的重叠区按离中心最近的分）。
    守的是同一条：入口判定必须排在 @wait 之前，否则演出时点菜单没反应。"""
    src = _read(os.path.join("web", "myonl-player.js"))
    tap = src[src.index("function onTap(e)"):src.index("let tapStart = null;")]
    wait_at = tap.index("state.waitUntil > performance.now()")
    ctl_at = tap.index("gameCtrlHit(p)")
    assert ctl_at < wait_at, "菜单/喇叭/存回设要在 @wait 之前判断，否则等演出时点了没反应"
    assert tap.index("openMenu()") > ctl_at, "判定在入口函数里，调用排在它后面"
    assert tap.index("openPanel(ctl)") > ctl_at


def test_存档码能被脚本直接调用():
    src = _read(os.path.join("web", "myonl-player.js"))
    assert "exportCode: () => storeExportCode()" in src
    assert "importCode: (code) => storeImportCode(code)" in src


def test_标题页的继续游戏跟着新存档结构():
    """hasSave 原来读的是旧版单键 saveKey()（而且那个函数根本不存在，调用直接抛 ReferenceError
    被 try 吞掉），于是「继续游戏」永远不出现，玩家只能从头玩。"""
    src = _read(os.path.join("web", "myonl-player.js"))
    assert "saveKey(" not in src, "旧版单键已经不在了，不许再引用"
    body = src[src.index("let hasSave = false;"):src.index("// P97：竖屏不要卡片")]
    assert "storeRead()" in body, "要按 myonl:v2:save 的新结构判断有没有档"
    assert "d.auto" in body and "slots" in body


def test_自动档没有时继续游戏退到最近一格():
    """有手动档但自动档被清（清空后导入、换设备）时，点「继续游戏」必须退到最近一格，
    否则玩家按了"继续"，实际从第一句重开。"""
    src = _read(os.path.join("web", "myonl-player.js"))
    body = src[src.index("function startGame(fromSave)"):src.index("// ---------- 输入 ----------")]
    assert "storeAuto() || latestSlot()" in body, "自动档缺失时要退到最近一格手动档"
    assert "settleAfterLoad()" in body, "继续游戏也要抹平 @wait，别停在没有台词的静默里"


def test_换版本不丢档():
    """存档键里带着剧本哈希：作者改一句剧本指纹就变，旧档在新指纹下"看不见"了 ——
    盘上还在，人以为丢了。首次读档要把同标题旧指纹的记录搬进来，且旧键不删（可回滚）。

    同时守住一个坑：迁移函数曾被写成同名两份，后定义的那份静默覆盖前面，迁移一直没生效。
    """
    src = _read(os.path.join("web", "myonl-player.js"))
    assert src.count("function storeMigrate(") == 1, "同名迁移函数只能有一份，否则后者会静默覆盖前者"
    assert "function storeMigrateGid(" in src, "要有按指纹搬旧档的那一份"
    read = src[src.index("function storeRead()"):src.index("function storeFlush()")]
    assert "storeMigrateGid()" in read, "首次读档要扫一遍旧指纹"
    gid = src[src.index("function storeMigrateGid()"):src.index("function storeRead()")]
    assert "myonl:v2:save:" in gid and 'indexOf(pre) !== 0' in gid, "只搬同标题同作品的旧记录"
    assert "localStorage.removeItem" not in gid, "旧键不许删，包更新出问题还得能退回去"
