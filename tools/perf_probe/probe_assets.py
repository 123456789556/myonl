# -*- coding: utf-8 -*-
"""实测 2：素材量递增下的内存与帧时间，找明显掉帧拐点。

档位：20 / 60 / 120 张 1280x720 背景（dataURI），剧本逐张 @bg + 一句旁白。
流程：起浏览器 → 跳过首启向导 → 进游戏 → 逐句推进把背景一张张翻出来，
在稳定状态采样帧时间与内存（heap 位图 MB、DOM 图数、活跃 assets）。

每档每参数跑 3 次取中位；帧时间给 median / p95 / max / 超 50ms 帧数。
"""
from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from probe_common import (WORK, frame_summary, heap_mb, launch_context, read_debug,
                          write_json, FRAME_PROBE_JS)

PACKS = {
    20: WORK / "work_img20" / "pack.html",
    60: WORK / "work_img60" / "pack.html",
    120: WORK / "work_img120" / "pack.html",
}

MATRIX = [
    ("desktop", "phone-portrait"),
    ("low-end-4x", "phone-portrait"),
    ("very-low-6x", "phone-portrait"),
]


def skip_setup_and_enter(page) -> None:
    """点掉首启向导（suSkip），再点标题进游戏；游戏内引导点一下关掉。"""
    page.wait_for_function("() => window.MYONL_DEBUG && window.MYONL_DEBUG.state.scene === 'title'", timeout=10000)
    page.wait_for_timeout(300)
    # 向导：直接点「跳过」按钮；没向导就跳过这一步
    rects = page.evaluate("() => window.MYONL_DEBUG.rects")
    skip = next((r for r in rects if r["id"] == "suSkip"), None)
    if skip:
        page.evaluate(f"() => window.MYONL_DEBUG.tap({skip['x'] + skip['w']/2}, {skip['y'] + skip['h']/2})")
        page.wait_for_timeout(300)
    # 标题页 → 进游戏（startRect 或直接点画布中下部）
    page.evaluate("() => { const r = window.MYONL_DEBUG.state.startRect; if (r) window.MYONL_DEBUG.tap(r.x + r.w/2, r.y + r.h/2); else window.MYONL_DEBUG.tap(540, 1900); }")
    page.wait_for_timeout(400)
    # 游戏内引导：点一下关掉
    g = page.evaluate("() => window.MYONL_DEBUG.state.guide")
    if g:
        page.evaluate("() => window.MYONL_DEBUG.tap(540, 1200)")
        page.wait_for_timeout(200)


def advance_scene(page, taps: int) -> None:
    """逐句推进剧本，把背景一张张翻出来。"""
    for i in range(taps):
        # 打字机未完先全显，再翻页
        page.evaluate("() => { const d = window.MYONL_DEBUG; if (!d) return; d.tap(540, 1200); }")
        page.wait_for_timeout(120)
        page.evaluate("() => { const d = window.MYONL_DEBUG; if (!d) return; d.tap(540, 1200); }")
        page.wait_for_timeout(120)


def measure_once(pw, profile_key: str, viewport_key: str, pack_path: Path,
                 taps: int) -> dict:
    browser, ctx, page, cdp = launch_context(pw, profile_key, viewport_key, True)
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append("pageerror: " + str(e)))
    page.on("console", lambda m: errors.append("console.error: " + m.text)
            if m.type == "error" else None)
    page.add_init_script(FRAME_PROBE_JS)

    page.goto(pack_path.as_uri(), wait_until="load")
    skip_setup_and_enter(page)

    # 推进到素材基本铺开：每档 taps 张数 + 余量
    advance_scene(page, taps + 4)
    page.wait_for_timeout(800)

    frames = frame_summary(page)
    heap = heap_mb(page)
    debug = read_debug(page)
    result = {"frames": frames, "heap": heap, "debug": debug, "errors": errors[:5],
              "ok": not errors}
    browser.close()
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--out", default=str(WORK / "results"))
    ap.add_argument("--count", type=int, choices=[20, 60, 120], default=None)
    args = ap.parse_args()

    out_dir = Path(args.out)
    counts = [args.count] if args.count else [20, 60, 120]
    report: dict = {"runs": args.runs, "matrix": MATRIX, "results": []}

    with sync_playwright() as pw:
        for pkey, vkey in MATRIX:
            for n in counts:
                pack_path = PACKS[n]
                if not pack_path.exists():
                    print(f"[skip] {pack_path}")
                    continue
                runs = []
                for i in range(args.runs):
                    r = measure_once(pw, pkey, vkey, pack_path, n)
                    runs.append(r)
                    fr = r["frames"] or {}
                    print(f"[{pkey}/{vkey}/n={n}] run{i+1}: frames med={fr.get('median')} "
                          f"p95={fr.get('p95')} over50={fr.get('over50')} heap={r['heap']} "
                          f"assets={r['debug']['assets'] if r['debug'] else None} err={len(r['errors'])}")
                report["results"].append({
                    "profile": pkey, "viewport": vkey, "count": n,
                    "frames": [r["frames"] for r in runs],
                    "heap": [r["heap"] for r in runs],
                    "assets": [r["debug"]["assets"] if r["debug"] else None for r in runs],
                    "errors": [r["errors"] for r in runs],
                })

    write_json(out_dir / "assets_load.json", report)
    print("\nwritten:", out_dir / "assets_load.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
