"""多尺寸真机截图：改完界面先看这个，别靠想象。

用法：
    D:\\Python313\\python.exe tools/shot_screens.py dist/web/editor-single.html
    D:\\Python313\\python.exe tools/shot_screens.py some/game.html --tag game

输出：docs/images/preview/<tag>-<宽>x<高>.png，以及一张拼图 <tag>-grid.png。
浏览器用本机 Edge（playwright 的 chromium 未下载，但 channel=msedge 可用）。
"""
import argparse
import pathlib
import sys

from playwright.sync_api import sync_playwright

SIZES = [
    # 手机竖：20:9 —— 对齐用户真机 1080x2400（CSS 360x800，dpr 3）
    ("手机竖", 360, 800),
    # iPhone 13/14 逻辑分辨率（19.5:9）：刘海 + 安全区的典型情况
    ("苹果竖", 390, 844),
    # Pixel 7（20:9，稍宽）：安卓中端常见
    ("安卓宽竖", 412, 915),
    # 16:9 老安卓机：还没被淘汰的那批
    ("老机竖", 360, 640),
    ("手机横", 800, 360),
    # 平板
    ("平板竖", 768, 1024),
    ("平板横", 1024, 768),
]

ROOT = pathlib.Path(__file__).resolve().parent.parent


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("target", help="要截的 html 路径（相对仓库根或绝对路径）")
    ap.add_argument("--tag", default=None, help="文件名前缀，默认取 html 主名")
    ap.add_argument("--wait", type=float, default=1.2, help="每页加载后等待秒数")
    ap.add_argument("--scale", type=float, default=1.0, help="像素密度")
    args = ap.parse_args()

    page_path = pathlib.Path(args.target)
    if not page_path.is_absolute():
        page_path = ROOT / page_path
    if not page_path.is_file():
        print(f"找不到 {page_path}", file=sys.stderr)
        return 2

    tag = args.tag or page_path.stem
    out_dir = ROOT / "docs" / "images" / "preview"
    out_dir.mkdir(parents=True, exist_ok=True)

    url = page_path.resolve().as_uri()
    made = []

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        for label, w, h in SIZES:
            page = browser.new_page(
                viewport={"width": w, "height": h},
                device_scale_factor=args.scale,
                has_touch=True,
                is_mobile=w < 900,
            )
            page.goto(url, wait_until="load")
            page.wait_for_timeout(int(args.wait * 1000))
            out = out_dir / f"{tag}-{w}x{h}.png"
            page.screenshot(path=str(out))
            made.append((label, w, h, out))
            page.close()
        browser.close()

    for label, w, h, out in made:
        print(f"{label:4s} {w}x{h}  {out.relative_to(ROOT)}  {out.stat().st_size} bytes")

    # 拼一张对比图，方便一次看完
    try:
        from PIL import Image, ImageDraw

        pad, cap = 16, 26
        cols = 4
        cell_w = max(im.width for _, _, _, im_path in made for im in [Image.open(im_path)]) if False else None
        imgs = [(label, w, h, Image.open(out)) for label, w, h, out in made]
        cell_w = max(im.width for _, _, _, im in imgs)
        cell_h = max(im.height for _, _, _, im in imgs)
        canvas = Image.new("RGB", (cols * (cell_w + pad) + pad, cell_h + cap + pad * 2), (11, 16, 32))
        draw = ImageDraw.Draw(canvas)
        for i, (label, w, h, im) in enumerate(imgs):
            x = pad + i * (cell_w + pad)
            y = pad + cap
            canvas.paste(im, (x, y))
            draw.text((x, pad + 6), f"{label} {w}x{h}", fill=(200, 210, 230))
        grid = out_dir / f"{tag}-grid.png"
        canvas.save(grid)
        print(f"拼图 {grid.relative_to(ROOT)}  {grid.stat().st_size} bytes")
    except Exception as e:  # 拼图失败不影响单张
        print(f"拼图跳过：{type(e).__name__}: {e}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
