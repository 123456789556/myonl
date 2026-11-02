"""P30-S3：引擎配置前哨——只读主题/键位（config.json），与可写偏好 settings.json 分工。

职责边界：
- `config.json`（游戏素材根目录下，可选）：窗口标题、字号、色板、遮罩 alpha、键位表。
  由美术/项目配置，引擎只读，玩家不可写。
- `settings.json`（玩家目录，已有）：音量、速度、窗口大小等玩家偏好，可写可持久化。
- 本模块只提供默认值 + 覆盖合并 + 取值接口，不 import pygame（键位用 "K_UP" 这类字符串）。

使用：
    cfg = config.load(assets_root)
    cfg.window_title        # "MYONL" 或 config.json 覆盖值
    cfg.font("body")        # 28
    cfg.color("selected_bg")# (40, 54, 96)
    cfg.alpha("menu")       # 235
    config.keymap(cfg)      # {pygame 键码: "up"/"confirm"/...}
"""

from __future__ import annotations

import copy
import json
import os
import sys

CONFIG_FILE = "config.json"

# 默认值：与 P29 前的硬编码常量一一对应，保证不写 config.json 时行为零变化
DEFAULTS = {
    "window_title": "MYONL",
    "title_music": "",     # P33：标题画面 BGM（音乐名，空 = 不播）；进标题淡入、离开淡出
    # T10：逻辑画布尺寸（默认 1280×720，可配 1920×1080 等）；
    # 所有 UI 坐标按此尺寸排版，物理窗口由 settings.json window_size 控制（等比 letterbox）。
    "canvas_size": [1280, 720],
    "font": {
        "body": 28,    # 正文字号（原 FONT_SIZE）
        "title": 72,   # 标题画面引擎名字号（原 TITLE_FONT_SIZE）
        "mid": 40,     # 中号字
        "small": 22,   # 小号字
        # P37-T6 字体层级扩展：章节标题 / 选项 / 强调
        "heading": 56,
        "option": 26,
        "em": 28,
    },
    # P37-T6 字体排版：行高（相对字号倍数），渲染层消费，老项目走默认合理值
    "line_height": {
        "body": 1.6,
        "heading": 1.3,
        "option": 1.4,
    },
    # 演出节奏（开发者可配；单位：秒 / 毫秒）。默认值参考现代 galgame 的常见手感：
    # 场景切换短淡入、转场 0.4s、大幕切换更慢、CG 入场略快。
    "pacing": {
        "scene_fade": 0.35,      # @bg 切背景的淡入时长（商业手感：介于 0.3 快切与 0.4 舒缓之间）
        "dissolve": 0.45,        # dissolve/wipe/slide 转场默认时长
        "chapter_fade": 0.9,     # 章节/大幕切换（淡出+黑场+淡入的总时长）
        "scene_gap": 0.25,       # 幕间黑场停顿
        "cg_fade": 0.3,          # CG 入场淡入
        "title_fade": 1.1,       # 标题画面淡入
        "auto_advance_ms": 900,  # AUTO 自动播放推进间隔（毫秒；商业作品常见 600~1200）
    },
    "colors": {
        "dialog_fg": [255, 255, 255],
        "dialog_fg_dim": [150, 150, 150],
        "text": [255, 255, 255],
        "disabled": [136, 136, 136],
        "highlight": [255, 255, 200],
        "selected_bg": [40, 54, 96],
        "selected_fg": [255, 255, 255],
        "selected_border": [140, 180, 255],
        "idle_bg": [0, 0, 0],
        "missing": [51, 51, 51],
    },
    "alphas": {
        "selected_bg": 235,
        "idle_bg": 180,
        "menu": 235,
        "slots": 240,
        "settings": 240,
        "backlog": 200,
        "gallery": 240,
        "gallery_detail": 245,
    },
    # P35 可配置化：语义主题色 + UI 布局
    # P51 升级：UI 段现在提供引擎级默认（像素化/偏圆矩形/圆角与几何），
    # 老项目不写 ui 段即继承新默认；如需旧观感可在 config.json 显式覆盖。
    "theme": {},
    "ui": {
        # C2：选项组与对话框的间距（720p 基准，随 ui_scale 放大；0=贴着对话框）
        # 2026-11-02：补齐编辑器 UI 设计区需要的完整默认值（渲染层原本写死在 _ui_int 里，
        # 提到 DEFAULTS 后 GET /api/ui-design 不会再对老工程返回 null）。
        "choices": {"dialog_gap": 40, "width": 420, "row_height": 52, "radius": 8},
        "quickbar": {"button_width": 64, "button_height": 26, "gap": 8, "margin_x": 24,
                     "margin_y": 10, "alpha": 185, "radius": 15,
                     "position": "bottom", "align": "right"},
        "settings": {"row_width": 620, "row_height": 72, "nav_width": 180, "top": 210},
        # C3：标题排版——左列布局的作品名 x（y 用 title_text_y / ui.title.logo_y）
        "title": {"left_x": 96},
        # P52：游戏内菜单几何（row_width/row_height/top/radius；缺省=原硬编码 380/54/240/12）
        "menu": {"row_width": 380, "row_height": 54, "top": 240, "radius": 12},
        # P51：UI 像素化（Python 程序化绘制，不用 AI 生图）
        # - pixelated: 是否开启像素块渲染（低分辨率绘制 + NEAREST 放大）
        # - pixel_scale: 像素块大小（逻辑画布 1280×720 下 4px 一格）
        # - corner_radius: 默认圆角（偏圆矩形默认 10；0=直角贴边；更大值=圆角矩形）
        # 位置/大小由 dialogue.default 的 offset_x/offset_y/panel_width 控制，
        # 玩家可在 settings.json 的 ui_geometry 里覆盖（见 renderer 初始化合并）。
        "pixelated": True,
        "pixel_scale": 4,
        "corner_radius": 10,
    },
    # P44-D SKIP 规则：默认开启；mode="viewed" 仅已浏览内容可跳（避免跳过未读剧情）
    "skip": {"enabled": True, "mode": "viewed"},
    # P0-1 对话框 DSL：几何/底色/边宽（主题侧，游戏开发者可改）；
    # 缺省值 = 原硬编码常量，不写 config.json 时行为零变化
    "dialogue": {
        "default": {          # 主对话框（角色台词 / 旁白）
            "height": 180,    # 对话框高度（原 DIALOG_HEIGHT）
            "margin": 24,     # 左右内边距
            "border_width": 2,  # 白边宽
            "bg_alpha": 150,  # 半透明底 alpha（P51：像素化 UI 默认偏圆矩形）
            "radius": 10,    # 圆角（P51：默认 10=偏圆矩形；0=直角贴边；更大值=圆角矩形）
            # P51：几何可调——玩家可改位置/大小（默认 0=引擎默认贴边几何）
            "offset_x": 0,    # 横向偏移（像素，0=默认）
            "offset_y": 0,    # 纵向偏移（像素，0=默认）
            "panel_width": 0, # 面板宽（0=默认全宽），>0 时自定义宽度
            "name_y": 12,     # 角色名距对话框顶
            "name_gap": 8,    # 角色名与正文间距
            "narration_y": 16,  # 旁白正文距顶
            # P44-D 界面轻量化：旁白与角色台词共用同一面板（统一尺寸/居中排版）、
            # 角色名不画框、打字机完成后右下角显示推进小三角（均可由 config.json 覆盖）
            "no_panel_narration": False,
            "name_chip": False,
            "next_arrow": True,
            # P46 正文对齐：left（默认，左对齐顶格）/ center / right；旁白与台词同规范
            "align": "left",
            # 字幕隐藏条（对话框顶部的悬停机关）：
            # - capture_height: 捕获区高度（鼠标悬停判定区域，默认 24px）
            # - line_height: 显现的顶边细线高度（默认 2px）
            # - alpha_normal: 正常态显现时线条 α（默认 160，淡而克制）
            # - alpha_hidden: 隐藏态线条 α（默认 200，略亮提示"再点恢复"）
            # - symbol: 顶边中央符号（默认 "."）
            # - symbol_size: 符号字号（默认 10）
            # - full_width: 是否拉通整屏宽（默认 true）
            "curtain": {
                "capture_height": 24,
                "line_height": 2,
                "alpha_normal": 160,
                "alpha_hidden": 200,
                "symbol": ".",
                "symbol_size": 10,
                "full_width": True,
            },
        },
        "nvl": {              # NVL 旁白：整屏文字，无底部条
            "bg_alpha": 90,   # 全屏半透明底
            "margin": 80,     # 左右留白
            "top": 200,       # 文字起始 y（距顶）
            "bottom": 60,     # 底部留白
            "line_gap": 8,    # 行距附加
            "align": "left",  # P46：NVL 与主对话框共用对齐语义
        },
    },
    "keymap": {
        "up": ["K_UP"],
        "down": ["K_DOWN"],
        "left": ["K_LEFT"],
        "right": ["K_RIGHT"],
        "confirm": ["K_RETURN", "K_KP_ENTER", "K_SPACE"],
        "back": ["K_ESCAPE"],
        "slot1": ["K_1"],
        "slot2": ["K_2"],
        "slot3": ["K_3"],
        "slot4": ["K_4"],
        "slot5": ["K_5"],
        "slot6": ["K_6"],
        "slot7": ["K_7"],
        "slot8": ["K_8"],
        "slot9": ["K_9"],
        "slot10": ["K_0"],
        "quicksave": ["K_F5"],   # 快速存档：固定写 saves/slot_quick.json
    },
}


