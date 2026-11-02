# -*- coding: utf-8 -*-
"""tests/test_newbie.py：P16 新手教程验收（无头 dummy 模式）。

对应任务书 8 条验收：
  1. new 生成目录结构完整（script.gal + images 4 文件 + audio/ + fonts/）
  2. 模板剧本 parse 零报错，指令覆盖 ≥8 种
  3. 示例项目 Runtime 两条分支都能跑到 finished
  4. 非法/重名游戏名中文拒绝且不覆盖（CLI + 编辑器 /api/new 双入口同一实现）
  5. onboarding 状态机静态断言（localStorage 键 / 三步标题 / 跳过 / 重开按钮）
  6. games/newbie_demo/ 红字扫描零缺失（剧本引用素材全部存在）
  7. 删掉占位素材后 Runtime + Renderer 无头仍跑完（占位色块降级）
  8. CLI 旧功能回归（--check / --tojson / --fromjson）
"""
from __future__ import annotations

import http.client
import json
import os
import socket
import threading
from pathlib import Path

import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")   # 须在 import pygame 前
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

from engine import cli  # noqa: E402
from engine.editor import EditorApp, ThreadingHTTPServer, _scan_assets  # noqa: E402
from engine.newgame import TEMPLATE, create_game, validate_name  # noqa: E402
from engine.parser import parse_file, parse_text  # noqa: E402
from engine.renderer import Renderer  # noqa: E402
from engine.runtime import Runtime  # noqa: E402

pytestmark = [pytest.mark.ui, pytest.mark.integration]

ROOT = Path(__file__).resolve().parent.parent
DEMO_DIR = ROOT / "games" / "newbie_demo"


# ---------- 工具 ----------

def _run_to_end(script_path, choose_index=0, max_steps=200):
    """无头跑剧本到 finished；遇选项固定选第 choose_index 个可选项。返回最终快照。"""
    rt = Runtime()
    rt.load(str(script_path))
    for _ in range(max_steps):
        state = rt.snapshot()
        if state.get("finished"):
            return state
        pc = state.get("pending_choice")
        if pc:
            options = pc.get("options") or []
            # 优先选指定下标；不可用则退到第一个可选项
            picked = None
            if 0 <= choose_index < len(options) and options[choose_index].get("available"):
                picked = choose_index
            else:
                for i, o in enumerate(options):
                    if o.get("available"):
                        picked = i
                        break
            assert picked is not None, "所有选项均不可选，剧本卡死"
            rt.choose(picked)
        else:
            rt.step()
    raise AssertionError(f"超过 {max_steps} 步仍未 finished")


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture
def server(tmp_path, monkeypatch):
    """在随机端口起编辑器服务线程（仿 tests/test_editor.py），返回端口。"""
    monkeypatch.chdir(tmp_path)
    port = _free_port()
    app = EditorApp(str(tmp_path))
    srv = ThreadingHTTPServer(("127.0.0.1", port), app.make_handler())
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield port
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


# ---------- 验收 1：目录结构完整 ----------

def test_新建目录结构完整(tmp_path):
    root = create_game("结构测试", str(tmp_path))
    assert (root / "script.gal").is_file()
    assert (root / "audio").is_dir()
    assert (root / "fonts").is_dir()
    images = {p.name for p in (root / "images").iterdir() if p.is_file()}
    assert images == {"bg_教室.png", "bg_天台.png", "林晚_微笑.png", "林晚_生气.png"}
    # 尺寸符合任务书：背景 1280×720，立绘 512×1024
    assert pygame.image.load(str(root / "images" / "bg_教室.png")).get_size() == (1280, 720)
    assert pygame.image.load(str(root / "images" / "林晚_微笑.png")).get_size() == (512, 1024)
    # 剧本内容即静态模板
    assert (root / "script.gal").read_text(encoding="utf-8") == TEMPLATE


# ---------- 验收 2：模板语法通过、指令覆盖 ≥8 种 ----------

def test_模板语法与指令覆盖():
    instrs = parse_text(TEMPLATE, source="模板")
    ops = {i["op"] for i in instrs}
    expected = {"character", "bg", "show", "say", "choice", "label", "set", "if", "jump", "end"}
    assert expected <= ops, f"模板指令覆盖不足：缺 {expected - ops}"
    assert len(ops) >= 8


# ---------- 验收 3：示例项目两条分支跑通 ----------

def test_示例两分支跑通(tmp_path):
    root = create_game("分支测试", str(tmp_path))
    script = root / "script.gal"
    # 分支一：选「接下来去哪？」→ 走 set/if 教学段
    end1 = _run_to_end(script, choose_index=0)
    assert end1["finished"] is True
    assert end1["vars"].get("进度") == 1  # 经过了 @set 进度 += 1
    # 分支二：选「直接看结局吧」→ 直达结局
    end2 = _run_to_end(script, choose_index=1)
    assert end2["finished"] is True
    assert "进度" not in end2["vars"]  # 未经过变量教学段，证明真走了另一条分支


# ---------- 验收 4：非法/重名拒绝且不覆盖（双入口） ----------

@pytest.mark.parametrize("bad", ["", "   ", "带 空格", "带符号!", "a" * 21, "斜/杠", "点.名"])
def test_非法游戏名拒绝(bad):
    with pytest.raises(ValueError):
        validate_name(bad)


