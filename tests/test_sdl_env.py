# -*- coding: utf-8 -*-
"""无头预览的环境隔离：dummy SDL 只能影响本次预览，不能污染「运行」子进程。"""
from __future__ import annotations

import os

import pytest

from engine.sdl_env import dummy_video

pytestmark = [pytest.mark.unit]


def test_dummy_video退出后恢复原值(monkeypatch):
    monkeypatch.setenv("SDL_VIDEODRIVER", "windows")
    monkeypatch.delenv("SDL_AUDIODRIVER", raising=False)

    @dummy_video
    def _inside():
        assert os.environ["SDL_VIDEODRIVER"] == "dummy"
        assert os.environ["SDL_AUDIODRIVER"] == "dummy"
        return 42

    assert _inside() == 42
    assert os.environ["SDL_VIDEODRIVER"] == "windows"
    assert "SDL_AUDIODRIVER" not in os.environ


def test_预览不把dummy传给运行子进程(tmp_path, monkeypatch):
    """回归：以前 editor.py 用 setdefault 永久改成 dummy，点「运行」永远不弹窗。"""
    from engine import editor

    monkeypatch.delenv("SDL_VIDEODRIVER", raising=False)
    monkeypatch.delenv("SDL_AUDIODRIVER", raising=False)
    script = tmp_path / "script.gal"
    script.write_text("@ 你好\n@end\n", encoding="utf-8")

    png = editor._preview_png(str(script), str(tmp_path), max_frames=2)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert "SDL_VIDEODRIVER" not in os.environ
    assert "SDL_AUDIODRIVER" not in os.environ

    _cmd, env = editor._demo_spawn(str(script), str(tmp_path))
    assert env.get("SDL_VIDEODRIVER") != "dummy"
