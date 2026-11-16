"""P61 单文件导出的测试：一个 .html 里带剧本 + 播放器 + 图片，能在 file:// 下跑。

要点：
- 产物只有一个文件，图片必须是 data URI（不能留 assets/ 引用，否则发出去就断图）；
- pack 内联成 window.__MYONL_PACK__，播放器不能再 fetch("pack.json")；
- </script> 这种会把内联脚本提前闭合的序列必须被转义；
- 缺素材不硬失败；CLI --single 与编辑器 HTTP 路由都要能用。
"""
from __future__ import annotations

import json
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import webpack as W  # noqa: E402

pytestmark = [pytest.mark.unit]

DEMO = os.path.join(ROOT, "games", "教程示例")


def _read(path) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


# ============ 1. 产物 ============


@pytest.mark.integration
def test_单文件只有一个产物且素材内嵌(tmp_path):
    out = tmp_path / "game.html"
    stat = W.build_single(DEMO, str(out))
    assert os.path.isfile(out)
    assert stat["bytes"] == os.path.getsize(out)
    html = _read(out)

    # 没有外链资源：不能出现 src="assets/ 或 src="*.js"
    assert 'src="assets/' not in html
    assert "<script src=" not in html
    # pack 内联
    assert "window.__MYONL_PACK__=" in html
    # 图片是 data URI
    assert "data:image/png;base64," in html


@pytest.mark.integration
def test_内联的_pack_能解析且指令齐全(tmp_path):
    out = tmp_path / "game.html"
    W.build_single(DEMO, str(out))
    html = _read(out)
    m = re.search(r"window\.__MYONL_PACK__=(\{.*?\});</script>", html, re.S)
    assert m, "没找到内联 pack"
    pack = json.loads(m.group(1))
    assert pack["single"] is True
    assert pack["ins"] and pack["ins"][0]["op"] == "character"
    assert pack["assets"], "素材表不能是空的"
    assert all(v.startswith("data:") for v in pack["assets"].values())


@pytest.mark.integration
def test_播放器三个文件都内联了(tmp_path):
    out = tmp_path / "game.html"
    W.build_single(DEMO, str(out))
    html = _read(out)
    # 播放器独有标识：三个文件的关键符号都得在
    assert "createVM" in html            # myonl-core.js
    assert "function fit" in html or "const fit" in html  # myonl-layout / player
    assert "bootPack" in html            # 单文件启动分支
    assert html.count("<script>") >= 4   # pack + 三个播放器


# ============ 2. 边界 ============


def test_script_闭合序列被转义():
    assert W._js_safe("a</script>b") == "a<\\/script>b"
    assert "</SCRIPT" not in W._js_safe("</SCRIPT>")


@pytest.mark.integration
def test_缺素材时仍能生成(tmp_path):
    """把一个素材改名，导出不该抛异常，只是少一张图。"""
    import shutil

    proj = tmp_path / "proj"
    shutil.copytree(DEMO, proj)
    images = proj / "images"
    if images.is_dir():
        first = sorted(p for p in images.iterdir() if p.is_file())
        if first:
            first[0].rename(first[0].with_suffix(".gone"))
    out = tmp_path / "g.html"
    stat = W.build_single(str(proj), str(out))
    assert os.path.isfile(out)
    assert stat["missing"] or stat["images"] >= 1


@pytest.mark.integration
def test_cli_single(tmp_path):
    out = tmp_path / "cli.html"
    assert W.main([DEMO, "--single", str(out)]) == 0
    assert os.path.isfile(out)


# ============ 3. 编辑器路由 ============


@pytest.mark.integration
def test_编辑器导出单文件并能取回(tmp_path):
    """点一次「导出一个文件」→ 拿到 /single-file/ 地址 → 真能取回整份 HTML。"""
    import socket
    import threading
    from urllib.parse import quote

    import urllib.request

    from engine import editor as E

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
    port2 = sock.getsockname()[1]
    sock.close()
    srv = E.ThreadingHTTPServer(("127.0.0.1", port2), app.make_handler())
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port2}/api/export-single",
            data=b"{}", headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8"))
        assert data["ok"] is True, data
        assert data["kb"] >= 1
        out = os.path.join(app.pack_root(), "dist", "single", "小工程.html")
        assert os.path.isfile(out)
        with urllib.request.urlopen(
                f"http://127.0.0.1:{port2}" + quote(data["url"]), timeout=30) as r:
            html = r.read().decode("utf-8")
        assert "window.__MYONL_PACK__=" in html
        # 越界防护
        try:
            urllib.request.urlopen(
                f"http://127.0.0.1:{port2}/single-file/../../secret.txt", timeout=10)
            raise AssertionError("越界读取没被拦住")
        except urllib.error.HTTPError as e:
            assert e.code in (400, 404)
    finally:
        srv.shutdown()



@pytest.mark.integration
def test_单文件路径越界被拒(tmp_path):
    """_safe_within 保护 /single-file/ 不会被 ../ 拉出去。"""
    from engine import editor as E

    base = os.path.join(str(tmp_path), "dist", "single")
    os.makedirs(base, exist_ok=True)
    with pytest.raises(ValueError):
        E._safe_within(base, "../secret.txt")
