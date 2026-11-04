# -*- coding: utf-8 -*-
"""存档 / 读档失败必须给可见反馈。

发行版没有控制台，失败只写 stderr 玩家永远看不到；这里守住存档失败、
读档失败两条路径都会弹 toast，读档失败还退回存档列表重选。
"""
from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

from engine.demo import _apply_business, _do_load
from engine.renderer import Renderer
from engine.save import SaveError
from engine.ui import UI

pytestmark = [pytest.mark.ui]


class _FailingRuntime:
    def save(self, slot):
        raise SaveError("磁盘已满")

    def load_save(self, slot):
        raise SaveError("存档损坏")


@pytest.fixture()
def ren(tmp_path):
    r = Renderer((1280, 720), str(tmp_path))
    yield r
    r.close()


def test_存档失败弹提示(ren, tmp_path):
    ui = UI()
    ui.mode = "slots"
    _apply_business({"action": "save_slot", "slot": 1}, _FailingRuntime(), ren, ui,
                    "", str(tmp_path / "settings.json"))
    assert "存档失败" in ren._toast_text


def test_读档失败弹提示并退回列表(ren):
    ui = UI()
    ui.mode = "playing"
    assert _do_load(_FailingRuntime(), ui, 1, ren) is None
    assert "读档失败" in ren._toast_text
    assert ui.mode == "slots", "读档失败应退回列表重选，而不是停在打不开的存档"
