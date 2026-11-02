# -*- coding: utf-8 -*-
"""A4：照片转立绘——纯色背景抠成透明 PNG（边缘羽化 + 自动裁边）。

用法：
    py -3 tools/make_sprite_transparent.py 照片.jpg --out images/林晚_微笑.png
    py -3 tools/make_sprite_transparent.py 素材目录 --out images/ --tolerance 40

算法：从四条边向内 flood fill 与四角背景色相近的像素 → 设为透明；
再做一次 1px 羽化（alpha 平滑）并裁掉四周空白，得到可直接 @show 的立绘 PNG。
只依赖 Pillow（requirements-dev.txt 已含），不联网、不改原图。
"""
from __future__ import annotations

import argparse
import sys
from collections import deque
from pathlib import Path

from PIL import Image, ImageFilter

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp")


def _bg_color(px, w: int, h: int) -> tuple[int, int, int]:
    """四角平均色作为背景色（照片常见纯色/渐变背景的近似）。"""
    corners = [px[0, 0], px[w - 1, 0], px[0, h - 1], px[w - 1, h - 1]]
    return tuple(sum(c[i] for c in corners) // len(corners) for i in range(3))  # type: ignore[return-value]


def _close(c, bg, tol: int) -> bool:
    return (abs(c[0] - bg[0]) <= tol and abs(c[1] - bg[1]) <= tol
            and abs(c[2] - bg[2]) <= tol)


def make_transparent(src, dst=None, tolerance: int = 32, feather: bool = True) -> Path:
    """把 src 的纯色背景抠透明，返回输出的 PNG 路径。"""
    src = Path(src)
    dst = Path(dst) if dst else src.with_suffix(".png")
    if dst.suffix.lower() != ".png":
        dst = dst.with_suffix(".png")
    img = Image.open(src).convert("RGBA")
    w, h = img.size
    px = img.load()
    bg = _bg_color(px, w, h)
    seen = bytearray(w * h)
    queue = deque()
    for x in range(w):
        for y in (0, h - 1):
            queue.append((x, y))
    for y in range(h):
        for x in (0, w - 1):
            queue.append((x, y))
    while queue:
        x, y = queue.popleft()
        if not (0 <= x < w and 0 <= y < h):
            continue
        idx = y * w + x
        if seen[idx]:
            continue
        c = px[x, y]
        if not _close(c, bg, tolerance):
            continue
        seen[idx] = 1
        px[x, y] = (c[0], c[1], c[2], 0)
        queue.extend(((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)))

    if feather:
        alpha = img.getchannel("A").filter(ImageFilter.GaussianBlur(0.6))
        img.putalpha(alpha)
    bbox = img.getchannel("A").getbbox()
    if bbox:
        img = img.crop(bbox)
    dst.parent.mkdir(parents=True, exist_ok=True)
    img.save(dst, "PNG", optimize=True)
    return dst


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="照片转立绘：纯色背景抠透明 + 自动裁边（A4）")
    ap.add_argument("source", help="单张图片或图片目录")
    ap.add_argument("--out", required=True,
                    help="输出：单张给 .png 路径；目录输入给输出目录")
    ap.add_argument("--tolerance", type=int, default=32,
                    help="背景色容差 0~120（默认 32；背景不干净时调大）")
    ap.add_argument("--no-feather", action="store_true", help="关闭 1px 羽化（硬边）")
    args = ap.parse_args(argv)

    src = Path(args.source)
    out = Path(args.out)
    tol = max(0, min(120, args.tolerance))
    if src.is_dir():
        out.mkdir(parents=True, exist_ok=True)
        done, failed = 0, 0
        for p in sorted(src.rglob("*")):
            if p.is_file() and p.suffix.lower() in IMAGE_EXTS:
                try:
                    target = make_transparent(p, out / (p.stem + ".png"), tol,
                                              not args.no_feather)
                    print(f"OK  {p.name} -> {target}")
                    done += 1
                except (OSError, ValueError) as e:
                    print(f"ERR {p.name}: {e}", file=sys.stderr)
                    failed += 1
        print(f"完成：{done} 张成功，{failed} 张失败")
        return 0 if failed == 0 else 1
    try:
        target = make_transparent(src, out, tol, not args.no_feather)
    except (OSError, ValueError) as e:
        print(f"错误：{e}", file=sys.stderr)
        return 2
    print(f"已生成透明立绘：{target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
