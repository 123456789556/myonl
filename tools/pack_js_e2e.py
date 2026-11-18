# -*- coding: utf-8 -*-
"""JS 侧成品自检：用 parser.js + pack.js 造的单文件 HTML，真浏览器里能不能跑。

不测真机，只测 Chromium（和 APK 里的 WebView 同为 Blink 内核）。
检查：无 JS 异常、canvas 有尺寸、点得动、有文本渲染、无横向溢出。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML = ROOT / "dist" / "web" / "js-pack.html"

from playwright.sync_api import sync_playwright  # noqa: E402

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(("[ OK ] " if ok else "[FAIL] ") + name + (("  " + detail) if detail else ""))


def main():
    if not HTML.exists():
        print("[FAIL] 没有 dist/web/js-pack.html，先跑 node tools/_pack_build.js")
        return 1

    errors = []
    with sync_playwright() as p:
        br = p.chromium.launch()
        ctx = br.new_context(viewport={"width": 412, "height": 915},
                             device_scale_factor=2, has_touch=True)
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append("pageerror: " + str(e)))
        page.on("console", lambda m: errors.append("console.error: " + m.text)
                if m.type == "error" else None)
        page.goto(HTML.as_uri())
        page.wait_for_timeout(1200)

        pack = page.evaluate("() => window.__MYONL_PACK__ && window.__MYONL_PACK__.ins.length")
        check("pack 注入", pack == 348, "ins=" + str(pack))

        box = page.evaluate("""() => {
            const c = document.getElementById('game');
            if (!c) return null;
            const r = c.getBoundingClientRect();
            return {w: Math.round(r.width), h: Math.round(r.height)};
        }""")
        check("canvas 有尺寸", box and box["w"] > 100 and box["h"] > 100, json.dumps(box))

        # 点三下推进（标题页/开场白都要能过）
        for _ in range(4):
            page.mouse.click(206, 700)
            page.wait_for_timeout(420)

        shot = page.evaluate("""() => {
            const c = document.getElementById('game');
            const g = c.getContext('2d');
            const d = g.getImageData(0, 0, c.width, c.height).data;
            let nonBlack = 0, sampled = 0;
            for (let i = 0; i < d.length; i += 4 * 37) {
                sampled++;
                if (d[i] > 40 || d[i + 1] > 40 || d[i + 2] > 40) nonBlack++;
            }
            return {sampled: sampled, nonBlack: nonBlack};
        }""")
        check("画面不是全黑", shot["nonBlack"] > shot["sampled"] * 0.01, json.dumps(shot))

        overflow = page.evaluate("() => document.documentElement.scrollWidth - window.innerWidth")
        check("无横向溢出", overflow <= 0, "overflow=" + str(overflow))

        page.screenshot(path=str(ROOT / "dist" / "web" / "js-pack-shot.png"))
        check("零 JS 异常", len(errors) == 0, "; ".join(errors[:3]))
        br.close()

    bad = [r for r in results if not r[1]]
    print("\n%d/%d 通过" % (len(results) - len(bad), len(results)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
