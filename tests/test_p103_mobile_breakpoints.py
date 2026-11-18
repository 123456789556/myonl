"""P103：安卓平板适配 —— 断点从「窄屏」扩成「窄屏 或 触屏设备」。

1280×800 的安卓平板横屏原来掉进桌面 IDE（左文件树 + 右检查器一屏铺满，手指点不动），
根因是编辑器只按宽度判断移动壳。这一轮把 CSS 的 21 处 860px 断点与 JS 的 mobileMQ
统一成同一条条件，并给平板正文收口行宽。
"""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "editor" / "editor.css").read_text(encoding="utf-8")
SHELL = (ROOT / "editor" / "editor_shell.js").read_text(encoding="utf-8")

pytestmark = [pytest.mark.unit]

BROAD = "(pointer: coarse) and (hover: none) and (max-width: 1400px)"


def test_every_860_breakpoint_carries_touch_clause():
    """一条都不能漏：漏一处，那一段样式在平板上就还是桌面版。"""
    for line in CSS.split("\n"):
        s = line.strip()
        if s.startswith("@media") and "max-width: 860px" in s:
            assert BROAD in s, f"断点没扩：{s}"


def test_breakpoint_count_is_stable():
    hits = [
        l for l in CSS.split("\n")
        if l.strip().startswith("@media") and BROAD in l
    ]
    assert len(hits) >= 21, len(hits)


def test_js_mobile_mq_matches_css():
    """JS 决定进不进移动壳，条件必须和 CSS 逐字相同，否则表里不一。"""
    assert BROAD in SHELL
    assert "window.matchMedia(MOBILE_MQ)" in SHELL


def test_topbar_title_fills_middle_gap():
    """390 宽顶栏原来中间空 300px，放当前文件名。桌面隐藏。"""
    assert ".m-title { display: none; }" in CSS
    assert ".menubar .m-title {" in CSS
    assert "m-title" in SHELL
    assert 'getElementById("filePath")' in SHELL


def test_tablet_body_line_measure():
    """平板一行 70+ 字符读不动，17px/29px 落到 37 个中文字。"""
    assert ".line-numbers { font-size: 12.5px; line-height: 29px; }" in CSS
    assert "@media (pointer: coarse) and (min-width: 900px)" in CSS


def test_landscape_menubar_clears_tab_column():
    """横屏左侧竖 tab 栏占 60px，顶栏原来没让位，左上「‹ 返回」被压在底下点不到。"""
    assert ".menubar { padding-left: 68px !important; }" in CSS
