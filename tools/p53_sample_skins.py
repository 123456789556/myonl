"""P53 皮肤示例素材生成器：给教程示例造两张可直接用的皮肤贴图。

产出（写进 games/教程示例/images/）：
    textbox.png —— 九宫格友好的对话框贴图（半透明深色玻璃 + 暖色细线）
    paper.png   —— 可平铺的纸纹（panel_texture 用）

用法：
    py -3 tools/p53_sample_skins.py [项目根，默认 games/教程示例]

为什么用脚本生成而不是塞两张图进仓库：素材可复现、可改参数重跑，
也不给发行包凭空加体积（教程示例是用户可改的样板，不是内置资源）。
"""
from __future__ import annotations

import os
import random
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

W, H = 640, 170          # 贴图基准尺寸；游戏里按九宫格拉成任意宽高
RADIUS = 20
GOLD = (214, 186, 132)   # 暖色细线（不刺眼，压在深色底上刚好可读）


def make_textbox(size=(W, H)) -> pygame.Surface:
    """半透明深色玻璃面板：竖向渐变 + 圆角 + 1px 暖色内描边 + 顶部高光。"""
    w, h = size
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    body = pygame.Surface((w, h), pygame.SRCALPHA)
    # 竖向渐变：上深下浅（贴到画面上时底部更透，文字仍够对比度）
    for y in range(h):
        t = y / max(1, h - 1)
        alpha = int(214 - 34 * t)
        color = (22 + int(6 * t), 24 + int(8 * t), 34 + int(12 * t))
        pygame.draw.line(body, (*color, alpha), (0, y), (w - 1, y))
    mask = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.rect(mask, (255, 255, 255, 255), pygame.Rect(0, 0, w, h),
                     border_radius=RADIUS)
    body.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    surf.blit(body, (0, 0))
    # 暖色内描边（九宫格四角靠它保持形状，拉伸时边线跟着走）
    pygame.draw.rect(surf, (*GOLD, 96), pygame.Rect(1, 1, w - 2, h - 2),
                     width=1, border_radius=RADIUS - 1)
    # 顶部高光：一条 2px 的浅色
    pygame.draw.line(surf, (255, 255, 255, 40), (RADIUS, 2), (w - RADIUS, 2), 2)
    return surf


def make_paper(size=64, seed=20261115) -> pygame.Surface:
    """可平铺纸纹：低对比噪点，左右上下接缝对齐（同一噪点图循环不显格子）。"""
    random.seed(seed)
    tex = pygame.Surface((size, size), pygame.SRCALPHA)
    tex.fill((255, 255, 255, 0))
    for y in range(size):
        for x in range(size):
            v = random.randint(0, 42)
            if v:
                # 暖白噪点，靠 panel_texture_alpha 控制强度
                tex.set_at((x, y), (250, 244, 232, v))
    # 两条极淡的横纹，让平铺看起来像纸不是沙
    for y in range(0, size, 16):
        pygame.draw.line(tex, (250, 244, 232, 8), (0, y), (size - 1, y))
    return tex


def main() -> int:
    root = sys.argv[1] if len(sys.argv) > 1 else os.path.join("games", "教程示例")
    out_dir = os.path.join(root, "images")
    if not os.path.isdir(root):
        print(f"项目根不存在：{root}")
        return 1
    os.makedirs(out_dir, exist_ok=True)
    pygame.init()
    pygame.display.set_mode((1, 1))   # dummy 驱动下也需要一个显示面
    try:
        tb = make_textbox()
        paper = make_paper()
        tb_path = os.path.join(out_dir, "textbox.png")
        paper_path = os.path.join(out_dir, "paper.png")
        pygame.image.save(tb, tb_path)
        pygame.image.save(paper, paper_path)
        print(f"已生成 {tb_path}（{tb.get_width()}×{tb.get_height()}）")
        print(f"已生成 {paper_path}（{paper.get_width()}×{paper.get_height()}，可平铺）")
        # 顺带出一张九宫格拉伸后的样子，便于肉眼确认不变形
        from engine import dialog_skin

        demo = pygame.Surface((1600, 240), pygame.SRCALPHA)
        demo.fill((28, 30, 42, 0))
        stretched = dialog_skin.compose_panel(tb, 1600, 240, [28, 20, 28, 20],
                                             None, 0, 0, paper, 40, 255)
        demo.blit(stretched, (0, 0))
        shot = os.path.join("screenshots", "p53-dialog-skin.png")
        os.makedirs("screenshots", exist_ok=True)
        pygame.image.save(demo, shot)
        print(f"已生成对照图 {shot}（1600×240 九宫格拉伸 + 纸纹 40）")
    finally:
        pygame.quit()
    return 0


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    raise SystemExit(main())
