"""P277：舞台不在时，空轨道要收掉，左右贴住并留一条分界线。

用户原话：预览消失的话要自适应，左右两边向中间移动，一个分界。
以前只把舞台藏了，那条 34% 的列轨道还立在那儿，表单字段全被推到右边，
中间留一大块空白 —— 用户看到的是「一块坏掉的空」。
"""

import pytest

pytestmark = [pytest.mark.unit]

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIX = (ROOT / "editor" / "ui-fix.css").read_text(encoding="utf-8")
SCENE = (ROOT / "editor" / "editor_scene.js").read_text(encoding="utf-8")


def test_empty_track_collapses():
    assert "html.m-shell #scenePage.m-detail.m-no-stage #sceneForm { grid-template-columns: minmax(0, 1fr) !important; column-gap: 0 !important; }" in FIX
    # 舞台不在才算空；有背景图 / 视频 / 缺图提示 / 角色贴片，四种之一就不空
    assert '.sf-stage-bg, .sf-stage-video, .sf-stage-missing, .sf-sprite' in SCENE
    assert 'wr.classList.toggle("m-stage-empty", empty);' in SCENE
    assert 'sp.classList.toggle("m-no-stage", empty);' in SCENE


def test_divider_is_a_line_not_a_pill():
    # 分界：一条 1px 竖线；那根蓝胶囊（::after）在空态下不再画
    assert "html.m-shell #scenePage.m-no-stage .m-rail-grip { width: 13px; margin-left: -7px; border-left: 1px solid var(--surface1); }" in FIX
    assert "html.m-shell #scenePage.m-no-stage .m-rail-grip::after { display: none; }" in FIX
    # 把手还能拖：宽度没归零
    assert "width: 13px" in FIX


def test_old_placeholder_is_gone():
    assert 'content: "选背景后这里显示画面预览"' not in FIX
    assert "#scenePage .sf-stage-wrap.m-stage-empty { display: none; }" in FIX


MOB = (ROOT / "editor" / "mobile" / "editor_mobile.js").read_text(encoding="utf-8")
CSS = (ROOT / "editor" / "editor.css").read_text(encoding="utf-8")


def test_bar_keeps_only_navigation():
    # 顶栏只留「‹ 作品 / 作品名 / 流程·列表 / ⋯ / 试玩 / 菜单」；新建与保存交给 ⋯
    assert "var KEEP = { sceneClose: 1 };" in MOB
    assert 'html.m-shell .menubar #sceneAdd, html.m-shell .menubar #sceneSave { display: none !important; }' in CSS
    # 视图组靠右，跟作品名分开
    assert "html.m-shell .menubar #mGraphBar { margin-left: auto; margin-right: 8px; }" in CSS


def test_more_menu_carries_the_moved_actions():
    assert '["sceneAdd", "＋ 新建一幕"]' in MOB
    assert '["sceneSave", "保存这一幕"]' in MOB
    assert '["graphOri", "竖排 / 横排切换"]' in MOB
    # 点的是同一个节点，不另写一套逻辑
    assert 'var src = document.getElementById(it[0]); if (src) src.click();' in MOB
    # 竖排/横排 收进 ⋯ 后，条上不再画那一枚
    assert "html.m-shell #mGraphBar .m-gori { display: none; }" in CSS


def test_ori_label_refreshes_after_click():
    # 点完不刷标签的话，人只看到菜单关了、图翻了，不知道当前是竖还是横
    LAY = (ROOT / "editor" / "mobile" / "ui_layout.js").read_text(encoding="utf-8")
    assert 'graphBar(document.getElementById("scenePage"), graphOn());' in LAY
