# -*- coding: utf-8 -*-
"""M1：教程示例工程（games/教程示例）的可用性约束。

教程工程是发行包里给陌生人的第一印象，必须：
1. 文件齐全（剧本/配置/素材/打包档案/图标）
2. 可以直接跑：11 种指令，两条分支都能走到 @end
3. 零缺素材（否则新用户第一眼就是红字）
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.parser import parse_file
from engine.runtime import Runtime

pytestmark = [pytest.mark.unit]

PROJECT = Path(__file__).resolve().parents[1] / "games" / "教程示例"


def test_文件齐全():
    for rel in ("script.gal", "config.json", "settings.json", "gallery_config.json",
                "pack_config.json", "icon.png", "images/bg_教室.png", "images/bg_天台.png",
                "images/林晚_微笑.png", "images/林晚_生气.png"):
        assert (PROJECT / rel).is_file(), f"教程示例缺 {rel}"


def test_指令覆盖至少8种():
    ops = {i["op"] for i in parse_file(str(PROJECT / "script.gal"))}
    expected = {"character", "bg", "show", "say", "choice", "label", "set", "if", "jump", "end"}
    assert expected <= ops, f"教程缺指令：{expected - ops}"
    assert len(ops) >= 8


def test_两条分支都能结束():
    for choice in (0, 1):
        rt = Runtime()
        rt.load(str(PROJECT / "script.gal"))
        for _ in range(300):
            st = rt.snapshot()
            if st["finished"]:
                break
            if st["pending_wait"]:
                rt.advance_wait(999)
            elif st["pending_choice"] is not None:
                rt.choose(choice)
            else:
                rt.step()
        assert rt.snapshot()["finished"], f"分支 {choice} 没跑完"


def test_pack_config可打包():
    cfg = json.loads((PROJECT / "pack_config.json").read_text(encoding="utf-8"))
    for key in ("game_name", "version", "icon"):
        assert cfg.get(key), f"pack_config 缺 {key}"
