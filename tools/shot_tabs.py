"""进作品后把五个页签逐页截下来，用来判断哪些页还是"相册式"交互。"""
import pathlib
import sys

from playwright.sync_api import sync_playwright

HTML = pathlib.Path(r"D:\娱乐工作区\myonl\MYONL引擎\dist\web\editor-single.html").resolve().as_uri()
OUT = pathlib.Path(r"D:\娱乐工作区\myonl\MYONL引擎\docs\images\preview")
OUT.mkdir(exist_ok=True)

# 一个带两幕、有选项的作品，光靠"拼素材"做不出来，正好用来测编排
PROJECT = """@bg 走廊
@show 林晚 calm
@music 放学

@ 放学后的教室只剩两个人。
@[林晚] 你还不走？

@choice:
    > 一起留下来 -> 留下
    > 先回家 -> 走

@label 留下
@bg 教室
@[林晚] 那我们写作业吧。
@jump 结尾

@label 走
@bg 街道
@ 你去了一趟便利店。
@jump 结尾

@label 结尾
@[林晚] 明天见。
@end
"""

TABS = [("script", "剧本"), ("assets", "素材"), ("look", "外观"),
        ("preview", "预览"), ("export", "导出")]

with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge", headless=True)
    for w, h in [(360, 800), (800, 360)]:
        pg = b.new_page(viewport={"width": w, "height": h}, has_touch=True, is_mobile=w < 900)
        pg.add_init_script(
            "localStorage.setItem('myonl:off:lib:v1', JSON.stringify({current:'p1',projects:[{name:'测试两幕',text:" + repr(PROJECT).replace("'", '"') + ",ctime:Date.now(),mtime:Date.now()}]}))"
        )
        pg.goto(HTML)
        pg.wait_for_timeout(1500)
        # 点进作品
        for sel in [".m-home-hero", ".m-home-card"]:
            el = pg.query_selector(sel)
            if el:
                el.click()
                break
        pg.wait_for_timeout(1200)
        # 按 data-tab 点，不用 text=：页面正文里到处都有「素材」「外观」这些词，
        # text= 会先撞上正文那一处，然后因为不可点而超时，看起来像页签坏了。
        for key, label in TABS:
            try:
                pg.click(f'.m-tab[data-tab="{key}"]', timeout=4000)
                pg.wait_for_timeout(900)
                pg.screenshot(path=str(OUT / f"tab-{label}-{w}x{h}.png"))
                print("ok", label, f"{w}x{h}")
            except Exception as e:
                print("skip", label, f"{w}x{h}", str(e)[:80])
        pg.close()
    b.close()
