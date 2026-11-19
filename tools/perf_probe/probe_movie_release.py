# -*- coding: utf-8 -*-
"""实测 3：真视频解码是否在切场景 / 离开后真正释放。

观测量（JS 侧可复现，不靠"看起来没了"）：
  - MYONL_DEBUG.video.movie.count  : 播放器复用池里活着的 <video> 句柄数
  - MYONL_DEBUG.video.movie.readyState / paused
  - document.querySelectorAll('video').length : DOM 里真实 <video> 节点数
  - performance.memory.usedJSHeapSize : heap 采样（进视频前 / 在视频中 / 切走后各采一次）
  - 切走后主动调一次 gc 不可用（无 --js-flags），改为强制两次空闲等待后再读数。

剧本流（work_movie/pack.html）：
  静态 → 进视频 → 切走(静态) → 再进视频 → 再切走。
每个稳定点采样一次；结论看"切走后 count 是否回 0、DOM video 是否 0、heap 是否回落"。

用法：
  python tools/perf_probe/probe_movie_release.py [--runs 3]
"""
from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from probe_common import WORK, heap_mb, launch_context, read_debug, write_json, FRAME_PROBE_JS

PACK = WORK / "work_movie" / "pack.html"

MATRIX = [
    ("desktop", "phone-portrait"),
    ("low-end-4x", "phone-portrait"),
]


def state_snapshot(page, label: str) -> dict:
    d = read_debug(page)
    heap = heap_mb(page)
    return {"label": label, "t": round(time.perf_counter() * 1000, 1),
            "heap": heap, "debug": d}


def advance_once(page) -> None:
    """翻一页：点一下。打字机未完这一下全显，再点才翻页；轮询到状态真正变了。"""
    before = page.evaluate("() => { const d = window.MYONL_DEBUG.state; return {say: d.say && d.say.text, video: d.video && d.video.name, ended: d.ended}; }")
    for _ in range(3):
        page.evaluate("() => window.MYONL_DEBUG.tap(540, 1200)")
        page.wait_for_timeout(180)
        after = page.evaluate("() => { const d = window.MYONL_DEBUG.state; return {say: d.say && d.say.text, video: d.video && d.video.name, ended: d.ended}; }")
        if after != before:
            return
    # 三次都没变：可能卡在全显/选项上，不再硬点


def run_once(pw, pkey: str, vkey: str) -> dict:
    browser, ctx, page, cdp = launch_context(pw, pkey, vkey, True)
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append("pageerror: " + str(e)))
    page.on("console", lambda m: errors.append("console.error: " + m.text)
            if m.type == "error" else None)
    page.add_init_script(FRAME_PROBE_JS)
    page.goto(PACK.as_uri(), wait_until="load")

    # 跳过首启向导 + 进游戏
    page.wait_for_function("() => window.MYONL_DEBUG && window.MYONL_DEBUG.state.scene === 'title'", timeout=10000)
    page.wait_for_timeout(300)
    rects = page.evaluate("() => window.MYONL_DEBUG.rects")
    skip = next((r for r in rects if r["id"] == "suSkip"), None)
    if skip:
        page.evaluate(f"() => window.MYONL_DEBUG.tap({skip['x'] + skip['w']/2}, {skip['y'] + skip['h']/2})")
        page.wait_for_timeout(300)
    page.evaluate("() => { const r = window.MYONL_DEBUG.state.startRect; if (r) window.MYONL_DEBUG.tap(r.x + r.w/2, r.y + r.h/2); else window.MYONL_DEBUG.tap(540, 1900); }")
    page.wait_for_timeout(400)
    if page.evaluate("() => window.MYONL_DEBUG.state.guide"):
        page.evaluate("() => window.MYONL_DEBUG.tap(540, 1200)")
        page.wait_for_timeout(200)

    snaps = []
    # 进入游戏时 next() 已把开场 bg/say/video 连续吃掉，初始即"第一次进视频"。
    # 先点一下回到开场静态，得到干净的"视频前"基线。
    advance_once(page)
    page.wait_for_timeout(1200)
    snaps.append(state_snapshot(page, "static-before"))

    # 第 1 次翻页：进第一次视频
    advance_once(page)
    page.wait_for_timeout(1500)   # 等解码起播
    snaps.append(state_snapshot(page, "movie-playing-1"))

    # 第 2 次翻页：切走，触发 releaseMovie
    advance_once(page)
    page.wait_for_timeout(1500)
    snaps.append(state_snapshot(page, "after-release-1"))

    # 第 3 次翻页：再进视频
    advance_once(page)
    page.wait_for_timeout(1500)
    snaps.append(state_snapshot(page, "movie-playing-2"))

    # 第 4 次翻页：再切走
    advance_once(page)
    page.wait_for_timeout(1500)
    snaps.append(state_snapshot(page, "after-release-2"))

    # 补充观测：releaseMovie 只去 src/load，DOM 节点被复用留着。
    # 这里直接读 DOM video 节点的 src/readyState，区分"句柄已释放"与"节点残留"。
    def dom_now():
        return page.evaluate("""() => {
          const els = [...document.querySelectorAll('video')];
          return els.map(e => ({hasSrcAttr: !!e.getAttribute('src'),
                                hasCurrentSrc: !!e.currentSrc,
                                readyState: e.readyState, paused: e.paused,
                                videoWidth: e.videoWidth}));
        }""")
    for s in snaps:
        s["domVideoEls"] = dom_now()

    result = {"profile": pkey, "viewport": vkey, "snaps": snaps, "errors": errors[:5]}
    browser.close()
    return result


