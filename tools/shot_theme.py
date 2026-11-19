"""同一页分别按深色、浅色截图，用来对比配色与层次。"""
import pathlib

from playwright.sync_api import sync_playwright

HTML = pathlib.Path(r"D:\娱乐工作区\myonl\MYONL引擎\dist\web\editor-single.html").resolve().as_uri()
OUT = pathlib.Path(r"D:\娱乐工作区\myonl\MYONL引擎\docs\images\preview")

PROJECT = """@name 测试两幕
@bg 走廊
@show 林晚 calm center

放学后的教室只剩两个人。
[@林晚] 你还不走？

@choice
* 留下 | 一起留下来
* 走 | 先回家

=== 留下 ===
[@林晚] 那我们写作业吧
@jump 结尾

=== 结尾 ===
[@林晚] 明天见。
@end
"""

def inj(text):
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")

with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge", headless=True)
    for theme in ["dark", "light"]:
        pg = b.new_page(viewport={"width": 360, "height": 800}, has_touch=True, is_mobile=True)
        pg.add_init_script(
            'localStorage.setItem("myonl:off:lib:v1", JSON.stringify({current:"p1",'
            'projects:[{name:"测试两幕",text:"' + inj(PROJECT) + '",ctime:1,mtime:1}]}));'
            'localStorage.setItem("gal_editor_theme", "' + theme + '");'
        )
        pg.goto(HTML)
        pg.wait_for_timeout(1500)
        pg.screenshot(path=str(OUT / f"theme-{theme}-home.png"))
        el = pg.query_selector(".m-home-hero") or pg.query_selector(".m-home-card")
        if el:
            el.click()
        pg.wait_for_timeout(1200)
        pg.screenshot(path=str(OUT / f"theme-{theme}-inside.png"))
        # 设置抽屉
        try:
            pg.click("text=设置", timeout=3000)
            pg.wait_for_timeout(700)
            pg.screenshot(path=str(OUT / f"theme-{theme}-settings.png"))
        except Exception as e:
            print("settings skip", str(e)[:60])
        print(theme, "done")
        pg.close()
    b.close()
