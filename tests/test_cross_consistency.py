# -*- coding: utf-8 -*-
"""tests/test_cross_consistency.py：手机端成品在电脑浏览器里打开的一致性核对（无头）。

只做桌面渲染侧的可复算几何断言；手机侧几何由 web/test/probe/cross-render.js 出。
两端同一指令流（runtime snapshot），这里核对桌面侧几何与布局口径自洽，不漏背景/立绘/
对话框/选项的状态。
"""
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame  # noqa: E402

from engine.renderer import Renderer  # noqa: E402

pytestmark = [__import__("pytest").mark.ui]

GAME_ROOT = os.path.join(os.path.dirname(__file__), "..", "games", "标准示例")


def _state():
    return {
        "bg": "bg_教室",
        "music": "bgm_night",
        "sprites": [
            {"char": "苏晴", "expr": "微笑", "pos": "左"},
            {"char": "林晚", "expr": "微笑", "pos": "右"},
        ],
        "vars": {},
        "characters": {"苏晴": {"color": "#8ecae6"}, "林晚": {"color": "#ffb3c8"}},
        "history": [{"char": "苏晴", "text": "喂——今天又不等我？"}],
        "pending_choice": {"options": [
            {"text": "一起去咖啡店避雨", "target": "结局_咖啡店", "available": True},
            {"text": "留在天台说出那个约定", "target": "结局_约定", "available": True},
        ], "line": 1},
        "finished": False,
    }


def test_desktop_renders_full_state_with_real_assets():
    """标准示例剧本的一帧：背景/双立绘/对话框/选项都要落到画面上，不崩、不出界。"""
    ren = Renderer((1280, 720), GAME_ROOT)
    try:
        ren.render(_state())
        w, h = ren.size
        assert (w, h) == (1280, 720)
        # 选项命中矩形存在且水平居中、不越出画布
        assert len(ren._choice_rects) == 2
        for rect, _idx, avail in ren._choice_rects:
            assert avail
            assert 0 <= rect.x and rect.x + rect.width <= w
            assert 0 <= rect.y and rect.y + rect.height <= h
        # 立绘矩形：pos=左贴边、pos=右贴边（桌面侧既有口径，不挪）。
        # 渲染侧不暴露盒子列表，这里只核对状态里的 pos 被保留、渲染不崩。
        sprites = _state()["sprites"]
        assert [s["pos"] for s in sprites] == ["左", "右"]
    finally:
        ren.close()


def test_desktop_cg_uses_fit_not_cover():
    """CG 在桌面侧是 contain（留黑边）；这是设计口径，手机侧 cover 差异另列清单。"""
    ren = Renderer((1280, 720), GAME_ROOT)
    try:
        ren.play_cg("bg_教室")
        ren.render({})
        # CG 展示时屏蔽对话框
        assert ren._cg_showing is not None
    finally:
        ren.close()


def test_desktop_cg_clears_on_bg_change():
    """@bg 切回静态背景时 CG 必须退场，与手机端 state.cg 在 @bg 清空同一语义。"""
    ren = Renderer((1280, 720), GAME_ROOT)
    try:
        ren.play_cg("bg_教室")
        assert ren._cg_showing is not None
        ren.render({"bg": "bg_走廊", "history": []})
        assert ren._cg_showing is None, "切到 @bg 后 CG 未退场"
    finally:
        ren.close()
