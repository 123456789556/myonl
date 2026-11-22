# -*- coding: utf-8 -*-
"""P215：手机壳判据必须只有一套；触控目标不许被桌面时代的全局 button 规则压扁。

这一轮实测出来的三件事，全部转成契约，防止下次改样式又悄悄退化：

1. 1280×800 的安卓平板横屏，CSS 与 ui_layout 都认它是手机，唯独 editor_home.js
   的判据少了触屏那一条，首页直接 return 没建 —— 半手机半桌面。
2. editor.css 有一条全局 `button { height: 28px }`（桌面工具条用的），
   它把底栏四个格子钉成 28px 高，容器 58px 上下各 15px 点不到。总纲要求 ≥44px。
3. 作品卡 flex:1 1 0 会去分列表剩余高度，屏幕越高卡越胖（平板实测 254px，
   而缩略图固定 88px），与紧邻注释写的「撑满反而空出大半屏」自相矛盾。
"""
from __future__ import annotations

import pathlib
import re

import pytest

pytestmark = [pytest.mark.unit]

ROOT = pathlib.Path(__file__).resolve().parents[1]
EDITOR = ROOT / "editor"

CANON_PARTS = ("max-width:860px", "max-height:520px", "pointer:coarse", "hover:none", "max-width:1400px")


def _read(rel: str) -> str:
    return (EDITOR / rel).read_text(encoding="utf-8")


def _squeeze_js(text: str) -> str:
    """JS 里媒体查询常被拆成 "..." + "..." 两截，去掉引号/加号/空白才看得见全串。"""
    return re.sub(r"""[\s"'+]""", "", text)


def _strip_css_comments(text: str) -> str:
    return re.sub(r"/\*.*?\*/", "", text, flags=re.S)


def test_手机壳判据处处一致():
    """凡是决定「走不走手机壳」的 matchMedia，三段都得齐。"""
    files = [
        "editor_shell.js",
        "editor_main.js",
        "mobile/editor_home.js",
        "mobile/editor_mobile.js",
        "mobile/ui_polish.js",
    ]
    bad = []
    for rel in files:
        flat = _squeeze_js(_read(rel))
        for m in re.finditer(r"\(max-width:860px\),\(max-height:520px\)", flat):
            window = flat[m.start():m.start() + 160]
            if not all(p in window for p in CANON_PARTS):
                bad.append("%s: %s" % (rel, window[:110]))
    assert not bad, "手机壳判据缺段（少了触屏兜底，平板会漏成桌面）：\n" + "\n".join(bad)


def test_底栏格子解开了全局button死高():
    css = _strip_css_comments(_read("editor.css"))
    m = re.search(r"\.m-nav-item\s*\{[^}]*\}", css)
    assert m, "找不到 .m-nav-item 规则"
    body = re.sub(r"\s+", "", m.group(0))
    assert "height:auto" in body, ".m-nav-item 必须解开全局 button 的 28px 死高"
    assert "min-height:44px" in body, ".m-nav-item 触控目标下限必须是 44px"


def test_作品卡不去分屏幕高度():
    css = re.sub(r"\s+", "", _strip_css_comments(_read("editor.css")))
    assert ".m-home-list.m-home-card{flex:110" not in css, (
        "作品卡又改回 flex:1 1 0 了 —— 屏幕越高卡越胖，平板上会变成 254px 的空白胖卡"
    )
    assert ".m-home-list.m-home-card{flex:00auto" in css, "作品卡应按内容取高"


def test_全局button死高还在_所以覆盖不能删():
    """这条不是要求保留坏规则，而是说明上面两条覆盖为什么必须存在。

    哪天全局 button 的 height 被去掉了，上面两条覆盖可以一起简化；
    但只要它还在，删掉覆盖就等于把底栏压回 28px。
    """
    css = re.sub(r"\s+", "", _strip_css_comments(_read("editor.css")))
    if re.search(r"(?m)^button\{height:28px", css):
        assert "min-height:44px" in css