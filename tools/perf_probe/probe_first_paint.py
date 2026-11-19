# -*- coding: utf-8 -*-
"""实测 1：首屏耗时（导航开始 → 首帧可交互）。

口径（与另两套脚本一致）：
  - t0 = 导航开始：performance.timeOrigin（页面导航起点）。
  - 首帧可交互：标题页画布已画出非黑像素，且 state.scene === 'title'、
    startRect 已算出（按钮可点），boot 遮罩已撤。
  - 每个 (profile, viewport, pack) 组合跑 N 次（默认 3），报中位 + 各次抖动。

用法：
  python tools/perf_probe/probe_first_paint.py [--runs 3] [--out tools/perf_probe/results]
"""
from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from probe_common import (WORK, VIEWPORTS, frame_summary, heap_mb, init_script,
                          launch_context, read_debug, write_json, FRAME_PROBE_JS)

ROOT = Path(__file__).resolve().parents[2]

PACKS = {
    "empty": WORK / "work_empty" / "pack.html",
    "img20": WORK / "work_img20" / "pack.html",
    "img60": WORK / "work_img60" / "pack.html",
    "img120": WORK / "work_img120" / "pack.html",
}

# 组合：低端档 × 手机竖屏为主；另加一组平板竖屏与桌面对照。
MATRIX = [
    ("desktop", "phone-portrait"),
    ("low-end-4x", "phone-portrait"),
    ("very-low-6x", "phone-portrait"),
    ("low-end-4x", "tablet-portrait"),
]


def measure_once(pw, profile_key: str, viewport_key: str, pack_path: Path,
                 headless: bool = True) -> dict:
    browser, ctx, page, cdp = launch_context(pw, profile_key, viewport_key, headless)
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append("pageerror: " + str(e)))
    page.on("console", lambda m: errors.append("console.error: " + m.text)
            if m.type == "error" else None)

    page.add_init_script(FRAME_PROBE_JS)
    nav_start = time.perf_counter()
    page.goto(pack_path.as_uri(), wait_until="load")

    # 首启向导（setup）盖在标题页上：startRect 在向导关掉前不算出来。
    # 可交互判据改为：scene=title、boot 已撤、画布有非黑像素、向导/引导任一已就绪。
    tti_ms = None
    deadline = time.perf_counter() + 20
    while time.perf_counter() < deadline:
        st = page.evaluate("""() => {
          const d = window.MYONL_DEBUG;
          if (!d) return null;
          const boot = document.getElementById('boot');
          const c = document.getElementById('game');
          let nb = 0;
          if (c) {
            try {
              const g = c.getContext('2d');
              const im = g.getImageData(0, 0, c.width, c.height).data;
              for (let i = 0; i < im.length; i += 4 * 97) {
                if (im[i] > 40 || im[i+1] > 40 || im[i+2] > 40) nb++;
              }
            } catch (e) {}
          }
          const ready = d.state.setup || d.state.startRect;
          return {scene: d.state.scene, ready: !!ready,
                  bootGone: !boot, nonBlack: nb, say: d.state.say && d.state.say.text};
        }""")
        if st and st["scene"] == "title" and st["ready"] and st["bootGone"] and st["nonBlack"] > 0:
            tti_ms = round((time.perf_counter() - nav_start) * 1000, 1)
            break
        page.wait_for_timeout(50)

    # 稳一下，取首屏后帧时间与内存
    page.wait_for_timeout(1200)
    frames = frame_summary(page)
    heap = heap_mb(page)
    debug = read_debug(page)
    result = {
        "tti_ms": tti_ms,
        "frames": frames,
        "heap": heap,
        "debug": debug,
        "errors": errors[:5],
        "ok": tti_ms is not None and not errors,
    }
    browser.close()
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--out", default=str(WORK / "results"))
    ap.add_argument("--pack", choices=list(PACKS.keys()), default=None)
    ap.add_argument("--headless", action="store_true", default=True)
    args = ap.parse_args()

    out_dir = Path(args.out)
    packs = [args.pack] if args.pack else list(PACKS.keys())
    report: dict = {"runs": args.runs, "matrix": MATRIX, "results": []}

    with sync_playwright() as pw:
        for pkey, vkey in MATRIX:
            for pack_name in packs:
                pack_path = PACKS[pack_name]
                if not pack_path.exists():
                    print(f"[skip] {pack_path} 不存在")
                    continue
                runs = []
                for i in range(args.runs):
                    r = measure_once(pw, pkey, vkey, pack_path, args.headless)
                    runs.append(r)
                    print(f"[{pkey}/{vkey}/{pack_name}] run{i+1}: tti={r['tti_ms']}ms "
                          f"heap={r['heap']} frames={r['frames']} err={len(r['errors'])}")
                ttis = [r["tti_ms"] for r in runs if r["tti_ms"] is not None]
                agg = {
                    "profile": pkey, "viewport": vkey, "pack": pack_name,
                    "tti_ms": {"runs": ttis, "median": statistics.median(ttis) if ttis else None,
                               "min": min(ttis) if ttis else None,
                               "max": max(ttis) if ttis else None},
                    "frames": [r["frames"] for r in runs],
                    "heap": [r["heap"] for r in runs],
                    "errors": [r["errors"] for r in runs],
                }
                report["results"].append(agg)

    write_json(out_dir / "first_paint.json", report)
    print("\nwritten:", out_dir / "first_paint.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
