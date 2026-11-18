"""P102：演出模式（竖 / 横 / 自动）提到菜单第一层 + 菜单九行不再出屏、不再透字。

用户在手机上切握法是很高的频操作，原来的路径是「菜单 → 设置 → 画面方向」三层；
现在菜单里一行「画面方向 · 竖屏/横屏/自动」，点一次就循环。

同时，菜单多一项后暴露了两个旧账：
- 竖屏九行按 2.3 倍行高算会顶到屏底，最下面那行被裁；
- 菜单面板 0.90 不透明，底下台词从幕里透出来，看着像没画完。
"""
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

ROOT = Path(__file__).resolve().parents[1]
PLAYER = ROOT / "web" / "myonl-player.js"


def _src() -> str:
    return PLAYER.read_text(encoding="utf-8")


def _fn(src: str, name: str) -> str:
    """抠出一个函数体（到下一个顶层 function 之前），避免全文件瞎撞。"""
    start = src.index(f"function {name}(")
    nxt = src.index("\n  function ", start + 1)
    return src[start:nxt]


def test_orient_is_one_tap_in_menu():
    """菜单列表里要有 orient 这一项，且标签带当前值。"""
    body = _fn(_src(), "drawMenuList")
    assert '["orient",' in body, "菜单里没有「画面方向」这一项"
    assert "orientLabel()" in body, "标签没带当前值，玩家不知道现在是什么档"


def test_orient_label_covers_three_states():
    src = _src()
    body = _fn(src, "orientLabel")
    assert "portrait" in body and "landscape" in body and "自动" in body
    assert "PREF.orient" in body


def test_acting_on_orient_cycles_and_persists():
    src = _src()
    act = _fn(src, "act")
    at = act.index('id === "orient"')
    tail = act[at:at + 400]
    assert "auto" in tail and "portrait" in tail and "landscape" in tail, "不是三档循环"
    assert "savePrefs()" in tail, "切了方向不存盘，下次打开又变回自动"
    assert "fit()" in tail, "没重算布局，画面不会真的转过去"


def test_menu_row_count_matches_nine_items():
    """菜单多一项，面板行数常量必须跟着走，否则面板算矮、列表溢出。"""
    src = _src()
    panel = _fn(src, "menuPanel")
    assert "(L.landscape ? 5 : 9)" in panel


def test_vertical_menu_row_is_compressed():
    """竖屏九行要压到 2.12 倍行高（2.3 会顶到屏底）。"""
    body = _fn(_src(), "menuRowH")
    assert "2.12" in body


def test_menu_panel_is_opaque_enough():
    """菜单是纯字列表，0.90 会让台词透上来；要单给菜单页更高不透明度。"""
    src = _src()
    body = _fn(src, "drawMenu")
    assert 'UI.view === "menu"' in body
    assert "rgba(13,16,24,.970)" in body


def test_debug_exposes_panel_geometry():
    """验收脚本要能量到面板有没有出屏，MYONL_DEBUG 得能读到 panel 几何。"""
    src = _src()
    assert "get panel()" in src
    seg = src[src.index("get panel()"):src.index("get panel()") + 400]
    assert "viewH" in seg and "menuPanel()" in seg
