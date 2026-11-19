"""注入一个本地作品，真点进去截图——用来检查「场景编辑」这类只有进作品才看得见的界面。

用法：
    D:\\Python313\\python.exe tools/shot_flow.py dist/web/editor-single.html --tag scene
输出：
    docs/images/preview/<tag>-home-<w>x<h>.png
    docs/images/preview/<tag>-inside-<w>x<h>.png
"""
import argparse
import json
import pathlib
import sys

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
LIB_KEY = "myonl:off:lib:v1"

SIZES = [
    ("手机竖", 360, 800),
    ("手机横", 800, 360),
]


def seed_lib():
    return {
        "current": "我的第一个游戏",
        "projects": [
            {
                "name": "我的第一个游戏",
                "text": "@bg 走廊\n@ hello world!\n",
                "ctime": 1763500000,
                "mtime": 1763500000,
            }
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("target")
    ap.add_argument("--tag", default="flow")
    args = ap.parse_args()

    page_path = pathlib.Path(args.target)
    if not page_path.is_absolute():
        page_path = ROOT / page_path
    if not page_path.is_file():
        print(f"找不到 {page_path}", file=sys.stderr)
        return 2

    out_dir = ROOT / "docs" / "images" / "preview"
    out_dir.mkdir(parents=True, exist_ok=True)
    url = page_path.resolve().as_uri()
    seed = "localStorage.setItem(%s, %s);" % (
        json.dumps(LIB_KEY),
        json.dumps(json.dumps(seed_lib(), ensure_ascii=False)),
    )

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        for label, w, h in SIZES:
            page = browser.new_page(viewport={"width": w, "height": h}, has_touch=True,
                                    is_mobile=w < 900)
            page.add_init_script(seed)
            page.goto(url, wait_until="load")
            page.wait_for_timeout(1200)
            home = out_dir / f"{args.tag}-home-{w}x{h}.png"
            page.screenshot(path=str(home))
            print(f"{label} 首页  {home.relative_to(ROOT)}")

            clicked = False
            for sel in (".m-home-hero", ".m-home-card"):
                if page.locator(sel).count():
                    page.locator(sel).first.click()
                    clicked = True
                    break
            page.wait_for_timeout(1500)
            inside = out_dir / f"{args.tag}-inside-{w}x{h}.png"
            page.screenshot(path=str(inside))
            print(f"{label} 作品内{'（已点进）' if clicked else '（没找到可点的卡片）'}  {inside.relative_to(ROOT)}")
            page.close()
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
