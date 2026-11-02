"""通用时间轴调度器（P30-C-a / B3）。

一个时钟、一类轨道：镜头动画、转场、立绘帧序列、序幕停留全部挂在同一条 Timeline 上，
每帧 `tick(now)` 统一推进并产出各自的中间态，替代过去各写一套 `_t0` + 各自插值的做法。

铁律：
- 标准库 only，不 import pygame（renderer 通过 `_now_ms()` 传时刻进来），便于无头单测
- tick 每帧对每条轨的取值函数只调用一次（震动等含随机的取值函数依赖这一点）
- 轨的生命周期由调用方显式 cancel()，tick 不会偷偷删轨（便于查询"是否还在播"）

术语：
- 轨道 Track：名字 + 起始毫秒 + 时长 + 取值函数 `fn(t)`，t 为已缓动的归一化进度 0~1
- 补间：多种缓动曲线（T7 起 22 个名字：6 族 × 3 方向 = 18 条标准曲线，
  外加 linear / none / ease_in / ease_out，其中 ease_in、ease_out 是 quad 别名，向后兼容）；
  `none` = 直达（不插值，直接取目标值）
- hold 轨：只有时长没有取值，表达"停一会儿"（序幕字幕/CG 停留）
- 时钟 Clock：只记起点，用来算"已过多久"（立绘帧序列按流逝时间取帧，不做进度插值）
"""
from __future__ import annotations

import math
from typing import Any  # value() 各轨取值类型异质（镜头 tuple / 转场 float…），诚实标 Any


# ---- T7：缓动曲线库（6 族 × in/out/in_out = 18 条标准曲线 + 4 个基础名字）----
# 所有函数入参/出参均为 0~1 归一化进度；back 族是唯一会短暂过冲（<0 或 >1）的曲线族。
# 命名规则：ease_in_X / ease_out_X / ease_in_out_X，X 为曲线族（quad/cubic/quart/sine/expo/back）。

def _ease_in_quad(t: float) -> float:
    return t * t


def _ease_out_quad(t: float) -> float:
    return 1.0 - (1.0 - t) * (1.0 - t)


def _ease_in_out_quad(t: float) -> float:
    # 分段二次：前半加速、后半减速（不是 cos 近似——cos 版属 sine 族，会与 in_out_sine 撞车）
    return 2.0 * t * t if t < 0.5 else 1.0 - 2.0 * (1.0 - t) * (1.0 - t)


def _ease_in_cubic(t: float) -> float:
    return t * t * t


def _ease_out_cubic(t: float) -> float:
    t1 = 1.0 - t
    return 1.0 - t1 * t1 * t1


def _ease_in_out_cubic(t: float) -> float:
    return 4.0 * t * t * t if t < 0.5 else 1.0 - 4.0 * (1.0 - t) * (1.0 - t) * (1.0 - t)


def _ease_in_quart(t: float) -> float:
    return t * t * t * t


def _ease_out_quart(t: float) -> float:
    t1 = 1.0 - t
    return 1.0 - t1 * t1 * t1 * t1


def _ease_in_out_quart(t: float) -> float:
    return 8.0 * t * t * t * t if t < 0.5 else 1.0 - 8.0 * (1.0 - t) ** 4


def _ease_in_sine(t: float) -> float:
    return 1.0 - math.cos(t * math.pi * 0.5)


def _ease_out_sine(t: float) -> float:
    return math.sin(t * math.pi * 0.5)


def _ease_in_out_sine(t: float) -> float:
    return 0.5 - 0.5 * math.cos(math.pi * t)


def _ease_in_expo(t: float) -> float:
    return 0.0 if t == 0 else 2.0 ** (10.0 * t - 10.0)


def _ease_out_expo(t: float) -> float:
    return 1.0 if t == 1.0 else 1.0 - 2.0 ** (-10.0 * t)


