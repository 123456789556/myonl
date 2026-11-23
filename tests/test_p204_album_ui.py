# -*- coding: utf-8 -*-
"""P204 照手机相册：三格底栏、整页二级页、左上返回箭头、长按多选、批量删。

用户原话：「你就看这样的，你好像很少有这种回去的箭头，我不喜欢你把很多东西都
放在屏幕的最上面那一行的中间位置」「作品教程那部分总是有一个横线真的很丑」
「说多少遍删掉下面的教程换成素材」。

守五件事：
1. 底栏只留 作品 / 素材 / 设置，教程不在底栏（给一个列表下方的小入口）；
2. 底栏顶上那条 1px 横线去掉；
3. 回收箱与素材改成整页：左上返回箭头、标题居中、右上动作 —— 不是底部抽屉；
4. 回收箱照相册「最近删除」：三列格子、每格写还剩几天、可多选、底部还原/彻底删除；
5. 首页长按卡片进选择模式：顶栏取消/已选/全选，底部一条删除，批量删只问一次。
"""
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

ROOT = Path(__file__).resolve().parents[1]
HOME_JS = (ROOT / "editor" / "mobile" / "editor_home.js").read_text(encoding="utf-8")
TRASH_JS = (ROOT / "editor" / "mobile" / "editor_trash.js").read_text(encoding="utf-8")
CSS = (ROOT / "editor" / "mobile" / "ui-layout.css").read_text(encoding="utf-8")


def test_底栏三格且没有横线():
    nav = HOME_JS.split('id="mHomeNav"')[1].split("</div>")[0]
    # P210：用户第四次要求「我的作品下面最好四个 tab 最少四个」→ 加回一格，放回收箱
    assert nav.count("data-nav=") == 4
    assert 'data-nav="lib"' in nav and "<span>素材</span>" in nav
    assert 'data-nav="bin"' in nav and "<span>回收箱</span>" in nav
    assert 'data-nav="tut"' not in nav
    assert "border-top: 0 !important" in CSS


def test_教程不占列而是列表下的一行速查tab():
    # P205 用户：「教程不要单独出，最好放在素材库里」；P206 又加一句「教程不要单独开一列」
    assert 'id="mHomeTutLink"' not in HOME_JS
    # v1.2.53 用户：「素材内有笔记」—— 三个素材格之后加第四格「笔记」，
    # 教程仍然只是一行速查，不占格。
    assert '["image", "图片"], ["audio", "音频"], ["video", "视频"], ["note", "笔记"]]' in TRASH_JS
    assert '"tut"' not in TRASH_JS.split("LIB_TABS")[1].split(";")[0]
    assert 'id="mLibTut"' in TRASH_JS and "写法速查" in TRASH_JS
    assert "一行就是一屏" in TRASH_JS


def test_二级页是整页且返回箭头在左():
    assert ".m-bin-page, .m-lib-page" in CSS
    assert "grid-template-columns: 76px 1fr 76px" in CSS
    assert 'id="mBinLeft" aria-label="返回">‹<' in TRASH_JS
    assert ".m-bin-title { text-align: center;" in CSS
    # 回收箱与素材都必须走这层骨架，不许退回 m-sheet 抽屉
    assert 'binEl.className = "m-bin-page";' in TRASH_JS
    assert 'asEl.className = "m-lib-page";' in TRASH_JS
    # 设置页也走这层骨架，左上 ‹，顶上圆形头像
    assert 'sheet.className = "m-bin-page m-set-page";' in HOME_JS
    assert 'id="mSetAvatar"' in HOME_JS and 'id="mSetName"' in HOME_JS
    # 非选择态顶栏得真收起：display:grid 会顶掉 hidden
    assert ".m-sel-top[hidden]" in CSS


def test_回收箱照相册最近删除():
    assert "grid-template-columns: repeat(3, 1fr)" in CSS
    assert "days + \" 天\"" in TRASH_JS
    assert 'class="m-bin-cell" data-row=' in TRASH_JS
    assert 'id="mBinRestore"' in TRASH_JS and 'id="mBinPurge"' in TRASH_JS
    # 「选择」在右上，选中后变「全选」；标题变成已选 N
    assert "已选 \" + picked.length" in TRASH_JS
    assert '"选择"' in TRASH_JS


def test_首页长按进多选():
    assert "setTimeout(function () {" in HOME_JS and "}, 480)" in HOME_JS
    assert "if (selMode) { toggleSel(b.dataset.folder); return; }" in HOME_JS
    assert 'id="mSelTop"' in HOME_JS and 'id="mSelBar"' in HOME_JS
    assert 'id="mSelCancel"' in HOME_JS and 'id="mSelAll"' in HOME_JS and 'id="mSelDel"' in HOME_JS
    # 批量删只问一次，进回收箱还能还原
    assert "MYONLTrash.delMany" in HOME_JS
    assert "会先进回收箱，30 天内能还原" in HOME_JS


def test_批量删除只reload一次():
    assert "function delMany(names)" in TRASH_JS
    assert TRASH_JS.count("location.reload()") >= 2  # 批量搬箱/还原后各自只刷一次
    # delMany 里必须只有一次 reload：N 个作品不许刷 N 遍
    del_many = TRASH_JS.split("function delMany(names)")[1].split("function del(")[0]
    assert del_many.count("location.reload()") == 1
    assert "function restoreMany(names)" in TRASH_JS
    assert "function purgeMany(names)" in TRASH_JS
