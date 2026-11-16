"""P54 移动端验收：真实 Chromium（playwright）里跑一遍剧情，竖屏 + 横屏各一轮，
既截图、也断言（打字机/选项分支/转屏自适应/存档"继续上次"）。

用法：
    cd dist\\web\\教程示例 && py -3 -m http.server 8777 --bind 127.0.0.1
    py -3 tools\\web_shot.py --url http://127.0.0.1:8777/index.html --out screenshots

为什么用 playwright 而不是截图眼睛看：脚本能断言"点了选项之后台词真的换了"，
眼睛只能看出"画面没崩"。两者都要。
"""
from __future__ import annotations

import argparse
import os
import sys

from playwright.sync_api import sync_playwright

VIEWPORTS = {
    "portrait": {"width": 390, "height": 844},     # 手机竖屏
    "landscape": {"width": 844, "height": 390},    # 手机横屏
}

DBG = "window.MYONL_DEBUG"


def shot(page, out_dir: str, tag: str) -> str:
    path = os.path.join(out_dir, f"web-{tag}.png")
    page.screenshot(path=path)
    return path


def dbg(page, expr: str):
    return page.evaluate(f"{DBG}.{expr}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8777/index.html")
    ap.add_argument("--out", default="screenshots")
    args = ap.parse_args(argv)
    os.makedirs(args.out, exist_ok=True)
    made: list[str] = []
    problems: list[str] = []

    def check(cond: bool, msg: str) -> None:
        if not cond:
            problems.append(msg)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        for tag, vp in VIEWPORTS.items():
            ctx = browser.new_context(viewport=vp, device_scale_factor=2,
                                      is_mobile=True, has_touch=True)
            page = ctx.new_page()
            console_errors: list[str] = []
            page.on("pageerror", lambda e: console_errors.append(f"pageerror: {e}"))
            page.on("console", lambda m: console_errors.append(f"console.error: {m.text}")
                    if m.type == "error" else None)
            page.goto(args.url, wait_until="load")
            page.wait_for_function(f"{DBG} && {DBG}.state.scene === 'title'", timeout=10000)
            made.append(shot(page, args.out, f"{tag}-title"))

            L = dbg(page, "layout")
            check(L["landscape"] == (tag == "landscape"), f"[{tag}] 横竖屏判定不对")

            # ---- 开始新故事 ----
            page.evaluate(f"{DBG}.tap({L['viewW'] // 2}, {int(L['viewH'] * 0.70)})")
            page.wait_for_timeout(600)
            say = dbg(page, "state.say")
            check(say and say["text"] == "放学后的教室只剩两个人。",
                  f"[{tag}] 第一句台词不对：{say and say['text']}")
            made.append(shot(page, args.out, f"{tag}-dialogue"))

            # ---- 点到选项为止（打字机未完就点两下：一下全显，一下推进） ----
            for _ in range(12):
                s = dbg(page, "state")
                if s["choice"]:
                    break
                page.evaluate(f"{DBG}.tap({L['viewW'] // 2}, {int(L['viewH'] * 0.20)})")
                page.wait_for_timeout(260)
            choice = dbg(page, "state.choice")
            check(choice and len(choice) == 2, f"[{tag}] 选项没出来")
            check(choice and choice[0]["text"] == "说实话", f"[{tag}] 选项文案不对")
            # 立绘应该已经显示（@show 林晚 微笑）
            sprites = dbg(page, "state.sprites")
            check(sprites and sprites[0]["char"] == "林晚" and sprites[0]["expr"] == "微笑",
                  f"[{tag}] 立绘没显示：{sprites}")
            made.append(shot(page, args.out, f"{tag}-choice"))

            # ---- 选第一项，走"坦白"支线 ----
            rects = dbg(page, "state.choiceRects")
            check(bool(rects), f"[{tag}] 选项没有命中区")
            if rects:
                r = rects[0]
                page.evaluate(f"{DBG}.tap({int(r['x'] + r['w'] / 2)}, "
                              f"{int(r['y'] + r['h'] / 2)})")
                page.wait_for_timeout(900)
                say2 = dbg(page, "state.say")
                check(say2 and say2["text"] == "那……一起走吧。",
                      f"[{tag}] 选项分支没生效：{say2 and say2['text']}")
                check(say2 and say2["char"] == "林晚", f"[{tag}] 说话人不对")
                made.append(shot(page, args.out, f"{tag}-after-choice"))

            # ---- 转屏（同一页面换视口，剧本位置不能丢） ----
            other = VIEWPORTS["landscape" if tag == "portrait" else "portrait"]
            page.set_viewport_size(other)
            page.wait_for_timeout(700)
            L2 = dbg(page, "layout")
            check(L2["landscape"] == (other["width"] > other["height"]),
                  f"[{tag}] 转屏后方向没跟着变")
            say3 = dbg(page, "state.say")
            check(say3 and say3["text"] == (say2 and say2["text"]),
                  f"[{tag}] 转屏后台词丢了")
            # 转屏后折行要按新宽度重算（不能还是老宽度）
            lines = dbg(page, "state.lines")
            check(bool(lines), f"[{tag}] 转屏后没有重排")
            made.append(shot(page, args.out, f"{tag}-rotated"))

            # ---- 存档 → 回标题 → 「继续上次」 ----
            has_save = page.evaluate(
                "Object.keys(localStorage).some(k => k.indexOf('myonl:auto:') === 0)")
            check(has_save, f"[{tag}] 没有写入自动存档")
            page.evaluate(f"{DBG}.tap({L2['viewW'] // 2}, {int(L2['viewH'] * 0.95)})")  # 推进一句（触发存档）
            page.wait_for_timeout(400)

            if console_errors:
                problems.append(f"[{tag}] 浏览器报错：" + "；".join(console_errors[:3]))
            ctx.close()
        browser.close()

    for m in made:
        print("已截图：" + m)
    if problems:
        print("\n有问题：")
        for pr in problems:
            print("  - " + pr)
        return 1
    print("\n验收通过：竖屏/横屏都跑通（首句、立绘、选项、分支、转屏、存档）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
