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
import errno
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, unquote, urlparse
import urllib.error
import urllib.request
from . import packaging
from .newgame import create_game
from . import characters as characters_api
from .parser import GalSyntaxError, dump_text, parse_text
from .sdl_env import dummy_video
# 预览渲染/缓存/补全拆到独立模块，此处按原名导入以保证历史引用不变
from .editor_preview import (
    _PreviewCancelled,
    _completions,
    _preview_cache_clear,
    _preview_cache_get,
    _preview_cache_key,
    _preview_cache_put,
    _preview_is_stale,
    _preview_note_seq,
    _preview_png,
)
# 多文件工程/路径校验拆到独立模块，此处按原名导入以保证历史引用不变
from .editor_project import (
    _ASSET_NAME,
    _check_gal_text,
    _cleanup_stale_tmp,
    _collect_project_labels,
    _list_gal_files,
    _new_chapter,
    _parse_at_root,
    _parse_rel,
    _rel_edit_dir,
    _rel_gal,
    _remove_quiet,
    _resolve_include,
    _safe_within,
    _to_rel,
    extract_timeline,
    scene_state_at,
)

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


# 预览串行锁：pygame 非线程安全，同一时刻只跑一次预览渲染
_preview_lock = threading.Lock()


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
    _write_text_atomic(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
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
    """写工程 config.json（失败抛 OSError 由调用方处理；原子写避免写坏旧配置）。

    写盘前做一次瘦身：**这次新增的、且恰好等于引擎默认值的键**不写进去
    （读取时 `_deep_merge(DEFAULTS, ...)` 会补回来，行为不变）。文件里原本就有的键
    一律原样保留 —— 那是作者自己写的，不能替他删。
    不做这一步的话，编辑器保存一次就把六组默认值铺满 config.json，
    改没改过完全分不出来。
    """
    path = os.path.join(root, "config.json")
    from .config import DEFAULTS as _DEFAULTS

    try:
        with open(path, "r", encoding="utf-8") as f:
            old = json.load(f)
    except (OSError, ValueError):
        old = {}
    slim = _prune_echoed_defaults(data, old if isinstance(old, dict) else {}, _DEFAULTS)
    _write_text_atomic(path, json.dumps(slim, ensure_ascii=False, indent=2) + "\n")
    return path


def _prune_echoed_defaults(new, old, default):
    """删掉「本次新增、等于默认值」的键；old 里已有的键一律保留。"""
    if not isinstance(new, dict):
        return new
    default = default if isinstance(default, dict) else {}
    old = old if isinstance(old, dict) else {}
    out = {}
    for k, v in new.items():
        d = default.get(k)
        if isinstance(v, dict) and isinstance(d, dict):
            sub = _prune_echoed_defaults(v, old.get(k), d)
            if sub or isinstance(old.get(k), dict):
                out[k] = sub if sub else (old.get(k) or {})
            continue
        if k in old:
            out[k] = v
            continue
        if d is not None and v == d:
            continue
        out[k] = v
    return out


def _project_orientation(root: str) -> str:
    """工程想要的画面方向：any（跟随手机）/ portrait / landscape。读坏了一律当 any。"""
    value = str(_load_project_config(root).get("orientation") or "any").strip().lower()
    return value if value in ("any", "portrait", "landscape") else "any"


def _preview_canvas_size(root: str, portrait: bool) -> tuple:
    """预览画布尺寸：尊重工程配的 canvas_size，只按方向摆正长短边。

    以前不管工程是竖屏还是横屏都按 1280×720 出图，手机上看预览就是一条被压扁的横带。
    """
    size = (1280, 720)
    try:
        cs = _load_project_config(root).get("canvas_size")
        if isinstance(cs, (list, tuple)) and len(cs) == 2:
            w, h = int(cs[0]), int(cs[1])
            if w > 0 and h > 0:
                size = (w, h)
    except (TypeError, ValueError):
        pass
    w, h = size
    if portrait and w > h:
        return (h, w)
    if not portrait and h > w:
        return (h, w)
    return (w, h)


def _write_text_atomic(path: str, text: str) -> None:
    """先写同目录临时文件再原子替换：写一半失败时原文件仍是上一版，不留半截剧本。"""
    dir_ = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(suffix=".tmp", dir=dir_)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        _remove_quiet(tmp)
        raise


def _write_error_text(action: str, e: OSError, rel: str) -> str:
    """把写盘失败翻译成可操作中文（只读/占用/磁盘满），不把 Errno 英文原文抛给用户。"""
    if isinstance(e, PermissionError) or getattr(e, "errno", None) in (
            errno.EACCES, errno.EPERM, errno.EROFS):
        return (f"{action}：没有写入权限（{rel}）。文件可能是只读或被其它程序占用，"
                "请取消只读 / 关闭占用后重试")
    if getattr(e, "errno", None) == errno.ENOSPC:
        return f"{action}：磁盘空间不足（{rel}）"
    return f"{action}：{e}"


# UI 设计页「界面开关」：写到项目 settings.json，作为玩家默认值
_UI_INTERFACE_KEYS = ("quickbar_enabled",)


def _as_switch(value) -> int:
    """开关值统一成 0/1：兼容 true/1/"1"/"on" 与 false/0/"0"/"off"。"""
    if isinstance(value, str):
        return 0 if value.strip().lower() in ("", "0", "false", "no", "off") else 1
    return 1 if value else 0


def _interface_settings(root: str) -> dict:
    """读项目 settings.json 的界面开关；缺省回落引擎默认（快捷栏开）。"""
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


_SKIN_STR_KEYS = ("panel_image", "panel_texture")
_ASSET_NAME_RE = re.compile(r"[\w\-. ]{1,64}")


def _clean_dialogue_value(key: str, val: object) -> tuple[bool, object]:
    """P53：dialogue 段写入前的类型清洗（返回 (是否接受, 归一值)）。

    皮肤键都来自前端输入，必须挡住脏数据：
    贴图名只允许项目 images 下的名字（不含目录穿越），
    九宫格四边 / 染色只允许数值，其余数字键只允许数字。
    """
    if key in _SKIN_STR_KEYS:
        if not isinstance(val, str):
            return (False, None)
        name = val.strip()
        if not name:
            return (True, "")
        if ".." in name or "/" in name or "\\" in name:
            return (False, None)
        if not _ASSET_NAME_RE.fullmatch(name):
            return (False, None)
        return (True, name)
    if key == "panel_slice":
        if isinstance(val, bool):
            return (False, None)
        if isinstance(val, (int, float)):
            return (True, max(0, min(4000, int(val))))
        if isinstance(val, (list, tuple)) and len(val) == 4:
            if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in val):
                return (True, [max(0, min(4000, int(v))) for v in val])
        return (False, None)
    if key == "panel_tint":
        if val is None:
            return (True, None)
        if (isinstance(val, (list, tuple)) and len(val) == 3
                and all(isinstance(v, int) and 0 <= v <= 255 for v in val)):
            return (True, [int(v) for v in val])
        return (False, None)
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        return (True, int(val))
    return (False, None)