def _deep_merge(base: dict, override: dict, *, _path: str = "") -> dict:
    """覆盖合并：override 的叶子覆盖 base，缺的键保留默认。

    类型防护：当 base 某键为 dict 而 override 为非 dict 时，保留 base 默认值并打印警告，
    防止 config.json 里写错类型（如 "font": "large"）导致后续 .get() 崩溃。
    """
    out = copy.deepcopy(base)
    for key, val in (override or {}).items():
        loc = f"{_path}.{key}" if _path else key
        if isinstance(out.get(key), dict) and not isinstance(val, dict):
            print(f'[配置警告] 键 "{loc}" 应为对象，收到 {type(val).__name__}，已保留默认值',
                  file=sys.stderr)
            continue
        if isinstance(val, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], val, _path=loc)
        else:
            out[key] = copy.deepcopy(val)
    return out


def _as_bool(value, default: bool = True) -> bool:
    """配置布尔：兼容手写/旧编辑器写进来的 "true"/"false" 字符串。"""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        s = value.strip().lower()
        if s in ("true", "1", "yes", "on"):
            return True
        if s in ("false", "0", "no", "off"):
            return False
    return default


def _as_color(value, default: tuple) -> tuple:
    """把 [r,g,b] / [r,g,b,a] 转成元组；非法值回落默认（不崩）。"""
    if isinstance(value, (list, tuple)) and len(value) in (3, 4):
        try:
            return tuple(int(v) for v in value)
        except (TypeError, ValueError):
            return default
    return default


