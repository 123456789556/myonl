"""MYONL 渲染层 · 文本与面板工具（renderer.py 模块化拆分）。

TextMixin 的方法原样迁自 engine/renderer.py：方法体与签名不变，
经 self 访问实例状态（__init__ 中初始化）与其他 Mixin 方法；
常量与纯函数统一来自 render_utils（engine.renderer 再导出，命名空间不变）。
"""
from __future__ import annotations

from collections import OrderedDict
from typing import TYPE_CHECKING

import pygame

from . import richtext

if TYPE_CHECKING:  # pragma: no cover - 仅供类型检查
    from .config import Config
from .render_utils import _wrap_text

# T8：字体 Surface 缓存上限（条）。对话逐字打字机每帧都要重渲染同一行，
# 命中后直接复用 Surface；500 条约覆盖若干屏正文 + 名字/提示文字。
TEXT_CACHE_MAX = 500
# T8：字体度量缓存上限（条）。折行量的是逐字增长的前缀，相邻帧几乎全重叠，
# 2000 条足够覆盖约 30 行台词的前缀，超出按 LRU 淘汰。
TEXT_WIDTH_CACHE_MAX = 2000


class TextMixin:
    """文本与面板工具方法集（经多继承组合进 Renderer，见 engine/renderer.py）。"""

    # 宿主（Renderer）注入的属性：此处只为静态检查声明类型——
    # pyright 单独分析 Mixin 时看不到宿主类属性，运行期由 Renderer.__init__ 赋值。
    _screen: pygame.Surface
    _font: pygame.font.Font
    _small_font: pygame.font.Font
    _font_book: "richtext.FontBook"
    size: tuple
    config: "Config"
    # T8：缓存容器同样是宿主注入（OrderedDict，LRU）
    _text_cache: OrderedDict
    _text_cache_max: int
    _text_width_cache: OrderedDict
    _text_width_max: int

    if TYPE_CHECKING:  # pragma: no cover - 仅供 pyright：实现在 WindowMixin（render_window.py）
        def _now_ms(self) -> int: ...

    def _cached_font_surface(self, font, text: str, antialias: bool,
                             color) -> pygame.Surface:
        """T8：字体 Surface 缓存——相同 (字体, 文本, 颜色, 抗锯齿) 直接复用渲染结果。

        键里的字体用 id(font)：渲染层字体全部来自 FontBook 或 __init__ 创建的常驻字体对象，
        生命周期与 Renderer 一致，不存在 id 复用的窗口；缓存满时按 LRU 淘汰最久未用条目。
        """
        key = (id(font), text, tuple(color), bool(antialias))
        cache = self._text_cache
        surf = cache.get(key)
        if surf is not None:
            cache.move_to_end(key)  # 命中即标记为最近使用
            return surf
        surf = font.render(text, antialias, color)
        cache[key] = surf
        if len(cache) > self._text_cache_max:
            cache.popitem(last=False)  # 淘汰最久未用（省内存，不无限长）
        return surf

    def _font_width(self, font, text: str) -> int:
        """T8：字体度量缓存——`font.size()` 量一次 CJK 串约 70µs，打字机每帧要量 O(长度) 次。

        折行量的是「逐字增长的前缀」（"雨"、"雨停"、"雨停在"…），相邻两帧前缀几乎完全重叠；
        按 (字体 id, 文本) 缓存后，每帧只多量 1 个新前缀，其余全部字典命中，断行结果不变。
        """
        key = (id(font), text)
        width = self._text_width_cache.get(key)
        if width is not None:
            self._text_width_cache.move_to_end(key)
            return width
        width = font.size(text)[0]
        self._text_width_cache[key] = width
        if len(self._text_width_cache) > self._text_width_max:
            self._text_width_cache.popitem(last=False)
        return width

    def _wrap_text_cached(self, text, font, max_width):
        """T8：折行走 `_font_width` 缓存；算法本身复用 render_utils._wrap_text（唯一实现）。"""
        return _wrap_text(text, font, max_width,
                          measure=lambda s: self._font_width(font, s))

    # ---- P51-T6：热重载提示（左下角 toast）----

    def toast(self, text, seconds: float = 2.0) -> None:
        """左下角弹一条短提示（热重载成功 / 失败反馈），seconds 秒后自动消失。"""
        self._toast_text = str(text)
        self._toast_until = self._now_ms() + int(max(0.1, float(seconds)) * 1000)

    def _draw_toast(self) -> None:
        """画左下角 toast；无提示或已过期直接返回（每帧调用无副作用）。"""
        text = getattr(self, "_toast_text", "")
        if not text or self._now_ms() >= getattr(self, "_toast_until", 0):
            return
        img = self._cached_font_surface(self._small_font, text, True, (255, 255, 255))
        pad_x, pad_y = 10, 6
        width, height = img.get_width() + pad_x * 2, img.get_height() + pad_y * 2
        rect = pygame.Rect(16, self.size[1] - 56 - height, width, height)
        panel = self._rounded_panel(rect, self.config.theme_color("surface"), 210,
                                    min(10, height // 2))
        self._screen.blit(panel, rect.topleft)
        self._screen.blit(img, (rect.x + pad_x, rect.y + pad_y))

    # ---- P46 富文本：样式行绘制 ----

    def _rich_color(self, style, base_color):
        """解析 {color=} 片段颜色；非法值回落本行基色（不崩）。"""
        raw = style[2]
        if not raw:
            return base_color
        try:
            return pygame.Color(raw)
        except (ValueError, TypeError):
            return base_color

    @staticmethod
    def _shadow_for(color) -> tuple:
        """按文字亮度选阴影色：深色文字配白阴影（浅色面板），浅色文字配黑阴影。"""
        r, g, b = tuple(color)[:3]
        lum = 0.299 * r + 0.587 * g + 0.114 * b
        return (255, 255, 255) if lum < 120 else (0, 0, 0)

    def _blit_rich_line(self, rich_line, x: int, y: int, base_color,
                        target=None, shadow: bool = True) -> int:
        """在 (x, y) 起绘制一行富文本（逐片段换字体/颜色），返回该行像素宽。"""
        target = target if target is not None else self._screen
        cx = x
        for seg, style in rich_line:
            if not seg:
                continue
            font = self._font_book.get(style)
            color = self._rich_color(style, base_color)
            if shadow:
                # T8：阴影与正文都走缓存（同一片段第二次绘制起不再 font.render）
                sh = self._cached_font_surface(font, seg, True, self._shadow_for(color))
                for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2)):
                    target.blit(sh, (cx + dx, y + dy))
            target.blit(self._cached_font_surface(font, seg, True, color), (cx, y))
            cx += self._font_width(font, seg)
        return cx - x

    def _rich_line_x(self, align: str, line_w: int, margin: int) -> int:
        """按对齐求行起始 x：left=顶格 / center=居中 / right=右顶格。"""
        w = self.size[0]
        if align == "center":
            return (w - line_w) // 2
        if align == "right":
            return w - margin - line_w
        return margin

    def _rich_segments(self, shown_raw: str, plain_lines: list) -> list:
        """原文（可含未闭合标签）→ 逐行样式行（与 plain_lines 一一对应）。"""
        return richtext.split_rich_lines(richtext.parse(shown_raw), plain_lines)

    @staticmethod
    def _text_align(dlg: dict) -> str:
        """从 dialogue 布局取对齐；非法值回落 left（P46）。"""
        align = str(dlg.get("align", "left")).strip().lower()
        return align if align in ("left", "center", "right") else "left"

    def _rounded_panel(self, rect: pygame.Rect, color, alpha: int, radius: int,
                       border_color=None, border_width: int = 0,
                       pixelated: bool = False, pixel_scale: int = 4) -> pygame.Surface:
        """生成一块可叠色的圆角面板（独立 Surface 保证 RGBA 透明度生效）。

        P51：pixelated=True 时走像素化渲染——先按 pixel_scale 缩小绘制圆角矩形
        （圆角半径同步整除缩放），再用 NEAREST 放大回原尺寸，形成像素块边缘。
        纯 Python 程序化，不依赖任何 AI 生图。
        """
        if pixelated and pixel_scale > 1 and rect.width >= pixel_scale and rect.height >= pixel_scale:
            lw = max(1, rect.width // pixel_scale)
            lh = max(1, rect.height // pixel_scale)
            small = pygame.Surface((lw, lh), pygame.SRCALPHA)
            small_radius = max(0, radius // pixel_scale)
            pygame.draw.rect(small, (*tuple(color)[:3], alpha), small.get_rect(),
                             border_radius=small_radius)
            if border_width > 0 and border_color is not None:
                pygame.draw.rect(small, (*tuple(border_color)[:3], 255), small.get_rect(),
                                 border_width, border_radius=small_radius)
            # NEAREST 放大：保持硬像素边缘，不插值
            panel = pygame.transform.scale(small, (rect.width, rect.height))
            return panel
        panel = pygame.Surface((max(1, rect.width), max(1, rect.height)), pygame.SRCALPHA)
        radius = max(0, min(radius, min(rect.width, rect.height) // 2))
        pygame.draw.rect(panel, (*tuple(color)[:3], alpha), panel.get_rect(),
                         border_radius=radius)
        if border_width > 0 and border_color is not None:
            pygame.draw.rect(panel, (*tuple(border_color)[:3], 255), panel.get_rect(),
                             border_width, border_radius=radius)
        return panel

    @staticmethod
    def _make_vgradient(width: int, height: int, top_alpha: int, bottom_alpha: int,
                        color=(0, 0, 0)) -> pygame.Surface:
        """生成垂直渐变 Surface：顶部 top_alpha → 底部 bottom_alpha。

        用于对话框/NVL/序幕的半透明底，替代纯色填充让边缘自然融入背景。
        """
        surf = pygame.Surface((width, height), pygame.SRCALPHA)
        if height <= 0:
            return surf
        for y in range(height):
            t = y / max(1, height - 1)
            a = int(top_alpha + (bottom_alpha - top_alpha) * t)
            pygame.draw.line(surf, (*color, a), (0, y), (width - 1, y))
        return surf

    def _draw_text_with_shadow(self, text, font, color, pos, shadow_color=None,
                               shadow_offset=2, target=None) -> None:
        """带阴影的文字绘制：先画 4 向阴影再画正文，保证任何背景可读。

        shadow_color 缺省时按文字亮度自适应（P46：深色文字配白阴影，浅色配黑）。
        """
        target = target if target is not None else self._screen
        if shadow_color is None:
            shadow_color = self._shadow_for(color)
        # T8：角色名/提示字每帧都画，走缓存避免重复 font.render
        shadow = self._cached_font_surface(font, text, True, shadow_color)
        for dx, dy in ((-shadow_offset, 0), (shadow_offset, 0),
                       (0, -shadow_offset), (0, shadow_offset)):
            target.blit(shadow, (pos[0] + dx, pos[1] + dy))
        img = self._cached_font_surface(font, text, True, color)
        target.blit(img, pos)

    def _blit_centered_lines(self, lines, rect, color, top_aligned=False, target=None,
                             line_gap=0) -> None:
        """在 rect 内逐行水平居中绘制。top_aligned 时从 rect 顶部开始，否则整体垂直居中。"""
        target = target if target is not None else self._screen
        line_h = self._font.get_linesize()
        if top_aligned:
            y = rect.top
        else:
            y = rect.top + max(0, (rect.height - line_h * len(lines)) // 2)
        for line in lines:
            img = self._cached_font_surface(self._font, line, True, color)
            target.blit(img, (rect.centerx - img.get_width() // 2, y))
            y += line_h + line_gap

    def _blit_centered_lines_shadow(self, lines, rect, color, top_aligned=False,
                                    target=None, line_gap=0, shadow_color=(0, 0, 0),
                                    shadow_offset=2) -> None:
        """带阴影的居中逐行绘制（旁白用，浅色背景也能读清）。"""
        target = target if target is not None else self._screen
        line_h = self._font.get_linesize()
        y = rect.top if top_aligned else rect.top + max(0, (rect.height - line_h * len(lines)) // 2)
        for line in lines:
            shadow = self._cached_font_surface(self._font, line, True, shadow_color)
            sx = rect.centerx - shadow.get_width() // 2
            for dx, dy in ((-shadow_offset, 0), (shadow_offset, 0),
                           (0, -shadow_offset), (0, shadow_offset)):
                target.blit(shadow, (sx + dx, y + dy))
            img = self._cached_font_surface(self._font, line, True, color)
            target.blit(img, (rect.centerx - img.get_width() // 2, y))
            y += line_h + line_gap

    # ==================== 内部：UI 层绘制（只读 ui_view） ====================

    def _blit_centered_text(self, text, y, font, color) -> None:
        """指定字号、水平居中、给定 y 画一行文字。"""
        img = self._cached_font_surface(font, str(text), True, color)
        self._screen.blit(img, ((self.size[0] - img.get_width()) // 2, y))

    def _render_spaced_text(self, text, font, color, spacing=0,
                            shadow_color=None, shadow_offset=2):
        """渲染带字距的文字（可选柔和阴影），返回 Surface。

        spacing>0 时逐字渲染并插入水平间距，形成现代 gal 标题的疏朗感；
        shadow_color 给每个字叠加同色偏移阴影，保证任何背景可读。

        T8：spacing<=0 且无阴影时直接返回字体缓存里的 Surface——调用方只许 blit，
        不得原地修改（set_alpha/fill 等），否则会污染其他绘制。
        """
        text = str(text)
        if spacing <= 0:
            img = self._cached_font_surface(font, text, True, color)
            if shadow_color is None:
                return img
            out = pygame.Surface((img.get_width() + shadow_offset,
                                  img.get_height() + shadow_offset),
                                 pygame.SRCALPHA)
            out.blit(self._cached_font_surface(font, text, True, shadow_color),
                     (shadow_offset, shadow_offset))
            out.blit(img, (0, 0))
            return out
        imgs = [self._cached_font_surface(font, ch, True, color) for ch in text]
        if not imgs:
            return self._cached_font_surface(font, "", True, color)
        h = max(i.get_height() for i in imgs)
        total_w = sum(i.get_width() for i in imgs) + spacing * (len(imgs) - 1)
        extra = shadow_offset if shadow_color is not None else 0
        surf = pygame.Surface((total_w + extra, h + extra), pygame.SRCALPHA)
        x = 0
        for i, ch in enumerate(text):
            img = imgs[i]
            if shadow_color is not None:
                sh = self._cached_font_surface(font, ch, True, shadow_color)
                surf.blit(sh, (x + shadow_offset, shadow_offset))
            surf.blit(img, (x, 0))
            x += img.get_width() + spacing
        return surf
