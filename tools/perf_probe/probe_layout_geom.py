# -*- coding: utf-8 -*-
"""W-1 宽屏双栏几何核验（真 Chromium）。

在三档尺寸下进游戏，读 MYONL_DEBUG 的 layout 栏位参数 + panel 矩形 + 选项矩形，
校验：
  - 横屏平板（1280×800 / 1024×600）wide=true：对话栏与立绘栏 x 区间不重叠，
    三块都不出界（0 ≤ x, x+w ≤ viewW）；选项栏与对话栏同列。
  - 竖屏（800×1280）wide=false：退回整幅居中几何。

不依赖像素肉眼判读，矩形全部来自调试口真实计算结果。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from probe_common import WORK, launch_context

PACK = WORK / "work_empty" / "pack.html"

CASES = [
    ("tablet-landscape-1280x800", 1280, 800),
    ("tablet-landscape-1024x600", 1024, 600),
    ("tablet-portrait-800x1280", 800, 1280),
]


def enter(page):
    page.wait_for_function("() => window.MYONL_DEBUG && window.MYONL_DEBUG.state.scene === 'title'",
                           timeout=10000)
    page.wait_for_timeout(300)
    rects = page.evaluate("() => window.MYONL_DEBUG.rects")
    skip = next((r for r in rects if r["id"] == "suSkip"), None)
    if skip:
        page.evaluate(f"() => window.MYONL_DEBUG.tap({skip['x']+skip['w']/2}, {skip['y']+skip['h']/2})")
        page.wait_for_timeout(300)
    page.evaluate("() => { const r = window.MYONL_DEBUG.state.startRect; if (r) window.MYONL_DEBUG.tap(r.x+r.w/2, r.y+r.h/2); else window.MYONL_DEBUG.tap(540,1900); }")
    page.wait_for_timeout(400)
    if page.evaluate("() => window.MYONL_DEBUG.state.guide"):
        page.evaluate("() => window.MYONL_DEBUG.tap(540,1200)")
        page.wait_for_timeout(200)


def read_geom(page):
    return page.evaluate("""() => {
      const d = window.MYONL_DEBUG;
      const L = d.layout;
      const panel = d.panel;
      const choices = (d.state.choiceRects || []).slice();
      return {viewW: L.viewW, viewH: L.viewH, landscape: L.landscape, wide: L.wide,
              spriteColX: L.spriteColX, spriteColW: L.spriteColW,
              dialogColX: L.dialogColX, dialogColW: L.dialogColW,
              choiceColX: L.choiceColX, choiceColW: L.choiceColW,
              panel: panel, choices: choices};
    }""")


def check(name, w, h, g):
    errs = []
    vw, vh = g["viewW"], g["viewH"]
    # 出界校验
    for k, box in [("panel", g["panel"]), ("sprite", {"x": g["spriteColX"], "w": g["spriteColW"]}),
                   ("dialog", {"x": g["dialogColX"], "w": g["dialogColW"]}),
                   ("choice", {"x": g["choiceColX"], "w": g["choiceColW"]})]:
        if box is None:
            continue
        x, bw = box["x"], box["w"]
        if x < -1 or x + bw > vw + 1:
            errs.append(f"{k} 出界: x={x} w={bw} viewW={vw}")
    if g["wide"]:
        # 对话栏与立绘栏不重叠：dialog 右缘 ≤ sprite 左缘（留 2px 缝）
        dr = g["dialogColX"] + g["dialogColW"]
        sl = g["spriteColX"]
        if dr > sl + 2:
            errs.append(f"对话栏与立绘栏重叠: dialog 右缘={dr} > sprite 左缘={sl}")
        if g["choiceColX"] != g["dialogColX"]:
            errs.append(f"选项列左缘 {g['choiceColX']} != 对话列 {g['dialogColX']}")
    else:
        # 非宽屏：立绘栏占整幅
        if g["spriteColX"] != 0 or g["spriteColW"] != vw:
            errs.append(f"非宽屏立绘栏未整幅: x={g['spriteColX']} w={g['spriteColW']} viewW={vw}")
    return errs


def main():
    report = []
    with sync_playwright() as pw:
        for name, w, h in CASES:
            browser, ctx, page, cdp = launch_context(pw, "desktop", "phone-portrait", True)
            # 用 CDP 覆盖到目标尺寸（headless set_viewport 不稳，见 probe_rotation 注）
            cdp.send("Emulation.setDeviceMetricsOverride",
                     {"width": w, "height": h, "deviceScaleFactor": 1, "mobile": True})
            page.evaluate("() => { window.dispatchEvent(new Event('orientationchange')); "
                          "window.dispatchEvent(new Event('resize')); }")
            page.goto(PACK.as_uri(), wait_until="load")
            enter(page)
            page.wait_for_timeout(600)
            g = read_geom(page)
            errs = check(name, w, h, g)
            report.append({"case": name, "viewport": [w, h], "geom": g, "errors": errs})
            print(f"[{name}] {w}x{h} wide={g['wide']} landscape={g['landscape']} "
                  f"panel=({g['panel']['x']},{g['panel']['y']},{g['panel']['w']},{g['panel']['h']}) "
                  f"dialog=({g['dialogColX']},{g['dialogColW']}) sprite=({g['spriteColX']},{g['spriteColW']}) "
                  f"choice=({g['choiceColX']},{g['choiceColW']}) errors={errs}")
            browser.close()
    out = WORK / "results" / "layout_geom.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    bad = [r for r in report if r["errors"]]
    print("\nwritten:", out, "| 不通过:", len(bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
