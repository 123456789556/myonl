"""MYONL 渲染层 · 立绘层（renderer.py 模块化拆分）。

SpriteMixin 的方法原样迁自 engine/renderer.py：方法体与签名不变，
经 self 访问实例状态（__init__ 中初始化）与其他 Mixin 方法；
常量与纯函数统一来自 render_utils（engine.renderer 再导出，命名空间不变）。
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pygame
from .render_utils import (
    SPRITE_MARGIN,
    ANIM_FPS,
    SPRITE_ANIM_DEFAULTS,
    LAYER_ORDER,
)


class SpriteMixin:
    """立绘层方法集（经多继承组合进 Renderer，见 engine/renderer.py）。"""

    _ui_scale: float  # T10 视觉比例（720p 基准；由 Renderer.__init__ 注入）

    # 宿主（Renderer.__init__）注入的实例属性 / 其他 Mixin 方法——仅静态检查声明。
    if TYPE_CHECKING:  # pragma: no cover
        size: Any
        timeline: Any
        _screen: pygame.Surface
        _layer_cache: dict
        _sprite_anim: dict
        _sequence_index: Any
        _voice_busy: Any
        _voice_length: Any
        _voice_t0: Any
        _dialog_top: Any
        _load_image: Any
        _load_image_path: Any
        _load_window: Any
        _now_ms: Any

    def _layer_composite(self, char, layers: dict):
        """P30-C-d：把 images/layers/角色ID/部位_素材.png 按固定顺序合成一张立绘。

        缺 `部位_素材` 先回退 `部位_默认`，仍缺则跳过该部位；一层都拼不出返回 None
        （调用方回退整张 `角色ID_表情.png`）。合成结果按 (角色, 部位清单) 缓存，逐帧不重拼。
        """
        key = (char, tuple(sorted(layers.items())))
        cached = self._layer_cache.get(key)
        if cached is not None:
            return cached
        ordered = list(LAYER_ORDER) + [p for p in layers if p not in LAYER_ORDER]
        parts = []
        for part in ordered:
            if part not in layers:
                continue
            img = self._load_image(f"layers/{char}/{part}_{layers[part]}")
            if img is None:
                img = self._load_image(f"layers/{char}/{part}_默认")
            if img is not None:
                parts.append(img)
        if not parts:
            return None
        canvas = pygame.Surface(parts[0].get_size(), pygame.SRCALPHA)
        for img in parts:
            canvas.blit(img, (0, 0))
        if len(self._layer_cache) >= 64:   # 表情/服装组合有限，超量整体丢弃即可
            self._layer_cache.clear()
        self._layer_cache[key] = canvas
        return canvas

    def play_anim(self, char, param, from_value, to_value, secs, easing="linear") -> None:
        """P30-C-c：给某个立绘参数挂一条补间轨（x / y / alpha / scale）。

        - `from_value` 为 None 时从"当前显示值"起步（DSL 的 `参数=目标` 写法）
        - `from_value` 显式给出时先把显示值放到起点（DSL 的 `参数=起始~结束` 写法）
        - `secs=0` 即直达：时长为 0 的轨当帧就取到目标值
        显示值留在 `_sprite_anim`（纯展示层，不进 GameState / 存档）；`@hide` 时随角色清掉。
        """
        values = self._sprite_anim.setdefault(char, {})
        start = float(values.get(param, SPRITE_ANIM_DEFAULTS[param])) \
            if from_value is None else float(from_value)
        end = float(to_value)
        values[param] = start
        self.timeline.play(f"anim:{char}:{param}", 0.0 if secs is None else float(secs) * 1000,
                           lambda t: start + (end - start) * t, t0=self._now_ms(),
                           easing=easing, meta={"char": char, "param": param})

    def _update_sprite_anim(self, now: int) -> None:
        """立绘补间推进：把各条 anim 轨本帧的值写进显示值，播完收轨（值留在原地）。"""
        for name in self.timeline.names():
            if not name.startswith("anim:"):
                continue
            track = self.timeline.track(name)
            value = self.timeline.value(name)
            if value is not None:
                self._sprite_anim.setdefault(track.meta["char"], {})[track.meta["param"]] = value
            if track.done(now):
                self.timeline.cancel(name)

    def _clear_sprite_anim(self, char) -> None:
        """清掉某角色的补间显示值（角色退场/重出场时不继承旧偏移）。"""
        self._sprite_anim.pop(char, None)
        for name in self.timeline.names():
            track = self.timeline.track(name)
            if name.startswith("anim:") and track.meta.get("char") == char:
                self.timeline.cancel(name)

    def _sprite_image(self, sp: dict, speaking):
        """立绘图：优先动画帧组（说话时切"说话"帧组，缺失则保持当前动画），都没有回退静态立绘。

        唇形细化：说话且有语音播放时，说话帧组按「语音已播时长/总时长」循环；
        无语音时保持原共享动画时钟（Timeline 的 sprite 时钟）。
        P30-C-d：写了 `部位:素材` 时走分层合成图（缺部位用 `_默认` 兜底，全缺回退整张）。
        """
        char, expr = sp.get("char"), sp.get("expr")
        if sp.get("layers"):
            composed = self._layer_composite(char, sp["layers"])
            if composed is not None:
                return composed
        anim = sp.get("anim") or "呼吸"
        is_speaking = (speaking is not None and char == speaking
                       and self._sequence_index("anims", f"{char}_{expr}_说话"))
        if is_speaking:
            anim = "说话"
        frames = self._sequence_index("anims", f"{char}_{expr}_{anim}")
        if frames:
            if is_speaking and self._voice_busy() and self._voice_length > 0:
                # 唇形随语音循环：progress = 已播时长 / 总时长
                elapsed = (self._now_ms() - self._voice_t0) / 1000.0
                progress = max(0.0, min(1.0, elapsed / self._voice_length))
                idx = int(progress * ANIM_FPS * 4) % len(frames)
            else:
                # P30-C-a：无语音时走 Timeline 的 sprite 时钟（首次取用时起算，全立绘共享）
                elapsed = self.timeline.elapsed("sprite", self._now_ms())
                idx = int(elapsed / 1000.0 * ANIM_FPS) % len(frames)
            self._load_window(frames, idx)
            img = self._load_image_path(frames[idx])
            if img is not None:
                return img
        return self._load_image(f"{char}_{expr}")  # 回退静态立绘（缺动画帧不崩）

    def _draw_sprites(self, sprites, speaking=None, target=None) -> None:
        target = target if target is not None else self._screen
        w, _h = self.size
        area_bottom = self._dialog_top()
        n = len(sprites)
        # P30-C-c：不在场的角色不保留补间偏移（@hide 由 state 驱动，这里顺手回收）
        if self._sprite_anim:
            live = {sp.get("char") for sp in sprites}
            for gone in [c for c in self._sprite_anim if c not in live]:
                self._clear_sprite_anim(gone)
        if n == 0:
            return
        # P30-C-b：按 z 升序绘制（大者在上）；z 相同时稳定排序＝保持 state.sprites 原顺序，
        # 旧剧本（无 z）绘制顺序与旧版完全一致
        for i in sorted(range(n), key=lambda k: sprites[k].get("z", 0)):
            sp = sprites[i]
            char, expr = sp.get("char"), sp.get("expr")
            if char is None or expr is None:
                continue
            name = f"{char}_{expr}"
            img = self._sprite_image(sp, speaking)
            if img is None:
                # ④ 占位改为渐变剪影（深色渐变 + 模糊人形轮廓，画面上不写文件名）
                base = (min(int(w / n), 280), 420)
                rect = self._sprite_rect(base, sp, i, n)
                self._draw_sprite_placeholder(rect, target)
                continue
            rect = self._sprite_rect(img.get_size(), sp, i, n)
            disp = self._sprite_anim.get(char)
            if disp:
                rect = self._apply_sprite_anim(rect, disp)
            scaled = (pygame.transform.smoothscale(img, rect.size)
                      if img.get_size() != rect.size else img)
            if disp and disp.get("alpha", 1.0) < 1.0:
                scaled = scaled.copy()   # 缓存里的 Surface 不能就地改 alpha
                scaled.set_alpha(int(255 * max(0.0, min(1.0, disp["alpha"]))))
            target.blit(scaled, rect)
            # ⑬ 立绘底部 8% 高度渐隐（仅立绘层，不动 CG/背景）
            fade_h = max(4, int(rect.height * 0.08))
            fade = pygame.Surface((rect.width, fade_h), pygame.SRCALPHA)
            for j in range(fade_h):
                alpha = int(255 * (1 - j / fade_h))
                pygame.draw.line(fade, (0, 0, 0, alpha), (0, j), (rect.width, j))
            target.blit(fade, (rect.x, rect.bottom - fade_h))

    def _apply_sprite_anim(self, rect, disp):
        """把补间显示值叠加到立绘 rect：scale 以底部中心为锚，再平移 x/y。"""
        scale = float(disp.get("scale", 1.0))
        if scale != 1.0:
            center_x, bottom = rect.centerx, rect.bottom
            rect = pygame.Rect(0, 0, max(1, int(rect.width * scale)),
                               max(1, int(rect.height * scale)))
            rect.centerx, rect.bottom = center_x, bottom
        dx, dy = int(disp.get("x", 0.0)), int(disp.get("y", 0.0))
        if dx or dy:
            rect = rect.move(dx, dy)
        return rect

    def _draw_sprite_placeholder(self, rect, target) -> None:
        """④ 立绘占位：深色纵向渐变 + 居中模糊人形轮廓剪影。"""
        # 深色纵向渐变
        for y in range(rect.height):
            t = y / max(1, rect.height - 1)
            c = (int(40 + 20 * t), int(35 + 15 * t), int(60 + 20 * t))
            pygame.draw.line(target, c, (rect.x, rect.y + y), (rect.right, rect.y + y))
        # 居中模糊人形剪影（三个圆角矩形：头/躯干/腿）
        cx = rect.centerx
        body_top = rect.y + int(rect.height * 0.18)
        head = pygame.Rect(cx - int(rect.width * 0.12), rect.y + int(rect.height * 0.05),
                           int(rect.width * 0.24), int(rect.height * 0.15))
        body = pygame.Rect(cx - int(rect.width * 0.2), body_top,
                           int(rect.width * 0.4), int(rect.height * 0.45))
        legs = pygame.Rect(cx - int(rect.width * 0.17), body.bottom,
                           int(rect.width * 0.34), rect.bottom - body.bottom - 2)
        silhouette = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
        pygame.draw.ellipse(silhouette, (255, 255, 255, 28), head.inflate(0, -rect.height * 0.02))
        pygame.draw.rect(silhouette, (255, 255, 255, 28), body, border_radius=max(2, rect.width // 12))
        pygame.draw.rect(silhouette, (255, 255, 255, 28), legs, border_radius=max(2, rect.width // 16))
        target.blit(silhouette, rect.topleft)

    def _sprite_rect(self, size, sp, index: int, count: int):
        """立绘目标矩形。

        - 未写 pos/scale：旧行为（等宽均分槽位，从右往左，单立绘即居中）
        - 写了 pos/scale：按原图尺寸 × scale，超屏等比收进；左/右贴边留 SPRITE_MARGIN
        """
        w, _h = self.size
        area_bottom = self._dialog_top()
        sw, sh = size
        pos = sp.get("pos")
        if pos is None and "scale" not in sp:
            slot_w = w / count
            center_x = int(w - (index + 0.5) * slot_w)
            k = min(int(slot_w) / sw if sw else 1.0, area_bottom / sh if sh else 1.0)
            tw, th = max(1, int(sw * k)), max(1, int(sh * k))
            return pygame.Rect(center_x - tw // 2, area_bottom - th, tw, th)
        scale = float(sp.get("scale") or 1.0)
        tw, th = max(1, int(sw * scale)), max(1, int(sh * scale))
        margin = int(round(SPRITE_MARGIN * self._ui_scale))  # T10 视觉比例
        max_w, max_h = w - 2 * margin, area_bottom
        k = min(1.0, max_w / tw if tw else 1.0, max_h / th if th else 1.0)
        tw, th = max(1, int(tw * k)), max(1, int(th * k))
        if pos == "左":
            x = margin
        elif pos == "右":
            x = w - margin - tw
        else:  # 中（缺省）
            x = (w - tw) // 2
        rect = pygame.Rect(x, area_bottom - th, tw, th)
        # 场景视图（可视化）：x/y 是相对默认位置的像素偏移
        ox, oy = int(sp.get("x") or 0), int(sp.get("y") or 0)
        if ox or oy:
            rect = rect.move(ox, oy)
        return rect

    # ==================== 内部：CG / 镜头 / 转场绘制 ====================
