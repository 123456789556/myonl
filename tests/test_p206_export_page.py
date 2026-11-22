# -*- coding: utf-8 -*-
"""P206 导出页：自己的整页，不再是「界面设计中心」里夹的一条。

用户看过 v1.2.30 的导出页：一屏皮肤参数，真正要按的五个动作埋在底下，
原话「导入导出也要好好做，有些界面的设计显然不大好」。

守四件事：
1. 导出是整页：左上 ‹ 返回、标题居中，和垃圾箱/素材/设置同一套骨架；
2. 先把体积摆出来，再让人决定走哪条（单文件 / APK）；
3. 五个动作分两组：发给别人（HTML / APK）、留后路（.gal / .json / 版本历史）；
4. 旧的那条「插进参数页」只作兜底，正常路径不再走它。
"""
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

ROOT = Path(__file__).resolve().parents[1]
EXP = (ROOT / "editor" / "mobile" / "editor_export.js").read_text(encoding="utf-8")
OFF = (ROOT / "editor" / "gal_offline.js").read_text(encoding="utf-8")
CSS = (ROOT / "editor" / "mobile" / "ui-layout.css").read_text(encoding="utf-8")
HTML = (ROOT / "editor" / "index.html").read_text(encoding="utf-8")
ROUTES = (ROOT / "engine" / "editor.py").read_text(encoding="utf-8")


def test_导出页是整页且返回箭头在左():
    assert 'el.className = "m-bin-page m-exp-page";' in EXP
    assert 'id="mExpLeft" aria-label="返回">‹<' in EXP
    assert '<span class="m-bin-title">导出</span>' in EXP
    assert 'id="mExpLeft"' in EXP and "addEventListener" in EXP


def test_先量体积再决定走哪条():
    assert "MYONLAssets.allSplit" in EXP
    assert "超过 30 MB" in EXP and "能单文件发" in EXP
    assert 'id="mExpSize"' in EXP


def test_五个动作都接上真函数():
    for fn in ("__myonlExportPack", "__myonlExportApk", "__myonlExportGal",
               "__myonlExportLib"):
        assert fn in EXP, fn
    assert "MYONLSnapshotsUI" in EXP
    # 两组：发给别人 / 留后路
    assert "发给别人" in EXP and "给自己留后路" in EXP


def test_正常路径不再插进参数页():
    assert "window.MYONLExport" in OFF and "MYONLExport.open()" in OFF
    # 兜底还在（老壳/老页面还能用），但不能是唯一路径
    assert "injectExportBar" in OFF


def test_导出页有样式且能加载():
    assert ".m-exp-row" in CSS and ".m-exp-size" in CSS
    assert "/editor_export.js" in HTML
    assert '"/editor_export.js"' in ROUTES