# T10 视觉比例：这些 dialogue 键是「像素几何」，按 UI 比例缩放；
# alpha / 字符串 / 布尔（bg_alpha、align、next_arrow…）不缩放。
_DIALOGUE_SCALE_KEYS = frozenset({
    "height", "margin", "border_width", "radius", "offset_x", "offset_y",
    "panel_width", "name_y", "name_gap", "narration_y", "top", "bottom",
    "line_gap", "capture_height", "line_height", "symbol_size",
})


def _scale_dialogue_geometry(node: dict, scale: float) -> dict:
    """按 UI 比例缩放对话框几何（递归处理 curtain 等嵌套段）；scale=1 原样返回。"""
    if scale == 1.0:
        return node
    out = {}
    for key, val in node.items():
        if key in _DIALOGUE_SCALE_KEYS and isinstance(val, (int, float)) and not isinstance(val, bool):
            out[key] = int(round(val * scale))
        elif isinstance(val, dict):
            out[key] = _scale_dialogue_geometry(val, scale)
        else:
            out[key] = val
    return out


# P35 语义主题色 fallback（不进 DEFAULTS，保持空 dict 契约；老项目走合理深色兜底）
# 放在模块级供编辑器 UI 设计区读取「未覆盖时的实际颜色」。
THEME_FALLBACK = {
    "primary": (104, 156, 255),
    "primary_soft": (52, 76, 128),
    "accent": (255, 205, 130),
    "surface": (20, 24, 36),
    "surface_alt": (32, 38, 56),
    "text": (240, 244, 255),
    "text_dim": (150, 160, 184),
    "border": (64, 72, 96),
    "danger": (243, 139, 168),
    "success": (166, 227, 161),
    "shadow": (0, 0, 0),
}


