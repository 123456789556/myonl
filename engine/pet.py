# -*- coding: utf-8 -*-
"""
Mooki 桌宠 v2 —— 发光小团子（伪 Live2D 视差 · 真透明窗口）
=============================================================
运行: py -m engine.pet [--capture 路径.png] [--frames N]（源码）
      editor.exe --pet                                      （发行版，默认关闭）

交互:
  滚轮        : 切换表情 (normal / happy / surprise / angry)
  = / -       : 放大 / 缩小（0.8~1.5，位置与大小会记住）
  左键单击拖  : 移动桌宠窗口（松手吸附角落）
  左键双击    : 弹爱心气泡
  右键        : 弹出菜单（打开 MYONL 引擎 / 退出）
  鼠标感知    : 以桌宠中心为圆心、半径 3R 的圆形范围，移出则静止不跟随
  Esc         : 退出

透明实现:
  离屏 32 位 SRCALPHA surface 渲染 → UpdateLayeredWindow 逐帧上传
  (pygame display 的 SRCALPHA 在本机无效, 只能走 layered 上传)

预留接口:
  import_sprite(path)      — 导入外部 PNG 替换身体层(可导入)
  register_action(name, fn)— 注册扩展交互回调(插件接口)
"""

import argparse
import ctypes
import json
import math
import os
import random
import sys
from ctypes import wintypes

import pygame

# ---------------- Win32 ----------------
user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TOOLWINDOW = 0x00000080
HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOACTIVATE = 0x0010
ULW_ALPHA = 2
AC_SRC_OVER = 0x00
AC_SRC_ALPHA = 0x01


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class SIZE(ctypes.Structure):
    _fields_ = [("cx", ctypes.c_long), ("cy", ctypes.c_long)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int32),
                ("biHeight", ctypes.c_int32), ("biPlanes", ctypes.c_uint16),
                ("biBitCount", ctypes.c_uint16), ("biCompression", ctypes.c_uint32),
                ("biSizeImage", ctypes.c_uint32), ("biXPelsPerMeter", ctypes.c_int32),
                ("biYPelsPerMeter", ctypes.c_int32), ("biClrUsed", ctypes.c_uint32),
                ("biClrImportant", ctypes.c_uint32)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER),
                ("bmiColors", ctypes.c_uint32 * 3)]


BLENDFUNCTION = ctypes.c_ubyte * 4


def get_hwnd():
    return pygame.display.get_wm_info().get("window")


def set_window_style(hwnd):
    """加 LAYERED(手动管理) + TOOLWINDOW(隐藏任务栏)"""
    ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex | WS_EX_LAYERED | WS_EX_TOOLWINDOW)


def set_topmost(hwnd, on=True):
    user32.SetWindowPos(hwnd, HWND_TOPMOST if on else HWND_NOTOPMOST,
                        0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)


def get_cursor():
    pt = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def get_window_rect(hwnd):
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top


# ---------------- Layered 上传 ----------------
_hdc_mem = None
_dib_bits = None
_dib = None


def init_layered(hwnd, w, h):
    global _hdc_mem, _dib_bits, _dib
    dc_screen = user32.GetDC(None)
    _hdc_mem = gdi32.CreateCompatibleDC(dc_screen)
    bih = BITMAPINFOHEADER()
    bih.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bih.biWidth = w
    bih.biHeight = -h          # 负高度 = 顶向下(DIB 自上而下)
    bih.biPlanes = 1
    bih.biBitCount = 32
    bih.biCompression = 0      # BI_RGB
    bmi = BITMAPINFO()
    bmi.bmiHeader = bih
    _dib_bits = ctypes.c_void_p()
    _dib = gdi32.CreateDIBSection(dc_screen, ctypes.byref(bmi), 0,
                                  ctypes.byref(_dib_bits), None, 0)
    gdi32.SelectObject(_hdc_mem, _dib)
    user32.ReleaseDC(None, dc_screen)


