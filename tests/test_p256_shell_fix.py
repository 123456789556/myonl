# -*- coding: utf-8 -*-
"""P256 手机壳的两处硬伤（本轮深检挖出来的，不是猜的）。

1. 进作品 / 新建作品后整屏白 1.8 秒：`html.m-boot body{visibility:hidden}` 只等首页挂
   `m-home-open`，进编辑器时永远等不到，只能等 60×30ms 兜底。实测 1904ms → 修后 85ms。
2. 卡片「⋯」那块面板实际铺满整屏：容器还带着老规则 `.m-sheet{inset:0}`，
   四行按钮挤在屏幕最上面；遮罩自己没挂 `.on`（0×0、点不中），点空白关不掉。
   修遮罩时还踩到第二层：遮罩有 z-index、正文没有，反过来盖住按钮（点删除没反应）。
"""
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "editor" / "index.html").read_text(encoding="utf-8")
CSS = (ROOT / "editor" / "mobile" / "ui-layout.css").read_text(encoding="utf-8")


def test_进编辑器不再等满兜底():
    # 首帧遮挡的摘除条件必须包含编辑器形态，否则每次进作品都白屏 1.8s
    assert "editor-level" in HTML
    assert 'classList.contains("m-home-open")' in HTML


def test_更多面板贴底不留整屏白():
    # P256 当时把面板钉在底部（top:auto）+ 加灰罩 + 正文压遮罩；P257 用户否掉了这套
    # （「不要出现灰色」「不占全屏」「不要靠着屏幕边缘」），改成贴着 ⋯ 的小浮层。
    # 这条只留一句：贴底抽屉那套规则不能再回来；细节断言交给 test_p257_more_menu.py。
    assert ".m-more-sheet" not in CSS
    assert ".m-more-pop" in CSS
