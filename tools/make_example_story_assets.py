# -*- coding: utf-8 -*-
"""P18 M2：为《示例故事》生成占位素材（色块 + 静音音频）。

只写 games/示例故事/ 的 images/ 与 audio/；同名文件已存在则跳过（不覆盖用户素材）。
命名按 P18 素材清单：bg_01/bg_02/她_normal/她_smile/cg_cg_01/cg_cg_02 + bgm_01/voice_01/voice_02。

用法：
    py tools/make_example_story_assets.py            # 默认 games/示例故事
    py tools/make_example_story_assets.py --overwrite  # 强制重新生成
"""
from __future__ import annotations

import argparse
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# 复用 engine.newgame 的中文字体与名字绘制逻辑（P16 同一套）
from engine.newgame import _blit_name, _cjk_font  # noqa: E402

BG_SIZE = (1280, 720)
SPRITE_SIZE = (512, 1024)

_BG_SPECS = [
    ("bg_01", (202, 176, 124), "教室"),
    ("bg_02", (122, 168, 220), "街道"),
]
_SPRITE_SPECS = [
    ("她_normal", (238, 176, 190)),
    ("她_smile", (255, 204, 153)),
]
_CG_SPECS = [
    ("cg_cg_01", (196, 146, 118), "CG·平常的一天"),
    ("cg_cg_02", (64, 84, 148), "CG·一起回家"),
]
_AUDIO_SPECS = [
    ("bgm_01", 3),   # 3 秒静音
    ("voice_01", 2),  # 关键配音占位（静音，真素材后续替换）
    ("voice_02", 2),
]


def _save_png(surf, out: Path) -> bool:
    if out.exists():
        return False
    out.parent.mkdir(parents=True, exist_ok=True)
    import pygame
    pygame.image.save(surf, str(out))
    return True


def _save_silence(out: Path, seconds: float) -> bool:
    if out.exists():
        return False
    out.parent.mkdir(parents=True, exist_ok=True)
    rate, nch, sw = 22050, 1, 2  # 16bit 单声道
    frames = bytearray(b"\x00\x00" * (rate * nch * int(seconds)))
    with wave.open(str(out), "wb") as w:
        w.setnchannels(nch)
        w.setsampwidth(sw)
        w.setframerate(rate)
        w.writeframes(bytes(frames))
    return True


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="为《示例故事》生成占位素材")
    ap.add_argument("game_dir", nargs="?", default=str(ROOT / "games" / "示例故事"))
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    import os
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    import pygame
    pygame.font.init()

    root = Path(args.game_dir)
    img_dir = root / "images"
    aud_dir = root / "audio"
    made = []

    for name, rgb, label in _BG_SPECS:
        surf = pygame.Surface(BG_SIZE)
        surf.fill(rgb)
        if _save_png(surf, img_dir / f"{name}.png"):
            made.append(str(img_dir / f"{name}.png"))
    for name, rgb in _SPRITE_SPECS:
        surf = pygame.Surface(SPRITE_SIZE)
        surf.fill(rgb)
        _blit_name(surf, name.replace("_", "·") if False else name, rgb, root)
        if _save_png(surf, img_dir / f"{name}.png"):
            made.append(str(img_dir / f"{name}.png"))
    for name, rgb, label in _CG_SPECS:
        surf = pygame.Surface(BG_SIZE)
        surf.fill(rgb)
        _blit_name(surf, label, rgb, root)
        if _save_png(surf, img_dir / f"{name}.png"):
            made.append(str(img_dir / f"{name}.png"))
    for name, secs in _AUDIO_SPECS:
        if _save_silence(aud_dir / f"{name}.wav", secs):
            made.append(str(aud_dir / f"{name}.wav"))

    for p in made:
        print(f"已生成：{p}")
    print(f"共生成 {len(made)} 个占位素材（其余已存在跳过）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
