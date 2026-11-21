# -*- coding: utf-8 -*-
"""P195 手机端首页 v4：卡片规格、真搜索、浮起的新建键、卡片化教程。

用户这两轮只给了感受，不给方向：「很奇怪就是体验下来不大好」「我不知道」。
所以这一版按可验证的四件事收口，不靠形容词：
1. 卡片从「46px 缩略 + 三个胶囊」换成「72px 方图 + 一行灰字」，卡高 110 → 92；
2. 顶栏放大镜是真过滤（打字就筛卡片，副标题给命中数），不是摆个假框；
3. 底栏中间的「新建」浮起成蓝圆键 —— 这一屏唯一"往前推"的动作；
4. 教程抽屉一条一块卡（图标 + 标题 + 一句人话 + 一行能照抄的写法），主按钮置顶。
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


def test_底栏新建成浮起圆键():
    assert 'class="m-nav-item m-nav-main" data-nav="new"' in HOME_JS
    assert 'class="m-nav-main-ic"' in HOME_JS
    assert ".m-nav-main-ic {" in CSS
    assert "margin-top: -18px" in CSS
    # 蓝底白加号：这是这一屏唯一的主推进动作
    assert "background: var(--blue); color: #fff;" in CSS


def test_横屏详情填满右栏():
    assert "width: 88px; height: 88px" in CSS
    assert 'class="m-det-kv"' in HOME_JS
    assert "<b>' + p.ins + '</b><span>句台词</span>" in HOME_JS
    assert "width: 100%; height: 44px" in CSS


def test_教程一条一块卡且主按钮置顶():
    assert "m-tut-item" in HOME_JS
    assert "m-tut-ic2" in HOME_JS
    assert "'<code>'" in HOME_JS
    # 主按钮必须在条目之前：点开教程下一步就是动手，不该先滚一屏
    i_start = HOME_JS.index('id="mTutStart"')
    i_doc = HOME_JS.index('<div class="m-tut-doc">')
    assert i_start < i_doc, "「建一份练习」被排到教程条目下面了"
