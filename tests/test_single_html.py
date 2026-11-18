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
def test_单文件自身体积有报告(tmp_path):
    """P119：解码内存预算管的是"摊在画面上要多少"，管不到"这个 HTML 自身多重"。

    手机要先把整个文件读进内存才出第一句，40 MB 起明显慢、80 MB 大概率白屏，
    所以打包结果必须单独报文件体积和警告。
    """
    out = tmp_path / "game.html"
    stat = W.build_single(DEMO, str(out))
    assert "file_mb" in stat, "打包结果缺 file_mb"
    assert "file_warning" in stat, "打包结果缺 file_warning"
    assert stat["file_mb"] > 0
    assert stat["file_mb"] == round(os.path.getsize(out) / (1024 * 1024), 1)
    # 小工程的示例包不该触发警告
    assert stat["file_warning"] == "", f"示例工程不该报警告：{stat['file_warning']}"


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


# ---- P62：音频内嵌 ----


def _make_project(tmp_path, script, *, audio=(), images=()):
    """造一个最小工程（剧本 + 需要的音频/图片）。"""
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "script.gal").write_text(script, encoding="utf-8")
    if audio:
        d = proj / "audio"
        d.mkdir()
        for name in audio:
            (d / name).write_bytes(b"OggS\x00fake-audio-bytes")
    if images:
        d2 = proj / "images"
        d2.mkdir()
        for name in images:
            (d2 / name).write_bytes(b"\x89PNG\r\n\x1a\nfake")
    return proj


def test_音频被收集进_pack(tmp_path):
    proj = _make_project(
        tmp_path,
        "@character 甲 #ffffff\n@music bgm_a\n@label start\n@[甲] 你好\n@sfx se_1\n@end\n",
        audio=("bgm_a.ogg", "se_1.ogg"))
    out = tmp_path / "web"
    stat = W.build_web(str(proj), str(out))
    assert stat["audio"] == 2, stat
    pack = json.loads((out / "pack.json").read_text(encoding="utf-8"))
    assert set(pack["audio"]) == {"bgm_a", "se_1"}
    assert os.path.isfile(out / "assets" / "bgm_a.ogg")
    # 已经实现了，不该再报"暂不支持"
    assert "music" not in pack["unsupported"]


def test_单文件里音频是_data_uri(tmp_path):
    proj = _make_project(
        tmp_path,
        "@character 甲 #ffffff\n@music bgm_a\n@label start\n@[甲] 你好\n@end\n",
        audio=("bgm_a.ogg",))
    out = tmp_path / "g.html"
    stat = W.build_single(str(proj), str(out))
    html = _read(out)
    assert "data:audio/ogg;base64," in html
    assert stat["audio"] == 1


def test_缺音频不硬失败(tmp_path):
    proj = _make_project(
        tmp_path,
        "@character 甲 #ffffff\n@music 没有这首\n@label start\n@[甲] 你好\n@end\n",
        audio=())
    out = tmp_path / "g.html"
    stat = W.build_single(str(proj), str(out))
    assert os.path.isfile(out)
    assert "没有这首" in stat["missing"]


# ---- P62：大图压缩 ----


def test_大图会被压小(tmp_path):
    pytest.importorskip("PIL")
    import random
    from PIL import Image

    proj = tmp_path / "proj"
    (proj / "images").mkdir(parents=True)
    px = bytearray()
    rnd = random.Random(3)
    for _ in range(1200 * 1200):
        px += bytes((rnd.randrange(256), rnd.randrange(256), rnd.randrange(256)))
    Image.frombytes("RGB", (1200, 1200), bytes(px)).save(proj / "images" / "noise.png")
    (proj / "script.gal").write_text(
        "@character 甲 #ffffff\n@bg noise\n@label start\n@[甲] 你好\n@end\n", encoding="utf-8")

    out = tmp_path / "g.html"
    stat = W.build_single(str(proj), str(out))
    assert stat["saved"] > 100 * 1024, stat
    assert "data:image/webp;base64," in _read(out)


# ---- P63：@cg 全屏演出 ----


def test_cg_图会被收集并内嵌(tmp_path):
    """@cg 之前根本没收集，导到手机上就是空白。"""
    proj = tmp_path / "proj"
    (proj / "images").mkdir(parents=True)
    (proj / "images" / "cg_拥抱.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")
    (proj / "script.gal").write_text(
        "@character 甲 #ffffff\n@bg bg_a\n@label start\n@[甲] 好\n"
        "@cg cg_拥抱\n@ 看这一幕\n@bg bg_a\n@end\n", encoding="utf-8")
    out = tmp_path / "web"
    stat = W.build_web(str(proj), str(out))
    pack = json.loads((out / "pack.json").read_text(encoding="utf-8"))
    assert "cg_拥抱" in pack["assets"], "CG 图必须进素材表"
    assert "cg" not in pack["unsupported"], "cg 已实现，不该再报不支持"
    assert "bg_a" in stat["missing"]      # 背景确实不存在，如实记录

    single = tmp_path / "g.html"
    W.build_single(str(proj), str(single))
    html = _read(single)
    assert "cg_拥抱" in html and "data:image/png;base64," in html


def test_小图保持原样(tmp_path):
    pytest.importorskip("PIL")
    from PIL import Image

    proj = tmp_path / "proj"
    (proj / "images").mkdir(parents=True)
    Image.new("RGB", (40, 40), (1, 2, 3)).save(proj / "images" / "tiny.png")
    (proj / "script.gal").write_text(
        "@character 甲 #ffffff\n@bg tiny\n@label start\n@[甲] 你好\n@end\n", encoding="utf-8")
    out = tmp_path / "g.html"
    stat = W.build_single(str(proj), str(out))
    assert stat["saved"] == 0
    assert "data:image/png;base64," in _read(out)


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
