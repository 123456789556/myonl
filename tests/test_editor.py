"""编辑器 API 层测试（tests/test_editor.py）。

用 threading 起测试服务器于随机端口，http.client 请求，全部 headless。
覆盖：静态首页 / check / preview / complete / run / script 读写 / 路径穿越 / 端口占用 / 卡片视图 render 往返。
"""
from __future__ import annotations

import http.client
import json
import os
import socket
import sys
import threading

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
    """在随机端口起一个编辑器服务线程，返回 (port, project_root)。"""
    monkeypatch.chdir(tmp_path)
    port = _free_port()
    app = EditorApp(str(tmp_path))
    srv = ThreadingHTTPServer(("127.0.0.1", port), app.make_handler())
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield port, str(tmp_path)
    srv.shutdown()
    srv.server_close()


def _post(port, path, body):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    conn.request("POST", path, data, {"Content-Type": "application/json"})
    resp = conn.getresponse()
    raw = resp.read()
    conn.close()
    return resp.status, raw


def _get(port, path):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    conn.request("GET", path)
    resp = conn.getresponse()
    raw = resp.read()
    conn.close()
    return resp.status, resp, raw


VALID_SCRIPT = """@character 林晚 #ffcccc
@character 苏晨 #aaccff
@label start
@bg classroom
@show 林晚 smile
@ 林晚 今天天气真好
@ 苏晨 是啊
@choice:
    > 一起走吧 -> go
    > 改天吧 -> finish
@label go
@set score += 1
@end
@label finish
@end
"""

BAD_SCRIPT = "@unknowncmd 123\n@end\n"


# 1. 静态首页
def test_homepage(server):
    port, _ = server
    status, resp, raw = _get(port, "/")
    assert status == 200
    assert resp.getheader("Content-Type").startswith("text/html")
    text = raw.decode("utf-8")
    assert "MYONL 编辑器" in text
    assert "<textarea" in text


# 2. check 合法
def test_check_ok(server):
    port, _ = server
    status, raw = _post(port, "/api/check", {"text": VALID_SCRIPT})
    assert status == 200
    body = json.loads(raw)
    assert body["ok"] is True
    assert body["count"] >= 1


# 3. check 错误
def test_check_error(server):
    port, _ = server
    status, raw = _post(port, "/api/check", {"text": BAD_SCRIPT})
    assert status == 200
    body = json.loads(raw)
    assert body["ok"] is False
    assert body["line"] > 0
    assert isinstance(body["message"], str) and body["message"]
    assert body["file"]


# 3b. A1：check 错误同时给结构化字段（summary/detail/hint），旧字段保留
def test_check_error_结构化字段(server):
    port, _ = server
    status, raw = _post(port, "/api/check", {"text": BAD_SCRIPT})
    assert status == 200
    body = json.loads(raw)
    for key in ("summary", "detail", "hint", "line", "file", "message"):
        assert key in body, f"/api/check 错误缺少字段 {key}"
    assert body["summary"] == body["message"]
    assert body["detail"].startswith(body["file"])
    assert body["hint"]                 # A3：未知指令会给出「你是不是想写…」建议


# 3c. 工程目录不可写（只读盘/无权限）时：不能断连接，要给中文错误
def test_check_工程目录不可写时返回中文错误(server, monkeypatch):
    port, _ = server

    def _boom(*args, **kwargs):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(editor_mod.tempfile, "mkstemp", _boom)
    status, raw = _post(port, "/api/check", {"text": VALID_SCRIPT, "path": "script.gal"})
    assert status == 400
    body = json.loads(raw)
    assert body["ok"] is False
    assert "工程目录不可写" in body["message"]
    assert "权限" in body["message"]


# 4. preview 出图
def test_preview_png(server, monkeypatch):
    port, project = server
    status, raw = _post(port, "/api/preview", {"text": VALID_SCRIPT, "frames": 10})
    assert status == 200
    assert raw[:4] == b"\x89PNG"
    assert len(raw) > 0


# 5. preview 解析失败
def test_preview_error(server):
    port, _ = server
    status, raw = _post(port, "/api/preview", {"text": BAD_SCRIPT})
    assert status == 422
    body = json.loads(raw)
    assert "file" in body and "line" in body and "message" in body


# 5.1 预览内容哈希缓存：相同文本不重复渲染，不同文本重新渲染
def test_preview_content_hash_cache(server, monkeypatch):
    port, _ = server
    calls = []

    def fake_png(script_path, assets_root, max_frames=30, cancel=None):
        calls.append(script_path)
        return b"\x89PNG-cache"

    monkeypatch.setattr(editor_mod, "_preview_png", fake_png)
    editor_mod._preview_cache_clear()
    try:
        status, raw = _post(port, "/api/preview", {"text": VALID_SCRIPT, "frames": 10})
        assert status == 200 and raw == b"\x89PNG-cache" and len(calls) == 1
        status, raw = _post(port, "/api/preview", {"text": VALID_SCRIPT, "frames": 10})
        assert status == 200 and raw == b"\x89PNG-cache" and len(calls) == 1
        changed = VALID_SCRIPT + "@ 林晚 追加一句\n"
        status, raw = _post(port, "/api/preview", {"text": changed, "frames": 10})
        assert status == 200 and len(calls) == 2
    finally:
        editor_mod._preview_cache_clear()


# 5.2 预览取消标记：新序号到达后，旧序号在排队阶段直接放弃（204）
def test_preview_stale_request_skipped(server, monkeypatch):
    port, _ = server
    called = []

    def fake_png(script_path, assets_root, max_frames=30, cancel=None):
        called.append(script_path)
        return b"\x89PNG-stale"

    monkeypatch.setattr(editor_mod, "_preview_png", fake_png)
    editor_mod._preview_cache_clear()
    editor_mod._preview_note_seq("tab-test", 5)
    try:
        status, raw = _post(port, "/api/preview", {
            "text": VALID_SCRIPT, "frames": 10, "client": "tab-test", "seq": 4})
        assert status == 204 and raw == b""
        assert called == []
    finally:
        editor_mod._preview_cache_clear()


