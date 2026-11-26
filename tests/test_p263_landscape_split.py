"""P263：横屏剧本页恢复「左栏场景树 + 右栏正文」。

为什么要有这条：
    手机端自 P190 起是「列表一屏 / 单个场景一屏」，横屏（844×390）也被当成窄屏，
    一屏只给一件事。可是横屏本来有 844 的宽度，最能用的正是左右并排：
    左边一直看得见自己写到第几幕，右边改词。实测分栏前正文只有 127px 高，
    台词卡被挤到屏幕外；分栏 + 去掉底部那份 76px 预留后是 203px。
    另外实现上有四个坑，每个都踩过一次，所以都在这里钉住：
      1. 页面底部 76px 预留是 ui-layout.css 的 id 级 !important，class 级覆盖不掉；
      2. 「变量与条件」原来排在第一屏，把台词卡挤下去 → 改 order 6；
      3. 分栏后右下角「查找」压住画面预览 → 横屏从「⋯ → 查找台词」进；
      4. 横屏详情里「＋新场景 / ⋯」原本被隐藏，分栏后左栏就是列表，必须放出来。
"""

from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "editor" / "editor.css").read_text(encoding="utf-8")
LAYOUT = (ROOT / "editor" / "mobile" / "ui_layout.js").read_text(encoding="utf-8")
MOBILE = (ROOT / "editor" / "mobile" / "editor_mobile.js").read_text(encoding="utf-8")
FIND = (ROOT / "editor" / "editor_find.js").read_text(encoding="utf-8")


def _block() -> str:
    start = CSS.index("/* 横屏（≥700 宽）剧本页")
    end = CSS.index("\n}\n", start) + 2
    return CSS[start:end]


def test_横屏分栏只在_700_宽以上():
    blk = _block()
    assert "@media (orientation: landscape) and (min-width: 700px)" in blk
    # 窄横屏不许分栏：360 高切两栏，正文只剩十几字宽
    assert "max-height: 620px" not in blk


def test_左栏就是场景列表且详情里也看得见():
    blk = _block()
    assert "flex-direction: row" in blk
    # P264 起宽度改吃 --m-rail（可拖），232 只是默认值
    assert "width: var(--m-rail, 232px)" in blk
    assert "html.m-shell .scene-page.m-detail .scene-list { display: block; }" in blk


def test_详情里放出新场景与更多():
    blk = _block()
    assert "#sceneAdd { display: inline-flex !important; }" in blk
    assert ".scn-more { display: inline-flex !important; }" in blk


def test_底部_76px_预留要真去掉():
    blk = _block()
    # ui-layout.css 那条是 id 级 !important，所以这里必须用 4 个 class 压过去
    assert "#scenePage.center-page.scene-page.open" in blk
    assert "padding-bottom: 0 !important" in blk
    # 先给 vh 兜底，再给 dvh/真机可见高
    assert "height: calc(100vh - 92px) !important" in blk
    assert "var(--m-vvh, 100dvh)" in blk


def test_变量条排在台词之后():
    assert "#mVarEntry { order: 6; }" in _block()


def test_查找入口改从更多菜单进():
    # P279：右下角查找浮钮（#mlFab）已整体撤除（DOM/CSS/死规则一并清掉），手机入口只走 ⋯ 弹层；
    # 原断言 "#mlFab:not(.x) { display: none !important; }" 随 editor.css 那条死规则一起删除。
    assert "mlFab" not in FIND, "editor_find.js 里不许再留浮钮节点/样式引用"
    assert "#mlFab" not in CSS, "editor.css 里不许再留 #mlFab 死规则"
    assert '["mlFind", "查找台词"]' in MOBILE
    assert "MYONLLintUI.open()" in MOBILE


def test_可见高跟随_visualViewport():
    assert 'DE.style.setProperty("--m-vvh"' in LAYOUT
    assert 'visualViewport.addEventListener("resize", apply)' in LAYOUT
    # 只在手机壳里算，桌面端不碰
    idx = LAYOUT.index('DE.style.setProperty("--m-vvh"')
    assert "if (!shell()) return;" in LAYOUT[:idx]