def test_重名不覆盖(tmp_path):
    root = create_game("重名测试", str(tmp_path))
    marker = root / "script.gal"
    marker.write_text("# 用户已修改\n", encoding="utf-8")
    with pytest.raises(ValueError, match="已存在"):
        create_game("重名测试", str(tmp_path))
    # 原内容未被覆盖
    assert marker.read_text(encoding="utf-8") == "# 用户已修改\n"


def test_cli_new(tmp_path, capsys):
    assert cli.main(["new", "命令行游戏", "--dir", str(tmp_path)]) == 0
    assert (tmp_path / "命令行游戏" / "script.gal").is_file()
    # 重名 → 退出码 1 + 中文报错
    assert cli.main(["new", "命令行游戏", "--dir", str(tmp_path)]) == 1
    assert "已存在" in capsys.readouterr().err
    # 非法名 → 退出码 1
    assert cli.main(["new", "坏 名字", "--dir", str(tmp_path)]) == 1


def test_api_new(server):
    port = server
    # 成功：200 + ok，目录落盘
    status, raw = _post(port, "/api/new", {"name": "接口游戏"})
    assert status == 200
    body = json.loads(raw)
    assert body["ok"] is True
    assert (Path(body["path"]) / "script.gal").is_file()
    # 重名：400 + 中文提示，不覆盖
    status, raw = _post(port, "/api/new", {"name": "接口游戏"})
    assert status == 400
    assert "已存在" in json.loads(raw)["message"]
    # 非法名：400
    status, raw = _post(port, "/api/new", {"name": "坏 名字"})
    assert status == 400
    assert json.loads(raw)["ok"] is False


# ---------- 验收 5：onboarding 状态机静态断言 ----------

def test_onboarding静态断言():
    html = (ROOT / "editor" / "index.html").read_text(encoding="utf-8")
    html += "\n" + (ROOT / "editor" / "editor_main.js").read_text(encoding="utf-8")
    # localStorage 键与三步标题
    assert "gal_onboarding_done" in html
    for title in ("这是你的创作台", "写第一行", "看效果 / 出包"):
        assert title in html
    # 可跳过、可重开、步骤标记
    assert "obSkip" in html          # 跳过按钮
    assert "btnGuide" in html        # 顶栏「新手引导」重开入口
    assert 'data-step="1"' in html   # 步骤状态载体
    assert "obNext" in html and "obPrev" in html  # 上一步/下一步


# ---------- 验收 6：newbie_demo 红字扫描零缺失 ----------

def _script_asset_refs(instrs):
    """从指令列表收集素材引用：{类别: {素材名}}（与 P12 红字扫描同一口径）。"""
    refs = {"images": set(), "videos": set(), "audio": set()}
    for i in instrs:
        op = i["op"]
        if op == "bg":
            refs["images"].add(i["image"])
        elif op in ("show", "cg"):
            refs["images"].add(f"{i['char']}_{i['expr']}" if op == "show" else i["name"])
        elif op == "video":
            refs["videos"].add(i["name"])
        elif op == "music":
            refs["audio"].add(i["track"])
        elif op in ("sfx", "voice"):
            refs["audio"].add(i["sound"])
    return refs


def test_newbie_demo素材零缺失():
    assert DEMO_DIR.is_dir(), "games/newbie_demo/ 未入库"
    instrs = parse_file(DEMO_DIR / "script.gal")
    assets = _scan_assets(str(DEMO_DIR))
    refs = _script_asset_refs(instrs)
    missing = {cat: sorted(names - set(assets[cat])) for cat, names in refs.items()}
    missing = {cat: m for cat, m in missing.items() if m}
    assert not missing, f"红字缺失素材：{missing}"


# ---------- 验收 7：删掉占位素材后仍跑完（降级不崩） ----------

def test_无素材降级跑完(tmp_path):
    root = create_game("降级测试", str(tmp_path))
    # 删掉全部占位素材与字体目录，只留剧本
    import shutil
    shutil.rmtree(root / "images")
    shutil.rmtree(root / "audio")
    shutil.rmtree(root / "fonts")
    ren = Renderer((1280, 720), str(root))
    try:
        rt = Runtime()
        rt.load(str(root / "script.gal"))
        for _ in range(200):
            state = rt.snapshot()
            ren.render(state)  # 缺素材走占位色块，不应抛异常
            if state.get("finished"):
                break
            pc = state.get("pending_choice")
            if pc:
                rt.choose(0)
            else:
                ren.reveal_all()
                rt.step()
        else:
            raise AssertionError("超过 200 步仍未 finished")
        assert rt.snapshot()["finished"] is True
    finally:
        ren.close()


# ---------- 验收 8：CLI 旧功能回归 ----------

def test_cli旧功能回归(tmp_path, capsys):
    script = tmp_path / "r.gal"
    script.write_text("@character 林晚 #ffcccc\n@ 林晚 你好\n@end\n", encoding="utf-8")
    # --check
    assert cli.main(["--check", str(script)]) == 0
    assert "语法检查通过" in capsys.readouterr().out
    # --tojson
    out_json = tmp_path / "r.json"
    assert cli.main(["--tojson", str(script), "-o", str(out_json)]) == 0
    assert out_json.is_file()
    # --fromjson 往返
    out_gal = tmp_path / "r2.gal"
    assert cli.main(["--fromjson", str(out_json), "-o", str(out_gal)]) == 0
    assert parse_file(out_gal)  # 还原文本可再解析
    # 语法错误 → 退出码 1
    bad = tmp_path / "bad.gal"
    bad.write_text("@unknowncmd 1\n", encoding="utf-8")
    assert cli.main(["--check", str(bad)]) == 1