def test_preview_seq_state():
    editor_mod._preview_note_seq("tab-a", 1)
    assert not editor_mod._preview_is_stale("tab-a", 1)
    editor_mod._preview_note_seq("tab-a", 3)
    assert editor_mod._preview_is_stale("tab-a", 1)
    assert not editor_mod._preview_is_stale("tab-a", 3)
    # 非法序号不参与判断
    editor_mod._preview_note_seq("tab-a", "x")
    assert not editor_mod._preview_is_stale("tab-a", 4)


# 6. complete 补全
def test_complete(server):
    port, _ = server
    # @ → 含指令
    status, raw = _post(port, "/api/complete", {"line": "@"})
    assert status == 200
    items = json.loads(raw)["items"]
    assert "@label" in items
    # @ 林 → 含已定义角色名（全文扫描）
    status, raw = _post(port, "/api/complete", {
        "line": "@ 林",
        "text": "@character 林晚 #ffcccc\n@character 苏晨 #aaccff\n@ 林晚 你好",
    })
    items = json.loads(raw)["items"]
    assert "林晚" in items


# 7. run 异步
def test_run_async(server, monkeypatch, tmp_path):
    port, project = server
    calls = []

    class FakePopen:
        def __init__(self, *args, **kwargs):
            calls.append((args, kwargs))
        def poll(self):
            return 0
        def wait(self, timeout=None):
            return 0

    monkeypatch.setattr(editor_mod.subprocess, "Popen", FakePopen)
    status, raw = _post(port, "/api/run", {"text": VALID_SCRIPT})
    assert status == 200
    body = json.loads(raw)
    assert body["ok"] is True
    assert calls, "subprocess.Popen 应被调用"
    # 验证临时剧本文件曾被生成（检查项目目录内有 .gal 临时文件，run 后已清理，所以用 Popen 调用参数判断）
    args = calls[0][0]
    assert any(".gal" in str(a) for a in args[0])


# 7b. A3 运行链路：源码形态注入 PYTHONPATH（cwd=工程目录也能 import engine）
def test_demo_spawn_source_injects_pythonpath(tmp_path):
    cmd, env = editor_mod._demo_spawn(str(tmp_path / "tmp_x.gal"), str(tmp_path))
    assert cmd[1:3] == ["-m", "engine.demo"]
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(editor_mod.__file__)))
    assert env["PYTHONPATH"].split(os.pathsep)[0] == repo_root
    assert "--assets" in cmd


