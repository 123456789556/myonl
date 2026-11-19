"""验证「预览比例」这一项真的能在设置里找到、点了会变。"""
import pathlib
import sys

from playwright.sync_api import sync_playwright

HTML = pathlib.Path(r"D:\娱乐工作区\myonl\MYONL引擎\dist\web\editor-single.html").resolve().as_uri()
OUT = pathlib.Path(r"D:\娱乐工作区\myonl\MYONL引擎\docs\images\preview")

with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge", headless=True)
    pg = b.new_page(viewport={"width": 360, "height": 800}, has_touch=True, is_mobile=True)
    pg.goto(HTML)
    pg.wait_for_timeout(1500)

    # 首页「设置」入口（m-home-set 或文字）
    opened = False
    for sel in ["#mHomeSet", ".m-home-set", "text=设置"]:
        try:
            el = pg.query_selector(sel)
            if el:
                el.click()
                opened = True
                break
        except Exception:
            continue
    print("打开设置:", opened)
    pg.wait_for_timeout(600)

    row = pg.query_selector("#mSetRatio")
    print("有预览比例这一行:", bool(row))
    if row:
        print("三档:", [e.inner_text() for e in row.query_selector_all("button")])
        pg.click("#mSetRatio button[data-v='20:9']")
        pg.wait_for_timeout(300)
        pad = pg.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--sf-pad')")
        print("点 20:9 后 --sf-pad =", pad.strip())
        saved = pg.evaluate("localStorage.getItem('myonl_preview_ratio')")
        print("已存:", saved)
        pg.screenshot(path=str(OUT / "settings-ratio-360x800.png"))
        print("截图:", OUT / "settings-ratio-360x800.png")

    b.close()
