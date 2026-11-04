# -*- coding: utf-8 -*-
"""tests/test_editor_pro.py：P17 多文件工程编辑与可视化增强验收。

对应任务书 8 条验收：
  1. /api/files 递归列出全部 .gal（含子目录）
  2. /api/file/new 新建章节：白名单拒绝非法名、重名不覆盖、骨架含 @label、语法通过
  3. /api/file/save + /api/file/read 读写往返一致；realpath 越界读/写被拒
  4. 保存前语法校验：坏语法拒绝落盘并返回行号，文件保持原内容
  5. /api/include-target 解析 @include 目标（含跨目录相对路径）
  6. /api/labels 跨文件收集 @label（文件+行号）+ @jump 目标
  7. 场景时间线提取：bg/show/music/voice/choice 按时序、行号正确（含 include 过滤）
  8. 清理：make_handler 拆分（无 300+ 行函数）+ 6 处未使用导入已清
"""
from __future__ import annotations

import ast
import http.client
import inspect
import json
import os
import re
import socket
import stat
import threading
from pathlib import Path
from urllib.parse import quote

import pytest

from engine.editor import (EditorApp, ThreadingHTTPServer, _EditorHandler,
                           _parse_at_root, extract_timeline, scene_state_at)
from engine.parser import parse_file, parse_text

pytestmark = [pytest.mark.integration]

ROOT = Path(__file__).resolve().parent.parent


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture
def server(tmp_path, monkeypatch):
    """在随机端口起编辑器服务线程，返回 (port, project_root)。"""
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
    conn.request("GET", quote(path, safe="/?=&"))  # 路径含中文需 URL 编码
    resp = conn.getresponse()
    raw = resp.read()
    conn.close()
    return resp.status, raw


def _write(root, rel, text):
    p = Path(root) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


# ---------- 验收 1：文件树递归列出全部 .gal ----------

def test_文件树递归列出(server):
    port, root = server
    _write(root, "script.gal", "@end\n")
    _write(root, "章节/第一章.gal", "@label 第一章\n@end\n")
    _write(root, "章节/幕间/插曲.gal", "@label 插曲\n@end\n")
    _write(root, "说明.txt", "不是剧本\n")
    _write(root, "__pycache__/缓存.gal", "@end\n")
    _write(root, ".hidden/隐藏.gal", "@end\n")
    status, raw = _get(port, "/api/files")
    assert status == 200
    body = json.loads(raw)
    assert body["ok"] is True
    assert body["files"] == ["script.gal", "章节/幕间/插曲.gal", "章节/第一章.gal"]
    assert body["current"] == "script.gal"


# ---------- 验收 2：新建章节 ----------

def test_新建章节(server):
    port, root = server
    # 成功：骨架含 @label，落盘且语法通过
    status, raw = _post(port, "/api/file/new", {"name": "第一章"})
    assert status == 200
    body = json.loads(raw)
    assert body["ok"] is True and body["path"] == "第一章.gal"
    text = (Path(root) / "第一章.gal").read_text(encoding="utf-8")
    assert "@label 第一章" in text
    assert parse_file(Path(root) / "第一章.gal")  # 生成后语法通过
    # 带 .gal 后缀的名字也去重后缀
    status, raw = _post(port, "/api/file/new", {"name": "第二章.gal"})
    assert status == 200
    assert json.loads(raw)["path"] == "第二章.gal"
    # 重名 → 400 且不覆盖
    (Path(root) / "第一章.gal").write_text("# 已修改\n", encoding="utf-8")
    status, raw = _post(port, "/api/file/new", {"name": "第一章"})
    assert status == 400
    assert "已存在" in json.loads(raw)["message"]
    assert (Path(root) / "第一章.gal").read_text(encoding="utf-8") == "# 已修改\n"
    # 非法名 → 400 中文
    for bad in ["", "坏 名字", "带/斜杠", "带点.名", "符号!"]:
        status, raw = _post(port, "/api/file/new", {"name": bad})
        assert status == 400, bad
        assert json.loads(raw)["ok"] is False


# ---------- 验收 3：读写往返 + 越界拒绝 ----------

