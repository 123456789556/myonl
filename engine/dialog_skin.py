"""P53 对话框皮肤：贴图九宫格 + 渐变蒙版 + 纹理平铺（纯函数，无窗口依赖）。

为什么不是"整张 PNG 替换"：
    主流做法（Ren'Py 的 textbox.png、以及"两分钟教你做 galgame 对话框"的教程）
    是一张固定尺寸的图整张盖上去——面板尺寸一变，要么被拉变形，要么重画一张。
MYONL 走另一条：同一张自己画的 PNG，
    ① 按九宫格切片（四角不缩放、边与中段拉伸）→ 任意宽高都不变形；
    ② 渐变蒙版在引擎里算（顶部/底部羽化），不用回 PS 加蒙版；
    ③ 纹理在引擎里平铺叠加，不用回 PS 做图案填充；
    ④ 结果能反导出成 textbox.png，给 Ren'Py 直接用。

这里只有 Surface 进出，不读配置、不碰全局，便于无头单测。
"""
from __future__ import annotations

from typing import Iterable, Sequence

import pygame

# 九宫格四条边最多各占一半：防止 insets 比目标尺寸还大时算出负的中段
_MIN_MID = 1


def parse_insets(value: object, w: int, h: int) -> tuple[int, int, int, int]:
    """把 panel_slice 配置归一成 (左, 上, 右, 下)。

    接受单个数字（四边同值）或长度 4 的序列；非法/负数按 0 处理，
    并夹到「四边之和不超过源图尺寸」的范围，保证可切片。
    """
    def _int(v: object) -> int:
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            return 0
        return max(0, int(v))

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        l = t = r = b = _int(value)
    elif isinstance(value, (list, tuple)) and len(value) == 4:
        l, t, r, b = (_int(v) for v in value)
    else:
        return (0, 0, 0, 0)

    # 左右之和 < w，上下之和 < h（留至少 1px 中段）
    max_lr = max(0, (max(0, w) - _MIN_MID) // 2)
    max_tb = max(0, (max(0, h) - _MIN_MID) // 2)
    l = min(l, max_lr)
    r = min(r, max_lr)
    if l + r > w - _MIN_MID:
        r = max(0, w - _MIN_MID - l)
    t = min(t, max_tb)
    b = min(b, max_tb)
    if t + b > h - _MIN_MID:
        b = max(0, h - _MIN_MID - t)
    return (l, t, r, b)


def _scaled(piece: pygame.Surface, size: tuple[int, int],
            pixelated: bool) -> pygame.Surface:
    """缩放一小块：像素化用 nearest（保硬边），否则 smoothscale（保渐变）。"""
    if piece.get_size() == size:
        return piece
    if pixelated:
        return pygame.transform.scale(piece, size)
    return pygame.transform.smoothscale(piece, size)


def _split(count: int, near: int, far: int) -> list[tuple[int, int]]:
    """一维三段区间：贴图源与目标共用同一套 (起点, 长度) 切法。"""
    mid = max(_MIN_MID, count - near - far) if count >= near + far + _MIN_MID \
        else max(0, count - near - far)
    return [(0, near), (near, mid), (near + mid, far)]


def nine_slice(src: pygame.Surface, out_w: int, out_h: int,
               insets: Sequence[int] | int = 0,
               pixelated: bool = False) -> pygame.Surface:
    """九宫格缩放：四角原尺寸、四边单向拉伸、中段双向拉伸。

    insets 为 (左, 上, 右, 下) 或单值；越界会被 parse_insets 夹到合法范围。
    """
    out_w = max(1, int(out_w))
    out_h = max(1, int(out_h))
    sw, sh = src.get_size()
    l, t, r, b = parse_insets(insets, sw, sh)
    out = pygame.Surface((out_w, out_h), pygame.SRCALPHA)
    src_cols = _split(sw, l, r)
    src_rows = _split(sh, t, b)
    dst_cols = _split(out_w, min(l, max(0, out_w - _MIN_MID)),
                      min(r, max(0, out_w - _MIN_MID)))
    dst_rows = _split(out_h, min(t, max(0, out_h - _MIN_MID)),
                      min(b, max(0, out_h - _MIN_MID)))
    for ci, (sx, scw) in enumerate(src_cols):
        if scw <= 0:
            continue
        dx, dcw = dst_cols[ci]
        if dcw <= 0:
            continue
        for ri, (sy, sch) in enumerate(src_rows):
            if sch <= 0:
                continue
            dy, dch = dst_rows[ri]
            if dch <= 0:
                continue
            piece = src.subsurface(pygame.Rect(sx, sy, scw, sch))
            out.blit(_scaled(piece, (dcw, dch), pixelated), (dx, dy))
    return out


def vertical_fade(surface: pygame.Surface, top_px: int = 0,
                  bottom_px: int = 0) -> pygame.Surface:
    """垂直渐变蒙版：顶部 top_px 从全透明渐入、底部 bottom_px 渐出。

    对应 PS 里的「渐变蒙版」——让贴图与画面自然融合，不留硬边。
    返回新 Surface（不改入参）。
    """
    h = surface.get_height()
    if h <= 0:
        return surface.copy()
    top_px = max(0, min(int(top_px), h))
    bottom_px = max(0, min(int(bottom_px), h))
    if not top_px and not bottom_px:
        return surface.copy()
    mask = pygame.Surface((1, h), pygame.SRCALPHA)
    for y in range(h):
        a = 255
        if top_px and y < top_px:
            a = int(255 * (y + 1) / (top_px + 1))
        if bottom_px and y >= h - bottom_px:
            fade = int(255 * (h - y) / (bottom_px + 1))
            a = min(a, max(0, fade))
        mask.set_at((0, y), (255, 255, 255, max(0, a)))
    mask = pygame.transform.scale(mask, (max(1, surface.get_width()), h))
    out = surface.copy()
    out.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    return out


def tint(surface: pygame.Surface, rgb: Iterable[int]) -> pygame.Surface:
    """整体染色（乘法混合）：把别人的贴图改成自己主题色，不用回 PS 调色。"""
    try:
        color = tuple(max(0, min(255, int(c))) for c in tuple(rgb)[:3])
    except (TypeError, ValueError):
        return surface.copy()
    if len(color) != 3:
        return surface.copy()
    out = surface.copy()
    out.fill((*color, 255), special_flags=pygame.BLEND_RGB_MULT)
    return out


def tile(texture: pygame.Surface, width: int, height: int) -> pygame.Surface:
    """把纹理平铺成 width×height（图案填充），纹理大于目标时等比压到一屏。"""
    width = max(1, int(width))
    height = max(1, int(height))
    tw, th = texture.get_size()
    if tw <= 0 or th <= 0:
        return pygame.Surface((width, height), pygame.SRCALPHA)
    out = pygame.Surface((width, height), pygame.SRCALPHA)
    if tw > width or th > height:
        # 纹理比面板还大：等比缩到能放下，避免只露一个角
        ratio = min(width / tw, height / th)
        tex = _scaled(texture,
                      (max(1, int(tw * ratio)), max(1, int(th * ratio))), False)
    else:
        tex = texture
    tw, th = tex.get_size()
    for y in range(0, height, th):
        for x in range(0, width, tw):
            out.blit(tex, (x, y))
    return out


def compose_panel(panel: pygame.Surface, out_w: int, out_h: int,
                  insets: Sequence[int] | int = 0,
                  tint_rgb: Iterable[int] | None = None,
                  fade_top: int = 0, fade_bottom: int = 0,
                  texture: pygame.Surface | None = None,
                  texture_alpha: int = 0,
                  alpha: int = 255,
                  pixelated: bool = False) -> pygame.Surface:
    """按顺序合成对话框面板：九宫格 → 染色 → 渐变蒙版 → 纹理 → 总透明度。"""
    out = nine_slice(panel, out_w, out_h, insets, pixelated=pixelated)
    if tint_rgb is not None:
        out = tint(out, tint_rgb)
    if fade_top or fade_bottom:
        out = vertical_fade(out, fade_top, fade_bottom)
    if texture is not None and texture_alpha > 0:
        layer = tile(texture, out.get_width(), out.get_height())
        layer.set_alpha(max(0, min(255, int(texture_alpha))))
        out.blit(layer, (0, 0))
    alpha = max(0, min(255, int(alpha)))
    if alpha < 255:
        faded = out.copy()
        faded.fill((255, 255, 255, alpha), special_flags=pygame.BLEND_RGBA_MULT)
        out = faded
    return out


def surface_for(dlg: dict, width: int, height: int, load_image,
                pixelated: bool = False,
                cache: dict | None = None) -> pygame.Surface | None:
    """按 dialogue 配置合成贴图面板；没配图 / 图缺失返回 None（调用方走旧路径）。

    load_image 由渲染层注入（按素材名取 Surface，缺失返回 None），
    本模块不碰素材目录与缓存策略，只做像素合成。
    cache 给同一个面板尺寸/参数复用一份结果，避免每帧重新缩放。
    """
    name = str(dlg.get("panel_image") or "").strip()
    if not name or width <= 0 or height <= 0:
        return None
    img = load_image(name)
    if img is None:
        return None
    tex_name = str(dlg.get("panel_texture") or "").strip()
    tex = load_image(tex_name) if tex_name else None
    tint_val = dlg.get("panel_tint")
    tint_rgb = (tuple(int(v) for v in tint_val[:3])
                if isinstance(tint_val, (list, tuple)) and len(tint_val) == 3
                else None)
    slice_val = dlg.get("panel_slice", 0)
    slice_key = (tuple(int(v) for v in slice_val)
                 if isinstance(slice_val, (list, tuple)) else int(slice_val or 0))
    fade_top = int(dlg.get("panel_fade", 0) or 0)
    fade_bottom = int(dlg.get("panel_fade_bottom", 0) or 0)
    tex_alpha = int(dlg.get("panel_texture_alpha", 0) or 0)
    _alpha = dlg.get("panel_alpha")
    panel_alpha = (int(_alpha) if isinstance(_alpha, (int, float))
                   and not isinstance(_alpha, bool) else 255)
    key = (id(img), id(tex), int(width), int(height), slice_key, tint_rgb,
           fade_top, fade_bottom, tex_alpha, panel_alpha, bool(pixelated))
    if cache is not None and cache.get(key) is not None:
        return cache[key]
    try:
        surf = compose_panel(img, width, height, slice_key, tint_rgb, fade_top,
                             fade_bottom, tex, tex_alpha, panel_alpha,
                             pixelated=pixelated)
    except (pygame.error, ValueError):
        return None
    if cache is not None:
        if len(cache) >= 8:
            cache.clear()
        cache[key] = surf
    return surf


def solid_panel(width: int, height: int, rgb: Iterable[int], alpha: int,
                radius: int = 0, pixelated: bool = False) -> pygame.Surface:
    """没有贴图时的纯色兜底面板（导出成品图用）。"""
    color = tuple(max(0, min(255, int(c))) for c in tuple(rgb)[:3])
    if len(color) != 3:
        color = (0, 0, 0)
    surf = pygame.Surface((max(1, int(width)), max(1, int(height))), pygame.SRCALPHA)
    body = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
    radius = max(0, int(radius))
    if radius > 0:
        r = min(radius, min(body.get_width(), body.get_height()) // 2)
        pygame.draw.rect(body, (*color, max(0, min(255, int(alpha)))),
                         body.get_rect(), border_radius=r)
    else:
        body.fill((*color, max(0, min(255, int(alpha)))))
    if pixelated and radius > 0:
        # 像素化：先缩到 1/scale 再放大回来，边缘出现像素台阶（与引擎 UI 一致）
        small = pygame.transform.scale(
            body, (max(1, body.get_width() // 4), max(1, body.get_height() // 4)))
        body = pygame.transform.scale(small, surf.get_size())
    surf.blit(body, (0, 0))
    return surf
