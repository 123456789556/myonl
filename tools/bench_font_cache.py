# -*- coding: utf-8 -*-
"""T8 字体缓存基准：同一段对话的绘制成本，缓存开 vs 关。

用法：
  py -3 tools/bench_font_cache.py                 # 默认 60 字长台词 / 200 轮 / 门槛 20%
  py -3 tools/bench_font_cache.py --rounds 500
  py -3 tools/bench_font_cache.py --mode frame    # 附加：整帧 demo 循环对照（看 60FPS 上限影响）

为什么不用整帧 FPS 当主指标：主循环 `clock.tick(60)` 在有头/无头下都会把空闲帧
睡到 16.7ms（实测占整帧 65%），只要绘制成本低于上限，FPS 恒为 60 —— 缓存收益被帧率上限完全掩盖。
所以主指标取「对话绘制耗时」：直接连续调用 Renderer._draw_dialog（面板 + 折行 + 富文本 +
角色名 + 提示字），这是对话框里所有文字相关开销的真实入口，缓存命中与否只影响这一层。
`--mode frame` 保留整帧对照，用伪造时钟绕开 tick 睡眠，用于交叉验证。

判定：对话绘制均值提升 < --min-gain（默认 20%）时退出码 1，可当验收门。
"""
from __future__ import annotations

import argparse
import contextlib
import io
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")  # 无头模式，须在 import pygame 前生效
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

from engine import demo  # noqa: E402
from engine.render_text import TextMixin  # noqa: E402
from engine.renderer import Renderer  # noqa: E402

TEXT = ("雨停在站台尽头，风把旧车票吹到手心。林晚抬头看我，说今晚的车比往常晚，"
        "我们就沿着铁轨慢慢走，走到灯都熄了再回去。")

HISTORY = [{"char": "林晚", "text": TEXT}]
CHARACTERS = {"林晚": {"color": "#aaccff", "kind": "default"}}


def _typed_lengths(total: int, step: int = 4) -> list[int]:
    """打字机过程取样：从 1 个字到整行，每隔 step 字取一帧。"""
    return list(range(1, total + 1, step)) + [total]


def _measure_dialog(rounds: int, text: str = TEXT) -> float:
    """连续绘制对话（含打字机多阶段前缀），返回平均每次耗时 ms。"""
    ren = Renderer((1280, 720), str(ROOT))
    lengths = _typed_lengths(len(text))
    try:
        ren._draw_dialog(HISTORY, CHARACTERS, False)  # 预热：字体/配置/资源缓存就绪
        t0 = time.perf_counter()
        for _ in range(rounds):
            for shown in lengths:
                ren._tw_text = text
                ren._tw_shown = float(shown)
                ren._draw_dialog(HISTORY, CHARACTERS, False)
        elapsed = time.perf_counter() - t0
    finally:
        ren.close()
    return elapsed * 1000.0 / (rounds * len(lengths))


def _measure_frame(max_frames: int) -> dict:
    """整帧对照：伪造 Clock（tick 返回 16ms 不睡眠），绕开 60FPS 上限只看 CPU。"""
    class _FakeClock:
        def tick(self, fps: int = 0) -> int:
            return 16

    original = pygame.time.Clock
    pygame.time.Clock = _FakeClock  # type: ignore[assignment]
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            demo.run(str(ROOT / "script.gal"), assets_root=str(ROOT),
                     max_frames=max_frames, auto=True, profile=True)
    finally:
        pygame.time.Clock = original  # type: ignore[assignment]
    out = buf.getvalue()
    result = {"raw": out}
    for line in out.splitlines():
        stripped = line.strip()
        if stripped.startswith("帧数"):
            result["frames"] = int(stripped.split()[1])
            result["mean"] = float(stripped.rsplit("均值", 1)[1].split("ms")[0])
        elif stripped.startswith("渲染:"):
            result["render"] = float(stripped.split("均值", 1)[1].split("/")[0])
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=200, help="每种打字阶段的重复轮数")
    ap.add_argument("--min-gain", type=float, default=20.0, help="对话绘制提升门槛（%%）")
    ap.add_argument("--mode", choices=("dialog", "frame", "both"), default="dialog")
    ap.add_argument("--frames", type=int, default=600, help="--mode frame 的帧数上限")
    args = ap.parse_args()

    original = TextMixin._cached_font_surface

    def _uncached(self, font, text, antialias, color):
        return font.render(text, antialias, color)

    gain = 0.0
    original_width = TextMixin._font_width

    def _uncached_width(self, font, text):
        return font.size(text)[0]

    def _disable_font_caches():
        TextMixin._cached_font_surface = _uncached
        TextMixin._font_width = _uncached_width

    def _restore_font_caches():
        TextMixin._cached_font_surface = original
        TextMixin._font_width = original_width

    if args.mode in ("dialog", "both"):
        _disable_font_caches()
        try:
            off_ms = _measure_dialog(args.rounds)
        finally:
            _restore_font_caches()
        on_ms = _measure_dialog(args.rounds)
        gain = (off_ms - on_ms) / off_ms * 100.0
        print(f"对话绘制（{len(_typed_lengths(len(TEXT)))} 个打字阶段 × {args.rounds} 轮，"
              f"无头 dummy，1280×720）")
        print(f"  字体缓存关：{off_ms:.3f} ms/次")
        print(f"  字体缓存开：{on_ms:.3f} ms/次")
        print(f"  提升：{gain:+.1f}%（门槛 {args.min_gain:.0f}%）")

    if args.mode in ("frame", "both"):
        print("\n整帧对照（伪造时钟绕开 60FPS 上限，纯 CPU）")
        _disable_font_caches()
        try:
            off = _measure_frame(args.frames)
        finally:
            _restore_font_caches()
        on = _measure_frame(args.frames)
        print(f"  缓存关：{off.get('mean', 0):.2f} ms/帧（{off.get('frames', 0)} 帧）")
        print(f"  缓存开：{on.get('mean', 0):.2f} ms/帧（{on.get('frames', 0)} 帧）")

    if args.mode == "dialog":
        if gain < args.min_gain:
            print(f"未过门槛：对话绘制提升 {gain:.1f}% < {args.min_gain:.0f}%")
            return 1
        print("通过：字体缓存收益达到验收门槛")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
