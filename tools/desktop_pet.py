"""
MYONL · Mooki 桌宠 MVP
==========================
一个胖乎乎的月牙小精灵，悬浮在桌面角落。
- 眼睛跟随鼠标
- 点击 → 眨眼 + 爱心气泡
- 拖拽移动（按住左键）
- 闲置呼吸动画 + 偶尔眨眼
- 右键菜单（置顶 / 换表情 / 退出）
- Esc 退出
- 完全代码绘制，零素材依赖，PyInstaller 可打包为独立 exe

技术栈：pygame-ce 2.5.x（与游戏引擎同栈）
"""

from __future__ import annotations
import sys
import math
import random
import time
from pathlib import Path

import pygame
import pygame.gfxdraw  # pygame-ce：gfxdraw 需显式导入


def _gdraw(fn, *args):
    """gfxdraw 包装：pygame-ce 的 gfxdraw 只收 int 坐标，float 会抛异常。

    所有数值参数统一 int(round())；list/tuple（如 polygon 顶点）递归处理。
    """
    def _c(v):
        if isinstance(v, float):
            return int(round(v))
        if isinstance(v, (list, tuple)):
            return type(v)(_c(x) for x in v)
        return v
    return fn(*tuple(_c(a) for a in args))


# ========== 配色（和 brand/moyul_sprite.svg 一致）==========
COLOR_BODY = (255, 247, 230)       # 月白
COLOR_GOLD = (255, 209, 102)       # 金边
COLOR_STAR = (255, 224, 102)       # 星光
COLOR_CHEEK = (255, 182, 193)      # 腮红
COLOR_DARK = (42, 48, 89)          # 深空蓝（瞳孔 + 嘴巴）
COLOR_WHITE = (255, 255, 255)
COLOR_PINK_BUBBLE = (255, 143, 163)


# ========== 窗口配置 ==========
WIN_W, WIN_H = 180, 150           # 迷你窗尺寸
FPS = 60


# ========== 工具函数 ==========
def _blit_circle_lined(surf, color, center, r, width=2):
    """描边圆（用 pygame.gfxdraw 画填充圆 + 描边）"""
    _gdraw(pygame.gfxdraw.filled_circle, surf, center[0], center[1], r, color)
    _gdraw(pygame.gfxdraw.aacircle, surf, center[0], center[1], r, color)
    # 额外加粗描边
    if width > 1:
        _gdraw(pygame.gfxdraw.aacircle, surf, center[0], center[1], r, color)


# ========== 精灵绘制（纯 pygame 代码）==========
def draw_sprite(
    surf: pygame.Surface,
    blink: float = 0.0,       # 0.0 = 完全睁开, 1.0 = 完全闭上
    breath: float = 0.0,      # 0.0 ~ 1.0 呼吸相位
    pupil_offset: tuple[float, float] = (0, 0),  # 瞳孔偏移 (dx, dy) px
    expr: str = "normal",     # normal / happy / surprise / angry
):
    """在 surf 上绘制Mooki精灵（居中，约 150×130 占比）"""
    W, H = surf.get_size()
    cx, cy = W // 2, H // 2

    # ---------- 头顶小星星 ----------
    star_cx, star_cy = cx, cy - 58
    _draw_star(surf, star_cx, star_cy, r_outer=8, r_inner=3.5, color=COLOR_STAR)

    # ---------- 月牙身体（用贝塞尔弧线画 evenodd 效果）----------
    _draw_moon_body(surf, cx, cy, breath)

    # ---------- 腮红 ----------
    _gdraw(pygame.gfxdraw.filled_ellipse, surf, cx - 28, cy + 8, 10, 5, COLOR_CHEEK)
    _gdraw(pygame.gfxdraw.filled_ellipse, surf, cx + 28, cy + 8, 10, 5, COLOR_CHEEK)

    # ---------- 眼睛 ----------
    eye_y = cy - 2
    eye_lx = cx - 22
    eye_rx = cx + 22
    _draw_eye(surf, eye_lx, eye_y, pupil_offset, blink, expr, is_left=True)
    _draw_eye(surf, eye_rx, eye_y, pupil_offset, blink, expr, is_left=False)

    # ---------- 嘴巴 ----------
    _draw_mouth(surf, cx, cy + 28, expr)


