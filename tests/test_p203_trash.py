# -*- coding: utf-8 -*-
"""P203 作品可删、删了能找回：卡片「⋯」更多菜单 + 垃圾箱 + 素材库格。

用户这轮原话：「做一个删除的垃圾箱标志，每个作品那里都有三个点的标志表示更多的
处理方式」「我们的游戏怎么删除呢是不是可以批量处理呢有没有垃圾箱呢三十天内可
以找回呢」「文本改成素材库」。

守六件事：
1. 每张作品卡右上有一个「⋯」，点它出菜单，不再只有"点开=进作品"一个动作；
2. 删除不是真删，先进 `myonl:off:trash:v1`，30 天可找回；
3. 垃圾箱**不动** `myonl:off:lib:v1` 的结构 —— 那个库空掉会被 readLib 当成
   「第一次打开」重建一个"我的第一个游戏"，所以回收不能塞在里面；
4. 改名要同步草稿，否则下次打开会被判成别人的草稿丢掉；
5. 未命名作品自动编号，不再靠 `未命名 · MMDD-HHMM` 撞名；
6. 底栏第四格是素材库，用既有的跨作品素材库（window.MYONLAssets）。
"""
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

ROOT = Path(__file__).resolve().parents[1]
TRASH_JS = (ROOT / "editor" / "mobile" / "editor_trash.js").read_text(encoding="utf-8")
LAYOUT_JS = (ROOT / "editor" / "mobile" / "ui_layout.js").read_text(encoding="utf-8")
HOME_JS = (ROOT / "editor" / "mobile" / "editor_home.js").read_text(encoding="utf-8")
OFFLINE_JS = (ROOT / "editor" / "gal_offline.js").read_text(encoding="utf-8")
INDEX_HTML = (ROOT / "editor" / "index.html").read_text(encoding="utf-8")
CSS = (ROOT / "editor" / "mobile" / "ui-layout.css").read_text(encoding="utf-8")


def test_卡片右上有一个更多按钮():
    assert '<button type="button" class="m-card-more" data-more="\' + folder' in HOME_JS
    # 卡片从 button 改成 div：button 里不许套 button，否则两层点击互相吞
    assert "return '<div class=\"m-home-card'" in HOME_JS
    assert "\" data-folder=\"' + folder + '\" role=\"button\" tabindex=\"0\">'" in HOME_JS
    # 点「⋯」不能顺带进作品
    assert 'if (e.target.closest && e.target.closest("[data-more]")) return;' in HOME_JS
    assert "MYONLTrash.more(" in HOME_JS


def test_删除进垃圾箱不真删():
    assert "window.MYONLTrash" in TRASH_JS
    assert '"myonl:off:trash:v1"' in TRASH_JS
    # 30 天：常量写成乘式，改天数时算式还在
    assert "var KEEP_DAYS = 30;" in TRASH_JS
    assert "Date.now() - KEEP_DAYS * DAY" in TRASH_JS
    # 删当前作品时把草稿一起丢掉，不然下次打开会把删掉的内容写回库
    assert "MYONLDraft" in TRASH_JS and "drop(" in TRASH_JS


def test_垃圾箱不碰作品库结构():
    # 独立 key：readLib 里「lib.projects.length 为 0 → 重建 blankLib」这条
    # 会把空库变成"我的第一个游戏"，回收站塞进 lib 必然触发它
    assert '"myonl:off:lib:v1"' not in TRASH_JS
    assert "blankLib" not in TRASH_JS


def test_改名对外暴露且与内核同一份缓存():
    # editor_trash 改名只能调 ui_layout 暴露的这个入口
    assert "window.MYONLRenameProject = renameProject;" in LAYOUT_JS
    # 直接写 localStorage 会被下一次 writeLib 用 memLib 整体覆盖回去
    assert "var api = window.__myonlLib;" in LAYOUT_JS
    assert "api.write(lib);" in LAYOUT_JS
    assert "window.__myonlLib = { read: readLib, write: writeLib };" in OFFLINE_JS


def test_垃圾箱自己有入口不怕作品删光():
    # 只靠卡片上的「⋯」，作品删到最后一张就再也进不去垃圾箱了
    assert 'id="mHomeBin"' in HOME_JS
    assert "window.MYONLTrash.openBin()" in HOME_JS
    # 空的时候不显示：home.css 给 .m-home-find 定了 display:flex，得压回去
    assert "refreshBin()" in HOME_JS
    assert "b.hidden = !n;" in HOME_JS
    assert ".m-home-find[hidden] { display: none; }" in CSS


def test_点删除先问一句再进垃圾箱():
    # P209：换成自绘弹窗（系统 confirm 在手机上丑得没法看），动作仍是「先问一句再进箱」
    assert "dlgConfirm({" in TRASH_JS
    assert 'title: "删除「" + name + "」？"' in TRASH_JS
    assert 'msg: "会先进垃圾箱，" + KEEP_DAYS + " 天内能还原。"' in TRASH_JS


def test_新建入口常驻列表末尾():
    # 底栏那颗「新建」撤了，虚线卡就是唯一入口：空态有、有作品也有
    assert "list.innerHTML += ghostCard();" in HOME_JS
    assert "'</div>' + ghostCard();" in HOME_JS
    # 两处都挂到同一个按钮 id 上，点击走 newProject
    assert 'if (gh) gh.addEventListener("click", newProject);' in HOME_JS


def test_首页不挂编辑器状态栏():
    # 真机截图里「第 4 行 / ✓ 共 15 行」压进底栏，像没加载完的残字
    assert 'sbEl.style.display = "none"' in HOME_JS


def test_横屏左栏标出右栏是哪一张():
    assert "c.dataset.folder === selFolder" in HOME_JS
    assert "min-width: 0;" in CSS


def test_未命名自动编号():
    assert "MYONLTrash.nextName(lib)" in OFFLINE_JS
    assert "function nextName(" in TRASH_JS


def test_底栏第四格是素材库():
    assert "MYONLAssetLib.open()" in HOME_JS
    assert "window.MYONLAssetLib" in TRASH_JS
    # 用既有的跨作品素材库，不新建一套存储
    assert "MYONLAssets" in TRASH_JS
    # 三个脚本/路由都挂上了
    assert 'data-nav="lib"' in HOME_JS
    assert "/editor_trash.js" in INDEX_HTML
