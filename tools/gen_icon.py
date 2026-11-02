# -*- coding: utf-8 -*-
"""MYONL 应用图标导出：版 A（MY + 右上独立星 + 极淡光晕）
矢量源: brand/icon_my.svg（PIL 复刻一致）
输出:   brand/icon/icon_my_{512,256,128,64,32,16}.png + 单色/反白 512
"""
import os
from PIL import Image, ImageDraw, ImageFont

ROOT = r"D:\娱乐工作区\自研项目\MYONL引擎"
OUT = os.path.join(ROOT, "brand", "icon")
os.makedirs(OUT, exist_ok=True)

BG_TOP = (38, 52, 138)      # #26348A
BG_BOT = (69, 43, 148)      # #452B94
MY_TOP = (255, 255, 255)    # #FFFFFF
MY_BOT = (220, 213, 255)    # #DCD5FF
STAR = (255, 233, 168)      # #FFE9A8
GLOW = (124, 107, 255)      # #7C6BFF

def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))

def vgrad(size, top, bot):
    img = Image.new("RGB", size)
    px = img.load()
    h = size[1]
    for y in range(h):
        c = lerp(top, bot, y / (h - 1))
        for x in range(size[0]):
            px[x, y] = c
    return img

def rounded_mask(size, radius):
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, size[0] - 1, size[1] - 1], radius=radius, fill=255)
    return m

def text_gradient_mask(text, font, gap):
    # 逐字符测量并排版（含字距 gap），返回 (mask, total_w)
    tmp = Image.new("L", (1, 1), 0)
    d = ImageDraw.Draw(tmp)
    widths = [d.textbbox((0, 0), ch, font=font)[2] for ch in text]
    total_w = sum(widths) + gap * (len(text) - 1)
    mask = Image.new("L", (total_w, font.size * 2), 0)
    dm = ImageDraw.Draw(mask)
    x = 0
    for ch, w in zip(text, widths):
        dm.text((x, 0), ch, font=font, fill=255)
        x += w + gap
    return mask, total_w

def draw_icon(size, mono=None, reverse=False):
    S = size
    u = S / 512.0  # 缩放单位
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    # 极淡光晕（中心 radial，低 alpha）
    glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    cx, cy = S * 0.5, S * 0.46
    R = S * 0.55
    for i in range(40):
        r = R * (1 - i / 40.0)
        a = int(70 * (1 - r / R) ** 1.6)
        gd.ellipse([cx - r, cy - r, cx + r, cy + r], fill=GLOW + (a,))
    img.alpha_composite(glow)

    # 渐变圆角底
    base = vgrad((S, S), BG_TOP, BG_BOT)
    rad = int(46 * u)
    base.putalpha(rounded_mask((S, S), rad))
    img.alpha_composite(base)
    # 底描边
    od = ImageDraw.Draw(img)
    od.rounded_rectangle([int(8*u), int(8*u), S - int(8*u) - 1, S - int(8*u) - 1],
                         radius=int(38*u), outline=(255, 255, 255, 40), width=max(1, int(1.5*u)))

    if mono == "black":
        # 白底黑标
        mono_img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        mm = Image.new("L", (S, S), 0)
        ImageDraw.Draw(mm).rounded_rectangle([0, 0, S-1, S-1], radius=rad, fill=255)
        mono_img.paste((255, 255, 255, 255), (0, 0), mm)
        img = mono_img
        my_color = (20, 20, 30, 255)
        star_color = (40, 40, 50, 255)
    elif reverse:
        mono_img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        mm = Image.new("L", (S, S), 0)
        ImageDraw.Draw(mm).rounded_rectangle([0, 0, S-1, S-1], radius=rad, fill=255)
        mono_img.paste((10, 12, 24, 255), (0, 0), mm)
        img = mono_img
        my_color = (255, 255, 255, 255)
        star_color = (255, 233, 168, 255)
    else:
        my_color = None
        star_color = STAR

    # MY 字母（粗体，渐变或单色）
    font = ImageFont.truetype(r"C:\Windows\Fonts\arialbd.ttf", int(96 * u))
    mask, tw = text_gradient_mask("MY", font, max(1, int(2 * u)))
    tw = min(tw, S)
    mask = mask.crop((0, 0, tw, mask.height))
    x0 = int((S - tw) / 2)
    y0 = int(S * 0.5 - mask.height / 2.0)
    if my_color:
        color_img = Image.new("RGB", (tw, mask.height), my_color[:3])
        color_img.putalpha(mask)
        img.paste(color_img, (x0, y0), mask)
    else:
        grad = vgrad((tw, mask.height), MY_TOP, MY_BOT)
        grad.putalpha(mask)
        img.paste(grad, (x0, y0), mask)

    # 右上独立星（菱形）
    sd = ImageDraw.Draw(img)
    sx, sy = int(178 * u), int(48 * u)
    hd = int(4.5 * u)
    sd.polygon([(sx, sy - hd), (sx + hd, sy), (sx, sy + hd), (sx - hd, sy)], fill=star_color)
    return img

def main():
    img512 = draw_icon(512)
    img512.save(os.path.join(OUT, "icon_my_512.png"))
    for s in (256, 128, 64, 32, 16):
        img512.resize((s, s), Image.LANCZOS).save(os.path.join(OUT, f"icon_my_{s}.png"))
    draw_icon(512, mono="black").save(os.path.join(OUT, "icon_my_mono_512.png"))
    draw_icon(512, reverse=True).save(os.path.join(OUT, "icon_my_reverse_512.png"))
    print("exported to", OUT)
    for f in sorted(os.listdir(OUT)):
        print(" ", f)

if __name__ == "__main__":
    main()
