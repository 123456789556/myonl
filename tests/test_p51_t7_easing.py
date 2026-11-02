# -*- coding: utf-8 -*-
"""P51-T7 验收：缓动曲线库（engine/timeline.py `EASINGS`，八大方向 3.1）。

验收口径（计划-P51 T7）：10+ 曲线、单测端点 + 单调性、旧语法全绿。

- 端点：除 `none`（直达，永远返回 1）外，所有曲线 f(0)=0、f(1)=1；
  back 族两端会过冲，但端点仍严格取 0/1。
- 单调性：除 back 族（设计上就要过冲）外，0→1 全程非递减。
- 族间区分：in/out/in_out 三方向互不相同；quad 的 in_out 不再与 sine 撞车（历史 bug 回归）。
- 解析器：`ease=<曲线名>` 从 `timeline.EASINGS` 取单一数据源，新曲线全部可解析、可 dump 往返，
  未知曲线报中文错误并列出可选值。
"""
import math

import pytest

from engine import timeline
from engine.parser import GalSyntaxError, dump_text, parse_text

pytestmark = [pytest.mark.unit]

BASIC = {"linear", "none", "ease_in", "ease_out"}
FAMILIES = ("quad", "cubic", "quart", "sine", "expo", "back")
STANDARD = {f"ease_{d}_{fam}" for fam in FAMILIES for d in ("in", "out", "in_out")}
ALL_NAMES = BASIC | STANDARD


def test_曲线名齐全且可调用():
    """22 个名字 = 4 个基础名 + 6 族 × 3 方向（验收要求 10+）。"""
    assert set(timeline.EASINGS) == ALL_NAMES
    assert len(STANDARD) == 18 and len(ALL_NAMES) == 22
    for name, fn in timeline.EASINGS.items():
        assert callable(fn), name
        assert isinstance(fn(0.3), float), name


@pytest.mark.parametrize("name", sorted(n for n in ALL_NAMES if n != "none"))
def test_端点_起点0终点1(name):
    fn = timeline.EASINGS[name]
    assert fn(0.0) == pytest.approx(0.0, abs=1e-9)
    assert fn(1.0) == pytest.approx(1.0, abs=1e-9)


@pytest.mark.parametrize("name", sorted(n for n in ALL_NAMES
                                        if "_back" not in n and n != "none"))
def test_单调性_非back族全程不减(name):
    fn = timeline.EASINGS[name]
    prev = -1.0
    for i in range(101):
        t = i / 100.0
        value = fn(t)
        assert value + 1e-12 >= prev, f"{name} 在 t={t} 处回退（{prev} → {value}）"
        prev = value


def test_none_直达不看进度():
    none = timeline.EASINGS["none"]
    assert none(0.0) == 1.0 and none(0.5) == 1.0 and none(1.0) == 1.0


def test_back族端点严格且双向过冲():
    """back 族是唯一允许越出 0~1 的曲线族：端点仍严格，几何上必须过冲。"""
    for name in ("ease_in_back", "ease_out_back", "ease_in_out_back"):
        fn = timeline.EASINGS[name]
        assert fn(0.0) == pytest.approx(0.0)
        assert fn(1.0) == pytest.approx(1.0)

    samples = {name: [timeline.EASINGS[name](i / 100.0) for i in range(101)]
               for name in ("ease_in_back", "ease_out_back", "ease_in_out_back")}
    assert min(samples["ease_in_back"]) < 0.0      # 起步先退一点
    assert max(samples["ease_out_back"]) > 1.0     # 收尾冲过头
    assert min(samples["ease_in_out_back"]) < 0.0 and max(samples["ease_in_out_back"]) > 1.0


def test_方向与族互不相同():
    """in/out 两方向、quad/sine 两族都不能退化成同一条曲线（历史 bug 回归）。"""
    for fam in FAMILIES:
        in_fn = timeline.EASINGS[f"ease_in_{fam}"]
        out_fn = timeline.EASINGS[f"ease_out_{fam}"]
        assert abs(in_fn(0.3) - out_fn(0.3)) > 1e-3, f"{fam} 的 in/out 撞车"

    quad_in_out = timeline.EASINGS["ease_in_out_quad"]
    sine_in_out = timeline.EASINGS["ease_in_out_sine"]
    assert quad_in_out(0.25) == pytest.approx(0.125)          # 2t² 前半段
    assert sine_in_out(0.25) == pytest.approx(0.5 - 0.5 * math.cos(math.pi / 4))
    assert abs(quad_in_out(0.25) - sine_in_out(0.25)) > 1e-3  # 曾被写成同一条


def test_已知曲线取值():
    e = timeline.EASINGS
    assert e["linear"](0.5) == 0.5
    assert e["ease_in"](0.5) == 0.25                     # quad 别名，慢起
    assert e["ease_out"](0.5) == 0.75                    # quad 别名，快起
    assert e["ease_in_cubic"](0.5) == pytest.approx(0.125)
    assert e["ease_in_out_cubic"](0.5) == pytest.approx(0.5)
    assert e["ease_in_out_quart"](0.25) == pytest.approx(0.03125)
    assert e["ease_in_out_sine"](0.5) == pytest.approx(0.5)
    assert e["ease_in_out_back"](0.5) == pytest.approx(0.5)
    assert e["ease_in_expo"](0.0) == 0.0 and e["ease_in_expo"](1.0) == pytest.approx(1.0)
    assert e["ease_out_expo"](0.0) == 0.0 and e["ease_out_expo"](1.0) == 1.0


@pytest.mark.parametrize("name", sorted(STANDARD))
def test_parser_新曲线可解析且dump往返(name):
    ins = parse_text(f"@anim 玛丽 x=-100~0 1.5 ease={name}\n")[0]
    assert ins["ease"] == name
    assert dump_text([ins]).strip() == f"@anim 玛丽 x=-100~0 1.5 ease={name}"


def test_parser_未知曲线报错并列出可选值():
    with pytest.raises(GalSyntaxError) as exc:
        parse_text("@anim 玛丽 x=-100~0 1 ease=飞一般\n")
    msg = str(exc.value)
    assert "ease 只能是" in msg
    assert "ease_in_out_back" in msg and "linear" in msg


def test_轨道接入新曲线():
    """Timeline 轨按 easing 名取样（Track.sample 走 EASINGS 表）。"""
    tl = timeline.Timeline()
    tl.play("x", 1000, lambda t: t, easing="ease_in_out_quart")
    assert tl.tick(250)["x"] == pytest.approx(0.03125)
    assert tl.tick(1000)["x"] == pytest.approx(1.0)
