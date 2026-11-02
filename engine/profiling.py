"""迭代-01 任务2（八大方向 6.1）：轻量帧耗时 profiling，零依赖、默认关闭。

用法：`py -3 -m engine.demo 剧本.gal --profile [--auto] [--max-frames N]`，
主循环结束时打印每帧耗时分布（视图/渲染/输入/业务/帧总 + IO 子项）。

- demo 主循环按阶段 perf_counter 计时，经模块级单例 PROFILER 记录；
- 渲染层真实磁盘加载（图片/音效缓存未命中才发生）经 track_io() 上报为 IO 子项
  ——IO 是渲染/业务耗时的组成部分，单独列出便于观察缓存命中影响；
- 默认关闭：未启用时 add/measure/track_io 全部短路，开销可忽略；
- 同进程多次 demo.run（测试场景）由调用方负责 reset，互不污染。
"""
from __future__ import annotations

import math
import time
from contextlib import contextmanager

# 报告输出顺序（IO 恒最后，标注为子项）
_PHASE_ORDER = ("帧总", "视图", "渲染", "输入", "业务", "IO")


class FrameProfiler:
    """按阶段收集每帧毫秒样本，输出 count/total/mean/p50/p95/max。"""

    def __init__(self, enabled: bool = False) -> None:
        self.enabled = enabled
        self._samples: dict[str, list[float]] = {}

    def reset(self) -> None:
        self._samples = {}

    def add(self, phase: str, ms: float) -> None:
        if self.enabled:
            self._samples.setdefault(phase, []).append(ms)

    @contextmanager
    def measure(self, phase: str):
        """计时上下文；未启用时零记录直接透传。"""
        if not self.enabled:
            yield
            return
        t0 = time.perf_counter()
        try:
            yield
        finally:
            self.add(phase, (time.perf_counter() - t0) * 1000.0)

    @staticmethod
    def _pct(sorted_vals: list[float], q: float) -> float:
        """最近秩百分位：q ∈ (0, 1]。"""
        n = len(sorted_vals)
        idx = max(0, min(n - 1, int(math.ceil(q * n)) - 1))
        return sorted_vals[idx]

    def report(self, wall_ms: float | None = None, frames: int | None = None) -> str:
        """汇总文本。wall_ms/frames 由调用方给（循环墙钟与帧数），用于 FPS 行。"""
        lines = ["[profile] 每帧耗时分布（ms）"]
        if wall_ms is not None and frames is not None:
            fps = frames / (wall_ms / 1000.0) if wall_ms > 0 else 0.0
            mean = wall_ms / frames if frames else 0.0
            lines.append(f"  帧数 {frames} / 墙钟 {wall_ms:.0f} ms"
                         f"（{fps:.1f} FPS，均值 {mean:.2f} ms/帧）")
        for phase in _PHASE_ORDER:
            vals = self._samples.get(phase)
            if not vals:
                continue
            srt = sorted(vals)
            n = len(vals)
            tag = "（渲染/业务的子项）" if phase == "IO" else ""
            lines.append(
                f"  {phase}{tag}: 次数 {n} / 合计 {sum(vals):.1f}"
                f" / 均值 {sum(vals) / n:.2f} / p50 {self._pct(srt, 0.50):.2f}"
                f" / p95 {self._pct(srt, 0.95):.2f} / 最大 {srt[-1]:.1f}"
            )
        return "\n".join(lines)


# 模块级单例：渲染层（render_media）无需持有引用即可上报 IO。
PROFILER = FrameProfiler()


@contextmanager
def track_io():
    """真实读盘（缓存未命中）时计时上报 IO；未启用 profiling 时零开销。"""
    if not PROFILER.enabled:
        yield
        return
    t0 = time.perf_counter()
    try:
        yield
    finally:
        PROFILER.add("IO", (time.perf_counter() - t0) * 1000.0)
