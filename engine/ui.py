"""MYONL 玩家侧 UI 状态机。

纯逻辑层：不 import pygame、不读写 GameState（无状态铁律延伸：菜单/光标/回看
都是展示层状态，绝不进 GameState，也绝不进存档）。
- 模式：title / playing / menu / slots / settings / backlog
- demo 每帧把统一键名喂给 handle()，handle() 返回业务动作 dict（demo 执行）或
  None（纯导航，UI 自己消化）；renderer 每帧从 view() 取数据画 UI 层
- 存档列表 / 设置通过 save.list_slots() / data.load_settings() 读取（均为标准库模块）
"""
from __future__ import annotations

import time

from . import data
from . import i18n
from . import save as save_api

# 全部模式（mode 属性校验用）
MODES = ("title", "playing", "menu", "slots", "settings", "backlog", "gallery")

# 标题画面菜单项（3.6）与游戏内菜单项（3.2），顺序即光标顺序
TITLE_ITEMS = ("开始新游戏", "继续", "读档", "设置", "画廊", "退出")
MENU_ITEMS = ("存档", "读档", "画廊", "回标题", "设置", "退出")

# 画廊页签
GALLERY_TABS = ("CG 鉴赏", "立绘鉴赏")
QUICKBAR_ITEMS = ("SAVE", "LOAD", "LOG", "AUTO", "SKIP", "CONFIG")  # P34-T1：游戏内快捷栏
GALLERY_COLS = 4          # 缩略图网格每行列数
GALLERY_ROWS = 3          # 网格行数（一屏 12 格）
GALLERY_SLIDE_MS = 5000   # P28 E3：画廊大图幻灯片每张停留时长（毫秒）

# 设置项定稿（3.4）：键名 / 显示名 / 下限 / 上限 / 步进 / 显示类别
# P30-S2-1：text_speed 显示类别 speed（档位慢/中/快），存储仍是数字；
# P30-S2-2：settings_hidden 可在 settings.json 显式隐藏任意项
SETTINGS_ITEMS = (
    {"key": "text_speed", "label": "打字速度", "min": 5, "max": 120, "step": 5, "kind": "speed",
     "group": "基础"},
    {"key": "bgm_volume", "label": "音乐音量", "min": 0.0, "max": 1.0, "step": 0.1, "kind": "volume",
     "group": "音频"},
    {"key": "sfx_volume", "label": "音效音量", "min": 0.0, "max": 1.0, "step": 0.1, "kind": "volume",
     "group": "音频"},
    {"key": "voice_enabled", "label": "配音", "min": 0, "max": 1, "step": 1, "kind": "switch",
     "group": "语音"},
    {"key": "voice_auto_advance", "label": "语音自动推进", "min": 0, "max": 1, "step": 1, "kind": "switch",
     "group": "语音"},
    # P37-M1：语言切换放末位——既有项光标位置不变（老存档/老测试零影响）
    # P49：语言归"语音"分组（截图④视觉：语言跟在语音自动推进下方）；基础页只留打字速度
    {"key": "lang", "label": "语言", "kind": "choice", "group": "语音",
     "options": ["zh-CN", "en-US"], "labels": ["中文", "English"]},
    # M1.5：追加在末尾、新组「高级」——不改变既有 基础/音频/语音 三页的项与顺序
    {"key": "display_mode", "label": "显示模式", "kind": "choice", "group": "高级",
     "options": ["window", "borderless", "fullscreen"],
     "labels": ["窗口", "无边框全屏", "全屏"]},
    {"key": "auto_speed", "label": "自动播放速度", "kind": "choice", "group": "高级",
     "options": ["slow", "normal", "fast"], "labels": ["慢", "中", "快"]},
    {"key": "muted", "label": "静音", "min": 0, "max": 1, "step": 1, "kind": "switch",
     "group": "高级"},
    {"key": "voice_volume", "label": "配音音量", "min": 0.0, "max": 1.0, "step": 0.1, "kind": "volume",
     "group": "高级"},
    {"key": "font_scale", "label": "字号", "kind": "choice", "group": "高级",
     "options": ["small", "medium", "large"], "labels": ["小", "中", "大"]},
    # U7/U9/U10：玩家侧可调交互（追加在末尾，不改变既有项顺序与光标位置）
    {"key": "dialog_alpha_scale", "label": "对话框透明度", "min": 0.3, "max": 1.0, "step": 0.1,
     "kind": "volume", "group": "高级"},
    {"key": "dialog_offset_y", "label": "对话框位置", "min": -80, "max": 80, "step": 10,
     "kind": "offset", "group": "高级"},
    {"key": "reduce_effects", "label": "减少动效", "min": 0, "max": 1, "step": 1, "kind": "switch",
     "group": "高级"},
    {"key": "confirm_key", "label": "确认键", "kind": "choice", "group": "高级",
     "options": ["both", "space", "enter"], "labels": ["空格/回车", "仅空格", "仅回车"]},
    # U10：完整键位自定义（回车进入改键，按新键绑定；Esc/Delete 恢复默认）
    {"key": "key_up", "label": "上", "kind": "key", "group": "键位"},
    {"key": "key_down", "label": "下", "kind": "key", "group": "键位"},
    {"key": "key_left", "label": "左", "kind": "key", "group": "键位"},
    {"key": "key_right", "label": "右", "kind": "key", "group": "键位"},
    {"key": "key_confirm", "label": "确认", "kind": "key", "group": "键位"},
    {"key": "key_back", "label": "返回", "kind": "key", "group": "键位"},
    # 界面：玩家侧显示项——追加在末尾，不改既有分组顺序与光标位置
    {"key": "quickbar_enabled", "label": "快捷栏", "min": 0, "max": 1, "step": 1,
     "kind": "switch", "group": "界面"},
    {"key": "pet_enabled", "label": "桌宠", "min": 0, "max": 1, "step": 1,
     "kind": "switch", "group": "界面"},
)