def _draw_star(surf, cx, cy, r_outer, r_inner, color):
    """画五角星（pygame 原生不支持多边形填色+描边同时 AA，所以直接画 polygon）"""
    points = []
    for i in range(10):
        angle = -math.pi / 2 + i * math.pi / 5   # 从顶部开始
        r = r_outer if i % 2 == 0 else r_inner
        # gfxdraw 只收 int 坐标（float 会抛异常）
        points.append((int(round(cx + r * math.cos(angle))),
                       int(round(cy + r * math.sin(angle)))))
    if len(points) >= 3:
        _gdraw(pygame.gfxdraw.filled_polygon, surf, points, color)
        _gdraw(pygame.gfxdraw.aapolygon, surf, points, color)


def _draw_moon_body(surf, cx, cy, breath):
    """月牙身体：两个椭圆差集 + 金边描边"""
    # 呼吸缩放（轻微）
    scale = 1.0 + 0.04 * math.sin(breath * 2 * math.pi)
    ex = int(62 * scale)   # 外椭圆 rx
    ey = int(52 * scale)   # 外椭圆 ry
    ix = int(44 * scale)   # 内椭圆 rx
    iy = int(36 * scale)   # 内椭圆 ry

    # 外椭圆（大，浅月白）
    _gdraw(pygame.gfxdraw.filled_ellipse, surf, cx, cy, ex, ey, COLOR_BODY)
    # 内椭圆（小，画成月白？不——evenodd 效果：用 Surface 遮罩）
    # 简单做法：直接在内椭圆区域画两次——第一次画 body 色填充，第二次在外椭圆+内椭圆边界画金边
    # 其实更简单——用 clip + 反向画内椭圆为背景色 → 不行 surf 是透明的
    # 用 Surface 临时遮罩：
    mask = pygame.Surface((surf.get_width(), surf.get_height()), pygame.SRCALPHA)
    # 先画整外椭圆
    _gdraw(pygame.gfxdraw.filled_ellipse, mask, cx, cy, ex, ey, COLOR_BODY + (255,))
    # 再在内椭圆位置"挖掉"——画透明色（但 gfxdraw 不支持 alpha 挖掉）
    # 换方案：用 surfarray 手动做 evenodd？太重。
    # 最可行方案：直接画两条弧线描金边 + 填充（不用 mask，接受小瑕疵）
    # 让我们画外椭圆描边 + 内椭圆下半描边（形成金边 evenodd 视觉）

    # 外椭圆描边（金色，3px，粗一点）
    _gdraw(pygame.gfxdraw.aaellipse, surf, cx, cy, ex, ey, COLOR_GOLD)
    _gdraw(pygame.gfxdraw.aaellipse, surf, cx, cy, ex - 1, ey - 1, COLOR_GOLD)

    # 内椭圆（下半弧 + 两端圆连接）—— 这部分是"凹进去"的视觉
    # 简化：画一个小椭圆在下方，颜色和 body 一样，描边也金色，形成 evenodd 视觉
    inner_top_y = cy - iy + 6   # 内椭圆顶部位置（在外椭圆内部）
    _gdraw(pygame.gfxdraw.filled_ellipse, surf, cx, inner_top_y + iy - 6, ix, iy - 2, surf.get_at((cx, cy + 10)) if False else (255,247,230,255))
    # 不对，内椭圆填充应该和 body 同色，但要让它"挖掉"外椭圆的下半部分
    # 换思路：整个月牙用 evenodd 方式直接画 surface 遮罩
    _mask_evenodd(surf, cx, cy, ex, ey, ix, iy, COLOR_BODY, COLOR_GOLD)