class Config:
    """只读配置视图：默认值 + config.json 覆盖。"""

    def __init__(self, overrides: dict | None = None):
        self.data = _deep_merge(DEFAULTS, overrides or {})
        self.warnings: list[str] = []

    # ---- 常用取值 ----
    @property
    def window_title(self) -> str:
        title = self.data.get("window_title")
        return title if isinstance(title, str) and title else DEFAULTS["window_title"]

    def font(self, name: str = "body") -> int:
        val = (self.data.get("font") or {}).get(name, DEFAULTS["font"].get(name, 28))
        try:
            size = int(val)
        except (TypeError, ValueError):
            size = DEFAULTS["font"].get(name, 28)
        # T10 视觉比例：字号按 720p 基准等比放大（1080p → ×1.5），保证对话框占比不缩水
        return max(8, int(round(size * self.ui_scale())))

    def color(self, name: str) -> tuple:
        raw = (self.data.get("colors") or {}).get(name)
        default = DEFAULTS["colors"].get(name, (255, 255, 255))
        return _as_color(raw, tuple(default))

    def alpha(self, name: str) -> int:
        val = (self.data.get("alphas") or {}).get(name, DEFAULTS["alphas"].get(name, 255))
        try:
            return max(0, min(255, int(val)))
        except (TypeError, ValueError):
            return DEFAULTS["alphas"].get(name, 255)

    # P37-T6 主题色板 fallback（模块级 THEME_FALLBACK 的类内别名）
    _THEME_FALLBACK = THEME_FALLBACK

    def theme_color(self, name: str) -> tuple:
        """P35 语义主题色（primary/accent/surface/text/border/danger/success…）。
        config.json 未定义时走内置深色 fallback（不返回纯白，避免老项目意外白屏）。
        """
        raw = (self.data.get("theme") or {}).get(name)
        if raw is not None:
            default = self._THEME_FALLBACK.get(name, (255, 255, 255))
            return _as_color(raw, default)
        return self._THEME_FALLBACK.get(name, (255, 255, 255))

    def line_height(self, name: str = "body") -> float:
        """P37-T6 行高（相对字号倍数）；非法回落 1.5。"""
        val = (self.data.get("line_height") or {}).get(
            name, DEFAULTS["line_height"].get(name, 1.5))
        try:
            lh = float(val)
            return lh if 0.8 <= lh <= 4.0 else 1.5
        except (TypeError, ValueError):
            return 1.5

    def ui_section(self, name: str) -> dict:
        """P35 UI 布局段（quickbar/title/choices/settings）：默认值 + config.json 覆盖。"""
        base = copy.deepcopy(DEFAULTS.get("ui", {}).get(name) or {})
        override = (self.data.get("ui") or {}).get(name)
        if isinstance(override, dict):
            base = _deep_merge(base, override)
        return base

    def ui_value(self, section: str, key: str, default=None):
        """取单个 UI 布局值；非法类型不在这里处理，由渲染层做数值兜底。"""
        return self.ui_section(section).get(key, default)

    # ---- P51：UI 像素化全局开关（ui 段顶层键，非按段布局）----

    def ui_global(self, key: str, default=None):
        """取 ui 段顶层键（pixelated/pixel_scale/corner_radius）；缺省回落默认。"""
        raw = (self.data.get("ui") or {}).get(key)
        if raw is None:
            return (DEFAULTS.get("ui") or {}).get(key, default)
        return raw

    def pixelated(self) -> bool:
        """UI 像素化开关（默认 True，Python 程序化像素块渲染）。"""
        return _as_bool(self.ui_global("pixelated", True), True)

    def pixel_scale(self) -> int:
        """像素块大小（逻辑画布下每格像素数）；非法回落 4。"""
        try:
            return max(1, min(16, int(self.ui_global("pixel_scale", 4))))
        except (TypeError, ValueError):
            return 4

    def corner_radius(self) -> int:
        """UI 默认圆角（偏圆矩形）；非法回落 10。"""
        try:
            return max(0, min(80, int(self.ui_global("corner_radius", 10))))
        except (TypeError, ValueError):
            return 10

    def ui_scale(self) -> float:
        """T10 视觉比例：UI 尺寸相对 720p 的倍数（默认 = 画布高 / 720，1080p → 1.5）。

        config.json 写 "ui_scale": 数字 可显式指定；写 1.0 = 关掉等比缩放、保持纯像素观感
        （等价于「只出 1080 专用预设」那条路：字号与几何自己按像素写死）。
        取值范围 0.5~4.0，防手滑写成 100。
        """
        raw = self.data.get("ui_scale")
        if isinstance(raw, (int, float)) and not isinstance(raw, bool):
            try:
                return max(0.5, min(4.0, float(raw)))
            except (TypeError, ValueError):
                pass
        return max(0.5, min(4.0, self.canvas_size()[1] / 720.0))

    def canvas_size(self) -> tuple:
        """T10：逻辑画布尺寸（宽, 高）；非法值回落 1280×720。"""
        raw = self.data.get("canvas_size")
        default = tuple(DEFAULTS["canvas_size"])
        if isinstance(raw, (list, tuple)) and len(raw) == 2:
            try:
                w, h = int(raw[0]), int(raw[1])
                if 640 <= w <= 7680 and 360 <= h <= 4320:
                    return (w, h)
            except (TypeError, ValueError):
                pass
        return default

    # ---- P51：玩家覆盖层（settings.json ui_geometry）----

    def apply_player_ui(self, ui_geometry: dict) -> None:
        """把玩家存档里的 UI 几何覆盖并入配置视图（引擎默认 ← config.json ← 玩家）。

        ui_geometry 支持键：radius / offset_x / offset_y / panel_width / height，
        与 dialogue.default 键名一致，仅做类型安全的 int 合并；未知键忽略。
        """
        if not isinstance(ui_geometry, dict):
            return
        dlg = self.data.setdefault("dialogue", {}).setdefault("default", {})
        for key in ("radius", "offset_x", "offset_y", "panel_width", "height"):
            val = ui_geometry.get(key)
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                dlg[key] = int(val)

    def to_dict(self) -> dict:
        """导出完整生效配置（默认值 + 覆盖），供编辑器/打包工具展示与改写。"""
        return copy.deepcopy(self.data)

    def dialogue(self, name: str = "default") -> dict:
        """对话框布局几何（P0-1）：config.json dialogue.<name> 覆盖默认，缺键/非法回落。"""
        default_base = DEFAULTS.get("dialogue", {}).get("default") or {}
        base = DEFAULTS.get("dialogue", {}).get(name)
        if not isinstance(base, dict) or not base:
            base = default_base  # 未知布局名回落默认布局
        override = (self.data.get("dialogue") or {}).get(name) or {}
        out = dict(base)
        for key, val in override.items():
            # P46：覆盖值类型须与默认值类型一致——字符串键（如 align）接受字符串，
            # 布尔键接受布尔，数字键接受数字；类型不符跳过保留默认（不崩）
            base_val = out.get(key)
            if isinstance(base_val, bool):
                if isinstance(val, bool):
                    out[key] = val
            elif isinstance(base_val, str):
                if isinstance(val, str):
                    out[key] = val
            elif isinstance(base_val, dict) and isinstance(val, dict):
                # 嵌套字典（如 curtain）深度合并
                out[key] = _deep_merge(base_val, val)
            elif isinstance(val, (int, float)) and not isinstance(val, bool):
                out[key] = int(val)
        return _scale_dialogue_geometry(out, self.ui_scale())

    def pacing(self) -> dict:
        """演出节奏配置（开发者层）：默认值 ← config.json 的 pacing 段，只接受数字覆盖。"""
        base = copy.deepcopy(DEFAULTS.get("pacing") or {})
        override = self.data.get("pacing") or {}
        if isinstance(override, dict):
            for key, val in override.items():
                if key in base and isinstance(val, (int, float)) and not isinstance(val, bool):
                    base[key] = float(val)
        return base

    def pacing_value(self, name: str, default: float) -> float:
        """取单个节奏值；非法/缺失回落 default。"""
        try:
            return float(self.pacing().get(name, default))
        except (TypeError, ValueError):
            return float(default)

    def keymap_table(self) -> dict:
        table = self.data.get("keymap")
        return table if isinstance(table, dict) and table else DEFAULTS["keymap"]


