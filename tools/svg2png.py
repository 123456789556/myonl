"""SVG → PNG 导出工具（pygame-ce load_sized_svg，无头渲染）。

用法:
    py tools/svg2png.py <svg路径> <输出PNG路径> <宽> [高]

示例:
    py tools/svg2png.py brand/moyul_icon.svg brand/moyul_icon_512.png 512
"""
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame


def main() -> int:
    if len(sys.argv) < 4:
        print("用法: py tools/svg2png.py <svg路径> <输出PNG路径> <宽> [高]")
        return 1
    svg_path, out_path, w = sys.argv[1], sys.argv[2], int(sys.argv[3])
    h = int(sys.argv[4]) if len(sys.argv) > 4 else w
    pygame.init()
    surf = pygame.image.load_sized_svg(svg_path, (w, h))
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    pygame.image.save(surf, out_path)
    print(f"OK {out_path} {w}x{h}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
