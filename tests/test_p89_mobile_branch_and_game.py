# -*- coding: utf-8 -*-
"""P89：手机端播放器的分支语义 + 《研修日志》工程本身。

为什么有这两条：
- H5 的 VM 读 `ins["else"]`，parser 输出的是 `else_body`。只要哪个剧本用 @if/@else，
  手机端条件为假时就不进 else，直接顺着往下流，落进下一个 @label —— 结局整条走错。
  这个错在桌面上看不出来（桌面走另一套 runtime），只能靠断言盯着。
- 《研修日志》是发布用的示例作品：剧本要能解析、两个结局 label 都在、背景和立绘
  在 images 里都有 —— 缺一张，手机端就是黑屏。
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GAME = ROOT / "games" / "研修日志"
CORE_JS = ROOT / "web" / "myonl-core.js"

pytestmark = [pytest.mark.unit]

if not (GAME / "script.gal").is_file():
    pytest.skip("《研修日志》工程不在仓库里", allow_module_level=True)


def _ops():
    from engine.parser import parse_file

    return parse_file(GAME / "script.gal")


def test_手机端_if_读的是_else_body_不是_else():
    src = CORE_JS.read_text(encoding="utf-8")
    assert 'ins["else_body"]' in src, "VM 必须读 parser 的 else_body 字段"
    # 不允许再出现只读 ins["else"] 的老写法
    assert not re.search(r'const elseBody = ins\["else"\] \|\| \[\];', src)


def test_剧本能解析且两个结局都在():
    ops = _ops()
    labels = {o["name"] for o in ops if o.get("op") == "label"}
    assert "结局_卷帘门" in labels
    assert "结局_归档" in labels
    assert sum(1 for o in ops if o.get("op") == "say") >= 200, "短篇至少 200 句台词"


def test_剧本里用到的图都在工程里():
    ops = _ops()
    names = set()
    for o in ops:
        for key in ("image", "char", "name"):
            v = o.get(key)
            if isinstance(v, str) and v.startswith("bg_"):
                names.add(v)
        if o.get("op") == "show":
            names.add(f"{o['char']}_{o.get('expr') or '默认'}")
    images = {p.name for p in (GAME / "images").iterdir()}
    missing = [n for n in sorted(names) if (n + ".png") not in images and (n + ".jpg") not in images]
    assert not missing, f"剧本引用了不存在的图：{missing}"