# P30-S2-1：打字速度三档实际取值（慢/中/快），循环调整，老数值按最近档显示
TEXT_SPEED_LEVELS = (20, 45, 90)

# M1.5：AUTO 推进速度倍率（叠在 config.pacing.auto_advance_ms 上；玩家可调）
AUTO_SPEED_FACTORS = {"slow": 1.6, "normal": 1.0, "fast": 0.6}

# M1.5-B：玩家字号档位倍率（叠在 config.font 上；行距用同一比例自动跟随）
FONT_SCALE_FACTORS = {"small": 0.85, "medium": 1.0, "large": 1.2}


def font_scale_factor(settings) -> float:
    """玩家选择的字号倍率；缺省/非法回落到 1.0（中档）。"""
    scale = str((settings or {}).get("font_scale") or "medium")
    return FONT_SCALE_FACTORS.get(scale, 1.0)


def auto_interval_ms(settings, base_ms: float = 900) -> int:
    """AUTO 推进间隔 = 开发者节奏（pacing.auto_advance_ms）× 玩家速度倍率。"""
    speed = str((settings or {}).get("auto_speed") or "normal")
    factor = AUTO_SPEED_FACTORS.get(speed, 1.0)
    try:
        base = float(base_ms)
    except (TypeError, ValueError):
        base = 900.0
    return max(150, int(base * factor))

BACKLOG_PAGE_SIZE = 20  # 回看一屏最多 20 条（3.5）


def next_value(key, current):
    """设置项取下一档：到顶回到底（循环）。demo 执行 settings_change 动作时使用。

    音量类浮点步进做一位小数取整，避免 0.7 + 0.1 = 0.79999... 的浮点噪声。
    P30-S2-1：打字速度按三档循环（20 → 45 → 90 → 20），不再逐 5 步进。
    """
    if key == "text_speed":
        try:
            cur = float(current)
        except (TypeError, ValueError):
            cur = TEXT_SPEED_LEVELS[0]
        idx = min(range(len(TEXT_SPEED_LEVELS)),
                  key=lambda i: abs(TEXT_SPEED_LEVELS[i] - cur))
        return TEXT_SPEED_LEVELS[(idx + 1) % len(TEXT_SPEED_LEVELS)]
    item = next((i for i in SETTINGS_ITEMS if i["key"] == key), None)
    if item is None:
        raise KeyError(f"未知设置项：{key!r}（可用：{[i['key'] for i in SETTINGS_ITEMS]}）")
    if item.get("kind") == "choice":
        opts = item.get("options") or []
        if not opts:
            return current
        try:
            idx = opts.index(current)
        except ValueError:
            idx = 0
        return opts[(idx + 1) % len(opts)]
    if item.get("kind") == "key":
        return current  # U10：键位项由改键流程处理，回车不循环
    lo, hi, step = float(item["min"]), float(item["max"]), float(item["step"])
    try:
        cur = float(current)
    except (TypeError, ValueError):
        cur = lo
    nxt = cur + step
    if nxt > hi + 1e-9:
        nxt = lo  # 循环：到顶回到底
    if step < 1:
        return round(nxt, 1)
    return int(nxt)


