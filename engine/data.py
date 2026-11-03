"""MYONL 资源路径解析 + 设置读写 + 中文字体查找。

零转换铁律：资源就是 images/xxx.png、audio/xxx.ogg、fonts/xxx.ttf 放文件夹里直接读，
禁止任何中间格式 / 转换工具 / 打包流程。
只用 Python 标准库；异常信息用中文。
"""
from __future__ import annotations

import json
import os
import sys

# 内置默认设置
DEFAULT_SETTINGS = {
    "text_speed": 45,     # 打字机速度，字符/秒（M1.5 商业向默认=中档；可三档 20/45/90）
    "bgm_volume": 0.7,    # 音乐音量 0.0~1.0
    "sfx_volume": 0.8,    # 音效音量 0.0~1.0
    "voice_volume": 0.9,      # M1.5：配音音量（独立于音乐/音效）
    "muted": False,           # M1.5：一键静音（保留各项音量数值，取消后恢复）
    "auto_speed": "normal",   # M1.5：AUTO 推进速度 slow/normal/fast（倍率叠在 pacing.auto_advance_ms 上）
    "display_mode": "window", # M1.5：显示模式 window/borderless/fullscreen
    "font_scale": "medium",    # M1.5-B：玩家字号档位 small/medium/large（0.85/1.0/1.2，行距随之等比）
    "dialog_alpha_scale": 1.0,  # U7：玩家可调对话框透明度倍率（1.0=跟随项目 config，不覆盖开发者设定）
    "dialog_offset_y": 0,       # U7：玩家可调对话框纵向位置（像素，0=项目默认）
    "reduce_effects": 0,        # U9：无障碍——减少动效（1 关掉震动/闪烁等重效果）
    "confirm_key": "both",      # U10：确认键方案 both/space/enter（both=空格与回车都可）
    # U10：玩家自定义键位（pygame.key.name 小写名；空串=沿用项目 config 默认）
    "key_up": "", "key_down": "", "key_left": "", "key_right": "",
    "key_confirm": "", "key_back": "",
    "voice_enabled": 1,       # 配音开关：1 开 / 0 关
    "voice_auto_advance": 0,  # 语音播完自动推进：1 开（播完才允许继续并自动推进）/ 0 关
    "splash": 1,              # P26 T1：开场序幕开关：1 开（有 开场.gal 时先播）/ 0 关
    "settings_hidden": [],    # P30-S2-2：设置页显式隐藏项（如 ["voice_enabled"]），list 类型
    "ending_hold_ms": 4000,   # P30-S2-3：终幕画面停留时长（毫秒），到点才淡出回标题
    "window_size": [1280, 720],  # P31-a：窗口宽高（可拖拽缩放，跨启动记忆）
    "fullscreen": False,         # P31-a：全屏开关（F11 切换后记忆）
    "lang": "zh-CN",             # P37-M1：界面语言（zh-CN / en-US），老配置默认中文
    # 玩家侧「界面」：快捷栏显隐 / 桌宠。默认保持原行为（快捷栏开、桌宠关）
    "quickbar_enabled": 1,    # 1 显示快捷栏 / 0 隐藏（仍可用键盘快捷键）
    "pet_enabled": 0,         # 1 游戏运行时拉起桌宠 / 0 关闭（默认关）
    # P40：数据目录策略（存档/设置/未来自定义数据落点）
    #   "" / "game"     → 随游戏目录（删游戏 = 数据一并删干净，默认）
    #   "appdata"       → %APPDATA%/Moyul/<游戏名>（卸载/删游戏后数据保留）
    #   绝对路径        → 开发者自定义数据位置
    "data_dir": "",
}

# settings.json 中允许出现的 list 类型键（load 时按原样保留，不做数值校验）
_LIST_SETTING_KEYS = ("settings_hidden", "window_size")

# settings.json 中允许出现的 bool 类型键（load 时按原样保留）
# splash：模板 settings.json 写 True/False（P26 序幕开关），与默认 int 1/0 语义等价，一并放行
_BOOL_SETTING_KEYS = ("fullscreen", "splash", "muted")

