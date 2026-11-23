# -*- coding: utf-8 -*-
"""P255 画面方向是作品的限制（不是摆设）+ 导入搬回首页 + 头像相册。

用户这轮的原话：「导入导出我觉得不该在这个位置」「游戏画面改一下这个命名不好」
「头像图片可导入」「横屏竖屏应该是对游戏的限制」「多按键不能用」。

守五件事：
1. 作品能定方向，且这个值真的会被出片端读到（工程 config → meta → 播放器）；
2. 手机上这个开关点得动（离线内核要有这条路由，存在本机）；
3. 限定了方向的作品，成品里不再出现「画面方向」那一项（按不动的键不摆）；
4. 导入在首页页头，设置页不再有导入 / 导出两行；
5. 头像可以从相册挑（只有真的没有选图能力的旧包才挡）。
"""
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

ROOT = Path(__file__).resolve().parents[1]
OFF_IN = (ROOT / "editor" / "gal_offline.js").read_text(encoding="utf-8")
PLAYER = (ROOT / "web" / "myonl-player.js").read_text(encoding="utf-8")
WEBPACK = (ROOT / "engine" / "webpack.py").read_text(encoding="utf-8")
HOME = (ROOT / "editor" / "mobile" / "editor_home.js").read_text(encoding="utf-8")


def test_手机端存的画面方向会进成品():
    # 以前两处调用写死 "any"，设置页那一档等于存了个没人看的数
    assert 'orientation: "any"' not in OFF_IN.split("MYONLPack.buildPack")[1][:2000]
    assert OFF_IN.count("orientation: readOrient()") >= 2
    # 离线内核要有这条路由，否则手机上点「只竖屏」会弹「手机本地没有这个接口」
    assert 'ROUTES["GET /api/orientation"]' in OFF_IN
    assert 'ROUTES["POST /api/orientation"]' in OFF_IN
    assert "myonl:off:orientation:v1" in OFF_IN
    assert 'orientation: readOrient()' in OFF_IN  # /api/home 也回这个值


def test_出片端把方向写进又读回来():
    assert "_ORIENT_GUARD" in WEBPACK and "_ORIENT_JS" in WEBPACK
    # 两个渲染器（单文件 / 分目录）都要挂，少一个就有一种成品不受限
    assert WEBPACK.count("{_ORIENT_GUARD}") >= 2
    assert WEBPACK.count("{_ORIENT_JS}") >= 2
    assert 'name="myonl-orientation"' in WEBPACK


def test_限定了方向就不再摆那一项():
    assert "LOCK_ORIENT" in PLAYER
    # 菜单、设置、首启三问都要按锁定值收口
    assert "LOCK_ORIENT !== \"auto\"" in PLAYER
    assert "settingsGroups()" in PLAYER
    # 首启：锁定作品直接跳过「用哪种画面」那一问（step 从 0 起跳）
    assert 'step: LOCK_ORIENT !== "auto" ? 1 : 0' in PLAYER
    assert 'picks: {orient: LOCK_ORIENT !== "auto" ? LOCK_ORIENT : PREF.orient' in PLAYER


def test_导入在首页页头而不是设置页():
    assert 'id="mHomeImport"' in HOME
    assert 'id="mSetImport"' not in HOME
    assert 'id="mSetExport"' not in HOME
    # 页头三颗钮同排同尺寸
    assert HOME.count('m-home-find') >= 3


def test_头像能从相册挑():
    # 老判断是「安卓一律不给换」，把 v1.2.52 之后真能选图的包也一起挡了
    assert "__MYONL_CAN_PICK" in HOME
    assert 'inp.type = "file"' in HOME
    assert 'inp.accept = "image/*"' in HOME


def test_画面方向这名字不再叫游戏画面():
    assert '"游戏画面"' not in HOME
    for label in ("都行", "只竖屏", "只横屏"):
        assert label in HOME
