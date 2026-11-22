# -*- coding: utf-8 -*-
"""P216：宽屏自适应列数 + 二级页触控目标 44px。

尺寸底板（13 档 × 6 页，`_tools/尺寸底板/sizeboard.py`）实测出来的两批问题，
这里把修法固化成契约，防止下次改样式又退回去：

1. 首页列表在宽屏必须自适应多列，且内容列封顶 —— 否则 800 平板卡宽 768、
   1280 平板卡宽 1248，缩略图固定 88px，右边一千多像素全是空白。
   门槛必须 <= 600px：690×840 折叠屏展开竖屏在 700 门槛下漏成单列（实测卡宽 658）。
2. 二级页这些控件原来都不到 44px：
   .m-bin-act 76×40 / .m-profile-nm 36×28 / .m-profile-pen 26×26 /
   .m-seg button 58×37 / .m-swatches button 32×32（色板用伪元素撑点击区，视觉不变）。
"""
from __future__ import annotations

import pathlib
import re

import pytest

pytestmark = [pytest.mark.unit]

EDITOR = pathlib.Path(__file__).resolve().parents[1] / "editor"


def _css(rel: str) -> str:
    text = (EDITOR / rel).read_text(encoding="utf-8")
    return re.sub(r"\s+", "", re.sub(r"/\*.*?\*/", "", text, flags=re.S))


def test_宽屏自适应门槛不高于600():
    css = _css("mobile/home.css")
    m = re.search(r"@media\(min-width:(\d+)px\)and\(min-height:(\d+)px\)", css)
    assert m, "home.css 里找不到宽屏自适应的媒体查询"
    w, h = int(m.group(1)), int(m.group(2))
    assert w <= 600, "门槛 %dpx 太高，690 宽的折叠屏会漏成单列通屏长带" % w
    assert h >= 521, "必须排除矮横屏（那档已有左列表+右详情两栏，两套不能同时生效）"


def test_列数由宽度自己算而不是写死():
    css = _css("mobile/home.css")
    assert "repeat(auto-fill,minmax(" in css, (
        "列数必须用 auto-fill + minmax 自适应；写死「平板两列」以后出更宽的屏又要改代码"
    )
    assert "max-width:1080px" in css, "内容列要封顶，再宽的屏也不把卡片拉成通屏长带"


def test_分组标题与空态占整行():
    css = _css("mobile/home.css")
    assert "grid-column:1/-1" in css, "分组标题/空态挤进某一列就会错位"


def test_二级页触控目标补到44():
    css = _css("mobile/ui-layout.css")
    need = [
        "html.m-shell.m-bin-act{height:44px",
        "html.m-shell.m-profile-nm{min-height:44px",
        "html.m-shell.m-profile-pen{width:44px;height:44px",
        "html.m-shell.m-segbutton{min-height:44px",
    ]
    missing = [n for n in need if n not in css]
    assert not missing, "二级页触控目标覆盖被删了：%s" % missing


def test_色板扩点击区但不改视觉尺寸():
    """色板圆点视觉上仍是 32px，靠居中的 44×44 伪元素撑可点范围。

    直接把 button 改成 44×44 会让选中描边跟着变大、圆点之间挤在一起，
    那是改审美不是补可达性。伪元素属于按钮本体，参与命中测试。
    """
    css = _css("mobile/ui-layout.css")
    assert "html.m-shell.m-swatchesbutton{position:relative" in css
    m = re.search(r"html\.m-shell\.m-swatchesbutton::after\{[^}]*\}", css)
    assert m, "色板缺少撑点击区的伪元素"
    body = m.group(0)
    assert "width:44px" in body and "height:44px" in body
    assert "translate(-50%,-50%)" in body, "伪元素必须居中，否则点击区偏移"


def test_首页放大镜与垃圾箱入口44():
    css = _css("mobile/home.css")
    m = re.search(r"\.m-home-find\{[^}]*\}", css)
    assert m, "找不到 .m-home-find"
    assert "width:44px" in m.group(0) and "height:44px" in m.group(0), (
        "顶栏右上放大镜/垃圾箱原来 38×38，11 档触屏全部报目标不足"
    )