@dummy_video
def _textbox_png(assets_root: str, dlg_patch: dict, ui_patch: dict,
                 width: int, height: int | None = None) -> bytes:
    """P53：按当前设计导出一张成品 textbox.png（贴图 + 九宫格 + 渐变 + 纹理已完成）。

    导出的图既能给 MYONL 自己当 panel_image 回填，也能直接丢进其它引擎/别的
    工具里用——这是「设计器」而不是「参数面板」的关键：产出物是资产，不是配置。
    """
    from . import dialog_skin
    from .renderer import Renderer
    import pygame

    ren = Renderer(assets_root=assets_root)
    try:
        ren.config.apply_player_ui(dlg_patch)
        ui_cfg = ren.config.data.setdefault("ui", {})
        for k, v in ui_patch.items():
            ui_cfg[k] = v
        dlg = ren.config.dialogue("default")
        width = max(1, int(width))
        height = max(1, int(height or dlg.get("height", 180)))
        name = str(dlg.get("panel_image") or "").strip()
        img = ren._load_image(name) if name else None
        tex_name = str(dlg.get("panel_texture") or "").strip()
        tex = ren._load_image(tex_name) if tex_name else None
        tint_val = dlg.get("panel_tint")
        tint_rgb = (tuple(int(v) for v in tint_val[:3])
                    if isinstance(tint_val, (list, tuple)) and len(tint_val) == 3
                    else None)
        if img is None:
            # 没贴图：用主题 surface 色 + 圆角导出一张等效底图
            surf = dialog_skin.solid_panel(
                width, height, ren.config.theme_color("surface"),
                int(dlg.get("bg_alpha", 150)), int(dlg.get("radius", 10)),
                pixelated=bool(ren.config.pixelated()),
            )
        else:
            surf = dialog_skin.compose_panel(
                img, width, height, dlg.get("panel_slice", 0), tint_rgb,
                int(dlg.get("panel_fade", 0) or 0),
                int(dlg.get("panel_fade_bottom", 0) or 0),
                tex, int(dlg.get("panel_texture_alpha", 0) or 0),
                int(dlg.get("panel_alpha", 255) or 255),
                pixelated=bool(ren.config.pixelated()),
            )
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        tmp.close()
        try:
            pygame.image.save(surf, tmp.name)
            with open(tmp.name, "rb") as f:
                return f.read()
        finally:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass
    finally:
        ren.close()


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
        # P53：皮肤键（贴图/九宫格/渐变/纹理/内边距）不在玩家覆盖白名单里，
        # 预览要单独并进内存配置，否则预览看不见皮肤
        dlg_cfg = ren.config.data.setdefault("dialogue", {}).setdefault("default", {})
        for k, v in dlg_patch.items():
            ok, val = _clean_dialogue_value(k, v)
            if ok and val is not None:
                dlg_cfg[k] = val
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
    (re.compile(r"^@fg\s"), "images"),        # P73 起 @fg 也吃图片名
    (re.compile(r"^@cg\s"), "images"),
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


class _BadJsonBody(Exception):
    """POST 请求体解码失败（截断 / 非 JSON / 非 UTF-8）。由 do_POST 统一回 400。"""