def summarize(run: dict) -> dict:
    by = {s["label"]: s for s in run["snaps"]}
    def movie(label):
        d = by[label]["debug"]
        return d["video"]["movie"] if d else None
    def dom(label):
        d = by[label]["debug"]
        return d["domVideos"] if d else None
    def dom_els(label):
        return by[label].get("domVideoEls")
    def heap(label):
        return by[label]["heap"]
    out = {
        "profile": run["profile"],
        "playing1": movie("movie-playing-1"),
        "release1": movie("after-release-1"),
        "playing2": movie("movie-playing-2"),
        "release2": movie("after-release-2"),
        "domVideos": {k: dom(k) for k in by},
        "domVideoEls": {k: dom_els(k) for k in by},
        "heap": {k: heap(k) for k in by},
        "released1": movie("after-release-1") and movie("after-release-1")["count"] == 0,
        "released2": movie("after-release-2") and movie("after-release-2")["count"] == 0,
        # 句柄释放判据：count=0 且 DOM 节点无 src、readyState=0
        "srcCleared1": bool(dom_els("after-release-1")) and
                        all((not e["hasSrcAttr"]) and (not e["hasCurrentSrc"]) and e["readyState"] == 0
                            for e in dom_els("after-release-1")),
        "srcCleared2": bool(dom_els("after-release-2")) and
                        all((not e["hasSrcAttr"]) and (not e["hasCurrentSrc"]) and e["readyState"] == 0
                            for e in dom_els("after-release-2")),
        "errors": run["errors"],
    }
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--out", default=str(WORK / "results"))
    args = ap.parse_args()

    report: dict = {"runs": args.runs, "results": [], "summary": []}
    with sync_playwright() as pw:
        for pkey, vkey in MATRIX:
            runs = []
            for i in range(args.runs):
                r = run_once(pw, pkey, vkey)
                runs.append(r)
                s = summarize(r)
                print(f"[{pkey}] run{i+1}: playing1={s['playing1']} release1={s['release1']} "
                      f"srcCleared1={s['srcCleared1']} release2={s['release2']} "
                      f"srcCleared2={s['srcCleared2']} domEls={s['domVideoEls']}")
            report["results"].append(runs)
            report["summary"].append({
                "profile": pkey,
                "released1_runs": [summarize(r)["released1"] for r in runs],
                "released2_runs": [summarize(r)["released2"] for r in runs],
                "srcCleared1_runs": [summarize(r)["srcCleared1"] for r in runs],
                "srcCleared2_runs": [summarize(r)["srcCleared2"] for r in runs],
                "release1_movie": [summarize(r)["release1"] for r in runs],
                "domVideoEls": [summarize(r)["domVideoEls"] for r in runs],
                "heap": [summarize(r)["heap"] for r in runs],
            })

    write_json(Path(args.out) / "movie_release.json", report)
    print("\nwritten:", Path(args.out) / "movie_release.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