class UI:
    """玩家侧 UI 状态机。模式：title / playing / menu / slots / settings / backlog。"""

    def __init__(self, config=None):
        # 模式 title，光标 0，无菜单数据
        self._mode = "title"
        self._cursor = 0
        self._config = config              # P44：可选 Config（标题菜单 items 覆盖用，None=引擎默认）
        self._slots = None            # slots 模式的 11 行数据（quick + 1~10）
        self._slots_purpose = None    # "save" / "load"
        self._settings = None         # settings 模式的当前设置值
        self._history = []            # 回看数据源（demo 每帧注入 GameState.history）
        self._backlog_offset = 0      # 回看翻页偏移：0 = 最新一屏
        self.capturing = None         # U10：正在改键的设置键名（None=未在改键）
        self._return_mode = "title"   # slots / settings 的返回地（title 或 menu）
        self.auto_on = False          # P34-T1：快捷栏 AUTO 开关（自动播放）
        self.skip_on = False          # P34-T1：快捷栏 SKIP 开关（快进）
        # P44-D：skip 默认关闭；开发者可在 config.skip.enabled 或
        # config.ui.quickbar.skip_enabled（旧键）开启。
        # skip.mode: "viewed" 仅已浏览内容可跳 / "all" 全部内容可直接跳
        skip_cfg = (config.data.get("skip") or {}) if config is not None else {}
        qb_cfg = ((config.data.get("ui") or {}).get("quickbar") or {}) if config is not None else {}
        self.skip_allowed = bool(skip_cfg.get("enabled", False) or qb_cfg.get("skip_enabled", False))
        mode = str(skip_cfg.get("mode", "viewed")).strip().lower()
        self.skip_mode = mode if mode in ("viewed", "all") else "viewed"
        self._slot_entries = []       # save.list_slots() 原始结果缓存
        self._has_save = False        # 是否存在任何存档（标题"继续"灰置依据）
        self.settings_path: str | None = None  # demo 指到 assets_root/settings.json；None = cwd 默认
        # ---- 画廊（P13）：demo 每帧注入已解锁 CG 与已见立绘 ----
        self._gallery = []            # 已解锁 CG 名列表（state["gallery"]，进存档）
        self._seen_sprites = []       # 已见过立绘 "char_expr"（不进存档，会话级）
        self._gallery_tab = 0         # 0=CG 鉴赏 / 1=立绘鉴赏
        self._gallery_page = 0        # 网格翻页
        self._gallery_detail = None   # 大图鉴赏中的条目名（None=网格视图）
        # P28 E1/E3：固定格子清单（gallery_config.json，空=只显示已解锁项）+ 幻灯片状态
        self._gallery_cells = []      # [{"name": 格名, "images": [图名...]}]
        self._gallery_detail_index = 0  # 幻灯片当前张下标
        self._gallery_slide_t0 = None   # 幻灯片计时起点（毫秒）
        self._last_now_ms = 0           # 最近一次 view() 注入的时钟（handle 手动切换用）
        self._game_title = None       # ⑪ 作品名（refresh 时从 settings.json 读）
        self._script_title = None     # ⑪ 作品名第二级：剧本首行 # 注释（demo 注入）
        self._settings_tab = 0        # P49：设置分组页（0=基础 / 1=音频 / 2=语音，按 items 顺序）
        self.refresh()

    def set_config(self, config) -> None:
        """P51 配置热重载：替换配置视图并重算依赖它的开关（skip 策略 / 标题菜单）。

        demo 改完 config.json 后调用；不重建 UI 状态机，只换数据源。
        """
        self._config = config
        if config is not None:
            skip_cfg = config.data.get("skip") or {}
            qb_cfg = (config.data.get("ui") or {}).get("quickbar") or {}
            self.skip_allowed = bool(skip_cfg.get("enabled", False)
                                     or qb_cfg.get("skip_enabled", False))
            mode = str(skip_cfg.get("mode", "viewed")).strip().lower()
            self.skip_mode = mode if mode in ("viewed", "all") else "viewed"
        self.refresh()

    def title_items(self) -> tuple:
        """标题画面菜单项：config.ui.title.items 可覆盖（如标准模板去掉画廊），缺省 TITLE_ITEMS。

        P44：模板/开发者可在 config.json 里写 ui.title.items 自定义主菜单，
        动作按 label 匹配（开始新游戏/继续/读档/设置/画廊/退出），顺序即光标顺序。
        """
        items = None
        if self._config is not None:
            items = self._config.ui_value("title", "items")
        if isinstance(items, (list, tuple)) and items:
            return tuple(str(i) for i in items)
        return TITLE_ITEMS

    def _visible_settings(self) -> list:
        """P30-S2-2：设置页可见项——settings.json 的 settings_hidden 显式隐藏，默认全显示。

        隐藏项不进 view["items"]，renderer 不画、光标不落位，但设置值本身仍保留。
        """
        hidden = set((self._settings or {}).get("settings_hidden", []) or [])
        return [it for it in SETTINGS_ITEMS if it["key"] not in hidden]

    # ==================== 对外属性 ====================

    @property
    def mode(self) -> str:
        return self._mode

    @mode.setter
    def mode(self, value: str) -> None:
        """demo 在业务动作失败时回退模式（如读档失败回 slots）。合法模式见 MODES。"""
        if value not in MODES:
            raise ValueError(f"未知 UI 模式：{value!r}（可用：{list(MODES)}）")
        self._mode = value
        self._cursor = 0

    # ==================== 数据注入 / 刷新 ====================

    def set_history(self, history) -> None:
        """demo 每帧把 GameState 的 history 注入（回看数据源，纯查看不改状态）。"""
        self._history = list(history or [])
        # 历史变短（如读档回到过去）时钳制翻页偏移，防止越界
        max_off = max(0, len(self._history) - BACKLOG_PAGE_SIZE)
        self._backlog_offset = min(self._backlog_offset, max_off)

    def set_gallery(self, gallery, seen_sprites) -> None:
        """demo 每帧注入已解锁 CG 列表与已见立绘列表（画廊数据源，纯查看）。"""
        self._gallery = list(gallery or [])
        self._seen_sprites = list(seen_sprites or [])

    def set_gallery_config(self, cells) -> None:
        """P28 E1：注入固定格子清单（data.load_gallery_config 的结果）。

        空清单 = 保持旧行为（只显示已解锁 CG）。
        """
        self._gallery_cells = [
            {"name": str(c.get("name")), "images": list(c.get("images") or []),
             "require": list(c.get("require") or [])}  # P33：解锁前置条件（CG 名列表）
            for c in (cells or []) if isinstance(c, dict) and c.get("name")
        ]

    def refresh(self) -> None:
        """刷新存档列表缓存与设置值。进入 title / slots / settings 时自动调用。"""
        try:
            entries = save_api.list_slots()
        except Exception:
            entries = []  # 存档目录不可读不阻塞 UI
        self._slot_entries = entries
        self._has_save = bool(entries)
        self._settings = data.load_settings(self.settings_path)
        # ⑪ 作品名一级：settings.json 的 title 字段（无则留给剧本注释 / 未命名作品）
        title = self._settings.get("title") if isinstance(self._settings, dict) else None
        self._game_title = str(title).strip() if title else None
        if self._mode == "slots" and self._slots_purpose is not None:
            self._rebuild_slot_rows()

    def set_settings(self, settings) -> None:
        """demo 修改设置后同步内存值：修改即写 UI 立即显示；也用于落盘后回写
        （assets 根不是当前目录时 refresh 读不到同一个文件）。"""
        if isinstance(settings, dict):
            self._settings = dict(settings)

    def set_script_title(self, title) -> None:
        """⑪ 作品名二级：demo 读剧本首行 # 注释后注入（None/空串 = 无）。"""
        text = str(title).strip() if title else ""
        self._script_title = text or None

    # ==================== 输入处理 ====================

    def handle(self, key: str) -> dict | None:
        """消费一个统一键名（up/down/confirm/back/backlog/slot1~slot10/quicksave）。

        返回业务动作 dict（demo 执行）或 None（纯导航，UI 自己消化）。
        """
        # F5 快存：游戏进行中随时可用（不进入存档列表，直接写独立 quick 槽）
        if key == "quicksave" and self._mode == "playing":
            return {"action": "save_slot", "slot": save_api.QUICK_SLOT}
        handler = {
            "title": self._handle_title,
            "playing": self._handle_playing,
            "menu": self._handle_menu,
            "slots": self._handle_slots,
            "settings": self._handle_settings,
            "backlog": self._handle_backlog,
            "gallery": self._handle_gallery,
        }[self._mode]
        return handler(key)

    def click(self, hit: dict, pos: tuple | None = None) -> dict | None:
        """P31-b：鼠标点击分派。

        renderer 只上报"点了哪个区域"（平面 dict），语义仍由 UI 决定：
        列表项 = 先同步光标再走 confirm，与键盘完全同一条逻辑，不新增第二套行为。
        pos：P49 逻辑画布坐标（音量滑条按点击位置比例定值，供拖动复用）。
        """
        if not isinstance(hit, dict):
            return None
        kind = hit.get("kind")
        if kind == "key":
            return self.handle(str(hit.get("key") or "back"))
        if kind == "gallery_tab":
            idx = hit.get("index")
            if not isinstance(idx, int) or not (0 <= idx < len(GALLERY_TABS)):
                return None
            self._gallery_tab = idx
            self._cursor = 0
            self._gallery_page = 0
            self._close_detail()
            return None
        if kind == "toggle_subtitles":
            # P48：对话框顶部 ▼——隐藏/显示字幕栏（截图模式），渲染层切换
            return {"action": "toggle_subtitles"}
        if kind == "prev_arrow":
            # P48：快捷栏 ◀ = 回看上一句（打开历史）
            self._enter("backlog")
            self._backlog_offset = 0
            return None
        if kind == "quickbar":
            # P34-T1：游戏内快捷栏（SAVE/LOAD/LOG/AUTO/SKIP/CONFIG）
            idx = hit.get("index")
            if not isinstance(idx, int) or not (0 <= idx < len(QUICKBAR_ITEMS)):
                return None
            if idx == 0:      # SAVE
                self._enter_slots("save", return_mode="playing")
            elif idx == 1:    # LOAD
                self._enter_slots("load", return_mode="playing")
            elif idx == 2:    # LOG
                self._enter("backlog")
                self._backlog_offset = 0
            elif idx == 3:    # AUTO
                self.auto_on = not self.auto_on
            elif idx == 4:    # SKIP（P44-C：默认禁，开发者 config.ui.quickbar.skip_enabled 开启）
                if self.skip_allowed:
                    self.skip_on = not self.skip_on
                return None
            elif idx == 5:    # CONFIG
                self._enter("settings", return_mode="playing")
            return None
        if kind == "settings_nav":
            # P35/P49：左侧分组导航——点击切到该分组页并选中组首项（只移动光标，不修改值）
            idx = hit.get("index")
            if self._mode == "settings" and isinstance(idx, int) and idx >= 0:
                visible = self._visible_settings()
                _idxs, _gname = self._settings_group_range(visible)  # 稳定当前页序号
                g = (visible[idx].get("group") or "基础") if 0 <= idx < len(visible) else None
                if g is not None:
                    # 组名 → 分页序号（按 SETTINGS_ITEMS 出现顺序）
                    groups = []
                    for it in visible:
                        gn = it.get("group") or "基础"
                        if gn not in groups:
                            groups.append(gn)
                    if g in groups:
                        self._settings_tab = groups.index(g)
                self._cursor = idx
            return None
        if kind == "settings_slider":
            # P49：音量滑条——点击/拖动任意位置 = 按比例直接定值（0~100%）
            if self._mode == "settings" and isinstance(pos, tuple):
                key = hit.get("key")
                bar = hit.get("bar")
                if key and isinstance(bar, (tuple, list)) and len(bar) == 2:
                    bx, bw = float(bar[0]), float(bar[1])
                    if bw > 0:
                        ratio = max(0.0, min(1.0, (pos[0] - bx) / bw))
                        self._cursor = min(self._cursor, max(0, len(self._visible_settings()) - 1))
                        return {"action": "settings_set", "key": key,
                                "value": round(ratio, 2)}
            return None
        if kind != "item":
            return None
        idx = hit.get("index")
        if not isinstance(idx, int) or not hit.get("enabled", True):
            return None
        if self._mode == "title":
            if not (0 <= idx < len(self.title_items())):
                return None
            self._cursor = idx
        elif self._mode == "menu":
            if not (0 <= idx < len(MENU_ITEMS)):
                return None
            self._cursor = idx
        elif self._mode == "settings":
            if not (0 <= idx < len(self._visible_settings())):
                return None
            self._cursor = idx
        elif self._mode == "slots":
            if not (0 <= idx < len(self._slots or [])):
                return None
            self._cursor = idx
        elif self._mode == "gallery":
            items = self._gallery_items()
            per_page = GALLERY_COLS * GALLERY_ROWS
            page = items[self._gallery_page * per_page:(self._gallery_page + 1) * per_page]
            if not (0 <= idx < len(page)) or not page[idx].get("unlocked"):
                return None
            self._cursor = idx
        return self.handle("confirm")

    # ==================== 视图导出 ====================

    def view(self, now_ms=None) -> dict:
        """导出当前模式的绘制数据（renderer 只读，不反向操作 UI）。

        now_ms：可选的毫秒时钟（demo 传 renderer._now_ms()）；画廊幻灯片用它自动换图。
        省略时用系统单调时钟（纯测试/离线调用）。
        """
        now = self._now_ms(now_ms)
        self._last_now_ms = now
        v = {
            "mode": self._mode,
            # ⑪ 作品名三级回退：settings.title → 剧本首行 # 注释 → 未命名作品
            "title": self._game_title or self._script_title or "未命名作品",
            "items": None,
            "cursor": self._cursor,
            "slots": None,        # None 表示不在存档列表模式
            "slots_mode": None,   # "save" / "load"
            "settings": None,
            "history": None,
            "backlog_offset": 0,
        }
        lang = str((self._settings or {}).get("lang") or i18n.DEFAULT_LANG)
        if self._mode == "title":
            # P44：菜单项可配置（config.ui.title.items）；"继续"无存档灰置，其余可用
            v["items"] = [
                {"label": i18n.t(label, lang), "enabled": (label != "继续") or self._has_save}
                for label in self.title_items()
            ]
        elif self._mode == "menu":
            v["items"] = [{"label": i18n.t(s, lang), "enabled": True} for s in MENU_ITEMS]
        elif self._mode == "slots":
            v["slots"] = self._slots
            v["slots_mode"] = self._slots_purpose
        elif self._mode == "settings":
            cur = self._settings or {}
            v["settings"] = dict(cur)
            # P30-S2-2：只导出可见项（settings_hidden 声明隐藏的不进列表，光标范围同步缩小）
            # P49：同时导出当前分组页序号（渲染层只画该组，左侧导航按它高亮）
            visible = self._visible_settings()
            groups = []
            for it in visible:
                g = it.get("group", "基础")
                if g not in groups:
                    groups.append(g)
            v["settings_tab"] = self._settings_tab if 0 <= self._settings_tab < len(groups) else 0
            v["settings_groups"] = [i18n.t(g, lang) for g in groups]
            v["capturing"] = self.capturing   # U10：改键中（渲染层显示「请按键…」）
            v["items"] = [
                {"label": i18n.t(it["label"], lang), "key": it["key"], "kind": it["kind"],
                 "group": i18n.t(it.get("group", "基础"), lang),
                 "enabled": True,
                 # P37-M1：枚举项把候选值与显示标签带给渲染层（普通项为 None）
                 "options": it.get("options"),
                 "labels": ([i18n.t(x, lang) for x in it["labels"]]
                            if it.get("labels") else None),
                 "value": cur.get(it["key"], data.DEFAULT_SETTINGS[it["key"]])}
                for it in visible
            ]
        elif self._mode == "backlog":
            v["history"] = self._visible_history()
            v["backlog_offset"] = self._backlog_offset
        elif self._mode == "gallery":
            v["gallery"] = self._gallery_view(now)
        else:  # playing：导出快捷栏（P34-T1）
            v["quickbar"] = {"labels": list(QUICKBAR_ITEMS),
                             "auto": self.auto_on, "skip": self.skip_on,
                             "skip_allowed": self.skip_allowed,
                             "skip_mode": self.skip_mode}
        return v

    # ==================== 各模式键位语义 ====================

    def _handle_title(self, key: str) -> dict | None:
        items = self.title_items()
        if key in ("up", "down"):
            self._move_cursor(len(items), -1 if key == "up" else 1)
            return None
        if key == "back":
            return {"action": "quit"}  # 标题画面 Esc = 退出（3.1）
        if key == "confirm":
            if not (0 <= self._cursor < len(items)):
                return None
            label = items[self._cursor]
            if label == "开始新游戏":
                self._enter("playing")
                return {"action": "start_game"}
            if label == "继续":  # 无存档灰置，confirm 不产生动作
                if not self._has_save:
                    return None
                self._enter("playing")
                return {"action": "continue_game"}
            if label == "读档":
                self._enter_slots("load", return_mode="title")
                return None
            if label == "设置":
                self._enter("settings", return_mode="title")
                return None
            if label == "画廊":  # 标题页直达 P30-S2-3 收尾引导闭环
                self._enter("gallery", return_mode="title")
                self._gallery_tab = 0
                self._gallery_page = 0
                self._gallery_detail = None
                return None
            if label == "退出":
                return {"action": "quit"}
        return None

    def _handle_playing(self, key: str) -> dict | None:
        # 游戏中正常游玩键（空格推进/选项选择）由 renderer 直发游戏动作，不经 UI；
        # 选项模式优先于回看/菜单（renderer 保证有选项时不发 backlog 键）
        if key == "back":
            self._enter("menu")
            return None
        if key == "backlog":
            self._enter("backlog")
            self._backlog_offset = 0  # 每次打开从最新一屏起
            return None
        return None

    def _handle_menu(self, key: str) -> dict | None:
        if key in ("up", "down"):
            self._move_cursor(len(MENU_ITEMS), -1 if key == "up" else 1)
            return None
        if key == "back":
            self._enter("playing")
            return None
        if key == "confirm":
            idx = self._cursor
            if idx == 0:  # 存档
                self._enter_slots("save", return_mode="menu")
                return None
            if idx == 1:  # 读档
                self._enter_slots("load", return_mode="menu")
                return None
            if idx == 2:  # 画廊
                self._enter("gallery", return_mode="menu")
                self._gallery_tab = 0
                self._gallery_page = 0
                self._close_detail()
                return None
            if idx == 3:  # 回标题
                self._enter("title")
                return {"action": "to_title"}
            if idx == 4:  # 设置
                self._enter("settings", return_mode="menu")
                return None
            if idx == 5:  # 退出
                return {"action": "quit"}
        return None

    def _handle_slots(self, key: str) -> dict | None:
        rows = self._slots or []
        n = len(rows)
        cols = 5 if n > 9 else 3  # 与渲染层一致：10 格 5×2，少于此数 3 列
        if key in ("up", "down"):
            # 九宫格导航：上下移动一整行（越界停在边界），左右移动一列
            delta = (cols if key == "down" else -cols)
            target = self._cursor + delta
            if 0 <= target < n:
                self._cursor = target
            return None
        if key in ("left", "right"):
            target = self._cursor + (1 if key == "right" else -1)
            if 0 <= target < n:
                self._cursor = target
            return None
        if key == "back":
            self._enter(self._return_mode)
            return None
        slot = None
        if key == "confirm":
            if 0 <= self._cursor < len(rows):
                row = rows[self._cursor]
                if row["enabled"]:  # 读档模式空位灰置不可选
                    slot = row["slot"]
        elif key == "quicksave":
            # 快存独立于 10 个普通存档位（slot_quick.json），不再覆盖存档 1
            if save_api.QUICK_SLOT:
                slot = save_api.QUICK_SLOT
        elif key.startswith("slot") and key[4:].isdigit():
            k = int(key[4:])
            # 数字键 1~9 / 0 直选对应格（0 = 第 10 格）
            if 1 <= k <= n and rows[k - 1]["enabled"]:
                slot = rows[k - 1]["slot"]
        if slot is None:
            return None
        if self._slots_purpose == "save":
            # 存档后留在列表（demo 执行完会 refresh 刷新显示），覆盖不二次确认（3.3）
            return {"action": "save_slot", "slot": slot}
        self._enter("playing")  # 读档乐观切换；失败由 demo 回退模式
        return {"action": "load_slot", "slot": slot}

    def _handle_settings(self, key: str) -> dict | None:
        # P30-S2-2：光标范围按可见项（settings_hidden 过滤后）计算
        # P49：分页——方向键在分组内移动，到底/到顶跨到相邻分组（循环），
        # 分页高亮随光标移动实时切换（键盘与鼠标同一套分页状态）。
        visible = self._visible_settings()
        if key in ("up", "down"):
            if not visible:
                return None
            groups = []
            for it in visible:
                g = it.get("group") or "基础"
                if g not in groups:
                    groups.append(g)
            idxs, _g = self._settings_group_range(visible)
            step = 1 if key == "down" else -1
            cur = idxs.index(self._cursor) if self._cursor in idxs else -1
            if cur >= 0 and 0 <= cur + step < len(idxs):
                self._cursor = idxs[cur + step]       # 页内移动
            else:
                # 跨页：切到相邻分组首/末项（循环）
                gi = (self._settings_tab + step) % len(groups)
                idxs2, _g2 = self._settings_group_range(visible, gi)
                self._settings_tab = gi
                self._cursor = idxs2[0] if step > 0 else idxs2[-1]
            return None
        if key == "back":
            self._enter(self._return_mode)
            return None
        if key == "confirm":
            self._cursor = min(self._cursor, max(0, len(visible) - 1))
            item = visible[self._cursor]
            # U10：键位项进入"按新键"捕获，其余项循环/直接改值
            if item.get("kind") == "key":
                return {"action": "settings_capture", "key": item["key"]}
            # 修改即写由 demo 执行（调 next_value + data.save_settings）
            # choice 类无 step（P37-M1），demo 只用 key 调 next_value
            return {"action": "settings_change", "key": item["key"], "delta": item.get("step")}
        return None

    def _settings_group_range(self, visible: list, tab: int | None = None) -> tuple:
        """P49：返回指定分组（缺省当前页）的可见项索引列表与组名（组内项不必连续）。

        没有可见项时返回 ([], None)；tab 越界时折回最后一组。
        """
        if not visible:
            return ([], None)
        groups = []
        for it in visible:
            g = it.get("group") or "基础"
            if g not in groups:
                groups.append(g)
        gi = tab if (tab is not None and 0 <= tab < len(groups)) else (
            self._settings_tab if 0 <= self._settings_tab < len(groups) else len(groups) - 1)
        if tab is not None:
            self._settings_tab = gi
        gname = groups[gi]
        idxs = [i for i, it in enumerate(visible) if (it.get("group") or "基础") == gname]
        return (idxs, gname)

    def _handle_backlog(self, key: str) -> dict | None:
        if key == "up":  # 往过去翻一页
            max_off = max(0, len(self._history) - BACKLOG_PAGE_SIZE)
            self._backlog_offset = min(self._backlog_offset + BACKLOG_PAGE_SIZE, max_off)
            return None
        if key == "down":  # 往最新翻一页；已在最新一屏时关闭回看（3.1：↓ 或 Esc 关闭）
            if self._backlog_offset <= 0:
                self._enter("playing")
            else:
                self._backlog_offset = max(0, self._backlog_offset - BACKLOG_PAGE_SIZE)
            return None
        if key == "back":
            self._enter("playing")
            return None
        return None

    # ==================== 画廊（P13 / P28 E1+E3）====================

    @staticmethod
    def _now_ms(now_ms=None) -> int:
        """统一时钟：外部注入优先，缺省用 stdlib 单调时钟（毫秒）。"""
        if now_ms is not None:
            return int(now_ms)
        return int(time.monotonic() * 1000)

    def _cell_images(self, name: str) -> list[str]:
        """格名 → 幻灯片图列表（无配置/未命中 = 空，走单图旧行为）。"""
        for cell in self._gallery_cells:
            if cell["name"] == name:
                return list(cell.get("images") or [])
        return []

    def _gallery_items(self) -> list[dict]:
        """当前页签的条目列表。

        P28 E1：CG 页签有 gallery_config.json 时固定渲染全部格子（含未解锁），
        无配置时保持旧行为（只列已解锁 CG）；立绘页签始终只列已见立绘。
        """
        if self._gallery_tab == 0:
            if self._gallery_cells:
                unlocked = set(self._gallery)
                # P33：有 require 的格由前置 CG 全部解锁决定（如"4 结局全通"奖励格）；
                # 无 require 的格保持旧行为（自身被 @cg 过即解锁）
                def _cell_unlocked(c) -> bool:
                    req = c.get("require") or []
                    if req:
                        return all(r in unlocked for r in req)
                    return c["name"] in unlocked
                return [{"name": c["name"], "kind": "cg",
                         "unlocked": _cell_unlocked(c),
                         "images": list(c.get("images") or [])}
                        for c in self._gallery_cells]
            return [{"name": n, "kind": "cg", "unlocked": True} for n in self._gallery]
        return [{"name": n, "kind": "sprite", "unlocked": True} for n in self._seen_sprites]

    def _gallery_view(self, now_ms: int) -> dict:
        """画廊模式导出给 renderer 的数据（网格或大图详情）。"""
        items = self._gallery_items()
        per_page = GALLERY_COLS * GALLERY_ROWS
        pages = max(1, (len(items) + per_page - 1) // per_page)
        self._gallery_page = min(self._gallery_page, pages - 1)
        start = self._gallery_page * per_page
        page_items = items[start:start + per_page]
        cursor = min(self._cursor, max(0, len(page_items) - 1))
        detail = self._gallery_detail
        detail_images = self._cell_images(detail) if detail is not None and self._gallery_tab == 0 else []
        if detail is not None and detail_images:
            detail_images = self._advance_slide(detail_images, now_ms)
        return {
            "tab": self._gallery_tab,
            "tabs": list(GALLERY_TABS),
            "items": page_items,
            "page": self._gallery_page,
            "pages": pages,
            "cols": GALLERY_COLS,
            "cursor": cursor,
            "detail": detail,
            "detail_images": detail_images,
            "detail_index": self._gallery_detail_index,
            # 光标落在未解锁格：renderer 底部提示"未解锁"
            "locked_selected": bool(page_items and not page_items[cursor].get("unlocked")),
            "total": len(items),
        }

    def _advance_slide(self, images: list[str], now_ms: int) -> list[str]:
        """P28 E3：幻灯片自动换图（每 GALLERY_SLIDE_MS 一张，循环）。"""
        n = len(images)
        if n <= 1:
            self._gallery_detail_index = 0
            self._gallery_slide_t0 = None
            return images
        if self._gallery_slide_t0 is None:
            self._gallery_detail_index = min(self._gallery_detail_index, n - 1)
            self._gallery_slide_t0 = now_ms
            return images
        elapsed = now_ms - self._gallery_slide_t0
        if elapsed >= GALLERY_SLIDE_MS:
            step = elapsed // GALLERY_SLIDE_MS
            self._gallery_detail_index = (self._gallery_detail_index + step) % n
            self._gallery_slide_t0 = now_ms
        return images

    def _open_detail(self, name: str) -> None:
        """进入大图鉴赏：重置幻灯片到第一张。"""
        self._gallery_detail = name
        self._gallery_detail_index = 0
        self._gallery_slide_t0 = None

    def _close_detail(self) -> None:
        self._gallery_detail = None
        self._gallery_detail_index = 0
        self._gallery_slide_t0 = None

    def _handle_gallery(self, key: str) -> dict | None:
        if self._gallery_detail is not None:
            images = self._cell_images(self._gallery_detail) if self._gallery_tab == 0 else []
            if key in ("confirm", "back"):
                self._close_detail()
            elif key in ("left", "right") and len(images) > 1:
                # P28 E3：手动切换幻灯片，并重置自动计时
                step = -1 if key == "left" else 1
                self._gallery_detail_index = (self._gallery_detail_index + step) % len(images)
                self._gallery_slide_t0 = self._last_now_ms
            return None
        items = self._gallery_items()
        per_page = GALLERY_COLS * GALLERY_ROWS
        page_items = items[self._gallery_page * per_page:(self._gallery_page + 1) * per_page]
        if key == "back":
            # 回到进画廊前的界面（标题 / 游戏内菜单），不要一律钻回菜单
            self._enter(self._return_mode)
            return None
        if key == "left" or key == "right":
            # 左右键切页签（光标回到 0）
            self._gallery_tab = (self._gallery_tab + (1 if key == "right" else -1)) % len(GALLERY_TABS)
            self._cursor = 0
            self._gallery_page = 0
            self._close_detail()
            return None
        if not page_items:
            return None
        n = len(page_items)
        self._cursor = min(self._cursor, n - 1)
        if key == "up":
            self._cursor = (self._cursor - GALLERY_COLS) % n if n > GALLERY_COLS else self._cursor
        elif key == "down":
            self._cursor = (self._cursor + GALLERY_COLS) % n if n > GALLERY_COLS else self._cursor
        elif key == "confirm":
            item = page_items[self._cursor]
            if item.get("unlocked"):  # 未解锁格不可进入（界面提示"未解锁"）
                self._open_detail(item["name"])
        return None

    def _enter(self, mode: str, return_mode: str | None = None) -> None:
        """切模式并重置光标；进 title / settings 时顺带刷新外部数据。"""
        self._mode = mode
        self._cursor = 0
        if return_mode is not None:
            self._return_mode = return_mode
        if mode in ("title", "settings"):
            self.refresh()

    def _enter_slots(self, purpose: str, return_mode: str) -> None:
        self._mode = "slots"
        self._slots_purpose = purpose
        self._return_mode = return_mode
        self.refresh()  # 进 slots 必刷新存档列表（3.3 数据源）
        self._rebuild_slot_rows()
        self._cursor = 0
        if purpose == "load":
            # 读档模式光标落到第一个有存档的位上，省去按键
            for i, row in enumerate(self._slots or []):
                if row["enabled"]:
                    self._cursor = i
                    break

    def _rebuild_slot_rows(self) -> None:
        """把 list_slots() 结果补全成存档网格：默认 10 位（config.ui.slots.count 可改）。"""
        count = save_api.SLOT_COUNT
        try:
            slots_cfg = ((self._config.data.get("ui") or {}).get("slots") or {}) \
                if self._config is not None else {}
            count = int(slots_cfg.get("count", save_api.SLOT_COUNT))
        except (TypeError, ValueError):
            count = save_api.SLOT_COUNT
        count = max(1, min(count, save_api.SLOT_COUNT))
        by_slot = {e["slot"]: e for e in self._slot_entries}
        rows = []
        for n in range(1, count + 1):
            key = str(n)
            entry = by_slot.get(key)
            empty = entry is None
            rows.append({
                "slot": int(key),
                "name": f"存档 {key}",
                "label": None if empty else entry.get("label"),
                "saved_at": None if empty else entry.get("saved_at"),
                # ⑨ 存档卡片三要素（list_slots 已返回，这里透传给 renderer 画卡片）
                "thumbnail_path": None if empty else entry.get("thumbnail_path"),
                "chapter_name": None if empty else entry.get("chapter_name"),
                "last_text": None if empty else entry.get("last_text"),
                "empty": empty,
                # 读档模式下空位灰置不可选；存档模式全部可选（覆盖不二次确认）
                "enabled": not (empty and self._slots_purpose == "load"),
            })
        self._slots = rows

    def _move_cursor(self, count: int, delta: int, base: int = 0) -> None:
        """光标循环移动（到底回顶）。灰置项可停留但 confirm 无效。

        base：可选区间起点（P49 设置分页——只在 [base, base+count) 内移动，到边夹停）。
        """
        if count <= 0:
            return
        target = self._cursor + delta
        if base:
            if target < base:
                target = base
            elif target >= base + count:
                target = base + count - 1
            self._cursor = target
            return
        self._cursor = (self._cursor + delta) % count

    def _visible_history(self) -> list[dict]:
        """回看当前屏的历史切片：offset 0 = 最新一屏，越大越往过去。"""
        n = len(self._history)
        end = n - self._backlog_offset
        start = max(0, end - BACKLOG_PAGE_SIZE)
        return self._history[start:end]
