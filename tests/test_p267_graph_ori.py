"""P267：流程图能竖排也能横排、右下角小总览、正文行距收紧。

用户原话：「调整距离，并且蓝图可以竖着可以横着，在再来一个小的总览去寻找」「暂时只测试升级打包」。

钉住的事（844×390 实测）：
    1. 方向记在 localStorage（=h 才是横排），换方向重新看全局；
    2. 竖排：层往下、同层往右；横排：层往右、同层往下。画线按「层方向 / 横方向」两个轴说话，不许再写死 x/y；
    3. 小总览跟主图一起生成，图整个在栏里时不显示；手指落在总览上是导航，不是平移主图；
    4. 幕名到「台词」之间收紧；窄横屏（<780）缩放只留「□」。
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


def test_orientation_is_remembered_and_refits():
    assert 'ORI = "myonl:off:graphOri:v1", MW = 88, MH = 64;' in LAYOUT
    assert 'return localStorage.getItem(ORI) === "h";' in LAYOUT
    assert "if (o) { try { localStorage.setItem(ORI, o); } catch (err) {} gSig = \"\"; gCount = -1; renderGraph(); return; }" in LAYOUT
    assert 'data-o="v" aria-label="竖排">竖排</button><button type="button" data-o="h" aria-label="横排">横排</button>' in LAYOUT


def test_layout_and_edges_speak_in_two_axes():
    # 落点：竖排层往下 / 横排层往右
    assert "n.x = H ? major : minor + (NW - gw) / 2; n.y = H ? minor + (NH - gh) / 2 : major;" in LAYOUT
    assert "major = rank[a] * (step + LA)" in LAYOUT
    # 画线：四个取端口函数按方向换轴，不许再出现写死的 a.x + NW
    assert "function al(n) { return H ? n.x : n.y; }" in LAYOUT
    assert "function ac(n) { return H ? n.y : n.x; }" in LAYOUT
    assert "function pt(a, b) { return H ? a + \" \" + b : b + \" \" + a; }" in LAYOUT
    assert "var lx = H ? l1 : l2, ly = H ? l2 : l1;" in LAYOUT
    # 小总览里的 node 中心可以写 a.x + NW / 2（那是按主图坐标算缩略，不归这条管）
    main = LAYOUT[: LAYOUT.index("h.push('<svg id=\"mMini\"")]
    assert "a.x + NW" not in main


def test_minimap_built_with_graph_and_navigates():
    assert "h.push('<svg id=\"mMini\" viewBox=\"0 0 ' + MW + \" \" + MH" in LAYOUT
    assert '<rect id="mMiniV"/></svg>' in LAYOUT
    # 图整个在栏里不显示；取景框跟着视图走
    assert 'mm.style.display = (gD.w * gT.z > W + 1 || gD.h * gT.z > H + 1) ? "" : "none";' in LAYOUT
    assert "function miniNav(e)" in LAYOUT
    assert "if (p[0] < -1e5) { miniNav(e); return; }" in LAYOUT
    assert 'var onMini = !!(e.target.closest && e.target.closest("#mMini"));' in LAYOUT
    b = _block()
    assert "#mGraph #mMini { position: absolute; right: 6px; bottom: 6px; width: 88px; height: 64px;" in b
    assert "#mGraph #mMini #mMiniV {" in b


def test_spacing_rules():
    b = _block()
    # 正文行距：幕名与「台词」之间收紧
    assert "html.m-shell #scenePage .sf-scene { margin-bottom: 4px; padding-bottom: 2px; }" in b
    assert "html.m-shell #scenePage .sf-sec { margin: 6px 0 4px; }" in b
    # 窄横屏顶栏放不下：缩放只留「□」
    assert "html.m-shell.m-chrome-on .m-gzoom [data-z=\"-\"], html.m-shell.m-chrome-on .m-gzoom [data-z=\"+\"] { display: none; }" in b
