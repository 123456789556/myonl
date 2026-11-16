"""P56 可迁移导出的测试：Ren'Py 投影 / 通用 JSON / 编辑器路由。

这一层的意义是「不被锁死」：作者随时能把剧本和素材带走。所以测试盯的是
**带走的东西是否真能用**——不是「跑通了」，而是「Ren'Py 语法结构对不对、
图有没有真拷过去、缺什么有没有如实报出来」。
"""
from __future__ import annotations

import json
import os
import socket
import sys
import threading

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import editor as E  # noqa: E402
from engine import portable as P  # noqa: E402

pytestmark = [pytest.mark.unit]

DEMO = os.path.join(ROOT, "games", "教程示例")


def _mini_project(tmp_path, text: str) -> str:
    proj = tmp_path / "迷你工程"
    proj.mkdir()
    (proj / "script.gal").write_text(text, encoding="utf-8")
    (proj / "images").mkdir()
    return str(proj)


# ============ 1. Ren'Py 投影 ============


@pytest.mark.integration
def test_RenPy工程结构与语法骨架(tmp_path):
    out = tmp_path / "renpy"
    stat = P.build_renpy(DEMO, str(out))
    script = (out / "game" / "script.rpy").read_text(encoding="utf-8")
    # 起手必须有 label start，且不能重复定义同名 label（Ren'Py 会直接报错）
    assert "label start" in script
    assert script.count("\nlabel start:") <= 1
    assert "menu:" in script                       # 选项翻成 menu
    assert "jump " in script                       # 跳转保留
    assert "scene " in script and "show " in script  # 背景/立绘
    assert "return" in script                      # @end
    # 每个 image 声明都要指向真实存在的图
    for line in script.splitlines():
        if line.startswith("image "):
            rel = line.split('"')[1]
            assert (out / "game" / rel).is_file(), f"声明的图不存在：{rel}"
    assert stat["images"] >= 1
    # options.rpy 与 README 也要在（作者打开就得知道怎么跑）
    assert (out / "game" / "options.rpy").is_file()
    assert "Ren'Py SDK" in (out / "README.md").read_text(encoding="utf-8")


@pytest.mark.integration
def test_RenPy不假造中文标识符(tmp_path):
    """中文图名/label 统一换英文短名，原名进注释——否则换台机器就可能编不过。"""
    out = tmp_path / "renpy"
    P.build_renpy(DEMO, str(out))
    script = (out / "game" / "script.rpy").read_text(encoding="utf-8")
    decls = [ln for ln in script.splitlines() if ln.startswith("image ")]
    assert decls, "没有 image 声明"
    for ln in decls:
        short = ln.split()[1]
        assert short.isascii(), f"图像短名不是 ASCII：{short}"
        assert "#" in ln, "短名旁边要写原名注释"


@pytest.mark.integration
def test_桌面专属指令如实标记(tmp_path):
    proj = _mini_project(tmp_path, "@music bgm_main\n@label start\n@ 测试\n@end\n")
    stat = P.build_renpy(proj, str(tmp_path / "out"))
    assert "music" in stat["unsupported"]
    # 没投影的指令不许出现在 .rpy 里（假装支持比不写更坏）
    script = (tmp_path / "out" / "game" / "script.rpy").read_text(encoding="utf-8")
    assert "bgm_main" not in script


@pytest.mark.integration
def test_缺素材记进告警不硬失败(tmp_path):
    proj = _mini_project(tmp_path, "@bg 不存在的背景\n@label start\n@ 旁白\n@end\n")
    stat = P.build_renpy(proj, str(tmp_path / "out"))
    assert "不存在的背景" in stat["missing"]
    assert any("背景没找到" in w for w in stat["warnings"])


# ============ 2. 通用 JSON ============


@pytest.mark.integration
def test_通用JSON带格式说明与素材清单(tmp_path):
    out = tmp_path / "json"
    stat = P.build_json(DEMO, str(out))
    data = json.loads((out / "game.json").read_text(encoding="utf-8"))
    assert data["format"] == "myonl-ir/1"
    assert data["ins"] and data["ins"][0]["op"] == "character"
    assert data["characters"][0]["name"] == "林晚"
    for key, rel in data["assets"].items():
        assert (out / rel).is_file(), f"素材清单里的文件不存在：{rel}"
    readme = (out / "README.md").read_text(encoding="utf-8")
    for token in ("myonl-ir/1", "| `say` |", "| `choice` |", "| `if` |"):
        assert token in readme, f"格式说明缺 {token}"
    assert stat["instructions"] >= 10


@pytest.mark.integration
def test_both_两个目标都产出(tmp_path):
    res = P.build_portable(DEMO, str(tmp_path / "pkg"), engine="both")
    engines = [s["engine"] for s in res["stats"]]
    assert engines == ["json", "renpy"]
    assert os.path.isfile(tmp_path / "pkg" / "json" / "game.json")
    assert os.path.isfile(tmp_path / "pkg" / "renpy" / "game" / "script.rpy")
    with pytest.raises(ValueError):
        P.build_portable(DEMO, str(tmp_path / "x"), engine="unity")


# ============ 3. 编辑器路由 ============


def _req(port, method, path):
    import http.client
    from urllib.parse import quote

    safe = quote(path, safe="/:?&=%")
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=20)
    body = json.dumps({"engine": "both"}).encode("utf-8") if method == "POST" else None
    conn.request(method, safe, body, {"Content-Type": "application/json"})
    resp = conn.getresponse()
    raw = resp.read()
    headers = dict(resp.getheaders())
    conn.close()
    return resp.status, raw, headers


@pytest.mark.integration
def test_接口端到端_导出可迁移包并能下载(tmp_path):
    games = tmp_path / "games"
    games.mkdir()
    proj = games / "小工程"
    proj.mkdir()
    (proj / "script.gal").write_text(
        "@character 甲 #ffffff\n@label start\n@[甲] 你好呀\n@end\n", encoding="utf-8")
    (proj / "images").mkdir()
    app = E.EditorApp(str(proj))
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    srv = E.ThreadingHTTPServer(("127.0.0.1", port), app.make_handler())
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        status, raw, _h = _req(port, "POST", "/api/export-portable")
        assert status == 200, raw
        data = json.loads(raw)
        assert data["ok"] is True
        assert [it["engine"] for it in data["items"]] == ["json", "renpy"]
        for item in data["items"]:
            assert os.path.isfile(item["zip"]), "没生成 zip"
            status, raw, headers = _req(port, "GET", item["url"])
            assert status == 200
            assert raw[:2] == b"PK", "下载回来的不是 zip"
            assert "attachment" in headers.get("Content-Disposition", "")
        # 越界防护：只认 dist/portable 下的 zip
        status, _raw, _h2 = _req(port, "GET", "/portable-file/../../etc/passwd")
        assert status in (400, 404)
    finally:
        srv.shutdown()


def test_编辑器有可迁移包入口():
    ui_js = open(os.path.join(ROOT, "editor", "editor_uidesign.js"), encoding="utf-8").read()
    for token in ("uidExportPortable", "/api/export-portable", "可迁移包"):
        assert token in ui_js, f"编辑器前端缺 {token}"
    assert ("POST", "/api/export-portable") in E._EditorHandler._ROUTES
    assert hasattr(E._EditorHandler, "_serve_portable_file")
