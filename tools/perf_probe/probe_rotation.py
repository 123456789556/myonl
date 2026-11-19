# -*- coding: utf-8 -*-
"""实测 4：横竖屏切换时帧序列视频 t0 是否重置、进度是否跳变。

现象（技术债）：转屏只触发 fit() 重排，没重设 state.video.t0；帧序列用
(performance.now() - t0) 推算帧号，转屏期间经过的真实时间被算进帧号，画面跳到随机帧。

口径：
  - 进帧序列视频后，记录帧号 frameIdx（debug.video.frameIdx）；
  - 改 viewport 横竖互换触发 resize/orientationchange，等重排完成；
  - 再读 frameIdx，对比转屏前后差值：正常应 ≈ 转屏期间自然推进的帧数（小增量），
    不发生回绕/大跳变。真视频（file=）不在本脚本范围，其时钟由 <video> 自己维护。

用法：
  python tools/perf_probe/probe_rotation.py [--runs 3]
"""
from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from probe_common import WORK, launch_context, read_debug, write_json, FRAME_PROBE_JS

PACK = WORK / "work_movie" / "pack.html"


def enter_frame_seq(page) -> None:
    page.wait_for_function("() => window.MYONL_DEBUG && window.MYONL_DEBUG.state.scene === 'title'", timeout=10000)
    page.wait_for_timeout(300)
    rects = page.evaluate("() => window.MYONL_DEBUG.rects")
    skip = next((r for r in rects if r["id"] == "suSkip"), None)
    if skip:
        page.evaluate(f"() => window.MYONL_DEBUG.tap({skip['x']+skip['w']/2}, {skip['y']+skip['h']/2})")
        page.wait_for_timeout(300)
    page.evaluate("() => { const r = window.MYONL_DEBUG.state.startRect; if (r) window.MYONL_DEBUG.tap(r.x+r.w/2, r.y+r.h/2); else window.MYONL_DEBUG.tap(540,1900); }")
    page.wait_for_timeout(400)
    if page.evaluate("() => window.MYONL_DEBUG.state.guide"):
        page.evaluate("() => window.MYONL_DEBUG.tap(540,1200)"); page.wait_for_timeout(200)


def tap_once(page) -> None:
    before = page.evaluate("() => { const s = window.MYONL_DEBUG.state; return {say: s.say&&s.say.text, video: s.video&&s.video.name}; }")
    for _ in range(3):
        page.evaluate("() => window.MYONL_DEBUG.tap(540,1200)")
        page.wait_for_timeout(220)
        after = page.evaluate("() => { const s = window.MYONL_DEBUG.state; return {say: s.say&&s.say.text, video: s.video&&s.video.name}; }")
        if after != before:
            return


def frame_idx(page):
    d = read_debug(page)
    return d["video"].get("frameIdx") if d and d.get("video") else None


def video_t0(page):
    return page.evaluate("() => { const s = window.MYONL_DEBUG.state.video; return s ? s.t0 : null; }")


def internal_state(page):
    """基线版调试口不暴露 state.video；读不到就返回 None，报告里标测不出。"""
    return page.evaluate("() => { const s = window.MYONL_DEBUG.state; return s && s.video ? s.video : null; }")


def read_canvas_frame(page):
    """从画布当前贴出的帧号反推（帧序列每帧是渐变纯色，读中心像素）。
    基线版读不到内部 t0 时用这个做旁证；返回像素三元组或 None。"""
    return page.evaluate("""() => {
      const c = document.querySelector('canvas');
      if (!c) return null;
      const ctx = c.getContext('2d');
      const x = Math.floor(c.width/2), y = Math.floor(c.height/2);
      const d = ctx.getImageData(x, y, 1, 1).data;
      return [d[0], d[1], d[2]];
    }""")
    """基线版调试口不暴露 state.video；读不到就返回 None，报告里标测不出。"""
    return page.evaluate("() => { const s = window.MYONL_DEBUG.state; return s && s.video ? s.video : null; }")


