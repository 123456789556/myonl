# -*- coding: utf-8 -*-
"""演出节奏默认值（config.pacing）：现代 galgame 手感的三层默认值之一。

引擎默认（config.DEFAULTS.pacing） ← 项目配置（config.json 的 pacing 段） ← 玩家设置（settings）。
本测试覆盖前两层：默认值、覆盖、非法兜底、以及渲染层是否真的读它。
"""
from __future__ import annotations

import json
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from pathlib import Path  # noqa: E402

import pytest  # noqa: E402

from engine import config as cfgapi  # noqa: E402
from engine.renderer import Renderer  # noqa: E402

pytestmark = [pytest.mark.unit]


def test_引擎默认节奏值():
    cfg = cfgapi.Config()
    pacing = cfg.pacing()
    assert pacing["scene_fade"] == 0.35
    assert pacing["dissolve"] == 0.45
    assert pacing["chapter_fade"] == 0.9
    assert pacing["scene_gap"] == 0.25
    assert pacing["auto_advance_ms"] == 900


def test_项目配置覆盖节奏():
    cfg = cfgapi.Config({"pacing": {"scene_fade": 0.75, "dissolve": 0.6}})
    assert cfg.pacing_value("scene_fade", 0.3) == 0.75
    assert cfg.pacing_value("dissolve", 0.45) == 0.6
    assert cfg.pacing_value("chapter_fade", 0.9) == 0.9  # 未覆盖保留默认


def test_非法与未知节奏键被忽略():
    cfg = cfgapi.Config({"pacing": {"scene_fade": "快一点", "chapter_fade": True,
                                        "不存在的键": 9}})
    assert cfg.pacing_value("scene_fade", 0.35) == 0.35
    assert cfg.pacing_value("chapter_fade", 0.9) == 0.9
    assert "不存在的键" not in cfg.pacing()


def test_pacing_value缺失键回落默认():
    cfg = cfgapi.Config()
    assert cfg.pacing_value("不存在的节奏", 1.25) == 1.25


def test_渲染层读取场景淡入默认值(tmp_path):
    (tmp_path / "config.json").write_text(
        json.dumps({"pacing": {"scene_fade": 0.75}}), encoding="utf-8")
    ren = Renderer(size=(1280, 720), assets_root=str(tmp_path))
    try:
        assert ren._pacing("scene_fade", 0.3) == 0.75
        assert ren._bg_fade_seconds == 0.75
        assert ren._pacing("dissolve", 0.45) == 0.45
    finally:
        ren.close()


def test_未配置时渲染层回到引擎默认(tmp_path):
    ren = Renderer(size=(1280, 720), assets_root=str(tmp_path))
    try:
        assert ren._bg_fade_seconds == 0.35
        assert ren._pacing("auto_advance_ms", 900) == 900
    finally:
        ren.close()
