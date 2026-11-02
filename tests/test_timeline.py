# -*- coding: utf-8 -*-
"""P30-C-a 验收：通用时间轴调度器（engine/timeline.py）+ 渲染层接入。

前半是纯函数单测（不需要 pygame）；后半是渲染层接入断言（无头 dummy 驱动，
时间源用 monkeypatch 固定，验证"镜头/转场/停留真的来自同一条时间轴"）。
"""
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")  # 无头模式，须在 import pygame 前生效

import pytest

from engine import timeline
from engine.renderer import CAM_PAN_RATIO, Renderer

pytestmark = [pytest.mark.unit, pytest.mark.ui]


# ==================== 1. 补间函数 ====================

def test_三档补间与直达():
    assert timeline.EASINGS["linear"](0.5) == 0.5
    assert timeline.EASINGS["ease_in"](0.5) == 0.25          # 慢起
    assert timeline.EASINGS["ease_out"](0.5) == 0.75         # 快起
    assert timeline.EASINGS["none"](0.0) == 1.0              # 直达：不看进度，直接取目标
    assert timeline.EASINGS["none"](0.9) == 1.0


def test_未知补间名回落线性():
    tl = timeline.Timeline()
    track = tl.play("x", 1000, lambda t: t, easing="飞一般")
    assert track.easing == timeline.DEFAULT_EASING
    tl.tick(500)
    assert tl.value("x") == pytest.approx(0.5)


# ==================== 2. 轨的推进 / 完成 ====================

def test_轨按时刻插值并钳制():
    tl = timeline.Timeline()
    tl.play("x", 1000, lambda t: 100.0 * t, t0=1000)
    assert tl.tick(500)["x"] == pytest.approx(0.0)    # 未开始
    assert tl.tick(1500)["x"] == pytest.approx(50.0)  # 半程
    assert tl.tick(2000)["x"] == pytest.approx(100.0)  # 播完
    assert tl.tick(9999)["x"] == pytest.approx(100.0)  # 超时不再过冲


def test_进度与完成判定():
    tl = timeline.Timeline()
    tl.play("x", 800, lambda t: t, t0=0)
    assert tl.progress("x", 0) == 0.0
    assert tl.progress("x", 400) == pytest.approx(0.5)
    assert tl.done("x", 799) is False
    assert tl.done("x", 800) is True
    # tick 不自动删轨：生命周期由调用方显式 cancel
    tl.tick(900)
    assert tl.has("x") is True
    tl.cancel("x")
    assert tl.has("x") is False and tl.value("x") is None


def test_零时长轨立即完成():
    tl = timeline.Timeline()
    tl.play("x", 0, lambda t: "target")
    assert tl.done("x", 0) is True
    assert tl.tick(0)["x"] == "target"


def test_循环轨永远不算完():
    tl = timeline.Timeline()
    tl.play("loop", 1000, lambda t: t, loop=True)
    assert tl.progress("loop", 1500) == pytest.approx(0.5)
    assert tl.progress("loop", 2500) == pytest.approx(0.5)
    assert tl.done("loop", 99_999) is False


def test_hold轨只计时不取值():
    tl = timeline.Timeline()
    tl.hold("splash", 1200, t0=0)
    assert tl.tick(600)["splash"] is None
    assert tl.done("splash", 600) is False
    assert tl.done("splash", 1200) is True
    assert tl.progress("splash", 1200) == 1.0


def test_同名轨覆盖与清空():
    tl = timeline.Timeline()
    tl.play("camera", 1000, lambda t: "旧", t0=0)
    tl.play("camera", 500, lambda t: "新", t0=0)
    assert tl.tick(100)["camera"] == "新"
    assert tl.names() == ["camera"]
    tl.play("splash", 100, t0=0)
    tl.clear()
    assert tl.names() == [] and tl.value("camera") is None


def test_取值函数每帧只调用一次():
    """含随机的取值函数（震动）依赖这条约定，重复调用会得到不同画面。"""
    calls = []

    def fn(t):
        calls.append(t)
        return len(calls)

    tl = timeline.Timeline()
    tl.play("shake", 1000, fn, t0=0)
    tl.tick(100)
    tl.tick(200)
    assert len(calls) == 2


# ==================== 3. 时钟 ====================

def test_时钟首次调用起算且可重置():
    tl = timeline.Timeline()
    assert tl.elapsed("sprite", 5000) == 0        # 首次调用即起点
    assert tl.elapsed("sprite", 5300) == 300
    tl.reset_clock("sprite")
    assert tl.elapsed("sprite", 9000) == 0


# ==================== 4. 渲染层接入 ====================

def _make_ren(tmp_path, monkeypatch):
    """固定时间源的 renderer：返回 (renderer, 可写的时间盒子)。"""
    box = [0]
    monkeypatch.setattr(Renderer, "_now_ms", lambda self: box[0])
    return Renderer((320, 180), str(tmp_path)), box


def test_渲染层_镜头pan进度来自时间轴(tmp_path, monkeypatch):
    ren, box = _make_ren(tmp_path, monkeypatch)
    try:
        ren.play_camera("pan", ["右", 1.0])
        track = ren.timeline.track("camera")
        assert track is not None and track.dur == 1000 and track.meta["kind"] == "pan"
        ren.render({})
        assert ren._cam_dx == pytest.approx(0.0)
        box[0] = 500
        ren.render({})
        assert ren._cam_dx == pytest.approx(320 * CAM_PAN_RATIO * 0.5)
        box[0] = 1000
        ren.render({})
        # 播完停在目标位置，轨被回收
        assert ren._cam_dx == pytest.approx(320 * CAM_PAN_RATIO)
        assert ren.timeline.track("camera") is None
    finally:
        ren.close()


def test_渲染层_镜头reset播完归零(tmp_path, monkeypatch):
    ren, box = _make_ren(tmp_path, monkeypatch)
    try:
        ren.play_camera("pan", ["右", 1.0])
        box[0] = 1000
        ren.render({})
        assert ren._cam_dx != pytest.approx(0.0)
        ren.play_camera("reset", [0.5])
        box[0] = 1250
        ren.render({})
        assert ren._cam_dx == pytest.approx(320 * CAM_PAN_RATIO * 0.5)
        box[0] = 1500
        ren.render({})
        assert ren._cam_dx == pytest.approx(0.0)
        assert ren._cam_scale == pytest.approx(1.0)
    finally:
        ren.close()


def test_渲染层_转场进度来自时间轴(tmp_path, monkeypatch):
    ren, box = _make_ren(tmp_path, monkeypatch)
    try:
        state = {"bg": "a", "sprites": [], "history": []}
        box[0] = 100
        ren.render(state)
        ren.play_transition("dissolve", [0.6])
        box[0] = 200
        state["bg"] = "b"
        ren.render(state)
        track = ren.timeline.track("transition")
        assert track is not None and track.dur == 600
        # 转场轨在本帧（bg 变化）才挂上，一帧之后才开始有采样值；进度从 0 起
        assert ren.timeline.progress("transition", box[0]) == pytest.approx(0.0)
        box[0] = 500
        ren.render(state)
        assert ren.timeline.value("transition") == pytest.approx(0.5)
        box[0] = 800
        ren.render(state)
        assert ren.timeline.track("transition") is None and ren._trans_old is None
    finally:
        ren.close()


def test_退出序幕清掉停留轨(tmp_path, monkeypatch):
    ren, box = _make_ren(tmp_path, monkeypatch)
    try:
        ren.set_splash(True)
        ren.timeline.hold("splash", 1200, t0=0)
        ren.set_splash(False)
        assert ren.timeline.has("splash") is False
    finally:
        ren.close()
