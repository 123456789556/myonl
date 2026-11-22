# -*- coding: utf-8 -*-
"""P219：新建先给名字 / 手机端能点出变量与条件 / 桌面能换作品 / 指令数不算 @label。

用户这一轮的原话：
- 「新建项目的话，它不能直接就是一个未命名」
- 「手机端和电脑端…变量数值这个东西我们还是得做一下」
- 「电脑端换作品没有入口，这个不太好」
- 「它显示 1 句，可是里面一句台词都没有」

前三条是这一轮真做进去的，最后一条是把口径修对。每条都钉一个断言，防止回退。
"""
from __future__ import annotations

import pathlib
import re

import pytest

pytestmark = [pytest.mark.unit]

ROOT = pathlib.Path(__file__).resolve().parents[1]
OFF = (ROOT / "editor" / "gal_offline.js").read_text(encoding="utf-8")
HOME = (ROOT / "editor" / "mobile" / "editor_home.js").read_text(encoding="utf-8")
MOB = (ROOT / "editor" / "mobile" / "editor_mobile.js").read_text(encoding="utf-8")
LAYOUT = (ROOT / "editor" / "mobile" / "ui-layout.css").read_text(encoding="utf-8")
CSS = (ROOT / "editor" / "editor.css").read_text(encoding="utf-8")
SWITCH = (ROOT / "editor" / "editor_switch.js").read_text(encoding="utf-8")
SHELL = (ROOT / "editor" / "editor_shell.js").read_text(encoding="utf-8")
INDEX = (ROOT / "editor" / "index.html").read_text(encoding="utf-8")
EDPY = (ROOT / "engine" / "editor.py").read_text(encoding="utf-8")


def _code(text: str) -> str:
    """剥掉整行 // 注释：断言要认代码，不能认注释里说的那句话。"""
    return "\n".join(l for l in text.split("\n") if not l.strip().startswith("//"))


def test_新建先问名字再建():
    m = re.search(r"function newProject\(\)[\s\S]*?\n  \}", HOME)
    assert m, "找不到 newProject"
    body = _code(m.group(0))
    assert "dlgPrompt(" in body, "点新建必须先把名字问出来"
    assert "name === null" in body, "点取消就一条都不许建"
    # 旧写法：直接 POST 一个空名，首页立刻多一张「未命名 N」
    assert "'{\"name\":\"\"}'" not in body


def test_取消起名不建作品():
    # 取消那条分支必须在 fetch 之前 return，否则一次误点就多一部作品
    m = re.search(r"function newProject\(\)[\s\S]*?\n  \}", HOME)
    body = _code(m.group(0))
    cut = body.split("if (name === null)")[1]
    assert cut.index("return") < cut.index("fetch(")


def test_指令数不把label算成一句():
    m = re.search(r"function countIns\(text\)[^\n]*", OFF)
    assert m, "找不到 countIns"
    assert "@label" in m.group(0), "零台词作品卡片上原来写着「1 句」"
    # 电脑端同口径
    assert "not s.startswith(\"@label\")" in EDPY


def test_手机端有变量与条件的入口():
    assert "function openVarSheet()" in MOB
    assert "function doSet()" in MOB and "function doIf()" in MOB
    body = _code(MOB)
    assert '"@set " + name + " " + op + " " + val' in body
    assert '"@if " + name + " " + cmp + " " + val + ":",' in body
    assert '"    @jump " + target' in body, "条件块的 @jump 必须缩进，否则 parser 认不出在 @if 里面"


def test_变量入口挂在属性面板里而不是顶栏_COMMA_那颗只在列表态可见():
    body = _code(MOB)
    assert "function hookVarEntry()" in body
    assert 'form.appendChild(box)' in body
    # ⋯ 在详情态是 display:none（editor.css:2961），挂上去等于藏起来
    assert re.search(r"\.scene-page\.m-detail \.scn-more \{ display: none", CSS)
    assert 'scnPop.appendChild(varBtn)' not in body, "别往那颗看不见的 ⋯ 里塞"


def test_写入要走编辑器的主脚本以便撤销与自动保存():
    body = _code(MOB)
    m = re.search(r"function writeBlock\([\s\S]*?\n  \}", body)
    assert m
    seg = m.group(0)
    assert "setSourceValue" in seg, "绕过主脚本直接改 textarea 等于丢掉撤销栈"
    assert 'getElementById("btnSave")' in seg, "写完不落盘，刷新就没了"


def test_变量面板样式有自己的一格不靠全局button():
    assert ".m-varsheet {" in LAYOUT
    # editor.css:1377 的全局 button{height:28px} 咬过四次，这里必须自带高度
    assert ".m-var-do {" in LAYOUT and "height: 38px" in LAYOUT


def test_桌面有换作品入口():
    assert "window.__openProjectSwitch" in SWITCH
    assert "换作品" in SHELL
    assert "editor_switch.js" in INDEX, "脚本没挂进 index.html"
    assert '"/editor_switch.js"' in EDPY, "桌面后端有静态白名单，不加这条就是 404"


def test_换作品只传目录名():
    # 桌面 /api/project 只收 {folder}，传绝对路径会被「工程名不合法」挡回去
    body = _code(SWITCH)
    assert "JSON.stringify({ folder: abs })" in body
    assert "project_root: abs" not in body
