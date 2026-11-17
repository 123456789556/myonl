"""插线把成品推到手机（P88 砍掉扫码连接、P89 砍掉 AI 助手之后，只剩这一块）。

判据都是可验证的事实，不碰真机：
- 没 adb / 没设备时如实返回 ok=False 和一句人话；
- 没有设备时 push 不假装成功。
"""
from __future__ import annotations

import os

import pytest

from engine import mobile_link

pytestmark = [pytest.mark.unit]


def test_没有设备时_adb_如实报错(monkeypatch):
    monkeypatch.setattr(mobile_link, "_adb_path", lambda: "")
    st = mobile_link.adb_state()
    assert st["ok"] is False
    assert st["devices"] == []
    assert "adb" in st["message"]


def test_没有设备时_push_不假装成功(monkeypatch, tmp_path):
    monkeypatch.setattr(mobile_link, "_adb_path", lambda: "")
    f = tmp_path / "a.html"
    f.write_text("x", encoding="utf-8")
    r = mobile_link.adb_push(str(f))
    assert r["ok"] is False
    assert "adb" in r["message"]
