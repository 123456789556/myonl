# -*- coding: utf-8 -*-
"""桌面窗口（pywebview）关闭确认：有未保存修改时先弹确认框，取消则留在窗口。

桌面版关闭窗口走的是原生窗口事件，浏览器那套 beforeunload 不一定生效，
因此由前端把脏状态通知给 Python（_EditorBridge），关闭时只看这个布尔量。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from engine.editor_app import (CLOSE_CONFIRM_TEXT, _EditorBridge,
                               make_closing_handler)

pytestmark = [pytest.mark.unit]

ROOT = Path(__file__).resolve().parent.parent


class _FakeWindow:
    def __init__(self, answer=True, explode=False):
        self.calls = []
        self._answer = answer
        self._explode = explode

    def create_confirmation_dialog(self, title, text):
        self.calls.append((title, text))
        if self._explode:
            raise OSError("对话框不可用")
        return self._answer


def test_没有未保存修改直接关闭():
    win = _FakeWindow()
    bridge = _EditorBridge()
    assert make_closing_handler(win, bridge)() is True
    assert win.calls == [], "无未保存时不应弹确认框"


def test_有未保存修改时弹确认框并可取消关闭():
    win = _FakeWindow(answer=False)
    bridge = _EditorBridge()
    bridge.set_dirty(True)
    assert make_closing_handler(win, bridge)() is False, "用户取消应阻止关闭"
    assert win.calls and win.calls[0][1] == CLOSE_CONFIRM_TEXT
    assert "未保存" in CLOSE_CONFIRM_TEXT


def test_确认后允许关闭():
    win = _FakeWindow(answer=True)
    bridge = _EditorBridge()
    bridge.set_dirty(True)
    assert make_closing_handler(win, bridge)() is True


def test_确认框不可用时不阻塞关闭():
    win = _FakeWindow(explode=True)
    bridge = _EditorBridge()
    bridge.set_dirty(True)
    assert make_closing_handler(win, bridge)() is True, "确认框故障不能导致关不掉窗口"


def test_保存后脏标记复位():
    bridge = _EditorBridge()
    bridge.set_dirty(True)
    assert bridge.dirty is True
    bridge.set_dirty(False)
    assert bridge.dirty is False


def test_前端把脏状态同步给桌面窗口():
    js = (ROOT / "editor" / "editor_pro.js").read_text(encoding="utf-8")
    assert "window.pywebview.api.set_dirty(anyDirty)" in js, "脏状态变化应通知 Python"
    assert "__proAnyDirty" in js, "应暴露任一文件未保存的查询入口"
