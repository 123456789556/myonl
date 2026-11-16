"""双屏对比图：竖屏 390×844 + 横屏 844×390 并排，一眼看两个方向的排版。

用法：
    py -3 tools/mobile_dual.py            # 出编辑器 + 播放器各一张
    py -3 tools/mobile_dual.py editor     # 只出编辑器

前置：编辑器服务已起（py -3 -m engine.editor --port 8790 --script games\\教程示例\\script.gal）。
输出：screenshots/mobile-dual-editor.png / mobile-dual-player.png
"""
from __future__ import annotations

import io
import sys
import urllib.parse

from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import sync_playwright

root_dir = __file__.rsplit("\\", 1)[0] + "\\.."

BASE = "http://127.0.0.1:8790"
SHOT_DIR = root_dir + r"\screenshots"
PAD = 16
TOP = 46

PORTRAIT = (390, 844)
LANDSCAPE = (844, 390)


def _font(size: int):
    for name in (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\simhei.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def shot(browser, url: str, size, theme: str, *, after=None) -> Image.Image:
    page = browser.new_page(viewport={"width": size[0], "height": size[1]},
                            has_touch=True, device_scale_factor=1)
    page.add_init_script(
        "try{localStorage.setItem('gal_editor_theme','%s');"
        "localStorage.setItem('gal_welcome_done','1');"
        "sessionStorage.setItem('myonl:editing','1');}catch(e){}" % theme
    )
    page.goto(url, wait_until="load")
    page.wait_for_timeout(1500)
    if after:
        after(page)
        page.wait_for_timeout(900)
    raw = page.screenshot()
    page.close()
    return Image.open(io.BytesIO(raw)).convert("RGB")


def compose(name: str, left: Image.Image, right: Image.Image, theme: str):
    lw, lh = left.size
    rw, rh = right.size
    w = PAD * 3 + lw + rw
    h = TOP + PAD * 2 + max(lh, rh)
    canvas = Image.new("RGB", (w, h), (18, 18, 20) if theme == "dark" else (240, 240, 242))
    fg = (228, 230, 236) if theme == "dark" else (32, 34, 40)
    f = _font(17)
    d = ImageDraw.Draw(canvas)
    d.text((PAD, 14), f"竖屏  {lw}×{lh}", font=f, fill=fg)
    d.text((PAD * 2 + lw, 14), f"横屏  {rw}×{rh}", font=f, fill=fg)
    canvas.paste(left, (PAD, TOP + PAD))
    canvas.paste(right, (PAD * 2 + lw, TOP + PAD))
    # 两台"设备"各描一圈边框，别糊在底色上
    edge = (68, 70, 78) if theme == "dark" else (198, 200, 208)
    d.rectangle([PAD - 1, TOP + PAD - 1, PAD + lw, TOP + PAD + lh], outline=edge)
    d.rectangle([PAD * 2 + lw - 1, TOP + PAD - 1, PAD * 2 + lw + rw, TOP + PAD + rh], outline=edge)
    out = SHOT_DIR + "\\" + name
    canvas.save(out)
    print("saved", out, canvas.size)


def editor_shots(browser, theme="dark"):
    url = BASE + "/"
    left = shot(browser, url, PORTRAIT, theme)
    right = shot(browser, url, LANDSCAPE, theme)
    compose(f"mobile-dual-editor-{theme}.png", left, right, theme)


def player_shots(browser, theme="dark"):
    url = (BASE + "/single-file/" + urllib.parse.quote("教程示例") + ".html")

    def step(page):
        try:
            page.click("text=开始新故事", timeout=4000)
        except Exception:
            page.mouse.click(page.viewport_size["width"] / 2, page.viewport_size["height"] * 0.8)
        page.wait_for_timeout(700)
        for _ in range(4):
            page.mouse.click(page.viewport_size["width"] / 2,
                             page.viewport_size["height"] * 0.82)
            page.wait_for_timeout(420)

    left = shot(browser, url, PORTRAIT, theme, after=step)
    right = shot(browser, url, LANDSCAPE, theme, after=step)
    compose("mobile-dual-player.png", left, right, theme)


def main() -> int:
    which = sys.argv[1] if len(sys.argv) > 1 else "both"
    with sync_playwright() as p:
        b = p.chromium.launch()
        if which in ("both", "editor"):
            editor_shots(b, "dark")
            editor_shots(b, "light")
        if which in ("both", "player"):
            player_shots(b, "dark")
        b.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
