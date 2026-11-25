"""P264：横屏把「预览」和「编辑」对调，预览可收起，左栏可拖宽。

用户原话：「横屏编辑和预览区换一下位置，预览区可关闭，左边区域收一些可以拖动宽度，自适应做好」。

钉住四件事，都是实测过的：
    1. 换位：预览在左（grid 第一列 34%），编辑在右吃剩下的宽度；`> *` 默认第 2 列，
       只有 `.sf-stage-wrap` 回第 1 列 —— 写反了就是 P263 的原样，等于没做；
    2. 左栏宽度只吃 `--m-rail`，CSS 里不许再写死 width:232px（否则拖动写得再对也不动）；
    3. 收起：`m-stage-off` 时第一列压到 34px、预览内部子元素全隐藏，编辑拿走其余宽度；
    4. 自适应的两条硬边界：左栏 150–320、整块编辑区至少 380；竖屏不许露出手柄与按钮
       （分栏只在 `(orientation: landscape) and (min-width: 700px)` 成立）。
"""

from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "editor" / "editor.css").read_text(encoding="utf-8")
LAYOUT = (ROOT / "editor" / "mobile" / "ui_layout.js").read_text(encoding="utf-8")


def _block() -> str:
    start = CSS.index("/* 横屏（≥700 宽）剧本页")
    end = CSS.index("\n}\n", start) + 2
    return CSS[start:end]


def test_preview_moved_left_editor_right():
    b = _block()
    # P268：列宽改吃 --m-prev（默认 34%），拖动见 test_p268_pane_widths
    assert "html.m-shell #scenePage.m-detail #sceneForm { grid-template-columns: var(--m-prev, 34%) minmax(0, 1fr) !important; }" in b
    assert "html.m-shell #scenePage #sceneForm > * { grid-column: 2; }" in b
    assert "html.m-shell #scenePage #sceneForm > .sf-stage-wrap { grid-column: 1; top: 0; }" in b   # P265：top 必须是 0
    # 底部的保存/删除按钮原来横跨两列，换位后仍要横跨，否则会被塞进 170px 的预览列
    assert "> .sf-actions { grid-column: 1 / -1; }" in b


def test_rail_width_only_from_var():
    b = _block()
    assert "width: var(--m-rail, 232px); flex: 0 0 var(--m-rail, 232px)" in b
    assert "width: 232px; flex: 0 0 232px" not in b


def test_preview_collapse_rules():
    b = _block()
    assert "html.m-shell.m-stage-off #scenePage.m-detail #sceneForm { grid-template-columns: 34px minmax(0, 1fr) !important; }" in b
    assert "html.m-shell.m-stage-off #scenePage .sf-stage-wrap > :not(.m-stage-btn)" in b
    assert "html.m-shell.m-stage-off .m-stage-btn" in b


def test_drag_geometry_and_persistence():
    # P268：加预览列后三样东西要一起存在，否则左栏拖宽会把正文挤没
    assert 'var RAIL = "myonl:off:railW:v1", STAGE = "myonl:off:stageOff:v1", PREV = "myonl:off:prevW:v1";' in LAYOUT
    assert 'id = "mRailGrip"' in LAYOUT
    assert "Math.min(Math.max(railPx(), 150), railMax())" in LAYOUT
    assert "Math.max(150, Math.min(320, window.innerWidth - 460))" in LAYOUT
    # 宽度都要落到本机：P268 起两条把手共用 setItem(key, cur())，key 是 RAIL / PREV 之一
    assert 'try { localStorage.setItem(key, String(cur())); } catch (err) {}' in LAYOUT
    assert 'try { localStorage.setItem(STAGE, stageOff() ? "0" : "1"); } catch (e) {}' in LAYOUT


def test_split_gate_hides_controls_outside_landscape():
    # 竖屏不许出手柄/按钮：分栏只在 ≥700 宽且横着时成立
    assert "var split = window.innerWidth >= 700 && window.innerWidth > window.innerHeight;" in LAYOUT
    assert 'if (g) g.style.display = split ? "" : "none";' in LAYOUT
    assert 'if (b) {' in LAYOUT and 'b.style.display = split ? "" : "none";' in LAYOUT


def test_preview_button_labels():
    # 收起后按钮变成竖排「预览」，点一下回来；展开时是一枚浅色的 ×
    assert 'b.textContent = stageOff() ? "\\u9884\\u89C8" : "\\u00D7";' in LAYOUT
    assert "展开画面预览" in LAYOUT and "收起画面预览" in LAYOUT
