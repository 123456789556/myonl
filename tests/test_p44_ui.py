# -*- coding: utf-8 -*-
"""tests/test_p44_ui.py：P44 标题菜单可配置（5 项去画廊）+ 左列布局验收。

- ui.title.items：config.json 覆盖主菜单项（标准模板 5 项），动作按 label 匹配
- ui.title.align="left"：标题页左列布局（游戏名左上 + 菜单左列）渲染不崩
- 引擎默认（无配置）仍为 TITLE_ITEMS 6 项含画廊：老游戏/既有测试零影响
"""
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")  # 无头模式，须在 import pygame 前生效

import json

import pytest

from engine.config import load as load_config
from engine import save as save_api
from engine.ui import TITLE_ITEMS, UI
from engine.renderer import Renderer

pytestmark = [pytest.mark.ui]

# 标准模板的 5 项主菜单（P44：去画廊，退出保留）
FIVE_ITEMS = ["开始新游戏", "继续", "读档", "设置", "退出"]


@pytest.fixture
def iso_saves(tmp_path):
    """把存档目录指到临时空目录，隔离项目根的真实存档（标题"继续"灰置断言才可复现）。

    用毕 reset_saves_dir()：set_saves_dir 是模块级全局，不恢复会污染后续测试。
    """
    save_api.set_saves_dir(str(tmp_path / "saves"))
    yield tmp_path
    save_api.reset_saves_dir()


def _write_config(root, extra=None):
    """写 config.json；extra 深合并进 ui.title（模拟标准模板覆盖）。"""
    cfg = {"ui": {"title": {"items": FIVE_ITEMS, "align": "left"}}}
    if extra:
        cfg["ui"]["title"].update(extra)
    (root / "config.json").write_text(
        json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    return root


# ---------- 菜单项可配置 ----------

def test_标题菜单_默认六项含画廊():
    """引擎默认（无 config）：TITLE_ITEMS 保持 6 项含画廊，既有行为不变。"""
    ui = UI()
    assert ui.title_items() == TITLE_ITEMS
    assert "画廊" in ui.title_items()
    assert len(ui.title_items()) == 6


def test_标题菜单_config覆盖为五项去画廊(tmp_path, iso_saves):
    """标准模板配置：主菜单 5 项，去掉画廊。"""
    ui = UI(config=load_config(str(_write_config(tmp_path))))
    assert ui.title_items() == tuple(FIVE_ITEMS)
    assert "画廊" not in ui.title_items()
    assert len(ui.title_items()) == 5


def test_标题菜单_config缺省_items_回退默认(tmp_path):
    """config.json 存在但没写 items：回退 TITLE_ITEMS（老游戏零影响）。"""
    (tmp_path / "config.json").write_text('{"window_title": "X"}', encoding="utf-8")
    ui = UI(config=load_config(str(tmp_path)))
    assert ui.title_items() == TITLE_ITEMS


# ---------- 动作按 label 匹配（5 项下索引漂移仍正确） ----------

def test_标题五项_光标移到底_确认退出(tmp_path, iso_saves):
    ui = UI(config=load_config(str(_write_config(tmp_path))))
    # 5 项：开始/继续/读档/设置/退出 —— 4 次 down 到"退出"，confirm = quit
    for _ in range(4):
        ui.handle("down")
    assert ui.handle("confirm") == {"action": "quit"}


def test_标题五项_光标到设置_确认进设置模式(tmp_path, iso_saves):
    ui = UI(config=load_config(str(_write_config(tmp_path))))
    ui.refresh()
    for _ in range(3):  # 0 开始 → 1 继续 → 2 读档 → 3 设置
        ui.handle("down")
    ui.handle("confirm")
    assert ui.view()["mode"] == "settings"


def test_标题五项_继续无存档灰置(tmp_path, iso_saves):
    """5 项配置下"继续"仍按无存档灰置（enabled=False）。"""
    ui = UI(config=load_config(str(_write_config(tmp_path))))
    ui.refresh()
    items = ui.view()["items"]
    assert [it["label"] for it in items] == FIVE_ITEMS
    assert items[1]["enabled"] is False  # 无存档，继续灰置
    assert items[0]["enabled"] is True


# ---------- 左列布局渲染 ----------

@pytest.fixture
def ren(tmp_path):
    _write_config(tmp_path)
    r = Renderer((1280, 720), str(tmp_path))
    yield r
    r.close()


def test_标题左列_渲染不崩(ren):
    """ui.title.align=left：标题页完整渲染（游戏名左上 + 左列菜单 + 版本）。"""
    view = {"mode": "title", "title": "测试游戏",
            "items": [{"label": s, "enabled": True} for s in FIVE_ITEMS],
            "cursor": 0}
    ren.render({}, view)  # 不抛错即通过（命中列表照常登记）
    assert ren._ui_hits  # 菜单项仍整行可点


def test_标题居中_渲染不崩(tmp_path):
    """引擎默认 align=center 路径不受改动影响。"""
    r = Renderer((1280, 720), str(tmp_path))
    try:
        view = {"mode": "title", "title": "测试游戏",
                "items": [{"label": s, "enabled": True} for s in TITLE_ITEMS],
                "cursor": 0}
        r.render({}, view)
        assert len(r._ui_hits) == 6
    finally:
        r.close()


# ---------- P44-D SKIP 规则配置 ----------

def test_skip默认禁用_且规则为仅已浏览():
    ui = UI()
    assert ui.skip_allowed is False
    assert ui.skip_mode == "viewed"


def test_skip规则_config开启全部可跳(tmp_path):
    (tmp_path / "config.json").write_text(
        '{"skip": {"enabled": true, "mode": "all"}}', encoding="utf-8")
    ui = UI(config=load_config(str(tmp_path)))
    assert ui.skip_allowed is True
    assert ui.skip_mode == "all"


def test_skip规则_非法mode回退仅已浏览(tmp_path):
    (tmp_path / "config.json").write_text(
        '{"skip": {"enabled": true, "mode": "nonsense"}}', encoding="utf-8")
    ui = UI(config=load_config(str(tmp_path)))
    assert ui.skip_mode == "viewed"