# settings.json 中允许出现的 str 类型键（load 时按原样保留）
# P49：lang（语言切换）/ data_dir / title 等自定义键都是字符串，此前被类型校验
# 静默忽略——切语言保存后重启不生效（隐藏 bug），统一放行字符串键。
_STR_SETTING_KEYS = ("lang", "data_dir", "title", "icon_title", "display_mode", "auto_speed",
                     "quality_tier", "font_scale", "confirm_key",
                     "key_up", "key_down", "key_left", "key_right", "key_confirm", "key_back")

# 音频 / 字体 / 图片允许的后缀（查找顺序即优先级）
_IMAGE_EXTS = (".png", ".jpg")  # P29 A1：优先 png，找不到自动回退 jpg（旧素材零影响）
_AUDIO_EXTS = (".ogg", ".mp3", ".wav")
_FONT_EXTS = (".ttf", ".ttc", ".otf")

# P28 E3：画廊幻灯片配置（游戏目录下，缺省=单图旧行为）
GALLERY_CONFIG_NAME = "gallery_config.json"

# Windows 系统中文字体候选（按优先级）
_CJK_FONT_CANDIDATES = (
    "msyh.ttc",       # 微软雅黑
    "msyh.ttf",
    "simhei.ttf",     # 黑体
    "simsun.ttc",     # 宋体
    "simkai.ttf",     # 楷体
    "Deng.ttf",       # 等线
    "STHeiti Light.ttc",
    "PingFang.ttc",
    "NotoSansCJK-Regular.ttc",
)


class DataError(Exception):
    """资源/设置错误。中文提示。"""