def test_文件读写往返与越界(server):
    port, root = server
    content = "@character 林晚 #ffcccc\n@label 开始\n@ 林晚 你好\n@end\n"
    _write(root, "a.gal", content)
    # 读
    status, raw = _get(port, "/api/file/read?path=a.gal")
    assert status == 200
    assert json.loads(raw)["text"] == content
    # 写（新内容）→ 读回完全一致
    new_content = "@label 改后\n@jump 改后\n@end\n"
    status, raw = _post(port, "/api/file/save", {"path": "a.gal", "content": new_content})
    assert status == 200
    assert json.loads(raw)["ok"] is True
    status, raw = _get(port, "/api/file/read?path=a.gal")
    assert json.loads(raw)["text"] == new_content
    # 越界读/写被拒（中文报错）
    status, raw = _get(port, "/api/file/read?path=../../evil.gal")
    assert status == 400
    status, raw = _post(port, "/api/file/save",
                        {"path": "../../evil.gal", "content": "@end\n"})
    assert status == 400
    assert "越界" in json.loads(raw)["message"]
    # 非 .gal 被拒
    status, raw = _post(port, "/api/file/save", {"path": "a.txt", "content": "x"})
    assert status == 400
    # 不存在的文件不能靠 save 创建（走 file/new）
    status, raw = _post(port, "/api/file/save", {"path": "不存在.gal", "content": "@end\n"})
    assert status == 404


def test_只读文件保存失败给中文可操作提示(server):
    """保存失败不能把 Errno/Permission denied 原文抛给用户，要说明原因与下一步动作。"""
    port, root = server
    _write(root, "ro.gal", "@end\n")
    target = Path(root) / "ro.gal"
    os.chmod(target, stat.S_IREAD)
    try:
        status, raw = _post(port, "/api/file/save",
                            {"path": "ro.gal", "content": "@end\n"})
    finally:
        os.chmod(target, stat.S_IWRITE)
    assert status == 500
    body = json.loads(raw)
    assert body["ok"] is False
    assert "写入权限" in body["message"] and "ro.gal" in body["message"]
    assert "Errno" not in body["message"] and "Permission denied" not in body["message"]


# ---------- 验收 4：保存前语法校验 ----------

def test_保存前语法校验(server):
    port, root = server
    good = "@label 开始\n@end\n"
    _write(root, "b.gal", good)
    status, raw = _post(port, "/api/file/save",
                        {"path": "b.gal", "content": "@unknowncmd 1\n@end\n"})
    assert status == 200
    body = json.loads(raw)
    assert body["ok"] is False
    assert body["line"] == 1 and body["message"]
    # 坏文件未落盘
    assert (Path(root) / "b.gal").read_text(encoding="utf-8") == good


# ---------- 验收 5：@include 跳转 ----------

def test_include目标解析(server):
    port, root = server
    _write(root, "script.gal", "@include 章节/第一章.gal\n@end\n")
    _write(root, "章节/第一章.gal", "@include 幕间.gal  # 相对当前文件\n@end\n")
    _write(root, "章节/幕间.gal", "@end\n")
    # 顶层 include
    status, raw = _get(port, "/api/include-target?path=script.gal&line=1")
    assert status == 200
    body = json.loads(raw)
    assert body["ok"] is True and body["target"] == "章节/第一章.gal" and body["exists"]
    # 跨目录：相对当前文件所在目录解析，且容忍行尾注释
    status, raw = _get(port, "/api/include-target?path=章节/第一章.gal&line=1")
    body = json.loads(raw)
    assert body["ok"] is True and body["target"] == "章节/幕间.gal" and body["exists"]
    # 非 include 行 → 400
    status, raw = _get(port, "/api/include-target?path=script.gal&line=2")
    assert status == 400
    assert "不是 @include" in json.loads(raw)["message"]
    # 行号越界 / 目标不存在 / 越出项目
    assert _get(port, "/api/include-target?path=script.gal&line=99")[0] == 400
    _write(root, "c.gal", "@include 没有的文件.gal\n")
    body = json.loads(_get(port, "/api/include-target?path=c.gal&line=1")[1])
    assert body["ok"] is True and body["exists"] is False
    _write(root, "d.gal", "@include ../../外面.gal\n")
    status, raw = _get(port, "/api/include-target?path=d.gal&line=1")
    assert status == 400
    assert "越出项目" in json.loads(raw)["message"]


# ---------- 验收 6：标签大纲 ----------

