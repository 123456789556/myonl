# -*- coding: utf-8 -*-
"""P89：手机端播放器的分支语义（+ 示例作品自检，作品不在时只跳那一条）。

为什么有这条：
- H5 的 VM 读 `ins["else"]`，parser 输出的是 `else_body`。只要哪个剧本用 @if/@else，
  手机端条件为假时就不进 else，直接顺着往下流，落进下一个 @label —— 结局整条走错。
  这个错在桌面上看不出来（桌面走另一套 runtime），只能靠断言盯着。
- 这一条只看 `web/myonl-core.js` 源码，跟有没有示例作品无关，**任何时候都必须跑**。

关于示例作品：仓库里带的示例工程（`games/教程示例` 等）由 `test_p100` / `test_p104` 盯着。
原来这里还测过一部完整短篇，那部作品已移出仓库（版权归原作者，不放公开仓库），
所以依赖它的两条改成"有才跑、没有就跳"，别把播放器那条一起连坐掉。
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CORE_JS = ROOT / "web" / "myonl-core.js"

# 仓库外的可选工程：只做"能解析、素材不缺"的加练。名字用通用占位，
# 不写具体作品名——测试文件也是公开的，没必要把本地工程叫什么告诉陌生人。
OPT_GAME = ROOT / "games" / "示例工程"
HAS_OPT = (OPT_GAME / "script.gal").is_file()
needs_opt = pytest.mark.skipif(not HAS_OPT, reason="这个可选工程不在仓库里")

pytestmark = [pytest.mark.unit]


def test_手机端_if_读的是_else_body_不是_else():
    src = CORE_JS.read_text(encoding="utf-8")
    assert 'ins["else_body"]' in src, "VM 必须读 parser 的 else_body 字段"
    # 不允许再出现只读 ins["else"] 的老写法
    assert not re.search(r'const elseBody = ins\["else"\] \|\| \[\];', src)


@needs_opt
def test_剧本能解析且两个结局都在():
    from engine.parser import parse_file

    ops = parse_file(OPT_GAME / "script.gal")
    labels = {o["name"] for o in ops if o.get("op") == "label"}
    assert "结局_卷帘门" in labels
    assert "结局_归档" in labels
    assert sum(1 for o in ops if o.get("op") == "say") >= 200, "短篇至少 200 句台词"


@needs_opt
def test_剧本里用到的图都在工程里():
    from engine.parser import parse_file

    ops = parse_file(OPT_GAME / "script.gal")
    names = set()
    for o in ops:
        for key in ("image", "char", "name"):
            v = o.get(key)
            if isinstance(v, str) and v.startswith("bg_"):
                names.add(v)
        if o.get("op") == "show":
            names.add(f"{o['char']}_{o.get('expr') or '默认'}")
    images = {p.name for p in (OPT_GAME / "images").iterdir()}
    missing = [n for n in sorted(names) if (n + ".png") not in images and (n + ".jpg") not in images]
    assert not missing, f"剧本引用了不存在的图：{missing}"
