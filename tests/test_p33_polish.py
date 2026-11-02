# -*- coding: utf-8 -*-
"""tests/test_p33_polish.py：P33 品质打磨验收（@bg 淡入 / 标题音乐 / 画廊解锁条件）。

验收项：
  1. @bg 支持 fadein=秒 扩展参数（parser 解析 + dump 往返 + sfx 严格单参不放开）
  2. runtime bg 指令事件携带 fadein（无参数时不带键）
  3. renderer.play_bg 设置的淡入时长在下一次背景切换生效，缺省仍 0.3s
  4. config 新增 title_music 键（默认空 = 不播；可被 config.json 覆盖）
  5. gallery_config.json 支持对象值 {"images": [...], "require": [CG 名...]}，
     require 未满足时画廊格锁定（对齐原作：cg_dark_mary/cg_dawn_mary 需 4 结局全通）
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from engine import data  # noqa: E402
from engine import config as cfgapi  # noqa: E402
from engine.parser import dump_text, parse_text  # noqa: E402
from engine.runtime import Runtime  # noqa: E402

pytestmark = [pytest.mark.unit]


# ---------- 1. @bg fadein 语法 ----------

def test_bg_fadein解析():
    instrs = parse_text("@bg bg_beach1 fadein=1.5")
    assert instrs[0]["op"] == "bg"
    assert instrs[0]["image"] == "bg_beach1"
    assert instrs[0]["fadein"] == 1.5


def test_bg_无fadein不带键():
    instrs = parse_text("@bg bg_beach1")
    assert "fadein" not in instrs[0]


def test_bg_fadein非法值拒绝():
    from engine.parser import GalSyntaxError
    with pytest.raises(GalSyntaxError, match="数字"):
        parse_text("@bg bg_x fadein=abc")
    with pytest.raises(GalSyntaxError, match="负数"):
        parse_text("@bg bg_x fadein=-1")
    with pytest.raises(GalSyntaxError, match="不支持参数"):
        parse_text("@bg bg_x fadeout=1")  # bg 只支持 fadein


def test_sfx仍严格单参():
    from engine.parser import GalSyntaxError
    with pytest.raises(GalSyntaxError):
        parse_text("@sfx click fadein=1")


def test_bg_fadein_dump往返():
    instrs = parse_text("@bg bg_x fadein=2")
    text = dump_text(instrs)
    assert "fadein=2" in text
    re = parse_text(text)
    assert re[0]["fadein"] == 2


def test_music行为不变():
    instrs = parse_text("@music waves fadein=1 fadeout=2")
    assert instrs[0]["fadein"] == 1 and instrs[0]["fadeout"] == 2


# ---------- 2. runtime 事件携带 fadein ----------

def test_runtime_bg事件带fadein(tmp_path):
    (tmp_path / "s.gal").write_text("@bg bg_a fadein=1.2\n", encoding="utf-8")
    rt = Runtime()
    rt.load(tmp_path / "s.gal")
    ev = rt.step()
    assert ev["type"] == "scene"
    assert ev["bg"] == "bg_a"
    assert ev["fadein"] == 1.2


def test_runtime_bg事件无参数不带fadein键(tmp_path):
    (tmp_path / "s.gal").write_text("@bg bg_a\n", encoding="utf-8")
    rt = Runtime()
    rt.load(tmp_path / "s.gal")
    ev = rt.step()
    assert ev["type"] == "scene"
    assert "fadein" not in ev


# ---------- 3. renderer 淡入时长 ----------

def test_renderer_play_bg淡入时长生效():
    from engine.renderer import Renderer
    r = Renderer((640, 360), ".")  # 空资产目录：缺图走降级不崩
    r.render({"bg": "a", "history": []})  # 首次设背景（默认 0.3s）
    r.play_bg(1.5)
    r.render({"bg": "b", "history": []})  # 背景切换 → 应用 play_bg 时长
    assert r._bg_fade_seconds == 1.5
    # 一次性消费：下次切换回到默认
    r.render({"bg": "c", "history": []})
    assert r._bg_fade_seconds == cfgapi.Config().pacing_value("scene_fade", 0.35)


def test_renderer_默认淡入取配置值():
    """默认淡入时长来自 config.pacing.scene_fade（商业向 0.35s），不再是写死 0.3。"""
    from engine.renderer import Renderer
    r = Renderer((640, 360), ".")
    r.render({"bg": "a", "history": []})
    r.render({"bg": "b", "history": []})
    assert r._bg_fade_seconds == cfgapi.Config().pacing_value("scene_fade", 0.35)


def test_renderer_play_bg缺省回到默认():
    from engine.renderer import Renderer
    r = Renderer((640, 360), ".")
    r.play_bg()  # 不带参数 = 清除自定义，回到默认
    r.render({"bg": "a", "history": []})
    r.render({"bg": "b", "history": []})
    assert r._bg_fade_seconds == cfgapi.Config().pacing_value("scene_fade", 0.35)


# ---------- 4. config title_music ----------

def test_config_title_music默认空():
    cfg = cfgapi.Config()
    assert cfg.data.get("title_music") == ""


def test_config_title_music可覆盖(tmp_path):
    (tmp_path / "config.json").write_text(
        json.dumps({"title_music": "waves"}, ensure_ascii=False), encoding="utf-8")
    cfg = cfgapi.load(str(tmp_path))
    assert cfg.data.get("title_music") == "waves"


# ---------- 5. 画廊 require 解锁条件 ----------

def _make_gallery_root(tmp_path, config_value):
    (tmp_path / "gallery_config.json").write_text(
        json.dumps({"_说明": "测试", **config_value}, ensure_ascii=False), encoding="utf-8")
    return tmp_path


def test_gallery_对象格式解析(tmp_path):
    root = _make_gallery_root(tmp_path, {
        "cg_a": {"images": ["img1", "img2"], "require": ["cg_end1", "cg_end2"]},
        "cg_b": ["img3"],
    })
    cells = data.load_gallery_config(root)
    by = {c["name"]: c for c in cells}
    assert by["cg_a"]["images"] == ["img1", "img2"]
    assert by["cg_a"]["require"] == ["cg_end1", "cg_end2"]
    assert by["cg_b"]["images"] == ["img3"]
    assert by["cg_b"]["require"] == []  # 列表格式 = 无条件


def test_gallery_require未满足锁定():
    from engine.ui import UI
    ui = UI()
    ui.set_gallery_config([
        {"name": "cg_mary", "images": ["x"], "require": ["cg_end1", "cg_end2"]},
        {"name": "cg_end1", "images": ["y"]},
    ])
    # 只解锁了 cg_end1：require 未满足 → 锁
    ui.set_gallery(["cg_end1"], [])
    items = {i["name"]: i for i in ui._gallery_items()}
    assert items["cg_mary"]["unlocked"] is False
    # 4 结局全通 → 解锁
    ui.set_gallery(["cg_end1", "cg_end2"], [])
    items = {i["name"]: i for i in ui._gallery_items()}
    assert items["cg_mary"]["unlocked"] is True


def test_gallery_旧格式不受影响():
    from engine.ui import UI
    ui = UI()
    ui.set_gallery_config([{"name": "cg_a", "images": ["x"]}])
    ui.set_gallery(["cg_a"], [])
    items = ui._gallery_items()
    assert items[0]["unlocked"] is True


# ---------- 6. 月光漫步配置对齐（仓库真实文件） ----------

def test_月光漫步配置已带标题音乐与require():
    root = Path("games/月光漫步")
    if not root.is_dir():
        pytest.skip("月光漫步不在仓库内")
    cfg = json.loads((root / "config.json").read_text(encoding="utf-8-sig"))
    assert cfg.get("title_music") == "waves"
    gal = json.loads((root / "gallery_config.json").read_text(encoding="utf-8-sig"))
    need = {"cg_end1", "cg_end2", "cg_end3", "cg_end4"}
    for key in ("cg_dark_mary", "cg_dawn_mary"):
        assert isinstance(gal[key], dict), f"{key} 应为对象格式"
        assert set(gal[key]["require"]) == need, f"{key} 应要求 4 结局全通"
