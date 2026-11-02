"""MYONL 渲染层 · UI 页面（存档/设置/回看/相册）（renderer.py 模块化拆分）。

UiPagesMixin 的方法原样迁自 engine/renderer.py：方法体与签名不变，
经 self 访问实例状态（__init__ 中初始化）与其他 Mixin 方法；
常量与纯函数统一来自 render_utils（engine.renderer 再导出，命名空间不变）。
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pygame
import os
from . import richtext
from . import save as save_api
from .render_utils import (
    _clip_text,
    _format_setting,
    _scale_to_fit,
    _slot_card_head,
    _slot_row_text,
    UI_HIGHLIGHT,
    UI_DISABLED,
)

# U10：玩家改键后设置里存的是 pygame.key.name 的小写名，这里换成中文/箭头显示
_KEY_LABELS = {
    "space": "空格", "return": "回车", "escape": "Esc", "tab": "Tab",
    "backspace": "退格", "delete": "Del", "insert": "Ins",
    "up": "↑", "down": "↓", "left": "←", "right": "→",
}


class UiPagesMixin:
    """UI 页面（存档/设置/回看/相册）方法集（经多继承组合进 Renderer，见 engine/renderer.py）。"""

    if TYPE_CHECKING:  # pragma: no cover - 仅供 pyright：实现在 TextMixin（render_text.py）
        def _cached_font_surface(self, font, text, antialias, color) -> pygame.Surface: ...

    # C1：宿主注入属性 / 其他 Mixin 方法——仅静态检查声明（运行期由 Renderer 负责）。
    if TYPE_CHECKING:  # pragma: no cover
        config: Any
        size: Any
        assets_root: Any
        _screen: pygame.Surface
        _font: Any
        _small_font: Any
        _mid_font: Any
        _ui_scale: Any
        _ui_hits: Any
        _ui_int: Any
        _t: Any
        _hovered: Any
        _draw_dim: Any
        _blit_centered_text: Any
        _blit_centered_lines: Any
        _rounded_panel: Any
        _load_cg: Any
        _load_image: Any
        _load_image_path: Any
        _draw_bg_placeholder: Any

    def _draw_slots(self, view) -> None:
        """存档 / 读档：卡片网格（缩略图 + 位名/章节/时间 + 末句）。

        默认 10 个位置：10 位时 5×2 网格，少于此数仍用 3 列；空位灰块可写；
        读档模式空位灰置；左上角「← 返回」回到上个界面；选中格才画 2px 高亮边框。
        """
        self._draw_dim(self.config.alpha("slots"))
        purpose = view.get("slot_purpose", view.get("slots_mode"))
        title = self._t("读档") if purpose == "load" else self._t("存档")
        self._blit_centered_text(title, 24, self._mid_font, (255, 255, 255))
        # P48-b：左上角仅一个「←」箭头（去掉"返回"两字；Esc 返回在底部提示）
        back_img = self._cached_font_surface(self._mid_font, "←", True, (185, 190, 200))
        back_rect = pygame.Rect(24, 18, 40, 36)
        if self._hovered(back_rect):
            pygame.draw.rect(self._screen, self.config.theme_color("primary_soft"),
                             back_rect, border_radius=8)
        self._screen.blit(back_img, (back_rect.centerx - back_img.get_width() // 2,
                                     back_rect.centery - back_img.get_height() // 2))
        self._ui_hits.append((back_rect.copy(), {"kind": "key", "key": "back"}))

        rows = view.get("slots") or []
        cursor = view.get("cursor", 0)
        w, h = self.size
        # 10 个存档位时用 5×2（1280 宽下 5×190 + 4×24 = 1046，仍居中）；否则沿用 3×3 大卡
        if len(rows) > 9:
            cols, cell_w, cell_h, gap = 5, 190, 176, 24
        else:
            cols, cell_w, cell_h, gap = 3, 262, 176, 24
        grid_w = cols * cell_w + (cols - 1) * gap
        left = (w - grid_w) // 2
        bottom_limit = 660
        row_count = max(1, (len(rows) + cols - 1) // cols)
        grid_h = row_count * cell_h + (row_count - 1) * gap
        # 网格在标题与底部提示之间垂直居中（10 格 5×2 时不再挤在屏幕上半部）
        top = max(76, 76 + (bottom_limit - 76 - grid_h) // 2)
        total = len(rows)
        card_radius = 12  # P48-b：存档卡片圆角
        for i, row in enumerate(rows):
            r, col = divmod(i, cols)  # 先行后列（divmod 第一个是行号）
            rect = pygame.Rect(left + col * (cell_w + gap), top + r * (cell_h + gap),
                               cell_w, cell_h)
            if rect.bottom > bottom_limit:
                break
            available = bool(row.get("available", row.get("enabled", True)))
            # 卡片底：深色半透明圆角块
            bg = pygame.Surface(rect.size, pygame.SRCALPHA)
            pygame.draw.rect(bg, (0, 0, 0, 200), bg.get_rect(), border_radius=card_radius)
            self._screen.blit(bg, rect.topleft)
            # P48-b：默认无框；选中格 2px 高亮、悬停 1px（同圆角，键盘导航必须有可见光标）
            if i == cursor and available:
                pygame.draw.rect(self._screen, UI_HIGHLIGHT, rect, 2, border_radius=card_radius)
            elif available and self._hovered(rect):
                pygame.draw.rect(self._screen, UI_HIGHLIGHT, rect, 1, border_radius=card_radius)
            self._ui_hits.append((rect.copy(), {"kind": "item", "index": i, "enabled": available}))
            if row.get("empty"):
                # 空位：灰块 + 位名
                img = self._cached_font_surface(self._small_font, self._t(str(row.get("name") or f"存档 {i + 1}")), True,
                                              (150, 150, 150))
                self._screen.blit(img, (rect.centerx - img.get_width() // 2,
                                        rect.centery - img.get_height() // 2))
                continue
            # 缩略图（等比缩放居中，缺失 → 灰占位块；圆角裁切）
            thumb_rect = pygame.Rect(rect.x + 9, rect.y + 9, cell_w - 18, 104)
            thumb = self._slot_thumb(row)
            if thumb is not None:
                fit = _scale_to_fit(thumb, thumb_rect.width, thumb_rect.height)
                fit_rect = fit.get_rect(center=thumb_rect.center)
                # 圆角遮罩：避免方角缩略图戳破圆角卡片观感
                mask = pygame.Surface(thumb_rect.size, pygame.SRCALPHA)
                pygame.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(),
                                 border_radius=card_radius)
                self._screen.blit(fit, fit_rect.topleft, special_flags=0)
                cut = self._screen.subsurface(thumb_rect).copy()
                cut.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
                self._screen.blit(cut, thumb_rect.topleft)
            else:
                pygame.draw.rect(self._screen, (70, 70, 78), thumb_rect,
                                 border_radius=card_radius)
                pygame.draw.rect(self._screen, (140, 140, 140), thumb_rect, 1,
                                 border_radius=card_radius)
            # 下两行：位名·章节名·时间 / 末句（截断）
            text_x = rect.x + 12
            text_w = rect.width - 24
            line1 = _slot_card_head(row)
            # 卡片首行是拼接文案，逐词翻译（存档 N / 快速存档 / 未命名进度）
            line1 = (line1.replace("快速存档", self._t("快速存档"))
                     .replace("存档 ", self._t("存档") + " ")
                     .replace("未命名进度", self._t("未命名进度")))
            line2 = str(row.get("last_text") or self._t("（无对话记录）"))
            c1 = (255, 255, 255) if available else UI_DISABLED
            c2 = (175, 178, 188) if available else UI_DISABLED
            img1 = self._cached_font_surface(self._small_font, _clip_text(line1, self._small_font, text_w), True, c1)
            img2 = self._cached_font_surface(self._small_font, _clip_text(line2, self._small_font, text_w), True, c2)
            self._screen.blit(img1, (text_x, thumb_rect.bottom + 8))
            self._screen.blit(img2, (text_x, thumb_rect.bottom + 8 + img1.get_height() + 3))

        # P48-b：底部提示只保留「Esc 返回」（其余操作提示去掉）
        self._blit_centered_text(self._t("Esc 返回"), h - 34, self._small_font, (200, 200, 200))

    def _slot_thumb(self, row):
        """⑨ 读存档缩略图：绝对路径直接用；相对路径依次按 assets 根、存档目录、
        存档文件名解析（兼容旧存档里的 "saves/thumb_1.png"）。缺失返回 None。"""
        path = row.get("thumbnail_path")
        if not path:
            return None
        path = str(path)
        if not os.path.isabs(path):
            for cand in (os.path.join(self.assets_root, path),
                         os.path.join(str(save_api.saves_dir()), path),
                         os.path.join(str(save_api.saves_dir()), os.path.basename(path))):
                if os.path.isfile(cand):
                    path = cand
                    break
        return self._load_image_path(path)

    def _draw_setting_control(self, item: dict, value, x: int, center_y: int, width: int) -> None:
        """设置项右侧现代控件：音量滑条 / 打字速度三档 / 开关胶囊 / 文本兜底。"""
        kind = item.get("kind")
        primary = self.config.theme_color("primary")
        dim = self.config.theme_color("text_dim")
        if kind == "volume":
            try:
                ratio = max(0.0, min(1.0, float(value)))
            except (TypeError, ValueError):
                ratio = 0.0
            bar = pygame.Rect(x, center_y - 4, width, 8)
            self._screen.blit(self._rounded_panel(bar, self.config.theme_color("surface_alt"),
                                                 255, 4), bar.topleft)
            fill = pygame.Rect(x, center_y - 4, int(width * ratio), 8)
            if fill.width > 0:
                self._screen.blit(self._rounded_panel(fill, primary, 255, 4), fill.topleft)
            knob_x = x + int(width * ratio)
            pygame.draw.circle(self._screen, (255, 255, 255), (knob_x, center_y), 7)
            pct = self._cached_font_surface(self._small_font, f"{int(ratio * 100)}%", True, dim)
            self._screen.blit(pct, (x + width + 16, center_y - pct.get_height() // 2))
            # P49：滑条自身登记可点区域（含 knob 容差），后画者优先于整行——
            # 点条子 = 按比例定值，点行其他处 = 选中整行。key 用于写设置。
            hit_rect = bar.inflate(0, 14)  # 高 8 太细，加高捕获区便于鼠标
            self._ui_hits.append((hit_rect.copy(),
                                   {"kind": "settings_slider", "key": item.get("key"),
                                    "bar": (bar.x, bar.width)}))
        elif kind == "speed":
            try:
                cur = float(value)
            except (TypeError, ValueError):
                cur = 45.0
            levels = (20, 45, 90)
            labels = ("慢", "中", "快")
            idx = min(range(3), key=lambda i: abs(levels[i] - cur))
            seg_w = (width - 16) // 3
            for i, lab in enumerate(labels):
                seg = pygame.Rect(x + i * (seg_w + 8), center_y - 15, seg_w, 30)
                if i == idx:
                    self._screen.blit(self._rounded_panel(seg, primary, 230, 10), seg.topleft)
                    color = (18, 22, 32)
                else:
                    self._screen.blit(self._rounded_panel(
                        seg, self.config.theme_color("surface_alt"), 210, 10), seg.topleft)
                    color = dim
                img = self._cached_font_surface(self._small_font, lab, True, color)
                self._screen.blit(img, (seg.centerx - img.get_width() // 2,
                                        seg.centery - img.get_height() // 2))
        elif kind == "offset":
            # U7：对话框位置滑条（-80~80 px，0=项目默认），值与 volume 同款交互
            item_min = item.get("min", 0)
            item_max = item.get("max", 0)
            try:
                v = float(value)
            except (TypeError, ValueError):
                v = 0.0
            span = (item_max - item_min) or 1
            ratio = max(0.0, min(1.0, (v - item_min) / span))
            bar = pygame.Rect(x, center_y - 4, width, 8)
            self._screen.blit(self._rounded_panel(bar, self.config.theme_color("surface_alt"),
                                                 255, 4), bar.topleft)
            fill = pygame.Rect(x, center_y - 4, int(width * ratio), 8)
            if fill.width > 0:
                self._screen.blit(self._rounded_panel(fill, primary, 255, 4), fill.topleft)
            pygame.draw.circle(self._screen, (255, 255, 255),
                               (x + int(width * ratio), center_y), 7)
            px = int(round(v / 10.0) * 10)
            lab = "默认" if px == 0 else (f"上移 {abs(px)}" if px < 0 else f"下移 {px}")
            txt = self._cached_font_surface(self._small_font, lab, True, dim)
            self._screen.blit(txt, (x + width + 16, center_y - txt.get_height() // 2))
            self._ui_hits.append((bar.inflate(0, 14).copy(),
                                  {"kind": "settings_slider", "key": item.get("key"),
                                   "bar": (bar.x, bar.width)}))
        elif kind == "key":
            # U10：键位项——捕获中显示「请按键…」，否则显示当前绑定或「默认」
            if item.get("capturing"):
                txt = self._cached_font_surface(self._small_font, "请按键…（Esc 取消）", True,
                                                primary)
            else:
                raw = str(value or "").strip()
                lab = _KEY_LABELS.get(raw, raw.upper()) if raw else "默认"
                txt = self._cached_font_surface(self._small_font, lab, True, dim)
            self._screen.blit(txt, (x + width - txt.get_width(),
                                    center_y - txt.get_height() // 2))
        elif kind == "switch":
            on = bool(value)
            pill = pygame.Rect(x + width - 64, center_y - 15, 64, 30)
            self._screen.blit(self._rounded_panel(
                pill, primary if on else self.config.theme_color("surface_alt"), 235, 15),
                pill.topleft)
            knob_x = pill.right - 16 if on else pill.left + 16
            pygame.draw.circle(self._screen, (255, 255, 255), (knob_x, pill.centery), 11)
            txt = self._cached_font_surface(self._small_font, "ON" if on else "OFF", True,
                                          (18, 22, 32) if on else dim)
            tx = pill.left - 8 - txt.get_width()
            self._screen.blit(txt, (tx, pill.centery - txt.get_height() // 2))
        elif kind == "choice":
            # P37-M1：枚举选项（如语言），显示中文标签而非内部值
            opts = item.get("options") or []
            labels = item.get("labels") or opts
            try:
                idx = opts.index(value)
            except ValueError:
                idx = 0
            lab = labels[idx] if idx < len(labels) else str(value)
            # 箭头用 ← →（中文字体自带），◄/► 在部分字体里是豆腐块
            txt = self._cached_font_surface(self._small_font, f"←  {lab}  →", True, dim)
            self._screen.blit(txt, (x + width - txt.get_width(),
                                    center_y - txt.get_height() // 2))
        else:
            txt = self._cached_font_surface(self._small_font, _format_setting(value, kind), True, dim)
            self._screen.blit(txt, (x + width - txt.get_width(),
                                    center_y - txt.get_height() // 2))

    def _settings_hint(self, group_items) -> str:
        """C1：设置页底部提示按当前页能力变化——有滑条才提示「滑条可拖动」。"""
        has_volume = any(it.get("kind") in ("volume", "offset") for it in (group_items or []))
        if any(it.get("kind") == "key" for it in (group_items or [])):
            return self._t("↑↓ 选择 · 回车改键 · Esc 返回")
        if has_volume:
            return self._t("↑↓ 选择 · 回车调整 · 滑条可拖动 · Esc 返回")
        return self._t("↑↓ 选择 · 回车调整 · Esc 返回")

    def _draw_settings(self, view) -> None:
        """P35/P49 设置：左侧分组导航 + 右侧当前分组页控件行（滑条/档位/开关）。

        P49 分页：一次只画"基础/音频/语音"中一个分组的项，点击左侧导航切换页面；
        音量滑条支持鼠标点击/拖动按比例定值（0~100%）。
        """
        self._draw_dim(self.config.alpha("settings"))
        self._blit_centered_text(self._t("设置"), 96, self._mid_font, (255, 255, 255))
        items = view.get("items") or []
        settings = view.get("settings") or {}
        cursor = view.get("cursor", 0)
        groups = list(view.get("settings_groups") or [])
        tab = int(view.get("settings_tab") or 0)
        if not groups:
            for item in items:
                g = item.get("group") or "基础"
                if g not in groups:
                    groups.append(g)
        if not (0 <= tab < len(groups)):
            tab = 0
        w, _h = self.size
        row_w = self._ui_int("settings", "row_width", 620, 320, w - 120)
        row_h = self._ui_int("settings", "row_height", 72, 44, 110)
        nav_w = self._ui_int("settings", "nav_width", 180, 100, 260)
        top = self._ui_int("settings", "top", 210)
        gap = 24
        total_w = nav_w + gap + row_w
        origin_x = (w - total_w) // 2
        right_x = origin_x + nav_w + gap
        active_group = groups[tab] if tab < len(groups) else None
        # C1：整体内容卡片（导航 + 当前分组）——先画底，行/导航控件后画
        nav_count = max(1, len(groups))
        content_count = max(1, len([it for it in items if (it.get("group") or "基础") == active_group]))
        # U7/U9/U10 后「高级」组项变多：按可用高度自动压缩行距，避免控件掉出屏幕
        avail_h = _h - (top - 68) - 28 - 68 - 24
        if content_count * row_h > avail_h:
            row_h = max(44, avail_h // content_count)
        card_pad = 28
        card_h = 68 + max(nav_count * 54, content_count * row_h + 8) + 28
        # 卡片在标题与底部提示之间垂直居中（只有 1 项时不再挤在屏幕上半部）
        avail_top, avail_bottom = 120, _h - 80
        card_top = max(avail_top, avail_top + (avail_bottom - avail_top - card_h) // 2)
        top = card_top + 68
        card = pygame.Rect(origin_x - card_pad, card_top,
                           total_w + card_pad * 2, card_h)
        self._screen.blit(self._rounded_panel(
            card, self.config.theme_color("surface"), 150, 16,
            border_color=self.config.theme_color("border"), border_width=1), card.topleft)
        nav_title = self._cached_font_surface(self._small_font, self._t("设置分组"), True,
                                              self.config.theme_color("text_dim"))
        self._screen.blit(nav_title, (origin_x, top - 44))
        group_title = f"{active_group} · {content_count} 项"
        gt = self._cached_font_surface(self._small_font, group_title, True,
                                       self.config.theme_color("text"))
        self._screen.blit(gt, (right_x, top - 44))
        pygame.draw.rect(self._screen, self.config.theme_color("primary"),
                         pygame.Rect(right_x, top - 24, 48, 2), border_radius=1)

        # 左侧分组导航：选中页主题色胶囊 + 竖条；点击切页（hit 带组首项全局 index）
        for gi, g in enumerate(groups):
            rect = pygame.Rect(origin_x, top + gi * 54, nav_w, 46)
            active = g == active_group
            if active:
                self._screen.blit(self._rounded_panel(
                    rect, self.config.theme_color("primary_soft"), 230, 10,
                    border_color=self.config.theme_color("primary"), border_width=1),
                    rect.topleft)
                pygame.draw.rect(self._screen, self.config.theme_color("accent"),
                                 pygame.Rect(rect.x + 8, rect.y + 10, 4, rect.height - 20),
                                 border_radius=2)
            img = self._cached_font_surface(self._font, g, True,
                                    (255, 255, 255) if active else self.config.theme_color("text_dim"))
            self._screen.blit(img, (rect.x + 24, rect.centery - img.get_height() // 2))
            first = next((i for i, it in enumerate(items)
                          if (it.get("group") or "基础") == g), 0)
            self._ui_hits.append((rect.copy(), {"kind": "settings_nav", "index": first}))
        # 右侧控件行：只画当前分组的项；组内第 j 行
        group_items = [it for it in items if (it.get("group") or "基础") == active_group]
        for j, item in enumerate(group_items):
            i = items.index(item)  # 全局序号（光标/hit 用全局索引，避免跨组错位）
            rect = pygame.Rect(right_x, top + j * row_h, row_w, row_h - 10)
            bg = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
            bg.fill((*self.config.theme_color("surface"), 186))
            self._screen.blit(bg, rect.topleft)
            # P44-D：默认无框；选中/悬停才显示 1px 状态边框
            if i == cursor or self._hovered(rect):
                pygame.draw.rect(self._screen, self.config.theme_color("primary"),
                                 rect, 1, border_radius=12)
            key = item.get("key")
            value = item.get("value", settings.get(key))
            label = self._cached_font_surface(self._font, str(item.get("label", key)), True,
                                      self.config.theme_color("text"))
            self._screen.blit(label, (rect.x + 26, rect.centery - label.get_height() // 2))
            # 整行先登记（点行空白处 = 选中该行），滑条 hit 在控件内部后登记 → 条子优先
            self._ui_hits.append((rect.copy(), {"kind": "item", "index": i, "enabled": True}))
            ctrl_x = rect.x + max(200, rect.width // 2 + 10)
            ctrl_w = max(120, rect.right - 28 - ctrl_x - 62)
            item = dict(item)
            item["capturing"] = view.get("capturing") == key   # U10：正在改这一项
            self._draw_setting_control(item, value, ctrl_x, rect.centery, ctrl_w)
        self._blit_centered_text(self._settings_hint(group_items),
                                 self.size[1] - int(80 * self._ui_scale),
                                 self._small_font, (200, 200, 200))

    def _draw_backlog(self, view) -> None:
        """回看：对话框区域替换为历史列表（最多 20 条一屏）。"""
        self._draw_dim(self.config.alpha("backlog"))
        # P31-b：回看态点击任意位置 = 关闭（与 Esc 同义）
        self._ui_hits.append((pygame.Rect(0, 0, *self.size), {"kind": "key", "key": "back"}))
        w, h = self.size
        box = pygame.Rect(60, 36, w - 120, h - 72)
        panel = pygame.Surface(box.size, pygame.SRCALPHA)
        panel.fill((0, 0, 0, 245))
        self._screen.blit(panel, box.topleft)
        # P44-D：回看面板默认无边框（轻量、简洁）
        self._blit_centered_text(self._t("回看"), box.top + 10, self._small_font, (255, 255, 200))

        history = view.get("history") or []
        y = box.top + 52
        line_h = self._small_font.get_linesize() + 2
        if history:
            # 一屏最多 20 条：条数多时压紧行距，保证不压到页脚
            available = box.bottom - 40 - y
            line_h = min(line_h, max(18, available // len(history)))
        max_width = box.width - 48
        if not history:
            self._blit_centered_text(self._t("（还没有对话）"), box.top + 120,
                                     self._small_font, (200, 200, 200))
        for entry in history:
            char = entry.get("char")
            # P46：回看去标记显示（列表行不排版富文本）
            text = richtext.strip(str(entry.get("text") or ""))
            line = f"{char}：{text}" if char else text
            img = self._cached_font_surface(self._small_font, _clip_text(line, self._small_font, max_width),
                                          True, (255, 255, 255))
            self._screen.blit(img, (box.x + 24, y))
            y += line_h
        self._blit_centered_text(self._t("↑↓ 翻页 · Esc 返回"), box.bottom - 36,
                                 self._small_font, (200, 200, 200))

    def _detail_image(self, tab, detail, images, index):
        """大图详情取图：返回 (实际下标, 实际图名, Surface|None)。

        P28 E3：幻灯片里某张缺图时向后跳过（循环找第一张可加载的），全缺才回退格名单图。
        """
        shown, img = str(detail), None
        idx = 0
        if tab == 0 and images:
            n = len(images)
            idx = max(0, min(int(index or 0), n - 1))
            for k in range(n):
                j = (idx + k) % n
                cand = self._load_cg(images[j])
                if cand is not None:
                    idx, shown, img = j, images[j], cand
                    break
        if img is None:
            img = self._load_cg(detail) if tab == 0 else self._load_image(str(detail))
        return idx, shown, img

    def _draw_gallery(self, view) -> None:
        """画廊：页签（CG 鉴赏 / 立绘鉴赏）+ 缩略图网格 / 大图详情。

        P28 E1：未解锁格画 cg_locked 灰锁图，光标在锁格时底部提示"未解锁"。
        P28 E3：详情页可播放幻灯片（gallery_config.json 的图序列，UI 每 5s 自动换图）。
        """
        self._draw_dim(self.config.alpha("gallery"))
        g = view.get("gallery") or {}
        w, h = self.size
        tabs = g.get("tabs") or ["CG 鉴赏", "立绘鉴赏"]
        tab = g.get("tab", 0)

        detail = g.get("detail")
        if detail is not None:
            # 大图鉴赏：CG 走双查（新名优先，旧 cg_ 前缀兜底），立绘直接用 char_expr
            images = [str(x) for x in (g.get("detail_images") or [])]
            idx, shown, img = self._detail_image(tab, detail, images, g.get("detail_index") or 0)
            self._screen.fill((0, 0, 0))
            if img is None:
                self._blit_centered_lines(
                    [f"缺图: {shown}（images/{shown}.png）"],
                    pygame.Rect(0, 0, w, h - 60), (255, 255, 255))
            else:
                scaled = _scale_to_fit(img, w, h - 60)
                self._screen.blit(scaled, ((w - scaled.get_width()) // 2,
                                           (h - 60 - scaled.get_height()) // 2))
            title = str(detail) if shown == str(detail) else f"{detail} · {shown}"
            if images:
                title += f"（{idx + 1}/{len(images)}）"
            self._blit_centered_text(title, h - 48, self._small_font, (255, 255, 200))
            hint = self._t("←→ 手动切换 · 回车 / Esc 返回网格" if len(images) > 1
                           else "回车 / Esc 返回网格")
            self._blit_centered_text(hint, h - 26, self._small_font, (200, 200, 200))
            # P31-b：大图页任意位置点击 = 返回网格
            self._ui_hits.append((pygame.Rect(0, 0, w, h), {"kind": "key", "key": "back"}))
            return

        # 页签行
        x = w // 2 - 200
        for i, t in enumerate(tabs):
            color = (255, 255, 200) if i == tab else (160, 160, 160)
            img = self._cached_font_surface(self._font, str(t), True, color)
            self._screen.blit(img, (x + i * 200, 40))
            # P31-b：页签可点（切页签）
            self._ui_hits.append((pygame.Rect(x + i * 200 - 8, 36,
                                              max(96, img.get_width() + 16),
                                              img.get_height() + 12),
                                  {"kind": "gallery_tab", "index": i}))
            if i == tab:
                pygame.draw.line(self._screen, (255, 255, 200),
                                 (x + i * 200, 40 + img.get_height() + 4),
                                 (x + i * 200 + img.get_width(), 40 + img.get_height() + 4), 2)
        if g.get("locked_selected"):
            hint, hint_color = self._t("未解锁"), (255, 220, 120)
        else:
            hint, hint_color = self._t("←→ 切页签 · ↑↓ 移动 · 回车看大图 · Esc 返回"), (200, 200, 200)
        self._blit_centered_text(hint, h - 30, self._small_font, hint_color)

        items = g.get("items") or []
        if not items:
            msg = "（还没有解锁 CG）" if tab == 0 else "（还没有见过立绘）"
            self._blit_centered_text(msg, h // 2 - 40, self._font, (180, 180, 180))
            return

        cols = max(1, int(g.get("cols") or 4))
        cursor = g.get("cursor", 0)
        cell_w = 220
        cell_h = 150
        gap = 24
        grid_w = cols * cell_w + (cols - 1) * gap
        left = (w - grid_w) // 2
        top = 120
        for i, item in enumerate(items):
            row, col = divmod(i, cols)
            rect = pygame.Rect(left + col * (cell_w + gap), top + row * (cell_h + gap),
                               cell_w, cell_h)
            name = str(item.get("name") or "")
            locked = not item.get("unlocked", True)
            if locked:
                lock_img = self._load_cg("cg_locked")
                if lock_img is not None:
                    thumb = _scale_to_fit(lock_img, cell_w, cell_h - 24)
                    self._screen.blit(thumb, (rect.centerx - thumb.get_width() // 2, rect.y))
                else:
                    # 灰锁图也缺失：深灰块占位，仍然表达"未解锁"
                    pygame.draw.rect(self._screen, (48, 48, 48),
                                     (rect.x, rect.y, cell_w, cell_h - 24))
                label_text = "???"
            else:
                img = (self._load_cg(name) if item.get("kind") == "cg"
                       else self._load_image(name))
                if img is not None:
                    thumb = _scale_to_fit(img, cell_w, cell_h - 24)
                    self._screen.blit(thumb, (rect.centerx - thumb.get_width() // 2, rect.y))
                else:
                    # ④ 画廊缩略图占位：深色渐变
                    self._draw_bg_placeholder((rect.x, rect.y, cell_w, cell_h - 24), self._screen)
                label_text = name
            label = self._cached_font_surface(self._small_font, label_text, True,
                                            (150, 150, 150) if locked else (255, 255, 255))
            self._screen.blit(label, (rect.centerx - label.get_width() // 2, rect.bottom - 22))
            if i == cursor:
                pygame.draw.rect(self._screen, UI_HIGHLIGHT, rect, 2)
            # P31-b：缩略图格可点（锁格也登记，由 ui 判未解锁后忽略）
            self._ui_hits.append((rect.copy(), {"kind": "item", "index": i, "enabled": True}))
