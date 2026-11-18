# -*- coding: utf-8 -*-
"""P117 手机端素材链路：静态守住几个关键实现，退回去就红。"""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
OFF = (ROOT / "editor" / "gal_offline.js").read_text(encoding="utf-8")
CSS = (ROOT / "editor" / "editor.css").read_text(encoding="utf-8")
MAIN = (ROOT / "editor" / "editor_main.js").read_text(encoding="utf-8")
HOME_JS = (ROOT / "editor" / "editor_home.js").read_text(encoding="utf-8")

pytestmark = [pytest.mark.unit]


def test_有素材库对象且走_IndexedDB():
    assert "window.MYONLAssets" in OFF
    assert "indexedDB" in OFF
    assert "myonl-assets" in OFF
    # 名字索引单独放 localStorage，否则同步的 /api/assets 答不上来
    assert "myonl:assets:index:v1" in OFF


def test_图片进来会被压到最长边_1280():
    assert "MAX_SIDE = 1280" in OFF
    assert "toDataURL(\"image/jpeg\", 0.82)" in OFF


def test_素材接口报真名字不再回空数组():
    seg = OFF.split('ROUTES["GET /api/assets"]')[1][:400]
    assert "idxRead()" in seg
    assert "images: []" not in seg


def test_素材真图有单独取图分支():
    assert "/api/asset/images/" in OFF
    assert "dataUrlToResponse" in OFF


def test_成品导出带上素材():
    seg = OFF.split("window.__myonlExportPack = function")[1][:1100]
    assert "MYONLAssets.allSplit()" in seg
    assert "assets: assets" in seg
    assert "audio: audio" in seg
    # 传空的老写法（buildPack 两个参数都是空）不许再回来
    assert "assets: {}, audio: {}, videos" not in seg


def test_素材分图片和音频两类():
    assert 'KIND_KEY = "myonl:assets:kind:v1"' in OFF
    assert 'out.audio[n] = v.dataUrl' in OFF
    # 音频原样存，不走压缩链路（压了只掉质量不掉体积）
    assert "function audioDataUrl(file)" in OFF


def test_接口把图片和音频分开报():
    seg = OFF.split('ROUTES["GET /api/assets"]')[1][:520]
    assert "audio: auds" in seg
    assert "images: imgs" in seg


def test_投递区能拖也能点():
    assert 'drop.addEventListener("drop"' in OFF
    assert "MAX_FILES = 20" in OFF
    assert "MAX_BYTES = 24 * 1024 * 1024" in OFF
    assert 'input.accept = "image/*,audio/*"' in OFF
    # 多选里混进不能收的类型，进度不能卡在「导入中」
    assert "done + failed" in OFF


def test_素材缩略图地址会被换成真数据():
    assert "fixAssetImages" in OFF
    assert 'img[src*="/api/asset/images/"]' in OFF


def test_素材面板层级抬到详情页之上():
    # 基础 z 只有 80，被场景详情页盖住 → 手机上点「素材」像没反应
    assert ".main.mobile-asset-open .asset-pane { z-index: 460" in CSS


def test_设置抽屉的_on_与兜底都在():
    seg = HOME_JS.split("openSettings")[1][:700]
    assert "m-set-sheet on" in seg
    assert "transform: none !important" in CSS


def test_素材刷新入口暴露给了离线内核():
    assert "window.__refreshAssets = refreshAssets" in MAIN
