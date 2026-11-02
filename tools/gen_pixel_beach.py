# -*- coding: utf-8 -*-
"""P51：程序化生成"海边像素画"背景（1280×720）——纯 Python 绘制，不用 AI。

做法：在 160×90 的逻辑画布上逐像素画（每个逻辑像素 = 8×8 物理像素），
再用 NEAREST 放大到 1280×720，得到硬像素块的海边像素画。

画面（白天晴天海边）：
  天空(顶) → 云 → 太阳(右上) → 海(中) → 白色浪花 → 沙滩(底) → 海鸥(两点)
"""
import os
import random

from PIL import Image

LW, LH = 160, 90          # 逻辑画布（每格 8px）
SCALE = 8                 # 放大倍数 → 1280×720

# 调色板（RGB）
SKY_TOP = (96, 168, 224)      # 顶部天空
SKY_BOT = (188, 224, 244)     # 地平线天空
SEA = (60, 132, 192)          # 海
SEA_LIGHT = (110, 178, 224)   # 海面浅条
FOAM = (246, 252, 255)        # 浪花
SAND = (236, 210, 160)        # 沙滩
SAND_DARK = (214, 184, 132)   # 沙滩阴影
SUN = (255, 226, 120)         # 太阳
SUN_CORE = (255, 246, 200)
CLOUD = (252, 252, 254)       # 云
BIRD = (52, 66, 92)           # 海鸥


def make_beach() -> Image.Image:
    rng = random.Random(51)  # 固定种子：可复现
    img = Image.new("RGB", (LW, LH))
    px = img.load()

    def vgrad(x, y):
        """竖直渐变：天空部分 y∈[0, 地平线)。"""
        t = y / max(1, HORIZON)
        r = int(SKY_TOP[0] + (SKY_BOT[0] - SKY_TOP[0]) * t)
        g = int(SKY_TOP[1] + (SKY_BOT[1] - SKY_TOP[1]) * t)
        b = int(SKY_TOP[2] + (SKY_BOT[2] - SKY_TOP[2]) * t)
        return (r, g, b)

    HORIZON = 46                # 海平线 y
    SEA_TOP = HORIZON
    SEA_BOT = 74                # 海/沙交界
    SAND_TOP = SEA_BOT

    for y in range(LH):
        for x in range(LW):
            if y < HORIZON:
                px[x, y] = vgrad(x, y)
            elif y < SEA_BOT:
                # 海面：带少量横向深浅条（像素感）
                band = (y - SEA_TOP) % 5
                c = SEA_LIGHT if band in (1, 3) else SEA
                px[x, y] = c
            else:
                # 沙滩
                c = SAND
                if (x + y) % 9 == 0:
                    c = SAND_DARK
                px[x, y] = c

    # 太阳：右上角圆块（像素圆）
    cx, cy, r = 132, 12, 7
    for y in range(cy - r, cy + r + 1):
        for x in range(cx - r, cx + r + 1):
            if (x - cx) ** 2 + (y - cy) ** 2 <= r * r:
                px[x, y] = SUN
    # 太阳核心亮格
    for y in range(cy - 2, cy + 3):
        for x in range(cx - 2, cx + 3):
            px[x, y] = SUN_CORE if 0 <= x < LW and 0 <= y < LH else px[x, y]

    # 云：三团白色像素云（左上/中上/右上偏左），固定形状
    clouds = [
        ((28, 16), 5), ((58, 10), 6), ((86, 20), 4),
    ]
    for (bcx, bcy), br in clouds:
        for y in range(bcy - br, bcy + br + 1):
            for x in range(bcx - br, bcx + br + 1):
                d = (x - bcx) ** 2 / (br ** 2) + (y - bcy) ** 2 / ((br // 2 + 1) ** 2)
                if d <= 1 and 0 <= x < LW and 0 <= y < HORIZON:
                    px[x, y] = CLOUD

    # 浪花：海面与沙滩交界处的白色锯齿带
    for x in range(LW):
        jitter = 1 if (x // 3) % 2 else 0
        px[x, SEA_BOT - 1 - jitter] = FOAM
        px[x, SEA_BOT] = FOAM if x % 4 else SAND

    # 海鸥：深色"人"字两点
    for (bx, by) in [(52, 30), (60, 34), (110, 26), (118, 32)]:
        px[bx, by] = BIRD
        px[bx - 2, by + 1] = BIRD
        px[bx + 2, by + 1] = BIRD

    # 放大到物理尺寸：NEAREST 保持硬像素块
    big = img.resize((LW * SCALE, LH * SCALE), Image.NEAREST)
    return big


def main():
    out_dir = os.path.join(os.path.dirname(__file__), "..", "games", "新游戏", "images")
    out = os.path.join(out_dir, "bg_海边像素.png")
    os.makedirs(out_dir, exist_ok=True)
    img = make_beach()
    img.save(out)
    print(f"已生成: {out} ({img.size[0]}x{img.size[1]})")


if __name__ == "__main__":
    main()
