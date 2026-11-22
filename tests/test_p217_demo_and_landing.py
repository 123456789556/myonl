# -*- coding: utf-8 -*-
"""P217：默认只有一份示范案例；打开作品直接落在台词上；设置页不写说明书。

用户这一轮的三条原话：
- 「你只要搞一个示范案例，然后你有个教程……示范案例跟教程绑在一起，名字叫示范案例」
- 「我打开一个作品，它直接给我弹出一个莫名其妙的窗口，一个界面，那是肯定不可能允许的」
- 「这些文字我觉得完全是没有必要的，是可以省略掉的」
- 「他的头像应该是用户两字，而不是只有一个用」

每条都对应一个曾经真实存在的缺陷，这里把它们钉住。
"""
from __future__ import annotations

import pathlib
import re

import pytest

pytestmark = [pytest.mark.unit]

ROOT = pathlib.Path(__file__).resolve().parents[1]
OFF = (ROOT / "editor" / "gal_offline.js").read_text(encoding="utf-8")
HOME = (ROOT / "editor" / "mobile" / "editor_home.js").read_text(encoding="utf-8")
MOB = (ROOT / "editor" / "mobile" / "editor_mobile.js").read_text(encoding="utf-8")
TRASH = (ROOT / "editor" / "mobile" / "editor_trash.js").read_text(encoding="utf-8")
DRAFT = (ROOT / "editor" / "editor_draft.js").read_text(encoding="utf-8")


def test_默认库只有一份示范案例():
    m = re.search(r"function blankLib\(\)[\s\S]*?\n  \}", OFF)
    assert m, "找不到 blankLib"
    body = m.group(0)
    assert body.count("name:") == 1, "默认库只许有一份作品，多出来的都是用户没要过的东西"
    assert 'current: "示范案例"' in body
    assert 'name: "示范案例"' in body


def test_教程不再另建一份作品():
    assert 'var TUT_NAME = "示范案例"' in HOME
    assert "TUT_TEXT" not in HOME, "第二份示例正文迟早和第一份说法不一致"
    assert "window.MYONLOpenDemo = openTutorial" in HOME


def test_速查里能直接打开示范案例():
    assert 'id="mLibTutDemo"' in TRASH
    assert "window.MYONLOpenDemo()" in TRASH
    # 速查不许再把人指向「新建项目」当示例入口：示例只有示范案例那一份
    assert "它会给你一份能玩的短作品" not in TRASH


def test_新建项目给的是空白不是又一份示范():
    m = re.search(r'ROUTES\["POST /api/new"\][\s\S]*?\n  \};', OFF)
    assert m, "找不到 /api/new"
    body = _code(m.group(0))
    assert '"@label start\\n"' in body, "新建要给一幕零台词的空白"
    assert "starterText()" not in body, "每建一个都塞 15 句示范台词，等于逼用户先删干净"
    # 默认那一份仍然用完整示范正文
    assert "var t = starterText();" in OFF


def test_选择态顶栏不许压住第一张卡():
    css = (ROOT / "editor" / "mobile" / "ui-layout.css").read_text(encoding="utf-8")
    m = re.search(r"html\.m-shell body\.m-selecting \.m-home \{[^}]*\}", css)
    assert m, "选择态没有给固定顶栏让位"
    # editor.css 那条 .m-home{padding:… !important} 会整条压掉非 important 的 padding-top
    assert "!important" in m.group(0)


def test_取消全选不许折成两行():
    css = (ROOT / "editor" / "mobile" / "ui-layout.css").read_text(encoding="utf-8")
    m = re.search(r"^html\.m-shell \.m-sel-all \{[^}]*\}", css, re.M)
    assert m
    assert "white-space: nowrap" in m.group(0)
    assert "padding-left: 0" in m.group(0)
    assert "76px 1fr 88px" in css, "右上格子要装得下四个字"


def test_垃圾箱选择态取消也不许折行():
    # 左上那颗平时是 26px 的「‹」，选择态变成「取消」两个字，44px 装不下
    assert 'binEl.classList.toggle("m-bin-sel", binSelOn)' in TRASH
    css = (ROOT / "editor" / "mobile" / "ui-layout.css").read_text(encoding="utf-8")
    m = re.search(r"html\.m-shell \.m-bin-sel \.m-bin-top \.m-back \{[^}]*\}", css)
    assert m, "选择态没有把箭头按钮改排成文字按钮"
    assert "white-space: nowrap" in m.group(0)
    assert "width: auto" in m.group(0)


def test_头像写两个字不是一个字():
    assert "function avatarText(name)" in HOME
    assert "s.slice(0, 2)" in HOME
    assert "pname.slice(0, 1)" not in HOME
    assert "(p.name || DEF_NAME).slice(0, 1)" not in HOME


def _code(src: str) -> str:
    """去掉整行注释 —— 注释里写着「原来这里是…」，别让校验撞上自己。"""
    return "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("//"))


def test_设置页三条说明书已删():
    code = _code(HOME)
    for stale in ("拿不准就选「跟随」", "只改上面那块预览框的形状", "选中态、按钮、作品卡上的蓝都跟着换"):
        assert stale not in code, "设置页还留着解释性长句：" + stale


def test_预览比例含安卓平板的16比10():
    assert '"16:10": "62.5%"' in HOME
    assert 'data-v="16:10"' in HOME


def test_切逐句不再无条件把人踢回场景列表():
    m = re.search(r"function setScriptMode\(m\)[\s\S]*?\n  \}", MOB)
    assert m, "找不到 setScriptMode"
    body = _code(m.group(0))
    # exitDetail 只许出现在「真的从源码切过来」那个分支里，且要按 wantDetail 决定
    assert "wantDetail" in body, "重开场景页时要回到用户上次待的那一态"
    assert body.count("exitDetail()") == 1


def test_多幕作品也直接落到第一幕():
    assert "items.length === 1" not in MOB, "只有单幕才进详情的话，多幕作品打开就是场景列表"
    assert "autoEnterDone" in MOB
    assert "wantDetail = true" in MOB


def test_保存提示不再一处说两遍():
    # 判据挂 CSS（手机壳 + saved 态），不挂 JS 里「另一处此刻可见吗」——
    # 状态栏那一格保存后才被放出来，比 paint 晚一拍，JS 判一次会漏。
    assert 'el.setAttribute("data-state", state)' in DRAFT
    css = (ROOT / "editor" / "mobile" / "ui-layout.css").read_text(encoding="utf-8")
    assert 'html.m-shell #mDraftBar[data-state="saved"]' in css
    assert "display: none !important" in css