def game_root() -> str:
    """游戏根目录：打包后（PyInstaller onedir）= exe 所在目录；开发时 = 当前工作目录。

    资源（images/ audio/ fonts/）相对它解析；数据（saves/ settings）按 data_dir 策略
    落 data_root()，默认随游戏根（删游戏=删干净），可选 AppData（删游戏数据保留）。
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.getcwd()


def _read_data_dir(root: str) -> str:
    """只读 root/settings.json 里的 data_dir 键（不加载全部设置，避免循环依赖）。"""
    p = os.path.join(root, "settings.json")
    if os.path.isfile(p):
        try:
            with open(p, "r", encoding="utf-8-sig") as f:
                d = json.load(f)
            if isinstance(d, dict) and isinstance(d.get("data_dir"), str):
                return d["data_dir"].strip()
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            pass
    return ""


def data_root(root: str | None = None) -> str:
    """数据根目录（存档/设置/后续扩展数据落点），按 settings.data_dir 策略解析。

    - "" / "game"（默认）→ 随游戏目录（删除游戏 = 数据删干净）
    - "appdata"           → %APPDATA%/Moyul/<游戏名>（删除游戏后数据保留）
    - 绝对路径            → 开发者自定义数据位置
    """
    root = root if root is not None else game_root()
    mode = _read_data_dir(root)
    if mode in ("", "game"):
        return root
    if mode.lower() == "appdata":
        base = os.environ.get("APPDATA") or os.path.join(
            os.path.expanduser("~"), "AppData", "Roaming")
        game_name = os.path.basename(os.path.abspath(root))
        return os.path.join(base, "Moyul", game_name)
    if os.path.isabs(mode):
        return mode
    return root


def engine_data_root() -> str:
    """引擎级数据根（编辑器配置/插件/mod/缓存），独立于安装目录与游戏。

    删掉引擎安装文件夹后重新下载，数据仍在（本地保留、无需注册），自然接回。
    结构（预留）：
      %APPDATA%/Moyul/editor/    编辑器配置（.editor_config 等，P41-T2 迁移）
      %APPDATA%/Moyul/plugins/   插件（未来插件生态，目录先行）
      %APPDATA%/Moyul/mods/      mod（未来 mod 生态，目录先行）
      %APPDATA%/Moyul/cache/     缓存（缩略图/临时文件等）
    """
    base = os.environ.get("APPDATA") or os.path.join(
        os.path.expanduser("~"), "AppData", "Roaming")
    return os.path.join(base, "Moyul")


def _resolve(root, subdir, name, exts, kind) -> str:
    """通用资源解析：root/subdir/name + 候选后缀，逐个试存在性。"""
    if not name or not str(name).strip():
        raise DataError(f"{kind}名为空，无法定位资源文件")
    name = str(name).strip()
    base_dir = os.path.join(root, subdir)
    for ext in exts:
        path = os.path.join(base_dir, name + ext)
        if os.path.isfile(path):
            return path
    tried = "、".join(name + e for e in exts)
    raise DataError(f"找不到{kind}文件：{os.path.join(base_dir, name)}（尝试过：{tried}）")


def resolve_image(root, name) -> str:
    """root/images/{name}.png（缺 png 回退 .jpg），缺失抛 DataError。"""
    return _resolve(root, "images", name, _IMAGE_EXTS, "图片")


def resolve_audio(root, name) -> str:
    """root/audio/{name}.ogg（兼容 .mp3/.wav），缺失抛 DataError。"""
    return _resolve(root, "audio", name, _AUDIO_EXTS, "音频")


def resolve_font(root, name) -> str:
    """root/fonts/{name}.ttf/.ttc，缺失抛 DataError。"""
    return _resolve(root, "fonts", name, _FONT_EXTS, "字体")


def image_hint(name) -> str:
    """P29 A4：缺失提示用的图片候选文案，随 _IMAGE_EXTS 自动同步。

    如 images/x.png 或 images/x.jpg——素材转 JPG 后预检不会误报。
    """
    return " 或 ".join(f"images/{name}{ext}" for ext in _IMAGE_EXTS)


def audio_hint(name) -> str:
    """P29 A4：缺失提示用的音频候选文案，随 _AUDIO_EXTS 自动同步。"""
    return " 或 ".join(f"audio/{name}{ext}" for ext in _AUDIO_EXTS)


def find_cjk_font(root=None) -> str:
    """查找中文字体：游戏目录 fonts/ 优先，其次系统字体；都找不到抛 DataError。

    打包发布时把中文字体放进游戏目录的 fonts/，可保证别的机器上中文不乱码。
    """
    font_dir = os.path.join(root if root is not None else game_root(), "fonts")
    if os.path.isdir(font_dir):
        for name in sorted(os.listdir(font_dir)):
            path = os.path.join(font_dir, name)
            if os.path.isfile(path) and name.lower().endswith(_FONT_EXTS):
                return path
    candidates = []
    if sys.platform.startswith("win"):
        windir = os.environ.get("WINDIR", r"C:\Windows")
        fonts_dir = os.path.join(windir, "Fonts")
        candidates = [os.path.join(fonts_dir, f) for f in _CJK_FONT_CANDIDATES]
    elif sys.platform == "darwin":
        candidates = [
            "/System/Library/Fonts/PingFang.ttc",
            "/System/Library/Fonts/STHeiti Light.ttc",
            "/Library/Fonts/Arial Unicode.ttf",
        ]
    else:  # Linux 等
        candidates = [
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
            "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
        ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    raise DataError("找不到系统中文字体，中文将无法显示")


def _settings_path(path=None) -> str:
    """设置文件路径：显式 path 直接用；缺省时按 data_dir 策略落数据根。

    data_dir 非空（appdata/自定义）且数据根已有 settings.json → 用数据根的，
    保证「删游戏数据保留」时设置也从数据根读写。
    """
    if path is not None:
        return path
    root = game_root()
    if _read_data_dir(root) not in ("", "game"):
        d = data_root(root)
        dp = os.path.join(d, "settings.json")
        if os.path.isfile(dp):
            return dp
    return os.path.join(root, "settings.json")


def load_settings(path=None) -> dict:
    """读 settings.json；文件不存在或内容损坏时返回内置默认（不崩）。"""
    p = _settings_path(path)
    settings = dict(DEFAULT_SETTINGS)
    if not os.path.isfile(p):
        return settings
    try:
        with open(p, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        # 损坏的设置文件不阻塞启动，回退默认
        return settings
    if isinstance(data, dict):
        for key, value in data.items():
            if key not in DEFAULT_SETTINGS:
                # P31-c：保留引擎未声明的自定义键（如 title / title_text_y），否则存一次就丢
                settings[key] = value
                continue
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                settings[key] = value
            elif key in _LIST_SETTING_KEYS and isinstance(value, list):
                # P30-S2-2：settings_hidden 列表原样保留
                settings[key] = value
            elif key in _BOOL_SETTING_KEYS and isinstance(value, bool):
                # P31-a：fullscreen 布尔原样保留（数值型分支会把它当 0/1，故单列）
                settings[key] = value
            elif key in _STR_SETTING_KEYS and isinstance(value, str):
                # P49：lang/data_dir/title 等字符串键原样保留（切语言后重启才生效）
                settings[key] = value
            else:
                print(f'[设置警告] 键 "{key}" 的值类型不对（{type(value).__name__}），已忽略',
                      file=sys.stderr)
    return settings


def save_settings(settings, path=None) -> None:
    """写 settings.json（UTF-8，保留中文；先写临时文件再原子替换，避免写一半损坏）。

    path 缺省时：data_dir 非空 → 写入数据根（自动建目录）；否则写游戏根 settings.json。
    """
    p = _settings_path(path)
    if path is None:
        root = game_root()
        if _read_data_dir(root) not in ("", "game"):
            d = data_root(root)
            os.makedirs(d, exist_ok=True)
            p = os.path.join(d, "settings.json")
    data = dict(DEFAULT_SETTINGS)
    if isinstance(settings, dict):
        # P31-c：连同引擎未知的键一起落盘（原来只写 DEFAULT_SETTINGS 里有的键，
        # 导致改一次设置/拖一次窗口就把 title 之类的项目自定义键抹掉）
        data.update(settings)
    tmp = p + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, p)
    except OSError:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass
        raise


def load_gallery_config(root=None) -> list[dict]:
    """P28 E1/E3：读画廊配置，返回固定格子清单 [{"name": 格名, "images": [图名...]}]。

    - 文件缺省 / 损坏 / 格式不对 → 返回 []（画廊保持旧的"只显示已解锁项"行为）
    - 每格的值可以是图片名列表（幻灯片）或单个图片名（单图）
    - 下划线开头的键视为备注字段，不参与格子
    """
    base = root if root is not None else game_root()
    path = os.path.join(base, GALLERY_CONFIG_NAME)
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            raw = json.load(f)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as e:
        print(f"[画廊警告] {GALLERY_CONFIG_NAME} 读取失败，已按单图模式显示：{e}", file=sys.stderr)
        return []
    if not isinstance(raw, dict):
        print(f"[画廊警告] {GALLERY_CONFIG_NAME} 顶层应为对象，已按单图模式显示", file=sys.stderr)
        return []
    cells = []
    for name, value in raw.items():
        key = str(name).strip()
        if not key or key.startswith("_"):
            continue
        require: list[str] = []
        if isinstance(value, str):
            images = [value.strip()] if value.strip() else []
        elif isinstance(value, list):
            images = [str(v).strip() for v in value if isinstance(v, str) and v.strip()]
        elif isinstance(value, dict):
            # P33：对象格式 {"images": [...], "require": [CG 名...]}——require 全部解锁才显示该格
            imgs = value.get("images")
            if isinstance(imgs, str):
                images = [imgs.strip()] if imgs.strip() else []
            elif isinstance(imgs, list):
                images = [str(v).strip() for v in imgs if isinstance(v, str) and v.strip()]
            else:
                continue  # 缺 images 视为非法格
            if isinstance(value.get("require"), list):
                require = [str(r).strip() for r in value["require"]
                           if isinstance(r, str) and r.strip()]
        else:
            continue  # 非法值跳过，不影响其它格子
        cells.append({"name": key, "images": images, "require": require})
    return cells
