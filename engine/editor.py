"""MYONL 本地 Web 编辑器。

完全离线、只绑 127.0.0.1 的 HTTP 服务：左写 .gal 剧本，右实时预览，
语法错误行内高亮、自动补全、一键弹窗口跑 demo。

只用 Python 标准库（http.server / threading / subprocess / os / json / tempfile）。
只 import 调用引擎核心（parser / runtime / renderer / data / demo / cli），绝不修改。

P17：多文件工程——文件树/读写/新建章节/跨文件标签大纲/include 跳转/场景时间线/场景状态。
路由集中在 _EditorHandler._ROUTES 注册表，每路由一个方法，do_GET/do_POST 只做分发。

启动：
    py -m engine.editor [--port 8000] [--script 剧本.gal]
"""
from __future__ import annotations

import base64
import binascii
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

from . import packaging
from .newgame import create_game
from . import characters as characters_api
from .parser import GalSyntaxError, dump_text, parse_file, parse_text
from .sdl_env import dummy_video

# 桌宠（实验功能）：编辑器内「打开/关闭」一个独立的 Mooki 桌宠进程
_PET_LOCK = threading.Lock()
_PET_PROC: subprocess.Popen | None = None


def _demo_worker_entry() -> None:
    """打包形态下的 demo 启动器入口（A3 修复）。

    PyInstaller 冻结后 sys.executable 指向 editor.exe 自身，`python -m engine.demo`
    无从谈起；这里在导入期截获特殊参数，把 editor.exe 变身 demo 主循环进程：
        editor.exe --demo-worker <剧本.gal> --assets <资源根>
    跑完（窗口关闭）顺手删掉编辑器生成的临时剧本，然后退出，绝不进编辑器逻辑。
    非冻结（源码运行）或无此参数时立即返回，零副作用。
    """
    if not getattr(sys, "frozen", False):
        return
    argv = sys.argv[1:]
    if not argv or argv[0] != "--demo-worker":
        return
    from . import demo
    script = argv[1] if len(argv) > 1 and not argv[1].startswith("-") else ""
    try:
        rc = demo.main(argv[1:])
    finally:
        if script and os.path.basename(script).startswith("tmp"):
            try:
                os.unlink(script)
            except OSError:
                pass
    sys.exit(rc)


_demo_worker_entry()


def _demo_spawn(tmp_path: str, project_root: str):
    """构造「▶ 运行」的子进程命令与环境（A3 修复）。

    返回 (cmd, env)。两个历史坑：
    1. 源码形态 cwd=工程目录时 `python -m engine.demo` 找不到 engine 包，
       子进程秒退且 stdout/stderr 被吞，表现为「进程 CPU 恒 0.296 不增长」；
       这里把 engine 包所在仓库根注入 PYTHONPATH，无论 cwd 在哪都能 import。
    2. 冻结形态 sys.executable 是 editor.exe，改用 --demo-worker 重启自身。
    """
    env = dict(os.environ)
    if getattr(sys, "frozen", False):
        return [sys.executable, "--demo-worker", tmp_path,
                "--assets", project_root], env
    pkg_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env["PYTHONPATH"] = pkg_root + os.pathsep + env.get("PYTHONPATH", "")
    return [sys.executable, "-m", "engine.demo", tmp_path,
            "--assets", project_root], env


# 全部支持的指令名（自动补全候选）
_DIRECTIVES = [
    "@character", "@bg", "@music", "@sfx", "@voice", "@video", "@show", "@hide",
    "@choice:", "@label", "@jump", "@if", "@elif", "@else:", "@set", "@end", "@include",
    "@chapter",
]

# 扫描剧本提取角色/标签/变量名
_RE_CHARACTER = re.compile(r"^@character\s+(\S+)", re.MULTILINE)
_RE_LABEL = re.compile(r"^@label\s+(\S+)", re.MULTILINE)
_RE_SET_VAR = re.compile(r"^@set\s+(\S+)\s*[+\-]?=", re.MULTILINE)

# 预览串行锁：pygame 非线程安全，同一时刻只跑一次预览渲染
_preview_lock = threading.Lock()


def _collect_symbols(text: str) -> dict:
    """从剧本文本扫描已定义的角色名 / 标签名 / 变量名。"""
    return {
        "characters": _RE_CHARACTER.findall(text or ""),
        "labels": _RE_LABEL.findall(text or ""),
        "vars": _RE_SET_VAR.findall(text or ""),
    }


def _completions(line: str, full_text: str = "") -> list:
    """根据当前行 + 全文给出补全候选（前缀匹配，不区分大小写）。"""
    line = line or ""
    # 当前正在输入的 token：取最后一段非空白
    token = ""
    parts = line.rsplit(None, 1)
    if parts:
        token = parts[-1].lstrip("@")
    syms = _collect_symbols(full_text or line)
    candidates: list = []
    # 指令名：去掉前缀 @ 后做匹配
    for d in _DIRECTIVES:
        name = d[1:]
        if not token or name.lower().startswith(token.lower()):
            candidates.append(d)
    # 角色名 / 标签名 / 变量名
    for n in syms["characters"] + syms["labels"] + syms["vars"]:
        if not token or n.lower().startswith(token.lower()):
            candidates.append(n)
    # 去重保序
    seen = set()
    out = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


@dummy_video
def _preview_png(script_path: str, assets_root: str, max_frames: int = 30) -> bytes:
    """无窗口跑剧本 auto 钩子，返回当前帧 PNG bytes。

    用 dummy 视频驱动，复用 Runtime + Renderer（demo.run 内部会关闭 Renderer，
    无法取到截图，故在此自行实现 auto 循环）。pygame 非线程安全，调用方需持锁。
    dummy_video 只在本函数内生效，退出即恢复环境——否则「运行」子进程会继承 dummy。
    """
    from .renderer import Renderer
    from .runtime import Runtime

    rt = Runtime()
    ren = Renderer(assets_root=assets_root)  # T10：画布尺寸从 config.json 读取
    png_path = ""
    try:
        rt.load(script_path)
        frames = 0
        while True:
            state = rt.snapshot()
            ren.render(state)
            if state.get("finished"):
                break
            pc = state.get("pending_choice")
            if pc:
                chosen = False
                for i, o in enumerate(pc.get("options") or []):
                    if o.get("available"):
                        rt.choose(i)
                        chosen = True
                        break
                if not chosen:
                    break  # 全不可选：停在当前帧
            else:
                ren.reveal_all()
                ev = rt.step()
                if ev and ev.get("type") == "sfx":
                    ren.play_sfx(ev.get("sound"))
            frames += 1
            if max_frames is not None and frames >= max_frames:
                break
        # 最后再画一帧确保画面与状态一致
        ren.render(rt.snapshot())
        png_path = ren.screenshot()
        with open(png_path, "rb") as f:
            return f.read()
    finally:
        ren.close()
        # 清理截图临时文件
        if png_path and os.path.exists(png_path):
            try:
                os.remove(png_path)
            except OSError:
                pass


def _safe_within(root: str, target: str) -> str:
    """把 target 解析到 root 下的绝对路径；若越界则抛 ValueError。"""
    root_real = os.path.realpath(root)
    candidate = os.path.realpath(os.path.join(root_real, target)) if not os.path.isabs(target) \
        else os.path.realpath(target)
    if candidate != root_real and not candidate.startswith(root_real + os.sep):
        raise ValueError(f"路径越界：{target}")
    return candidate


# ==================== P20 配置与数据目录（只追加，核心零改动） ====================
_EDITOR_CONFIG = ".editor_config.json"


def _editor_front_dir() -> str:
    """编辑器前端目录：源码运行时是仓库 editor/；PyInstaller 打包后在 _MEIPASS/editor。"""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return os.path.join(base, "editor")
    return os.path.realpath(os.path.join(os.path.dirname(__file__), "..", "editor"))


# ==================== M1.5：内嵌教程 / 说明书（边写边看） ====================
# 只读内置 md：id 是固定白名单（不接受用户路径，天然无穿越）；打包后在 _MEIPASS/docs。
_HELP_DOCS = (
    ("quickstart", "快速上手", "快速上手.md"),
    ("dev-guide", "开发者使用指南", "开发者使用指南.md"),
    ("assets", "素材导入指南", "素材导入指南.md"),
    ("engine-spec", "引擎规格（engine_spec）", "engine_spec.md"),
    ("plugins", "插件开发指南", "插件开发指南.md"),
    ("packaging", "打包使用指南", "打包使用指南.md"),
)


def _docs_dir() -> str:
    """教程文档目录：源码运行是仓库 docs/；PyInstaller 打包后是 _MEIPASS/docs。"""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return os.path.join(base, "docs")
    return os.path.realpath(os.path.join(os.path.dirname(__file__), "..", "docs"))


def _read_help_doc(doc_id: str):
    """按白名单 id 读教程，返回 (title, text)；不存在返回 None。"""
    for key, title, filename in _HELP_DOCS:
        if key != doc_id:
            continue
        path = os.path.join(_docs_dir(), filename)
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                return title, f.read()
        except OSError:
            return None
    return None


