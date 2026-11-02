# -*- coding: utf-8 -*-
"""MYONL 引擎启动入场动画（苹果风）

时间线（总约 2.6s）：
  0.00-0.90s  深蓝紫渐变背景渐显 + MY 图标淡入 + 轻微缩放(0.86→1.0, ease-out)
  0.90-2.00s  图标外圈光晕呼吸 2 次 + 星尘沿椭圆轨道漂浮闪烁
  2.00-2.60s  整体淡出

用法:
  py tools/splash.py --demo                         # 真窗口播放后退出
  py tools/splash.py --capture out.png [--frames N] # 渲染 N 帧后自截图（默认 90 帧 ≈ t=1.5s 呼吸期）
集成: from splash import run_splash; run_splash(screen)  # 播完返回，进入引擎主界面
"""
import sys
import math
import os
import argparse

# capture 模式不弹窗：用 dummy 视频驱动（须在 pygame.init 前设置）
if "--capture" in sys.argv:
    os.environ["SDL_VIDEODRIVER"] = "dummy"

import pygame

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ICON = os.path.join(ROOT, "brand", "icon", "icon_my_256.png")

W, H = 640, 400
BG_TOP = (11, 16, 48)
BG_BOT = (42, 27, 94)
GLOW_COLOR = (124, 107, 255)
STAR_COLOR = (255, 233, 168)

FADE_IN = 0.90
BREATH = 1.10
FADE_OUT = 2.00
FADE_OUT_DUR = 0.60
ICON_BASE = 200
FPS = 60


def vgrad_surface(size, top, bot):
    s = pygame.Surface(size)
    h = size[1]
    for y in range(h):
        t = y / max(1, h - 1)
        c = tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(3))
        pygame.draw.line(s, c, (0, y), (size[0], y))
    return s


def ease_out(x):
    return 1 - (1 - x) ** 3


def draw_frame(canvas, t, icon_img):
    # 背景（苹果风：干净深色渐变，无噪声）
    canvas.blit(BG_SURF, (0, 0))

    # 星尘：6 颗沿椭圆轨道缓慢漂浮 + 呼吸闪烁
    for i in range(6):
        phase = t * 0.7 + i * (2 * math.pi / 6)
        rx = 150 + 14 * math.sin(t * 0.9 + i)
        ry = 76 + 10 * math.cos(t * 1.1 + i * 1.7)
        x = W / 2 + rx * math.cos(phase)
        y = H / 2 - 10 + ry * math.sin(phase)
        twinkle = 0.5 + 0.5 * math.sin(t * 2.4 + i * 2.0)
        pygame.draw.circle(canvas, (*STAR_COLOR, int(160 * twinkle)),
                           (int(x), int(y)), 3)

    # 图标淡入 + 缩放
    if t < FADE_IN:
        k = ease_out(t / FADE_IN)
        scale = 0.86 + 0.14 * k
        alpha = int(255 * k)
    else:
        scale = 1.0
        alpha = 255
    size = int(ICON_BASE * scale)

    # 呼吸光晕（画在图标下层）
    glow = 0
    if t >= FADE_IN:
        gp = min(1.0, (t - FADE_IN) / BREATH)
        glow = int(64 * (0.55 + 0.45 * math.sin(2 * math.pi * 2 * gp)))
    if glow > 0:
        gs = pygame.Surface((size + 96, size + 96), pygame.SRCALPHA)
        gcr = (size + 96) // 2
        wr = max(6, int(10 + 6 * math.sin(t * 2.6)))
        pygame.draw.circle(gs, (*GLOW_COLOR, glow), (gcr, gcr), gcr - 6, wr)
        pygame.draw.circle(gs, (*GLOW_COLOR, int(glow * 0.5)),
                           (gcr, gcr), int(gcr * 0.86), max(3, wr - 3))
        canvas.blit(gs, (W / 2 - gs.get_width() / 2,
                         H / 2 - 10 - gs.get_height() / 2))

    icon = pygame.transform.smoothscale(icon_img, (size, size))
    icon.set_alpha(alpha)
    canvas.blit(icon, (W / 2 - size / 2, H / 2 - 10 - size / 2))

    # 整体淡出
    if t >= FADE_OUT:
        fo = min(1.0, (t - FADE_OUT) / FADE_OUT_DUR)
        fade = pygame.Surface((W, H))
        fade.fill((0, 0, 0))
        fade.set_alpha(int(255 * fo))
        canvas.blit(fade, (0, 0))

    return t >= FADE_OUT + FADE_OUT_DUR


def run_splash(screen=None, icon_img=None):
    """播放入场动画；screen 为 None 时创建独立窗口。播完返回。"""
    own = screen is None
    if own:
        screen = pygame.display.set_mode((W, H))
        pygame.display.set_caption("MYONL")
    canvas = screen
    if icon_img is None:
        icon_img = ICON_IMG
    clock = pygame.time.Clock()
    t = 0.0
    done = False
    while not done:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                if own:
                    pygame.quit()
                    sys.exit(0)
                return
            if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
                return
        done = draw_frame(canvas, t, icon_img)
        pygame.display.flip()
        clock.tick(FPS)
        t += 1.0 / FPS
    return


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--capture", metavar="PNG")
    ap.add_argument("--frames", type=int, default=90)
    args = ap.parse_args()

    pygame.init()
    global BG_SURF, ICON_IMG
    BG_SURF = vgrad_surface((W, H), BG_TOP, BG_BOT)
    ICON_IMG = pygame.image.load(ICON)

    if args.capture:
        canvas = pygame.Surface((W, H), pygame.SRCALPHA)
        t = 0.0
        for f in range(args.frames):
            draw_frame(canvas, t, ICON_IMG)
            t += 1.0 / FPS
        pygame.image.save(canvas, args.capture)
        print("captured:", args.capture, "t=%.2fs" % t)
        return

    if args.demo:
        run_splash()
        pygame.quit()
        return

    run_splash()


if __name__ == "__main__":
    main()
