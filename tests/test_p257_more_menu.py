# -*- coding: utf-8 -*-
"""P257：「⋯」从底部抽屉改成贴着按钮的小浮层（含六项处理方式）。

用户否掉上一版的原话：「不要出现灰色，这样很难看」「弹窗会出现在省略号附近，
不遮挡选中的项目得卡片」「不占全屏，只占少部分屏幕，而不是靠着屏幕边缘」。
所以这里断言的是一条条具体行为，不是"改过就行"：

1. 包里不再有 m-more-sheet 那套贴底抽屉 + 灰罩规则（CSS 里删净）。
2. 浮层自身有 min/max 宽、有投影、没有边框（不描灰线）。
3. 按压态只缩放、不铺灰底（静态画面里一个灰块也不能有）。
4. 六项处理方式齐全：重命名 / 导出这个作品 / 导入文件 / 复制一份 / 版本历史 / 删除。
5. 落点按「整张卡」算而不按那颗 ⋯ 算 —— 按按钮算会压住卡片下半截。
6. 点别处收起、再点同一颗收起、滚动与转屏收起。
7. 单作品导出不能顺手把导出整页也打开（旧委托见行里有"导出"就开整页）。
"""
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "editor" / "mobile" / "ui-layout.css").read_text(encoding="utf-8")
TRASH = (ROOT / "editor" / "mobile" / "editor_trash.js").read_text(encoding="utf-8")
EXPORT = (ROOT / "editor" / "mobile" / "editor_export.js").read_text(encoding="utf-8")
OFFLINE = (ROOT / "editor" / "gal_offline.js").read_text(encoding="utf-8")
HOME = (ROOT / "editor" / "mobile" / "editor_home.js").read_text(encoding="utf-8")


def test_抽屉与灰罩规则已删净():
    assert ".m-more-sheet" not in CSS
    assert ".m-sheet-mask" not in CSS


def test_浮层是实底带细边零投影():
    """P257 的「无边框、只做投影」被 P261 顶掉：全站去投影，改 1px 细描边分层。
    用户当时否的是灰罩和贴边（见 test_抽屉与灰罩规则已删净 / test_落点按整张卡算），
    不是一条 1px 的发丝线；投影没了又不描边，浮层就跟页面糊成一块（探针 25 条里的
    「浮层是实底」会当场红）。"""
    assert ".m-more-pop" in CSS
    assert "position: fixed" in CSS
    assert "min-width: 178px" in CSS
    assert "max-width: calc(100vw - 24px)" in CSS
    pop_block = CSS.split(".m-more-pop {", 1)[1].split("}", 1)[0]
    assert "border: 1px solid var(--surface0)" in pop_block
    assert "border-radius: 4px" in pop_block
    assert "box-shadow: none" in pop_block


def test_按压态不铺灰底():
    assert ".m-more-row2:active { transform: scale(" in CSS
    active = [ln for ln in CSS.splitlines() if "m-more-row2:active" in ln][0]
    assert "background" not in active


def test_六项处理方式齐全():
    for label in ["重命名", "导出这个作品", "导入文件", "复制一份", "版本历史", "删除"]:
        assert label in TRASH
    for hook in ["mMoreRen", "mMoreExp", "mMoreImp", "mMoreDup", "mMoreHist", "mMoreDel"]:
        assert hook in TRASH


def test_落点按整张卡算():
    # 直接从 ⋯ 按钮算会落到按钮下沿，正好压住卡片下半截（实测压 27px）
    assert 'anchor.closest(".m-home-card, .m-home-hero")' in TRASH
    assert "vh - r.bottom - M >= h + 8" in TRASH   # 先试卡片下方
    assert "r.top - h - 8" in TRASH                 # 放不下再翻到卡片上方


def test_点别处与转屏都收起():
    assert 'document.addEventListener("pointerdown", moreOff, true)' in TRASH
    assert 'window.addEventListener("scroll", closeMore' in TRASH
    assert 'window.addEventListener("resize", closeMore' in TRASH
    assert "moreAnchor === anchor" in TRASH   # 再点同一颗 = 收起


def test_单作品导出不再顺手开整页():
    # 旧委托：行文本里有"导出"就 MYONLExport.open()，会把整页导出盖在单作品导出上
    assert 'row.closest(".m-more-pop")' in OFFLINE


def test_三处对外能力还在():
    assert "exportOne" in EXPORT and "dupOne" in EXPORT
    assert "MYONLTrash.more(m.dataset.more, true, m)" in HOME
    assert "MYONLSnapshotsUI.open(folder)" in TRASH