def _load_editor_config(root: str) -> dict:
    """读工程内 .editor_config.json；缺失/损坏一律返回空 dict（不阻断启动）。"""
    try:
        with open(os.path.join(root, _EDITOR_CONFIG), "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_editor_config(root: str, data: dict) -> str:
    """配置写回工程根：.editor_config.json 跟随工程文件夹整体移动。"""
    path = os.path.join(root, _EDITOR_CONFIG)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return path


def _load_project_config(root: str) -> dict:
    """读工程 config.json（只读游戏配置，非 .editor_config.json）；缺失/损坏返回 {}。"""
    try:
        with open(os.path.join(root, "config.json"), "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_project_config(root: str, data: dict) -> str:
    """写工程 config.json（保留换行风格；失败抛 OSError 由调用方处理）。"""
    path = os.path.join(root, "config.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return path


# UI 设计页「界面开关」：写到项目 settings.json，作为玩家默认值
_UI_INTERFACE_KEYS = ("quickbar_enabled", "pet_enabled")


def _as_switch(value) -> int:
    """开关值统一成 0/1：兼容 true/1/"1"/"on" 与 false/0/"0"/"off"。"""
    if isinstance(value, str):
        return 0 if value.strip().lower() in ("", "0", "false", "no", "off") else 1
    return 1 if value else 0


def _interface_settings(root: str) -> dict:
    """读项目 settings.json 的界面开关；缺省回落引擎默认（快捷栏开 / 桌宠关）。"""
    from .data import DEFAULT_SETTINGS, load_settings

    st = load_settings(os.path.join(root, "settings.json"))
    return {k: _as_switch(st.get(k, DEFAULT_SETTINGS.get(k))) for k in _UI_INTERFACE_KEYS}


def _save_interface_settings(root: str, patch: dict) -> str:
    """把界面开关写进项目 settings.json（作者/玩家其余设置键原样保留）。"""
    from .data import load_settings, save_settings

    path = os.path.join(root, "settings.json")
    st = load_settings(path)
    for k in _UI_INTERFACE_KEYS:
        if k in patch:
            st[k] = _as_switch(patch.get(k))
    save_settings(st, path)
    return path


@dummy_video
def _ui_design_png(assets_root: str, ui_patch: dict, dlg_patch: dict,
                   font_patch: dict | None = None,
                   lh_patch: dict | None = None,
                   scene: str = "dialog",
                   theme_patch: dict | None = None,
                   font_file: str = "",
                   interface_patch: dict | None = None) -> bytes:
    """渲染一帧 UI 设计预览：纯色背景 + 一句台词 + 对话框（带指定几何/像素化）。

    复用 Renderer 的真实绘制路径；玩家级覆盖（ui_geometry）与 P51 引擎默认
    一起参与渲染，不改动磁盘上的 config.json。B2：字号 / 行距补丁同样参与预览。
    P52：scene 支持 dialog（默认）/ choices / quickbar / menu / settings——
    预览对应组的真实绘制路径（选项列表 / 快捷栏 / 游戏内菜单 / 设置页）。
    dummy_video 退出即恢复环境，不影响之后 spawn 的运行窗口。
    """
    from .config import DEFAULTS as _CFG_DEFAULTS
    from .renderer import Renderer

    ren = Renderer(assets_root=assets_root)  # T10：画布尺寸从 config.json 读取
    png_path = ""
    try:
        # P51：先把预览补丁合进配置视图（引擎默认 ← config.json ← 预览覆盖）
        ren.config.apply_player_ui(dlg_patch)
        ui_cfg = ren.config.data.setdefault("ui", {})
        for k, v in ui_patch.items():
            ui_cfg[k] = v
        # P52：嵌套组（choices/quickbar/menu/settings）合并进 ui 段
        for name in ("choices", "quickbar", "menu", "settings"):
            sec = ui_patch.get(name)
            if isinstance(sec, dict):
                cur = dict(ui_cfg.get(name) or {})
                cur.update(sec)
                ui_cfg[name] = cur
        # 2026-11-02 配色面板：主题色补丁参与预览（不改磁盘 config）
        if theme_patch:
            ren.config.data.setdefault("theme", {}).update(theme_patch)
        # B2：字号补丁 → 重建字体；行距补丁 → 绘制时生效
        if font_patch:
            ren.config.data.setdefault("font", {}).update(font_patch)
            ren._load_fonts()
        # 自定义字体：预览也走真实字体解析（相对项目根），看不到就回落自动查找
        if font_file:
            ren.config.data["font_file"] = font_file
            ren._load_fonts()
        if lh_patch:
            ren.config.data.setdefault("line_height", {}).update(lh_patch)
        # 界面开关：预览按面板上的选择走（快捷栏关掉时预览里也不画）
        if interface_patch and "quickbar_enabled" in interface_patch:
            ren.settings["quickbar_enabled"] = _as_switch(
                interface_patch.get("quickbar_enabled"))
        # 画一帧稳定的 UI 预览：深色纯底 + 名字 + 台词
        ren._screen.fill((30, 32, 44))
        text = "这是 UI 设计预览：调整圆角、位置与大小，右侧实时显示。"
        hist = [{"char": "林晚", "text": text}]
        chars = {"林晚": {"color": (255, 196, 120), "kind": "default"}}
        ren._tw_text = text
        ren._tw_shown = float(len(text))
        ren._draw_dialog(hist, chars, pending=False)
        # P52：按场景叠画对应 UI 组（全部走真实绘制路径）
        if scene == "choices":
            ren._options = [{"text": "去海边走走", "available": True},
                            {"text": "留在站台", "available": True},
                            {"text": "问她叫什么名字", "available": True}]
            ren._choice_index = 0
            ren._choice_rects = []
            ren._draw_choices()
        elif scene == "quickbar":
            ren._mouse_pos = (ren.size[0] - 60, ren.size[1] - 20)  # 让快捷栏显现
            ren._draw_quickbar({"quickbar": {
                "labels": ["AUTO", "SKIP", "SAVE", "LOAD", "SET", "BACKLOG"],
                "auto": False, "skip": False, "skip_allowed": True}})
        elif scene == "menu":
            ren._draw_menu({"items": [
                {"text": "继续游戏", "available": True},
                {"text": "保存", "available": True},
                {"text": "读取", "available": True},
                {"text": "设置", "available": True},
                {"text": "回到标题", "available": True},
            ], "cursor": 0})
        elif scene == "settings":
            ren._draw_settings({"items": [
                {"key": "text_speed", "label": "文字速度", "group": "基础",
                 "kind": "slider", "value": 60},
                {"key": "auto_advance", "label": "自动推进", "group": "基础",
                 "kind": "slider", "value": 40},
                {"key": "volume", "label": "音量", "group": "声音",
                 "kind": "slider", "value": 70},
                {"key": "window_size", "label": "窗口尺寸", "group": "显示",
                 "kind": "choice", "value": "1280×720"},
            ], "cursor": 0, "settings": {}, "settings_tab": 0})
        png_path = ren.screenshot()
        with open(png_path, "rb") as f:
            return f.read()
    finally:
        ren.close()
        if png_path and os.path.exists(png_path):
            try:
                os.remove(png_path)
            except OSError:
                pass


def _default_project(cwd: str) -> str:
    """未显式指定 --project 时：优先用当前目录配置里的 last_project（相对路径）。"""
    cfg = _load_editor_config(cwd)
    last = cfg.get("last_project")
    if isinstance(last, str) and last:
        candidate = os.path.realpath(os.path.join(cwd, last))
        if os.path.isdir(candidate):
            return candidate
    return os.path.realpath(cwd)


def _default_script(root: str) -> str:
    """工程的默认剧本：script.gal 存在则用它，否则用第一个 .gal。"""
    p = os.path.join(root, "script.gal")
    if os.path.isfile(p):
        return p
    files = _list_gal_files(root)
    return os.path.join(root, files[0].replace("/", os.sep)) if files else p


# ==================== P12 素材库（只追加，核心零改动） ====================
# 素材目录约定：images/（背景立绘） images/videos/（帧序列） images/anims/（动画帧）
#              audio/（音乐/音效/配音） fonts/（字体）
# 只 stat 文件名、不读内容（20GB 项目秒开，P11 资源管理原则）
_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")
_AUDIO_EXTS = (".wav", ".ogg", ".mp3")
_FONT_EXTS = (".ttf", ".otf")
_FRAME_SEQ = re.compile(r"^(.*)_\d{3}$")              # 帧序列命名：名称_001.png
_ASSET_NAME = re.compile(r"^[0-9A-Za-z_一-鿿]+$")       # 素材名白名单：中文/字母/数字/下划线
_IMPORT_NAME = re.compile(r"^[0-9A-Za-z_一-鿿]+\.[A-Za-z0-9]+$")  # 导入文件名：白名单主体 + 扩展名
_IMPORT_MAX_BYTES = 64 * 1024 * 1024                   # 单文件上限 64MB（解码后）
_IMPORT_DIRS = {"images": "images", "audio": "audio", "fonts": "fonts"}  # 可导入类别 → 目录
_IMPORT_EXTS = {"images": _IMAGE_EXTS, "audio": _AUDIO_EXTS, "fonts": _FONT_EXTS}
_EXEC_EXTS = {".exe", ".py", ".sh", ".bat", ".cmd", ".com", ".dll", ".msi", ".ps1"}
_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
         ".webp": "image/webp", ".wav": "audio/wav", ".ogg": "audio/ogg",
         ".mp3": "audio/mpeg", ".ttf": "font/ttf", ".otf": "font/otf"}

# 行首指令 → 补全联动的素材类别
_ASSET_COMPLETE = [
    (re.compile(r"^@bg\s"), "images"),
    (re.compile(r"^@video\s"), "videos"),
    (re.compile(r"^@music\s"), "audio"),
    (re.compile(r"^@sfx\s"), "audio"),
    (re.compile(r"^@voice\s"), "audio"),
]
_SHOW_EXPR = re.compile(r"^@show\s+(\S+)\s")  # @show 已到表情参数位置


def _list_asset_names(root: str, subdir: str, exts, strip_seq: bool = False) -> list:
    """列出子目录素材名（去扩展名；strip_seq 时按 _001 规则去编号）。缺目录 → 空列表。"""
    d = os.path.join(root, subdir)
    try:
        entries = os.listdir(d)
    except OSError:
        return []
    names = []
    for fn in entries:
        if not os.path.isfile(os.path.join(d, fn)):
            continue
        stem, ext = os.path.splitext(fn)
        if ext.lower() not in exts:
            continue
        if strip_seq:
            m = _FRAME_SEQ.match(stem)
            if m:
                stem = m.group(1)
        if stem and stem not in names:
            names.append(stem)
    return sorted(names)


def _scan_assets(root: str) -> dict:
    """素材清单：只列文件名（去扩展名），不读文件内容。"""
    return {
        "images": _list_asset_names(root, "images", _IMAGE_EXTS),
        "videos": _list_asset_names(root, os.path.join("images", "videos"),
                                    _IMAGE_EXTS, strip_seq=True),
        "anims": _list_asset_names(root, os.path.join("images", "anims"),
                                   _IMAGE_EXTS, strip_seq=True),
        "audio": _list_asset_names(root, "audio", _AUDIO_EXTS),
        "fonts": _list_asset_names(root, "fonts", _FONT_EXTS),
    }


def _find_asset_file(root: str, category: str, name: str) -> str | None:
    """按类别与素材名定位实际文件（videos/anims 取首帧做缩略图）；找不到返回 None。"""
    if category == "images":
        d, pats = os.path.join(root, "images"), [name + e for e in _IMAGE_EXTS]
    elif category == "videos":
        d = os.path.join(root, "images", "videos")
        pats = [f"{name}_001{e}" for e in (".png", ".webp")]
    elif category == "anims":
        d = os.path.join(root, "images", "anims")
        pats = [f"{name}_001{e}" for e in (".png", ".webp")]
    elif category == "audio":
        d, pats = os.path.join(root, "audio"), [name + e for e in _AUDIO_EXTS]
    elif category == "fonts":
        d, pats = os.path.join(root, "fonts"), [name + e for e in _FONT_EXTS]
    else:
        return None
    for fn in pats:
        p = os.path.join(d, fn)
        if os.path.isfile(p):
            return p
    return None


def _asset_completions(line: str, assets: dict) -> list:
    """按行首指令给出素材候选；@show 在表情位给出「角色_」前缀的表情后缀。"""
    for pat, cat in _ASSET_COMPLETE:
        if pat.search(line):
            return list(assets.get(cat, []))
    m = _SHOW_EXPR.search(line)
    if m:
        prefix = m.group(1) + "_"
        return [n[len(prefix):] for n in assets.get("images", []) if n.startswith(prefix)]
    return []


def _tail_token(line: str) -> str:
    """正在输入的素材名片段；行尾空白或刚写完指令名时为空串。"""
    if not line or line[-1] in " \t":
        return ""
    parts = line.split()
    return parts[-1] if len(parts) > 1 else ""


def _save_import(root: str, category: str, filename: str, data_b64: str,
                 overwrite: bool = False) -> dict:
    """校验并归档导入素材；一律返回 dict（不抛异常，错误走 ok:False 中文消息）。

    overwrite=False（默认）：同名自动加 _1/_2 后缀，不覆盖已有素材；
    overwrite=True：覆盖同名文件（前端三选「覆盖」时使用）。
    """
    if category not in _IMPORT_DIRS:
        return {"ok": False,
                "message": f"不支持的素材类别：{category}（支持 images / audio / fonts）"}
    if not isinstance(filename, str) or not filename:
        return {"ok": False, "message": "文件名不能为空"}
    if ".." in filename or "/" in filename or "\\" in filename:
        return {"ok": False, "message": "文件名不能包含路径（不允许 .. / \\ 等）"}
    if not _IMPORT_NAME.fullmatch(filename):
        return {"ok": False, "message": "文件名只支持中文/字母/数字/下划线，加扩展名"}
    stem, ext = os.path.splitext(filename)
    ext = ext.lower()
    if ext in _EXEC_EXTS:
        return {"ok": False, "message": f"不允许导入可执行文件（{ext}）"}
    if ext not in _IMPORT_EXTS[category]:
        exts = "、".join(_IMPORT_EXTS[category])
        return {"ok": False,
                "message": f"{category} 类素材只支持扩展名：{exts}，收到的是 {ext or '（无扩展名）'}"}
    if not isinstance(data_b64, str) or not data_b64:
        return {"ok": False, "message": "文件内容为空"}
    if data_b64.startswith("data:") and "," in data_b64[:80]:
        data_b64 = data_b64.split(",", 1)[1]  # 容忍 data:URL 前缀
    if len(data_b64) > _IMPORT_MAX_BYTES * 2:
        return {"ok": False,
                "message": f"文件过大：上限 {_IMPORT_MAX_BYTES // 1024 // 1024}MB"}
    try:
        blob = base64.b64decode(data_b64, validate=True)
    except (ValueError, binascii.Error):
        return {"ok": False, "message": "文件内容不是合法的 base64 数据"}
    if len(blob) > _IMPORT_MAX_BYTES:
        return {"ok": False,
                "message": f"文件过大：上限 {_IMPORT_MAX_BYTES // 1024 // 1024}MB"}
    subdir = _IMPORT_DIRS[category]
    try:
        target_dir = _safe_within(root, subdir)  # realpath 前缀校验（P7 安全模式）
    except ValueError as e:
        return {"ok": False, "message": str(e)}
    try:
        os.makedirs(target_dir, exist_ok=True)
    except OSError as e:
        return {"ok": False, "message": f"创建素材目录失败：{e}"}
    final = filename
    existed = os.path.exists(os.path.join(target_dir, final))
    if not overwrite:
        n = 0
        while os.path.exists(os.path.join(target_dir, final)):  # 同名冲突自动加后缀
            n += 1
            final = f"{stem}_{n}{ext}"
    try:
        with open(os.path.join(target_dir, final), "wb") as f:
            f.write(blob)
    except OSError as e:
        return {"ok": False, "message": f"写入文件失败：{e}"}
    resp = {"ok": True, "name": os.path.splitext(final)[0], "path": f"{subdir}/{final}"}
    if not overwrite and final != filename:
        resp["renamed_from"] = filename  # 同名冲突时告知前端提示
    if overwrite and existed:
        resp["overwritten"] = True
    return resp


# ==================== P17 多文件工程（只追加，核心零改动） ====================
_INCLUDE_LINE = re.compile(r"^@include\s+(\S+)")
_TAIL_COMMENT = re.compile(r"\s+#.*$")


_TMP_GAL_RE = re.compile(r"^tmp[a-z0-9_]{8}\.gal$")


def _remove_quiet(path: str, retries: int = 5) -> None:
    """删除临时剧本；Windows 上偶发被其它线程/进程短暂占用，短重试避免残留 tmp*.gal。"""
    for i in range(retries):
        try:
            os.remove(path)
            return
        except FileNotFoundError:
            return
        except OSError:
            if i == retries - 1:
                return
            time.sleep(0.02)


def _cleanup_stale_tmp(root: str, min_age: float = 0.5) -> int:
    """清掉上次异常退出残留的临时剧本（只认 mkstemp 命名 tmpXXXXXXXX.gal）。返回删除数。"""
    now = time.time()
    removed = 0
    try:
        names = os.listdir(root)
    except OSError:
        return 0
    for name in names:
        if not _TMP_GAL_RE.match(name):
            continue
        path = os.path.join(root, name)
        try:
            if now - os.path.getmtime(path) >= min_age:
                os.remove(path)
                removed += 1
        except OSError:
            continue
    return removed


def _is_tmp_gal(name: str) -> bool:
    """判断是否是编辑器预览用的临时剧本（mkstemp 命名：tmp + 8 位随机 + .gal）。"""
    return bool(_TMP_GAL_RE.match(name))


def _list_gal_files(root: str) -> list:
    """递归列出项目下全部 .gal：相对路径（/ 分隔），排序返回。"""
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d != "__pycache__"]
        for fn in filenames:
            if fn.lower().endswith(".gal") and not _is_tmp_gal(fn):
                rel = os.path.relpath(os.path.join(dirpath, fn), root)
                out.append(rel.replace(os.sep, "/"))
    return sorted(out)


def _walk_instrs(instrs):
    """按文档顺序铺平指令流（@if 嵌套体 + @elif/@else 体就地展开；@choice 选项无嵌套指令）。"""
    for i in instrs or []:
        yield i
        if i.get("op") == "if":
            yield from _walk_instrs(i.get("body"))
            yield from _walk_instrs(i.get("else_body"))


def _to_rel(root: str, path, fallback: str) -> str:
    """绝对路径转项目相对路径（/ 分隔）；转换失败返回 fallback。"""
    try:
        return os.path.relpath(path, root).replace(os.sep, "/")
    except (TypeError, ValueError):
        return fallback


def _rel_gal(root: str, rel: str) -> str:
    """校验相对路径指向项目内 .gal 并返回绝对路径；越界/非 .gal 抛 ValueError。"""
    rel = (rel or "").strip().replace("\\", "/").lstrip("/")
    if not rel or not rel.lower().endswith(".gal"):
        raise ValueError("只支持项目内的 .gal 文件")
    return _safe_within(root, rel)


def _check_gal_text(text: str, dir_: str) -> None:
    """在 dir_ 写临时文件做语法检查（@include 以该目录为基准）；有错抛 GalSyntaxError。"""
    fd, tmp = tempfile.mkstemp(suffix=".gal", dir=dir_)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        parse_file(tmp)
    finally:
        _remove_quiet(tmp)


def _parse_at_root(text: str, root: str):
    """把文本写到项目根临时文件再 parse_file（@include 以项目根为基准）。

    返回 (指令列表, 顶层文件真实路径)：include 展开的其它文件指令 file 字段≠顶层路径。
    """
    fd, tmp = _mkstemp_or_explain(root)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        return parse_file(tmp), os.path.realpath(tmp)
    finally:
        _remove_quiet(tmp)


def _mkstemp_or_explain(dir_: str):
    """在 dir_ 建临时 .gal；目录不可写时抛中文 ValueError（供各 API 统一返回 400）。"""
    try:
        return tempfile.mkstemp(suffix=".gal", dir=dir_)
    except OSError as e:
        raise ValueError(
            f"工程目录不可写，无法做语法检查（{dir_}）：请检查目录权限后重试"
        ) from e


def _rel_edit_dir(root: str, rel: str) -> str:
    """正在编辑的 rel 文件所在目录（_rel_gal 校验：.gal + 在项目内）。"""
    return os.path.dirname(_rel_gal(root, rel))


def _parse_rel(text: str, root: str, rel: str) -> list[dict]:
    """把 text 当作 root 下的 rel 文件解析（@include 以该文件所在目录为基准）。

    主文本的语法错误与指令 file 字段都定位到 rel（而非临时文件）；
    @include 展开的其他文件指令保留真实绝对路径。
    """
    dir_ = _rel_edit_dir(root, rel)
    fd, tmp = _mkstemp_or_explain(dir_)
    tmp_real = os.path.realpath(tmp)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        try:
            instrs = parse_file(tmp)
        except GalSyntaxError as e:
            if os.path.realpath(e.source) == tmp_real:
                e.source = rel
                e.args = (f"{rel} 第 {e.line} 行：{e.message}",)
            raise
        for i in _walk_instrs(instrs):
            if i.get("file") and os.path.realpath(i["file"]) == tmp_real:
                i["file"] = rel
        return instrs
    finally:
        _remove_quiet(tmp)


def _new_chapter(root: str, name: str) -> str:
    """新建章节文件（项目根下 name.gal）：白名单 + 不覆盖 + 教学骨架。返回相对路径。"""
    name = (name or "").strip()
    if name.lower().endswith(".gal"):
        name = name[:-4]
    if not name:
        raise ValueError("章节名不能为空")
    if not _ASSET_NAME.fullmatch(name):
        raise ValueError("章节名只支持中文/字母/数字/下划线，不能含空格或符号")
    rel = f"{name}.gal"
    target = os.path.realpath(os.path.join(root, rel))
    try:
        with open(target, "x", encoding="utf-8") as f:
            f.write(f"# 章节：{name}\n@label {name}\n@ 这里是新的一幕，开始写吧。\n")
    except FileExistsError:
        raise ValueError(f"章节「{name}」已存在，换个名字吧（不会覆盖已有文件）")
    return rel


def _collect_project_labels(root: str) -> dict:
    """跨文件收集 @label（文件+行号）与 @jump 目标；解析失败的文件进 errors 不中断。"""
    labels, jumps, errors = [], [], []
    seen = set()
    for rel in _list_gal_files(root):
        try:
            instrs = parse_file(os.path.join(root, rel.replace("/", os.sep)))
        except (GalSyntaxError, OSError, UnicodeDecodeError) as e:
            errors.append({"file": rel, "message": str(e)})
            continue
        for i in _walk_instrs(instrs):
            op = i.get("op")
            if op not in ("label", "jump"):
                continue
            f = _to_rel(root, i.get("file"), rel) if i.get("file") else rel
            key = (op, f, i.get("line"), i.get("name") or i.get("target"))
            if key in seen:  # include 展开造成的重复只收一次
                continue
            seen.add(key)
            if op == "label":
                labels.append({"file": f, "line": i.get("line"), "name": i.get("name")})
            else:
                jumps.append({"file": f, "line": i.get("line"), "target": i.get("target")})
    return {"labels": labels, "jumps": jumps, "errors": errors}


def _resolve_include(root: str, rel: str, line: int) -> dict:
    """解析某文件第 line 行的 @include 目标（相对当前文件所在目录，与 parser 同规则）。"""
    try:
        abs_path = _rel_gal(root, rel)
    except ValueError as e:
        return {"ok": False, "message": str(e)}
    try:
        with open(abs_path, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError as e:
        return {"ok": False, "message": f"读取文件失败：{e}"}
    if not (1 <= line <= len(lines)):
        return {"ok": False, "message": f"行号越界：{line}（共 {len(lines)} 行）"}
    content = _TAIL_COMMENT.sub("", lines[line - 1]).strip()
    m = _INCLUDE_LINE.match(content)
    if not m:
        return {"ok": False, "message": f"第 {line} 行不是 @include 指令"}
    arg = m.group(1)
    child = os.path.realpath(os.path.join(os.path.dirname(abs_path), arg))
    root_real = os.path.realpath(root)
    if child != root_real and not child.startswith(root_real + os.sep):
        return {"ok": False, "message": f"@include 目标越出项目目录：{arg}"}
    return {"ok": True, "target": _to_rel(root, child, arg),
            "exists": os.path.isfile(child)}


def extract_timeline(instrs, top_file: str = "<string>") -> list:
    """场景时间线节点：背景/立绘/音频三条泳道 + 选项节点，带行号。

    只取当前文件（file == top_file）；@include 展开的其它文件指令不计入
    （它们的行号属于别的文件，点击跳转会错位）。
    """
    nodes = []
    for i in _walk_instrs(instrs):
        if i.get("file") not in (None, top_file):
            continue
        op = i.get("op")
        ln = i.get("line")
        if op == "bg":
            nodes.append({"line": ln, "lane": "bg", "kind": "bg", "name": i.get("image"),
                          "label": i.get("image")})
        elif op == "video":
            nodes.append({"line": ln, "lane": "bg", "kind": "video", "name": i.get("name"),
                          "label": i.get("name")})
        elif op == "cg":
            nodes.append({"line": ln, "lane": "bg", "kind": "cg", "name": i.get("name"),
                          "label": "CG " + str(i.get("name"))})
        elif op == "show":
            char, expr = i.get("char"), i.get("expr")
            nodes.append({"line": ln, "lane": "sprite", "kind": "show",
                          "name": f"{char}_{expr}", "label": f"{char} {expr}"})
        elif op == "hide":
            nodes.append({"line": ln, "lane": "sprite", "kind": "hide",
                          "label": i.get("char")})
        elif op == "music":
            nodes.append({"line": ln, "lane": "audio", "kind": "music", "name": i.get("track"),
                          "label": i.get("track")})
        elif op == "sfx":
            nodes.append({"line": ln, "lane": "audio", "kind": "sfx", "name": i.get("sound"),
                          "label": i.get("sound")})
        elif op == "voice":
            nodes.append({"line": ln, "lane": "audio", "kind": "voice", "name": i.get("sound"),
                          "label": i.get("sound")})
        elif op == "choice":
            texts = [o.get("text", "") for o in (i.get("options") or [])]
            nodes.append({"line": ln, "lane": "choice", "kind": "choice",
                          "label": " / ".join(texts), "options": texts})
    return nodes


def scene_state_at(instrs, line: int, top_file: str = "<string>") -> dict:
    """某行处的场景状态：最后 bg / 当前 music / 可见立绘（文档顺序扫到 line 为止）。

    只算当前文件、忽略分支控制流（面板的近似展示，不模拟运行时）。
    """
    bg = music = None
    sprites = {}
    for i in _walk_instrs(instrs):
        if i.get("file") not in (None, top_file):
            continue
        if (i.get("line") or 0) > line:
            continue
        op = i.get("op")
        if op == "bg":
            bg = i.get("image")
        elif op == "music":
            music = i.get("track")
        elif op == "show":
            sprites[i.get("char")] = i.get("expr")
        elif op == "hide":
            sprites.pop(i.get("char"), None)
    return {"bg": bg, "music": music,
            "sprites": [{"char": c, "expr": e} for c, e in sprites.items()]}


class _EditorHandler(BaseHTTPRequestHandler):
    """编辑器请求处理器：路由集中在 _ROUTES 注册表，每路由一个方法。

    app（EditorApp 实例）由 make_handler 绑定到子类；全部写操作走
    realpath 前缀校验 + 白名单，保存前做语法校验（坏文件不落盘）。
    """

    app = None  # EditorApp 实例（make_handler 绑定）

    # 路由注册表：(方法, 路径) → 方法名；/api/asset/ 前缀走 do_GET 里的前缀分发
    _ROUTES = {
        ("GET", "/"): "_serve_index",
        ("GET", "/editor.css"): "_serve_editor_css",
        ("GET", "/editor_pro.js"): "_serve_pro_js",
        # 场景视图（可视化编辑）：独立模块，源码/场景互不覆盖
        ("GET", "/editor_scene.js"): "_serve_scene_js",
        ("GET", "/editor_characters.js"): "_serve_characters_js",
        ("GET", "/editor_main.js"): "_serve_main_js",
        # E9：编辑器三档模式 Level 1–3（前端档位开关，状态存 localStorage）
        ("GET", "/editor_level.js"): "_serve_level_js",
        # T16 域拆分：游戏内 UI 设计区 / 壳层（菜单 + 命令面板 + 教程）
        ("GET", "/editor_uidesign.js"): "_serve_uidesign_js",
        ("GET", "/editor_shell.js"): "_serve_shell_js",
        # 角色库（characters.json，项目级角色资产）
        ("GET", "/api/characters"): "_characters_get",
        # V4：角色引用计数（扫描工程内全部 .gal，跨 @include 文件）
        ("GET", "/api/characters/usage"): "_characters_usage",
        ("POST", "/api/characters"): "_characters_set",
        # 角色改名并同步全部 .gal 引用（@character/@show/@hide/@anim/台词）
        ("POST", "/api/character/rename"): "_character_rename",
        ("GET", "/api/script"): "_get_script",
        ("GET", "/api/assets"): "_get_assets",
        ("GET", "/api/config"): "_get_config",
        # P51：UI 设计区——读/写项目 config.json 的 ui + dialogue 几何段，独立预览
        ("GET", "/api/ui-design"): "_ui_design_get",
        ("POST", "/api/ui-design"): "_ui_design_set",
        ("POST", "/api/ui-design/preview"): "_ui_design_preview",
        # 桌宠（实验）：start / stop / status（源码模式可用；发行包后续接入）
        ("POST", "/api/pet"): "_pet_control",
        ("GET", "/api/complete"): "_complete",
        ("GET", "/api/files"): "_handle_files",
        ("GET", "/api/file/read"): "_handle_file_read",
        ("GET", "/api/labels"): "_handle_labels",
        ("GET", "/api/include-target"): "_handle_include_target",
        ("POST", "/api/check"): "_check",
        ("POST", "/api/preview"): "_preview",
        ("POST", "/api/complete"): "_complete",
        ("POST", "/api/run"): "_run",
        ("POST", "/api/render"): "_render",
        ("POST", "/api/script"): "_save_script",
        ("POST", "/api/import"): "_import_asset",
        ("POST", "/api/config"): "_set_config",
        ("POST", "/api/new"): "_new_game",
        ("POST", "/api/browse"): "_browse",
        ("POST", "/api/file/save"): "_handle_file_save",
        ("POST", "/api/file/new"): "_handle_file_new",
        ("POST", "/api/timeline"): "_handle_timeline",
        ("POST", "/api/scene"): "_handle_scene",
        # P35 打包发布
        # M1.5：内嵌教程（开发者侧「边写边看说明书」；玩家侧不出现）
        ("GET", "/api/help"): "_help_list",
        ("GET", "/api/help/doc"): "_help_doc",
        ("GET", "/api/pack/projects"): "_pack_projects",
        ("GET", "/api/pack/profile"): "_pack_profile_get",
        ("GET", "/api/pack/status"): "_pack_status",
        ("GET", "/api/pack/version"): "_pack_version",
        ("POST", "/api/pack/profile"): "_pack_profile_save",
        ("POST", "/api/pack/build"): "_pack_build",
    }

    # ---- 基础 ----

    def log_message(self, fmt, *args):  # 静默日志
        pass

    def _send_json(self, status: int, obj) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        # 编辑器 API 一律不缓存：文件内容/清单必须始终反映磁盘最新状态
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b""
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return {}

    # ---- 分发（只做路由，不含业务） ----

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/asset/"):
            self._get_asset(parsed.path)
            return
        self._dispatch("GET", parsed)

    def do_POST(self) -> None:
        self._dispatch("POST", urlparse(self.path))

    def _dispatch(self, method: str, parsed) -> None:
        name = self._ROUTES.get((method, parsed.path))
        if name is None:
            self._send_json(404, {"error": "不存在的路由"})
            return
        getattr(self, name)(parsed)

    # ---- 路由实现 ----

    def _serve_editor_file(self, name: str, mime: str) -> None:
        p = os.path.join(_editor_front_dir(), name)
        try:
            with open(p, "rb") as f:
                body = f.read()
        except OSError:
            self._send_json(500, {"error": f"编辑器前端文件缺失：{name}"})
            return
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")  # 前端文件始终取磁盘最新
        self.end_headers()
        self.wfile.write(body)

    # ---- M1.5：内嵌教程 ----

    def _help_list(self, parsed=None) -> None:
        """列出可用教程（只返回磁盘上真实存在的，打包漏带时不至于给死链）。"""
        docs = []
        for doc_id, title, filename in _HELP_DOCS:
            if os.path.isfile(os.path.join(_docs_dir(), filename)):
                docs.append({"id": doc_id, "title": title})
        self._send_json(200, {"ok": True, "docs": docs})

    def _help_doc(self, parsed) -> None:
        q = parse_qs(parsed.query)
        doc_id = (q.get("id") or [""])[0]
        found = _read_help_doc(doc_id)
        if found is None:
            self._send_json(404, {"ok": False, "message": f"没有这篇教程：{doc_id}"})
            return
        title, text = found
        self._send_json(200, {"ok": True, "id": doc_id, "title": title, "text": text})

    def _serve_index(self, parsed=None) -> None:
        self._serve_editor_file("index.html", "text/html; charset=utf-8")

    def _serve_editor_css(self, parsed=None) -> None:
        self._serve_editor_file("editor.css", "text/css; charset=utf-8")

    def _serve_pro_js(self, parsed=None) -> None:
        self._serve_editor_file("editor_pro.js", "application/javascript; charset=utf-8")

    def _app_root(self) -> str | None:
        """项目根目录（未初始化时 None；给新处理器做类型收窄）。"""
        app = self.app
        return app.project_root if app is not None else None

    def _characters_get(self, parsed=None) -> None:
        """读项目级角色库 characters.json。"""
        root = self._app_root()
        if root is None:
            self._send_json(500, {"ok": False, "message": "编辑器未初始化"})
            return
        self._send_json(200, {"ok": True, "data": characters_api.load(root)})

    def _character_rename(self, parsed=None) -> None:
        """角色批量改名：先校验，再改 characters.json 与所有 .gal 引用。"""
        data = self._read_json()
        old = str(data.get("old") or "").strip()
        new = str(data.get("new") or "").strip()
        root = self._app_root()
        if root is None:
            self._send_json(500, {"ok": False, "message": "编辑器未初始化"})
            return
        try:
            result = characters_api.rename_in_project(root, old, new)
        except ValueError as exc:
            self._send_json(400, {"ok": False, "message": str(exc)})
            return
        except OSError as exc:
            self._send_json(400, {"ok": False, "message": f"改名失败：{exc}"})
            return
        self._send_json(200, {"ok": True, "message": f"已改名 {old} → {new}（{result['files']} 个文件、{result['lines']} 行）", **result})

    def _characters_usage(self, parsed=None) -> None:
        """V4：角色在工程 .gal 里的引用计数（跨 @include 文件），用于角色库列表角标。"""
        root = self._app_root()
        if root is None:
            self._send_json(500, {"ok": False, "message": "编辑器未初始化"})
            return
        lib = characters_api.load(root)
        ids = [c["id"] for c in lib.get("characters") or []]
        self._send_json(200, {"ok": True, "usage": characters_api.usage_in_project(root, ids)})

    def _characters_set(self, parsed=None) -> None:
        """写角色库（校验后原子替换；角色 id 去重、颜色非法回退 #ffffff）。"""
        data = self._read_json()
        root = self._app_root()
        if root is None:
            self._send_json(500, {"ok": False, "message": "编辑器未初始化"})
            return
        try:
            target = characters_api.save(root, data)
        except OSError as e:
            self._send_json(400, {"ok": False, "message": f"角色库写入失败：{e}"})
            return
        self._send_json(200, {"ok": True, "path": target})

    def _serve_main_js(self, parsed=None) -> None:
        self._serve_editor_file("editor_main.js", "application/javascript; charset=utf-8")

    def _serve_characters_js(self, parsed=None) -> None:
        self._serve_editor_file("editor_characters.js", "application/javascript; charset=utf-8")

    def _serve_scene_js(self, parsed=None) -> None:
        self._serve_editor_file("editor_scene.js", "application/javascript; charset=utf-8")

    def _serve_level_js(self, parsed=None) -> None:
        self._serve_editor_file("editor_level.js", "application/javascript; charset=utf-8")

    def _serve_uidesign_js(self, parsed=None) -> None:
        self._serve_editor_file("editor_uidesign.js", "application/javascript; charset=utf-8")

    def _serve_shell_js(self, parsed=None) -> None:
        self._serve_editor_file("editor_shell.js", "application/javascript; charset=utf-8")

    def _check(self, parsed=None) -> None:
        data = self._read_json()
        text = data.get("text", "")
        rel = data.get("path")
        try:
            if rel:
                # 多文件工程：以正在编辑的文件目录为 @include 基准
                instrs = _parse_rel(text, self.app.project_root, rel)
            else:
                instrs = parse_text(text)
        except ValueError as e:
            self._send_json(400, {"ok": False, "message": str(e)})
            return
        except GalSyntaxError as e:
            # A1：新字段 summary/detail/hint + 旧字段 message/file/line
            self._send_json(200, {"ok": False, **e.to_dict()})
            return
        self._send_json(200, {"ok": True, "count": len(instrs),
                              "instructions": instrs})

    def _preview(self, parsed=None) -> None:
        data = self._read_json()
        text = data.get("text", "")
        frames = data.get("frames", 30)
        rel = data.get("path")
        try:
            # 临时剧本写在正在编辑的文件目录内，使 @include 基准正确
            base_dir = _rel_edit_dir(self.app.project_root, rel) if rel \
                else self.app.project_root
        except ValueError as e:
            self._send_json(400, {"ok": False, "message": str(e)})
            return
        try:
            if rel:
                _parse_rel(text, self.app.project_root, rel)
            else:
                parse_text(text)  # 先语法检查，解析失败直接 422
        except GalSyntaxError as e:
            self._send_json(422, {"ok": False, **e.to_dict()})
            return
        _cleanup_stale_tmp(base_dir, min_age=0.2)
        fd, tmp_path = tempfile.mkstemp(suffix=".gal", dir=base_dir)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(text)
            try:
                with _preview_lock:
                    png = _preview_png(tmp_path, self.app.project_root, frames)
            except Exception as e:
                self._send_json(500, {"ok": False, "message": f"预览渲染失败：{e}"})
                return
        finally:
            _remove_quiet(tmp_path)
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(png)))
        self.end_headers()
        self.wfile.write(png)

    def _complete(self, parsed=None) -> None:
        if parsed is not None and parsed.query:  # GET /api/complete?line=...&text=...
            q = parse_qs(parsed.query)
            line = (q.get("line") or [""])[0]
            full_text = (q.get("text") or [""])[0]
        else:
            data = self._read_json()
            line = data.get("line", "")
            full_text = data.get("text", "")
        items = _completions(line, full_text)
        # 素材候选按行首指令并入（@bg→images / @voice→audio / @show→表情后缀）
        try:
            assets = _scan_assets(self.app.data_root)
        except OSError:
            assets = {}
        token = _tail_token(line)
        for name in _asset_completions(line, assets):
            if token and not name.lower().startswith(token.lower()):
                continue
            if name not in items:
                items.append(name)
        self._send_json(200, {"items": items})

    def _get_assets(self, parsed=None) -> None:
        """素材清单（只列文件名，不读内容）。"""
        try:
            assets = _scan_assets(self.app.data_root)
        except OSError as e:
            self._send_json(500, {"ok": False, "message": f"扫描素材失败：{e}"})
            return
        self._send_json(200, {"ok": True, "assets": assets})

    def _get_config(self, parsed=None) -> None:
        """当前工程/数据目录与配置（设置面板读取）。"""
        self._send_json(200, self.app.config_info())

    def _set_config(self, parsed=None) -> None:
        """修改工程/数据目录或自动插指令偏好；配置写回工程 .editor_config.json。"""
        data = self._read_json()
        result = self.app.apply_config(
            project_root=data.get("project_root"),
            data_root=data.get("data_root"),
            auto_insert=data.get("auto_insert"),
        )
        self._send_json(200 if result.get("ok") else 400, result)

    # ==================== P51/P52：UI 设计区（独立于剧本编辑） ====================

    # 玩家/开发者可在 UI 设计区调整的键（其余 ui/dialogue 键保持项目 config.json 原样）
    # P52：扩为六组——对话框 / 名字框 / 选项 / 快捷栏 / 游戏内菜单 / 设置页
    _UI_DESIGN_UI_KEYS = ("pixelated", "pixel_scale", "corner_radius")
    _UI_DESIGN_DLG_KEYS = ("radius", "offset_x", "offset_y", "panel_width", "height",
                           "name_y", "name_gap")   # P52：名字框（y/间距）并入对话框组
    _UI_DESIGN_CHOICES_KEYS = ("width", "row_height", "dialog_gap", "radius")
    _UI_DESIGN_QUICKBAR_KEYS = ("button_width", "button_height", "gap", "margin_x",
                                "margin_y", "alpha", "radius", "position", "align", "icons")
    _UI_DESIGN_MENU_KEYS = ("row_width", "row_height", "top", "radius")
    _UI_DESIGN_SETTINGS_KEYS = ("row_width", "row_height", "nav_width", "top")
    # B2：排版常用两项（正文字号 / 正文行距），其余字号键保持项目原样
    _UI_DESIGN_FONT_KEYS = ("body",)
    _UI_DESIGN_LH_KEYS = ("body",)
    # 2026-11-02：配色面板——语义主题色白名单（shadow 不作为可调项）
    _UI_DESIGN_THEME_KEYS = ("primary", "primary_soft", "accent", "surface", "surface_alt",
                             "text", "text_dim", "border", "danger", "success")

    # P52：全部可调组 → (config.json 顶层段, 白名单, 响应键名)
    _UI_DESIGN_GROUPS = (
        ("ui", _UI_DESIGN_UI_KEYS, "ui"),
        ("dialogue", _UI_DESIGN_DLG_KEYS, "dialogue"),
        ("ui", _UI_DESIGN_CHOICES_KEYS, "choices"),      # ui.choices
        ("ui", _UI_DESIGN_QUICKBAR_KEYS, "quickbar"),    # ui.quickbar
        ("ui", _UI_DESIGN_MENU_KEYS, "menu"),            # ui.menu
        ("ui", _UI_DESIGN_SETTINGS_KEYS, "settings"),    # ui.settings
        ("font", _UI_DESIGN_FONT_KEYS, "font"),
        ("line_height", _UI_DESIGN_LH_KEYS, "line_height"),
    )

    def _ui_design_get(self, parsed=None) -> None:
        """读当前项目的 UI 设计字段（六组：ui/dialogue/choices/quickbar/menu/settings/font/lh）。

        返回磁盘 config.json 的现值；未写键以引擎默认补齐（前端显示"默认"）。
        """
        root = self.app.project_root
        cfg = _load_project_config(root)
        if not isinstance(cfg, dict):
            cfg = {}
        from .config import DEFAULTS as _CFG_DEFAULTS

        def _section(top: str) -> dict:
            return cfg.get(top) or {}

        def _default(top: str) -> dict:
            return (_CFG_DEFAULTS.get(top) or {})

        resp = {}
        # 先填所有段的"当前值"（未写键取引擎默认，仅展示）
        # ui 顶层段：pixelated 等直接键
        ui = _section("ui")
        dlg = dict(_section("dialogue").get("default") or {})
        engine_dlg = dict(_default("dialogue").get("default") or {})
        resp["ui"] = {k: ui.get(k, _default("ui").get(k)) for k in self._UI_DESIGN_UI_KEYS}
        resp["dialogue"] = {k: dlg.get(k, engine_dlg.get(k)) for k in self._UI_DESIGN_DLG_KEYS}
        for top, keys, name in self._UI_DESIGN_GROUPS:
            if name in ("ui", "dialogue", "font", "line_height"):
                continue
            cur = _section("ui").get(name) or {}   # 嵌套在 ui 段下
            eng = (_default("ui").get(name) or {})
            resp[name] = {k: cur.get(k, eng.get(k)) for k in keys}
        resp["font"] = {k: _section("font").get(k, _default("font").get(k))
                        for k in self._UI_DESIGN_FONT_KEYS}
        resp["line_height"] = {k: _section("line_height").get(k, _default("line_height").get(k))
                               for k in self._UI_DESIGN_LH_KEYS}
        # 配色：未覆盖的键显示引擎 fallback（真实生效色，而不是空值）
        from .config import THEME_FALLBACK as _THEME_FALLBACK
        theme = _section("theme")
        resp["theme"] = {k: list(theme.get(k) or _THEME_FALLBACK.get(k, (255, 255, 255)))
                         for k in self._UI_DESIGN_THEME_KEYS}
        # 「恢复引擎默认」用：未覆盖时的兜底色（前端不要自己再抄一份）
        resp["theme_defaults"] = {k: list(_THEME_FALLBACK.get(k, (255, 255, 255)))
                                  for k in self._UI_DESIGN_THEME_KEYS}
        # 1080p 预设：画布尺寸（顶层 canvas_size，[宽, 高]）
        size = cfg.get("canvas_size") or _CFG_DEFAULTS.get("canvas_size") or [1280, 720]
        resp["canvas"] = {"size": [int(size[0]), int(size[1])]}
        # 自定义字体（顶层 font_file）：相对项目根的 ttf/otf 路径，空 = 自动查找
        resp["font_file"] = str(cfg.get("font_file") or "")
        # 界面开关（项目 settings.json 的玩家默认值）：快捷栏显隐 / 桌宠
        resp["interface"] = _interface_settings(root)
        self._send_json(200, {"ok": True, **resp})

    def _ui_design_set(self, parsed=None) -> None:
        """把 UI 设计字段写回项目 config.json（白名单键，其余键原样保留）。

        六组：ui 顶层（pixelated 等）、dialogue.default（含名字框）、
        ui.choices / ui.quickbar / ui.menu / ui.settings、font、line_height。
        """
        data = self._read_json()
        root = self.app.project_root
        try:
            cfg = _load_project_config(root)
            cfg = dict(cfg)  # 浅拷贝：写回不污染内存共享

            # ui 顶层段（pixelated/pixel_scale/corner_radius）
            ui_patch = data.get("ui")
            if isinstance(ui_patch, dict):
                ui = dict(cfg.get("ui") or {})
                for k in self._UI_DESIGN_UI_KEYS:
                    if k in ui_patch:
                        ui[k] = ui_patch[k]
                cfg["ui"] = ui
            # dialogue.default（含名字框 name_y/name_gap）
            dlg_patch = data.get("dialogue")
            if isinstance(dlg_patch, dict):
                dlg = dict((cfg.get("dialogue") or {}).get("default") or {})
                for k in self._UI_DESIGN_DLG_KEYS:
                    if k in dlg_patch:
                        dlg[k] = dlg_patch[k]
                cfg.setdefault("dialogue", {})["default"] = dlg
            # ui 段下嵌套组：choices/quickbar/menu/settings
            ui = dict(cfg.get("ui") or {})
            for top, keys, name in self._UI_DESIGN_GROUPS:
                if name in ("ui", "dialogue", "font", "line_height"):
                    continue
                patch = data.get(name)
                if not isinstance(patch, dict):
                    continue
                sec = dict(ui.get(name) or {})
                for k in keys:
                    if k in patch:
                        sec[k] = patch[k]
                # 快捷栏图标：只接受 {标签: 图片名} 的字符串映射，脏数据不落盘
                if name == "quickbar" and "icons" in patch:
                    raw = patch.get("icons")
                    sec["icons"] = ({str(k).upper(): str(v) for k, v in raw.items()
                                     if isinstance(k, str) and isinstance(v, str) and v.strip()}
                                    if isinstance(raw, dict) else {})
                ui[name] = sec
            cfg["ui"] = ui
            # font / line_height
            font_patch = data.get("font")
            if isinstance(font_patch, dict):
                font = dict(cfg.get("font") or {})
                for k in self._UI_DESIGN_FONT_KEYS:
                    if k in font_patch:
                        font[k] = font_patch[k]
                cfg["font"] = font
            lh_patch = data.get("line_height")
            if isinstance(lh_patch, dict):
                lh = dict(cfg.get("line_height") or {})
                for k in self._UI_DESIGN_LH_KEYS:
                    if k in lh_patch:
                        lh[k] = lh_patch[k]
                cfg["line_height"] = lh
            # 配色：null = 删除覆盖（回落到引擎默认）；[r,g,b] = 写入
            theme_patch = data.get("theme")
            if isinstance(theme_patch, dict):
                theme = dict(cfg.get("theme") or {})
                for k in self._UI_DESIGN_THEME_KEYS:
                    if k not in theme_patch:
                        continue
                    val = theme_patch[k]
                    if val is None:
                        theme.pop(k, None)
                        continue
                    if (isinstance(val, (list, tuple)) and len(val) == 3
                            and all(isinstance(v, int) and 0 <= v <= 255 for v in val)):
                        theme[k] = [int(val[0]), int(val[1]), int(val[2])]
                cfg["theme"] = theme
            # 1080p 预设：顶层 canvas_size（只接受正整数宽高）
            cpatch = data.get("canvas")
            if isinstance(cpatch, dict):
                size = cpatch.get("size")
                if (isinstance(size, (list, tuple)) and len(size) == 2
                        and all(isinstance(v, int) and 320 <= v <= 7680 for v in size)):
                    cfg["canvas_size"] = [int(size[0]), int(size[1])]
            # 自定义字体：顶层 font_file（空串 = 清除覆盖，走自动查找）
            if "font_file" in data:
                ff = data.get("font_file")
                ff = ff.strip() if isinstance(ff, str) else ""
                if ff and (ff.startswith("..") or "\0" in ff):
                    self._send_json(400, {"ok": False,
                                          "message": "字体路径不合法：请写项目内的相对路径"})
                    return
                if ff and not ff.lower().endswith((".ttf", ".otf", ".ttc")):
                    self._send_json(400, {"ok": False,
                                          "message": "字体文件需为 .ttf / .otf / .ttc"})
                    return
                if ff:
                    cfg["font_file"] = ff
                else:
                    cfg.pop("font_file", None)
            path = _write_project_config(root, cfg)
            # 界面开关：写项目 settings.json（玩家默认值），与 config.json 分开保存
            iface = data.get("interface")
            settings_path = ""
            if isinstance(iface, dict):
                settings_path = _save_interface_settings(root, iface)
        except (OSError, ValueError, TypeError) as e:
            self._send_json(400, {"ok": False, "message": f"保存 UI 设计失败：{e}"})
            return
        result = {"ok": True, "path": path}
        if settings_path:
            result["settings_path"] = settings_path
        self._send_json(200, result)

    def _pet_control(self, parsed=None) -> None:
        """桌宠开关（实验功能）：start / stop / status。默认关闭。

        桌宠是独立的 pygame 进程，编辑器只在用户点「打开桌宠」时启动：
        源码模式 `python -m engine.pet`，发行版 `editor.exe --pet`。
        桌宠不进游戏包（pack.py 排除 engine.pet）；启动失败（无显示环境）会明确报错。
        """
        global _PET_PROC
        data = self._read_json()
        action = str(data.get("action") or "").strip() or "status"
        if action not in ("start", "stop", "status"):
            self._send_json(400, {"ok": False, "message": "action 只支持 start / stop / status"})
            return
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with _PET_LOCK:
            if action == "status":
                running = bool(_PET_PROC and _PET_PROC.poll() is None)
                self._send_json(200, {"ok": True, "running": running})
                return
            if action == "stop":
                proc = _PET_PROC
                _PET_PROC = None
                if proc and proc.poll() is None:
                    try:
                        proc.terminate()
                        proc.wait(timeout=3)
                    except (OSError, subprocess.TimeoutExpired):
                        try:
                            proc.kill()
                        except OSError:
                            pass
                self._send_json(200, {"ok": True, "running": False, "message": "桌宠已关闭"})
                return
            if _PET_PROC and _PET_PROC.poll() is None:
                self._send_json(200, {"ok": True, "running": True, "message": "桌宠已在运行"})
                return
            if getattr(sys, "frozen", False):
                pet_cmd = [sys.executable, "--pet"]   # editor.exe 内置桌宠
            else:
                pet_cmd = [sys.executable, "-m", "engine.pet"]
            try:
                _PET_PROC = subprocess.Popen(
                    pet_cmd,
                    cwd=str(root),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except OSError as e:
                _PET_PROC = None
                self._send_json(200, {"ok": False, "running": False,
                                      "message": f"桌宠启动失败：{e}"})
                return
            self._send_json(200, {"ok": True, "running": True,
                                  "message": "桌宠已打开（可拖动 / Esc 关闭）"})

    def _ui_design_preview(self, parsed=None) -> None:
        """用给定 UI 几何参数渲染一帧预览 PNG（不改磁盘配置）。

        参数：{ui: {…}, dialogue: {…}, font: {…}, line_height: {…},
        scene: "dialog"|"choices"|"quickbar"|"menu"|"settings"}，
        缺省键走项目 config.json 现值；scene 缺省 dialog。
        """
        data = self._read_json()
        ui_patch = data.get("ui")
        dlg_patch = data.get("dialogue")
        font_patch = data.get("font")
        lh_patch = data.get("line_height")
        theme_patch = data.get("theme")
        ui_patch = ui_patch if isinstance(ui_patch, dict) else {}
        dlg_patch = dlg_patch if isinstance(dlg_patch, dict) else {}
        font_patch = font_patch if isinstance(font_patch, dict) else {}
        lh_patch = lh_patch if isinstance(lh_patch, dict) else {}
        theme_patch = theme_patch if isinstance(theme_patch, dict) else {}
        scene = str(data.get("scene") or "dialog")
        if scene not in ("dialog", "choices", "quickbar", "menu", "settings"):
            scene = "dialog"
        font_file = data.get("font_file")
        font_file = font_file.strip() if isinstance(font_file, str) else ""
        interface_patch = data.get("interface")
        interface_patch = interface_patch if isinstance(interface_patch, dict) else {}
        try:
            with _preview_lock:
                png = _ui_design_png(self.app.project_root, ui_patch, dlg_patch,
                                     font_patch, lh_patch, scene=scene,
                                     theme_patch=theme_patch, font_file=font_file,
                                     interface_patch=interface_patch)
        except Exception as e:
            self._send_json(500, {"ok": False, "message": f"UI 预览渲染失败：{e}"})
            return
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(png)))
        self.end_headers()
        self.wfile.write(png)

    def _get_asset(self, path: str) -> None:
        """读单个素材字节（缩略图/试听）。

        支持 `/api/asset/<名>`（依次在 images/videos/anims/audio/fonts 找）
        与 `/api/asset/<类别>/<名>`（明确类别，同名时用）。
        """
        rest = unquote(path[len("/api/asset/"):])
        category, _, name = rest.partition("/")
        if name:
            if category not in ("images", "videos", "anims", "audio", "fonts"):
                self._send_json(400, {"ok": False,
                                      "message": "素材地址应为 /api/asset/<名> 或 /api/asset/<类别>/<名>"})
                return
            found = _find_asset_file(self.app.data_root, category, name) if _ASSET_NAME.fullmatch(name) else None
        else:
            if not _ASSET_NAME.fullmatch(category):
                self._send_json(400, {"ok": False, "message": f"非法素材名：{category}"})
                return
            name = category
            found = None
            for cat in ("images", "videos", "anims", "audio", "fonts"):
                found = _find_asset_file(self.app.data_root, cat, name) or found
                if found:
                    break
        if not found:
            self._send_json(404, {"ok": False, "message": f"素材不存在：{name}"})
            return
        ext = os.path.splitext(found)[1].lower()
        try:
            size = os.path.getsize(found)
            f = open(found, "rb")
        except OSError as e:
            self._send_json(500, {"ok": False, "message": f"读取素材失败：{e}"})
            return
        with f:
            self.send_response(200)
            self.send_header("Content-Type", _MIME.get(ext, "application/octet-stream"))
            self.send_header("Content-Length", str(size))
            self.send_header("Cache-Control", "max-age=30")
            self.end_headers()
            while True:
                chunk = f.read(64 * 1024)
                if not chunk:
                    break
                self.wfile.write(chunk)

    def _import_asset(self, parsed=None) -> None:
        """导入素材：POST JSON {category, filename, data_b64, overwrite?}。"""
        data = self._read_json()
        result = _save_import(
            self.app.data_root,
            data.get("category"),
            data.get("filename"),
            data.get("data_b64", data.get("data")),
            bool(data.get("overwrite", False)),
        )
        self._send_json(200 if result.get("ok") else 400, result)

    # ---- P35 打包发布 ----

    def _pack_target(self, folder):
        """把前端传来的项目文件夹解析为 games/ 内的安全绝对路径。"""
        games = self.app.pack_games_dir()
        if not isinstance(folder, str) or not folder.strip():
            return None, "请选择一个游戏项目"
        if os.sep in folder or "/" in folder:
            return None, "项目标识不合法（只允许文件夹名）"
        target = _safe_within(games, folder.strip())
        if not os.path.isdir(target):
            return None, f"游戏项目不存在：{folder}"
        if not os.path.isfile(os.path.join(target, "script.gal")):
            return None, f"项目缺少 script.gal：{folder}"
        return target, ""

    def _pack_projects(self, parsed=None) -> None:
        games = self.app.pack_games_dir()
        root = self.app.pack_root()
        rows = packaging.list_projects(games, root=root)
        for row in rows:
            row["history"] = packaging.project_history(
                os.path.join(games, row["folder"]), root)
        self._send_json(200, {
            "ok": True,
            "games_dir": games,
            "current": os.path.basename(self.app.project_root),
            "projects": rows,
        })

    def _pack_profile_get(self, parsed=None) -> None:
        qs = parse_qs(parsed.query) if parsed else {}
        folder = (qs.get("project") or [""])[0]
        target, err = self._pack_target(folder)
        if err:
            self._send_json(400, {"ok": False, "message": err})
            return
        profile = packaging.load_profile(target)
        if not profile:
            # 旧项目/新项目未建档：给出可直接编辑的默认档案
            profile = {
                "game_name": folder,
                "version": "1.0.0",
                "icon": "icon.png",
                "publisher": {"name": "", "account_id": "", "channel": "", "contact": ""},
                "description": "",
                "release_notes": "",
            }
        errors = packaging.validate_profile(profile, target)
        self._send_json(200, {
            "ok": True,
            "folder": folder,
            "path": os.path.join(target, packaging.PROFILE_NAME),
            "profile": profile,
            "errors": errors,
            "history": packaging.project_history(target, self.app.pack_root()),
        })

    def _pack_profile_save(self, parsed=None) -> None:
        data = self._read_json()
        folder = data.get("project")
        target, err = self._pack_target(folder)
        if err:
            self._send_json(400, {"ok": False, "message": err})
            return
        profile = data.get("profile")
        if not isinstance(profile, dict):
            self._send_json(400, {"ok": False, "message": "profile 必须是对象"})
            return
        packaging.save_profile(target, profile)
        errors = packaging.validate_profile(profile, target)
        self._send_json(200, {
            "ok": True,
            "message": "打包配置已保存" if not errors else "已保存；仍有必填项待完善",
            "errors": errors,
            "path": os.path.join(target, packaging.PROFILE_NAME),
        })

    def _pack_version(self, parsed=None) -> None:
        qs = parse_qs(parsed.query) if parsed else {}
        folder = (qs.get("project") or [""])[0]
        bump = (qs.get("bump") or ["patch"])[0]
        target, err = self._pack_target(folder)
        if err:
            self._send_json(400, {"ok": False, "message": err})
            return
        try:
            version = packaging.next_version(target, bump, self.app.pack_root())
        except packaging.PackProfileError as e:
            self._send_json(400, {"ok": False, "message": str(e)})
            return
        self._send_json(200, {"ok": True, "version": version})

    def _pack_build(self, parsed=None) -> None:
        data = self._read_json()
        target, err = self._pack_target(data.get("project"))
        if err:
            self._send_json(400, {"ok": False, "message": err})
            return
        bump = data.get("bump") or None
        version = data.get("version") or None
        if bump and bump not in ("patch", "minor", "major"):
            self._send_json(400, {"ok": False, "message": "版本递增方式不合法"})
            return
        if bump and version:
            self._send_json(400, {"ok": False, "message": "固定版本号与版本递增不能同时使用"})
            return
        # 先把前端编辑后的档案落盘，再校验；缺项立即返回，不启动构建
        profile = packaging.load_profile(target)
        incoming = data.get("profile")
        if isinstance(incoming, dict):
            for key in ("game_name", "version", "icon", "description", "release_notes"):
                if key in incoming:
                    profile[key] = incoming[key]
            pub_in = incoming.get("publisher")
            if isinstance(pub_in, dict):
                pub = profile.get("publisher") if isinstance(profile.get("publisher"), dict) else {}
                for key in ("name", "account_id", "channel", "contact"):
                    if key in pub_in:
                        pub[key] = pub_in[key]
                profile["publisher"] = pub
        packaging.save_profile(target, profile)
        errors = packaging.validate_profile(profile, target)
        if errors:
            self._send_json(400, {"ok": False, "message": "打包配置不完整", "errors": errors})
            return

        job_id = uuid.uuid4().hex[:12]
        job = {
            "id": job_id,
            "project": data.get("project"),
            "status": "running",
            "message": "打包任务已启动，正在准备……",
            "started_at": packaging._now_iso(),
            "finished_at": "",
            "result": None,
            "error": "",
        }
        with self.app.pack_jobs_lock:
            # 只保留最近 30 个任务，避免长时间运行内存膨胀
            if len(self.app.pack_jobs) > 30:
                for old in list(self.app.pack_jobs)[:len(self.app.pack_jobs) - 30]:
                    self.app.pack_jobs.pop(old, None)
            self.app.pack_jobs[job_id] = job

        root = self.app.pack_root()
        app = self.app

        def worker() -> None:
            if not app.pack_build_lock.acquire(blocking=False):
                with app.pack_jobs_lock:
                    job["message"] = "等待上一个打包任务完成……"
                app.pack_build_lock.acquire()
            try:
                with app.pack_jobs_lock:
                    job["message"] = "正在调用 PyInstaller 构建（可能需要数分钟）……"
                result = packaging.pack_project(
                    target, version=version, bump=bump, root=root,
                )
                with app.pack_jobs_lock:
                    job.update(status="ok", message="打包完成", result=result,
                               finished_at=packaging._now_iso())
            except Exception as e:  # noqa: BLE001 - 后台线程必须兜底，错误回传前端
                with app.pack_jobs_lock:
                    job.update(status="failed", message=f"打包失败：{e}", error=str(e),
                               finished_at=packaging._now_iso())
            finally:
                app.pack_build_lock.release()

        threading.Thread(target=worker, daemon=True, name=f"pack-{job_id}").start()
        self._send_json(200, {"ok": True, "job_id": job_id, "message": job["message"]})

    def _pack_status(self, parsed=None) -> None:
        qs = parse_qs(parsed.query) if parsed else {}
        job_id = (qs.get("id") or [""])[0]
        with self.app.pack_jobs_lock:
            job = self.app.pack_jobs.get(job_id)
            snapshot = json.loads(json.dumps(job)) if job else None
        if snapshot is None:
            self._send_json(404, {"ok": False, "message": "打包任务不存在"})
            return
        self._send_json(200, {"ok": True, "job": snapshot})

    def _new_game(self, parsed=None) -> None:
        """新建游戏：POST JSON {name, base_dir?} → base_dir/<name>/ 骨架，并切换当前项目打开它。

        base_dir 缺省时自动推断（当前项目在 games/ 下则建为同级兄弟，否则建 games/）。
        """
        data = self._read_json()
        name = data.get("name", "")
        base_dir = (data.get("base_dir") or "").strip()
        # 基准目录：优先用前端传入的 base_dir；否则自动推断
        if base_dir and os.path.isdir(base_dir):
            base = base_dir
        else:
            proj = os.path.realpath(self.app.project_root)
            parent = os.path.dirname(proj)
            base = parent if os.path.basename(parent) == "games" \
                else os.path.join(proj, "games")
        # P46：主题/对齐选项（缺省 black/left，非法值由 create_game 报中文错误）
        theme = str(data.get("theme") or "black")
        align = str(data.get("align") or "left")
        try:
            # 编辑器里的「新建游戏」= 极简空包：一行可改可删的旁白（@ hello world!），
            # 不预置任何素材；要成品观感可改用 standard 模板。
            root = create_game(name, base, template="hello",
                               theme=theme, align=align)
        except ValueError as e:
            self._send_json(400, {"ok": False, "message": str(e)})
            return
        except OSError as e:
            self._send_json(500, {"ok": False, "message": f"生成游戏失败：{e}"})
            return
        # 自动打开新游戏：切换项目根与默认剧本（素材栏/预览随之指向新目录）
        self.app.project_root = os.path.realpath(str(root))
        self.app.script_path = os.path.join(self.app.project_root, "script.gal")
        self.app.data_root = self.app.project_root
        self._send_json(200, {"ok": True, "path": self.app.project_root,
                              "message": f"已创建游戏「{name}」并打开"})

    def _browse(self, parsed=None) -> None:
        """弹出系统目录选择器，返回用户所选文件夹绝对路径。

        用于「新建游戏」时选择保存位置。服务端进程弹对话框（pywebview/浏览器均可）。
        无桌面会话或用户取消时返回空 path，前端降级为手动输入。
        """
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            sel = filedialog.askdirectory(title="选择游戏保存位置")
            root.destroy()
        except Exception as e:
            self._send_json(200, {"ok": False, "path": "",
                                  "message": f"无法弹出目录选择器：{e}"})
            return
        if not sel:
            self._send_json(200, {"ok": True, "path": "", "message": "已取消选择"})
            return
        self._send_json(200, {"ok": True, "path": os.path.realpath(sel)})

    def _render(self, parsed=None) -> None:
        """卡片视图 → .gal 文本。序列化只在后端一份（复用 parser.dump_text）。"""
        data = self._read_json()
        instructions = data.get("instructions")
        if not isinstance(instructions, list):
            self._send_json(200, {"ok": False, "message": "instructions 必须是数组"})
            return
        cleaned = []
        for i, ins in enumerate(instructions, 1):
            if not isinstance(ins, dict):
                self._send_json(200, {"ok": False,
                                      "message": f"第 {i} 条指令不是对象，无法生成文本"})
                return
            if not ins.get("op"):
                self._send_json(200, {"ok": False,
                                      "message": f"第 {i} 条指令缺少类型（op）"})
                return
            # 剔除运行时/解析期字段，只保留序列化需要的键（line/file/_body_id 不进文本）
            cleaned.append({k: v for k, v in ins.items()
                            if k not in ("line", "file", "_body_id")})
        try:
            text = dump_text(cleaned) if cleaned else ""
        except (ValueError, KeyError, TypeError, AttributeError) as e:
            self._send_json(200, {"ok": False, "message": f"生成剧本失败：{e}"})
            return
        self._send_json(200, {"ok": True, "text": text})

    def _run(self, parsed=None) -> None:
        data = self._read_json()
        text = data.get("text", "")
        rel = data.get("path")
        try:
            # 临时剧本写在正在编辑的文件目录内，使 @include 基准正确
            base_dir = _rel_edit_dir(self.app.project_root, rel) if rel \
                else self.app.project_root
        except ValueError as e:
            self._send_json(400, {"ok": False, "message": str(e)})
            return
        # 先检查语法
        try:
            if rel:
                _parse_rel(text, self.app.project_root, rel)
            else:
                parse_text(text)
        except GalSyntaxError as e:
            self._send_json(400, {"ok": False, **e.to_dict()})
            return
        # 写临时剧本
        fd, tmp_path = tempfile.mkstemp(suffix=".gal", dir=base_dir)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(text)
        except OSError:
            self._send_json(500, {"ok": False, "message": "临时剧本写入失败"})
            return
        # 独立 subprocess 弹真窗口跑 demo，不阻塞编辑器（A3：命令/环境见 _demo_spawn）
        cmd, env = _demo_spawn(tmp_path, self.app.project_root)
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=self.app.project_root,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as e:
            _remove_quiet(tmp_path)
            self._send_json(500, {"ok": False, "message": f"启动 demo 失败：{e}"})
            return

        def _wait_and_cleanup() -> None:
            try:
                proc.wait()
            finally:
                _remove_quiet(tmp_path)

        threading.Thread(target=_wait_and_cleanup, daemon=True).start()
        self._send_json(200, {"ok": True})

    def _get_script(self, parsed=None) -> None:
        path = self.app.script_path
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
        except FileNotFoundError:
            text = ""
        except OSError as e:
            self._send_json(500, {"error": f"读取剧本失败：{e}"})
            return
        self._send_json(200, {"path": path, "text": text})

    def _save_script(self, parsed=None) -> None:
        data = self._read_json()
        text = data.get("text", "")
        req_path = data.get("path")
        try:
            if req_path:
                target = _safe_within(self.app.project_root, req_path)
            else:
                target = self.app.script_path
        except ValueError as e:
            self._send_json(400, {"ok": False, "message": str(e)})
            return
        try:
            with open(target, "w", encoding="utf-8") as f:
                f.write(text)
        except OSError as e:
            self._send_json(500, {"ok": False, "message": f"保存失败：{e}"})
            return
        self._send_json(200, {"ok": True, "path": target})

    # ---- P17 多文件工程路由 ----

    def _handle_files(self, parsed=None) -> None:
        """文件树：递归列出项目下全部 .gal（相对路径）+ 当前打开文件。"""
        root = self.app.project_root
        try:
            files = _list_gal_files(root)
        except OSError as e:
            self._send_json(500, {"ok": False, "message": f"扫描文件失败：{e}"})
            return
        self._send_json(200, {"ok": True, "files": files,
                              "current": _to_rel(root, self.app.script_path, "script.gal")})

    def _handle_file_read(self, parsed) -> None:
        """读单个 .gal 文件内容（realpath 校验必须在项目内）。"""
        q = parse_qs(parsed.query)
        rel = (q.get("path") or [""])[0]
        try:
            target = _rel_gal(self.app.project_root, rel)
        except ValueError as e:
            self._send_json(400, {"ok": False, "message": str(e)})
            return
        try:
            with open(target, "r", encoding="utf-8") as f:
                text = f.read()
        except FileNotFoundError:
            self._send_json(404, {"ok": False, "message": f"文件不存在：{rel}"})
            return
        except OSError as e:
            self._send_json(500, {"ok": False, "message": f"读取文件失败：{e}"})
            return
        self._send_json(200, {"ok": True,
                              "path": _to_rel(self.app.project_root, target, rel),
                              "text": text})

    def _handle_file_save(self, parsed=None) -> None:
        """保存文件：{path, content}；realpath 校验 + 保存前语法校验（坏语法拒绝落盘）。"""
        data = self._read_json()
        rel = (data.get("path") or "").strip()
        content = data.get("content")
        try:
            target = _rel_gal(self.app.project_root, rel)
        except ValueError as e:
            self._send_json(400, {"ok": False, "message": str(e)})
            return
        if not isinstance(content, str):
            self._send_json(400, {"ok": False, "message": "content 必须是字符串"})
            return
        if not os.path.isfile(target):
            self._send_json(404, {"ok": False,
                                  "message": f"文件不存在：{rel}（新章节请用「＋ 新建章节」）"})
            return
        # 保存前语法校验：在目标同目录写临时文件解析（@include 基准正确），坏文件不落盘
        try:
            _check_gal_text(content, os.path.dirname(target))
        except GalSyntaxError as e:
            self._send_json(200, {"ok": False, "line": e.line,
                                  "file": os.path.basename(target),
                                  "message": f"语法错误，未保存：{e.message}"})
            return
        except OSError as e:
            self._send_json(500, {"ok": False, "message": f"语法检查失败：{e}"})
            return
        try:
            with open(target, "w", encoding="utf-8") as f:
                f.write(content)
        except OSError as e:
            self._send_json(500, {"ok": False, "message": f"保存失败：{e}"})
            return
        self._send_json(200, {"ok": True,
                              "path": _to_rel(self.app.project_root, target, rel),
                              "message": "已保存"})

    def _handle_file_new(self, parsed=None) -> None:
        """新建章节：{name}；白名单 + 不覆盖 + 生成教学骨架。"""
        data = self._read_json()
        try:
            rel = _new_chapter(self.app.project_root, data.get("name"))
        except ValueError as e:
            self._send_json(400, {"ok": False, "message": str(e)})
            return
        except OSError as e:
            self._send_json(500, {"ok": False, "message": f"创建章节失败：{e}"})
            return
        self._send_json(200, {"ok": True, "path": rel, "message": f"已创建章节 {rel}"})

    def _handle_labels(self, parsed=None) -> None:
        """跨文件标签大纲：全部 @label（文件+行号）+ @jump 目标（前端据此标注所在文件）。"""
        result = _collect_project_labels(self.app.project_root)
        self._send_json(200, {"ok": True, **result})

    def _handle_include_target(self, parsed) -> None:
        """解析某文件某行的 @include 目标文件（相对当前文件目录，与 parser 同规则）。"""
        q = parse_qs(parsed.query)
        rel = (q.get("path") or [""])[0]
        try:
            line = int((q.get("line") or ["0"])[0])
        except ValueError:
            line = 0
        result = _resolve_include(self.app.project_root, rel, line)
        self._send_json(200 if result.get("ok") else 400, result)

    def _handle_timeline(self, parsed=None) -> None:
        """场景时间线：{text, path?} → 背景/立绘/音频泳道节点 + 选项节点（只算当前文件）。"""
        data = self._read_json()
        text = data.get("text", "")
        rel = data.get("path")
        try:
            if rel:
                instrs = _parse_rel(text, self.app.project_root, rel)
                top = rel
            else:
                instrs, top = _parse_at_root(text, self.app.project_root)
        except ValueError as e:
            self._send_json(400, {"ok": False, "message": str(e)})
            return
        except GalSyntaxError as e:
            self._send_json(200, {"ok": False, "line": e.line, "message": e.message})
            return
        self._send_json(200, {"ok": True, "nodes": extract_timeline(instrs, top)})

    def _handle_scene(self, parsed=None) -> None:
        """当前场景状态：{text, line, path?} → 该行处的 bg / music / 可见立绘。"""
        data = self._read_json()
        text = data.get("text", "")
        rel = data.get("path")
        try:
            line = int(data.get("line") or 1)
        except (TypeError, ValueError):
            line = 1
        try:
            if rel:
                instrs = _parse_rel(text, self.app.project_root, rel)
                top = rel
            else:
                instrs, top = _parse_at_root(text, self.app.project_root)
        except ValueError as e:
            self._send_json(400, {"ok": False, "message": str(e)})
            return
        except GalSyntaxError as e:
            self._send_json(200, {"ok": False, "line": e.line, "message": e.message})
            return
        self._send_json(200, {"ok": True, **scene_state_at(instrs, line, top)})


