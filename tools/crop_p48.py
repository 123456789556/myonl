# -*- coding: utf-8 -*-
"""裁剪 P48 对话框帧的三角区域（快捷栏上方 ◀▶ 与对话框 ▲ 把手）放大核对。"""
import os
import sys
os.environ["SDL_VIDEODRIVER"] = "dummy"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pygame

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui_p48", "03_dialog_p48.png")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui_p48")
img = pygame.image.load(SRC)
w, h = img.get_size()
# 快捷栏上方三角区（右下）与对话框顶线把手（中上）
crops = {
    "04_triangles_p48.png": pygame.Rect(int(w * 0.90), int(h * 0.84), int(w * 0.10), int(h * 0.16)),
    "05_handle_p48.png": pygame.Rect(int(w * 0.40), int(h * 0.62), int(w * 0.20), int(h * 0.12)),
}
for name, rect in crops.items():
    sub = img.subsurface(rect)
    sub = pygame.transform.smoothscale(sub, (rect.width * 3, rect.height * 3))
    pygame.image.save(sub, os.path.join(OUT, name))
    print("CROPPED:", name)
