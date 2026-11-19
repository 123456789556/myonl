"""A3：坏 JSON body 必须在进业务路由前被 400 拦下，不能静默回空 dict 落盘。

背景（审计 A3）：`_read_json` 以前把截断 JSON / 非 JSON 文本 / 编码错和空 body
一样静默返回 `{}`。实测 `/api/characters`、`/api/script` 拿到空 dict 后蒙过校验，
把原角色库/剧本清空，前端却收到 200 `ok:true`。本文件锁死修复口径：

- 坏 body（截断、非 JSON、非 UTF-8）→ HTTP 400，`ok:false`，带「请求体不是合法 JSON」；
- 落盘文件保持原样，不被清空；
- 空 body 仍走旧的空 dict 兜底（与修复前行为一致）；
- 合法 JSON 正常保存，基线不回归。
"""
from __future__ import annotations

import http.client
import json
import os
import socket
import sys
import threading

import pytest

from engine.editor import EditorApp, ThreadingHTTPServer

pytestmark = [pytest.mark.integration]

CHARACTERS_ORIGINAL = {
    "schema": 1,
    "characters": [{"id": "lin", "name": "林晚", "color": "#ffcccc", "kind": "face"}],
}
SCRIPT_ORIGINAL = "@character 林晚 #ffcccc\n@label start\n@ 林晚 原文，不能被清空\n"


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture
def server(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "script.gal").write_text(SCRIPT_ORIGINAL, encoding="utf-8")
    (tmp_path / "characters.json").write_text(
        json.dumps(CHARACTERS_ORIGINAL, ensure_ascii=False), encoding="utf-8")
    port = _free_port()
    app = EditorApp(str(tmp_path))
    srv = ThreadingHTTPServer(("127.0.0.1", port), app.make_handler())
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield port, str(tmp_path)
    srv.shutdown()
    srv.server_close()


def _raw_post(port, path, raw: bytes):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    conn.request("POST", path, raw,
                 {"Content-Type": "application/json", "Content-Length": str(len(raw))})
    resp = conn.getresponse()
    body = resp.read()
    conn.close()
    return resp.status, body


def _json_post(port, path, obj):
    return _raw_post(port, path, json.dumps(obj, ensure_ascii=False).encode("utf-8"))


BAD_BODIES = [
    ("截断 JSON", b'{"text": "hello'),
    ("非 JSON 文本", b"this is not json at all <<<>>>"),
    ("非 UTF-8 字节", b'{"text": "\xff\xfe bad"}'),
]


@pytest.mark.parametrize("label,raw", BAD_BODIES)
def test_坏body打剧本保存_回400且剧本不被清空(server, label, raw):
    port, project = server
    status, body = _raw_post(port, "/api/script", raw)
    assert status == 400
    resp = json.loads(body.decode("utf-8"))
    assert resp["ok"] is False
    assert "合法 JSON" in resp["message"]
    assert open(os.path.join(project, "script.gal"), encoding="utf-8").read() == SCRIPT_ORIGINAL


@pytest.mark.parametrize("label,raw", BAD_BODIES)
def test_坏body打角色库_回400且角色不被清空(server, label, raw):
    port, project = server
    status, body = _raw_post(port, "/api/characters", raw)
    assert status == 400
    resp = json.loads(body.decode("utf-8"))
    assert resp["ok"] is False
    saved = json.loads(open(os.path.join(project, "characters.json"), encoding="utf-8").read())
    assert saved == CHARACTERS_ORIGINAL


def test_空body不当成坏JSON(server):
    # 修复只把「解码失败」标成坏 body；空 body 仍是旧的空 dict 兜底，路由自己做参数校验。
    port, project = server
    status, body = _raw_post(port, "/api/script", b"")
    resp = json.loads(body.decode("utf-8"))
    assert "合法 JSON" not in resp.get("message", ""), "空 body 不应被报成坏 JSON"


def test_合法JSON保存基线不回归(server):
    port, project = server
    new_text = "@ 林晚 合法保存\n"
    status, body = _json_post(port, "/api/script", {"text": new_text})
    assert status == 200
    assert json.loads(body.decode("utf-8"))["ok"] is True
    assert open(os.path.join(project, "script.gal"), encoding="utf-8").read() == new_text
