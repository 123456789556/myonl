"""MYONL 无状态渲染器。

铁律：
- render(state) 只读 GameState，绝不修改；展示进度（打字机/转场/音乐切换）只存 renderer 内部缓存
- 素材缺失 → 占位色块 + 中文标签兜底，不崩；音频缺失 → 静音不崩（stderr 中文警告）
- 资源零转换：images/ audio/ fonts/ 文件夹直读
- 本模块不得 import engine.runtime（依赖单向：parser → runtime → renderer）

render(state, ui_view) 支持 UI 覆盖层（标题/菜单/存档/设置/回看）；
handle_input(ui_mode) 按 UI 模式分发键位——非 playing 模式统一翻译成 UI 键名。
- 绘制方法按职责拆至 render_*.py 的 Mixin（见 class 基类），本模块为组合入口
"""
from __future__ import annotations

import os
import random
import sys
import time
from collections import OrderedDict

import pygame

from . import config as cfgapi
from . import data
from . import i18n
from . import richtext
from . import save as save_api
from . import timeline as tlapi
# renderer.py 拆分第 1 步：模块级工具函数与 UI 键位表迁至 render_utils.py
# （import 到本模块命名空间，engine.renderer._ui_key 等旧引用保持不变）
from .render_utils import (
    _UI_KEYMAP,
    _clip_text,
    _format_setting,
    _scale_to_fit,
    _slot_card_head,
    _slot_row_text,
    _ui_key,
    _wrap_text,
    # 常量（原定义于本模块，现统一定义在 render_utils）
    DEFAULT_SIZE,
    DIALOG_HEIGHT,
    DIALOG_TOP,
    CHOICE_ROW_HEIGHT,
    FADE_SECONDS,
    FONT_SIZE,
    MISSING_COLOR,
    TITLE_FONT_SIZE,
    UI_HIGHLIGHT,
    UI_DISABLED,
    UI_SELECTED_BG,
    UI_SELECTED_BG_ALPHA,
    UI_SELECTED_FG,
    UI_SELECTED_BORDER,
    UI_IDLE_BG,
    UI_IDLE_BG_ALPHA,
    DIALOG_FG,
    DIALOG_FG_DIM,
    SPRITE_MARGIN,
    IMG_CACHE_MAX,
    IMG_CACHE_MAX_BYTES,
    FRAME_WINDOW,
    ANIM_FPS,
    SFX_CACHE_MAX,
    _FRAME_EXTS,
    CAM_PAN_RATIO,
    CAM_ZOOM_SECONDS,
    CAM_SHAKE_PX,
    TRANS_DEFAULT_SECONDS,
    SPRITE_ANIM_DEFAULTS,
    LAYER_ORDER,
)
from .render_dialog import DialogMixin
from .render_media import MediaMixin
from .render_scene import SceneMixin
from .render_sprites import SpriteMixin
from .render_text import TextMixin, TEXT_CACHE_MAX, TEXT_WIDTH_CACHE_MAX
from .render_ui_pages import UiPagesMixin
from .render_ui_screens import UiScreensMixin
from .render_window import WindowMixin


# 非 playing 模式的 pygame 键 → 统一 UI 键名（数字键 1~9/0 → slot1~slot10）
# 已随 render_utils 拆分迁移（见文件顶部 import）