def _ease_in_out_expo(t: float) -> float:
    if t == 0:
        return 0.0
    if t == 1.0:
        return 1.0
    return 0.5 * (2.0 ** (20.0 * t - 10.0) if t < 0.5 else 2.0 - 2.0 ** (-20.0 * t + 10.0))


def _ease_in_back(t: float) -> float:
    c1 = 1.70158
    c3 = c1 + 1.0
    return c3 * t * t * t - c1 * t * t


def _ease_out_back(t: float) -> float:
    c1 = 1.70158
    c3 = c1 + 1.0
    t1 = t - 1.0
    return 1.0 + c3 * t1 * t1 * t1 + c1 * t1 * t1


def _ease_in_out_back(t: float) -> float:
    # 标准 easeInOutBack：两端各过冲一次（先退回一点再冲过去），t=0/1 处严格取 0/1
    c1 = 1.70158
    c2 = c1 * 1.525
    if t < 0.5:
        return ((2.0 * t) ** 2 * ((c2 + 1.0) * 2.0 * t - c2)) / 2.0
    return (((2.0 * t - 2.0) ** 2 * ((c2 + 1.0) * (2.0 * t - 2.0) + c2)) + 2.0) / 2.0


EASINGS = {
    # 基础三档（向后兼容）
    "linear": lambda t: t,
    "ease_in": _ease_in_quad,        # 别名，等同 ease_in_quad
    "ease_out": _ease_out_quad,      # 别名，等同 ease_out_quad
    "none": lambda t: 1.0,           # 直达：不插值，直接取目标
    # 二次方（quadratic）
    "ease_in_quad": _ease_in_quad,
    "ease_out_quad": _ease_out_quad,
    "ease_in_out_quad": _ease_in_out_quad,
    # 三次方（cubic）
    "ease_in_cubic": _ease_in_cubic,
    "ease_out_cubic": _ease_out_cubic,
    "ease_in_out_cubic": _ease_in_out_cubic,
    # 四次方（quartic）
    "ease_in_quart": _ease_in_quart,
    "ease_out_quart": _ease_out_quart,
    "ease_in_out_quart": _ease_in_out_quart,
    # 正弦（sine）
    "ease_in_sine": _ease_in_sine,
    "ease_out_sine": _ease_out_sine,
    "ease_in_out_sine": _ease_in_out_sine,
    # 指数（exponential）
    "ease_in_expo": _ease_in_expo,
    "ease_out_expo": _ease_out_expo,
    "ease_in_out_expo": _ease_in_out_expo,
    # 回弹（back）
    "ease_in_back": _ease_in_back,
    "ease_out_back": _ease_out_back,
    "ease_in_out_back": _ease_in_out_back,
}
DEFAULT_EASING = "linear"


def _clamp01(value: float) -> float:
    """把进度钳到 0~1（负进度=还没开始，>1=已播完）。"""
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


class Track:
    """一条动画轨：从 t0 开始、持续 dur 毫秒，按 easing 缓动后交给 fn 取值。

    `fn` 为 None 时是 hold 轨（只计时不取值）；`loop=True` 时进度按 1 取余（循环动画）。
    `meta` 存调用方自定义信息（如镜头轨的 kind、转场轨的参数），本模块不解释其内容。
    """

    __slots__ = ("name", "t0", "dur", "fn", "easing", "loop", "meta")

    def __init__(self, name, t0, dur, fn=None, easing=DEFAULT_EASING, loop=False, meta=None):
        self.name = str(name)
        self.t0 = int(t0)
        self.dur = max(0.0, float(dur))
        self.fn = fn
        self.easing = easing if easing in EASINGS else DEFAULT_EASING
        self.loop = bool(loop)
        self.meta = dict(meta or {})

    def progress(self, now: int) -> float:
        """本帧归一化进度：未开始=0，播完=1；loop 轨按 1 取余后不会到 1。"""
        if self.dur <= 0:
            return 1.0
        raw = (now - self.t0) / self.dur
        if self.loop:
            return raw % 1.0 if raw > 0 else 0.0
        return _clamp01(raw)

    def done(self, now: int) -> bool:
        """是否已播完（loop 轨永远不算播完）。"""
        return (not self.loop) and (now - self.t0) >= self.dur

    def sample(self, now: int):
        """本帧取值：hold 轨返回 None，其余返回 fn(缓动后的进度)。"""
        if self.fn is None:
            return None
        return self.fn(EASINGS[self.easing](self.progress(now)))


