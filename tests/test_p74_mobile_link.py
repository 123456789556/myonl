"""手机端：插线推成品 + AI 配置（P88 之后只剩这两块）的单元测试。

判据都是可验证的事实，不碰网络、不碰真机：
- 没 adb / 没设备时如实返回 ok=False 和一句人话；
- AI 配置绝不把明文 key 交给前端（payload 里只有掩码）；
- 保存时空 key = 沿用旧 key，clear_key 才真清。

P88 砍掉了「手机连接」（扫码 / 局域网地址），二维码那几条测试一并删掉。
"""
from __future__ import annotations

import json
import os

import pytest

from engine import ai, mobile_link

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


@pytest.fixture()
def ai_home(monkeypatch, tmp_path):
    """把 AI 配置目录指到临时目录，别动用户真的 ~/.myonl。"""
    d = tmp_path / "ai-home"
    monkeypatch.setattr(ai, "CONFIG_DIR", str(d))
    monkeypatch.setattr(ai, "CONFIG_PATH", str(d / "ai.json"))
    return d


def test_ai_默认关闭且不泄露_key(ai_home):
    p = ai.payload()
    assert p["ok"] is True
    assert p["enabled"] is False
    assert p["has_key"] is False
    assert p["key_mask"] == ""
    assert "key" not in {k for k, v in p.items() if isinstance(v, str) and v.startswith("sk-")}


def test_ai_保存后只回掩码(ai_home):
    ai.save({"key": "sk-abcdefghijklmn", "model": "m1", "enabled": True})
    p = ai.payload()
    assert p["has_key"] is True
    assert p["model"] == "m1"
    assert p["key_mask"].startswith("sk-a")
    assert "abcdefghij" not in json.dumps(p)      # 中间段不外泄
    assert "sk-abcdefghijklmn" not in json.dumps(p)


def test_ai_空key沿用旧值_clear才清(ai_home):
    ai.save({"key": "sk-original"})
    ai.save({"key": "", "model": "m2"})           # 空 key = 不动
    assert ai.payload()["has_key"] is True
    ai.save({"clear_key": True})
    assert ai.payload()["has_key"] is False


def test_ai_base_url_必须是_http(ai_home):
    r = ai.save({"base_url": "ftp://x"})
    assert r["ok"] is False
    r = ai.save({"base_url": "https://api.example.com/v1"})
    assert r["ok"] is True
    assert ai.payload()["base_url"] == "https://api.example.com/v1"


def test_ai_数值夹紧(ai_home):
    ai.save({"max_tokens": 1, "timeout": 9999})
    p = ai.payload()
    assert p["max_tokens"] == 64
    assert p["timeout"] == 120


def test_ai_ping_没key时直接说没配(ai_home):
    r = ai.ping()
    assert r["ok"] is False
    assert "key" in r["message"]


def test_ai_配置文件权限尽量收紧(ai_home):
    ai.save({"key": "sk-x"})
    path = ai.CONFIG_PATH
    assert os.path.isfile(path)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["key"] == "sk-x"