def run_once(pw, pkey: str) -> dict:
    browser, ctx, page, cdp = launch_context(pw, pkey, "phone-portrait", True)
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append("pageerror: " + str(e)))
    page.add_init_script(FRAME_PROBE_JS)
    page.goto(PACK.as_uri(), wait_until="load")
    enter_frame_seq(page)

    # 进游戏初始就在帧序列视频（startGame 的 next() 已把开场连续指令吃掉）。
    # 直接读当前段；若被向导/引导带到别处，再逐页找回来。
    for _ in range(6):
        cur = read_debug(page)
        v = cur["video"] if cur else None
        print("  loop:", v and {"name": v["name"], "file": v["file"], "say": cur["say"]})
        if v and v["name"] and not v["file"]:
            break
        tap_once(page)
        page.wait_for_timeout(600)
    page.wait_for_timeout(1200)
    v_before = read_debug(page)
    idx_before = v_before["video"].get("frameIdx") if v_before and v_before.get("video") else None
    t0_before = video_t0(page)
    px_before = read_canvas_frame(page)
    print("  before:", v_before["video"] if v_before else None)

    # 转屏：竖 → 横。headless 下 set_viewport_size 偶发被窗口最大化状态卡住，
    # 失败就回退到只派发 resize/orientationchange 事件（播放器监听的就是这两个）。
    def rotate(w, h):
        # 先派发 resize/orientationchange（播放器监听的就是这两个），再尝试改视口。
        page.evaluate("() => { window.dispatchEvent(new Event('resize')); "
                       "window.dispatchEvent(new Event('orientationchange')); }")
        try:
            page.set_viewport_size({"width": w, "height": h})
        except Exception as e:
            print("  viewport resize 失败，仅事件派发:", str(e)[:60])
        page.wait_for_timeout(700)

    def force_fit(w, h):
        # headless 下窗口尺寸改不动（setWindowBounds 报错），innerWidth/Height 不变，
        # fit() 按窗口尺寸算出的方向翻不回去；用 CDP 覆盖视口尺寸强制重算一次。
        try:
            cdp.send("Emulation.setDeviceMetricsOverride",
                     {"width": w, "height": h, "deviceScaleFactor": 1, "mobile": True})
            page.evaluate("() => window.dispatchEvent(new Event('orientationchange'))")
            page.evaluate("() => window.dispatchEvent(new Event('resize'))")
        except Exception:
            pass
        page.wait_for_timeout(400)

    rotate(915, 412)
    force_fit(915, 412)
    v_after_land = read_debug(page)
    idx_after_land = v_after_land["video"].get("frameIdx") if v_after_land and v_after_land.get("video") else None
    t0_after_land = video_t0(page)

    # 再转回竖
    rotate(412, 915)
    force_fit(412, 915)
    v_after_port = read_debug(page)
    idx_after_port = v_after_port["video"].get("frameIdx") if v_after_port and v_after_port.get("video") else None
    t0_after_port = video_t0(page)

    res = {
        "profile": pkey,
        "canvasPx": {"before": px_before,
                      "landscape": read_canvas_frame(page),
                      "portrait_again": read_canvas_frame(page)},
        "before": {"frameIdx": idx_before, "t0": t0_before,
                    "video": v_before["video"] if v_before else None,
                    "layout": v_before["layout"] if v_before else None},
        "landscape": {"frameIdx": idx_after_land, "t0": t0_after_land,
                       "video": v_after_land["video"] if v_after_land else None,
                       "layout": v_after_land["layout"] if v_after_land else None},
        "portrait_again": {"frameIdx": idx_after_port, "t0": t0_after_port,
                            "video": v_after_port["video"] if v_after_port else None,
                            "layout": v_after_port["layout"] if v_after_port else None},
        "errors": errors[:5],
    }
    browser.close()
    return res

def wrap_delta(a: int, b: int, length: int) -> int:
    """环形帧号差值 b - a，取最近方向。"""
    d = (b - a) % length
    if d > length // 2:
        d -= length
    return d


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--out", default=str(WORK / "results"))
    args = ap.parse_args()

    report: dict = {"runs": args.runs, "results": []}
    with sync_playwright() as pw:
        for pkey in ["desktop", "low-end-4x"]:
            runs = []
            for i in range(args.runs):
                r = run_once(pw, pkey)
                runs.append(r)
                print(f"[{pkey}] run{i+1}: before={r['before']['frameIdx']} "
                      f"land={r['landscape']['frameIdx']} back={r['portrait_again']['frameIdx']} "
                      f"t0changed={r['before']['t0'] != r['landscape']['t0']}")
            # 帧序列长度从 before.video.len 取
            length = (runs[0]["before"]["video"] or {}).get("len") or 12
            deltas = []
            for r in runs:
                b = r["before"]["frameIdx"]; l = r["landscape"]["frameIdx"]
                p = r["portrait_again"]["frameIdx"]
                if b is not None and l is not None:
                    deltas.append({"before_land": wrap_delta(b, l, length),
                                    "land_back": wrap_delta(l, p, length) if p is not None else None})
            # 布局是否真的翻到横屏（layout.landscape）；视口改不动时记下来
            layouts = [{"before": r["before"]["layout"], "land": r["landscape"]["layout"],
                        "back": r["portrait_again"]["layout"]} for r in runs]
            report["results"].append({"profile": pkey, "runs": runs, "deltas": deltas,
                                       "length": length, "layouts": layouts})

    write_json(Path(args.out) / "rotation_t0.json", report)
    print("\nwritten:", Path(args.out) / "rotation_t0.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