def upload_layer(hwnd, surf):
    """把 32 位 SRCALPHA surface 上传为窗口像素(真透明)"""
    data = pygame.image.tostring(surf, "BGRA", False)
    if _dib_bits is None:
        return
    ctypes.memmove(_dib_bits, data, len(data))
    pos = POINT(0, 0)
    size = SIZE(surf.get_width(), surf.get_height())
    src = POINT(0, 0)
    blend = (BLENDFUNCTION)(AC_SRC_OVER, 0, 255, AC_SRC_ALPHA)
    user32.UpdateLayeredWindow(hwnd, None, ctypes.byref(pos), ctypes.byref(size),
                               _hdc_mem, ctypes.byref(src), 0,
                               ctypes.byref(blend), ULW_ALPHA)


def resize_window(hwnd, scale):
    """按缩放系数改窗口像素尺寸（保持中心不变），重建 layered 位图。"""
    w, h = max(1, int(W * scale)), max(1, int(H * scale))
    wx, wy = get_window_rect(hwnd)
    nwx = wx - (w - W) // 2
    nwy = wy - (h - H) // 2
    user32.SetWindowPos(hwnd, 0, nwx, nwy, w, h,
                        SWP_NOACTIVATE | 0x0004)  # SWP_NOZORDER
    init_layered(hwnd, w, h)


# ---------------- 位置 / 大小记忆（用户目录，删游戏不丢） ----------------

_CFG_PATH = os.path.join(os.path.expanduser("~"), ".mooki.json")


