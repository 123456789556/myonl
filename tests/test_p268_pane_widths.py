"""P268：横屏剧本页左栏与预览两处宽度可拖、双击复位、方向键微调、宽度记住。

用户原话：「场景和预览界面的宽也可以调整，并且可以调整预览窗口的大小比列」「坚决交互问题不要看起来好用起来不好」。

钉住的事（844×390 / 700×360 / 390×844 实测）：
    1. 预览列宽度只吃 --m-prev（默认 34%，拖过就记本机）；左栏仍是 --m-rail，下限 150、上限 320；
    2. 两条把手同一套行为：22px 命中区、touch-action:none（否则手机上被滚动/缩放抢走）、双击复位、方向键 ±8（Shift ±32）；
    3. 预览与正文的下限：预览 ≥170、正文 ≥290（844 下拖到上限，正文还剩 253px 台词卡）；
    4. 预览收起时预览把手跟着消失；竖屏两条把手都不许出现；
    5. 空态占位与真舞台同一个高宽比（--sf-pad），拖宽预览要让画面真的长起来。
"""

from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "editor" / "editor.css").read_text(encoding="utf-8")
FIX = (ROOT / "editor" / "ui-fix.css").read_text(encoding="utf-8")
LAYOUT = (ROOT / "editor" / "mobile" / "ui_layout.js").read_text(encoding="utf-8")


def test_two_widths_have_own_keys_and_bounds():
    assert 'var RAIL = "myonl:off:railW:v1", STAGE = "myonl:off:stageOff:v1", PREV = "myonl:off:prevW:v1";' in LAYOUT
    assert 'try { v = parseInt(localStorage.getItem(PREV) || "", 10) || 0; } catch (e) {}' in LAYOUT
    assert "return v > 0 ? v : Math.round(window.innerWidth * .34);" in LAYOUT
    assert "function railMax() { return Math.max(150, Math.min(320, window.innerWidth - 460)); }" in LAYOUT
    # 正文列下限 290（844 下还剩 253px 台词卡），预览自己 ≥170
    assert "var byBody = window.innerWidth - rail - 290;" in LAYOUT
    assert "return Math.max(170, Math.min(460, byBody, byHigh));" in LAYOUT
    assert 'DE.style.setProperty("--m-prev", Math.min(Math.max(prevPx(), 170), prevMax()) + "px");' in LAYOUT


def test_grips_share_one_behaviour():
    # 一条把手：拖、双击复位、方向键微调
    assert "function bindGrip(g, page, kind) {" in LAYOUT
    assert 'var rail = kind === "rail", prop = rail ? "--m-rail" : "--m-prev", key = rail ? RAIL : PREV;' in LAYOUT
    assert "g.addEventListener(\"dblclick\"," in LAYOUT
    assert "try { localStorage.removeItem(key); } catch (err) {}" in LAYOUT
    assert 'var d = e.key === "ArrowLeft" ? -1 : e.key === "ArrowRight" ? 1 : 0;' in LAYOUT
    assert "set(cur() + d * (e.shiftKey ? 32 : 8)); save();" in LAYOUT
    assert "g.setAttribute(\"aria-orientation\", \"vertical\");" in LAYOUT
    assert 'g.id = "mPrevGrip"; pg.className = "m-prev-grip";' in LAYOUT
    # 预览把手在预览收起 / 竖屏时跟着藏
    assert 'if (pg) pg.style.display = split && !stageOff() ? "" : "none";' in LAYOUT


def test_grip_is_grabbable_on_touch():
    b = CSS[CSS.index("  .m-rail-grip, .m-prev-grip {"):CSS.index("  html.m-shell.m-dragging")]
    assert "width: 22px" in b and "margin-left: -11px" in b
    assert "touch-action: none;" in b
    assert "top: 52px" in b
    assert "background: rgba(79, 140, 255, .35);" in b
    assert ".m-rail-grip.on::after, .m-prev-grip.on::after { height: 76px;" in b
    assert "html.m-shell.m-dragging, html.m-shell.m-dragging * { cursor: col-resize !important; user-select: none; }" in CSS


def test_columns_read_only_the_vars():
    assert "html.m-shell #scenePage.m-detail #sceneForm { grid-template-columns: var(--m-prev, 34%) minmax(0, 1fr) !important; }" in CSS
    assert "minmax(170px, 34%)" not in CSS
    assert ".m-prev-grip { left: calc(var(--m-rail, 232px) + var(--m-prev, 34%)); }" in CSS
    assert "html.m-shell.m-stage-off #scenePage.m-detail #sceneForm { grid-template-columns: 34px minmax(0, 1fr) !important; }" in CSS


def test_empty_stage_follows_ratio():
    assert "padding-bottom: var(--sf-pad, 36%); position: relative;" in FIX
    assert "height: 0; min-height: 0; padding-bottom: var(--sf-pad, 36%);" in FIX
