"""把竖屏/横屏两张截图装进手机框，拼成一块可看的设计底板。

用法：
    D:\\Python313\\python.exe tools/make_board.py docs/images/preview/scene-fix2-inside-360x800.png docs/images/preview/scene-fix2-inside-800x360.png --out docs/images/preview/board-scene.png

两个框都按真机 20:9 比例（1080x2400 竖 / 2400x1080 横）标注。
"""
import argparse
import pathlib

from PIL import Image, ImageDraw, ImageFont

ROOT = pathlib.Path(__file__).resolve().parent.parent

BG = (11, 16, 32)
CARD = (20, 26, 44)
LINE = (56, 68, 96)
BLUE = (79, 140, 255)
TEXT = (214, 222, 240)
SUB = (128, 140, 168)


def font(size):
    for name in ("msyh.ttc", "msyhbd.ttc", "simhei.ttf"):
        try:
            return ImageFont.truetype(f"C:/Windows/Fonts/{name}", size)
        except Exception:
            continue
    return ImageFont.load_default()


def phone_frame(img, scale, label, ratio):
    """把截图贴进圆角手机框，返回 (画布, 框宽, 框高)。"""
    w = int(img.width * scale)
    h = int(img.height * scale)
    pad = 18
    canvas = Image.new("RGB", (w + pad * 2, h + pad * 2 + 40), BG)
    d = ImageDraw.Draw(canvas)

    # 外框
    d.rounded_rectangle(
        [0, 0, canvas.width - 1, canvas.height - 41],
        radius=28, fill=CARD, outline=LINE, width=2,
    )
    shot = img.resize((w, h), Image.LANCZOS)
    canvas.paste(shot, (pad, pad))

    # 刘海/听筒示意
    d.rounded_rectangle(
        [canvas.width // 2 - 40, pad + 4, canvas.width // 2 + 40, pad + 14],
        radius=6, fill=(8, 11, 20),
    )

    # 标签
    f1 = font(15)
    d.text((pad, canvas.height - 33), label, font=f1, fill=TEXT)
    f2 = font(12)
    d.text((pad + 8 + d.textlength(label, font=f1), canvas.height - 31), ratio, font=f2, fill=SUB)
    return canvas


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("vertical")
    ap.add_argument("horizontal")
    ap.add_argument("--out", default="docs/images/preview/board.png")
    ap.add_argument("--title", default="MYONL 手机端 · 两种屏幕")
    args = ap.parse_args()

    v = Image.open(ROOT / args.vertical if not pathlib.Path(args.vertical).is_absolute() else args.vertical)
    h = Image.open(ROOT / args.horizontal if not pathlib.Path(args.horizontal).is_absolute() else args.horizontal)

    # 让两个框高度接近：竖屏缩放到 1.0，横屏按高度对齐
    target_h = 640
    vs = target_h / v.height
    hs = target_h / h.height

    fv = phone_frame(v, vs, "竖屏", "1080x2400 · 20:9")
    fh = phone_frame(h, hs, "横屏", "2400x1080 · 20:9")

    gap = 40
    head = 64
    total_w = 40 + fv.width + gap + fh.width + 40
    total_h = head + max(fv.height, fh.height) + 40
    board = Image.new("RGB", (total_w, total_h), BG)
    d = ImageDraw.Draw(board)

    d.text((40, 20), args.title, font=font(24), fill=TEXT)
    d.text((40, 46), "同一份界面，两种真实屏幕比例下的样子", font=font(13), fill=SUB)

    board.paste(fv, (40, head))
    board.paste(fh, (40 + fv.width + gap, head))

    out = pathlib.Path(args.out)
    if not out.is_absolute():
        out = ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    board.save(out)
    print(f"底板 {out}  {out.stat().st_size} bytes  {board.width}x{board.height}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