def test_标签大纲跨文件(server):
    port, root = server
    _write(root, "script.gal",
           "@label 开始\n@include 章节/第一章.gal\n@jump 教室\n@label 结局\n@end\n")
    _write(root, "章节/第一章.gal", "@label 教室\n@ 旁白\n@jump 结局\n@end\n")
    _write(root, "坏文件.gal", "@unknowncmd 1\n")  # 解析失败进 errors，不中断
    status, raw = _get(port, "/api/labels")
    assert status == 200
    body = json.loads(raw)
    assert body["ok"] is True
    labels = {(l["file"], l["name"]) for l in body["labels"]}
    assert ("script.gal", "开始") in labels
    assert ("script.gal", "结局") in labels
    assert ("章节/第一章.gal", "教室") in labels
    # include 展开不重复计数
    assert [(l["file"], l["name"]) for l in body["labels"]].count(("章节/第一章.gal", "教室")) == 1
    # 行号正确
    教室 = [l for l in body["labels"] if l["name"] == "教室"][0]
    assert 教室["line"] == 1
    # @jump 目标（前端据此标注目标所在文件）
    jumps = {(j["file"], j["target"]) for j in body["jumps"]}
    assert ("script.gal", "教室") in jumps and ("章节/第一章.gal", "结局") in jumps
    # 坏文件进 errors
    assert any(e["file"] == "坏文件.gal" for e in body["errors"])


# ---------- 验收 7：场景时间线 + 场景状态 ----------

TIMELINE_SCRIPT = """@character 林晚 #aaccff
@bg bg_教室
@music 夜曲
@show 林晚 微笑
@ 林晚 你好。
@voice 早安
@choice:
    > 去天台 -> 天台
    > 留下 -> 留下
@label 天台
@label 留下
@if 进度 >= 1:
    @bg bg_天台
@end
"""


def test_场景时间线提取():
    instrs = parse_text(TIMELINE_SCRIPT)
    nodes = extract_timeline(instrs)
    got = [(n["line"], n["lane"], n["kind"]) for n in nodes]
    assert got == [
        (2, "bg", "bg"),
        (3, "audio", "music"),
        (4, "sprite", "show"),
        (6, "audio", "voice"),
        (7, "choice", "choice"),
        (13, "bg", "bg"),       # @if 嵌套里的 @bg 也按文档顺序铺平
    ]
    # 立绘节点素材名 = 角色_表情（用于缩略图）
    show = [n for n in nodes if n["kind"] == "show"][0]
    assert show["name"] == "林晚_微笑"
    # 选项节点带选项文本
    choice = [n for n in nodes if n["kind"] == "choice"][0]
    assert choice["options"] == ["去天台", "留下"]


def test_时间线只算当前文件(tmp_path):
    _write(str(tmp_path), "章节/一章.gal", "@bg bg_别章\n@show 别人 怒\n@end\n")
    text = "@bg bg_本章\n@include 章节/一章.gal\n@show 主角 笑\n@end\n"
    instrs, top = _parse_at_root(text, str(tmp_path))
    nodes = extract_timeline(instrs, top)
    # include 展开的其它文件指令不进时间线（行号属于别的文件）
    assert [n["label"] for n in nodes] == ["bg_本章", "主角 笑"]


def test_场景状态随行推进():
    instrs = parse_text(TIMELINE_SCRIPT)
    s = scene_state_at(instrs, 2)
    assert s["bg"] == "bg_教室" and s["music"] is None and s["sprites"] == []
    s = scene_state_at(instrs, 4)
    assert s["bg"] == "bg_教室" and s["music"] == "夜曲"
    assert s["sprites"] == [{"char": "林晚", "expr": "微笑"}]
    s = scene_state_at(instrs, 14)  # 扫到文末：@if 里的 @bg 生效
    assert s["bg"] == "bg_天台"


def test_时间线与场景HTTP(server):
    port, root = server
    status, raw = _post(port, "/api/timeline", {"text": TIMELINE_SCRIPT})
    assert status == 200
    body = json.loads(raw)
    assert body["ok"] is True and len(body["nodes"]) == 6
    status, raw = _post(port, "/api/scene", {"text": TIMELINE_SCRIPT, "line": 4})
    body = json.loads(raw)
    assert body["ok"] is True and body["bg"] == "bg_教室" and body["music"] == "夜曲"
    # 语法错误 → ok:false + 行号
    status, raw = _post(port, "/api/timeline", {"text": "@unknowncmd 1\n"})
    body = json.loads(raw)
    assert body["ok"] is False and body["line"] == 1


