"""P54 移动端编译链路的测试：编译器（webpack.py）真实跑一遍 + JS 端 node 冒烟。

要点：
- 编译器必须真的产出 pack.json / index.html / assets，且只拷引用到的素材；
- 缺素材不硬失败（记进 missing，让作者知道缺什么）；
- 桌面有、手机端没有的指令要如实列进 unsupported（不假装支持）；
- JS 侧的 VM 与布局用 node 直接跑（不需要浏览器）；
- 编辑器那条 HTTP 路由也要能用（导出 + 预览地址 + 越界防护）。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import webpack as W  # noqa: E402
from engine import editor as E  # noqa: E402

pytestmark = [pytest.mark.unit]

DEMO = os.path.join(ROOT, "games", "教程示例")
NODE = shutil.which("node")


def _run_node(script_rel: str) -> subprocess.CompletedProcess:
    # node 一定输出 UTF-8；不显式指定的话 subprocess 会按本机 locale 解（CI 上是 cp1252），
    # 中文日志就变成乱码、stdout 甚至直接 None，断言全挂——必须钉死 utf-8
    return subprocess.run([NODE, os.path.join(ROOT, script_rel)],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=60)


# ============ 1. 编译器：真实项目 ============


@pytest.mark.integration
def test_编译器产出完整包(tmp_path):
    out = tmp_path / "web"
    stat = W.build_web(DEMO, str(out))
    assert os.path.isfile(out / "index.html")
    assert os.path.isfile(out / "pack.json")
    for name in ("myonl-core.js", "myonl-layout.js", "myonl-player.js"):
        assert os.path.isfile(out / name), f"播放器文件没拷过去：{name}"
    assert stat["instructions"] >= 10
    assert stat["images"] >= 1
    pack = json.loads((out / "pack.json").read_text(encoding="utf-8"))
    assert pack["version"] == 1
    assert pack["ins"] and pack["ins"][0]["op"] == "character"
    # 角色表带颜色（播放器拿它决定名字颜色）
    names = {c["name"]: c for c in pack["characters"]}
    assert "林晚" in names and names["林晚"]["color"].startswith("#")
    # 素材清单指向真实文件，且 index.html 引脚本
    for key, rel in pack["assets"].items():
        assert os.path.isfile(out / rel), f"清单里的素材不存在：{rel}"
    html = (out / "index.html").read_text(encoding="utf-8")
    for token in ("myonl-core.js", "myonl-layout.js", "myonl-player.js", 'id="game"'):
        assert token in html
    assert "user-scalable=no" in html          # 手机上别让它双指缩放画布
    # config 只挑播放器用得上的子集，且对话框皮肤键完整带过去
    assert "dialogue" in pack["config"]
    dlg = pack["config"]["dialogue"].get("default") or {}
    assert dlg.get("panel_image") == "textbox"


@pytest.mark.integration
def test_只拷引用到的素材(tmp_path):
    out = tmp_path / "web"
    W.build_web(DEMO, str(out))
    pack = json.loads((out / "pack.json").read_text(encoding="utf-8"))
    copied = sorted(os.listdir(out / "assets"))
    expected = sorted(os.path.basename(v) for v in pack["assets"].values())
    assert copied == expected, "assets/ 里出现了没被引用的图（会导致包变大）"


@pytest.mark.integration
def test_缺素材不硬失败(tmp_path):
    proj = tmp_path / "缺图工程"
    shutil.copytree(DEMO, proj)
    # 删掉背景图，编译器要照常出包，只把缺失记进 missing
    for f in os.listdir(proj / "images"):
        if f.startswith("bg_"):
            os.remove(proj / "images" / f)
    out = tmp_path / "web"
    stat = W.build_web(str(proj), str(out))
    assert os.path.isfile(out / "pack.json")
    assert stat["missing"], "缺素材没被发现"


@pytest.mark.integration
def test_桌面专属指令如实标注(tmp_path):
    """P62 起 music/sfx 手机端已实现；仍不实现的（cg/video/…）必须如实列出来。"""
    proj = tmp_path / "带音乐工程"
    proj.mkdir()
    (proj / "script.gal").write_text(
        "@character 甲 #ffffff\n@label start\n@music bgm\n@cg 结尾图\n@[甲] 你好\n@end\n",
        encoding="utf-8")
    out = tmp_path / "web"
    stat = W.build_web(str(proj), str(out))
    assert "music" not in stat["unsupported"], "music 已经支持了，不该再报不支持"
    assert "cg" in stat["unsupported"], "桌面有、手机端没有的指令必须标注"
    pack = json.loads((out / "pack.json").read_text(encoding="utf-8"))
    assert "cg" in pack["unsupported"]


# ============ 2. JS 侧：node 直接跑（不需要浏览器）============


@pytest.mark.skipif(not NODE, reason="本机没有 node")
def test_内核冒烟_顺序分支变量存档():
    r = _run_node(os.path.join("web", "test", "vm-smoke.js"))
    assert r.returncode == 0, r.stderr
    assert "全部通过" in r.stdout


@pytest.mark.skipif(not NODE, reason="本机没有 node")
def test_布局冒烟_竖屏横屏都合格():
    r = _run_node(os.path.join("web", "test", "layout-smoke.js"))
    assert r.returncode == 0, r.stderr
    assert "全部通过" in r.stdout


@pytest.mark.skipif(not NODE, reason="本机没有 node")
@pytest.mark.parametrize("path", [
    os.path.join("web", "myonl-core.js"),
    os.path.join("web", "myonl-layout.js"),
    os.path.join("web", "myonl-player.js"),
])
def test_JS语法检查(path):
    r = subprocess.run([NODE, "--check", os.path.join(ROOT, path)],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, f"{path} 语法有问题：{r.stderr}"


@pytest.mark.skipif(not NODE, reason="本机没有 node")
def test_编辑器前端JS都有语法门禁():
    """编辑器前端一个引号写错就整页白屏，而 pytest 跑得再绿也发现不了——所以这里逐个 node --check。"""
    front = os.path.join(ROOT, "editor")
    bad = []
    for name in sorted(os.listdir(front)):
        if not name.endswith(".js"):
            continue
        r = subprocess.run([NODE, "--check", os.path.join(front, name)],
                           capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            bad.append(f"{name}: {r.stderr.strip().splitlines()[-3:]}")
    assert not bad, "编辑器前端语法有错：" + "；".join(str(b) for b in bad)


@pytest.mark.skipif(not NODE, reason="本机没有 node")
def test_播放器确实读厂房配置并且横竖屏都在():
    js = open(os.path.join(ROOT, "web", "myonl-player.js"), encoding="utf-8").read()
    lay = open(os.path.join(ROOT, "web", "myonl-layout.js"), encoding="utf-8").read()
    # 横竖屏都支持：布局按窗口比例，播放器监听转屏
    assert "orientationchange" in js and "addEventListener(\"resize\"" in js
    assert "landscape" in lay
    # 皮肤键必须在移动端也吃得下（和桌面端同一套语义）
    for token in ("panel_image", "panel_slice", "panel_texture", "panel_alpha", "pad_x"):
        assert token in js, f"播放器没读 {token}"
    # 打字机没完就先全显，别直接跳下一句
    assert "typeStart" in js
    # 编辑器里有「导出手机版」入口，且指向新路由（不然功能只在 CLI 里，作者用不到）
    ui_js = open(os.path.join(ROOT, "editor", "editor_uidesign.js"), encoding="utf-8").read()
    for token in ("uidExportWeb", "/api/export-web", "导出手机版"):
        assert token in ui_js, f"编辑器前端缺 {token}"
    assert ("POST", "/api/export-web") in E._EditorHandler._ROUTES
    assert ("GET", "/web-preview/x") not in E._EditorHandler._ROUTES  # 前缀路由，不在注册表
    assert hasattr(E._EditorHandler, "_serve_web_preview")


def test_发行包会带上手机端播放器():
    """发行版 editor.exe 里导出手机版要能跑：spec 必须打 web/ 三个 js，且 webpack 能定位到。"""
    spec = open(os.path.join(ROOT, "editor.spec"), encoding="utf-8").read()
    for name in ("myonl-core.js", "myonl-layout.js", "myonl-player.js"):
        assert name in spec, f"editor.spec 打包清单缺 {name}"
        assert os.path.isfile(os.path.join(ROOT, "web", name))
    assert "engine.webpack" in spec, "hiddenimports 缺 engine.webpack（懒加载在 frozen 下会失败）"
    # frozen 时走 _MEIPASS，源码版走仓库 web/
    assert "_MEIPASS" in open(os.path.join(ROOT, "engine", "webpack.py"), encoding="utf-8").read()


# ============ 3. 编辑器路由：导出 + 预览 ============


def _req(port, method, path, body=None):
    import http.client
    from urllib.parse import quote
    # 工程名是中文：路径必须 percent-encode，否则 http.client 直接拒发
    safe = quote(path, safe="/:?&=%")
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=20)
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    conn.request(method, safe, data, {"Content-Type": "application/json"})
    resp = conn.getresponse()
    raw = resp.read()
    conn.close()
    return resp.status, raw


@pytest.mark.integration
def test_接口端到端_导出手机版与预览(tmp_path):
    import threading

    games = tmp_path / "games"
    games.mkdir()
    proj = games / "小工程"
    proj.mkdir()
    (proj / "script.gal").write_text(
        "@character 甲 #ffffff\n@label start\n@[甲] 你好呀\n@end\n", encoding="utf-8")
    (proj / "images").mkdir()
    app = E.EditorApp(str(proj))
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    srv = E.ThreadingHTTPServer(("127.0.0.1", port), app.make_handler())
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        status, raw = _req(port, "POST", "/api/export-web", {})
        assert status == 200, raw
        data = json.loads(raw)
        assert data["ok"] is True
        out = os.path.join(app.pack_root(), "dist", "web", "小工程")
        assert os.path.isfile(os.path.join(out, "pack.json"))
        assert data["url"].endswith("/index.html")
        # 预览地址能真的拿到 index.html（不是死链）
        status, raw = _req(port, "GET", data["url"])
        assert status == 200 and b'id="game"' in raw
        # pack.json 也能读（播放器第一件事就是取它）
        status, raw = _req(port, "GET", "/web-preview/小工程/pack.json")
        assert status == 200 and json.loads(raw)["version"] == 1
        # 越界防护：不让人用 ../ 读工程外的文件
        status, raw = _req(port, "GET", "/web-preview/../../etc/passwd")
        assert status in (400, 404)
    finally:
        srv.shutdown()