def _load_cfg() -> dict:
    try:
        with open(_CFG_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_cfg(cfg: dict) -> None:
    try:
        with open(_CFG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False)
    except OSError:
        pass


def _remember(hwnd, scale) -> None:
    """把当前窗口位置与缩放写进记忆文件（拖动松手/缩放/退出时调用）。"""
    cfg = _load_cfg()
    cfg["pos"] = list(get_window_rect(hwnd))
    cfg["scale"] = round(float(scale), 2)
    _save_cfg(cfg)


def snap_to_edge(hwnd, scale):
    """拖动松手后，若靠近屏幕边缘则吸附到最近的角/边。"""
    w, h = max(1, int(W * scale)), max(1, int(H * scale))
    wx, wy = get_window_rect(hwnd)
    sw = user32.GetSystemMetrics(0)   # SM_CXSCREEN
    sh = user32.GetSystemMetrics(1)   # SM_CYSCREEN
    M = 80
    nx, ny = wx, wy
    if wx < M:
        nx = 0
    elif wx + w > sw - M:
        nx = sw - w
    if wy < M:
        ny = 0
    elif wy + h > sh - M:
        ny = sh - h
    if (nx, ny) != (wx, wy):
        user32.SetWindowPos(hwnd, 0, nx, ny, 0, 0,
                            SWP_NOSIZE | SWP_NOACTIVATE | 0x0004)


TPM_LEFTBUTTON = 0x0000
TPM_RETURNCMD = 0x0100


def show_menu(hwnd, scale=1.0):
    """右键弹出菜单：打开 MYONL 引擎 / 退出桌宠（Win32 TrackPopupMenu）"""
    import subprocess
    menu = user32.CreatePopupMenu()
    user32.AppendMenuW(menu, 0x0, 1, "打开 MYONL 引擎")
    user32.AppendMenuW(menu, 0x0, 2, "退出桌宠")
    pt = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    user32.SetForegroundWindow(hwnd)
    cmd = user32.TrackPopupMenu(menu, TPM_LEFTBUTTON | TPM_RETURNCMD,
                                pt.x, pt.y, 0, hwnd, None)
    user32.DestroyMenu(menu)
    if cmd == 1:
        if getattr(sys, "frozen", False):
            # 冻结版：sys.executable 就是 editor.exe，直接再启动一个编辑器窗口
            subprocess.Popen([sys.executable])
        else:
            ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            subprocess.Popen([sys.executable, "-m", "engine.editor_app"], cwd=ROOT)
    elif cmd == 2:
        _remember(hwnd, scale)   # 退出前记住位置/大小
        pygame.quit()
        os._exit(0)


# ---------------- 预设参数 ----------------
W, H = 240, 280          # 窗口基准尺寸(含光晕)
CX, CY = W // 2, 150     # 团子中心
BODY_R = 72              # 身体半径
MOON_R = 26              # 月牙半径
STAR_N = 8               # 星尘数量
SCALE_MIN, SCALE_MAX = 0.8, 1.5   # 桌宠尺寸缩放范围（1.0 = Trae 基准）
SENSE_FACTOR = 3.0       # 感知范围 = 桌宠半径 R × 3（圆形，移出则静止）

C_GLOW = (124, 107, 255)
C_BODY_TOP = (244, 240, 255)     # 团子高光（比原先深一点，更柔和）
C_BODY_BOT = (204, 195, 240)     # 团子主体（加深，紫调更明显）
C_MOON = (248, 248, 255)     # 头饰月牙：白色（更温和）
C_MOON_HI = (255, 255, 255)
C_IRIS = (56, 46, 140)
C_PUPIL = (24, 18, 66)
C_BLUSH = (255, 170, 178)
C_MOUTH = (120, 84, 160)


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


# ---------------- 预渲染静态层 ----------------
def make_body_surface():
    s = pygame.Surface((W, H), pygame.SRCALPHA)
    # 实心身体（去掉背后大光晕圆盘，更干净）
    body_s = pygame.Surface((BODY_R * 2, BODY_R * 2), pygame.SRCALPHA)
    pygame.draw.ellipse(body_s, (*C_BODY_BOT, 255), body_s.get_rect())
    s.blit(body_s, (CX - BODY_R, CY - BODY_R))
    # 顶部柔和高光（贴住身体，不外扩成圆盘）
    hi = pygame.Surface((BODY_R * 2, BODY_R * 2), pygame.SRCALPHA)
    pygame.draw.ellipse(hi, (*C_BODY_TOP, 120),
                        (0, 0, BODY_R * 2, int(BODY_R * 1.5)))
    s.blit(hi, (CX - BODY_R - 4, CY - BODY_R - 10))
    # 月亮：标准新月（去掉外圈白色描边盘）
    moon = pygame.Surface((MOON_R * 2 + 14, MOON_R * 2 + 14), pygame.SRCALPHA)
    mx, my = MOON_R + 7, MOON_R + 7
    pygame.draw.circle(moon, (*C_MOON, 255), (mx, my), MOON_R)
    pygame.draw.circle(moon, (0, 0, 0, 0), (mx + 10, my - 6), int(MOON_R * 0.68))
    moon_x, moon_y = CX - MOON_R - 5 + 20, CY - BODY_R - 14
    s.blit(moon, (moon_x, moon_y))
    # 白色月牙周围点缀柔和小圆星（圆形、白色，更柔和）
    mc = (MOON_R + 5 + 9, MOON_R + 5 - 5)  # 月牙视觉中心
    for sx, sy, sr, scol in [(-26, -2, 6, (255, 255, 255, 215)),
                             (26, -12, 5, (255, 255, 255, 195)),
                             (22, 14, 4, (255, 255, 255, 175))]:
        st = pygame.Surface((sr * 2 + 4, sr * 2 + 4), pygame.SRCALPHA)
        pygame.draw.circle(st, scol, (sr + 2, sr + 2), sr)
        s.blit(st, (moon_x + mc[0] + sx - sr - 2, moon_y + mc[1] + sy - sr - 2))
    return s


def make_star(radius, color, alpha):
    # 圆润"球星"：中心球 + 四角圆芒，柔和温和
    s = pygame.Surface((radius * 2 + 6, radius * 2 + 6), pygame.SRCALPHA)
    c = radius + 3
    pygame.draw.circle(s, (*color, alpha), (c, c), int(radius * 0.68))
    mr = max(2, int(radius * 0.30))
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        pygame.draw.circle(s, (*color, alpha),
                           (c + int(dx * radius * 0.92), c + int(dy * radius * 0.92)), mr)
    return s


# ---------------- 表情 ----------------
def draw_eye(surf, ex, ey, r, expr, blink, look):
    if blink:
        pygame.draw.arc(surf, C_IRIS, (ex - r, ey - int(r * 0.55),
                                       r * 2, int(r * 1.1)),
                        0.15 * math.pi, 0.85 * math.pi, 4)
        return
    pygame.draw.ellipse(surf, (255, 255, 255),
                        (ex - r, ey - int(r * 0.82), r * 2, int(r * 1.64)))
    ir = int(r * 0.78)
    irx, iry = ex + look[0], ey + look[1]
    pygame.draw.circle(surf, C_IRIS, (irx, iry), ir)
    pygame.draw.circle(surf, C_PUPIL, (irx, iry), int(ir * 0.52))
    pygame.draw.circle(surf, (255, 255, 255),
                       (irx - int(ir * 0.34), iry - int(ir * 0.34)), int(ir * 0.22))
    if expr == "surprise":
        pygame.draw.circle(surf, (255, 255, 255),
                           (irx + int(ir * 0.2), iry + int(ir * 0.2)), int(ir * 0.10))


def draw_mouth(surf, mx, my, expr, t):
    w, mcol = 26, C_MOUTH
    if expr == "happy":
        pygame.draw.arc(surf, mcol, (mx - w, my - 12, w * 2, w),
                        0.15 * math.pi, 0.85 * math.pi, 4)
        pygame.draw.circle(surf, (255, 130, 140), (mx + 8, my - 2), 3)
    elif expr == "surprise":
        pygame.draw.circle(surf, mcol, (mx, my), 9)
        pygame.draw.circle(surf, (255, 120, 130), (mx, my), 5)
    elif expr == "angry":
        pygame.draw.arc(surf, mcol, (mx - w, my + 2, w * 2, int(w * 0.7)),
                        1.15 * math.pi, 1.85 * math.pi, 4)
    else:
        pygame.draw.arc(surf, mcol, (mx - w, my - 8, w * 2, int(w * 0.85)),
                        0.2 * math.pi, 0.8 * math.pi, 4)


def draw_brow(surf, ex, ey, expr):
    if expr == "surprise":
        for k in (-1, 1):
            pygame.draw.arc(surf, C_IRIS,
                            (ex + k * 14 - 12, ey - 34, 26, 16),
                            0.0 * math.pi, 1.0 * math.pi, 3)
    elif expr == "angry":
        for k in (-1, 1):
            pygame.draw.arc(surf, C_IRIS,
                            (ex + k * 12 - 14, ey - 28, 30, 16),
                            1.1 * math.pi, 1.9 * math.pi, 3)


# ---------------- 插件/导入接口 ----------------
_PLUGIN_ACTIONS = {}
_EXTERNAL_BODY = None


def register_action(name, fn):
    _PLUGIN_ACTIONS[name] = fn


def import_sprite(path):
    global _EXTERNAL_BODY
    img = pygame.image.load(path).convert_alpha()
    _EXTERNAL_BODY = pygame.transform.smoothscale(
        img, (int(BODY_R * 2.4), int(BODY_R * 2.4)))
    return True


# ---------------- SVG 分层帧加载 ----------------
_LAYER_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "brand", "mooki_layers")
SVG_SCALE = 0.60          # 400x400 SVG → 240x240，贴入 240x280 窗口
_LAYER_NAMES = ["glow", "body", "cheeks", "star", "dust",
                "eyes", "pupils", "mouth_normal",
                "expr_happy", "expr_surprise", "expr_angry"]


