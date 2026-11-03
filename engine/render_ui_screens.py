"""MYONL 渲染层 · UI 界面屏（renderer.py 模块化拆分）。

UiScreensMixin 的方法原样迁自 engine/renderer.py：方法体与签名不变，
经 self 访问实例状态（__init__ 中初始化）与其他 Mixin 方法；
常量与纯函数统一来自 render_utils（engine.renderer 再导出，命名空间不变）。
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pygame
import random
from .render_utils import (
    _scale_to_fit,
)


class UiScreensMixin:
    """UI 界面屏方法集（经多继承组合进 Renderer，见 engine/renderer.py）。"""

    if TYPE_CHECKING:  # pragma: no cover - 仅供 pyright：实现在 TextMixin（render_text.py）
        def _cached_font_surface(self, font, text, antialias, color) -> pygame.Surface: ...

    # C3：宿主注入属性 / 其他 Mixin 方法——仅静态检查声明。
    if TYPE_CHECKING:  # pragma: no cover
        config: Any
        settings: Any
        size: Any
        _screen: pygame.Surface
        _font: Any
        _small_font: Any
        _mid_font: Any
        _title_font: Any
        _ui_hits: Any
        _ui_int: Any
        _ui_str: Any
        _t: Any
        _hovered: Any
        _blit_centered_text: Any
        _rounded_panel: Any
        _dialog_top: Any
        _draw_slots: Any
        _draw_settings: Any
        _draw_backlog: Any
        _draw_gallery: Any
        _draw_text_with_shadow: Any
        _load_image: Any
        _make_vgradient: Any
        _render_spaced_text: Any
        _ui_hidden: Any
        _ending_fade_t0: Any
        _ui_mode: Any

    def _quickbar_layout(self, count: int = 6) -> dict:
        """快捷栏布局：默认贴屏幕底部（主流 Galgame 交互习惯），可切回对话框上方。

        返回几何数据；enabled=False 时调用方不绘制、也不给对话框预留底边。
        """
        cfg = self.config.ui_section("quickbar")
        enabled = bool(cfg.get("enabled", True))
        bw = self._ui_int("quickbar", "button_width", 64, 40, 180)
        bh = self._ui_int("quickbar", "button_height", 26, 20, 60)
        gap = self._ui_int("quickbar", "gap", 8, 2, 40)
        mx = self._ui_int("quickbar", "margin_x", 24, 0, 200)
        my = self._ui_int("quickbar", "margin_y", 10, 0, 80)
        position = self._ui_str("quickbar", "position", "bottom")
        align = self._ui_str("quickbar", "align", "right")
        w, h = self.size
        total = max(1, count) * (bw + gap) - gap
        if align == "left":
            x0 = mx
        elif align == "center":
            x0 = (w - total) // 2
        else:
            x0 = w - total - mx
        if position == "above_dialog":
            y0 = self._dialog_top() - bh - my
        else:
            y0 = h - bh - my
        return {"enabled": enabled, "bw": bw, "bh": bh, "gap": gap,
                "x0": max(0, x0), "y0": max(0, y0), "alpha": self._ui_int(
                    "quickbar", "alpha", 185, 0, 255, scale=False),
                "radius": self._ui_int("quickbar", "radius", 15, 0, 40)}

    def _draw_ui(self, view) -> None:
        """按 ui_view["mode"] 分发绘制（UI 状态进 ui.py，renderer 只负责画）。"""
        mode = view.get("mode")
        self._ui_hits = []  # P31-b：每帧重建可点区域
        if mode == "title":
            self._draw_title(view)
        elif mode == "menu":
            self._draw_menu(view)
        elif mode == "slots":
            self._draw_slots(view)
        elif mode == "settings":
            self._draw_settings(view)
        elif mode == "backlog":
            self._draw_backlog(view)
        elif mode == "gallery":
            self._draw_gallery(view)

    def _draw_dim(self, alpha: int) -> None:
        """全屏半透明黑罩（游戏画面在下面，UI 层盖在上面）。

        ⑧ 菜单/读档/设置/画廊四模式强制 0.85+ 实色遮罩（调用处传 ≥224）；
        backlog 回看例外（保持半透明，游戏画面氛围可透）。
        """
        overlay = pygame.Surface(self.size, pygame.SRCALPHA)
        overlay.fill((0, 0, 0, alpha))
        self._screen.blit(overlay, (0, 0))

    def _draw_ui_items(self, items, cursor, top, row_h=54, width=380, radius: int | None = None,
                       align="center") -> None:
        """菜单项列表：圆角卡片 + 选中亮底/白字/描边/投影 + 鼠标 hover 反馈。

        align="center"（默认）：整列居中；
        align="left"（P44）：左列布局——菜单贴左缘。

        P44-D：所有菜单项等宽等高；默认纯文字、无背景框无边框，只有鼠标悬停
        才显示 1px 状态边框；键盘焦点项仅用主题色文字区分（不画框），
        符合「没选中没框、碰到才有反应」的轻量启动界面规范。
        """
        w, _h = self.size
        radius = self._ui_int("", "corner_radius", 12) if radius is None else radius
        left = align == "left"
        x0 = 110 if left else w // 2 - width // 2
        for i, item in enumerate(items):
            text = str(item.get("text", item.get("label", "")))
            available = bool(item.get("available", item.get("enabled", True)))
            rect = pygame.Rect(x0, top + i * row_h, width, row_h - 6)
            hover = self._hovered(rect) and available
            if hover:
                self._screen.blit(self._rounded_panel(
                    rect, self.config.theme_color("surface"), 0, radius,
                    border_color=self.config.theme_color("primary"), border_width=1),
                    rect.topleft)
                color = self.config.color("text")
            else:
                # P48-b：焦点项不再用主题色区分——与其它项同色（用户：颜色一致）；
                # 键盘焦点只给左侧一条 3px 主题色竖线（不画框、不占文字）
                color = self.config.color("text") if available else self.config.color("disabled")
            img = self._cached_font_surface(self._font, text, True, color)
            self._draw_text_with_shadow(text, self._font, color,
                                        (rect.centerx - img.get_width() // 2,
                                         rect.y + (rect.height - img.get_height()) // 2))
            if i == cursor and available and not hover:
                # 左缘竖线（左列布局在文字左侧；居中布局在整行左端）
                mark_x = x0 - 14 if left else rect.x - 14
                pygame.draw.rect(self._screen, self.config.theme_color("primary"),
                                 (mark_x, rect.centery - 9, 3, 18))
            # P31-b：整行可点（灰置项也登记，由 ui 判 enabled 后忽略）
            self._ui_hits.append((rect.copy(), {"kind": "item", "index": i, "enabled": available}))

    def _title_layout(self, has_bg: bool) -> dict:
        """C3：标题排版统一取值（对齐 / 是否显示 / 作品名坐标 / 字距 / 菜单几何）。

        左列与居中只差对齐方式，坐标都从 config/settings 来，不再写死 (96, 70)。
        """
        align = str(self.config.ui_value("title", "align", "center") or "center")
        left = align == "left"
        visible = bool(self.settings.get("title_text_visible", not has_bg))
        logo_y = int(self.settings.get(
            "title_text_y", self._ui_int("title", "logo_y", 150)))
        return {
            "align": "left" if left else "center",
            "left": left,
            "visible": visible,
            "x": self._ui_int("title", "left_x", 96) if left else 0,
            "y": logo_y,
            "spacing": self._ui_int("title", "letter_spacing", 3),
            "menu_top": self._ui_int("title", "menu_top", 300),
            "menu_row_height": self._ui_int("title", "menu_row_height", 54),
            "menu_width": self._ui_int("title", "menu_width", 380),
        }

    def _draw_title(self, view) -> None:
        """标题画面：背景图 → 缺省现代渐变；作品名 + 主题色下划线；菜单卡片。"""
        w, h = self.size
        # ⑪ 标题背景：优先 images/title_bg，缺省深色渐变
        bg = self._load_image("title_bg")
        if bg is not None:
            scaled = _scale_to_fit(bg, w, h)
            self._screen.blit(scaled, ((w - scaled.get_width()) // 2,
                                       (h - scaled.get_height()) // 2))
        else:
            # P35 现代渐变：深蓝黑 → 靛紫，叠两团主题光晕与底部暗角
            for y in range(h):
                t = y / max(1, h - 1)
                c = (int(16 + 26 * t), int(20 + 20 * t), int(42 + 34 * t))
                pygame.draw.line(self._screen, c, (0, y), (w, y))
            # P37-T5 星尘氛围：固定种子保证每帧位置一致（不闪烁），上半部 70% 散布
            star_count = self._ui_int("title", "stars", 36, scale=False)
            if star_count > 0:
                rng = random.Random(20241029)
                for _ in range(star_count):
                    sx = rng.randint(0, w - 1)
                    sy = rng.randint(0, int(h * 0.72))
                    sr = rng.choice((1, 1, 2))
                    sa = rng.randint(55, 165)
                    pygame.draw.circle(self._screen, (255, 255, 255, sa), (sx, sy), sr)
            glow = pygame.Surface((w, h), pygame.SRCALPHA)
            pygame.draw.circle(glow, (*self.config.theme_color("primary"), 26), (int(w * 0.18), 120), 260)
            pygame.draw.circle(glow, (*self.config.theme_color("accent"), 16), (int(w * 0.86), 220), 300)
            self._screen.blit(glow, (0, 0))
            vignette = self._make_vgradient(w, 120, 0, 120)
            self._screen.blit(vignette, (0, h - 120))
        # 作品名（view["title"] 已由 ui 从 settings.json 读取）
        # P30-S1-6：title_text_visible=False（有背景图时默认）不叠中文，避免双层标题；
        # 无背景图时默认显示（否则标题空白）；title_text_y 可调位置
        # P44：ui.title.align="left" 时作品名左列布局（左上角），配合左列菜单
        layout = self._title_layout(bg is not None)
        menu_top = layout["menu_top"]
        if layout["visible"]:
            title = str(view.get("title") or "MYONL")
            # P37-T5：字距疏朗 + 柔和阴影，现代 gal 标题质感
            title_surf = self._render_spaced_text(
                title, self._title_font, (255, 255, 255),
                spacing=layout["spacing"], shadow_color=(0, 0, 0, 130), shadow_offset=2)
            if layout["left"]:
                # C3：左列布局也走配置坐标（title_text_y / ui.title.logo_y / left_x）
                self._screen.blit(title_surf, (layout["x"], layout["y"]))
            else:
                self._screen.blit(title_surf,
                                  ((w - title_surf.get_width()) // 2, layout["y"]))
            # 作品名可见时把菜单往下推：大字号下 logo_y 与 menu_top 会重叠，
            # 第一项被标题盖住会像「灰掉/点不动」（空包默认配置就踩到）。
            menu_top = max(menu_top, layout["y"] + title_surf.get_height() + 16)
        self._draw_ui_items(
            view.get("items") or [], view.get("cursor", 0),
            menu_top, layout["menu_row_height"], layout["menu_width"],
            align=layout["align"],
        )
        # P30-S1-4：引擎署名默认不画（settings.json 里 show_engine_version=true 才显示）
        if self._show_engine_version():
            small = self._cached_font_surface(self._small_font, "MYONL v1.0", True, (120, 120, 140))
            self._screen.blit(small, (w - small.get_width() - 16,
                                      h - small.get_height() - 12))

    def _show_engine_version(self) -> bool:
        """标题页是否显示引擎版本号（默认 False：版本号不打扰玩家）。"""
        return bool(self.settings.get("show_engine_version", False))

    def ending_hold_ms(self) -> int:
        """P30-S2-3：终幕画面停留时长（毫秒，settings.json 的 ending_hold_ms，默认 1500）。"""
        try:
            return max(0, int(self.settings.get("ending_hold_ms", 1500)))
        except (TypeError, ValueError):
            return 1500

    def _quickbar_icon(self, icons, name, size: int):
        """快捷栏图标：ui.quickbar.icons 里按标签配了图就返回缩放后的 Surface。

        找不到配置 / 图片缺失 / 加载失败一律返回 None，调用方自动回退文字按钮，
        因此老项目（没有 icons 段）行为与之前完全一致。
        """
        if not isinstance(icons, dict):
            return None
        raw = icons.get(name) or icons.get(name.lower())
        if not isinstance(raw, str) or not raw.strip():
            return None
        raw = raw.strip()
        src = self._load_image(raw)
        if src is None:
            return None
        cache = getattr(self, "_quickbar_icon_cache", None)
        if cache is None:
            cache = self._quickbar_icon_cache = {}
        key = (raw, size)
        surf = cache.get(key)
        if surf is None:
            sw, sh = src.get_size()
            if sh <= 0:
                return None
            scale = size / float(sh)
            surf = pygame.transform.smoothscale(
                src, (max(1, int(round(sw * scale))), max(1, size)))
            cache[key] = surf
        return surf

    def _draw_quickbar(self, view) -> None:
        """P35 游戏内快捷栏：默认贴屏幕底部（SAVE/SKIP 等核心按钮）。

        P50（B+D 结合）：按钮改小、默认完全隐藏——鼠标移到快捷栏所在带区
        （底部区域）才显现；AUTO/SKIP 激活时强制常驻（玩家要知道开关状态）。
        形态：小文字按钮、无框无底、hover 浅底+主题色细边。
        """
        qb = view.get("quickbar") if isinstance(view, dict) else None
        if not qb:
            return
        labels = qb.get("labels") or []
        if not labels:
            return
        if self._ui_hidden:
            return  # P48：截图模式——快捷栏一并隐藏，画面干净
        lay = self._quickbar_layout(len(labels))
        if not lay["enabled"]:
            return
        bw, bh, gap = lay["bw"], lay["bh"], lay["gap"]
        x0, y0, radius = lay["x0"], lay["y0"], lay["radius"]
        mouse = getattr(self, "_mouse_pos", None)
        primary = self.config.theme_color("primary")
        text_dim = self.config.theme_color("text_dim")
        active_any = bool(qb.get("auto")) or bool(qb.get("skip"))
        qb_icons = self.config.ui_section("quickbar").get("icons")
        # P50：hover 带区 = 快捷栏整行上下各扩 14px；鼠标在其中才显现快捷栏
        bar_w = len(labels) * (bw + gap) - gap
        zone = pygame.Rect(x0, y0 - 14, bar_w, bh + 28)
        show = bool(mouse) and zone.collidepoint(mouse)
        if not (show or active_any):
            return  # P50：默认隐藏（尽可能藏），避免常驻视觉噪音
        for i, lab in enumerate(labels):
            rect = pygame.Rect(x0 + i * (bw + gap), y0, bw, bh)
            name = str(lab).upper()
            skip_locked = (name == "SKIP" and not bool(qb.get("skip_allowed")))
            active = (name == "AUTO" and bool(qb.get("auto"))) or \
                     (name == "SKIP" and bool(qb.get("skip")))
            hover = bool(mouse) and rect.collidepoint(mouse) and not skip_locked
            if active:
                bg = self._rounded_panel(rect, primary, 232, radius)
                self._screen.blit(bg, rect.topleft)
                color = (18, 22, 32)
            elif hover:
                self._screen.blit(self._rounded_panel(
                    rect, self.config.theme_color("primary_soft"), 230, radius,
                    border_color=primary, border_width=1), rect.topleft)
                color = (255, 255, 255)
            else:
                # P50.1：按键一律是圆角矩形（半透明深底+细边框），不再是裸文字；
                # 与整体 B+D 的「藏」一致：整排默认隐藏，显现时就是圆角矩形按键
                self._screen.blit(self._rounded_panel(
                    rect, (18, 22, 32), 140, radius,
                    border_color=(70, 78, 95), border_width=1), rect.topleft)
                color = (120, 126, 140) if skip_locked else text_dim
            icon = self._quickbar_icon(qb_icons, name, bh - 6)
            if icon is not None:
                self._screen.blit(icon, (rect.x + (bw - icon.get_width()) // 2,
                                         rect.y + (bh - icon.get_height()) // 2))
            else:
                img = self._cached_font_surface(self._small_font, lab, True, color)
                self._screen.blit(img, (rect.x + (bw - img.get_width()) // 2,
                                        rect.y + (bh - img.get_height()) // 2))
            self._ui_hits.append((rect.copy(), {"kind": "quickbar", "index": i}))
        # P48：快捷栏字母上方左右对称三角 ◀ ▶（右下角；◀=回看上一句，▶=推进下一句）。
        # ▶ 不登记命中：点击它落到画面 → 引擎按「点击推进」处理（与对话框 ▼ 同语义）。
        tri_y = y0 - 26
        last_right = x0 + len(labels) * (bw + gap) - gap
        prev_rect = pygame.Rect(last_right - 56, tri_y, 24, 24)
        next_rect = pygame.Rect(last_right - 28, tri_y, 24, 24)
        tri_hover = self.config.theme_color("primary") if mouse else (190, 195, 205)
        tri_dim = (150, 155, 165)
        for rect, flip in ((prev_rect, True), (next_rect, False)):
            hov = bool(mouse) and rect.collidepoint(mouse)
            c = tri_hover if hov else tri_dim
            s = pygame.Surface(rect.size, pygame.SRCALPHA)
            cx, cy = rect.width // 2, rect.height // 2
            if flip:
                pts = [(cx - 6, cy), (cx + 5, cy - 8), (cx + 5, cy + 8)]
            else:
                pts = [(cx + 6, cy), (cx - 5, cy - 8), (cx - 5, cy + 8)]
            pygame.draw.polygon(s, (*c, 230), pts)
            self._screen.blit(s, rect.topleft)
            if flip:
                self._ui_hits.append((rect.copy(), {"kind": "prev_arrow"}))

    def _draw_end_hint(self, state) -> None:
        """P30-S2-3：终幕停留期间右下角提示「即将返回标题」，淡出开始后不再画。"""
        if not isinstance(state, dict) or not state.get("finished"):
            return
        if self._ending_fade_t0 is not None:
            return
        if self._ui_mode not in (None, "playing"):
            return
        w, h = self.size
        img = self._cached_font_surface(self._small_font, self._t("结局 CG 已收录 · 即将返回标题"), True, (235, 235, 235))
        pad = 10
        box = pygame.Rect(w - img.get_width() - 24 - pad * 2, h - img.get_height() - 18 - pad,
                          img.get_width() + pad * 2, img.get_height() + pad)
        panel = pygame.Surface(box.size, pygame.SRCALPHA)
        panel.fill((0, 0, 0, 140))  # 深色药丸底，亮 CG 上也能读清
        self._screen.blit(panel, box.topleft)
        self._screen.blit(img, (box.x + pad, box.y + pad // 2))

    def _draw_menu(self, view) -> None:
        """游戏内菜单：盖住游戏画面的半透明菜单。

        几何走 ui.menu 段（row_width/row_height/top/radius），引擎默认 380/54/240/12；
        与标题菜单共用 _draw_ui_items 的圆角卡片绘制。
        """
        self._draw_dim(self.config.alpha("menu"))
        self._blit_centered_text("菜单", 120, self._mid_font, (255, 255, 255))
        row_w = self._ui_int("menu", "row_width", 380, 240, self.size[0] - 80)
        row_h = self._ui_int("menu", "row_height", 54, 40, 90)
        top = self._ui_int("menu", "top", 240)
        radius = self._ui_int("menu", "radius", 12, 0, 30)
        self._draw_ui_items(view.get("items") or [], view.get("cursor", 0), top,
                            row_h=row_h, width=row_w, radius=radius)
        self._blit_centered_text(self._t("↑↓ 选择 · 回车确认 · Esc 返回"), 640,
                                 self._small_font, (200, 200, 200))

