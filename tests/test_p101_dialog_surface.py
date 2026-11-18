"""P101：对话框不再挡画面。

用户的原话是「完全的车挡画面确实也不好」。查下来不是透明度问题，是三件事：
1. 面板贴满左右、最底 0.97 —— 立绘的鞋和地板被彻底盖掉；
2. 面板高度按 `rows + 0.9` 预留 —— 单行台词也撑出三行高的板，底下全是空的；
3. 菜单/存档的遮罩 0.93 —— 打开菜单等于把画面关掉。

这三条都是纯 JS 行为，pytest 只能在源码层钉住"机制还在"（真跑靠 compare_dlg.py 四档实拍）。
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


def test_dialog_style_is_a_preference_with_three_states():
    """档位要落在 PREF 里（换作品也记住），并夹在 0~2。"""
    src = _src()
    assert "dlg: 1" in src, "PREF 里没有 dlg 默认值"
    assert "PREF.dlg = Math.max(0, Math.min(2, Math.trunc(v.dlg)))" in src
    style = _fn(src, "dlgStyle")
    assert "PREF.dlg" in style
    assert "Math.min(2" in style and "Math.max(0" in style


def test_panel_inset_only_in_non_classic_styles():
    """经典档贴边（0 内缩），另两档要左右内缩 —— 这是"不再贴满整行"的机制。"""
    src = _src()
    rect = _fn(src, "panelRect")
    assert "const inset = st === 0 ? 0" in rect
    assert "x: L.panelX + inset" in rect
    assert "w: L.panelW - inset * 2" in rect
    assert "style: st" in rect


def test_non_classic_styles_do_not_paint_a_rect():
    """1/2 两档不能画矩形 —— 半透明矩形的病在"边界"，亮处露边暗处消失。"""
    src = _src()
    panel = _fn(src, "drawPanel")
    body_after = panel[panel.index("if (rect.style >= 1)"):]
    assert "return rect" in body_after
    # 全宽渐变画到 viewW，而不是 roundRect 那块 w
    assert "ctx.fillRect(0, ty0, L.viewW, L.viewH - ty0)" in panel
    # 走到矩形那条路的只有经典档
    assert "roundRect(x, y, w, h, radius, panelFill(x, y, w, h))" in panel


def test_panel_height_follows_the_real_line_count():
    """面板高度按实际行数给，不再额外预留将近一整行。"""
    src = _src()
    target = _fn(src, "panelTargetH")
    assert ("const minRows = L.landscape ? Math.max(1, rows) : Math.max(1.4, rows);"
            in target)
    assert "L.landscape ? 1.1" not in target, "横屏别再写死 1.1 行"


def test_menu_veil_no_longer_shuts_the_picture_down():
    """菜单遮罩要从 0.93 死黑改成上浅下深的渐变。"""
    src = _src()
    menu = _fn(src, "drawMenu")
    assert "0.93" not in menu
    assert "rgba(4,6,12," in menu
    assert "createLinearGradient" in menu
    assert "0.28" in menu and "0.66" in menu


def test_body_text_stays_centered_inside_the_inset_panel():
    """内缩后正文按面板居中，否则左右留白一宽一窄（换行宽度仍是 L.textW）。"""
    src = _src()
    assert "function textLeft(" in src
    left = _fn(src, "textLeft")
    assert "L.textW" in left
    assert "const tx = textLeft(rect)" in src
    # 名字牌和正文用同一条左缘
    assert "const plateX = textLeft(rect)" in src


def test_settings_exposes_the_dialog_group_and_wires_it():
    """设置页要真能切，点了要真的改 PREF 并落盘。"""
    src = _src()
    assert '["对话框", "dlg", ["经典", "幕", "字幕"], [0, 1, 2], PREF.dlg]' in src
    assert 'key === "dlg"' in src
