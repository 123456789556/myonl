# -*- coding: utf-8 -*-
"""P195 手机端首页 v4：卡片规格、真搜索、教程两版。

用户这两轮只给了感受，不给方向：「很奇怪就是体验下来不大好」「我不知道」。
所以这一版按可验证的四件事收口，不靠形容词：
1. 卡片从「46px 缩略 + 三个胶囊」换成「72px 方图 + 一行灰字」，卡高 110 → 92；
2. 顶栏放大镜是真过滤（打字就筛卡片，副标题给命中数），不是摆个假框；
3. 底栏四格平铺，「新建」不再浮起成圆键（P203 用户：中间的新建多余）；
4. 教程分两版：先读一遍（连续文字），再动手建（最小示例）。
"""
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

ROOT = Path(__file__).resolve().parents[1]
HOME_JS = (ROOT / "editor" / "mobile" / "editor_home.js").read_text(encoding="utf-8")
CSS = (ROOT / "editor" / "mobile" / "home.css").read_text(encoding="utf-8")


def test_卡片换成方图加一行灰字():
    # 三个胶囊是表单元素，一叠起来像设置项；换成一行灰字，重量轻、也省高度
    assert "m-card-chips" not in HOME_JS
    assert '<span class="m-card-meta">' in HOME_JS
    assert "width: 72px !important; height: 72px !important" in CSS
    assert ".m-home-card .m-card-name { font-size: 16.5px; }" in CSS


def test_搜索是真过滤():
    # 输入即筛，全量列表另存一份；取消恢复全部
    assert "var allProjects = [];" in HOME_JS
    assert "var findQ = \"\";" in HOME_JS
    assert 'projects.filter(function (x) {' in HOME_JS
    assert 'id="mHomeFindInput"' in HOME_JS
    assert '"搜到 " + shown.length + " 个"' in HOME_JS
    # 搜不到时给一句人话，不是一片空白
    assert "没搜到「" in HOME_JS
    assert "findQ = fin.value; render(allProjects);" in HOME_JS


def test_底栏平铺不再有浮起圆键():
    # P203 用户原话「中间的新建有些多余」：首页已有「新建项目」虚线卡，
    # 底栏再摆一颗蓝色＋ 就是同一个动作的第三条路。
    assert "m-nav-main" not in HOME_JS
    assert 'data-nav="new"' not in HOME_JS
    assert 'data-nav="lib"' in HOME_JS


def test_横屏详情填满右栏():
    assert "width: 88px; height: 88px" in CSS
    assert 'class="m-det-kv"' in HOME_JS
    assert "<b>' + p.ins + '</b><span>句台词</span>" in HOME_JS
    assert "width: 100%; height: 44px" in CSS


def test_教程两版且读的版本在前():
    # 读一遍是一篇能顺着读完的文字；动手建是一个按钮。顺序：先说是什么，再给动手。
    assert "m-tut-seg" in HOME_JS
    i_read = HOME_JS.index('id="mTutRead"')
    i_make = HOME_JS.index('id="mTutMake"')
    assert i_read < i_make, "「读一遍」应该排在「动手建」前面"
    # 读的版本是连续文字（小标题 + 段落 + 代码块），不是六张卡
    assert 'class="m-tut-h"' in HOME_JS
    assert 'class="m-tut-p"' in HOME_JS
    assert 'class="m-tut-c"' in HOME_JS
