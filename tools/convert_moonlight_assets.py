# -*- coding: utf-8 -*-
"""P25 M1 素材转换：Moonlight Walks -> MYONL《月光漫步》
源: games/月光漫步/src/moonlight-2.0/game/
目标: games/月光漫步/{images,audio}/
规则:
  背景 jpg -> images/bg_*.png (统一 1280x720 拉伸 LANCZOS)
  立绘 mary_dark_* -> images/玛丽_暗_*.png (保留透明原尺寸)
        mary_dawn_* -> images/玛丽_黎明_*.png
  new/ 其他 png -> images/原名.png
  音频 ogg/wav -> audio/原名
  画廊 gal-*.png -> images/cg_*.png (连字符转下划线)
  background/icon/saveslot.png -> images/原名.png
"""
import os
import sys
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MOON = os.path.join(ROOT, "作品", "副产物", "月光漫步")  # P44：月光漫步移出主线
if not os.path.isdir(_MOON):
    _MOON = os.path.join(ROOT, "games", "月光漫步")  # 旧位置兜底
SRC = os.path.join(_MOON, "src", "moonlight-2.0", "game")
NEW = os.path.join(SRC, "new")
OUT_IMG = os.path.join(_MOON, "images")
OUT_AUD = os.path.join(_MOON, "audio")

CANVAS = (1280, 720)
report = []
errors = []

def ensure(dir):
    os.makedirs(dir, exist_ok=True)

def to_png_bg(src, dst):
    im = Image.open(src).convert("RGB")
    im = im.resize(CANVAS, Image.LANCZOS)
    im.save(dst, "PNG")

def copy_png(src, dst):
    im = Image.open(src).convert("RGBA")
    im.save(dst, "PNG")

def main():
    ensure(OUT_IMG)
    ensure(OUT_AUD)

    # 1. 背景 jpg -> png (1280x720)
    bgs = sorted(f for f in os.listdir(NEW) if f.lower().endswith(".jpg"))
    for f in bgs:
        name = os.path.splitext(f)[0]           # beach1a
        dst = os.path.join(OUT_IMG, f"bg_{name}.png")
        try:
            to_png_bg(os.path.join(NEW, f), dst)
            report.append(f"bg {f} -> bg_{name}.png (1280x720)")
        except Exception as e:
            errors.append(f"bg {f}: {e}")

    # 2. 立绘重命名
    sprites = sorted(f for f in os.listdir(NEW) if f.lower().endswith(".png"))
    for f in sprites:
        base = os.path.splitext(f)[0]
        dst_name = None
        if base.startswith("mary_dark_"):
            dst_name = "玛丽_暗_" + base[len("mary_dark_"):] + ".png"
        elif base.startswith("mary_dawn_"):
            dst_name = "玛丽_黎明_" + base[len("mary_dawn_"):] + ".png"
        else:
            dst_name = f
        dst = os.path.join(OUT_IMG, dst_name)
        try:
            copy_png(os.path.join(NEW, f), dst)
            report.append(f"立绘 {f} -> {dst_name}")
        except Exception as e:
            errors.append(f"立绘 {f}: {e}")

    # 3. 音频 (根目录 ogg/wav)
    for f in sorted(os.listdir(SRC)):
        if f.lower().endswith((".ogg", ".wav", ".mp3")):
            src = os.path.join(SRC, f)
            dst = os.path.join(OUT_AUD, f)
            with open(src, "rb") as fin, open(dst, "wb") as fout:
                fout.write(fin.read())
            report.append(f"音频 {f}")

    # 4. 画廊 CG gal-*.png -> cg_*.png
    for f in sorted(os.listdir(SRC)):
        if f.startswith("gal-") and f.lower().endswith(".png"):
            dst_name = "cg_" + f[4:].replace("-", "_")   # gal-end1.png -> cg_end1.png
            dst = os.path.join(OUT_IMG, dst_name)
            try:
                copy_png(os.path.join(SRC, f), dst)
                report.append(f"CG {f} -> {dst_name}")
            except Exception as e:
                errors.append(f"CG {f}: {e}")

    # 5. 根目录杂项 png
    for f in ["background.png", "icon.png", "saveslot.png"]:
        src = os.path.join(SRC, f)
        if os.path.exists(src):
            dst = os.path.join(OUT_IMG, f)
            try:
                copy_png(src, dst)
                report.append(f"杂项 {f}")
            except Exception as e:
                errors.append(f"杂项 {f}: {e}")

    # 6. 报告
    print(f"=== 转换完成: {len(report)} 成功 / {len(errors)} 失败 ===")
    for line in report:
        print(line)
    for line in errors:
        print("ERROR:", line)
    print(f"=== images: {len(os.listdir(OUT_IMG))} 个 / audio: {len(os.listdir(OUT_AUD))} 个 ===")
    return 0 if not errors else 1

if __name__ == "__main__":
    sys.exit(main())