class Timeline:
    """并行轨 + 独立时钟的调度器。所有时刻都是调用方传进来的毫秒数。"""

    def __init__(self):
        self._tracks: dict[str, Track] = {}
        self._values: dict[str, object] = {}   # 本帧各轨取值（tick 时刷新）
        self._clocks: dict[str, int] = {}      # 时钟名 -> 起点毫秒
        self._now = 0

    # ---- 挂轨 ----

    def play(self, name, dur_ms, fn=None, t0=0, easing=DEFAULT_EASING,
             loop=False, meta=None) -> Track:
        """挂一条动画轨（同名覆盖，旧轨直接丢弃）；返回新轨，便于取 meta/t0。"""
        track = Track(name, t0, dur_ms, fn=fn, easing=easing, loop=loop, meta=meta)
        self._tracks[track.name] = track
        self._values.pop(track.name, None)
        return track

    def hold(self, name, dur_ms, t0=0, meta=None) -> Track:
        """挂一条 hold 轨：只有时长，用来表达"这段内容要停留这么久"。"""
        return self.play(name, dur_ms, fn=None, t0=t0, meta=meta)

    def cancel(self, name) -> None:
        """丢掉一条轨及其本帧缓存值（播完/被打断时调用）。"""
        self._tracks.pop(name, None)
        self._values.pop(name, None)

    def clear(self) -> None:
        """清空全部轨（切场景/退出序幕时用）。"""
        self._tracks.clear()
        self._values.clear()

    # ---- 推进与查询 ----

    def tick(self, now: int) -> dict:
        """推进到 now：刷新每条轨的本帧取值并返回 {轨名: 值}。

        每帧每条轨的 fn 只调用一次——震动等含随机的取值函数依赖这一点。
        """
        self._now = int(now)
        for name, track in self._tracks.items():
            self._values[name] = track.sample(now)
        return dict(self._values)

    def has(self, name) -> bool:
        """是否存在该轨（不论是否播完）。"""
        return name in self._tracks

    def track(self, name):
        """取轨对象（查 meta/t0/dur）；不存在返回 None。"""
        return self._tracks.get(name)

    def names(self):
        """当前全部轨名（调试/测试用）。"""
        return list(self._tracks)

    def value(self, name, default=None) -> Any:
        """本帧 tick 计算出的取值；没有该轨返回 default。"""
        return self._values.get(name, default)

    def done(self, name, now=None) -> bool:
        """该轨是否已播完；没有该轨视为已完成（True）。"""
        track = self._tracks.get(name)
        if track is None:
            return True
        return track.done(self._now if now is None else now)

    def progress(self, name, now=None) -> float:
        """该轨当前进度 0~1；没有该轨返回 1.0（视为已完成）。"""
        track = self._tracks.get(name)
        if track is None:
            return 1.0
        return track.progress(self._now if now is None else now)

    # ---- 时钟（只记起点，不做插值）----

    def elapsed(self, name, now: int) -> int:
        """时钟 name 从首次调用至今的毫秒数（首次调用即起点，之后只读）。"""
        t0 = self._clocks.get(name)
        if t0 is None:
            t0 = self._clocks[name] = int(now)
        return int(now) - t0

    def reset_clock(self, name) -> None:
        """重置时钟起点（下一位调用 elapsed 时重新起算）。"""
        self._clocks.pop(name, None)
