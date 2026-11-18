"""P110 契约：手机上做游戏不许再要求用户写 .gal 脚本。

背景（写在测试里，免得以后有人"优化"掉）：
    桌面端一直有完整的可视化场景编辑器（editor_scene.js），但窄屏时入口按钮是隐藏的，
    手机用户点进「剧本」tab 只会看到一屏 @character / @jump 文本 —— 这就是
    "让大家都能做游戏"过不去的真正原因，不是 UI 丑。
    修法不是再画一遍皮，而是：剧本页常驻一个「逐句编辑 / 源码」切换，
    默认进可视化；场景页在窄屏拆成「列表」和「单个场景」两页（一次只给一件事）。

这里只断言静态契约（不启浏览器）：谁把这些结构删了、或者让桌面端也被波及，测试就红。

:meta private:
"""

import re
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

ROOT = Path(__file__).resolve().parents[1]
MOBILE_JS = ROOT / "editor" / "editor_mobile.js"
CSS = ROOT / "editor" / "editor.css"
HTML = ROOT / "editor" / "index.html"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def test_script_has_sentence_mode_entry():
    """剧本页必须有一个常驻入口，能切到可视化编辑，而不是只给源码。"""
    js = _read(MOBILE_JS)
    assert "m-modebar" in js, "剧本页的「逐句编辑/源码」切换条被删了"
    assert "buildScriptModes" in js
    assert "逐句编辑" in js and "源码" in js
    # 默认必须是「逐句」高亮：不写代码的人一进来看到的就是可视化
    assert re.search(r'class="m-mode on" data-mode="sent"', js), "默认高亮的不是「逐句编辑」"
    # 点「逐句」要真的打开场景编辑器
    assert "__openSceneEditor" in js


def test_scene_page_switches_between_list_and_detail():
    """窄屏场景页必须能在「列表」和「单个场景」之间切，而不是硬塞成一栏。"""
    js = _read(MOBILE_JS)
    for needle in ("enterDetail", "exitDetail", "m-detail", "buildSceneMobile"):
        assert needle in js, f"缺 {needle}"
    # 列表点击要穿透到原来的 selectScene（捕获阶段监听、不阻断）
    assert 'closest("#sceneList .scene-item")' in js
    assert "setTimeout(enterDetail" in js
    # 详情页要有明确的返回控件
    assert "scn-back" in js and "场景列表" in js


def test_head_buttons_are_thinned_out():
    """顶栏原来 7 个按钮在 390 宽会被挤出屏幕，必须收进 ⋯。"""
    js = _read(MOBILE_JS)
    assert "scn-extra" in js, "顶栏按钮没有瘦身标记"
    assert "sceneAdd: 1" in js and "sceneSave: 1" in js and "sceneClose: 1" in js
    # ⋯ 弹层里要能把复制/删除/刷新递回去（不是自己重写一遍逻辑）
    for src in ("sceneCopy", "sceneDel", "sceneRefresh"):
        assert src in js, f"⋯ 弹层漏了 {src}"


def test_css_is_phone_only_and_narrow_only():
    """这些改造不许漏到桌面端：默认隐藏 + 全部包在窄屏媒体查询里。"""
    css = _read(CSS)
    assert re.search(r"^\.m-modebar\s*\{\s*display:\s*none;\s*\}", css, re.M), \
        "外层没有默认隐藏 .m-modebar，桌面端会冒出一条切换条"
    # 窄屏断点用同一组条件，避免和另外两处断点打架
    assert "(max-width: 860px), (max-height: 520px)" in css
    # 一栏两页的两条关键规则
    assert re.search(r"\.scene-page\.m-detail\s+\.scene-list\s*\{\s*display:\s*none", css)
    assert re.search(r"\.scene-page\.m-detail\s+\.scene-form\s*\{\s*display:\s*block", css)


def test_desktop_dropdown_cap_is_lifted_on_phone():
    """桌面给下拉框限了 440px（一行太宽不好读），窄屏必须解掉，否则平板右半边全空。"""
    css = _read(CSS)
    assert "max-width: none !important" in css.split("P110")[-1], \
        "窄屏没有解掉 440px 限制"


def test_entry_html_stays_under_budget():
    """上面所有逻辑都写进已有 JS，不许往 index.html 里堆。"""
    n = len(_read(HTML).splitlines())
    assert n < 600, f"editor/index.html 已 {n} 行（上限 <600）"