class EditorApp:
    """编辑器应用：持有项目根目录、数据目录、默认剧本路径；make_handler 返回绑定本实例的处理器类。"""

    def __init__(self, project_root: str, script_path: str | None = None):
        self.project_root = os.path.realpath(project_root)
        self.script_path = script_path or os.path.join(self.project_root, "script.gal")
        # 默认剧本路径必须在项目目录内
        sp = os.path.realpath(self.script_path)
        if sp != self.project_root and not sp.startswith(self.project_root + os.sep):
            raise ValueError(f"--script 路径必须在项目目录内：{script_path}")
        self.script_path = sp
        # 数据目录（素材库）：默认随工程；.editor_config.json 里有存在的自定义目录时用它
        self.data_root = self.project_root
        cfg = _load_editor_config(self.project_root)
        custom = cfg.get("data_root")
        if isinstance(custom, str) and custom and os.path.isdir(custom):
            self.data_root = os.path.realpath(custom)
        self.auto_insert = bool(cfg.get("auto_insert", True))
        # P35 打包发布：后台任务状态（同一时间只允许一个 PyInstaller 构建）
        self.pack_jobs: dict[str, dict] = {}
        self.pack_jobs_lock = threading.Lock()
        self.pack_build_lock = threading.Lock()

    def pack_games_dir(self) -> str:
        """定位 games/ 根：当前项目若已在 games/ 下则取同级目录，否则项目根/games。"""
        proj = self.project_root
        if os.path.basename(os.path.dirname(proj)) == "games":
            return os.path.realpath(os.path.dirname(proj))
        if os.path.basename(proj) == "games":
            return proj
        return os.path.realpath(os.path.join(proj, "games"))

    def pack_root(self) -> str:
        """打包历史/产物根目录：games 的父目录（仓库根），与 CLI 保持一致。"""
        games = self.pack_games_dir()
        return os.path.realpath(os.path.dirname(games))

    def config_info(self) -> dict:
        """设置面板需要的全部字段（路径均为绝对路径，供展示）。"""
        return {
            "ok": True,
            "project_root": self.project_root,
            "data_root": self.data_root,
            "default_data_root": self.project_root,
            "custom_data_root": self.data_root != self.project_root,
            "auto_insert": self.auto_insert,
            "config_path": os.path.join(self.project_root, _EDITOR_CONFIG),
        }

    def _write_config(self) -> str:
        """把当前偏好写回本工程；last_project 用相对路径（移动工程文件夹仍有效）。"""
        cfg = _load_editor_config(self.project_root)
        cfg["version"] = 1
        cfg["last_project"] = "."
        cfg["data_root"] = None if self.data_root == self.project_root else self.data_root
        cfg["auto_insert"] = self.auto_insert
        return _write_editor_config(self.project_root, cfg)

    def apply_config(self, project_root=None, data_root=None, auto_insert=None) -> dict:
        """切换工程 / 修改数据目录 / 自动插指令偏好；返回 {ok, ...} 或中文错误。"""
        if project_root not in (None, ""):
            if not os.path.isabs(str(project_root)):
                return {"ok": False, "message": "工程目录请填写绝对路径（例如 D:\\games\\我的游戏）"}
            p = os.path.realpath(str(project_root))
            if not os.path.isdir(p):
                return {"ok": False, "message": f"工程目录不存在：{project_root}"}
            self.project_root = p
            self.script_path = _default_script(p)
            # 新工程使用它自己的配置（配置跟随工程，不用重设）
            cfg = _load_editor_config(p)
            self.data_root = p
            custom = cfg.get("data_root")
            if isinstance(custom, str) and custom and os.path.isdir(custom):
                self.data_root = os.path.realpath(custom)
            self.auto_insert = bool(cfg.get("auto_insert", True))
        if data_root is not None:
            if str(data_root).strip() == "":
                self.data_root = self.project_root  # 空串 = 恢复默认（随工程）
            else:
                d = str(data_root).strip()
                if not os.path.isabs(d):
                    return {"ok": False, "message": "数据目录请填写绝对路径；留空表示随工程"}
                d = os.path.realpath(d)
                if not os.path.isdir(d):
                    return {"ok": False, "message": f"数据目录不存在：{data_root}"}
                self.data_root = d
        if auto_insert is not None:
            self.auto_insert = bool(auto_insert)
        try:
            self._write_config()
        except OSError as e:
            return {"ok": False, "message": f"配置写入失败：{e}"}
        return self.config_info()

    def make_handler(self):
        """返回请求处理器类（路由表见 _EditorHandler._ROUTES，每路由一个方法）。"""
        app = self

        class Handler(_EditorHandler):
            pass

        Handler.app = app
        return Handler


