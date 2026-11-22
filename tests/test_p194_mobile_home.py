# -*- coding: utf-8 -*-
"""P194 手机端首页收口，P203 改成四格 + 两版教程。

用户这轮的原话：「下面那栏明明可以加入」「专门放教程」「这个部分可以删掉」
「比例不对」「引擎拆分要做的移动端和 window 两个文件夹」。

守五件事：
1. 底栏四格（作品 / 教程 / 素材库 / 设置），每格都是真动作，没有哑按钮；
2. 首页正文里那两块重复的东西收干净：新手教程引导卡、页头设置按钮、
   「开始新的」两格；P203 再把底栏中间那颗「新建」也撤掉（首页已有虚线卡）；
3. 教程分两版：读一遍（一篇连续文字）/ 动手建（一份可删的最小示例）；
4. 横屏详情第一行是正方形缩略图 + 名字 + 主操作，不再是铺满整列的扁封条；
5. 手机端专属前端住 editor/mobile/，路由要能从 mobile/ 取到。
"""
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

ROOT = Path(__file__).resolve().parents[1]
HOME_JS = (ROOT / "editor" / "mobile" / "editor_home.js").read_text(encoding="utf-8")
CSS = (ROOT / "editor" / "mobile" / "home.css").read_text(encoding="utf-8")
EDITOR_PY = (ROOT / "engine" / "editor.py").read_text(encoding="utf-8")


def test_底栏三格都是真动作():
    for kind in ("home", "lib", "set"):
        assert f'data-nav="{kind}"' in HOME_JS, f"底栏少了 {kind} 这一格"
    # 三格共用一个委托，不许某格没接上
    assert 'if (kind === "lib") {' in HOME_JS
    assert 'else if (kind === "set") openSettings();' in HOME_JS
    # P204 用户连着两轮说「删掉下面的教程换成素材」：底栏不放教程
    assert 'data-nav="tut"' not in HOME_JS
    assert 'data-nav="new"' not in HOME_JS
    assert 'data-nav="import"' not in HOME_JS
    # P205：教程不再单独出（用户：放素材库里），首页那行小字入口也撤掉
    assert 'id="mHomeTutLink"' not in HOME_JS


def test_首页正文不再重复摆同一件事():
    # 教程引导卡、页头设置按钮、「开始新的」两格：都已在底栏有入口
    assert "m-tut-card" not in HOME_JS
    assert 'id="mHomeSet"' not in HOME_JS
    assert 'id="mHomeNew"' not in HOME_JS
    assert 'id="mHomeImport"' not in HOME_JS
    assert "m-quick-item" not in HOME_JS
    # 那句说明留着（用户要的），但不再挂在被压到底部的动作区上
    # P202：按「界面上只留 ≤6 字标签」压成一行短标签，同一层意思不变
    assert "先写台词，画面后补" in HOME_JS
    assert "没图没音乐也能先写台词" not in HOME_JS


def test_教程分两版():
    assert "function openTutorialSheet()" in HOME_JS
    # 读一遍那版讲的是真能用的指令，不是空话
    for line in ("@[小满]", "@[旁白]", "@choice:", "「素材库」"):
        assert line in HOME_JS, f"教程正文里少了 {line}"
    # 两版切换：读一遍 / 动手建
    assert 'id="mTutSeg"' in HOME_JS
    assert 'data-v="read"' in HOME_JS and 'data-v="make"' in HOME_JS
    assert 'id="mTutRead"' in HOME_JS and 'id="mTutMake"' in HOME_JS
    # 动手建的是真作品，且告诉人去哪儿删：走既有的 openTutorial（同一份 TUT_TEXT）
    assert 'id="mTutStart"' in HOME_JS
    assert "openTutorial();" in HOME_JS
    assert "不想要就在卡片右上「⋯」删掉" in HOME_JS


def test_横屏详情不再用扁封条():
    # 5:1 的铺满封面会把图拉成横带，看着不像封面（用户原话「比例不对」）
    assert "m-det-hero" not in HOME_JS
    assert '<div class="m-det-top">' in HOME_JS
    assert '<span class="m-det-thumb"' in HOME_JS
    assert "width: 88px; height: 88px" in CSS


def test_手机端前端住mobile目录():
    for name in ("editor_home.js", "home.css", "editor_mobile.js", "ui_polish.js"):
        assert (ROOT / "editor" / "mobile" / name).is_file(), f"mobile/ 缺 {name}"
        # 根目录不许再留同名副本：两份同名文件必然改一处漏一处
        assert not (ROOT / "editor" / name).is_file(), f"editor/{name} 应该已经搬走"
    # 路由能从 mobile/ 取到：/ui_polish.js、/editor_mobile.js 的 URL 不变
    assert 'os.path.join(front, "mobile")' in EDITOR_PY