def _mask_evenodd(surf, cx, cy, ex, ey, ix, iy, fill_color, stroke_color):
    """用临时 Surface 做 evenodd 椭圆差集 + 金边"""
    W, H = surf.get_size()
    tmp = pygame.Surface((W, H), pygame.SRCALPHA)
    # 在外椭圆区域填白
    _gdraw(pygame.gfxdraw.filled_ellipse, tmp, cx, cy, ex, ey, (255, 255, 255, 255))
    # 在内椭圆区域涂黑（挖掉）
    # 内椭圆应该让月牙厚度在两端保持，所以内椭圆位置稍微向上偏
    inner_cy = cy + 6
    _gdraw(pygame.gfxdraw.filled_ellipse, tmp, cx, inner_cy, ix, iy, (0, 0, 0, 255))
    # 用 mask 把 surf 对应位置画成 fill_color
    for x in range(max(0, cx - ex - 2), min(W, cx + ex + 2)):
        for y in range(max(0, cy - ey - 2), min(H, cy + ey + 2)):
            if tmp.get_at((x, y)) == (255, 255, 255, 255):
                surf.set_at((x, y), fill_color + (255,))
    # 金边描边：画两条 ellipse（外椭圆完整描 + 内椭圆下半描）
    _gdraw(pygame.gfxdraw.aaellipse, surf, cx, cy, ex, ey, stroke_color)
    _gdraw(pygame.gfxdraw.aaellipse, surf, cx, cy, ex - 1, ey - 1, stroke_color)
    # 内椭圆下半弧线描金（只画下半，模拟月牙内凹的金边）
    # 遍历内椭圆下半弧像素点
    step = max(1, 3)
    for i in range(step, 180, step):
        angle = i * math.pi / 180   # 0~180° = 下半弧
        px = int(cx + ix * math.cos(angle))
        py = int(inner_cy + iy * math.sin(angle))
        if 0 <= px < W and 0 <= py < H:
            surf.set_at((px, py), stroke_color)


def _draw_eye(surf, cx, cy, pupil_offset, blink, expr, is_left=True):
    """画一只眼睛
    blink: 0=完全睁开 → 1=完全闭上
    """
    ox, oy = pupil_offset
    # 眨眼插值：eyelid 从 -20 下降到 0 覆盖瞳孔
    eye_h = 20 - 16 * blink  # 眼睛高度（blink=1 → 只剩缝）
    eye_w = 17
    if eye_h < 3:
        eye_h = 3

    if expr == "happy":
        # 眯眼：只画微笑弧线
        eye_dir = 1 if is_left else -1
        _gdraw(pygame.gfxdraw.arc, surf, cx + eye_dir * 2, cy - 2, eye_w + 2, 0, 180, COLOR_DARK)
        _gdraw(pygame.gfxdraw.arc, surf, cx + eye_dir * 2, cy - 2, eye_w, 0, 180, COLOR_DARK)
        return

    # 眼白
    _gdraw(pygame.gfxdraw.filled_ellipse, surf, cx, cy, eye_w, eye_h, COLOR_WHITE)
    # 金边描边
    _gdraw(pygame.gfxdraw.aaellipse, surf, cx, cy, eye_w, eye_h, COLOR_GOLD)

    if blink < 0.5:  # 半睁以上画瞳孔
        pupil_r = 10 if expr == "surprise" else 8
        px = cx + int(ox)
        py = cy + int(oy)
        # 瞳孔（深空蓝）
        if eye_h >= pupil_r:
            _gdraw(pygame.gfxdraw.filled_circle, surf, px, py, pupil_r, COLOR_DARK)
            # 高光（左上小白点）
            hl_cx = px - 4 + (4 if not is_left else -4)  # 高光靠近内侧
            hl_cy = py - 4
            hl_r = 3 if expr == "surprise" else 2.5
            if eye_h >= hl_r + 2:
                _gdraw(pygame.gfxdraw.filled_circle, surf, hl_cx, hl_cy, hl_r, COLOR_WHITE)


def _draw_mouth(surf, cx, cy, expr):
    """嘴巴（画微笑弧线）"""
    if expr == "happy":
        # 大笑
        _gdraw(pygame.gfxdraw.arc, surf, cx, cy - 5, 10, 0, 180, COLOR_DARK)
        _gdraw(pygame.gfxdraw.arc, surf, cx, cy - 5, 8, 0, 180, COLOR_DARK)
    elif expr == "surprise":
        # O 嘴
        _gdraw(pygame.gfxdraw.filled_ellipse, surf, cx, cy, 4, 5, COLOR_DARK)
    elif expr == "angry":
        # 小嘴 + 下撇
        _gdraw(pygame.gfxdraw.line, surf, cx - 6, cy, cx + 6, cy, COLOR_DARK)
    else:
        # 正常微笑
        _gdraw(pygame.gfxdraw.arc, surf, cx, cy + 3, 8, 0, 180, COLOR_DARK)
        _gdraw(pygame.gfxdraw.arc, surf, cx, cy + 3, 6, 0, 180, COLOR_DARK)