# ---------- 验收 8：清理（make_handler 拆分 + 未使用导入） ----------

def _unused_imports(path: Path) -> list:
    """静态检查：import 进来的名字在文件中只出现一次（即 import 行本身）→ 未使用。"""
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names += [a.asname or a.name.split(".")[0] for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.module == "__future__":
                continue
            names += [a.asname or a.name for a in node.names]
    return [n for n in names if len(re.findall(rf"\b{re.escape(n)}\b", src)) <= 1]


def test_清理_make_handler拆分():
    src = inspect.getsource(EditorApp.make_handler)
    assert len(src.splitlines()) <= 30, "make_handler 应只做绑定，路由进 _ROUTES"
    # 全部 P17 路由已注册且每路由一个方法
    for route in [("GET", "/api/files"), ("GET", "/api/file/read"),
                  ("POST", "/api/file/save"), ("POST", "/api/file/new"),
                  ("GET", "/api/labels"), ("GET", "/api/include-target"),
                  ("POST", "/api/timeline"), ("POST", "/api/scene")]:
        assert route in _EditorHandler._ROUTES
        assert callable(getattr(_EditorHandler, _EditorHandler._ROUTES[route]))


def test_清理_未使用导入():
    for rel in ["engine/editor.py", "tests/test_editor.py",
                "tests/test_newbie.py", "tools/p13_screenshots.py"]:
        unused = _unused_imports(ROOT / rel)
        assert not unused, f"{rel} 有未使用导入：{unused}"


# ---------- 验收补充：check / timeline / scene 支持 path（@include 以编辑文件目录为基准） ----------

def test_check以编辑文件为include基准与错误定位(server):
    port, root = server
    _write(root, "script.gal", "@end\n")
    _write(root, "章节/第一章.gal", "@include 幕间.gal\n@end\n")
    _write(root, "章节/幕间.gal", "@end\n")
    # 正在编辑 章节/第一章.gal：@include 幕间.gal 相对 章节/ 解析 → 通过
    #（旧行为以项目根为基准会误报「文件不存在」）
    status, raw = _post(port, "/api/check",
                        {"text": "@include 幕间.gal\n@end\n", "path": "章节/第一章.gal"})
    assert status == 200
    body = json.loads(raw)
    assert body["ok"] is True
    # 不带 path → 旧行为：项目根基准，同文本误报文件不存在
    status, raw = _post(port, "/api/check", {"text": "@include 幕间.gal\n@end\n"})
    body = json.loads(raw)
    assert body["ok"] is False and "文件不存在" in body["message"]
    # 语法错误：file 字段定位到正在编辑的 rel，而不是临时文件路径
    status, raw = _post(port, "/api/check",
                        {"text": "@unknowncmd 1\n", "path": "章节/第一章.gal"})
    body = json.loads(raw)
    assert body["ok"] is False
    assert body["file"] == "章节/第一章.gal"
    assert body["line"] == 1
    assert root not in body["file"]


def test_时间线与场景支持path(server):
    port, root = server
    _write(root, "章节/一章.gal", "@bg bg_别章\n@end\n")
    # 正在编辑 script.gal：include 展开的他文件指令不进时间线
    text = "@bg bg_本章\n@include 章节/一章.gal\n@show 主角 笑\n@end\n"
    status, raw = _post(port, "/api/timeline", {"text": text, "path": "script.gal"})
    assert status == 200
    body = json.loads(raw)
    assert body["ok"] is True
    assert [n["label"] for n in body["nodes"]] == ["bg_本章", "主角 笑"]
    # 场景状态同样只算当前文件
    status, raw = _post(port, "/api/scene", {"text": text, "line": 3, "path": "script.gal"})
    body = json.loads(raw)
    assert body["ok"] is True and body["bg"] == "bg_本章"
    assert body["sprites"] == [{"char": "主角", "expr": "笑"}]
    # 正在编辑 章节/一章.gal 自身：其内容正常入时间线
    status, raw = _post(port, "/api/timeline",
                        {"text": "@bg bg_别章\n@end\n", "path": "章节/一章.gal"})
    body = json.loads(raw)
    assert body["ok"] is True
    assert [n["label"] for n in body["nodes"]] == ["bg_别章"]
