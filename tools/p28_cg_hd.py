# -*- coding: utf-8 -*-
"""CG 高清化：6 张替换为原作高清场景 + 2 张隐藏格立绘合成。
源图都是 1280×720（原作 new/*.jpg 转换），修复 cg_end1 错图（Searching 进度条）。"""
import shutil
from PIL import Image
import os

IMG = r"D:\娱乐工作区\自研项目\Moyul引擎\games\月光漫步\images"

# 1) 直接替换（原作画廊每格封面场景的高清版）
REPLACE = {
    "cg_dark.png":   "bg_beach2.png",     # 暗形态：月夜海滩
    "cg_dawn.png":   "bg_dawn1.png",     # 黎明形态：黎明海滩
    "cg_end1.png":   "bg_badending.png", # 结局1(坏结局)：修复原错图(Searching进度条)
    "cg_end2.png":   "bg_library.png",   # 结局2(历史)：图书馆
    "cg_end3.png":   "bg_littlemary2.png", # 结局3(片刻的新娘)：小女孩
    "cg_end4.png":   "bg_heaven.png",    # 结局4(携手走向光)：天堂白光
}
for dst, src in REPLACE.items():
    shutil.copyfile(os.path.join(IMG, src), os.path.join(IMG, dst))
    im = Image.open(os.path.join(IMG, dst))
    print("替换:", dst, "<-", src, im.size, im.mode)

# 2) 立绘合成（隐藏彩蛋格：场景 + 玛丽立绘）
def compose(dst, bg_name, spr_name, target_h=640):
    bg = Image.open(os.path.join(IMG, bg_name)).convert("RGBA")
    spr = Image.open(os.path.join(IMG, spr_name)).convert("RGBA")
    w, h = spr.size
    nh = target_h
    nw = int(w * nh / h)
    spr = spr.resize((nw, nh), Image.LANCZOS)
    x = (bg.width - nw) // 2
    y = bg.height - nh  # 底部贴地
    bg.alpha_composite(spr, (x, y))
    out = bg.convert("RGB")
    out.save(os.path.join(IMG, dst))
    print("合成:", dst, "=", bg_name, "+", spr_name, out.size)

compose("cg_dark_mary.png", "bg_beach2.png", "玛丽_暗_smiling.png")
compose("cg_dawn_mary.png", "bg_dawn1.png", "玛丽_黎明_smiling.png")

print("完成")