# 7c. A3 运行链路：冻结形态改用 editor.exe --demo-worker 重启自身
def test_demo_spawn_frozen_uses_worker(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    cmd, env = editor_mod._demo_spawn(str(tmp_path / "tmp_x.gal"), str(tmp_path))
    assert cmd[1] == "--demo-worker"
    assert cmd[0] == sys.executable
    assert "--assets" in cmd


# 7d. A3 运行链路：/api/run 把带 PYTHONPATH 的环境传给子进程
def test_run_async_passes_env(server, monkeypatch, tmp_path):
    port, project = server
    calls = []

    class FakePopen:
        def __init__(self, *args, **kwargs):
            calls.append((args, kwargs))
        def poll(self):
            return 0
        def wait(self, timeout=None):
            return 0

    monkeypatch.setattr(editor_mod.subprocess, "Popen", FakePopen)
    status, raw = _post(port, "/api/run", {"text": VALID_SCRIPT})
    assert status == 200
    env = calls[0][1].get("env")
    assert env and "PYTHONPATH" in env, "运行链路必须注入 PYTHONPATH，否则子进程找不到 engine 包"


# 7e. A1/A2 前端防线：候选联想与脏标记同步的关键钩子存在
def test_frontend_a1_a2_hooks():
    root = os.path.dirname(os.path.dirname(os.path.abspath(editor_mod.__file__)))
    html = open(os.path.join(root, "editor", "index.html"), encoding="utf-8").read()
    html += "\n" + open(os.path.join(root, "editor", "editor_main.js"), encoding="utf-8").read()
    pro = open(os.path.join(root, "editor", "editor_pro.js"), encoding="utf-8").read()
    # A1：检查器候选联想（datalist + 素材库缓存）
    assert "candidateField" in html and "datalist" in html and "charIdList" in html
    # A2：程序化改写派发 input（脏标记同步）、标题栏 ●、切换确认
    assert 'dispatchEvent(new Event("input"' in html
    assert "document.title" in pro and "确定切换吗" in pro


# 7f. D2 活动栏徽标：问题数 / 未保存 / 素材导入中
def test_frontend_d2_activity_badges():
    root = os.path.dirname(os.path.dirname(os.path.abspath(editor_mod.__file__)))
    html = open(os.path.join(root, "editor", "index.html"), encoding="utf-8").read()
    html += "\n" + open(os.path.join(root, "editor", "editor_main.js"), encoding="utf-8").read()
    pro = open(os.path.join(root, "editor", "editor_pro.js"), encoding="utf-8").read()
    css = open(os.path.join(root, "editor", "editor.css"), encoding="utf-8").read()
    for token in ("actProblemBadge", "actDirtyDot", "actImportSpin",
                  "__actSetDirty", "setActImporting"):
        assert token in html, f"index.html 缺 {token}"
    assert "__actSetDirty" in pro, "editor_pro.js 应把未保存状态推给活动栏"
    for token in (".act-badge", ".act-dot", ".act-spin"):
        assert token in css, f"editor.css 缺 {token}"


# 7g. D3 侧栏分区分组折叠：工程文件 / 章节大纲（chevron + 状态记忆）
def test_frontend_d3_sidebar_groups():
    root = os.path.dirname(os.path.dirname(os.path.abspath(editor_mod.__file__)))
    html = open(os.path.join(root, "editor", "index.html"), encoding="utf-8").read()
    html += "\n" + open(os.path.join(root, "editor", "editor_main.js"), encoding="utf-8").read()
    css = open(os.path.join(root, "editor", "editor.css"), encoding="utf-8").read()
    for token in ("fpTreeHead", "fpTreeChev", "fpOutlineHead", "fpOutlineChev",
                  "moyul_side_groups", "applySideGroup", "wireSideGroup"):
        assert token in html, f"index.html 缺 {token}"
    assert ".fp-chev" in css


# 7h. B2-UI：UI 设计区「字号 / 行距」控件 + GET 回落引擎默认
def test_ui_design_字号行距控件与读回(server):
    port, _ = server
    status, _resp, raw = _get(port, "/api/ui-design")
    assert status == 200
    body = json.loads(raw)
    assert body["ok"] is True
    assert body["font"]["body"] == 28            # 引擎默认正文字号
    assert body["line_height"]["body"] == 1.6    # 引擎默认正文行距
    root = os.path.dirname(os.path.dirname(os.path.abspath(editor_mod.__file__)))
    html = open(os.path.join(root, "editor", "index.html"), encoding="utf-8").read()
    html += "\n" + open(os.path.join(root, "editor", "editor_uidesign.js"), encoding="utf-8").read()
    for token in ("uidFontBody", "uidLineHeight", "line_height.body"):
        assert token in html, f"index.html 缺 {token}"


# 7i. B2-UI：POST 写回 font.body / line_height.body，非白名单字号键保留
def test_ui_design_字号行距写回保留其余(server):
    port, project = server
    cfg_path = os.path.join(project, "config.json")
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump({"ui": {"quickbar": {"enabled": True}}, "font": {"title": 72}},
                  f, ensure_ascii=False)
    status, raw = _post(port, "/api/ui-design",
                        {"font": {"body": 32}, "line_height": {"body": 1.8}})
    assert status == 200
    assert json.loads(raw)["ok"] is True
    with open(cfg_path, encoding="utf-8") as f:
        back = json.load(f)
    assert back["font"]["body"] == 32
    assert back["font"]["title"] == 72                       # 非白名单字号键保留
    assert back["line_height"]["body"] == 1.8
    assert back["ui"]["quickbar"]["enabled"] is True


# 7i-2. 1080p 预设：画布尺寸读写（canvas_size）
def test_ui_design_画布尺寸读写(server):
    port, project = server
    cfg_path = os.path.join(project, "config.json")
    status, _resp, raw = _get(port, "/api/ui-design")
    assert status == 200
    assert json.loads(raw)["canvas"]["size"] == [1280, 720]

    status, raw = _post(port, "/api/ui-design", {"canvas": {"size": [1920, 1080]}})
    assert status == 200
    with open(cfg_path, encoding="utf-8") as f:
        assert json.load(f)["canvas_size"] == [1920, 1080]

    # 非法尺寸被忽略，不写坏配置
    status, _raw = _post(port, "/api/ui-design", {"canvas": {"size": [0, -5]}})
    assert status == 200
    with open(cfg_path, encoding="utf-8") as f:
        assert json.load(f)["canvas_size"] == [1920, 1080]


# 7i-2b. 2026-11-02 空配置也要返回完整默认值（否则前端 Number(null)=0 会把几何写坏）
def test_ui_design_空配置返回完整默认值(server):
    port, _ = server
    status, _resp, raw = _get(port, "/api/ui-design")
    body = json.loads(raw)
    assert status == 200
    assert body["choices"]["width"] == 420
    assert body["choices"]["row_height"] == 52
    assert body["quickbar"]["button_width"] == 64
    assert body["quickbar"]["position"] == "bottom"
    assert body["settings"]["row_width"] == 620
    assert body["settings"]["top"] == 210


# 7i-3. 2026-11-02 配色面板：theme 读写 / null 清覆盖 / 非白名单保留
def test_ui_design_配色读写与清空(server):
    port, project = server
    cfg_path = os.path.join(project, "config.json")
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump({"theme": {"primary": [1, 2, 3], "shadow": [9, 9, 9]}}, f)

    status, _resp, raw = _get(port, "/api/ui-design")
    body = json.loads(raw)
    assert status == 200
    assert body["theme"]["primary"] == [1, 2, 3]
    assert body["theme"]["accent"] == [255, 205, 130]        # 未覆盖 → 引擎兜底色
    assert body["theme_defaults"]["primary"] == [104, 156, 255]

    status, raw = _post(port, "/api/ui-design",
                        {"theme": {"primary": [200, 10, 20],
                                   "border": [300, 0, 0],
                                   "shadow": [1, 1, 1]}})
    assert status == 200
    with open(cfg_path, encoding="utf-8") as f:
        back = json.load(f)["theme"]
    assert back["primary"] == [200, 10, 20]
    assert "border" not in back                              # 非法 RGB 不写入
    assert back["shadow"] == [9, 9, 9]                       # 非白名单键保留

    status, _raw = _post(port, "/api/ui-design", {"theme": {"primary": None}})
    assert status == 200
    with open(cfg_path, encoding="utf-8") as f:
        assert "primary" not in json.load(f)["theme"]        # null = 清掉覆盖


def test_ui_design_配色面板前端接线():
    root = os.path.dirname(os.path.dirname(os.path.abspath(editor_mod.__file__)))
    html = open(os.path.join(root, "editor", "index.html"), encoding="utf-8").read()
    js = open(os.path.join(root, "editor", "editor_uidesign.js"), encoding="utf-8").read()
    css = open(os.path.join(root, "editor", "editor.css"), encoding="utf-8").read()
    assert "uidPanelTheme" in html
    for token in ("THEME_FIELDS", "rgbToHex", "hexToRgb", "theme_defaults",
                  "uidThemeDefaults", "uidThemeCleared", "uidBuildThemePanel",
                  "uidThemePrimary", "uidThemeSurface", "uidThemeSuccess",
                  'class="uid-color"'):
        assert token in js, f"editor_uidesign.js 缺 {token}"
    assert ".uid-color" in css


def test_窄窗口布局约束_P3_P4():
    """P3：工具条可换行、按钮不被压缩成竖排；P4：≤900px 活动栏横排、编辑区限高、预览不越界。"""
    root = os.path.dirname(os.path.dirname(os.path.abspath(editor_mod.__file__)))
    css = open(os.path.join(root, "editor", "editor.css"), encoding="utf-8").read()
    # P3：放不下就换行，并禁止按钮收缩成竖排文字
    assert ".editor-toolbar { flex-wrap: wrap;" in css
    assert ".editor-toolbar .tb-btn { flex: 0 0 auto; white-space: nowrap; }" in css
    # 三栏中间宽度（如 1024）：预览右缘不得越过视口
    assert "max-width: calc(100vw - 560px);" in css
    # P4：取最后一个 900px 媒体块（本次新增），活动栏横排、编辑区限高、预览占满
    block = css.rsplit("@media (max-width: 900px)", 1)[1]
    assert ".activity-bar {" in block and "flex-direction: row;" in block
    assert ".left-pane { flex: 0 0 auto; min-height: 380px; max-height: 70vh; }" in block
    assert ".right-pane { flex: 0 0 auto; min-height: 300px; max-width: none; }" in block
    # 窄窗口顶栏收紧，避免 800px 横向滚动
    assert ".menubar .mb-brand, .menubar .mb-search .mb-kbd { display: none; }" in block


def test_检查去重与请求取消_P9_P10_P11():
    """P9/P10/P11：防抖后只发一次 /api/check（JSON 视图复用结果）、新一轮取消旧请求、同文本不重复渲染预览。"""
    root = os.path.dirname(os.path.dirname(os.path.abspath(editor_mod.__file__)))
    js = open(os.path.join(root, "editor", "editor_main.js"), encoding="utf-8").read()
    # P10：检查/预览流程里只保留一处 /api/check 直连，不再为 JSON 视图重复 POST
    assert js.count('fetch("/api/check"') == 1
    assert "checkResp.instructions" in js, "JSON 视图应复用本次检查返回的 instructions"
    # P11：AbortController 取消上一轮请求，主动取消不当作失败；旧响应不再落地
    assert "new AbortController()" in js
    assert "checkAbort.abort()" in js
    assert "ctrl.signal.aborted" in js
    assert "signal: ctrl.signal" in js
    # P9：文本 + 光标行未变时跳过重复预览；「重载预览」可强制重渲染
    assert "lastPreviewKey" in js and "previewKey" in js
    assert "function scheduleCheck(force)" in js and "scheduleCheck(true)" in js


def test_非语法错误不使用undefined行号():
    """检查失败且没有行号（目录不可写/路径非法）时，前端给中文提示，不再显示“第 undefined 行”。"""
    root = os.path.dirname(os.path.dirname(os.path.abspath(editor_mod.__file__)))
    js = open(os.path.join(root, "editor", "editor_main.js"), encoding="utf-8").read()
    assert "if (!checkResp.line)" in js
    assert "检查失败：${msg}" in js
    assert "if (!line || line < 1) return;" in js


def test_editor_app_webview2检测不崩():
    """发行版无控制台：WebView2 缺失检测必须返回布尔，不能抛异常。"""
    from engine import editor_app

    assert isinstance(editor_app._webview2_installed(), bool)


def test_editor_app_缺少webview2时弹提示并退出(monkeypatch):
    """缺 WebView2 时不能静默失败：返回 3 并给出中文安装提示。"""
    from engine import editor_app

    # 隔离可选 GUI 壳 pywebview：源码测试环境未必安装它；本用例只验证
    # “系统缺 WebView2 Runtime”这条独立分支，避免被 import webview 失败提前短路成 return 1。
    import types
    monkeypatch.setitem(sys.modules, "webview", types.SimpleNamespace(
        create_window=lambda *a, **k: None,
        start=lambda *a, **k: None,
    ))

    messages = []
    monkeypatch.setattr(editor_app, "_webview2_installed", lambda: False)
    monkeypatch.setattr(editor_app, "_show_startup_error", messages.append)
    assert editor_app.main([]) == 3
    assert messages and "WebView2" in messages[0]


# 7j. E-3 素材库：搜索框 + 批量导入进度
def test_frontend_e3_asset_search_and_progress():
    root = os.path.dirname(os.path.dirname(os.path.abspath(editor_mod.__file__)))
    html = open(os.path.join(root, "editor", "index.html"), encoding="utf-8").read()
    html += "\n" + open(os.path.join(root, "editor", "editor_main.js"), encoding="utf-8").read()
    css = open(os.path.join(root, "editor", "editor.css"), encoding="utf-8").read()
    for token in ("assetSearch", "assetSearchClear", "setAssetQuery", "assetProgress",
                  "assetProgressFill", "setImportProgress", "finishImportProgress"):
        assert token in html, f"index.html 缺 {token}"
    for token in (".asset-search", ".asset-progress-bar", ".asset-progress-fill"):
        assert token in css, f"editor.css 缺 {token}"


# 8. script 读写
def test_script_rw(server):
    port, project = server
    content = "@character 林晚 #ffcccc\n@end\n"
    status, raw = _post(port, "/api/script", {"text": content})
    assert status == 200
    body = json.loads(raw)
    assert body["ok"] is True
    # 读回
    status, resp, raw = _get(port, "/api/script")
    assert status == 200
    body = json.loads(raw)
    assert body["text"] == content


# 8b. 保存中途失败：磁盘上必须还是上一版，不能被截成半截剧本
def test_保存失败保留上一版文件(tmp_path, monkeypatch):
    target = tmp_path / "script.gal"
    target.write_text(VALID_SCRIPT, encoding="utf-8")

    def _boom(*args, **kwargs):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(editor_mod.os, "replace", _boom)
    with pytest.raises(OSError):
        editor_mod._write_text_atomic(str(target), "@unknown 123\n")
    assert target.read_text(encoding="utf-8") == VALID_SCRIPT   # 原文件完好
    assert list(tmp_path.glob("*.tmp")) == []                   # 临时文件也不残留


def test_保存失败时接口返回中文错误且文件不变(server, monkeypatch):
    port, project = server
    path = os.path.join(project, "script.gal")
    before = VALID_SCRIPT + "# 上一版注释\n"
    with open(path, "w", encoding="utf-8") as f:   # 与要保存的内容不同，才能看出有无被截断
        f.write(before)

    def _boom(*args, **kwargs):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(editor_mod.os, "replace", _boom)
    status, raw = _post(port, "/api/file/save",
                        {"path": "script.gal", "content": VALID_SCRIPT})
    assert status == 500
    body = json.loads(raw)
    assert body["ok"] is False
    assert "保存失败" in body["message"] and "权限" in body["message"]
    assert open(path, encoding="utf-8").read() == before


# 9. 路径穿越拦截
def test_path_traversal(server, tmp_path):
    port, project = server
    evil = "../../evil.gal"
    status, raw = _post(port, "/api/script", {"text": "bad", "path": evil})
    assert status == 400
    body = json.loads(raw)
    assert body["ok"] is False
    # 确认不落盘
    evil_abs = tmp_path / ".." / ".." / "evil.gal"
    assert not evil_abs.exists()


def test_相对script路径按项目目录解析(tmp_path):
    """--project games/X --script script.gal：相对路径应相对项目目录，而不是进程 cwd。"""
    script = tmp_path / "script.gal"
    script.write_text(VALID_SCRIPT, encoding="utf-8")
    app = EditorApp(str(tmp_path), "script.gal")
    assert app.script_path == os.path.realpath(script)
    # 越界路径仍必须拒绝
    with pytest.raises(ValueError, match="必须在项目目录内"):
        EditorApp(str(tmp_path), "../outside.gal")


# 10. 端口占用
def test_port_in_use(tmp_path, monkeypatch, capsys):
    port = _free_port()
    app = EditorApp(str(tmp_path))
    # Windows 下 SO_REUSEADDR 允许多 socket 同绑，必须全局设为 False
    monkeypatch.setattr(ThreadingHTTPServer, "allow_reuse_address", False)
    srv = ThreadingHTTPServer(("127.0.0.1", port), app.make_handler())
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        rc = editor_mod.main(["--port", str(port), "--project", str(tmp_path)])
        assert rc == 1
        err = capsys.readouterr().err
        assert "端口" in err
    finally:
        srv.shutdown()
        srv.server_close()


# 11. 回归：核心文件零改动（由 git diff 在交付说明验证；此处断言编辑器可正常工作）
def test_editor_smoke(server):
    port, _ = server
    status, raw = _post(port, "/api/check", {"text": "@end\n"})
    assert status == 200
    assert json.loads(raw)["ok"] is True


# ==================== 卡片视图 ====================

# 卡片视图的规范样例剧本（4 空格缩进，与 dump_text 输出格式一致，可直接往返）
CARD_SCRIPT = """@character 林晚 #ffcccc
@character 苏晨 #aaccff
@label start
@bg classroom
@music bgm_night
@sfx door_open
@show 林晚 smile
@hide 苏晨
@[林晚] 你好。
@ 旁白一句话
@set 好感 += 1
@if 好感 >= 1:
    @[林晚] 关系不错
@choice:
    > 一起去吧 -> go
    > 改天吧: 好感 >= 2 -> finish
@label go
@jump finish
@end
@label finish
@end
"""


# /api/check 额外返回 instructions
def test_check_returns_instructions(server):
    port, _ = server
    status, raw = _post(port, "/api/check", {"text": CARD_SCRIPT})
    assert status == 200
    body = json.loads(raw)
    assert body["ok"] is True
    ins = body["instructions"]
    assert isinstance(ins, list) and len(ins) == body["count"]
    # 每条指令都带 op 与 line（卡片视图据此渲染与显示行号）
    assert all("op" in i for i in ins)
    assert all("line" in i for i in ins)
    ops = [i["op"] for i in ins]
    assert "character" in ops and "choice" in ops and "if" in ops


# 往返一致：text → check → render → 文本完全一致
def test_render_roundtrip(server):
    port, _ = server
    _, raw = _post(port, "/api/check", {"text": CARD_SCRIPT})
    instructions = json.loads(raw)["instructions"]
    status, raw = _post(port, "/api/render", {"instructions": instructions})
    assert status == 200
    body = json.loads(raw)
    assert body["ok"] is True
    assert body["text"] == CARD_SCRIPT


# render 生成文本里不含 line/file 等传输字段
def test_render_strips_parse_fields(server):
    port, _ = server
    _, raw = _post(port, "/api/check", {"text": CARD_SCRIPT})
    status, raw = _post(port, "/api/render", {"instructions": json.loads(raw)["instructions"]})
    text = json.loads(raw)["text"]
    assert "line" not in text and "file" not in text
    # 也不应出现任何 JSON 残留（无花括号、无 "op": 键）
    assert "{" not in text and '"op"' not in text


# 空列表 → ok 且文本为空
def test_render_empty(server):
    port, _ = server
    status, raw = _post(port, "/api/render", {"instructions": []})
    assert status == 200
    body = json.loads(raw)
    assert body["ok"] is True
    assert body["text"] == ""


# 非法输入 → ok:false + 中文 message（不 5xx）
def test_render_invalid(server):
    port, _ = server
    # 非数组
    status, raw = _post(port, "/api/render", {"instructions": "not a list"})
    assert status == 200
    body = json.loads(raw)
    assert body["ok"] is False and "数组" in body["message"]
    # 缺 op
    status, raw = _post(port, "/api/render", {"instructions": [{"text": "没有类型"}]})
    assert status == 200
    body = json.loads(raw)
    assert body["ok"] is False and "op" in body["message"]
    # 元素不是对象
    status, raw = _post(port, "/api/render", {"instructions": ["字符串"]})
    assert status == 200
    assert json.loads(raw)["ok"] is False


# 二次往返稳定：render → check → render 结果不变（前端连续编辑的常见路径）
def test_render_stable_after_reparse(server):
    port, _ = server
    _, raw = _post(port, "/api/check", {"text": CARD_SCRIPT})
    _, raw = _post(port, "/api/render", {"instructions": json.loads(raw)["instructions"]})
    t1 = json.loads(raw)["text"]
    _, raw = _post(port, "/api/check", {"text": t1})
    _, raw = _post(port, "/api/render", {"instructions": json.loads(raw)["instructions"]})
    t2 = json.loads(raw)["text"]
    assert t1 == t2


# 嵌套结构往返：@if body 与 @choice 条件选项都不丢
def test_render_nested_structure(server):
    port, _ = server
    _, raw = _post(port, "/api/check", {"text": CARD_SCRIPT})
    ins = json.loads(raw)["instructions"]
    the_if = [i for i in ins if i["op"] == "if"][0]
    the_choice = [i for i in ins if i["op"] == "choice"][0]
    assert len(the_if["body"]) == 1
    assert len(the_choice["options"]) == 2
    assert the_choice["options"][1]["cond"] == {"var": "好感", "op": ">=", "value": 2}

    _, raw = _post(port, "/api/render", {"instructions": ins})
    text = json.loads(raw)["text"]
    assert "@if 好感 >= 1:" in text
    assert "    @[林晚] 关系不错" in text         # body 缩进 4 空格
    assert "> 改天吧: 好感 >= 2 -> finish" in text  # 条件选项保留

    # 再解析确认结构等价
    _, raw = _post(port, "/api/check", {"text": text})
    again = json.loads(raw)
    assert again["ok"] is True
    the_if2 = [i for i in again["instructions"] if i["op"] == "if"][0]
    assert len(the_if2["body"]) == 1


# ==================== P12 素材库 ====================

def _touch(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 16)


def _q(text: str) -> str:
    """URL 路径里的中文必须百分号编码（http.client 只接受 ASCII 路径）。"""
    from urllib.parse import quote
    return quote(text, safe="")


def _mkdir_assets(root):
    """造一个分类齐全的素材目录。"""
    from pathlib import Path
    r = Path(root)
    _touch(r / "images" / "classroom.png")
    _touch(r / "images" / "林晚_smile.png")
    _touch(r / "images" / "videos" / "雨夜_001.png")
    _touch(r / "images" / "videos" / "雨夜_002.png")
    _touch(r / "images" / "anims" / "林晚_smile_呼吸_001.png")
    (r / "audio").mkdir(parents=True, exist_ok=True)
    (r / "audio" / "bgm_night.ogg").write_bytes(b"OggS" + b"0" * 8)
    (r / "audio" / "林晚_你来了.wav").write_bytes(b"RIFF" + b"0" * 8)
    (r / "fonts").mkdir(parents=True, exist_ok=True)
    (r / "fonts" / "NotoSansCJK.ttf").write_bytes(b"ttf" + b"0" * 8)


# P12-1 素材清单：分类齐全；缺目录返回空列表不报错
def test_assets_list(server):
    port, root = server
    _mkdir_assets(root)
    status, _, raw = _get(port, "/api/assets")
    assert status == 200
    data = json.loads(raw)
    assert data["ok"] is True
    assets = data["assets"]
    assert assets["images"] == ["classroom", "林晚_smile"]
    assert assets["videos"] == ["雨夜"]
    assert assets["anims"] == ["林晚_smile_呼吸"]
    assert assets["audio"] == ["bgm_night", "林晚_你来了"]
    assert assets["fonts"] == ["NotoSansCJK"]

    # 空项目：所有分类都是空列表，不报错
    from pathlib import Path
    from engine.editor import _scan_assets
    assert _scan_assets(str(Path(root) / "empty")) == {
        "images": [], "videos": [], "anims": [], "audio": [], "fonts": []}


# P12-2 列表不含扩展名；videos 前缀按 _001 去编号
def test_assets_names_without_ext(server):
    port, root = server
    _mkdir_assets(root)
    _, _, raw = _get(port, "/api/assets")
    assets = json.loads(raw)["assets"]
    for cat in assets.values():
        for name in cat:
            assert "." not in name
    assert "雨夜" in assets["videos"] and "雨夜_001" not in assets["videos"]


# P12-3 导入成功：写入正确目录、返回路径、重名自动加后缀
def test_import_ok_and_rename(server):
    port, root = server
    import base64
    from pathlib import Path
    blob = b"\x89PNG\r\n\x1a\nimported"
    body = {"category": "images", "filename": "新背景.png",
            "data_b64": base64.b64encode(blob).decode()}
    status, raw = _post(port, "/api/import", body)
    assert status == 200
    resp = json.loads(raw)
    assert resp["ok"] is True
    assert resp["name"] == "新背景"
    assert resp["path"] == "images/新背景.png"
    assert (Path(root) / "images" / "新背景.png").read_bytes() == blob

    # 同名再传 → 自动加后缀
    status, raw = _post(port, "/api/import", body)
    resp = json.loads(raw)
    assert status == 200 and resp["ok"] is True
    assert resp["name"] == "新背景_1"
    assert resp["renamed_from"] == "新背景.png"
    assert (Path(root) / "images" / "新背景_1.png").is_file()

    # 音频进 audio/
    status, raw = _post(port, "/api/import", {
        "category": "audio", "filename": "bgm.ogg",
        "data_b64": base64.b64encode(b"OggS").decode()})
    assert json.loads(raw)["path"] == "audio/bgm.ogg"


# P12-4 导入安全：.. / 路径分隔符 / 可执行扩展名 → 中文报错，HTTP 200/400 不 500
@pytest.mark.parametrize("filename", [
    "../evil.png", "a/b.png", "a\\b.png", "virus.exe", "script.py", "noext",
])
def test_import_rejects_unsafe(server, filename):
    port, root = server
    import base64
    from pathlib import Path
    status, raw = _post(port, "/api/import", {
        "category": "images", "filename": filename,
        "data_b64": base64.b64encode(b"x").decode()})
    assert status != 500
    resp = json.loads(raw)
    assert resp["ok"] is False
    assert isinstance(resp["message"], str) and resp["message"]
    for bad in ("..", "/", "\\"):
        if bad in filename:
            assert "路径" in resp["message"] or "文件名" in resp["message"]
    # 什么都没落盘到项目外
    assert not (Path(root).parent / "evil.png").exists()


def test_import_rejects_bad_ext_and_empty(server):
    port, _ = server
    import base64
    b64 = base64.b64encode(b"x").decode()
    status, raw = _post(port, "/api/import", {
        "category": "images", "filename": "a.txt", "data_b64": b64})
    assert status == 400 and "扩展名" in json.loads(raw)["message"]
    status, raw = _post(port, "/api/import", {
        "category": "docs", "filename": "a.png", "data_b64": b64})
    assert status == 400 and "类别" in json.loads(raw)["message"]
    # 非法 base64
    status, raw = _post(port, "/api/import", {
        "category": "images", "filename": "a.png", "data_b64": "!!!not base64!!!"})
    assert status == 400 and "base64" in json.loads(raw)["message"]


# P12-5 素材读取：图片 image/*、音频 audio/*；缺失 404 中文
def test_asset_read(server):
    port, root = server
    _mkdir_assets(root)
    status, resp, raw = _get(port, "/api/asset/classroom")
    assert status == 200
    assert resp.getheader("Content-Type").startswith("image/")
    assert raw.startswith(b"\x89PNG")

    status, resp, raw = _get(port, "/api/asset/bgm_night")
    assert status == 200
    assert resp.getheader("Content-Type").startswith("audio/")

    # 视频/动画取首帧
    status, resp, _ = _get(port, "/api/asset/" + _q("雨夜"))
    assert status == 200 and resp.getheader("Content-Type").startswith("image/")

    # 显式类别形式
    status, resp, _ = _get(port, "/api/asset/audio/" + _q("林晚_你来了"))
    assert status == 200 and resp.getheader("Content-Type").startswith("audio/")

    status, _, raw = _get(port, "/api/asset/" + _q("不存在的"))
    assert status == 404
    assert "不存在" in json.loads(raw)["message"]


# P12-6 补全联动：@bg 含图片名、@voice 含音频名；原候选不回归
def test_complete_includes_assets(server):
    port, root = server
    _mkdir_assets(root)

    _, raw = _post(port, "/api/complete", {"line": "@bg ", "text": "@bg \n"})
    items = json.loads(raw)["items"]
    assert "classroom" in items and "林晚_smile" in items
    # 原有的前缀过滤行为不变：只出 @bg，不出其余指令
    assert "@bg" in items and "@character" not in items

    _, raw = _post(port, "/api/complete", {"line": "@voice ", "text": "@voice \n"})
    items = json.loads(raw)["items"]
    assert "林晚_你来了" in items and "bgm_night" in items

    _, raw = _post(port, "/api/complete", {"line": "@music ", "text": "@music \n"})
    assert "bgm_night" in json.loads(raw)["items"]

    # GET 形式（任务书 2.2 指定 GET /api/complete）
    status, _, raw = _get(port, "/api/complete?line=%40bg%20&text=%40bg%20")
    assert status == 200
    assert "classroom" in json.loads(raw)["items"]


def test_complete_show_expr_suffix(server):
    port, root = server
    _mkdir_assets(root)
    _, raw = _post(port, "/api/complete", {"line": "@show 林晚 ", "text": "@show 林晚 \n"})
    items = json.loads(raw)["items"]
    assert "smile" in items


# P12-7 回归：旧 API 未被素材路由破坏
def test_old_apis_not_regressed(server):
    port, _ = server
    status, raw = _post(port, "/api/check", {"text": VALID_SCRIPT})
    assert status == 200 and json.loads(raw)["ok"] is True
    _, raw = _post(port, "/api/render", {"instructions": [
        {"op": "bg", "image": "classroom"}, {"op": "end"}]})
    body = json.loads(raw)
    assert body["ok"] is True and "@bg classroom" in body["text"]
    status, _, _ = _get(port, "/")
    assert status == 200


# ==================== P20：导入增强 / 数据目录 / 配置可迁移 ====================

# P20-1 同名覆盖：overwrite=True 直接替换原文件（不再生成 _1）
def test_import_overwrite(server):
    import base64
    from pathlib import Path
    port, root = server
    first = {"category": "images", "filename": "同名背景.png",
             "data_b64": base64.b64encode(b"\x89PNG-A").decode()}
    status, raw = _post(port, "/api/import", first)
    assert status == 200 and json.loads(raw)["ok"] is True

    second = dict(first, data_b64=base64.b64encode(b"\x89PNG-B").decode(), overwrite=True)
    status, raw = _post(port, "/api/import", second)
    resp = json.loads(raw)
    assert status == 200 and resp["ok"] is True
    assert resp["overwritten"] is True and resp["path"] == "images/同名背景.png"
    assert (Path(root) / "images" / "同名背景.png").read_bytes() == b"\x89PNG-B"
    assert not (Path(root) / "images" / "同名背景_1.png").exists()


# P20-2 数据目录可自定义：扫描/导入/读取都走 /api/config 指定的目录
def test_custom_data_root(server, tmp_path):
    import base64
    from pathlib import Path
    port, _ = server
    data_dir = tmp_path.parent / (tmp_path.name + "_assets")
    (data_dir / "images").mkdir(parents=True)
    (data_dir / "images" / "外部背景.png").write_bytes(b"\x89PNG-external")

    status, raw = _post(port, "/api/config", {"data_root": str(data_dir)})
    cfg = json.loads(raw)
    assert status == 200 and cfg["ok"] is True
    assert cfg["custom_data_root"] is True
    assert Path(cfg["data_root"]) == data_dir

    _, _, raw = _get(port, "/api/assets")
    assert "外部背景" in json.loads(raw)["assets"]["images"]

    status, raw = _post(port, "/api/import", {
        "category": "images", "filename": "导入到数据目录.png",
        "data_b64": base64.b64encode(b"\x89PNG-new").decode()})
    assert status == 200 and json.loads(raw)["ok"] is True
    assert (data_dir / "images" / "导入到数据目录.png").is_file()

    # 空串 = 恢复默认（随工程）
    _, raw = _post(port, "/api/config", {"data_root": ""})
    assert json.loads(raw)["custom_data_root"] is False


# P20-3 配置跟随工程：.editor_config.json 落盘 + 整体移动文件夹后仍生效
def test_editor_config_follows_project(server, tmp_path, monkeypatch):
    import shutil
    from pathlib import Path
    port, root = server
    status, raw = _post(port, "/api/config", {"auto_insert": False})
    assert status == 200 and json.loads(raw)["auto_insert"] is False

    cfg_path = Path(root) / ".editor_config.json"
    assert cfg_path.is_file()
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert cfg["last_project"] == "."  # 相对路径：移动工程不失效
    assert cfg["data_root"] is None
    assert cfg["auto_insert"] is False

    moved = tmp_path.parent / (tmp_path.name + "_moved")
    monkeypatch.chdir(tmp_path.parent)  # Windows：不能移动进程当前目录
    shutil.move(root, moved)
    app = EditorApp(str(moved))
    assert app.project_root == str(moved)
    assert app.data_root == str(moved)
    assert app.auto_insert is False


# P20-4 设置面板切换工程：/api/files、/api/script 指向新工程并写入新配置
def test_config_switch_project(server, tmp_path):
    from pathlib import Path
    port, _ = server
    other = tmp_path.parent / (tmp_path.name + "_other")
    other.mkdir()
    (other / "main.gal").write_text("@ 另一个工程\n@end\n", encoding="utf-8")

    status, raw = _post(port, "/api/config", {"project_root": str(other)})
    cfg = json.loads(raw)
    assert status == 200 and cfg["ok"] is True
    assert Path(cfg["project_root"]) == other

    _, _, raw = _get(port, "/api/files")
    assert json.loads(raw)["files"] == ["main.gal"]
    _, _, raw = _get(port, "/api/script")
    assert "另一个工程" in json.loads(raw)["text"]
    assert (other / ".editor_config.json").is_file()


# P20-5 editor_app：随机端口起服务，页面可访问（不启动 GUI 窗口）
def test_editor_app_start_server(tmp_path, monkeypatch):
    from engine.editor_app import start_server
    monkeypatch.chdir(tmp_path)
    (tmp_path / "script.gal").write_text("@ 桌面窗口\n@end\n", encoding="utf-8")
    srv, url = start_server(str(tmp_path))
    try:
        port = int(url.rsplit(":", 1)[1])
        assert 1024 < port < 65536
        status, resp, raw = _get(port, "/")
        assert status == 200
        assert "MYONL 编辑器" in raw.decode("utf-8")
    finally:
        srv.shutdown()
        srv.server_close()


# 迭代-01 任务5：CSS 抽离——index.html 只留 <link>，editor.css 独立可服务
def test_editor_css_抽离冒烟(server):
    port, _ = server
    status, _, raw = _get(port, "/")
    html = raw.decode("utf-8")
    assert status == 200
    assert '<link rel="stylesheet" href="/editor.css">' in html
    assert "<style>" not in html  # 内联样式块已全部外置

    status, resp, raw = _get(port, "/editor.css")
    assert status == 200
    assert "text/css" in resp.getheader("Content-Type")
    css = raw.decode("utf-8")
    assert ":root" in css and "--blue:" in css  # 颜色变量化
    assert "--r-md:" in css and "--sp-3:" in css  # 圆角/间距变量化


# Trae 化批 3：T1 动作条三态 / T3 欢迎卡 / T4 预览锚点 / T5 查找替换 / T6 当前行 / T7 右栏标签 / T8 状态栏
def test_trae_phase3_frontend_structure():
    root = os.path.dirname(os.path.dirname(os.path.abspath(editor_mod.__file__)))
    html = open(os.path.join(root, "editor", "index.html"), encoding="utf-8").read()
    html += "\n" + open(os.path.join(root, "editor", "editor_main.js"), encoding="utf-8").read()
    pro = open(os.path.join(root, "editor", "editor_pro.js"), encoding="utf-8").read()
    css = open(os.path.join(root, "editor", "editor.css"), encoding="utf-8").read()
    # T5：替换需要走主脚本撤销栈
    assert "setSourceValue(v, a, b)" in html
    # T1/T3/T4：动作条三态、一次性欢迎卡（沿用 obCard）、预览锚定 @label start
    for token in ("__proToolbarSync", "__statusSaveSync", "打包中", "gal_welcome_done",
                  "打开教程工程", "开始写剧本",
                  "previewAnchorChip", "buildAnchoredText", "/api/scene"):
        assert token in pro, f"editor_pro.js 缺 {token}"
    assert "if (obShouldShow()) obStart();" not in html   # 首启不再弹旧设置引导
    # T5/T6/T7/T8：查找替换、当前行、右栏标签、状态栏保存分段
    for token in ("findInput", "find-hit", "findReplaceAll",
                  "lineHighlight", "rightTabs", "gal_right_tab", "sbSave"):
        assert token in pro, f"editor_pro.js 缺 {token}"
    for token in (".find-box", ".find-layer", ".cur-line", ".right-tabs",
                  ".tb-btn:disabled", ".preview-anchor", ".sb-item.dirty"):
        assert token in css, f"editor.css 缺 {token}"


# T2：发行版 README 与源码 README 分离（包内不出现源码指令）
def test_release_readme_只讲双击即用():
    import importlib.util
    root = os.path.dirname(os.path.dirname(os.path.abspath(editor_mod.__file__)))
    spec = importlib.util.spec_from_file_location(
        "build_release_zip", os.path.join(root, "tools", "build_release_zip.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    text = mod._release_readme()
    for bad in ("pip install", "engine.demo", "build.bat", "py -3"):
        assert bad not in text, f"发行版 README 不应包含源码指令：{bad}"
    for need in ("editor.exe", "Ctrl+S", "运行", "打包发布", "WebView2"):
        assert need in text, f"发行版 README 缺关键步骤：{need}"
    source_readme = open(os.path.join(root, "README.md"), encoding="utf-8").read()
    assert "## 源码开发" in source_readme and "发行包" in source_readme