def load_svg_layers():
    """加载 brand/mooki_layers/ 下的分层 PNG，缩放到 SVG_SCALE。

    返回 dict[name -> Surface]；缺图时返回空 dict，main 走代码绘制兜底。
    """
    layers = {}
    if not os.path.isdir(_LAYER_DIR):
        return layers
    for name in _LAYER_NAMES:
        path = os.path.join(_LAYER_DIR, f"mooki_{name}.png")
        if not os.path.isfile(path):
            return {}   # 任一缺失则整体回退到代码绘制
        img = pygame.image.load(path).convert_alpha()
        sw, sh = int(img.get_width() * SVG_SCALE), int(img.get_height() * SVG_SCALE)
        layers[name] = pygame.transform.smoothscale(img, (sw, sh))
    return layers


# ---------------- 主程序 ----------------
def main(capture=None, capture_after=90, start_scale=1.0):
    # 位置/大小记忆：上次拖动与缩放的结果优先，其次默认右上角
    cfg = _load_cfg()
    try:
        scale0 = float(cfg.get("scale") or start_scale)
    except (TypeError, ValueError):
        scale0 = start_scale
    scale0 = max(SCALE_MIN, min(SCALE_MAX, scale0))
    sw = user32.GetSystemMetrics(0)   # SM_CXSCREEN
    sh = user32.GetSystemMetrics(1)   # SM_CYSCREEN
    pos = cfg.get("pos")
    if (isinstance(pos, list) and len(pos) == 2
            and all(isinstance(v, int) for v in pos)
            and -W < pos[0] < sw and -H < pos[1] < sh):
        wx, wy = pos
    else:
        wx, wy = max(0, sw - W), 0
    os.environ["SDL_VIDEO_WINDOW_POS"] = f"{wx},{wy}"
    pygame.init()
    screen = pygame.display.set_mode((W, H), pygame.NOFRAME)
    pygame.display.set_caption("MYONL · Mooki")
    hwnd = get_hwnd()
    set_window_style(hwnd)
    set_topmost(hwnd, True)
    init_layered(hwnd, W, H)
    if abs(scale0 - 1.0) > 1e-6:
        resize_window(hwnd, scale0)   # 恢复上次大小

    # 离屏 32 位渲染层(带 alpha)
    canvas = pygame.Surface((W, H), pygame.SRCALPHA)

    # 加载 SVG 分层帧；缺图时 layers 为空，走代码绘制兜底
    layers = load_svg_layers()
    svg_ox, svg_oy = 0, 0   # 分层帧在 canvas 上的基准偏移（240x240 贴 240x280）

    clock = pygame.time.Clock()
    body = make_body_surface()
    stars = []
    for i in range(STAR_N):
        ang = i * math.pi * 2 / STAR_N + random.uniform(0, 0.6)
        rad = random.uniform(BODY_R + 30, BODY_R + 54)
        spd = random.uniform(0.35, 0.6)   # 同方向，顺滑环绕
        r = random.choice([4, 5, 6])
        stars.append([ang, rad, spd, r, (255, 255, 255)])  # 统一白色

    expr = "normal"
    blink_t = random.uniform(2.0, 5.0)
    blink_now = False
    blink_until = 0.0
    t = 0.0
    hearts = []
    dragging = False
    topmost = True
    reassert_n = 0
    frame_n = 0
    scale = scale0
    if abs(scale - 1.0) > 1e-3:
        resize_window(hwnd, scale)
    grab_off = None
    last_click_t = -1.0
    last_click_pos = (0, 0)

    while True:
        dt = clock.tick(60) / 1000.0
        t += dt
        frame_n += 1
        mx, my = get_cursor()

        wx0, wy0 = get_window_rect(hwnd)
        # 感知范围：以桌宠中心为圆心、半径 = 桌宠半径 × 3（随缩放）
        sense_r = BODY_R * scale * SENSE_FACTOR
        cx_s = wx0 + CX * scale      # 桌宠中心（屏幕坐标）
        cy_s = wy0 + CY * scale
        dist = math.hypot(mx - cx_s, my - cy_s)
        if dist <= sense_r:
            lx = clamp((mx - cx_s) / sense_r, -1, 1)
            ly = clamp((my - cy_s) / sense_r, -1, 1)
        else:
            lx = ly = 0.0            # 鼠标移出感知范围 → 静止不跟随
        look = (int(lx * 7), int(ly * 7))
        head = (int(lx * 4), int(ly * 4))

        breath = 1.0 + 0.035 * math.sin(t * 2.0)

        blink_t -= dt
        if blink_t <= 0:
            blink_now = True
            blink_until = t + 0.13
            blink_t = random.uniform(2.5, 6.0)
        if blink_now and t >= blink_until:
            blink_now = False

        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                _remember(hwnd, scale)
                pygame.quit()
                return
            if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
                _remember(hwnd, scale)
                pygame.quit()
                return
            if e.type == pygame.KEYDOWN and e.key in (pygame.K_EQUALS, pygame.K_KP_PLUS):
                scale = min(SCALE_MAX, scale + 0.1)
                resize_window(hwnd, scale)
                _remember(hwnd, scale)
            if e.type == pygame.KEYDOWN and e.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
                scale = max(SCALE_MIN, scale - 0.1)
                resize_window(hwnd, scale)
                _remember(hwnd, scale)
            if e.type == pygame.MOUSEWHEEL:
                order = ["normal", "happy", "surprise", "angry"]
                expr = order[(order.index(expr) + (1 if e.y > 0 else -1)) % 4]
            if e.type == pygame.MOUSEBUTTONDOWN:
                if e.button == 1:
                    dragging = True
                    grab_off = (mx - wx0, my - wy0)   # 屏幕坐标拖拽偏移
                    now = t
                    # 双击：两次按下间隔短且位置近 → 弹爱心（单击只拖拽，不误弹）
                    if now - last_click_t < 0.35 and \
                       math.hypot(mx - last_click_pos[0],
                                  my - last_click_pos[1]) < 12:
                        for _ in range(3):
                            hearts.append([CX + random.randint(-40, 40),
                                           CY - BODY_R - 10, 255, 0.0])
                        last_click_t = -1.0
                    else:
                        last_click_t = now
                        last_click_pos = (mx, my)
                    if topmost:
                        set_topmost(hwnd, True)  # 点击即保顶，防被其他置顶窗口抢
                elif e.button == 3:
                    show_menu(hwnd, scale)   # 右键菜单：打开引擎 / 退出
            if e.type == pygame.MOUSEBUTTONUP and e.button == 1:
                dragging = False
                grab_off = None
                snap_to_edge(hwnd, scale)   # 松手后吸附角落/边缘
                _remember(hwnd, scale)      # 记住新位置

        if dragging and grab_off:
            user32.SetWindowPos(hwnd, 0, mx - grab_off[0], my - grab_off[1],
                                0, 0, SWP_NOSIZE | SWP_NOACTIVATE | 0x0004)

        # 高频保顶：每 0.5s 重新置顶——桌宠最高层级，不可被文件/视频窗口覆盖（同 Trae）
        reassert_n += 1
        if topmost and reassert_n >= 30:
            reassert_n = 0
            set_topmost(hwnd, True)

        # ---- 渲染到离屏 canvas ----
        canvas.fill((0, 0, 0, 0))

        if layers:
            # ===== SVG 分层帧视差合成 =====
            # 视差幅度：glow±2 / body±4 / eyes±6 / pupils±8 / dust反向±2
            ox_g, oy_g = int(lx * 2), int(ly * 2)
            ox_b, oy_b = int(lx * 4), int(ly * 4)
            ox_e, oy_e = int(lx * 6), int(ly * 6)
            ox_p, oy_p = int(lx * 8), int(ly * 8)
            ox_d, oy_d = int(-lx * 2), int(-ly * 2)
            # 头顶星微晃（独立于视差）
            sway_x = int(3 * math.sin(t * 1.8))
            sway_y = int(2 * math.sin(t * 2.3))
            # 呼吸：身体/脸颊轻微缩放
            br = breath
            bw = int(layers["body"].get_width() * br)
            bh = int(layers["body"].get_height() * br)

            def blit_layer(name, dx=0, dy=0, scale=1.0):
                img = layers[name]
                if abs(scale - 1.0) > 1e-3:
                    img = pygame.transform.smoothscale(
                        img, (max(1, int(img.get_width() * scale)),
                              max(1, int(img.get_height() * scale))))
                canvas.blit(img, (svg_ox + dx, svg_oy + dy))

            # 光晕（缓跟）
            blit_layer("glow", ox_g, oy_g)
            # 星尘（缓跟反向，漂浮感）
            blit_layer("dust", ox_d, oy_d)
            # 身体（中跟 + 呼吸缩放）
            body_img = pygame.transform.smoothscale(layers["body"], (bw, bh))
            canvas.blit(body_img, (svg_ox + ox_b + (layers["body"].get_width() - bw) // 2,
                                   svg_oy + oy_b + (layers["body"].get_height() - bh) // 2))
            # 头顶星（随身体 + 微晃）
            blit_layer("star", ox_b + sway_x, oy_b + sway_y)
            # 腮红（随身体）
            blit_layer("cheeks", ox_b, oy_b)

            if expr == "normal":
                # 眼白（快跟）
                blit_layer("eyes", ox_e, oy_e)
                # 瞳孔（最快跟，鼠标跟随主驱动）；眨眼时不画瞳孔
                if not blink_now:
                    blit_layer("pupils", ox_p, oy_p)
                else:
                    # 眨眼：两眼各画一道弧线
                    for k in (-1, 1):
                        ex = svg_ox + ox_e + int(144 * SVG_SCALE) + k * int(112 * SVG_SCALE)
                        ey = svg_oy + oy_e + int(236 * SVG_SCALE)
                        pygame.draw.arc(canvas, (42, 48, 89),
                                        (ex - int(21 * SVG_SCALE), ey - int(12 * SVG_SCALE),
                                         int(42 * SVG_SCALE), int(24 * SVG_SCALE)),
                                        0.15 * math.pi, 0.85 * math.pi, 3)
                # 嘴（随身体）
                blit_layer("mouth_normal", ox_b, oy_b)
            else:
                # 非默认表情：扁整张替换眼+瞳孔+嘴，速度取眼白档
                blit_layer(f"expr_{expr}", ox_e, oy_e)
        else:
            # ===== 代码绘制兜底（缺 SVG 图层时） =====
            for st in stars:
                st[0] += st[2] * dt
                sx = CX + head[0] + math.cos(st[0]) * st[1]
                sy = CY + head[1] + math.sin(st[0]) * st[1] * 0.72
                tw = int(110 + 90 * math.sin(t * 2.6 + st[0] * 4))
                sr = st[3]
                sts = pygame.Surface((sr * 2 + 6, sr * 2 + 6), pygame.SRCALPHA)
                pygame.draw.circle(sts, (*st[4], tw), (sr + 3, sr + 3), sr)
                pygame.draw.circle(sts, (*st[4], int(tw * 0.35)),
                                   (sr + 3, sr + 3), sr + 2)
                canvas.blit(sts, (int(sx - sr - 3), int(sy - sr - 3)))

            br = int(BODY_R * breath)
            if _EXTERNAL_BODY is not None:
                eb = pygame.transform.smoothscale(_EXTERNAL_BODY,
                                                  (int(br * 2.4), int(br * 2.4)))
                canvas.blit(eb, (CX + head[0] - int(br * 1.2),
                                 CY + head[1] - int(br * 1.2)))
            else:
                canvas.blit(body, (head[0], head[1]))

            ex = CX + head[0]
            ey = CY - 2 + head[1]
            draw_eye(canvas, ex - 30, ey, 17, expr, blink_now, look)
            draw_eye(canvas, ex + 30, ey, 17, expr, blink_now, look)
            draw_brow(canvas, ex, ey - 6, expr)
            draw_mouth(canvas, ex, ey + 34, expr, t)

            for k in (-1, 1):
                c = pygame.Surface((20, 14), pygame.SRCALPHA)
                pygame.draw.ellipse(c, (*C_BLUSH, 110), c.get_rect())
                canvas.blit(c, (ex + k * 52 - 10, ey + 16))

        for h in hearts[:]:
            h[3] += dt
            if h[3] > 1.2:
                hearts.remove(h)
                continue
            a = int(255 * (1 - h[3] / 1.2))
            hy = h[1] - h[3] * 34
            hs = pygame.Surface((26, 26), pygame.SRCALPHA)
            pygame.draw.circle(hs, (255, 90, 110, a), (8, 9), 8)
            pygame.draw.circle(hs, (255, 90, 110, a), (18, 9), 8)
            pygame.draw.polygon(hs, (255, 90, 110, a),
                                [(2, 12), (13, 25), (24, 12)])
            canvas.blit(hs, (h[0] - 13, int(hy) - 13))

        # 上传为窗口像素(真透明)；缩放时整体放大窗口
        surf = canvas
        if abs(scale - 1.0) > 1e-3:
            surf = pygame.transform.smoothscale(
                canvas, (max(1, int(W * scale)), max(1, int(H * scale))))
        upload_layer(hwnd, surf)

        if capture and frame_n >= capture_after:
            pygame.image.save(surf, capture)
            print("captured:", capture)
            _remember(hwnd, scale)
            pygame.quit()
            return


def cli_main(argv=None) -> int:
    """命令行入口：--capture / --frames / --scale（编辑器与源码模式共用）。"""
    ap = argparse.ArgumentParser(description="Mooki 桌宠（MYONL 引擎内置）")
    ap.add_argument("--capture", default=None,
                    help="跑若干帧后截图保存并退出(自验证用)")
    ap.add_argument("--frames", type=int, default=90)
    ap.add_argument("--scale", type=float, default=1.0,
                    help="起始缩放系数(0.8~1.5)，自验证缩放渲染")
    args = ap.parse_args(argv)
    main(capture=args.capture, capture_after=args.frames, start_scale=args.scale)
    return 0


if __name__ == "__main__":
    raise SystemExit(cli_main())
