# -*- coding: utf-8 -*-
"""编辑器内嵌教程 / 说明书（M1.5「边写边看」）。

设计约束（用户明确）：
- 开发者侧：教程以「侧栏/顶部入口打开文档」的形式提供，边做边看，不强制流程、不打断写作；
- 玩家侧：游戏里**不出现**新手任务清单/基础指导流程，教程结束也不弹窗——那是编辑器的事；
- 只读内置 md（白名单 id），不接受用户路径 → 天然无目录穿越。
"""
from __future__ import annotations

import http.client
import json
import socket
import threading
from urllib.parse import quote

import pytest

from engine import editor as editor_mod
from engine.editor import EditorApp, ThreadingHTTPServer

pytestmark = [pytest.mark.integration]


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture
def server(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    port = _free_port()
    app = EditorApp(str(tmp_path))
    srv = ThreadingHTTPServer(("127.0.0.1", port), app.make_handler())
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield port
    srv.shutdown()
    srv.server_close()


def _get(port, path):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    conn.request("GET", path)
    resp = conn.getresponse()
    raw = resp.read()
    conn.close()
    return resp.status, raw


def test_教程清单包含快速上手与开发者指南(server):
    status, raw = _get(server, "/api/help")
    assert status == 200
    data = json.loads(raw.decode("utf-8"))
    assert data["ok"] is True
    ids = {item["id"] for item in data["docs"]}
    assert "quickstart" in ids and "dev-guide" in ids


def test_读取指定教程返回正文(server):
    status, raw = _get(server, "/api/help/doc?id=quickstart")
    assert status == 200
    data = json.loads(raw.decode("utf-8"))
    assert data["ok"] is True
    assert data["title"] == "快速上手"
    assert "快速上手" in data["text"]
    assert "# " in data["text"]  # 是 markdown 原文，前端负责渲染


def test_未知教程id返回404(server):
    status, raw = _get(server, "/api/help/doc?id=" + quote("不存在"))
    assert status == 404
    assert json.loads(raw.decode("utf-8"))["ok"] is False


def test_目录穿越被白名单挡住(server):
    for bad in ("../engine/config.py", "..%2Fengine%2Fconfig.py", "/etc/passwd", "quickstart/../secret"):
        status, _raw = _get(server, "/api/help/doc?id=" + bad)
        assert status == 404, f"{bad} 不该被读到"


def test_文档缺失时不崩(server, tmp_path, monkeypatch):
    monkeypatch.setattr(editor_mod, "_docs_dir", lambda: str(tmp_path / "no_such_docs"))
    status, raw = _get(server, "/api/help")
    assert status == 200
    assert json.loads(raw.decode("utf-8"))["docs"] == []
    status, _raw = _get(server, "/api/help/doc?id=quickstart")
    assert status == 404


def test_打包形态文档目录(monkeypatch, tmp_path):
    """PyInstaller 冻结后从 _MEIPASS/docs 读教程（发行包里也能看）。"""
    import sys

    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert editor_mod._docs_dir() == str(tmp_path / "docs")
