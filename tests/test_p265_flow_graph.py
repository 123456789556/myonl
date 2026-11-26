"""P265：横屏左栏换成蓝图式流程图、预览顶边与正文齐平、场景页头并进顶栏。

用户原话：
    「不平行，我觉得吧，可以把行往上移动一些，就是说场景编辑再退两次回到作品界面」
    「游戏可是预览图串联起来的节点分布图」「可串联可并联可视化更高也就是类似虚幻蓝图」

钉住的事，都是 844×390 实测过的：
    1. 流程图默认开、记在 localStorage（=list 才是列表）；节点编号必须和场景列表对上
       （第一个 @label 之前的内容算「开场设置」一幕，一条 @label 都没有时叫「剧本」）；
    2. 三种线：@jump、选项、没写出边时顺序流到下一幕；跳回前面的线不参与分层；
       目标不存在画成红虚线小块；
    3. 预览 sticky 的 top 必须是 0（写多少就下沉多少，「不平行」就是这么来的）；
    4. 场景页头并进顶栏：只挪 DOM 位置、倒着放回原位，竖屏 / <700 宽不许触发。
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


def test_graph_is_default_and_remembered():
    assert 'var VIEW = "myonl:off:sceneView:v1"' in LAYOUT
    assert 'return localStorage.getItem(VIEW) !== "list";' in LAYOUT
    assert 'localStorage.setItem(VIEW, m)' in LAYOUT


def test_node_numbering_matches_scene_list():
    # 列表把第一个 @label 之前的内容算一幕，流程图不照做的话点第 2 个节点会进第 1 幕
    assert 'name: "开场设置"' in LAYOUT and "head: true" in LAYOUT
    assert 'ns[0].name = "\\u5267\\u672c";' in LAYOUT
    # 点节点走列表自己的点击链路，不另写一份选中逻辑
    assert 'd.className = "scene-item"; d.setAttribute("data-i", String(i));' in LAYOUT
    assert "h.appendChild(d); d.click(); d.remove();" in LAYOUT


def test_three_edge_kinds_and_back_edges():
    assert 'k: "jump"' in LAYOUT and 'k: "choice"' in LAYOUT and 'k: "flow"' in LAYOUT
    assert "back: b < a" in LAYOUT
    assert "if (e.to === a && !e.back) k = Math.max(k, rank[e.from] + 1);" in LAYOUT   # 往回的线不排层
    assert "ghost: true" in LAYOUT and "m-gn ghost" in LAYOUT
    # 写了 @end 的幕到此为止，不许再顺序流到下一幕（示范案例的两条分叉必须并排，不能被压成一条线）
    assert 'if (/^\\s*@end\\b/.test(t)) cur.end = true;' in LAYOUT
    assert "if (!n.end && !edges.some(function (e) { return e.from === a; }) && a < ns.length - 1) edges.push(" in LAYOUT


def test_zoom_floor_and_fit():
    assert "gT.z = Math.max(0.6, Math.min(1, W / gD.w, H / gD.h));" in LAYOUT
    # P275：顶栏那三颗「− ＋ 全局」撤掉了（用户：「加减的全局不好，完全可以用手放大」），
    # 缩放交给双指/滚轮，回全局改成空白处点两下（见 taps）。范围放宽到 0.4~3。
    assert "Math.min(3, Math.max(0.4, gT.z * f))" in LAYOUT
    assert 'data-z="fit"' not in LAYOUT, "顶栏不许再有「全局」按钮"
    assert "graphFit(); gTap = null;" in LAYOUT, "空白处点两下要能回全局"


def test_preview_top_flush_with_text():
    b = _block()
    assert "html.m-shell #scenePage #sceneForm > .sf-stage-wrap { grid-column: 1; top: 0; }" in b
    assert ".sf-stage-wrap { grid-column: 1; top: 12px; }" not in b
    # 「真实渲染预览」不许再压住预览的收起钮
    assert "html.m-shell #scenePage .sf-real-btn { top: 44px; }" in b


def test_scene_head_merged_into_topbar():
    b = _block()
    assert "function chromeSync(split)" in LAYOUT
    assert 'var on = !!(split && p && mb && more && p.classList.contains("open"));' in LAYOUT
    assert "for (var i = els.length - 1; i >= 0; i--)" in LAYOUT       # 倒着放回去
    assert "graphSync(); chromeSync(split);" in LAYOUT
    assert "chromeSync(false); DE.classList.remove(\"m-stage-off\", \"m-graph-on\");" in LAYOUT
    assert "html.m-shell.m-chrome-on #scenePage .cp-head { display: none !important; }" in b
    assert "html.m-shell .menubar > #sceneAdd, html.m-shell .menubar > #sceneSave {" in b
    assert "html.m-shell .menubar > .scn-more {" in b
    assert "html.m-shell.m-chrome-on #scenePage .scn-pop { top: 6px; }" in b


def test_graph_css_only_in_landscape_block():
    # 媒体块外必须先关掉，否则竖屏 / 桌面壳会多出一块流程图
    assert "#mGraph, #mGraphBar { display: none; }" in CSS
    assert "html.m-shell.m-graph-on #mGraph { position: absolute;" in _block()
    assert "touch-action: none;" in _block()
