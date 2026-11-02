"""迭代-01 任务2（八大方向 6.1）：帧耗时 profiling。

FrameProfiler 统计数学 / 开关零开销 / track_io 上报 / demo --profile 端到端报告。
全部无头（dummy 视频驱动），saves/ 等相对路径由 fixture 隔离到 tmp_path。
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")  # 无头模式，须在 import pygame 前生效

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine import demo, profiling
from engine.profiling import PROFILER, FrameProfiler, track_io

pytestmark = [pytest.mark.integration]


@pytest.fixture(autouse=True)
def _clean_profiler(tmp_path, monkeypatch):
    """PROFILER 是模块级单例：用例前后都复位，且 saves/ 写入隔离到 tmp_path。"""
    monkeypatch.chdir(tmp_path)
    old = PROFILER.enabled
    PROFILER.enabled = False
    PROFILER.reset()
    yield
    PROFILER.enabled = old
    PROFILER.reset()


def test_disabled_profiler_records_nothing():
    p = FrameProfiler(enabled=False)
    p.add("渲染", 1.0)
    with p.measure("渲染"):
        pass
    assert p.report() == "[profile] 每帧耗时分布（ms）"  # 只有标题行


def test_stats_math():
    p = FrameProfiler(enabled=True)
    for i in range(1, 101):  # 1..100 ms
        p.add("渲染", float(i))
    out = p.report(wall_ms=5050.0, frames=100)
    assert "帧数 100 / 墙钟 5050 ms" in out
    assert "19.8 FPS" in out  # 100 帧 / 5.05s
    line = next(l for l in out.splitlines() if l.startswith("  渲染"))
    assert "次数 100" in line
    assert "合计 5050.0" in line
    assert "均值 50.50" in line
    assert "p50 50.00" in line   # 最近秩 ceil(0.5*100)=50
    assert "p95 95.00" in line   # 最近秩 ceil(0.95*100)=95
    assert "最大 100.0" in line


def test_measure_records_positive_and_respects_phase_order():
    p = FrameProfiler(enabled=True)
    with p.measure("输入"):
        pass
    with p.measure("视图"):
        pass
    out = p.report()
    phases = [l.split(":")[0].strip() for l in out.splitlines()[1:]]
    assert phases == ["视图", "输入"]  # 报告按固定阶段序，与记录先后无关


def test_track_io_reports_only_when_enabled():
    with track_io():
        pass
    assert "IO" not in PROFILER.report()  # 默认关闭不上报
    PROFILER.enabled = True
    with track_io():
        pass
    PROFILER.enabled = False
    line = next(l for l in PROFILER.report().splitlines() if l.startswith("  IO"))
    assert "次数 1" in line
    assert "子项" in line


_MINI_SCRIPT = """@character 林晚 #ffcccc
@ 林晚 第一句。
@ 林晚 第二句。
@end
"""


def test_demo_run_profile_prints_report(tmp_path, capsys):
    script = tmp_path / "a.gal"
    script.write_text(_MINI_SCRIPT, encoding="utf-8")
    demo.run(str(script), assets_root=str(tmp_path), max_frames=60, auto=True,
             profile=True)
    out = capsys.readouterr().out
    assert "[profile] 每帧耗时分布" in out
    for phase in ("帧总", "视图", "渲染", "输入", "业务"):
        assert f"\n  {phase}: 次数 " in out
    assert "FPS" in out
    assert PROFILER.enabled is False  # run 结束后复位，不污染同进程后续调用


def test_demo_run_without_profile_is_silent(tmp_path, capsys):
    script = tmp_path / "a.gal"
    script.write_text(_MINI_SCRIPT, encoding="utf-8")
    demo.run(str(script), assets_root=str(tmp_path), max_frames=30, auto=True)
    assert "[profile]" not in capsys.readouterr().out


def test_main_cli_profile_flag(tmp_path, capsys):
    script = tmp_path / "a.gal"
    script.write_text(_MINI_SCRIPT, encoding="utf-8")
    rc = demo.main([str(script), "--assets", str(tmp_path),
                    "--max-frames", "30", "--auto", "--profile"])
    assert rc == 0
    assert "[profile] 每帧耗时分布" in capsys.readouterr().out
