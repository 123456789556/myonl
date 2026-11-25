"""P269：横屏正文里「场景」小标并进幕名同一行，台词整行上移。

用户原话：「场景和 start 平行空间不是不会更大吗，下面内容往上移编辑版部分不是更大吗」。
意思是：把预览顶边跟「场景」对齐这件事本身不省地方；真正省地方的是把标题那块压矮。

钉住（844×390 实测，Playwright）：
    1. 横屏下 `.sf-scene` 是 flex + baseline，`.sf-label` 不再单独占一行（原来是 display:block + margin-bottom 6px）；
    2. 量：幕名块 44px → 20px，第一张台词卡 203 → 175（上移 28px），第二张卡在 321 露出来；
    3. 竖屏不许跟着变（还是两行，390×844 下幕名块 50px、第一张卡 542）；
    4. 「台词」那一行的下边距同步收到 4px，但按钮触控高不动。
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


def test_scene_label_inline_in_landscape():
    b = _block()
    # 整块变 baseline 对齐的一行；小标不再 block、不再留 6px 下边距
    assert "html.m-shell #scenePage .sf-scene { display: flex; align-items: baseline; gap: 8px; margin: 0 0 4px; padding-bottom: 0; }" in b
    assert "html.m-shell #scenePage .sf-scene .sf-label { display: inline-block; margin: 0; min-width: 0; font-size: 12.5px; }" in b
    # 幕名 17px / 1.2 行高：一行里还要看得清
    assert "html.m-shell #scenePage .sf-scene b { font-size: 17px; line-height: 1.2; }" in b
    # 旧的「两行」写法必须消失，否则等于没做
    assert "html.m-shell #scenePage .sf-scene { margin-bottom: 4px; padding-bottom: 2px; }" not in b


def test_say_row_margin_tightened():
    b = _block()
    assert "html.m-shell #scenePage .sf-sec { margin: 2px 0 4px; }" in b
    # 触控高不许动（按钮仍是 44 / 38）
    assert "@media (max-width: 779px) { html.m-shell.m-chrome-on .m-gzoom" in b


def test_portrait_rules_untouched():
    # 竖屏两行版式由 .scene-page 自己的规则给，横屏块不许盖到竖屏
    assert ".scene-page .sf-label { display: block; width: auto; margin-bottom: 6px; font-size: 12.5px; opacity: .7; }" in CSS
    b = _block()
    assert "html.m-shell #scenePage .sf-label { display: block" not in b
