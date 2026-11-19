"""截「场景列表」页，判断它现在是不是一堆同名卡片。"""
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
@bg 教室
[@林晚] 那我们写作业吧。
@jump 结尾

=== 走 ===
@bg 街道
你去了一趟便利店。
@jump 结尾

=== 结尾 ===
[@林晚] 明天见。
@end
"""

with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge", headless=True)
    for w, h in [(360, 800), (800, 360)]:
        pg = b.new_page(viewport={"width": w, "height": h}, has_touch=True, is_mobile=w < 900)
        j = PROJECT.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        pg.add_init_script(
            'localStorage.setItem("myonl:off:lib:v1", JSON.stringify({current:"p1",'
            'projects:[{name:"测试两幕",text:"' + j + '",ctime:' + str(1700000000000) + ',mtime:' + str(1700000000000) + '}]}))'
        )
        pg.goto(HTML)
        pg.wait_for_timeout(1500)
        el = pg.query_selector(".m-home-hero") or pg.query_selector(".m-home-card")
        if el:
            el.click()
        pg.wait_for_timeout(1200)
        # 场景列表按钮
        hit = False
        for sel in ["text=场景列表", "text=‹ 场景列表", "#btnSceneList"]:
            try:
                pg.click(sel, timeout=3000)
                hit = True
                break
            except Exception:
                continue
        print("打开场景列表:", hit, f"{w}x{h}")
        pg.wait_for_timeout(1200)
        pg.screenshot(path=str(OUT / f"scenelist-{w}x{h}.png"))
        pg.close()
    b.close()
