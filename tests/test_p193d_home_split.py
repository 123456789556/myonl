# -*- coding: utf-8 -*-
"""P193d 横屏「左列表 + 右详情」契约。

用户原话：「这一部分的设计不大好……要分开并且优化检查」。横屏 844×390 上
原来的两列卡片 + 右侧「开始新的」既不贴合矮屏，也和底栏入口重复。
现在改成：左列单行卡（一屏露完三张），右列是选中作品的详情 + 教程引导 + 说明。

守三件事：
1. 竖屏把详情面板收掉（一屏一个主角，列表就是主角）；
2. 横屏点卡片先选中、不直接进作品（否则右侧详情永远看不到第二张）；
3. 横屏把「开始新的」与底栏重复的那组收掉，且给底栏留出底部空间。
"""
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

ROOT = Path(__file__).resolve().parents[1]
HOME_JS = (ROOT / "editor" / "mobile" / "editor_home.js").read_text(encoding="utf-8")
CSS = (ROOT / "editor" / "mobile" / "home.css").read_text(encoding="utf-8")


def test_竖屏收起详情面板():
    assert ".m-home-detail { display: none; }" in CSS
    assert '<div class="m-home-detail" id="mHomeDetail"></div>' in HOME_JS


def test_横屏打开详情并收起重复入口():
    assert "@media (min-width: 700px) and (max-height: 520px)" in CSS
    assert ".m-home-detail { display: flex;" in CSS
    assert ".m-home-side { display: none !important; }" in CSS
    # 底栏在横屏底部占 46px + 安全区，不留位置第三张卡会被压掉半截
    assert "padding-bottom: calc(52px + env(safe-area-inset-bottom))" in CSS


def test_横屏点卡片先选中不直接进():
    assert "function splitMode()" in HOME_JS
    assert "if (splitMode()) { selFolder = b.dataset.folder; paintDetail(projects); return; }" in HOME_JS
    # 竖屏仍然一点就进，不许多一步
    assert "openProject(b.dataset.folder, b);" in HOME_JS


def test_详情面板有唯一主操作():
    assert "function paintDetail(projects)" in HOME_JS
    assert 'class="m-det-go">继续编辑' in HOME_JS
    assert "box.querySelector(\".m-det-go\").addEventListener(\"click\", function () { openProject(p.folder); });" in HOME_JS
    # P194：教程已进底栏第二格，右栏不再挂第二条教程入口（同一件事第三个位置）
    assert "m-det-tut" not in HOME_JS


def test_横屏空列表右栏只给一句指路():
    # 入口都在底栏（教程 / 新建 / 导入），右栏画按钮就是重复；但空列表不能什么都不画
    assert "box.innerHTML = '<div class=\"m-det-empty\">" in HOME_JS
    assert "点底部「教程」照着走一遍，或「新建」直接开写。" in HOME_JS
    assert "paintDetail(projects);\n  }" in HOME_JS


def test_空态类不与旧空态卡同名():
    # body 挂 m-home-empty 会把旧空态卡的虚线框/居中/内边距套到整页（横屏空态实测复现）
    editor_css = (ROOT / "editor" / "editor.css").read_text(encoding="utf-8")
    assert ".m-home-empty {" not in editor_css
    assert 'classList.toggle("m-home-blank"' in HOME_JS
    assert "body.m-home-blank .m-home-note" in editor_css