def serve(project_root: str, port: int = 8000, script_path: str | None = None) -> None:
    """启动编辑器 HTTP 服务（阻塞）。端口被占 → 中文报错退出。"""
    app = EditorApp(project_root, script_path)
    # 清理上次异常退出/被 Windows 占用删不掉的临时剧本（只认 mkstemp 命名，避免误删）
    for dirpath, _dirnames, _filenames in os.walk(app.project_root):
        _cleanup_stale_tmp(dirpath)
    server = ThreadingHTTPServer(("127.0.0.1", port), app.make_handler())
    print(f"MYONL 编辑器已启动：http://127.0.0.1:{port}")
    print(f"项目目录：{app.project_root}")
    print(f"默认剧本：{app.script_path}")
    print("按 Ctrl+C 停止。")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n编辑器已停止。")
    finally:
        server.server_close()


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="engine.editor", description="MYONL 本地 Web 编辑器")
    ap.add_argument("--port", type=int, default=8000, help="监听端口（默认 8000）")
    ap.add_argument("--script", default=None, help="默认打开的剧本路径（必须在项目目录内）")
    ap.add_argument("--project", default=None,
                    help="项目根目录（默认：当前目录；有 .editor_config.json 时用其中 last_project）")
    args = ap.parse_args(argv)
    project = args.project if args.project not in (None, "") else _default_project(os.getcwd())
    try:
        serve(project, args.port, args.script)
    except OSError as e:
        print(f"错误：端口 {args.port} 被占用或无法绑定（{e}），请换个端口重试。", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"错误：{e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