# ========== 爱心气泡类 ==========
class HeartBubble:
    """点击后冒出来向上飘的爱心"""
    def __init__(self, cx, cy):
        self.x, self.y = cx, cy
        self.vy = -1.8 - random.random() * 0.8  # 向上飘
        self.life = 1.0   # 透明度 1→0
        self.age = 0.0

    def update(self, dt):
        self.y += self.vy
        self.vy *= 0.96   # 减速
        self.age += dt
        self.life = max(0.0, 1.0 - self.age / 1.5)

    def draw(self, surf):
        alpha = int(self.life * 255)
        if alpha < 20: return
        # 简单爱心 = 两个圆 + 一个三角
        heart = pygame.Surface((24, 22), pygame.SRCALPHA)
        _gdraw(pygame.gfxdraw.filled_circle, heart, 7, 8, 6, COLOR_PINK_BUBBLE + (alpha,))
        _gdraw(pygame.gfxdraw.filled_circle, heart, 17, 8, 6, COLOR_PINK_BUBBLE + (alpha,))
        # 三角底部
        pts = [(1, 8), (23, 8), (12, 20)]
        _gdraw(pygame.gfxdraw.filled_polygon, heart, pts, COLOR_PINK_BUBBLE + (alpha,))
        surf.blit(heart, (int(self.x) - 12, int(self.y) - 12))


