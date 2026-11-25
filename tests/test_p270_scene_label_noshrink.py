"""P270：幕名一长，横屏标题行里「场景」小标不许被 flex 挤成竖排两个字。

实测（Playwright，844×390 / 700×360，把幕名换成 18 字长名）：
    改前  label 25×16 → 19×32（两个字各占一行，横屏 844 与 700 都会）
    改后  label 25×16 不动，幕名自己换行（255×20 → 255×41），台词卡位置不被推走
"""

from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "editor" / "editor.css").read_text(encoding="utf-8")


def _block() -> str:
    start = CSS.index("/* 横屏（≥700 宽）剧本页")
    end = CSS.index("\n}\n", start) + 2
    return CSS[start:end]


def test_label_never_shrinks():
    b = _block()
    rule = "html.m-shell #scenePage .sf-scene .sf-label"
    assert rule in b
    start = b.index(rule)
    decl = b[start:b.index("}", start)]
    # 不缩 + 不换行 + 不继承全局 min-width:64px（那会把标题推远 39px）
    assert "flex: 0 0 auto" in decl
    assert "white-space: nowrap" in decl
    assert "min-width: 0" in decl


def test_title_takes_the_squeeze():
    b = _block()
    rule = "html.m-shell #scenePage .sf-scene b"
    start = b.index(rule)
    decl = b[start:b.index("}", start)]
    # 幕名可缩可涨、可换行：挤它，别挤小标
    assert "flex: 1 1 auto" in decl
    assert "min-width: 0" in decl


def test_global_label_min_width_still_default():
    # 其他页（角色 / 背景 / 音乐 等 sf-row）的 64px 对齐基线不许被这轮的横屏规则带跑
    assert ".sf-label { display: inline-block; min-width: 64px;" in CSS
