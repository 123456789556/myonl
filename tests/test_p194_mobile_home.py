# -*- coding: utf-8 -*-
"""P194 手机端首页收口：底栏五格 + 教程抽屉 + 详情横排 + 按端分目录。

用户这轮的原话：「下面那栏明明可以加入」「专门放教程」「这个部分可以删掉」
「比例不对」「引擎拆分要做的移动端和 window 两个文件夹」。

守五件事：
1. 底栏五格（作品 / 教程 / 新建 / 导入 / 设置），每格都是真动作；
2. 首页正文里那两块重复的东西收干净：新手教程引导卡、页头设置按钮、
   「开始新的」两格（与底栏新建/导入同一件事）；
3. 教程是「语法速查 + 建一份可删练习」抽屉，不是只读文档，也不塞进 games/；
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


def test_底栏五格都是真动作():
    for kind in ("home", "tut", "new", "import", "set"):
        assert f'data-nav="{kind}"' in HOME_JS, f"底栏少了 {kind} 这一格"
    # 五格共用一个委托，不许某格没接上
    assert 'if (kind === "new") newProject();' in HOME_JS
    assert 'else if (kind === "import") importProject();' in HOME_JS
    assert 'else if (kind === "set") openSettings();' in HOME_JS
    assert 'else if (kind === "tut") openTutorialSheet();' in HOME_JS


def test_首页正文不再重复摆同一件事():
    # 教程引导卡、页头设置按钮、「开始新的」两格：都已在底栏有入口
    assert "m-tut-card" not in HOME_JS
    assert 'id="mHomeSet"' not in HOME_JS
    assert 'id="mHomeNew"' not in HOME_JS
    assert 'id="mHomeImport"' not in HOME_JS
    assert "m-quick-item" not in HOME_JS
    # 那句说明留着（用户要的），但不再挂在被压到底部的动作区上
    assert "没图没音乐也能先写台词" in HOME_JS


def test_教程是速查加可删练习():
    assert "function openTutorialSheet()" in HOME_JS
    # 语法速查讲的是真能用的指令，不是空话
    for line in ("@[小满]", "@[旁白]", "@choice:", "「素材」"):
        assert line in HOME_JS, f"教程速查里少了 {line}"
    # 按钮建的是真作品，且能删：走既有的 openTutorial（同一份 TUT_TEXT）
    assert 'id="mTutStart"' in HOME_JS
    assert "openTutorial();" in HOME_JS
    assert "不想要就删掉" in HOME_JS


def test_横屏详情不再用扁封条():
    # 5:1 的铺满封面会把图拉成横带，看着不像封面（用户原话「比例不对」）
    assert "m-det-hero" not in HOME_JS
    assert '<div class="m-det-top">' in HOME_JS
    assert '<span class="m-det-thumb"' in HOME_JS
    assert "width: 52px; height: 52px" in CSS


def test_手机端前端住mobile目录():
    for name in ("editor_home.js", "home.css", "editor_mobile.js", "ui_polish.js"):
        assert (ROOT / "editor" / "mobile" / name).is_file(), f"mobile/ 缺 {name}"
        # 根目录不许再留同名副本：两份同名文件必然改一处漏一处
        assert not (ROOT / "editor" / name).is_file(), f"editor/{name} 应该已经搬走"
    # 路由能从 mobile/ 取到：/ui_polish.js、/editor_mobile.js 的 URL 不变
    assert 'os.path.join(front, "mobile")' in EDITOR_PY