class Renderer(TextMixin, SceneMixin, SpriteMixin, MediaMixin, DialogMixin,
               UiScreensMixin, UiPagesMixin, WindowMixin):
    """把 Runtime.snapshot() 的 GameState 画成逻辑画布画面，并把玩家输入翻译成统一动作。"""

    def __init__(self, size=None, assets_root="."):
        # assets_root：资源根目录，其下有 images/、audio/、fonts/ 三个子目录
        self.assets_root = str(assets_root)
        self.settings = data.load_settings(os.path.join(self.assets_root, "settings.json"))
        # P30-S3：只读配置（config.json）——窗口标题/字号/色板/遮罩 alpha/键位
        self.config = cfgapi.load(self.assets_root)
        # T10：逻辑画布尺寸——显式传入优先，否则读 config.canvas_size()（默认 1280×720）
        if size is None:
            size = self.config.canvas_size()
        self.size = tuple(size)
        # P51：玩家可调 UI 几何（settings.json 的 ui_geometry）并入配置视图——
        # 引擎默认 ← config.json ← 玩家存档三层隔离，位置/大小/圆角玩家可改
        self.config.apply_player_ui(self.settings.get("ui_geometry"))
        self._ui_scale = self.config.ui_scale()  # T10 视觉比例（720p 基准，1080p=1.5）
        for w in self.config.warnings:
            print(f"[配置] {w}", file=sys.stderr)

        pygame.display.init()
        pygame.font.init()
        # P31-a：逻辑画布尺寸可配（T10），真实窗口可自由缩放（等比 letterbox 呈现）
        # M1.5：display_mode（窗口/无边框全屏/全屏）优先于旧 fullscreen 布尔（老 settings 兼容）
        _mode = str(self.settings.get("display_mode") or "").strip().lower()
        if _mode == "fullscreen":
            self._fullscreen = True
        elif _mode == "borderless":
            self._fullscreen = False
        else:
            self._fullscreen = bool(self.settings.get("fullscreen", False))
        self._borderless = _mode == "borderless"
        # M1.5：设备档位（低配自动降级；settings.quality_tier 可强制 low/mid/high）
        self._capability_tier = self._detect_tier()
        self._window_size = self._clamp_window_size(self.settings.get("window_size"))
        self._window_dirty = False      # 窗口尺寸/全屏是否有未落盘的改动
        self._window_persist_t0 = 0     # 上次落盘时刻（拖拽时按 500ms 节流写 settings.json）
        self._window = self._open_window()
        self._set_window_icon()  # 打包模板 exe 的通用图标 → 用工程 icon.png 覆盖窗口图标
        self._ensure_window_sane()  # P34：窗口自检（屏幕外/最小化特征强制还原居中）
        self._screen = pygame.Surface(self.size)   # 逻辑画布（所有绘制都按画布尺寸算）
        self._view = pygame.Rect(0, 0, *self.size)  # 逻辑画布在窗口中的位置（缩放 + 黑边）
        pygame.display.set_caption(self.config.window_title)
        self._keymap = cfgapi.keymap(self.config, self.settings)
        self._key_capture = None   # U10：设置页改键捕获态（下一键即绑定）
        try:
            pygame.mixer.init()
            self._audio_ok = True
        except pygame.error:
            # 无音频设备（如无头环境）→ 全部静音，不崩
            self._audio_ok = False

        self._load_fonts()

        # ---- 内部展示缓存（不进 GameState）----
        self._clock = pygame.time.Clock()
        self._img_cache = OrderedDict()  # 路径 -> Surface（LRU：末尾最新，超限从头释放）
        self._img_bytes = 0              # 图片缓存估算字节数
        self._img_cache_max = IMG_CACHE_MAX
        self._img_cache_max_bytes = IMG_CACHE_MAX_BYTES
        if self._reduce_effects():
            # 低配：图片缓存砍到 128MB 上限（先保流畅，再谈画质）
            self._img_cache_max_bytes = min(self._img_cache_max_bytes, 128 * 1024 * 1024)
        self._sfx_cache = OrderedDict()  # 路径 -> Sound（LRU，上限 SFX_CACHE_MAX）
        # T8：字体 Surface 缓存（字体 id, 文本, 颜色, 抗锯齿）-> Surface（LRU，上限 TEXT_CACHE_MAX）
        self._text_cache = OrderedDict()
        self._text_cache_max = TEXT_CACHE_MAX
        # T8：字体度量缓存（字体 id, 文本）-> 像素宽（LRU，上限 TEXT_WIDTH_CACHE_MAX）
        self._text_width_cache = OrderedDict()
        self._text_width_max = TEXT_WIDTH_CACHE_MAX
        self._seq_index = {}             # (子目录, 前缀) -> 帧路径列表（只 stat 不加载）
        self._video_key = None           # 当前视频 (名称, fps)，变化则重置计时
        self._video_t0 = 0               # 当前视频起始时刻（毫秒）
        self._video_warned = set()       # 已警告过的缺帧视频名（只警告一次）
        # P30-C-a：统一时间轴——镜头/转场/立绘帧序列/停留共用一个时钟，均不进 GameState
        self.timeline = tlapi.Timeline()
        self._vis_t0 = 0.0  # P33-b：窗口可见性自检节流（1s 一次，防抖动）
        self._voice_key = None           # 已配过音的 history 身份（防重复播放）
        self._voice_channel = None       # 配音专用声道（语音等待/自动推进的判定依据）
        self._voice_done_pending = False # 配音已起播、等待播完（voice_auto_advance 用）
        if self._audio_ok:
            try:
                pygame.mixer.set_reserved(0)  # 声道 0 留给配音，普通 sfx 不占
                self._voice_channel = pygame.mixer.Channel(0)
            except pygame.error:
                self._voice_channel = None
        self._last_bg = None            # 上一帧 bg（转场检测）
        self._toast_text = ""           # P51-T6：左下角短提示（热重载反馈）
        self._toast_until = 0
        self._fade_t0 = None            # 淡入起始时刻（pygame ticks，毫秒）
        # P33/M1.5：背景切换淡入时长，默认取 config.pacing.scene_fade
        self._bg_fade_seconds = self._pacing("scene_fade", FADE_SECONDS)
        self._next_bg_fade = None       # P33：@bg fadein= 传入的下一次淡入时长（一次性）
        self._music = None              # 当前已加载的音乐名
        self._pending_music = None      # P26 T3：等淡出完成后再切的新曲 {"track","fadein","due"}
        self._tw_text = ""              # 打字机目标全文
        self._tw_shown = 0.0            # 打字机已显示字符数（浮点累计）
        self._history_key = None        # (history 长度, 末条 char, 末条 text)，变化则重置打字机
        self._options: list[dict] | None = None  # 当前选项列表（pending_choice 非空时；UI 设计预览会直接注入示例）
        self._choice_key = None         # 选项身份（用于检测新选项组）
        self._choice_index = 0          # 当前高亮选项
        self._choice_rects = []         # [(Rect, 序号, 可点)]，鼠标点击判定用
        self._ui_hits = []              # P31-b：UI 层可点区域 [(Rect, 语义)]，每帧重collect
        self._mouse_down = False        # P49：鼠标左键按住状态（音量条拖动）
        self._choice_lock_t0 = None     # ⑤ 选项锁起始生效时间（None=无锁）
        self._choice_is_new = False     # ⑤ 新选项组标记（_draw_choices 画完后才启动时间锁）
        self._narration_cooldown_t0 = None  # ⑭ 旁白节奏差：char=None 台词打字机完后 400ms 推进冷却
        self._ending_fade_t0 = None         # ⑩ 结尾淡出开始时间（None=无）；值设置后开始 0.8s 淡出
        self._ending_fade_done = False      # ⑩ 淡出完成标记（demo 读此值决定是否回标题）
        self._ui_mode = None            # 当前 UI 模式（render 时从 ui_view 取，输入分发用）
        self._splash_mode = False       # P26 T1：序幕模式（不画对话框，台词当字幕居中显示）
        self._ui_hidden = False         # P48：截图模式——隐藏字幕栏/快捷栏（▼ 切换）
        # P30-S1-5：长段落翻页状态（history 变化时重置；仅 playing 分页）
        self._page_index = 0            # 当前台词第几页（0 起）
        self._page_count = 1            # 当前台词总页数（≤1 = 不分页）

        # ---- 演出系统内部缓存（CG / 镜头 / 转场 / 语音唇形，均不进 GameState）----
        self._scene = pygame.Surface(self.size)  # 背景+立绘合成层（镜头变换作用于此）
        self._cg_showing = None          # 当前展示的 CG 名（None=未展示）；展示时屏蔽对话框
        self._fg = None                  # P30-C-b：前景贴图 {"name","x","y","alpha"}（None=无）
        self._sprite_anim = {}           # P30-C-c：角色ID -> {x,y,alpha,scale} 补间后的显示值
        self._layer_cache = {}           # P30-C-d：分层立绘合成结果缓存（逐帧不重拼）
        # 镜头：只有持久状态留在 renderer（动画本身挂在 Timeline 的 camera 轨上）
        self._cam_dx = 0.0               # 持久平移偏移 x（pan 后停留）
        self._cam_dy = 0.0               # 持久平移偏移 y
        self._cam_scale = 1.0            # 持久缩放比（zoom 后停留）
        self._shake_dx = 0.0             # 临时震动偏移 x（shake 期间）
        self._shake_dy = 0.0             # 临时震动偏移 y
        # 转场：待生效 + 旧画面（播放进度挂在 Timeline 的 transition 轨上）
        self._pending_transition = None  # (kind, args) 待用转场，下一次 bg 变化时触发
        self._trans_old = None           # 转场前的旧画面 Surface（cross-fade 用）
        self._chapter = None             # U12：章节/幕间演出卡（黑场 + 标题渐显渐隐）
        # 语音唇形：记录当前配音的起始时刻与总时长
        self._voice_t0 = None
        self._voice_length = 0.0

    # ==================== 对外接口 ====================

    def _font_scale_factor(self) -> float:
        """玩家字号档位倍率（small 0.85 / medium 1.0 / large 1.2）；非法值回落 1.0。"""
        scale = str(self.settings.get("font_scale") or "medium")
        return {"small": 0.85, "medium": 1.0, "large": 1.2}.get(scale, 1.0)

    def _font_size(self, name: str) -> int:
        """config.font 基准（含 ui_scale）再乘玩家档位；行距由同一字号比例自然跟随。"""
        return max(8, int(round(self.config.font(name) * self._font_scale_factor())))

    def _load_fonts(self) -> None:
        """（重）建全部字体对象：启动与 P51 配置热重载改字号 / 换字体时复用。"""
        font_path = None
        custom = self.config.font_file()
        if custom:
            base = self.assets_root or data.game_root()
            cand = custom if os.path.isabs(custom) else os.path.join(base, custom)
            if os.path.isfile(cand):
                font_path = cand
            else:
                print(f"[字体警告] config.font_file 指向的字体不存在：{custom}，回退自动查找",
                      file=sys.stderr)
        if font_path is None:
            try:
                font_path = data.find_cjk_font()
            except data.DataError as e:
                print(f"[字体警告] {e}，回退到默认字体", file=sys.stderr)
                font_path = None
        self._font_path = font_path
        self._font = pygame.font.Font(font_path, self._font_size("body"))
        # UI 层字号：标题大字 / 页面小标题 / 回看与存档行
        self._title_font = pygame.font.Font(font_path, self._font_size("title"))
        self._mid_font = pygame.font.Font(font_path, self._font_size("mid"))
        self._small_font = pygame.font.Font(font_path, self._font_size("small"))
        # P37-T6 字体层级：章节标题 / 选项
        self._heading_font = pygame.font.Font(font_path, self._font_size("heading"))
        self._option_font = pygame.font.Font(font_path, self._font_size("option"))
        # P46 台词富文本：字体簿按 (字号,粗,斜) 缓存，pygame 合成样式无需额外字体文件
        self._font_book = richtext.FontBook(font_path, self._font_size("body"))
        # T8 缓存键含 id(font)：字体对象换了必须清空，否则会命中旧字形的 Surface
        for name in ("_text_cache", "_text_width_cache"):
            cache = getattr(self, name, None)
            if cache is not None:
                cache.clear()

    def apply_config(self, config) -> bool:
        """P51 配置热重载：换配置视图，重算玩家覆盖 / 键位 / 标题 / 字体。

        返回 False = 本次变更不能热应用（画布尺寸变了要重建窗口与 screen），
        由调用方提示玩家重启。
        """
        if tuple(config.canvas_size()) != tuple(self.size):
            return False
        self.config = config
        self.config.apply_player_ui(dict(self.settings.get("ui_geometry") or {}))
        for warning in self.config.warnings:
            print(f"[配置] {warning}", file=sys.stderr)
        try:
            pygame.display.set_caption(self.config.window_title)
        except pygame.error:
            pass
        self._ui_scale = self.config.ui_scale()
        self._keymap = cfgapi.keymap(self.config, self.settings)
        self._load_fonts()
        return True


    def render(self, state: dict, ui_view=None) -> None:
        """画一帧。state 为 Runtime.snapshot() 的 GameState（只读）。

        ui_view：可选参数，UI.view() 的返回值；None 时只画游戏画面，
        playing 模式也不额外绘制，只有 title / menu / slots / settings / backlog 覆盖游戏画面。
        """
        if not isinstance(state, dict):
            state = {}
        self._ui_mode = ui_view.get("mode") if isinstance(ui_view, dict) else None
        self._ui_hits = []  # P31-b：可点区域每帧重建（playing 也要清，避免残留上一界面）
        # P44-D：hover 判定统一用逻辑画布坐标（窗口缩放后仍准确）
        self._mouse_pos = self._to_canvas(pygame.mouse.get_pos())
        dt_ms = min(self._clock.tick(60), 100)  # 帧间隔（钳制，防长时间挂起后打字机跳变）
        self._last_dt_ms = dt_ms               # 主循环用来倒计时 @wait
        # P33-b：窗口可见性自检（最小化/屏幕外 → 恢复置前；1s 节流）
        if time.time() - self._vis_t0 > 1.0:
            self._vis_t0 = time.time()
            self._ensure_window_visible()
        self._restore_persistent_state(state)   # 读档后复原 fg / 镜头 / anim 最终态
        self._update_pending_music()  # P26 T3：淡出到点的待切音乐（CG 分支前也要推进）

        bg = state.get("bg")
        video = state.get("video")
        sprites = state.get("sprites") or []
        history = state.get("history") or []
        pending = state.get("pending_choice")
        characters = state.get("characters") or {}

        # U12：章节卡播放期间独占画面（黑场 + 标题），播完自动恢复
        if self._chapter is not None and self._draw_chapter():
            if isinstance(ui_view, dict) and self._ui_mode not in (None, "playing"):
                self._draw_ui(ui_view)
            self._draw_toast()
            self._present()
            return

        # CG 全屏展示：屏蔽背景/立绘/对话框，只画 CG 大图，UI 层仍可覆盖
        if self._cg_showing is not None:
            finished = isinstance(state, dict) and bool(state.get("finished"))
            self._draw_cg(self._cg_showing, show_hint=not finished)
            self._draw_end_hint(state)
            if isinstance(ui_view, dict) and self._ui_mode not in (None, "playing"):
                self._draw_ui(ui_view)
            self._draw_toast()
            self._present()
            return

        self._update_music(state.get("music"))
        self._update_typewriter(history, dt_ms, pending)
        self._update_choice(pending)
        self._update_voice(history)

        # 0. 时间轴统一推进（P30-C-a）
        #    镜头/转场/立绘补间/停留共用一个时钟；本帧每轨取值函数只跑一次
        #    （含随机的震动依赖此约定），且必须先于合成，立绘补间才没有一帧延迟
        now = self._now_ms()
        self.timeline.tick(now)
        self._update_camera(now)
        self._update_sprite_anim(now)

        # 正在说话的角色（台词打字机未放完时，其立绘切"说话"动画帧组）
        speaking = None
        if history and pending is None and not self.typewriter_complete():
            speaking = history[-1].get("char")

        # 1. 背景+立绘+前景合成到 _scene（镜头变换统一作用于此层）
        #    分层顺序（由底到顶）：bg < sprites（按 z） < fg < overlay（UI 遮罩）
        self._scene.fill((0, 0, 0))
        self._draw_background(bg, video, target=self._scene)
        self._draw_sprites(sprites, speaking, target=self._scene)
        self._draw_fg(target=self._scene)

        # 2. 背景切换检测：有待用转场 → 触发转场；否则走默认淡入
        if bg != self._last_bg:
            self._last_bg = bg
            if self._pending_transition is not None:
                kind, args = self._pending_transition
                self._pending_transition = None
                # 转场进度挂 Timeline 轨（dissolve/wipe/slide 共用一条，t 0~1 线性推进）
                secs = float(args[-1]) if args else self._pacing("dissolve", TRANS_DEFAULT_SECONDS)
                self.timeline.play("transition", secs * 1000, lambda t: t, t0=now,
                                   meta={"kind": kind, "args": args})
                self._trans_old = self._screen.copy()  # 转场前旧画面
                self._fade_t0 = None
            else:
                self.timeline.cancel("transition")
                self._trans_old = None
                # P33：应用 @bg fadein= 传入的一次性淡入时长（缺省 0.3s）
                secs = (self._pacing("scene_fade", FADE_SECONDS)
                        if self._next_bg_fade is None else self._next_bg_fade)
                self._next_bg_fade = None
                self._bg_fade_seconds = secs
                self._fade_t0 = now if secs > 0 else None

        # 3. 把 _scene 经镜头变换 blit 到 screen
        self._blit_scene_to_screen()

        # 4. 转场叠加（dissolve/wipe/slide）或默认淡入
        if self._trans_old is not None:
            self._draw_transition(now)
        else:
            self._draw_fade_overlay(now)

        # P30-S1-3：UI 覆盖态（菜单/读档/设置/画廊/回看）不画对话框与选项，
        # 否则白边与「空格 / 点击 继续」会从半透明遮罩下透出来
        ui_overlay = isinstance(ui_view, dict) and self._ui_mode not in (None, "playing")

        # 5. 对话框 + 打字机文字 / 选择提示
        if not ui_overlay:
            self._draw_dialog(history, characters, pending)
        # 6. 选项列表
        if pending and not ui_overlay:
            self._draw_choices()
        else:
            self._choice_rects = []

        # 7. UI 层：标题 / 菜单 / 存档列表 / 设置 / 回看（覆盖游戏画面；playing 不绘制）
        if ui_overlay:
            self._draw_ui(ui_view)

        # P34-T1：playing 常驻快捷栏（SAVE/LOAD/LOG/AUTO/SKIP/CONFIG；覆盖画面时不画）
        # P44-D：首屏（还没有任何台词）只保留主内容区域，隐藏快捷栏与底部附加 UI
        if not ui_overlay and self._ui_mode == "playing" and history and not self._splash_mode:
            self._draw_quickbar(ui_view)

        # P30-S2-3：终幕停留期间给收尾引导（淡出开始前）
        self._draw_end_hint(state)

        # ⑩ 结尾淡出 overlay（flip 之前画）
        self._draw_ending_fade(now)

        self._draw_toast()
        self._present()


    def handle_input(self) -> dict:
        """收集玩家输入，返回统一动作。

        UI 模式（title/menu/slots/settings/backlog）下把按键翻译成统一键名
        up / down / confirm / back / slot1~slot10（UI 不碰 pygame）。
        playing 与无 ui_view 时返回游戏动作（advance/quit 等），
        只额外把 ↑ 翻译成 backlog、Esc 翻译成 back。
        """
        # 语音自动推进：配音已播完且打字机完成 → 自发一次 advance
        # ⑭ 但旁白（char=None）打字机完后 400ms 内不自动推进，让玩家有节奏读旁白
        if (self._ui_mode in (None, "playing") and self._options is None
                and self._voice_done_pending and not self._voice_busy()
                and self.settings.get("voice_auto_advance") and self.typewriter_complete()
                and not self._has_next_page()):
            # ⑭ 旁白自动推进冷却检查
            cd = self._narration_cooldown_t0
            if cd is not None and self._now_ms() < cd:
                pass  # 冷却未过，不自发 advance
            else:
                self._voice_done_pending = False
                if cd is not None:
                    self._narration_cooldown_t0 = None
                return {"action": "advance"}
        # 无 voice_auto_advance 的纯 auto 驱动也需要旁白节奏差
        if (self._ui_mode in (None, "playing") and self._options is None
                and self._tw_shown >= len(self._tw_text) and self._tw_text):
            cd = self._narration_cooldown_t0
            if cd is not None and self._now_ms() < cd:
                pass  # 冷却未过，等
            elif cd is not None:
                self._narration_cooldown_t0 = None
        action = {"action": "none"}
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                return {"action": "quit"}
            if ev.type == pygame.VIDEORESIZE:
                # P31-a：窗口拖拽缩放（逻辑画布不变）
                self.resize(ev.w, ev.h)
                continue
            cap = self._capture_key_event(ev)
            if cap is not None:
                return cap
            # CG 展示中：空格/回车/点击 → 关闭 CG 并推进剧情
            if self._cg_showing is not None:
                if ev.type == pygame.KEYDOWN and (
                        _ui_key(ev.key, self._keymap) == "confirm" or ev.key == pygame.K_ESCAPE):
                    self._cg_showing = None
                    return {"action": "advance"}
                if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                    self._cg_showing = None
                    return {"action": "advance"}
                continue
            if ev.type == pygame.KEYDOWN:
                # ⑮ F11 切换全屏（所有模式通用）
                if ev.key == pygame.K_F11:
                    self.toggle_fullscreen()
                    continue
                if self._ui_mode not in (None, "playing"):
                    key = _ui_key(ev.key, self._keymap)
                    if key is not None:
                        return {"action": key}
                    continue
                if _ui_key(ev.key, self._keymap) == "back":
                    if self._ui_mode == "playing":
                        return {"action": "back"}
                    return {"action": "quit"}
                act = _ui_key(ev.key, self._keymap)
                if act == "quicksave":
                    return {"action": "quicksave"}
                if self._options is not None:
                    # 选项模式：方向键移动高亮，确认键确认，1-9 直选
                    # ⑤ 锁定期内忽略确认键（方向键仍可用）
                    # t0 = 锁开始生效时间；起始延迟 30ms 已在 t0 里，锁长 250ms
                    t0 = self._choice_lock_t0
                    now = self._now_ms()
                    locked = (t0 is not None and t0 <= now < t0 + 250)
                    if act == "up":
                        self._move_choice(-1)
                    elif act == "down":
                        self._move_choice(1)
                    elif act == "confirm":
                        if locked:
                            continue
                        if self._choice_available(self._choice_index):
                            return {"action": "choose", "index": self._choice_index}
                    elif pygame.K_1 <= ev.key <= pygame.K_9:
                        if locked:
                            continue
                        idx = ev.key - pygame.K_1
                        if self._choice_available(idx):
                            return {"action": "choose", "index": idx}
                else:
                    # P50：Insert / X 键——一键隐藏全部 UI（截图模式），再按恢复
                    # （业界标准：Ren'Py H 键 / 他人世界末日 Insert+X；选项态不隐藏防卡死）
                    if ev.key in (pygame.K_INSERT, pygame.K_x):
                        self._ui_hidden = not self._ui_hidden
                        self._mouse_down = False
                        continue
                    if act == "confirm":
                        action = self._advance_or_reveal()
                    elif act == "up" and self._ui_mode == "playing":
                        return {"action": "backlog"}
            elif ev.type == pygame.MOUSEBUTTONUP and ev.button == 1:
                self._mouse_down = False
                continue
            elif ev.type == pygame.MOUSEMOTION and self._mouse_down:
                # P49：按住拖动（音量滑条连续调节）——仅 UI 模式、且命中滑块才上报
                if self._ui_mode not in (None, "playing"):
                    pos = self._to_canvas(ev.pos)
                    hit = self._ui_hit_at(pos)
                    if hit is not None and hit.get("kind") == "settings_slider":
                        return {"action": "drag", "hit": hit, "pos": pos}
                continue
            elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                self._mouse_down = True
                act = self._mouse_down_action(ev)  # UI 控件 / 选项 / 推进（见 render_window）
                if act is not None:
                    return act
                continue
        return action

    def screenshot(self, path=None) -> str:
        """把当前帧存为 PNG，返回文件路径。path 省略时存 ./screenshots/ 下带时间戳的文件。"""
        if path is None:
            os.makedirs("screenshots", exist_ok=True)
            stamp = time.strftime("%Y%m%d_%H%M%S")
            path = os.path.join("screenshots", f"screenshot_{stamp}.png")
            n = 1
            while os.path.exists(path):  # 同一秒内多次截图不覆盖
                path = os.path.join("screenshots", f"screenshot_{stamp}_{n}.png")
                n += 1
        else:
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)
        pygame.image.save(self._screen, path)
        return path

    # ==================== ⑨ 存档卡片缩略图 ====================

    def save_thumbnail(self, path: str, size=(280, 160)) -> str:
        """⑨ 把当前画面缩成缩略图（280×160）存为 PNG，返回文件路径。

        demo 存档后调此方法生成 saves/thumb_{slot}.png，存档 JSON 里记录路径。"""
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        scaled = pygame.transform.smoothscale(self._screen, size)
        pygame.image.save(scaled, path)
        return path


    def _restore_persistent_state(self, state: dict) -> None:
        """从 GameState 还原持久化展示层状态（fg / zoom / anim 最终态）。

        每帧 render() 开头调用，保证读档后画面立即正确。
        只在 state 明确有该 key 时才覆盖（测试里直接调 renderer.play_fg 绕开
        runtime 路径时 state 没有这些 key，不应被默认值覆盖）。
        """
        # 前景
        if "fg" in state:
            self._fg = state.get("fg")
        # 镜头缩放（zoom 最终值；pan 偏移 runtime 算不出，不进 state）
        if "camera_zoom" in state:
            self._cam_scale = float(state["camera_zoom"])
        # 立绘最终态：只读 Timeline 没在跑的 param
        anim_final = state.get("anim_final") or {}
        for char, finals in anim_final.items():
            disp = self._sprite_anim.setdefault(char, {})
            for param, final in finals.items():
                track_name = f"anim:{char}:{param}"
                if self.timeline.track(track_name) is None:
                    disp[param] = float(final)


    def set_splash(self, flag: bool) -> None:
        """P26 T1：切换序幕模式（True = 隐藏对话框，台词以电影字幕方式显示）。"""
        self._splash_mode = bool(flag)
        if not flag:
            # 退出序幕时清掉序幕残留的展示状态（CG / 转场 / 镜头 / 停留轨）
            self._cg_showing = None
            self._fg = None
            self._pending_transition = None
            self.timeline.cancel("transition")
            self.timeline.cancel("splash")
            self._trans_old = None
            self._pending_music = None


    def _t(self, text: str) -> str:
        """P37-M1：翻译 UI 文案到当前语言（settings.json 的 lang，默认 zh-CN）。"""
        lang = str(self.settings.get("lang", i18n.DEFAULT_LANG))
        return i18n.t(text, lang)


    def close(self) -> None:
        """退出时释放 pygame 资源；未落盘的窗口尺寸在这里补写一次。"""
        if self._window_dirty:
            self._persist_window()
        try:
            if self._audio_ok:
                pygame.mixer.music.stop()
                pygame.mixer.quit()
        except pygame.error:
            pass
        pygame.display.quit()
        pygame.font.quit()

    # ---- auto 测试钩子用的展示状态查询（demo 专用，正常游玩不调用）----

    def _now_ms(self) -> int:
        """当前时刻（毫秒）。独立成方法便于测试替换时间源。"""
        return pygame.time.get_ticks()

    def _detect_tier(self) -> str:
        """设备档位：settings.quality_tier 显式覆盖 > 自动探测（失败回落 mid）。"""
        override = str(self.settings.get("quality_tier") or "auto").strip().lower()
        if override in ("low", "mid", "high"):
            return override
        try:
            from . import capability
            return capability.detect_spec()["tier"]
        except Exception:  # noqa: BLE001 — 探测失败不影响启动，按 mid 处理
            return "mid"

    def _reduce_effects(self) -> bool:
        """低配或玩家/开发者显式要求时，跳过震动/粒子等重效果。"""
        if getattr(self, "_capability_tier", "mid") == "low":
            return True
        return bool(self.settings.get("reduce_effects", False))

    def _pacing(self, name: str, default: float) -> float:
        """取演出节奏默认值（config.json 的 pacing 段）；非法值回落 default。"""
        return self.config.pacing_value(name, default)

    def _ui_int(self, section: str, key: str, default: int, lo: int | None = None,
               hi: int | None = None, scale: bool = True) -> int:
        """读取 UI 布局整数，非法值回落默认并夹到合理区间（配置写错不崩）。

        scale=True（默认）时按 T10 视觉比例换算成画布像素：配置值仍按 720p 基准书写，
        1080p 下自动 ×1.5；纯计数值 / alpha 等不是长度的参数传 scale=False。
        """
        raw = self.config.ui_value(section, key, default) if section else \
            (self.config.data.get("ui") or {}).get(key, default)
        try:
            val = int(raw)
        except (TypeError, ValueError):
            val = int(default)
        if lo is not None:
            val = max(lo, val)
        if hi is not None:
            val = min(hi, val)
        if scale and self._ui_scale != 1.0:
            val = int(round(val * self._ui_scale))
        return val

    def _ui_str(self, section: str, key: str, default: str) -> str:
        raw = self.config.ui_value(section, key, default)
        return str(raw).strip().lower() if raw is not None else default


    def _hovered(self, rect: pygame.Rect) -> bool:
        """鼠标是否悬停在指定逻辑矩形上（用于「仅 hover 显示边框」的统一交互态）。"""
        pos = getattr(self, "_mouse_pos", None)
        return bool(pos) and rect.collidepoint(pos)


# ---- UI 绘制用的小工具 ----
# P30-S2-2：设置行定义与过滤已上收 ui.py（SETTINGS_ITEMS 含 kind/步进），
# renderer 只读 view["items"]，不再各自维护一份清单
# 模块级工具函数（_format_setting/_slot_card_head/_slot_row_text/_clip_text/
# _ui_key/_scale_to_fit/_wrap_text）已迁至 render_utils.py（见文件顶部 import）