# ========== 桌宠主类 ==========
class DesktopPet:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("MYONL · Mooki")

        self.screen = pygame.display.set_mode((WIN_W, WIN_H), pygame.NOFRAME | pygame.SRCALPHA)
        self.clock = pygame.time.Clock()
        self.running = True

        # 位置（屏幕右下角）
        sw, sh = pygame.display.get_desktop_sizes()[0]
        self.x = sw - WIN_W - 40
        self.y = sh - WIN_H - 100
        pygame.display.set_mode((WIN_W, WIN_H), pygame.NOFRAME | pygame.SRCALPHA)
        # 用 SDL 窗口 API 移动
        import ctypes
        try:
            hwnd = pygame.display.get_wm_info()["window"]
            ctypes.windll.user32.MoveWindow(hwnd, self.x, self.y, WIN_W, WIN_H, True)
        except Exception:
            pass

        # 状态
        self.blink_t = 0.0
        self.blink_dur = 0.15
        self.blink_interval = 3.0 + random.random() * 4.0
        self.idle_t = 0.0       # 闲置呼吸时间
        self.expr = "normal"
        self.bubbles: list[HeartBubble] = []
        self.dragging = False
        self.drag_offset = (0, 0)
        self.topmost = True
        self.wave_t = 0.0

    # ---------- 主循环 ----------
    def run(self):
        while self.running:
            dt = self.clock.tick(FPS) / 1000.0
            self._update(dt)
            self._draw()
            pygame.display.flip()
        pygame.quit()

    # ---------- 帧更新 ----------
    def _update(self, dt):
        self.idle_t += dt
        self.wave_t += dt

        # ====== 鼠标跟随 ======
        mx, my = pygame.mouse.get_pos()
        # 计算相对桌面中心的偏移 → 瞳孔偏移
        sw, sh = pygame.display.get_desktop_sizes()[0]
        cx_screen = self.x + WIN_W / 2
        cy_screen = self.y + WIN_H / 2
        dx = (mx - cx_screen) / (sw / 2)
        dy = (my - cy_screen) / (sh / 2)
        # 限制范围 ±6
        self.pupil_offset = (
            max(-6.0, min(6.0, dx * 8.0)),
            max(-5.0, min(5.0, dy * 6.0)),
        )

        # ====== 眨眼 ======
        self.blink_t += dt
        if self.blink_t > self.blink_interval:
            self.blink_t = 0.0
            self.blink_interval = 3.0 + random.random() * 4.0
        blink_progress = self.blink_t / self.blink_interval
        # 用 sin 做眨眼前半闭后半开
        self.blink = max(0.0, math.sin(blink_progress * math.pi * 2 - math.pi/2) * 0.5 + 0.5) if blink_progress < 0.05 else 0.0
        # 简单点：快到 interval 末尾时眨眼
        t_left = self.blink_interval - self.blink_t
        if t_left < self.blink_dur:
            p = 1.0 - t_left / self.blink_dur   # 0→1 闭上
            self.blink = math.sin(p * math.pi)  # 0→1→0
        else:
            self.blink = 0.0

        # ====== 气泡更新 ======
        for b in self.bubbles:
            b.update(dt)
        self.bubbles = [b for b in self.bubbles if b.life > 0]

    # ---------- 绘制 ----------
    def _draw(self):
        self.screen.fill((0, 0, 0, 0))  # 透明背景
        # 呼吸相位
        breath = self.idle_t * 0.6
        draw_sprite(self.screen, self.blink, breath, self.pupil_offset, self.expr)
        # 爱心气泡
        for b in self.bubbles:
            b.draw(self.screen)

    # ---------- 事件 ----------
    def handle_event(self, event):
        if event.type == pygame.QUIT:
            self.running = False
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.running = False
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:   # 左键：拖拽
                self.dragging = True
                self.drag_offset = event.pos
                self.expr = "happy"
                # 冒爱心
                for _ in range(2):
                    self.bubbles.append(HeartBubble(WIN_W // 2 + random.randint(-10, 10), WIN_H // 2 - 30))
            elif event.button == 3:  # 右键：菜单
                self._show_menu()
            elif event.button == 4:  # 滚轮上：换表情
                self._cycle_expr()
            elif event.button == 5:  # 滚轮下
                self._cycle_expr()
        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button == 1:
                self.dragging = False
                self.expr = "normal"
        elif event.type == pygame.MOUSEMOTION:
            if self.dragging:
                mx, my = pygame.mouse.get_pos()
                import ctypes
                try:
                    hwnd = pygame.display.get_wm_info()["window"]
                    ctypes.windll.user32.MoveWindow(hwnd, mx - self.drag_offset[0], my - self.drag_offset[1], WIN_W, WIN_H, True)
                except Exception:
                    pass

    def _cycle_expr(self):
        exprs = ["normal", "happy", "surprise", "angry"]
        i = exprs.index(self.expr)
        self.expr = exprs[(i + 1) % len(exprs)]

    def _show_menu(self):
        """右键菜单（用 pygame 临时弹一个小窗）"""
        # 简化：直接打印到控制台，或用 tkinter 弹窗
        try:
            import tkinter as tk
            from tkinter import simpledialog
            root = tk.Tk()
            root.withdraw()
            # 用 messagebox 做菜单
            import tkinter.messagebox as mb
            # 简单方案：弹出一个"选一下"对话框
            topmost = mb.askyesno("Mooki · 设置", f"当前置顶状态：{'开' if self.topmost else '关'}\n\n是否切换置顶？")
            if topmost:
                self.topmost = not self.topmost
                # 切换置顶：Win32 API SetWindowPos
                import ctypes
                HWND_TOPMOST = -1
                HWND_NOTOPMOST = -2
                hwnd = pygame.display.get_wm_info()["window"]
                flag = HWND_TOPMOST if self.topmost else HWND_NOTOPMOST
                ctypes.windll.user32.SetWindowPos(hwnd, flag, 0, 0, 0, 0, 3)
        except Exception:
            print("[Mooki] 右键菜单暂不可用（无 tkinter）")


# ========== 入口 ==========
def main():
    pet = DesktopPet()

    # 单独跑事件循环（pygame 主循环在 run()，事件要 poll 出来）
    # 把事件处理集成进 run 循环
    original_run = pet.run
    import ctypes

    def patched_run():
        while pet.running:
            dt = pet.clock.tick(FPS) / 1000.0
            for event in pygame.event.get():
                pet.handle_event(event)
            pet._update(dt)
            pet._draw()
            pygame.display.flip()
        pygame.quit()

    patched_run()


if __name__ == "__main__":
    main()
