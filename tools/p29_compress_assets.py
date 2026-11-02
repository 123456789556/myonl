# -*- coding: utf-8 -*-
"""P29 A2：月光漫步素材瘦身（转 JPG / 降音频码率）。

安全铁律：
- 默认 dry-run：只打印计划与预估，不写任何文件；真正执行必须 --apply。
- --apply 前先把原 PNG/OGG 全量备份到 src/P29原始素材备份/（可回退）。
- 透明 PNG（立绘/UI 带 alpha）一律不转，保持原文件。
- 依赖 pygame 保存 JPG；audio 依赖 ffmpeg（无 ffmpeg 则跳过音频并说明）。
"""
import os
import shutil
import subprocess
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

ROOT = r"D:\娱乐工作区\自研项目\Moyul引擎"
GAME = os.path.join(ROOT, "games", "月光漫步")
IMAGES = os.path.join(GAME, "images")
AUDIO = os.path.join(GAME, "audio")
BACKUP = os.path.join(GAME, "src", "P29原始素材备份")
JPG_Q = 85
OGG_BITRATE = "96k"


def _has_alpha(surface) -> bool:
    return bool(surface.get_flags() & pygame.SRCALPHA)


def _convertible_pngs():
    """返回 [(路径, 相对名, 预估JPG体积)]：不透明、>200KB 且是 bg_/cg_/title_bg 的大图。
    小图（<=200KB）转 JPG 体积反而可能增大，保持 PNG。"""
    out = []
    for n in sorted(os.listdir(IMAGES)):
        if not n.lower().endswith(".png"):
            continue
        if not (n.startswith("bg_") or n.startswith("cg_") or n == "title_bg.png"):
            continue
        p = os.path.join(IMAGES, n)
        if os.path.getsize(p) <= 200_000:
            continue
        s = pygame.image.load(p)
        if _has_alpha(s):
            continue  # 透明：必须留 PNG
        est = max(60_000, int(s.get_width() * s.get_height() * 0.35))  # q85 1280x720 约 320KB
        out.append((p, n, est))
    return out


def _audio_plan():
    """返回 [(路径, 相对名, 原体积)]；无 ffmpeg 返回 None。"""
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=10)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    out = []
    for n in sorted(os.listdir(AUDIO)):
        if n.lower().endswith((".ogg", ".wav")):
            p = os.path.join(AUDIO, n)
            if os.path.getsize(p) > 200_000:  # 只压 >200KB 的
                out.append((p, n, os.path.getsize(p)))
    return out


def _backup(apply: bool):
    dst = os.path.join(BACKUP, "images")
    os.makedirs(dst, exist_ok=True)
    moved = 0
    for n in sorted(os.listdir(IMAGES)):
        if n.lower().endswith(".png"):
            src = os.path.join(IMAGES, n)
            d = os.path.join(dst, n)
            if not os.path.exists(d):
                shutil.copy2(src, d)
                moved += 1
    if os.path.isdir(AUDIO):
        adst = os.path.join(BACKUP, "audio")
        os.makedirs(adst, exist_ok=True)
        for n in sorted(os.listdir(AUDIO)):
            if n.lower().endswith((".ogg", ".wav")):
                src = os.path.join(AUDIO, n)
                d = os.path.join(adst, n)
                if not os.path.exists(d):
                    shutil.copy2(src, d)
                    moved += 1
    return moved


def main():
    apply = "--apply" in sys.argv
    pygame.init()
    pngs = _convertible_pngs()
    audio = _audio_plan()

    print(f"模式: {'APPLY（真实转换）' if apply else 'DRY-RUN（不写文件）'}")
    print(f"\n可转 JPG 的不透明大图 {len(pngs)} 张（q={JPG_Q}）:")
    png_bytes = 0
    for p, n, est in pngs:
        png_bytes += os.path.getsize(p)
        print(f"  {n:<28} {os.path.getsize(p)/1e6:6.2f} MB -> ~{est/1e6:5.2f} MB")
    png_after = sum(e for _, _, e in pngs)
    print(f"  合计 {png_bytes/1e6:.1f} MB -> ~{png_after/1e6:.1f} MB（省 ~{(png_bytes-png_after)/1e6:.1f} MB）")

    if audio is None:
        print("\naudio: 未检测到 ffmpeg，跳过音频压缩（需手动装 ffmpeg 或保持现状）")
    else:
        print(f"\n可压音频 {len(audio)} 首（-> {OGG_BITRATE} ogg）:")
        abytes = sum(s for _, _, s in audio)
        print(f"  原 {abytes/1e6:.1f} MB -> 预计 ~{(abytes*0.55)/1e6:.1f} MB（省 ~{(abytes*0.45)/1e6:.1f} MB）")

    if not apply:
        print("\n[DRY-RUN 结束] 未写任何文件。确认后加 --apply 执行（会先备份到 src/P29原始素材备份/）。")
        return

    backed = _backup(True)
    print(f"\n[APPLY] 已备份 {backed} 个原文件 -> {BACKUP}")
    for p, n, _ in pngs:
        s = pygame.image.load(p)
        jpg = os.path.splitext(p)[0] + ".jpg"
        pygame.image.save(s, jpg)
        os.remove(p)
        print(f"  转: {n} -> {os.path.basename(jpg)} ({os.path.getsize(jpg)/1e6:.2f} MB)")
    if audio is not None:
        for p, n, _ in audio:
            out = os.path.splitext(p)[0] + ".ogg"
            tmp = out + ".tmp.ogg"
            r = subprocess.run(["ffmpeg", "-y", "-i", p, "-b:a", OGG_BITRATE, tmp],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if r.returncode == 0 and os.path.exists(tmp) and os.path.getsize(tmp) > 0:
                os.replace(tmp, out)
                if os.path.abspath(p) != os.path.abspath(out):
                    os.remove(p)
                print(f"  压: {n} ({os.path.getsize(out)/1e6:.2f} MB)")
            else:
                print(f"  跳过: {n}（ffmpeg 失败）")
    print("[APPLY] 完成。请跑全量 pytest + 无头回归 + 画廊/开场截图对比。")


if __name__ == "__main__":
    main()