class _EditorHandler(BaseHTTPRequestHandler):
    """编辑器请求处理器：路由集中在 _ROUTES 注册表，每路由一个方法。

    app（EditorApp 实例）由 make_handler 绑定到子类；全部写操作走
    realpath 前缀校验 + 白名单，保存前做语法校验（坏文件不落盘）。
    """

    app = None  # EditorApp 实例（make_handler 绑定）
    _body_cache: bytes | None = None  # 本次请求已读正文，避免流被读两次

    # 路由注册表：(方法, 路径) → 方法名；/api/asset/ 前缀走 do_GET 里的前缀分发
    _ROUTES = {
        ("GET", "/"): "_serve_index",
        ("GET", "/editor.css"): "_serve_editor_css",
        # P65：手机端要能「添加到主屏幕」后全屏（无浏览器工具栏），这是 manifest + 图标
        ("GET", "/manifest.webmanifest"): "_serve_manifest",
        ("GET", "/icon-192.png"): "_serve_icon192",
        ("GET", "/icon-512.png"): "_serve_icon512",
        ("GET", "/editor_pro.js"): "_serve_pro_js",
        # 场景视图（可视化编辑）：独立模块，源码/场景互不覆盖
        ("GET", "/editor_scene.js"): "_serve_scene_js",
        ("GET", "/editor_strip.js"): "_serve_js",
        ("GET", "/asset_shrink.js"): "_serve_js",
        ("GET", "/strip.css"): "_serve_strip_css",
        ("GET", "/editor_characters.js"): "_serve_characters_js",
        ("GET", "/editor_main.js"): "_serve_main_js",
        ("GET", "/editor_utils.js"): "_serve_utils_js",
        # 手机离线内核：没有 Python 时由它顶替全部 /api/*（自带探测，有后端就退出）
        ("GET", "/gal_offline.js"): "_serve_offline_js",
        ("GET", "/parser.js"): "_serve_parser_js",
        ("GET", "/pack.js"): "_serve_pack_js",
        # E9：编辑器三档模式 Level 1–3（前端档位开关，状态存 localStorage）
        ("GET", "/editor_level.js"): "_serve_level_js",
        # T16 域拆分：游戏内 UI 设计区 / 壳层（菜单 + 命令面板 + 教程）
        ("GET", "/editor_uidesign.js"): "_serve_uidesign_js",
        ("GET", "/editor_shell.js"): "_serve_shell_js",
        # P65：手机端工作台（工程卡片第一层）
        ("GET", "/editor_home.js"): "_serve_home_js",
        # 设置里的「插线推送到手机」面板（P88 砍扫码、P89 砍 AI）
        ("GET", "/editor_link.js"): "_serve_link_js",
        # P171：浏览器里的 v2 签名（手机端出 APK 靠它）
        ("GET", "/apk_sign.js"): "_serve_apk_sign_js",
        # P76：手机端多层交互（外观分组钻取 / 素材看大图）
        ("GET", "/editor_mobile.js"): "_serve_mobile_js",
        # 版本快照（每次保存前把上一版留一份，独立 IndexedDB）
        ("GET", "/editor_snapshots.js"): "_serve_snapshots_js",
        # P67：游戏画面方向（any / portrait / landscape），存进工程 config.json
        ("GET", "/api/orientation"): "_get_orientation",
        ("POST", "/api/orientation"): "_set_orientation",
        # P67：工作台卡片缩略图（工程 icon.png，没有就退到 images/ 第一张）
        ("GET", "/api/thumb"): "_serve_thumb",
        # P178：作品体积体检（素材多大、还能不能单文件发）
        ("GET", "/api/asset-scan"): "_serve_asset_scan",
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
        ("POST", "/api/ui-design/export-textbox"): "_ui_design_export_textbox",
        ("POST", "/api/export-web"): "_export_web",
        ("POST", "/api/export-single"): "_export_single",
        ("POST", "/api/export-portable"): "_export_portable",
        ("POST", "/api/export-apk"): "_export_apk",
        # P88：手机「连接」（扫码 / 局域网发现）砍了 —— 只剩插线推成品。
        # 素材互传交给数据线（手机当 U 盘 / 文件管理器），不再自己做一套同步。
        ("GET", "/api/adb"): "_adb_get",
        ("POST", "/api/adb"): "_adb_push",
        ("GET", "/api/complete"): "_complete",
        ("GET", "/api/files"): "_handle_files",
        # P65：手机端工作台（工程卡片列表 / 点卡片切换工程）
        ("GET", "/api/home"): "_home",
        ("POST", "/api/project"): "_switch_project",
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
        ("POST", "/api/import_url"): "_import_url",
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
        ("GET", "/api/version"): "_app_version",
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

    def _send_png(self, png: bytes) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(png)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(png)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            # 客户端已发起新一轮请求并中断连接：正常现象，不写错误日志
            pass

    def _send_no_content(self) -> None:
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _read_json(self) -> dict:
        """读 POST JSON。空 body 返 {}；解码失败抛 _BadJsonBody（do_POST 统一回 400）。

        A3：以前坏 body（截断/非 JSON/编码错）和空 body 一样静默回 {}，
        保存/角色库等路由拿到空 dict 后蒙过校验落盘，把剧本/角色清空，
        前端还收到 200 ok:true。现在坏 body 抛错，在进业务路由前就被拦下。
        返回值收窄成 dict（不再是 dict | None），调用方直接 .get 即可。
        """
        if self._body_cache is None:
            length = int(self.headers.get("Content-Length", 0) or 0)
            self._body_cache = self.rfile.read(length) if length else b""
        raw = self._body_cache
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise _BadJsonBody("请求体不是合法 JSON") from exc

    # ---- 分发（只做路由，不含业务） ----

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/asset/"):
            self._get_asset(parsed.path)
            return
        if parsed.path.startswith("/web-preview/"):
            self._serve_web_preview(parsed.path)
            return
        if parsed.path.startswith("/single-file/"):
            self._serve_single_file(parsed.path)
            return
        if parsed.path.startswith("/portable-file/"):
            self._serve_portable_file(parsed.path)
            return
        if parsed.path.startswith("/apk-file/"):
            self._serve_apk_file(parsed.path)
            return
        # P171：前端要自己算 v2 签名，得先拿到模板和签名材料
        if parsed.path == "/template.apk":
            self._serve_template_apk()
            return
        if parsed.path == "/signkey.json":
            self._serve_signkey()
            return
        self._dispatch("GET", parsed)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        name = self._ROUTES.get(("POST", parsed.path))
        if name is None:
            self._send_json(404, {"error": "不存在的路由"})
            return
        handler = getattr(self, name)
        # A3：先读 body；坏 JSON 在进业务路由前就回 400，避免空 dict 蒙过校验落盘
        try:
            self._read_json()
        except _BadJsonBody as exc:
            self._send_json(400, {"ok": False, "message": str(exc)})
            return
        handler(parsed)

    def _dispatch(self, method: str, parsed) -> None:
        name = self._ROUTES.get((method, parsed.path))
        if name is None:
            self._send_json(404, {"error": "不存在的路由"})
            return
        getattr(self, name)(parsed)

    # ---- 路由实现 ----

    def _serve_editor_file(self, name: str, mime: str) -> None:
        p = os.path.join(_editor_front_dir(), name)
        if not os.path.isfile(p):
            # parser.js / pack.js 是内核，住在 engine/，电脑端和手机端共用同一份
            p = os.path.join(os.path.dirname(os.path.abspath(__file__)), name)
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

    def _serve_js(self, parsed=None) -> None:
        self._serve_editor_file(parsed.path.lstrip("/"), "application/javascript; charset=utf-8")

    def _serve_strip_css(self, parsed=None) -> None:
        self._serve_editor_file("strip.css", "text/css; charset=utf-8")

    # ---- P65：手机端 PWA（添加到主屏幕后全屏，不显示浏览器工具栏）----

    def _serve_manifest(self, parsed=None) -> None:
        self._serve_editor_file("manifest.webmanifest", "application/manifest+json; charset=utf-8")

    def _serve_icon192(self, parsed=None) -> None:
        self._serve_editor_file("icon-192.png", "image/png")

    def _serve_icon512(self, parsed=None) -> None:
        self._serve_editor_file("icon-512.png", "image/png")

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

    def _serve_utils_js(self, parsed=None) -> None:
        self._serve_editor_file("editor_utils.js", "application/javascript; charset=utf-8")

    def _serve_offline_js(self, parsed=None) -> None:
        """手机离线内核。电脑端把它服务出去也没关系——它自带探测，
        有 Python 后端时会立刻 return 不劫持 fetch。"""
        self._serve_editor_file("gal_offline.js", "application/javascript; charset=utf-8")

    def _serve_parser_js(self, parsed=None) -> None:
        """JS 解析器：手机端靠它把 .gal 编成指令，和 engine/parser.py 逐字段一致。"""
        self._serve_editor_file("parser.js", "application/javascript; charset=utf-8")

    def _serve_pack_js(self, parsed=None) -> None:
        """JS 打包器：手机端靠它把指令 + 素材拼成单文件成品 HTML。"""
        self._serve_editor_file("pack.js", "application/javascript; charset=utf-8")

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

    def _serve_home_js(self, parsed=None) -> None:
        self._serve_editor_file("editor_home.js", "application/javascript; charset=utf-8")

    def _serve_link_js(self, parsed=None) -> None:
        self._serve_editor_file("editor_link.js", "application/javascript; charset=utf-8")

    def _serve_mobile_js(self, parsed=None) -> None:
        self._serve_editor_file("editor_mobile.js", "application/javascript; charset=utf-8")

    def _serve_snapshots_js(self, parsed=None) -> None:
        self._serve_editor_file("editor_snapshots.js", "application/javascript; charset=utf-8")

    def _serve_apk_sign_js(self, parsed=None) -> None:
        self._serve_editor_file("apk_sign.js", "application/javascript; charset=utf-8")

    def _check(self, parsed=None) -> None:
        data = self._read_json()
        text = data.get("text", "")
        rel = data.get("path")
        # 新一轮检查开始即视为旧预览过期，服务端可在帧间放弃旧渲染
        _preview_note_seq(data.get("client"), data.get("seq"))
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
        client = data.get("client")
        seq = data.get("seq")
        # 同一标签页新序号一到，旧预览即为过期；渲染循环每帧检查一次
        _preview_note_seq(client, seq)
        stale = lambda: _preview_is_stale(client, seq)
        # 预览画布跟着工程方向走：竖屏工程（手机优先）不能拿 1280×720 去缩放，
        # 那会把画面压扁，还会让人以为背景没渲染
        proj_root = self._current_project_root()
        portrait = data.get("portrait")
        orient = _project_orientation(proj_root)
        if orient == "portrait":
            portrait = True
        elif orient == "landscape":
            portrait = False
        size = _preview_canvas_size(proj_root, bool(portrait))
        try:
            # 临时剧本写在正在编辑的文件目录内，使 @include 基准正确
            base_dir = _rel_edit_dir(self.app.project_root, rel) if rel \
                else self.app.project_root
        except ValueError as e:
            self._send_json(400, {"ok": False, "message": str(e)})
            return
        # 素材根必须是工程目录（剧本所在目录）：以前传的是启动目录，
        # 于是 @bg / @show 全都找不到图片，预览里只剩一个灰色人影
        cache_key = _preview_cache_key(text, base_dir, proj_root, frames, size)
        cached = _preview_cache_get(cache_key)
        if cached is not None:
            self._send_png(cached)
            return
        # 排队前再判一次：已被更新输入取代的请求不再解析/写临时文件
        if stale():
            self._send_no_content()
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
                acquired = False
                try:
                    # 等待渲染锁时持续轮询取消标记：已被新输入取代的请求不必排到队头
                    while True:
                        if _preview_lock.acquire(timeout=0.05):
                            acquired = True
                            break
                        if stale():
                            self._send_no_content()
                            return
                    # 排队期间用户已继续编辑：不再白跑这次渲染
                    if stale():
                        self._send_no_content()
                        return
                    png = _preview_png(tmp_path, proj_root, frames,
                                       cancel=stale, size=size)
                finally:
                    if acquired:
                        _preview_lock.release()
            except _PreviewCancelled:
                self._send_no_content()
                return
            except Exception as e:
                self._send_json(500, {"ok": False, "message": f"预览渲染失败：{e}"})
                return
        finally:
            _remove_quiet(tmp_path)
        _preview_cache_put(cache_key, png)
        self._send_png(png)

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
        """素材清单（只列文件名，不读内容）。

        优先扫「当前剧本所在目录」：`--script games/x/script.gal` 启动时
        `app.data_root` 还指着仓库根，扫出来是全空的 —— 前端拿着空清单会
        把每条 @bg / @show 都标成「缺素材」，而图其实都在工程目录里。
        """
        try:
            assets = _scan_assets(self._current_project_root())
            if not any(assets.values()):
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

    # ==================== 插线推送到手机（P88/P89 之后只剩这一块） ====================

    def _server_port(self) -> int:
        addr = getattr(self.server, "server_address", ())
        if isinstance(addr, tuple) and len(addr) > 1:
            try:
                return int(addr[1])
            except (TypeError, ValueError):
                pass
        return 8790

    def _adb_get(self, parsed=None) -> None:
        from . import mobile_link

        self._send_json(200, mobile_link.adb_state())

    def _adb_push(self, parsed=None) -> None:
        """把导出的单文件推到手机的 Download/MYONL/（需要插线 + USB 调试）。"""
        from . import mobile_link

        data = self._read_json()
        root = str(getattr(self.app, "project_root", "") or "")
        pack_root_fn = getattr(self.app, "pack_root", None)
        if not root or not callable(pack_root_fn):
            self._send_json(400, {"ok": False, "message": "还没打开工程"})
            return
        folder = os.path.basename(os.path.normpath(root))
        single = os.path.join(str(pack_root_fn()), "dist", "single", folder + ".html")
        if not os.path.isfile(single):
            self._send_json(400, {"ok": False,
                                  "message": "还没导出单文件：先在「导出」里导一次，再推到手机"})
            return
        mode = str(data.get("mode") or "simple").strip()
        if mode == "simple":     # 只检测，不推
            self._send_json(200, mobile_link.adb_state())
            return
        self._send_json(200, mobile_link.adb_push(single))

    # ==================== P51/P52：UI 设计区（独立于剧本编辑） ====================

    # 玩家/开发者可在 UI 设计区调整的键（其余 ui/dialogue 键保持项目 config.json 原样）
    # P52：扩为六组——对话框 / 名字框 / 选项 / 快捷栏 / 游戏内菜单 / 设置页
    _UI_DESIGN_UI_KEYS = ("pixelated", "pixel_scale", "corner_radius")
    _UI_DESIGN_DLG_KEYS = ("radius", "offset_x", "offset_y", "panel_width", "height",
                           "name_y", "name_gap",   # P52：名字框（y/间距）并入对话框组
                           # P53：对话框皮肤（贴图九宫格 / 渐变蒙版 / 纹理 / 内边距）
                           "panel_image", "panel_slice", "panel_tint",
                           "panel_fade", "panel_fade_bottom", "panel_texture",
                           "panel_texture_alpha", "panel_alpha", "pad_x", "pad_y")
    _UI_DESIGN_CHOICES_KEYS = ("width", "row_height", "dialog_gap", "radius", "gap", "bg", "fg")
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
        root = self._current_project_root()
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
        # 界面开关（项目 settings.json 的玩家默认值）：快捷栏显隐
        resp["interface"] = _interface_settings(root)
        self._send_json(200, {"ok": True, **resp})

    def _ui_design_set(self, parsed=None) -> None:
        """把 UI 设计字段写回项目 config.json（白名单键，其余键原样保留）。

        六组：ui 顶层（pixelated 等）、dialogue.default（含名字框）、
        ui.choices / ui.quickbar / ui.menu / ui.settings、font、line_height。
        """
        data = self._read_json()
        root = self._current_project_root()
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
                        ok, val = _clean_dialogue_value(k, dlg_patch[k])
                        if not ok:
                            continue
                        # P53：None（如 panel_tint）= 清掉覆盖，回落引擎默认
                        if val is None:
                            dlg.pop(k, None)
                        else:
                            dlg[k] = val
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
                    if k not in patch:
                        continue
                    # 选项按钮的两个颜色：只收 #rrggbb 或空串（空 = 跟随主题）
                    if name == "choices" and k in ("bg", "fg"):
                        val = str(patch[k] or "").strip()
                        if val and not re.fullmatch(r"#[0-9a-fA-F]{6}", val):
                            continue
                        sec[k] = val
                        continue
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
                png = _ui_design_png(self._current_project_root(), ui_patch, dlg_patch,
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

    def _ui_design_export_textbox(self, parsed=None) -> None:
        """P53：把当前对话框设计导出成成品 textbox.png，写进项目 images/。

        产出的是「资产」不是「配置」——可以直接当 panel_image 回填，
        也可以拿去给其它引擎/PS 流程用（尺寸按画布宽 × 面板高，与引擎同帧一致）。
        """
        data = self._read_json()
        dlg_patch = data.get("dialogue")
        ui_patch = data.get("ui")
        dlg_patch = dlg_patch if isinstance(dlg_patch, dict) else {}
        ui_patch = ui_patch if isinstance(ui_patch, dict) else {}
        root = str(getattr(self.app, "project_root", "") or "")
        if not root:
            self._send_json(400, {"ok": False, "message": "还没打开工程，无法导出"})
            return
        raw_name = str(data.get("name") or "").strip() or "textbox_export"
        if not re.fullmatch(r"[\w\-]{1,40}", raw_name):
            self._send_json(400, {"ok": False,
                                  "message": "导出名只能含字母/数字/下划线/短横线"})
            return
        try:
            cfg = _load_project_config(root) or {}
            size = cfg.get("canvas_size") or [1280, 720]
            width = int(size[0]) if isinstance(size, (list, tuple)) and size else 1280
            png = _textbox_png(root, dlg_patch, ui_patch, width, None)
        except Exception as e:   # noqa: BLE001 - 统一回给前端一句人话
            self._send_json(500, {"ok": False, "message": f"导出面板失败：{e}"})
            return
        out_dir = os.path.join(root, "images")
        path = os.path.join(out_dir, raw_name + ".png")
        # 重名不静默覆盖：用户可能已有同名素材（甚至就是那张正在用的皮肤图），
        # 必须先由前端确认再带 overwrite=true 重发，避免误删别人的画。
        if os.path.exists(path) and not data.get("overwrite"):
            self._send_json(409, {"ok": False, "exists": True,
                                  "message": f"images/{raw_name}.png 已存在，确认覆盖？"})
            return
        try:
            os.makedirs(out_dir, exist_ok=True)
            tmp = path + ".tmp"
            with open(tmp, "wb") as f:
                f.write(png)
            os.replace(tmp, path)
        except OSError as e:
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except OSError:
                pass
            self._send_json(500, {"ok": False, "message": f"写入图片失败：{e}"})
            return
        self._send_json(200, {"ok": True, "path": path, "name": raw_name,
                              "url": "/api/asset/images/" + raw_name,
                              "bytes": len(png), "width": width})

    def _export_web(self, parsed=None) -> None:
        """P54：把当前工程编译成「手机网页包」（竖屏/横屏都能跑）。

        和打包 exe 是两条腿：exe 给桌面、静态网页包给手机和 itch.io 这类平台。
        编译器在 engine/webpack.py，播放器在 web/，这里只负责串起来 + 给个预览地址。
        """
        from . import webpack as webpack_mod

        data = self._read_json()
        root = str(getattr(self.app, "project_root", "") or "")
        if not root or not os.path.isdir(root):
            self._send_json(400, {"ok": False, "message": "还没打开工程，无法导出"})
            return
        folder = os.path.basename(os.path.normpath(root))
        pack_root_fn = getattr(self.app, "pack_root", None)   # 类型上 app 可能是 None
        if not callable(pack_root_fn):
            self._send_json(500, {"ok": False, "message": "编辑器没有发行根，无法导出"})
            return
        out = os.path.join(str(pack_root_fn()), "dist", "web", folder)
        title = str(data.get("title") or "").strip()
        try:
            stat = webpack_mod.build_web(root, out, title=title)
        except Exception as e:   # noqa: BLE001 — 统一回一句人话
            self._send_json(500, {"ok": False, "message": f"导出手机版失败：{e}"})
            return
        self._send_json(200, {
            "ok": True,
            "out": stat["out"],
            "url": "/web-preview/" + folder + "/index.html",
            "instructions": stat["instructions"],
            "images": stat["images"],
            "missing": stat["missing"],
            "unsupported": stat["unsupported"],
        })

    def _export_portable(self, parsed=None) -> None:
        """P56：把当前工程导成「别的引擎能吃的文件」（Ren'Py 工程 / 通用 JSON）。

        这是防锁死的一层：作者随时可以把剧本+素材带走，不被 MYONL 自己的播放器绑住。
        body 里 engine=renpy|json|both，默认 both。
        """
        import zipfile

        from . import portable as portable_mod

        data = self._read_json()
        root = str(getattr(self.app, "project_root", "") or "")
        if not root or not os.path.isdir(root):
            self._send_json(400, {"ok": False, "message": "还没打开工程，无法导出"})
            return
        engine = str(data.get("engine") or "both").strip().lower()
        if engine not in ("renpy", "json", "both"):
            self._send_json(400, {"ok": False, "message": "engine 只能是 renpy / json / both"})
            return
        pack_root_fn = getattr(self.app, "pack_root", None)
        if not callable(pack_root_fn):
            self._send_json(500, {"ok": False, "message": "编辑器没有发行根，无法导出"})
            return
        folder = os.path.basename(os.path.normpath(root))
        out = os.path.join(str(pack_root_fn()), "dist", "portable", folder)
        try:
            res = portable_mod.build_portable(root, out, engine=engine)
        except Exception as e:   # noqa: BLE001 — 统一回一句人话
            self._send_json(500, {"ok": False, "message": f"导出可迁移包失败：{e}"})
            return

        items = []
        for stat in res["stats"]:
            zip_path = os.path.join(str(pack_root_fn()), "dist", "portable",
                                    f"{folder}-{stat['engine']}.zip")
            if os.path.isfile(zip_path):
                os.remove(zip_path)
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for base, _dirs, files in os.walk(stat["out"]):
                    for name in files:
                        full = os.path.join(base, name)
                        arc = os.path.join(folder + "-" + stat["engine"],
                                           os.path.relpath(full, stat["out"]))
                        zf.write(full, arc.replace(os.sep, "/"))
            items.append({
                "engine": stat["engine"],
                "out": stat["out"],
                "zip": zip_path,
                "zip_mb": round(os.path.getsize(zip_path) / (1024 * 1024), 2),
                "instructions": stat["instructions"],
                "images": stat["images"],
                "missing": stat["missing"],
                "unsupported": stat["unsupported"],
                "url": "/portable-file/" + f"{folder}-{stat['engine']}.zip",
            })
        self._send_json(200, {"ok": True, "out": res["out"], "items": items})

    def _serve_portable_file(self, path: str) -> None:
        """下载导出的可迁移包 zip（只有 dist/portable 下的 *.zip 放行）。"""
        rel = unquote(path[len("/portable-file/"):])
        pack_root_fn = getattr(self.app, "pack_root", None)
        base = os.path.join(str(pack_root_fn()) if callable(pack_root_fn) else "",
                            "dist", "portable")
        try:
            target = _safe_within(base, rel)
        except ValueError:
            self._send_json(400, {"error": "下载路径不合法"})
            return
        if not target.lower().endswith(".zip") or not os.path.isfile(target):
            self._send_json(404, {"error": "可迁移包不存在，先点一次「导出可迁移包」"})
            return
        try:
            with open(target, "rb") as f:
                body = f.read()
        except OSError as e:
            self._send_json(500, {"error": f"读导出包失败：{e}"})
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Length", str(len(body)))
        # 中文文件名走 RFC 5987，直接塞进 filename= 会被浏览器截成空串
        self.send_header("Content-Disposition",
                         "attachment; filename*=UTF-8''" +
                         quote(os.path.basename(target), safe=""))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _serve_web_preview(self, path: str) -> None:
        """服务「导出手机版」的产物目录，让作者点一下就真在浏览器里跑起来。

        只认 /web-preview/<工程文件夹>/<相对路径>，且整条路径必须落在
        <pack_root>/web 里，防止 ../ 之类的越界读取。
        """
        rel = path[len("/web-preview/"):]
        pack_root_fn = getattr(self.app, "pack_root", None)
        base = os.path.join(str(pack_root_fn()) if callable(pack_root_fn) else "", "dist", "web")
        try:
            target = _safe_within(base, unquote(rel))
        except ValueError:
            self._send_json(400, {"error": "预览路径不合法"})
            return
        if not os.path.isfile(target):
            self._send_json(404, {"error": "预览文件不存在，先点一次「导出手机版」"})
            return
        ext = os.path.splitext(target)[1].lower()
        mime = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
                ".json": "application/json; charset=utf-8", ".png": "image/png",
                ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
                ".ogg": "audio/ogg", ".mp3": "audio/mpeg", ".wav": "audio/wav"}.get(
                    ext, "application/octet-stream")
        try:
            with open(target, "rb") as f:
                body = f.read()
        except OSError as e:
            self._send_json(500, {"error": f"读预览文件失败：{e}"})
            return
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _export_single(self, parsed=None) -> None:
        """P61：导出一个 .html 单文件游戏（图片内嵌、播放器内联）。

        分目录的网页包发不了、手机上点不开；单文件版可以用手机浏览器直接打开，
        也能当作品发出去——这是「做完能交出去」的形态。
        """
        from . import webpack as webpack_mod

        data = self._read_json()
        root = str(getattr(self.app, "project_root", "") or "")
        if not root or not os.path.isdir(root):
            self._send_json(400, {"ok": False, "message": "还没打开工程，无法导出"})
            return
        pack_root_fn = getattr(self.app, "pack_root", None)
        if not callable(pack_root_fn):
            self._send_json(500, {"ok": False, "message": "编辑器没有发行根，无法导出"})
            return
        folder = os.path.basename(os.path.normpath(root))
        out = os.path.join(str(pack_root_fn()), "dist", "single", folder + ".html")
        title = str(data.get("title") or "").strip()
        try:
            stat = webpack_mod.build_single(root, out, title=title)
        except Exception as e:   # noqa: BLE001 — 统一回一句人话
            self._send_json(500, {"ok": False, "message": f"导出单文件失败：{e}"})
            return
        self._send_json(200, {
            "ok": True,
            "out": stat["out"],
            "url": "/single-file/" + folder + ".html",
            "kb": round(stat["bytes"] / 1024),
            "instructions": stat["instructions"],
            "images": stat["images"],
            "audio": stat.get("audio", 0),
            "saved_kb": round(stat.get("saved", 0) / 1024),
            "missing": stat["missing"],
            # P130：build_single 早就在算体积告警（40 MB / 80 MB 两档），
            # 但这两个字段一直没往接口递 —— 作者导出完看到"导出成功"就走人，
            # 手机上打开卡半天根本不知道为什么。现在原样透传，前端负责显示。
            "file_mb": stat.get("file_mb", 0),
            "file_warning": stat.get("file_warning", ""),
            "file_warning_level": stat.get("file_warning_level", ""),
        })

    def _export_apk(self, parsed=None) -> None:
        """把当前工程打成一个能直接装的 APK。

        原理一句话：模板 APK 里 `assets/game.html` 就是作品本体，换掉它、再按
        同一张证书重签 v2，装到手机上就是新作品。这也是 Yop2D 那种「手机端一键出包」
        的真实机制——不需要在手机上跑 Android 构建链。

        需要 Java 来做 RSA 签名（沿 apksig 官方库，手写 v2 字节流试过，容易错）。
        """
        import subprocess
        import zipfile

        from . import webpack as webpack_mod

        data = self._read_json()
        root = str(getattr(self.app, "project_root", "") or "")
        if not root or not os.path.isdir(root):
            self._send_json(400, {"ok": False, "message": "还没打开工程，无法导出"})
            return
        pack_root_fn = getattr(self.app, "pack_root", None)
        if not callable(pack_root_fn):
            self._send_json(500, {"ok": False, "message": "编辑器没有发行根，无法导出"})
            return
        base = str(pack_root_fn())
        folder = os.path.basename(os.path.normpath(root))
        single = os.path.join(base, "dist", "single", folder + ".html")
        title = str(data.get("title") or "").strip() or folder
        try:
            webpack_mod.build_single(root, single, title=title)
        except Exception as e:   # noqa: BLE001 — 统一回一句人话
            self._send_json(500, {"ok": False, "message": f"导不出单文件，APK 也就打不了：{e}"})
            return

        template = os.path.join(base, "android", "template.apk")
        signer = os.path.join(base, "tools", "vendor", "uber-apk-signer.jar")
        keystore = os.path.join(base, "android", "keystore", "myonl-test.p12")
        for path, what in ((template, "模板 APK"), (signer, "签名器"), (keystore, "签名证书")):
            if not os.path.isfile(path):
                self._send_json(400, {
                    "ok": False,
                    "message": f"缺{what}：{os.path.relpath(path, base)}",
                })
                return

        java = shutil.which("java") or ""
        if not java:
            jh = os.environ.get("JAVA_HOME", "")
            cand = os.path.join(jh, "bin", "java.exe" if os.name == "nt" else "java")
            java = cand if jh and os.path.isfile(cand) else ""
        if not java:
            self._send_json(400, {
                "ok": False,
                "need_java": True,
                "message": "这台电脑没有 Java，打不了 APK。装一个 JRE 17+ 就行"
                           "（zip 版解压后把 bin 加进 PATH）：https://adoptium.net",
            })
            return

        out_dir = os.path.join(base, "dist", "apk")
        os.makedirs(out_dir, exist_ok=True)
        unsigned = os.path.join(out_dir, "wip-unsigned.apk")
        final = os.path.join(out_dir, folder + ".apk")
        try:
            payload = open(single, "rb").read()
            with zipfile.ZipFile(template) as zin, zipfile.ZipFile(unsigned, "w") as zout:
                for item in zin.infolist():
                    blob = (payload if item.filename == "assets/game.html"
                            else zin.read(item.filename))
                    info = zipfile.ZipInfo(item.filename, date_time=item.date_time)
                    info.compress_type = item.compress_type
                    info.external_attr = item.external_attr
                    info.internal_attr = item.internal_attr
                    info.create_system = item.create_system
                    zout.writestr(info, blob)

            # 密码从环境变量读；没设就用这张公开测试证书的默认口令
            ks_pass = os.environ.get("MYONL_STORE_PASS", "").strip() or "myonl-apk-2026"
            proc = subprocess.run(
                [java, "-jar", signer, "--apks", unsigned,
                 "--ks", keystore, "--ksAlias", "myonl",
                 "--ksPass", ks_pass, "--ksKeyPass", ks_pass,
                 "--allowResign", "--skipZipAlign", "--out", out_dir],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=180,
            )
            log = (proc.stdout or "") + (proc.stderr or "")
            if "signature verified" not in log:
                self._send_json(500, {
                    "ok": False,
                    "message": "重签没过（Java 那边报错）：" + log[-600:],
                })
                return
            produced = [p for p in os.listdir(out_dir) if p.endswith("-signed.apk")]
            if not produced:
                self._send_json(500, {"ok": False, "message": "重签跑完了，但没找到产物"})
                return
            if os.path.exists(final):
                os.remove(final)
            os.replace(os.path.join(out_dir, produced[0]), final)
        except subprocess.TimeoutExpired:
            self._send_json(500, {"ok": False, "message": "签名超时（180 秒没跑完）"})
            return
        finally:
            if os.path.exists(unsigned):
                try:
                    os.remove(unsigned)
                except OSError:
                    pass

        size = os.path.getsize(final)
        self._send_json(200, {
            "ok": True,
            "out": final,
            "url": "/apk-file/" + folder + ".apk",
            "mb": round(size / 1048576, 2),
            "message": "打好了。传到手机上点开就能装，第一次会问一次「未知来源」。",
        })

    def _serve_single_file(self, path: str) -> None:
        """下载/预览单文件游戏：/single-file/<名字>.html"""
        rel = path[len("/single-file/"):]
        pack_root_fn = getattr(self.app, "pack_root", None)
        base = os.path.join(str(pack_root_fn()) if callable(pack_root_fn) else "", "dist", "single")
        try:
            target = _safe_within(base, unquote(rel))
        except ValueError:
            self._send_json(400, {"error": "路径不合法"})
            return
        if not os.path.isfile(target):
            self._send_json(404, {"error": "还没有这个单文件，先点一次「导出单文件」"})
            return
        try:
            with open(target, "rb") as f:
                body = f.read()
        except OSError as e:
            self._send_json(500, {"error": f"读文件失败：{e}"})
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _serve_apk_file(self, path: str) -> None:
        """下载 APK：/apk-file/<名字>.apk"""
        rel = path[len("/apk-file/"):]
        pack_root_fn = getattr(self.app, "pack_root", None)
        base = os.path.join(str(pack_root_fn()) if callable(pack_root_fn) else "", "dist", "apk")
        try:
            target = _safe_within(base, unquote(rel))
        except ValueError:
            self._send_json(400, {"error": "路径不合法"})
            return
        if not os.path.isfile(target):
            self._send_json(404, {"error": "还没有这个 APK，先点一次「打成 APK」"})
            return
        try:
            with open(target, "rb") as f:
                body = f.read()
        except OSError as e:
            self._send_json(500, {"error": f"读文件失败：{e}"})
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/vnd.android.package-archive")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Disposition",
                         f'attachment; filename="{quote(rel)}"')
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _serve_template_apk(self) -> None:
        """把模板 APK 递给前端，让它在浏览器里自己换壳 + 签 v2。"""
        pack_root_fn = getattr(self.app, "pack_root", None)
        base = str(pack_root_fn()) if callable(pack_root_fn) else ""
        target = os.path.join(base, "android", "template.apk")
        if not os.path.isfile(target):
            self._send_json(404, {"error": "缺模板 APK：android/template.apk"})
            return
        body = open(target, "rb").read()
        self.send_response(200)
        self.send_header("Content-Type", "application/vnd.android.package-archive")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _serve_signkey(self) -> None:
        """签名材料（私钥 + 证书 + 公钥）。

        这是公开的测试证书，本来就在仓库里当开发用；真发行得换成自己的。
        """
        pack_root_fn = getattr(self.app, "pack_root", None)
        base = str(pack_root_fn()) if callable(pack_root_fn) else ""
        target = os.path.join(base, "editor", "signkey.json")
        if not os.path.isfile(target):
            self._send_json(404, {
                "error": "缺签名材料：editor/signkey.json",
                "hint": "跑一次 python tools/export_signkey.py 生成",
            })
            return
        body = open(target, "rb").read()
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _resolve_asset(self, category: str, name: str) -> str | None:
        """按类别取素材文件：先当前作品目录，再数据目录。

        `--script games/x/script.gal` 启动时这两个根不是一回事，
        素材列表已经按作品目录扫，取图也必须用同一个根，否则列表有、点开 404。
        """
        roots = [self._current_project_root()]
        if self.app is not None:
            roots.append(self.app.data_root)
        for root in roots:
            if not root:
                continue
            found = _find_asset_file(root, category, name)
            if found:
                return found
        return None

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
            found = self._resolve_asset(category, name) if _ASSET_NAME.fullmatch(name) else None
        else:
            if not _ASSET_NAME.fullmatch(category):
                self._send_json(400, {"ok": False, "message": f"非法素材名：{category}"})
                return
            name = category
            found = None
            for cat in ("images", "videos", "anims", "audio", "fonts"):
                found = self._resolve_asset(cat, name) or found
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
        if result.get("ok"):
            # 素材变化会影响预览画面，清空内容哈希缓存
            _preview_cache_clear()
        self._send_json(200 if result.get("ok") else 400, result)

    def _import_url(self, parsed=None) -> None:
        """从网址把素材抓下来存进素材库：POST JSON {category?, url, filename?, overwrite?}。

        为什么不让前端自己 fetch：多数图床不带 CORS 头，浏览器读不到二进制；
        手机上更会被直接拦掉。后端没有这个限制。
        抓下来就是本地文件，导出时照样内嵌成单文件——不依赖对方服务器还活着。
        """
        data = self._read_json()
        url = (data.get("url") or "").strip()
        if not url.lower().startswith(("http://", "https://")):
            self._send_json(400, {"ok": False, "message": "只收 http:// 或 https:// 开头的网址"})
            return
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (compatible; MYONL/1.2)",
            })
            with urllib.request.urlopen(req, timeout=20) as resp:
                raw = resp.read()
                ctype = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        except urllib.error.HTTPError as e:
            self._send_json(400, {"ok": False, "message": f"下载失败：服务器返回 {e.code}"})
            return
        except Exception as e:
            self._send_json(400, {"ok": False, "message": f"下载失败：{e}"})
            return
        if not raw:
            self._send_json(400, {"ok": False, "message": "下载到的是空文件"})
            return
        if len(raw) > 64 * 1024 * 1024:
            self._send_json(400, {"ok": False, "message": "文件超过 64 MB，先压小再来"})
            return
        # 类型：先看服务器给的 Content-Type，认不出再退回网址后缀
        ext = ""
        if ctype.startswith("image/"):
            sub = ctype.split("/", 1)[1]
            ext = {"jpeg": "jpg", "svg+xml": ""}.get(sub, sub if sub.isalnum() else "")
        elif ctype.startswith("audio/"):
            sub = ctype.split("/", 1)[1]
            ext = sub if sub.isalnum() else ""
        path_ext = os.path.splitext(urlparse(url).path)[1].lower().lstrip(".")
        if path_ext in ("png", "jpg", "jpeg", "webp", "wav", "ogg", "mp3", "ttf", "otf"):
            ext = "jpg" if path_ext == "jpeg" else path_ext
        if ext in ("png", "jpg", "webp", "wav", "ogg", "mp3", "ttf", "otf"):
            category = "audio" if ext in ("wav", "ogg", "mp3") else (
                "fonts" if ext in ("ttf", "otf") else "images")
        else:
            self._send_json(400, {
                "ok": False,
                "message": f"认不出这个网址是什么文件（Content-Type: {ctype or '未知'}）。"
                           "请直接给图片或音频的直链。",
            })
            return
        name = (data.get("filename") or "").strip()
        if not name:
            base = os.path.basename(unquote(urlparse(url).path)) or "从网址导入"
            stem = os.path.splitext(base)[0][:60] or "从网址导入"
            # 素材名只允许中文/字母/数字/下划线（剧本里 @bg 名字 按空格切分），
            # 网址里的减号、点、括号一律换成下划线
            stem = re.sub(r"[^\w\u4e00-\u9fff]+", "_", stem).strip("_") or "从网址导入"
            name = f"{stem}.{ext}"
        elif "." not in name:
            name = f"{name}.{ext}"
        result = _save_import(
            self.app.data_root, category, name,
            base64.b64encode(raw).decode("ascii"), bool(data.get("overwrite", False)),
        )
        if result.get("ok"):
            _preview_cache_clear()
            result["bytes"] = len(raw)
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

    def _app_version(self, parsed=None) -> None:
        """状态栏版本号的唯一来源：以前 index.html 里写死一个 rcNN，
        发几个版本之后它还停在 rc19，玩家和我都分不清装的是哪一版。"""
        from . import __version__
        self._send_json(200, {"ok": True, "version": __version__})

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

    # ---- P65：手机端第一层「工作台」（工程卡片列表 / 切换工程）----

    def _games_dir(self) -> str | None:
        """工程所在的 games 目录：当前工程本身在 games/ 下时取它的父目录，否则取 <工程>/games。"""
        root = self._app_root()
        if not root:
            return None
        proj = os.path.realpath(root)
        parent = os.path.dirname(proj)
        return parent if os.path.basename(parent) == "games" else os.path.join(proj, "games")

    def _home(self, parsed=None) -> None:
        """工作台卡片数据：每个工程的名字 / 指令数 / 素材数 / 修改时间。

        只读磁盘不改状态。字段刻意少——手机一屏只放得下几张卡。
        """
        games = self._games_dir()
        # 当前工程按剧本所在目录算（`--script` 启动时 project_root 还是仓库根）
        cur = os.path.basename(self._current_project_root())
        rows = []
        if games and os.path.isdir(games):
            for child in sorted(os.listdir(games)):
                d = os.path.join(games, child)
                script = os.path.join(d, "script.gal")
                if not os.path.isdir(d) or not os.path.isfile(script):
                    continue
                try:
                    with open(script, encoding="utf-8", errors="replace") as f:
                        text = f.read()
                except OSError:
                    text = ""
                ins = sum(1 for ln in text.splitlines() if ln.strip().startswith("@"))
                # 素材按现有工程的目录约定统计（images/ 是图片，audio/ 是音频）
                assets = 0
                for sub in ("images", "audio", "fonts", "video"):
                    ap = os.path.join(d, sub)
                    if os.path.isdir(ap):
                        for _root, _dirs, files in os.walk(ap):
                            assets += len(files)
                rows.append({
                    "folder": child,
                    "name": child,
                    "ins": ins,
                    "assets": assets,
                    "mtime": os.path.getmtime(script),
                    "current": child == cur,
                })
        rows.sort(key=lambda r: (-r["mtime"], r["folder"]))
        self._send_json(200, {"ok": True, "current": cur, "games_dir": games or "",
                              "orientation": _project_orientation(self._current_project_root()),
                              "projects": rows})

    # P67：游戏画面方向（不是编辑器自己的方向）—— 导出/预览时按它提示玩家
    _ORIENTATIONS = ("any", "portrait", "landscape")

    def _current_project_root(self) -> str:
        """当前工程的根目录 = 剧本所在目录。

        不能用 `app.project_root`：`--script` 启动时它仍是启动时的当前目录，
        会把配置写到仓库根而不是 games/<工程>。
        """
        try:
            return os.path.dirname(os.path.realpath(self.app.script_path))
        except (AttributeError, TypeError):
            return self.app.project_root

    def _get_orientation(self, parsed=None) -> None:
        self._send_json(200, {"ok": True,
                              "orientation": _project_orientation(self._current_project_root())})

    def _set_orientation(self, parsed=None) -> None:
        """POST {orientation} → 写进工程 config.json 的顶层 orientation。"""
        data = self._read_json()
        value = str(data.get("orientation") or "").strip().lower()
        if value not in self._ORIENTATIONS:
            self._send_json(400, {"ok": False, "message": "只支持 any / portrait / landscape"})
            return
        root = self._current_project_root()
        cfg = _load_project_config(root)
        if not isinstance(cfg, dict):
            cfg = {}
        cfg["orientation"] = value
        try:
            _write_project_config(root, cfg)
        except OSError as exc:
            self._send_json(500, {"ok": False, "message": f"写配置失败：{exc}"})
            return
        self._send_json(200, {"ok": True, "orientation": value})

    def _serve_asset_scan(self, parsed=None) -> None:
        """作品体积体检：素材总大小、能不能单文件发。

        P178：作品要能长大。现在导出是"素材全 base64 内联进单个 HTML"，
        小作品没问题，语音和高清 CG 一进来就会在某个体积上崩掉。
        先把"多大、还能不能这么发"算清楚，让导出流程按档位说话。
        只认 games/ 的直接子目录，路径不合法一律拒绝。
        """
        q = parse_qs(parsed.query if parsed else "")
        folder = str((q.get("folder") or [""])[0]).strip()
        games = self._games_dir()
        if not folder or "/" in folder or "\\" in folder or folder in (".", ".."):
            self._send_json(400, {"ok": False, "message": "folder 不对"})
            return
        base = os.path.realpath(games or "")
        proj = os.path.realpath(os.path.join(base, folder))
        if os.path.dirname(proj) != base or not os.path.isdir(proj):
            self._send_json(404, {"ok": False, "message": "没有这个作品"})
            return
        from .asset_scan import scan as _scan_assets
        body = dict(ok=True, **_scan_assets(proj))
        self._send_json(200, body)

    def _serve_thumb(self, parsed=None) -> None:
        """工作台卡片缩略图：工程 icon.png；没有就用 images/ 里第一张图；都没有 → 404。

        只认 games/ 的直接子目录，路径不合法一律 404（不告诉对方目录在哪）。
        """
        q = parse_qs(parsed.query if parsed else "")
        folder = str((q.get("folder") or [""])[0]).strip()
        games = self._games_dir()
        if not folder or "/" in folder or "\\" in folder or folder in (".", ".."):
            self._send_json(404, {"ok": False, "message": "没有这张图"})
            return
        base = os.path.realpath(games or "")
        proj = os.path.realpath(os.path.join(base, folder))
        if os.path.dirname(proj) != base or not os.path.isdir(proj):
            self._send_json(404, {"ok": False, "message": "没有这张图"})
            return
        # 卡片图想要的是「这部长什么样」，而不是一张自动生成的字母图标：
        # 先找 images 里名字带 bg 的画面图，其次 icon.png，最后随便一张图
        imgs = []
        img_dir = os.path.join(proj, "images")
        if os.path.isdir(img_dir):
            ok = (".png", ".jpg", ".jpeg", ".webp")
            imgs = [n for n in sorted(os.listdir(img_dir))
                    if os.path.splitext(n)[1].lower() in ok]
        cand = ""
        for name in imgs:
            if "bg" in name.lower():
                cand = os.path.join(img_dir, name)
                break
        if not cand and os.path.isfile(os.path.join(proj, "icon.png")):
            cand = os.path.join(proj, "icon.png")
        if not cand and imgs:
            cand = os.path.join(img_dir, imgs[0])
        if not cand or not os.path.isfile(cand):
            self._send_json(404, {"ok": False, "message": "没有这张图"})
            return
        ext = os.path.splitext(cand)[1].lower()
        ctype = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                 ".webp": "image/webp"}.get(ext, "image/png")
        try:
            with open(cand, "rb") as f:
                blob = f.read()
        except OSError:
            self._send_json(404, {"ok": False, "message": "没有这张图"})
            return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(blob)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(blob)

    def _switch_project(self, parsed=None) -> None:
        """切换工程：POST {folder}。工作台卡片点进去 → 当前项目改指到 games/<folder>。"""
        data = self._read_json()
        folder = str(data.get("folder") or "").strip()
        games = self._games_dir()
        if not games:
            self._send_json(400, {"ok": False, "message": "还没有打开工程"})
            return
        base = os.path.realpath(games)
        target = os.path.realpath(os.path.join(base, folder))
        # 只允许 games/ 的直接子目录名：挡住 ../、绝对路径、以及「甲/../乙」这类绕路写法
        if not folder or folder in (".", "..") or "/" in folder or "\\" in folder:
            self._send_json(400, {"ok": False, "message": "工程名不合法"})
            return
        if os.path.dirname(target) != base:
            self._send_json(400, {"ok": False, "message": "工程名不合法"})
            return
        if not os.path.isfile(os.path.join(target, "script.gal")):
            self._send_json(404, {"ok": False, "message": f"没有这个工程：{folder}"})
            return
        self.app.project_root = target
        self.app.script_path = os.path.join(target, "script.gal")
        self.app.data_root = target
        self._send_json(200, {"ok": True, "folder": folder, "message": f"已打开「{folder}」"})

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
            _write_text_atomic(target, text)
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
            self._send_json(500, {"ok": False,
                                  "message": _write_error_text("语法检查失败", e, rel)})
            return
        try:
            _write_text_atomic(target, content)
        except OSError as e:
            self._send_json(500, {"ok": False,
                                  "message": _write_error_text("保存失败", e, rel)})
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
        # 相对路径按项目目录解析，避免 --project games/X --script script.gal 被误判越界
        # 未指定时沿用「script.gal 优先，否则第一个 .gal」，与设置页切换工程的规则一致
        raw_script = script_path or _default_script(self.project_root)
        if not os.path.isabs(raw_script):
            raw_script = os.path.join(self.project_root, raw_script)
        # 默认剧本路径必须在项目目录内
        sp = os.path.realpath(raw_script)
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
    """启动编辑器 HTTP 服务（阻塞）。端口被占 → 中文报错退出。

    只绑 127.0.0.1：同 WiFi 的手机连不上，这是刻意的 ——
    那套接口能改剧本、能删文件，不该交给整个局域网。
    手机端编游戏走的是另一条路（离线内核，见 docs/手机端编游戏.md）。
    """
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
