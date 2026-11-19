"""把多档截图拼成 README 用的展示图：竖版一排、横版一排。"""
import pathlib
import sys

from PIL import Image, ImageDraw, ImageFont

FONT = r"C:\Windows\Fonts\msyh.ttc"
try:
    LABEL_FONT = ImageFont.truetype(FONT, 22)
except Exception:
    LABEL_FONT = ImageFont.load_default()

PREVIEW = pathlib.Path(r"D:\娱乐工作区\myonl\MYONL引擎\docs\images\preview")
DOCS = pathlib.Path(r"D:\娱乐工作区\myonl\MYONL引擎\docs\images")
DOCS.mkdir(parents=True, exist_ok=True)


def row(files, labels, out, gap=20, pad=36, bg=(16, 17, 22), maxh=760):
    ims = [Image.open(PREVIEW / f).convert("RGB") for f in files]
    h = min(maxh, max(i.height for i in ims))
    scaled = []
    for im in ims:
        r = h / im.height
        scaled.append(im.resize((int(im.width * r), h), Image.LANCZOS))
    W = sum(s.width for s in scaled) + gap * (len(scaled) - 1) + pad * 2
    H = h + pad * 2 + 30
    canvas = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(canvas)
    x = pad
    for i, s in enumerate(scaled):
        canvas.paste(s, (x, pad))
        d.text((x + 4, pad + h + 8), labels[i], fill=(150, 158, 176), font=LABEL_FONT)
        x += s.width + gap
    canvas.save(out, optimize=True)
    print(out, canvas.size, out.stat().st_size, "bytes")


row(
    ["multi-360x800.png", "multi-390x844.png", "multi-412x915.png", "multi-360x640.png"],
    ["安卓 360×800", "苹果 390×844", "安卓 412×915", "老机 360×640"],
    DOCS / "showcase-portrait.png",
    maxh=700,
)

row(
    ["multi-800x360.png", "multi-1024x768.png"],
    ["手机横屏 800×360", "平板横屏 1024×768"],
    DOCS / "showcase-landscape.png",
    gap=28,
)

row(
    ["theme-light-home.png", "theme-dark-home.png"],
    ["浅色", "深色"],
    DOCS / "showcase-theme.png",
    maxh=760,
)