def load(assets_root: str = ".") -> Config:
    """读 assets_root/config.json；文件缺失或损坏 → 全默认（带中文警告，不崩）。"""
    path = os.path.join(str(assets_root), CONFIG_FILE)
    if not os.path.isfile(path):
        return Config()
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            raw = json.load(f)
    except (OSError, ValueError) as e:
        cfg = Config()
        cfg.warnings.append(f"配置文件 {CONFIG_FILE} 读取失败（{e}），已使用默认值")
        return cfg
    if not isinstance(raw, dict):
        cfg = Config()
        cfg.warnings.append(f"配置文件 {CONFIG_FILE} 顶层不是对象，已使用默认值")
        return cfg
    return Config(raw)


def keymap(cfg: Config, settings=None) -> dict:
    """{pygame 键码: 统一动作名}；键名写错（如 "K_FOO"）跳过并在 warnings 记录。

    settings 里 key_up/key_down/... 是玩家在设置页改的键（pygame.key.name 的小写名，
    空串 = 沿用项目 config 默认），覆盖对应动作的全部默认键。
    """
    import pygame

    result: dict = {}
    for action, names in cfg.keymap_table().items():
        if isinstance(names, str):
            names = [names]
        if not isinstance(names, (list, tuple)):
            cfg.warnings.append(f"键位 {action} 的取值不是字符串或数组，已忽略")
            continue
        for name in names:
            code = getattr(pygame, name, None) if isinstance(name, str) else None
            if isinstance(code, int):
                result[code] = action
            else:
                cfg.warnings.append(f"键位 {action} 引用了不存在的键名 {name!r}，已忽略")
    # U10：确认键方案（空格/回车）在「没有自定义确认键」时过滤默认确认键；
    # 自定义 key_confirm 优先，避免两套设置互相打架。
    preset = str((settings or {}).get("confirm_key") or "both")
    custom_confirm = str((settings or {}).get("key_confirm") or "").strip()
    if not custom_confirm and preset in ("space", "enter"):
        allowed = {pygame.K_SPACE} if preset == "space" else {pygame.K_RETURN, pygame.K_KP_ENTER}
        result = {k: v for k, v in result.items()
                  if not (v == "confirm" and k not in allowed)}
    # U10：玩家键位覆盖（只覆盖玩家能改的 6 个动作，其余仍走项目配置）
    for action in ("up", "down", "left", "right", "confirm", "back"):
        raw = str((settings or {}).get("key_" + action) or "").strip()
        if not raw:
            continue
        # 先用 K_<NAME> 直查（f/w/up/space…），特殊键名再交给 pygame.key.key_code
        code = getattr(pygame, "K_" + raw.upper(), None)
        if not isinstance(code, int):
            import warnings

            try:
                with warnings.catch_warnings():   # 无头环境未 init 时会提示，不影响结果
                    warnings.simplefilter("ignore")
                    code = pygame.key.key_code(raw)
            except (ValueError, AttributeError):
                continue  # 非法键名（手改 settings.json）忽略，保留默认
        result = {k: v for k, v in result.items() if v != action}
        result[code] = action
    return result
