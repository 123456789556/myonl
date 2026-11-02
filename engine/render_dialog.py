"""MYONL 渲染层 · 对话/选项/打字机（renderer.py 模块化拆分）。

DialogMixin 的方法原样迁自 engine/renderer.py：方法体与签名不变，
经 self 访问实例状态（__init__ 中初始化）与其他 Mixin 方法；
常量与纯函数统一来自 render_utils（engine.renderer 再导出，命名空间不变）。
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pygame

from . import richtext
from .render_utils import (
    CHOICE_ROW_HEIGHT,
)


class DialogMixin:
    """对话/选项/打字机方法集（经多继承组合进 Renderer，见 engine/renderer.py）。"""

    if TYPE_CHECKING:  # pragma: no cover - 仅供 pyright：实现在 TextMixin（render_text.py）
        def _wrap_text_cached(self, text, font, max_width) -> list: ...
        def _cached_font_surface(self, font, text, antialias, color) -> pygame.Surface: ...

    # C2：宿主（Renderer.__init__）注入的实例属性 / 其他 Mixin 方法——仅静态检查声明。
    # 拆模块后 pyright 单看 Mixin 时看不到宿主属性；这里只补声明，运行期仍由 Renderer 赋值。
    if TYPE_CHECKING:  # pragma: no cover
        config: Any
        settings: Any
        size: Any
        _screen: pygame.Surface
        _font: Any
        _small_font: Any
        _option_font: Any
        _font_book: Any
        _ui_hits: Any
        _ui_int: Any
        _ui_str: Any
        _t: Any
        _hovered: Any
        _draw_dim: Any
        _rounded_panel: Any
        _make_vgradient: Any
        _draw_text_with_shadow: Any
        _now_ms: Any
        _blit_rich_line: Any
        _rich_segments: Any
        _rich_line_x: Any
        _quickbar_layout: Any
        _text_align: Any
        _splash_mode: Any
        _ui_hidden: Any
        _voice_busy: Any
        _reduce_effects: Any

    def _tw_visible_len(self) -> int:
        """打字机全文的可视字符数（P46：富文本标记不占字数；纯文本与原 len 一致）。"""
        return len(richtext.strip(self._tw_text))

    def typewriter_complete(self) -> bool:
        """打字机是否已显示完全文。"""
        return self._tw_shown >= self._tw_visible_len()

    def reveal_all(self) -> None:
        """打字机直接显示全文（auto 测试钩子 / reveal 内部处理）。"""
        self._tw_shown = float(self._tw_visible_len())

    # ==================== 内部：状态跟踪 ====================

    def _update_typewriter(self, history, dt_ms, pending) -> None:
        """打字机推进。history 长度或末条变化时重置；选项出现时暂停推进。"""
        last = history[-1] if history else {}
        key = (len(history), last.get("char"), last.get("text"))
        if key != self._history_key:
            self._history_key = key
            self._tw_text = str(last.get("text") or "")
            self._tw_shown = 0.0
            # P30-S1-5：换句重置翻页状态
            self._page_index = 0
            self._page_count = 1
            # ⑭ history 变化 → 旁白冷却重置
            self._narration_cooldown_t0 = None
        if pending:
            return  # 选项出现时隐藏打字机区域，不推进
        speed = float(self.settings.get("text_speed", 30))  # 字符/秒
        visible = self._tw_visible_len()  # P46：标记不占字数
        if self._tw_shown < visible:
            self._tw_shown = min(visible, self._tw_shown + speed * dt_ms / 1000.0)
            return
        # ⑭ 打字机刚完成 + 旁白（char=None） → 设 400ms 推进冷却
        if last.get("char") is None and self._narration_cooldown_t0 is None:
            self._narration_cooldown_t0 = self._now_ms() + 400

    def _update_choice(self, pending) -> None:
        """选项组跟踪：新选项组出现时，高亮重置到第一个可选项。

        ⑤ 锁输入延迟到 _draw_choices 画完选项后才启动（真实游戏里 render 必走，
        测试里可能跳过 render 直接 handle_input，此时锁不生效）。"""
        if not pending:
            self._options = None
            self._choice_key = None
            self._choice_index = 0
            self._choice_lock_t0 = None
            self._choice_is_new = False
            return
        options = pending.get("options") or []
        key = (pending.get("line"), tuple(str(o.get("text", "")) for o in options))
        if key != self._choice_key:
            self._choice_key = key
            self._options = options
            self._choice_index = 0
            for i, o in enumerate(options):
                if o.get("available", True):
                    self._choice_index = i
                    break
            # ⑤ 标记新选项组，render 画完选项后设时间锁
            self._choice_is_new = True
            self._choice_lock_t0 = None

    def _advance_or_reveal(self) -> dict:
        """空格/点击：打字机未完 → reveal；已完且还有分页 → 翻页；否则 advance。

        玩家手动操作**不受**旁白冷却影响（可立即推进）。旁白冷却只拦自动推进。"""
        if self.settings.get("voice_auto_advance") and self._voice_busy():
            return {"action": "none"}
        if not self.typewriter_complete():
            self.reveal_all()
            return {"action": "reveal"}
        # P30-S1-5：长段落还有下一页 → 翻页（不推进剧情）
        if self._next_page():
            return {"action": "none"}
        return {"action": "advance"}

    def _has_next_page(self) -> bool:
        """当前台词是否还有下一页（P30-S1-5，自动推进判定用）。"""
        return self._page_count > 1 and self._page_index < self._page_count - 1

    def _next_page(self) -> bool:
        """翻到下一页；已到末页返回 False。"""
        if not self._has_next_page():
            return False
        self._page_index += 1
        return True

    def _choice_available(self, idx) -> bool:
        return (self._options is not None
                and 0 <= idx < len(self._options)
                and bool(self._options[idx].get("available", True)))

    def _move_choice(self, delta: int) -> None:
        """方向键在可选项之间循环移动高亮。"""
        opts = self._options or []
        n = len(opts)
        if n == 0:
            return
        for step in range(1, n + 1):
            j = (self._choice_index + delta * step) % n
            if opts[j].get("available", True):
                self._choice_index = j
                return

    def _choice_at(self, pos):
        """鼠标位置命中的可点选项序号，未命中返回 None。"""
        for rect, idx, available in self._choice_rects:
            if available and rect.collidepoint(pos):
                return idx
        return None

    # ==================== 内部：绘制 ====================

    def _dialog_bottom_reserve(self) -> int:
        """快捷栏贴底时给对话框文字预留的高度，避免最后一行被按钮压住。"""
        qb = self._quickbar_layout()
        if not qb["enabled"] or self._ui_str("quickbar", "position", "bottom") != "bottom":
            return 0
        return qb["bh"] + self._ui_int("quickbar", "margin_y", 10, 0, 80) + 4

    def _dialog_layout(self, history, characters, pending: bool) -> dict | None:
        """对话框文案布局（纯计算、不绘制，便于无头断言）。

        P30-S1-1：出选项（pending）时画上一句全文并压暗，代替原来的空白大框；
        P30-S1-5：playing 态按对话框可用行数分页（pages），翻页由 _draw_dialog 驱动；
        P0-1：按角色 kind 取 config.dialogue 几何（default 主对话框 / nvl 整屏旁白）。
        """
        if not history:
            return None
        last = history[-1]
        char = last.get("char")
        text = str(last.get("text") or "")
        # P46：打字机按可视字符截取（标记完整保留、不占字数）
        shown = text if pending else richtext.visible_prefix(
            self._tw_text, int(self._tw_shown))
        w, h = self.size
        # 角色 kind 决定布局；旁白/未定义角色一律 default
        kind = "default"
        if char is not None:
            try:
                kind = (characters.get(char) or {}).get("kind") or "default"
            except AttributeError:
                pass
        # @[[...]] 整屏独白：台词自带布局，优先于角色 kind
        kind = str(last.get("layout") or kind)
        dlg = self.config.dialogue(kind)
        # U7：玩家侧透明度倍率（设置页滑条）——1.0 时完全跟随项目 config，老工程行为不变
        if kind != "nvl":
            try:
                _alpha_scale = float((self.settings or {}).get("dialog_alpha_scale", 1.0))
            except (TypeError, ValueError):
                _alpha_scale = 1.0
            if 0.0 < _alpha_scale < 1.0:
                _base_alpha = int(dlg.get("bg_alpha", 150))
                dlg["bg_alpha"] = max(16, int(_base_alpha * _alpha_scale))
            try:
                _off_y = int((self.settings or {}).get("dialog_offset_y", 0) or 0)
            except (TypeError, ValueError):
                _off_y = 0
            if _off_y:
                dlg["offset_y"] = int(dlg.get("offset_y", 0)) + _off_y
        if kind == "nvl":
            top = int(dlg.get("top", 200))
            bottom = int(dlg.get("bottom", 60))
            margin = int(dlg.get("margin", 80))
            line_gap = int(dlg.get("line_gap", 8))
        else:
            height = int(dlg.get("height", 180))
            top = h - height
            margin = int(dlg.get("margin", 24))
            line_gap = 0
        # P51：玩家可调几何——布局与绘制共用同一偏移（off_x/off_y）
        off_x = int(dlg.get("offset_x", 0))
        off_y = int(dlg.get("offset_y", 0))
        top += off_y
        margin = max(0, margin + off_x)
        # 角色名颜色取 characters 定义（未定义/非法用白色）
        name_color = (255, 255, 255)
        if char is not None:
            try:
                name_color = pygame.Color(
                    (characters.get(char) or {}).get("color") or "#ffffff"
                )
            except (ValueError, TypeError):
                pass
        line_h = self._font.get_linesize()
        # P44-D：旁白与角色台词共用同一套排版基线——名字行下方起排，
        # 保证两种说话栏的正文位置、字号、对齐方式完全一致。
        if kind == "nvl":
            start_y = top + int(dlg.get("narration_y", 16))
        else:
            start_y = top + int(dlg.get("name_y", 12)) + self._font.get_height() \
                + int(dlg.get("name_gap", 8))
        # P46：折行按去标记纯文本计算（与旧版式一致），样式由 rich 行逐片段绘制
        lines = self._wrap_text_cached(richtext.strip(shown), self._font, w - margin * 2)
        rich = self._rich_segments(shown, lines)
        # 可用行数：布局高度 - 顶部偏移 - 底留一行（防最后一行贴边）
        # P30-S1-5：选项态（pending）不分页，全文一页（玩家优先看选项）
        # P0-1：nvl 整屏显示也不分页（整屏够用；超出部分截断由 _draw_dialog 兜底）
        reserve = 0
        if pending or kind == "nvl":
            pages = [lines] or [[]]
            rich_pages = [rich]
        else:
            reserve = self._dialog_bottom_reserve()
            avail_h = int(dlg.get("height", 180)) - (start_y - top) - line_h - reserve
            per_page = max(1, avail_h // line_h)
            pages = [lines[i:i + per_page] for i in range(0, len(lines), per_page)] or [[]]
            rich_pages = [rich[i:i + per_page] for i in range(0, len(rich), per_page)] or [[]]
        return {
            "char": char,
            "kind": kind,
            "name_color": name_color,
            "lines": lines,
            "rich": rich,  # P46：与 lines/pages 同构的样式行（绘制用；lines 保持纯文本兼容）
            "rich_pages": rich_pages,  # P46：与 pages 同构的样式分页
            "align": self._text_align(dlg),  # P46：left/center/right（非法值已回落 left）
            "pages": pages,
            "color": self.config.color("dialog_fg_dim") if pending else self.config.color("dialog_fg"),
            "start_y": start_y,
            "line_h": line_h,
            "margin": margin,
            "line_gap": line_gap,
            "reserve": reserve if kind != "nvl" else 0,
        }

    def _dialog_top(self) -> int:
        """对话框顶 y：跟随 config dialogue.default.height（P0-1，选项/UI 区域边界同源）。"""
        return self.size[1] - int(self.config.dialogue("default").get("height", 180))

    def _draw_dialog(self, history, characters, pending) -> None:
        w, h = self.size
        if self._splash_mode:  # P26 T1：序幕模式不画对话框，台词当电影字幕
            self._draw_splash_text(history)
            return
        # P48：截图模式——隐藏字幕栏/快捷栏，仅保留顶部 ▼（可点击恢复）；选项态不隐藏（不能卡死）
        if self._ui_hidden and not pending:
            height = int(self.config.dialogue("default").get("height", 200))
            self._draw_subtitle_toggle(h - height, w)
            return
        layout = self._dialog_layout(history, characters, bool(pending))
        if layout is None:
            return
        kind = layout["kind"]
        dlg = self.config.dialogue(kind)
        margin = layout["margin"]
        line_h = layout["line_h"]
        line_gap = layout["line_gap"]
        if kind == "nvl":
            # 视觉优化：NVL 整屏渐变底——顶部 80px 渐入、中部稳定、底部 80px 渐出
            # 消除纯色全屏的硬边感，文字区域始终有足够对比度
            top_fade = 80
            bottom_fade = 80
            mid_alpha = int(dlg.get("bg_alpha", 90))
            if h > top_fade + bottom_fade:
                top_panel = self._make_vgradient(w, top_fade, 0, mid_alpha)
                mid_panel = pygame.Surface((w, h - top_fade - bottom_fade), pygame.SRCALPHA)
                mid_panel.fill((0, 0, 0, mid_alpha))
                bot_panel = self._make_vgradient(w, bottom_fade, mid_alpha, 0)
                self._screen.blit(top_panel, (0, 0))
                self._screen.blit(mid_panel, (0, top_fade))
                self._screen.blit(bot_panel, (0, h - bottom_fade))
            else:
                panel = self._make_vgradient(w, h, 0, mid_alpha)
                self._screen.blit(panel, (0, 0))
        else:
            height = int(dlg.get("height", 180))
            top = h - height
            bg_alpha = int(dlg.get("bg_alpha", 160))
            radius = int(dlg.get("radius", 8))
            # P51：玩家可调几何——横向/纵向偏移 + 自定义面板宽（默认 0=贴边全宽）
            off_x = int(dlg.get("offset_x", 0))
            off_y = int(dlg.get("offset_y", 0))
            pw = int(dlg.get("panel_width", 0))
            pixel_scale = self.config.pixel_scale()
            if radius > 0:
                # P44-D 轻量化：默认无边框的圆角面板，只有鼠标悬停时才显示状态边框
                # P51：像素化面板（低分辨率+NEAREST）；玩家偏移/宽度作用于面板矩形
                if pw > 0:
                    pw = max(0, min(pw, w))
                    rect = pygame.Rect((w - pw) // 2 + off_x, top + off_y, pw, height - 8)
                else:
                    rect = pygame.Rect(18 + off_x, top + off_y, w - 36, height - 8)
                shadow_rect = rect.move(4, 6)
                shadow = self._rounded_panel(
                    shadow_rect, self.config.theme_color("shadow"), 70, radius,
                    pixelated=self.config.pixelated(), pixel_scale=pixel_scale,
                )
                self._screen.blit(shadow, shadow_rect.topleft)
                hover = self._hovered(rect)
                panel = self._rounded_panel(
                    rect, self.config.theme_color("surface"), bg_alpha, radius,
                    border_color=self.config.theme_color("primary") if hover else None,
                    border_width=1 if hover else 0,
                    pixelated=self.config.pixelated(), pixel_scale=pixel_scale,
                )
                self._screen.blit(panel, rect.topleft)
            else:
                # P48：无圆角——顶部一段加深区（上深下淡羽化）+ 顶边一条不明显细线
                # P51：玩家横向/纵向偏移作用于整条贴边加深区
                deep = min(36, height // 3)
                deep_alpha = min(255, bg_alpha + 70)
                top_panel = self._make_vgradient(w, deep, deep_alpha, bg_alpha)
                bot_panel = pygame.Surface((w, height - deep), pygame.SRCALPHA)
                bot_panel.fill((0, 0, 0, bg_alpha))
                self._screen.blit(top_panel, (off_x, top + off_y))
                self._screen.blit(bot_panel, (off_x, top + deep + off_y))
                # 顶边细线（不明显：低透明度深灰 1px）
                pygame.draw.line(self._screen, (16, 18, 24, 70), (off_x, top + off_y),
                                 (w + off_x, top + off_y))
            # P48：对话框顶边线上方中央的向下小三角 ▼——点击隐藏/显示字幕栏（截图用）
            if not pending and dlg.get("next_arrow", True):
                self._draw_subtitle_toggle(top + int(dlg.get("offset_y", 0)), w)
            # 移除白色硬边框——渐变羽化本身就是自然边界，描边会制造拼接感
            # （保留 border_width 配置项供需要的游戏显式开启，但默认不画）

        char = layout["char"]
        color = layout["color"]
        start_y = layout["start_y"]

        # P30-S1-5：playing 分页显示；选项态显示全文（不分页，优先让玩家看选项）
        # P0-1：nvl 整屏显示全文（不分页）
        if pending or kind == "nvl":
            lines = layout["lines"]
            rich_lines = layout["rich"]
        else:
            pages = layout["pages"]
            self._page_count = len(pages)
            self._page_index = max(0, min(self._page_index, self._page_count - 1))
            lines = pages[self._page_index]
            rich_lines = layout["rich_pages"][self._page_index]

        # P44-D：角色名纯文本、无外框，固定在该说话栏左上角（nvl 为全屏栏左上）
        if char is not None:
            name_y = (int(dlg.get("top", 200)) - line_h) if kind == "nvl" else \
                (h - int(dlg.get("height", 180)) + int(dlg.get("name_y", 12)))
            self._draw_text_with_shadow(str(char), self._font, layout["name_color"],
                                        (margin, name_y))
        # P46：正文按 config 对齐（left 顶格默认 / center / right），旁白与角色台词同规范；
        # 富文本样式行逐片段绘制，带阴影保证浅色背景可读
        align = layout["align"]
        y = start_y
        last_line_y = y
        last_line_w = 0
        last_line_text = ""
        if kind == "nvl":
            bottom_limit = h - 8
        else:
            # 对话框底 = 屏幕底；贴底快捷栏时额外让出按钮高度，避免压住末行
            bottom_limit = h - line_h - int(layout.get("reserve", 0))
        for line, rich_line in zip(lines, rich_lines):
            if y > bottom_limit:
                break  # 兜底截断：正常分页已覆盖，极端超长不越界
            line_w = richtext.line_width(rich_line, self._font_book.get)
            x = self._rich_line_x(align, line_w, margin)
            self._blit_rich_line(rich_line, x, y, color)
            last_line_y = y
            last_line_w = line_w
            last_line_text = line
            y += line_h + line_gap
        # P37-T2 打字机光标：非选项态且打字机未完成时，末行末尾画闪烁竖线（随对齐位置）
        if (not pending and not self.typewriter_complete()
                and kind != "nvl" and last_line_text):
            # U9：减少动效时不闪烁（常亮），避免光敏不适
            if self._reduce_effects() or (self._now_ms() // 500) % 2 == 0:
                cx = self._rich_line_x(align, last_line_w, margin) + last_line_w + 4
                ch = int(line_h * 0.75)
                cy = last_line_y + (line_h - ch) // 2
                pygame.draw.rect(self._screen, self.config.theme_color("accent"),
                                 pygame.Rect(cx, cy, 3, ch), border_radius=1)

        if pending:
            # 出选项时右上角给操作提示，代替原来的「选择：」提示字
            hint = self._cached_font_surface(self._small_font, self._t("↑↓ 选择 · 回车确认"), True, (200, 200, 200))
            hint_y = 12 if kind == "nvl" else h - int(dlg.get("height", 180)) + 12
            self._screen.blit(hint, (w - margin - hint.get_width(), hint_y))
        elif self._voice_busy():
            # 配音播放中指示（对话框右上角）
            hint = self._cached_font_surface(self._small_font, self._t("配音中"), True, (255, 255, 200))
            hint_y = 12 if kind == "nvl" else h - int(dlg.get("height", 180)) + 12
            self._screen.blit(hint, (w - margin - hint.get_width(), hint_y))

        # P30-S1-5：还有下一页 → 右下角「▽ 继续」提示（打字机放完才出现）
        if (not pending and self._page_count > 1
                and self._page_index < self._page_count - 1
                and self.typewriter_complete()):
            tip = self._cached_font_surface(self._small_font, self._t("▽ 继续"), True, (200, 200, 200))
            reserve = int(layout.get("reserve", 0)) if kind != "nvl" else 0
            tip_y = h - 40 if kind == "nvl" else \
                h - int(dlg.get("height", 180)) + int(dlg.get("height", 180)) - \
                tip.get_height() - 10 - reserve
            self._screen.blit(tip, (w - margin - tip.get_width(), tip_y))
        # P44-C：单页/末页打字机完成后右下角小 ▼，提示可推进下一句
        elif (not pending and dlg.get("next_arrow", True)
                and self.typewriter_complete() and kind != "nvl"):
            self._draw_next_arrow(w, h)

    def _draw_next_arrow(self, w, h) -> None:
        """P44-D：对话区底部居中的推进小三角按钮（主流 Galgame 的下一幕习惯）。

        默认无框，鼠标悬停时主题色高亮；点击对话区域任意位置均可推进。
        """
        # 对话框底部居中、略高于快捷栏：任何布局下都清晰可见且不与按钮重叠
        rect = pygame.Rect(w // 2 - 14, h - 66, 28, 28)
        hover = self._hovered(rect)
        color = self.config.theme_color("primary") if hover else (190, 195, 205)
        # 轻微呼吸感：透明度缓慢浮动，提示此处可继续；不做复杂动画
        alpha = 255 if hover else 175 + int(55 * abs((self._now_ms() % 1600) / 800.0 - 1))
        tri = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
        cx = rect.width // 2
        pygame.draw.polygon(tri, (*color, alpha), [(cx - 7, 10), (cx + 7, 10), (cx, 21)])
        self._screen.blit(tri, rect.topleft)
        self._ui_hits.append((rect.copy(), {"kind": "next_arrow"}))

    def _draw_subtitle_toggle(self, top, w) -> None:
        """字幕隐藏条（对话框顶部的悬停机关）。

        设计规格：
        - 捕获区：横跨对话框宽度、高 24px 的矩形，紧贴对话框顶边上方
        - 默认：完全透明（α0），屏幕上什么都看不到
        - 鼠标悬停到捕获区：显现一条 2px 细线（顶边），横贯整宽
          - 颜色：主题色（浅灰白）半透明 α160
          - 捕获区本体底色 α0——不覆盖、不脏化背景画面
          - 顶边正中央放一个句号「.」，同色同透明度
        - 点击 = 字幕整体隐藏（截图态）；隐藏中再点 = 恢复
        - 隐藏态：顶边细线提高到 α200（略亮一点，提示"再点恢复"）

        可配置项（config.json dialogue.default.curtain）：
        - capture_height: 捕获区高度（默认 24）
        - line_height: 顶边线高度（默认 2）
        - alpha_normal: 正常态显现时 α（默认 160）
        - alpha_hidden: 隐藏态 α（默认 200）
        - symbol: 中央符号（默认 "."）
        - symbol_size: 符号字号（默认 10）
        - full_width: 是否拉通整屏宽（默认 true）
        """
        cfg = self.config.dialogue("default").get("curtain") or {}

        # 捕获区高度（默认 24px）
        try:
            capture_h = max(12, min(48, int(cfg.get("capture_height", 24))))
        except (TypeError, ValueError):
            capture_h = 24

        # 顶边线高度（默认 2px）
        try:
            line_h = max(1, min(6, int(cfg.get("line_height", 2))))
        except (TypeError, ValueError):
            line_h = 2

        # α 值：正常态 160，隐藏态 200
        try:
            alpha_normal = max(60, min(255, int(cfg.get("alpha_normal", 160))))
        except (TypeError, ValueError):
            alpha_normal = 160
        try:
            alpha_hidden = max(alpha_normal, min(255, int(cfg.get("alpha_hidden", 200))))
        except (TypeError, ValueError):
            alpha_hidden = 200

        # 中央符号（默认句号）
        symbol = str(cfg.get("symbol", ".") or ".")
        try:
            symbol_size = max(6, min(20, int(cfg.get("symbol_size", 10))))
        except (TypeError, ValueError):
            symbol_size = 10

        # 宽度：默认拉通整屏
        full_width = bool(cfg.get("full_width", True))
        bar_w = w if full_width else min(w, int(cfg.get("width", w)))

        # 捕获区位置：紧贴对话框顶边上方
        hit_rect = pygame.Rect((w - bar_w) // 2, top - capture_h, bar_w, capture_h)
        hover = self._hovered(hit_rect)

        # 判定当前 α
        if self._ui_hidden:
            alpha = alpha_hidden
        else:
            alpha = alpha_normal

        # 未悬停时：完全透明（不画任何东西）
        if not hover:
            self._ui_hits.append((hit_rect.copy(), {"kind": "toggle_subtitles"}))
            return

        # 画顶边细线（只有线，底色 α0）
        color = self.config.theme_color("text")  # 浅灰白主题色
        line_surface = pygame.Surface((bar_w, line_h), pygame.SRCALPHA)
        pygame.draw.rect(line_surface, (*color, alpha), line_surface.get_rect())
        line_y = top - line_h  # 紧贴捕获区底部（即对话框顶边位置）
        self._screen.blit(line_surface, ((w - bar_w) // 2, line_y))

        # 画中央符号
        if symbol:
            sym_font = self._small_font  # 复用现有字体
            # 如果 symbol_size 与默认字号差距太大，尝试用对应字号
            if abs(symbol_size - self.config.font("small")) > 4:
                try:
                    from . import richtext
                    sym_font = self._font_book.get(symbol_size, False, False)
                except Exception:
                    pass
            sym_text = self._cached_font_surface(sym_font, symbol, True, (*color, alpha))
            sym_x = w // 2 - sym_text.get_width() // 2
            sym_y = line_y - sym_text.get_height() // 2 + line_h // 2
            self._screen.blit(sym_text, (sym_x, sym_y))

        self._ui_hits.append((hit_rect.copy(), {"kind": "toggle_subtitles"}))

    def _draw_splash_text(self, history) -> None:
        """序幕字幕——电影式居中字幕，带渐变底条保证可读、与画面自然融合。"""
        if not history:
            return
        # P46：打字机按可视字符截取；字幕保持电影式居中，支持富文本样式
        raw = str(history[-1].get("text") or "")
        text = richtext.visible_prefix(raw, int(self._tw_shown))
        if not text:
            return
        w, h = self.size
        lines = self._wrap_text_cached(richtext.strip(text), self._font, w - 200)
        if not lines:
            return
        rich_lines = self._rich_segments(text, lines)
        line_h = self._font.get_linesize()
        # 渐变底条：覆盖文字上下各 20px，垂直渐入渐出
        strip_top = h - 120 - (len(lines) - 1) * line_h - 20
        strip_h = len(lines) * line_h + 40
        strip = self._make_vgradient(w, strip_h, 0, 160)
        self._screen.blit(strip, (0, strip_top))
        strip_bot = self._make_vgradient(w, 20, 160, 0)
        self._screen.blit(strip_bot, (0, strip_top + strip_h))
        # 文字带 4 向阴影（居中字幕，不随 dialogue.align 变化）
        y = h - 120 - (len(lines) - 1) * line_h
        for i, rich_line in enumerate(rich_lines):
            line_w = richtext.line_width(rich_line, self._font_book.get)
            self._blit_rich_line(rich_line, (w - line_w) // 2, y + i * line_h,
                                 (255, 255, 255))

    def _draw_choices(self) -> None:
        """选项列表：窄条 420px 居中；选中行渐变高亮+圆角，非选中半透明+细边。

        视觉优化：用渐变替代纯色填充、圆角替代直角、文字带阴影，
        让选项与对话框风格统一、融入背景而非悬浮拼接。
        """
        w, _h = self.size
        options = self._options or []
        n = len(options)
        self._choice_rects = []
        row_w = self._ui_int("choices", "width", 420, 240, w - 80)
        row_h = self._ui_int("choices", "row_height", CHOICE_ROW_HEIGHT, 28, 90)
        # C2：选项组与对话框的间距单独可配（ui.choices.dialog_gap，默认 40）；
        # 老配置只写 ui.choices.gap 时沿用旧行为，避免升级后选项整体位移。
        _raw_choices = (self.config.data.get("ui") or {}).get("choices") or {}
        if "dialog_gap" in _raw_choices:
            dialog_gap = self._ui_int("choices", "dialog_gap", 40, 8, 160)
        elif "gap" in _raw_choices:
            dialog_gap = self._ui_int("choices", "gap", 24, 4, 60)
        else:
            dialog_gap = self._ui_int("choices", "dialog_gap", 40, 8, 160)
        radius = self._ui_int("choices", "radius", 8, 0, 30)
        bottom = self._dialog_top() - dialog_gap + int(self.settings.get("choice_offset_y", 0))
        mouse = getattr(self, "_mouse_pos", None)
        accent = self.config.theme_color("accent")
        for i, opt in enumerate(options):
            y = bottom - row_h * (n - i)
            rect = pygame.Rect(w // 2 - row_w // 2, y, row_w, row_h - 6)
            available = bool(opt.get("available", True))
            hover = bool(mouse) and rect.collidepoint(mouse)
            if i == self._choice_index and available:
                # 选中行：垂直渐变深蓝 + 圆角 + 亮边 + 白字阴影 + 阴影投影
                sel_bg = self.config.color("selected_bg")
                sel_top = tuple(max(0, c - 20) for c in sel_bg)
                # P37-T3 选中卡片阴影：与对话框投影风格统一
                sh = self._rounded_panel(rect.move(2, 3), self.config.theme_color("shadow"), 80, radius)
                self._screen.blit(sh, rect.move(2, 3).topleft)
                bg = self._make_vgradient(rect.width, rect.height, 200, 255, sel_top)
                self._screen.blit(bg, rect.topleft)
                pygame.draw.rect(self._screen, self.config.color("selected_border"), rect, 2,
                                 border_radius=radius)
                # 左侧主题色竖条：一眼锁定当前选项（现代卡片式选项的常见细节）
                pygame.draw.rect(self._screen, accent,
                                 pygame.Rect(rect.x + 6, rect.y + 10, 4, rect.height - 20),
                                 border_radius=2)
                text_color = self.config.color("selected_fg")
            elif hover and available:
                bg = self._rounded_panel(rect, self.config.theme_color("surface_alt"), 224, radius,
                                         border_color=self.config.theme_color("primary"), border_width=1)
                self._screen.blit(bg, rect.topleft)
                text_color = self.config.color("text")
            else:
                # 非选中行：半透明深色底，无边框（P44-D：默认无框，仅 hover 显示）
                bg = self._rounded_panel(
                    rect, self.config.color("idle_bg"), self.config.alpha("idle_bg"), radius)
                self._screen.blit(bg, rect.topleft)
                text_color = self.config.color("text") if available else self.config.color("disabled")
            # P46：选项文字去标记显示（选项是按钮，不做富文本排版）
            text = richtext.strip(str(opt.get("text", "")))
            img = self._cached_font_surface(self._option_font, text, True, text_color)
            self._draw_text_with_shadow(text, self._option_font, text_color,
                                        (rect.centerx - img.get_width() // 2,
                                         rect.y + (rect.height - img.get_height()) // 2))
            self._choice_rects.append((rect, i, available))
        # ⑤ 画完新选项组后启动锁：起始延迟 30ms（保证跨帧后才生效）+ 锁长 250ms
        if self._choice_is_new and self._choice_lock_t0 is None:
            self._choice_lock_t0 = self._now_ms() + 30  # t0 = 锁开始生效时间
        self._choice_is_new = False
