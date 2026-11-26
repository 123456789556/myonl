"""P272：用户截图点名的三处「处理不好」。

1. 顶栏缩放 − ＋ □：没有容器，跟左右两组站一起像掉在缝里；「□」谁也看不懂 → 统一容器 + 文字「全局」
2. 预览角上 ×：右边界被 22px 拖拽把手占着，压上去点不动、往内挪又悬空 → 移到预览左上角
3. 长幕名：换两行只剩「说出口」在第二行，看着像排错 → 单行省略，行高仍 20（台词卡还在 175）
4. 顺带：把手可见短条原来垂直居中，48px 短线悬在预览块下面，像条断线 → 贴顶 12px
"""

from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "editor" / "editor.css").read_text(encoding="utf-8")
JS = (ROOT / "editor" / "mobile" / "ui_layout.js").read_text(encoding="utf-8")


def test_zoom_group_has_its_own_frame():
    # 三组同一个写法：有边框、圆角、内部按钮不溢出的「一格一组」
    assert ("#mGraphBar .m-gmodes, #mGraphBar .m-gori { display: flex; "
            "border: 1px solid var(--surface1); border-radius: 4px; overflow: hidden; }") in CSS


def test_fit_button_reads_as_words():
    # P275 把这三颗整个撤了：不再有图标/文字之争，缩放交给手势，回全局靠点两下
    assert 'aria-label="看全局"' not in JS
    assert '>□</button>' not in JS


def test_title_single_line_ellipsis():
    assert ("html.m-shell #scenePage .sf-scene b { font-size: 17px; line-height: 1.2; flex: 1 1 auto; "
            "min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }") in CSS


def test_grip_stub_hugs_the_top():
    # 原：top:12px; width:5px; height:48px 蓝胶囊；新：1px 竖线、高 44px、贴顶 12px，线挪到把手外侧离开舞台图
    assert 'top: 12px; width: 1px; height: 44px;' in CSS
    # 垂直居中的老写法必须消失，否则短条又悬在预览块下面
    assert 'top: 50%; width: 5px; height: 48px; margin-top: -24px;' not in CSS
