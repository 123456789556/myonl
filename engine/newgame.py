# -*- coding: utf-8 -*-
"""新建游戏向导：生成可运行的项目骨架（目录 + 示例教学剧本 + 占位素材）。

CLI（engine.cli new）与编辑器「＋ 新建游戏」按钮共用本模块，逻辑不双份。
骨架结构与 P7 约定的项目结构一致：

    games/游戏名/
    ├── script.gal     示例教学剧本（中文注释版）
    ├── images/        占位素材：2 背景 + 2 立绘
    ├── audio/         空目录（无音乐也能跑）
    └── fonts/         空目录（引擎默认字体兜底）

占位素材是开发期演示，只写入新建的游戏目录，不进引擎默认资源。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from .sdl_env import dummy_video

# 游戏名白名单：中文/字母/数字/下划线，≤20 字符（与素材名白名单同一套）
_NAME = re.compile(r"^[0-9A-Za-z_一-鿿]+$")
_MAX_LEN = 20

# 可用模板：hello = 极简空包（一行旁白）；default = 教学骨架；
# moonlight = 复刻《月光漫步》全量资源；standard = 内置素材成品模板
TEMPLATES = ("hello", "default", "moonlight", "standard")

# P46 UI 主题模板：新建游戏时三选一，也可建后改 config.json 的 theme/colors 换肤
THEMES = ("black",)  # 标准版唯一：不再提供 purple/white 风格
THEME_LABELS = {"black": "标准版（近黑面板 + 白字 + 暖金强调）"}
# P46 正文对齐：left（左对齐顶格，默认）/ center / right
ALIGNS = ("left", "center", "right")
ALIGN_LABELS = {"left": "左对齐·顶格（默认）", "center": "居中", "right": "右对齐·顶格"}

# 月光漫步模板源目录（相对引擎仓库根）；moonlight 模板从这里复制，排除 saves/ 和 src/（Ren'Py 源码参考）
_MOONLIGHT_SRC_DIR_NAME = "月光漫步"
_MOONLIGHT_EXCLUDE_DIRS = {"saves", "src"}

# default 模板的配置文件：默认值即一套现代 UI（开发者不改也能打包出"像成品"的游戏）
# P44：title_text_visible=true —— 背景图（images/title_bg.png）上也叠作品名，避免"图是图、字没有"
def _settings_text_for(name: str) -> str:
    """新建游戏的 settings 文本：在默认值基础上按设备档位选窗口（M1.5）。

    只影响新建工程；老工程已有 window_size 不受影响。探测失败回落模板默认。
    """
    text = DEFAULT_SETTINGS_JSON.replace("我的游戏", name)
    try:
        from . import capability

        data = json.loads(text)
        data["window_size"] = list(capability.suggest_settings()["window_size"])
        data["display_mode"] = "window"
        return json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    except Exception:  # noqa: BLE001 — 探测/解析失败一律回落模板，不阻塞建工程
        return text


DEFAULT_SETTINGS_JSON = '{\n  "_说明": "玩家偏好（引擎可写）。title 显示在标题画面；splash=true 时若有开场.gal 会先播序幕。",\n  "title": "我的游戏",\n  "splash": true,\n  "title_text_visible": true\n}\n'
DEFAULT_GALLERY_JSON = '{\n  "_说明": "画廊配置：键=画廊格名，值=点开后轮播的高清场景序列。空对象表示暂无画廊。"\n}\n'


def _default_config(name: str, theme: str = "black", align: str = "left") -> dict:
    """标准模板配置：现代主题色 + 圆角对话框 + 底部快捷栏 + 卡片选项。

    只写"覆盖项"，其余键由 engine/config.py 的 DEFAULTS 兜底；
    开发者按这份文件改颜色/字号/布局即可完成视觉定制。

    标准版唯一（black）；align：left（默认）/ center / right——正文对齐（旁白与台词同规范）。
    """
    theme = theme if theme in THEMES else "black"
    align = align if align in ALIGNS else "left"
    cfg = {
        "_说明": "MYONL 只读配置：只写要覆盖的键，其余走引擎默认值。完整可配项见 engine/config.py 的 DEFAULTS。",
        "window_title": name,
        "title_music": "",
        "font": {"title": 84, "heading": 60, "mid": 42, "body": 28, "option": 26, "small": 22, "em": 28},
        "line_height": {"body": 1.6, "heading": 1.3, "option": 1.4},
        "theme": {
            # P44：标准模板默认「黑」主题（近黑面板 + 白字，克制不花哨）；
            # 白/紫两个预设见《开发者使用指南》主题章节，改这些色值即可换肤
            "primary": [130, 140, 160],
            "primary_soft": [48, 52, 62],
            "accent": [255, 205, 130],
            "surface": [20, 22, 26],
            "surface_alt": [34, 37, 44],
            "text": [240, 244, 250],
            "text_dim": [150, 156, 166],
            "border": [58, 62, 70],
            "danger": [243, 139, 168],
            "success": [166, 227, 161],
            "shadow": [0, 0, 0],
        },
        "colors": {
            "selected_bg": [30, 33, 39],
            "selected_border": [130, 140, 160],
            "selected_fg": [255, 255, 255],
            "dialog_fg": [244, 246, 252],
            "dialog_fg_dim": [168, 174, 184],
            "highlight": [255, 218, 150],
        },
        "alphas": {"selected_bg": 220, "idle_bg": 168, "menu": 228},
        "dialogue": {
            "default": {
                "height": 200, "margin": 56, "border_width": 0, "bg_alpha": 176,
                # P48：去圆角（0=直角）+ 顶部加深区 + 顶边细线 + ▼隐藏字幕
                "radius": 0, "name_y": 14, "name_gap": 10, "narration_y": 20,
                # P46：正文对齐（left/center/right），新建游戏时三选一
                "align": align,
            },
            "nvl": {"bg_alpha": 96, "margin": 96, "top": 190, "bottom": 70, "line_gap": 10,
                    "align": align},
        },
        # P44-D SKIP 规则：新建工程默认开启（viewed=仅已浏览内容可跳，避免跳过未读剧情）
        "skip": {"enabled": True, "mode": "viewed"},
        "ui": {
            "corner_radius": 14,
            "quickbar": {
                "enabled": True, "position": "bottom", "align": "right",
                "margin_x": 28, "margin_y": 10, "button_width": 92,
                "button_height": 32, "gap": 10, "alpha": 200, "radius": 16,
            },
            "title": {"menu_top": 230, "menu_width": 240, "menu_row_height": 52,
                       "logo_y": 150, "letter_spacing": 3, "stars": 36,
                       # P44：标准模板标题页 = 左列布局 + 5 项主菜单（去画廊，退出留在菜单里）
                       "align": "left",
                       "items": ["开始新游戏", "继续", "读档", "设置", "退出"]},
            "choices": {"width": 620, "row_height": 56, "gap": 20, "radius": 16},
            "slots": {"count": 10},  # 2026-11-02：与 save.SLOT_COUNT 一致（10 位，可改）
            "settings": {"row_width": 760, "row_height": 64, "top": 196, "nav_width": 190},
        },
    }
    return cfg


def _default_pack_config(name: str) -> dict:
    """标准打包档案：命名/版本/图标/运营号四项必填，模板给出可直接打包的默认值。"""
    return {
        "_说明": "打包档案（python pack.py <游戏目录> 自动读取）：上线前把游戏名、图标、运营号改成你自己的。",
        "schema": 1,
        "game_name": name,
        "version": "1.0.0",
        "icon": "icon.png",
        "publisher": {
            "name": "个人开发者",
            "account_id": "MYONL-DEMO",
            "channel": "本地发行",
            "contact": "",
        },
        "description": "由 MYONL 标准模板创建的游戏。",
        "release_notes": "首个版本",
    }

# 示例教学剧本（静态模板文本，用户可直接编辑；每行带中文注释，顺序即教学顺序）
TEMPLATE = """# ============================================================
# 新手教学剧本：带你 30 分钟做出第一个 Galgame
# 每一行都有中文注释，顺序就是学习顺序，直接改着玩！
# ============================================================

@character 林晚 #aaccff        # ① 定义角色与名字颜色（6 位十六进制）

@bg bg_教室                    # ② 换背景（images/bg_教室.png 是占位纯色块）

# @music 音乐名                # （演示写法：本示例不引用音频，保持开箱即跑）

@show 林晚 微笑                # ③ 显示立绘（images/林晚_微笑.png）

@ 林晚 你好，我是林晚。          # ④ 对话（@ 后面要有空格）
@ 林晚 带你 30 分钟做第一个游戏。

@choice:                       # ⑤ 选项（玩家分支，选项行以 > 开头并缩进）
    > 接下来去哪？ -> 教室
    > 直接看结局吧 -> 结局

@label 教室                    # 标签：跳转的目的地
@ 林晚 那我们继续。
@set 进度 += 1                 # ⑥ 变量（+= 累加，也支持 = 和 -=）
@if 进度 >= 1:                 # ⑦ 条件（满足才执行缩进块，也支持 ==）
    @ 林晚 你已经学会了变量和条件。
@jump 结局                     # 跳到「结局」标签

@label 结局
@ 林晚 恭喜完成！现在去替换这些占位素材吧。
@end                           # ⑧ 结束，回到标题

# ============================================================
# 下一步指引
# ------------------------------------------------------------
# 1. 换素材：把 images/ 里的占位图换成自己的图（同名覆盖即可），
#    或用编辑器右侧素材创作台「＋ 导入」拖入新素材。
# 2. 加音乐：在 audio/ 放入 .ogg/.mp3/.wav，然后写一行 @music 音乐名。
# 3. 加转场：在 @bg 之前写一行 @transition dissolve 0.6 试试渐隐切换。
# 4. 更多指令与玩法见《开发者使用指南.md》素材创作台章节。
# ============================================================
"""

# 占位素材规格：背景 = 纯色块；立绘 = 纯色块 + 居中名字文字
_BG_SIZE = (1280, 720)
_SPRITE_SIZE = (512, 1024)
_BG_SPECS = [("bg_教室", (202, 176, 124)), ("bg_天台", (122, 168, 220))]
_SPRITE_SPECS = [("林晚_微笑", (238, 176, 190)), ("林晚_生气", (214, 108, 118))]


def validate_name(name) -> str:
    """校验游戏名；合法返回原名，非法抛 ValueError（中文提示）。"""
    if not isinstance(name, str) or not name.strip():
        raise ValueError("游戏名不能为空")
    name = name.strip()
    if len(name) > _MAX_LEN:
        raise ValueError(f"游戏名太长：最多 {_MAX_LEN} 个字符，当前 {len(name)} 个")
    if not _NAME.fullmatch(name):
        raise ValueError("游戏名只支持中文/字母/数字/下划线，不能含空格或符号")
    return name


def create_game(name, base_dir="games", template="default",
                theme: str = "black", align: str = "left") -> Path:
    """在 base_dir 下生成「name/」项目骨架；已存在则报错且不覆盖。返回项目目录。

    template:
      - "hello"：极简空包——只有一行可改可删的旁白，不带素材（编辑器新建游戏默认用这个）
      - "default"：教学骨架（script.gal + 占位素材 + config/settings/gallery_config）
      - "moonlight"：复刻《月光漫步》全量资源（剧本 + 章节 + 图片 + 音频 + 配置）
      - "standard"：标准成品模板（P44-B1：自绘素材 + 示例小故事 + 现代 UI 配置）
    theme: 仅 black（标准版；保留参数兼容旧调用，moonlight 模板忽略）
    align: P46 正文对齐 left/center/right（moonlight 模板忽略）
    """
    name = validate_name(name)
    template = (template or "default").lower()
    if template not in TEMPLATES:
        raise ValueError(f'未知模板 "{template}"，可选：{", ".join(TEMPLATES)}')
    theme = (theme or "black").lower()
    if theme not in THEMES:
        raise ValueError(f'未知主题 "{theme}"，可选：{", ".join(THEMES)}')
    align = (align or "left").lower()
    if align not in ALIGNS:
        raise ValueError(f'未知对齐 "{align}"，可选：{", ".join(ALIGNS)}')
    root = Path(base_dir) / name
    if root.exists():
        raise ValueError(f"游戏「{name}」已存在，换个名字吧（不会覆盖已有目录）")
    try:
        if template == "moonlight":
            _copy_moonlight_template(root)
        elif template == "standard":
            _create_standard_skeleton(root, theme=theme, align=align)
        elif template == "hello":
            _create_hello_skeleton(root, theme=theme, align=align)
        else:
            _create_default_skeleton(root, theme=theme, align=align)
    except Exception:
        # 生成中途失败不留半成品目录
        import shutil
        shutil.rmtree(root, ignore_errors=True)
        raise
    return root


def _write_project_meta(root: Path, theme: str = "black", align: str = "left") -> None:
    """写四份配置（config/settings/gallery/pack）+ 默认图标；各模板共用，避免三份重复。"""
    name = root.name
    (root / "config.json").write_text(
        json.dumps(_default_config(name, theme=theme, align=align),
                   ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (root / "settings.json").write_text(_settings_text_for(name), encoding="utf-8")
    (root / "gallery_config.json").write_text(DEFAULT_GALLERY_JSON, encoding="utf-8")
    (root / "pack_config.json").write_text(
        json.dumps(_default_pack_config(name), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    make_default_icon(root)


def _create_default_skeleton(root: Path, theme: str = "black", align: str = "left") -> None:
    """default 模板：教学剧本 + 占位素材 + 现代 UI 配置 + 标准打包档案。"""
    (root / "images").mkdir(parents=True)
    (root / "audio").mkdir()
    (root / "fonts").mkdir()
    (root / "script.gal").write_text(TEMPLATE, encoding="utf-8")
    _write_project_meta(root, theme, align)
    make_placeholder_assets(root)


HELLO_TEMPLATE = """# 极简空包：这里只有一行旁白。
# 角色台词写成 @[林晚] 你好。 整屏独白写 @[[林晚]] 一整段文字……
# 改掉这句话、或整行删掉都可以；图片/音乐以后再导入也来得及。
@ hello world!
@end
"""


def _create_hello_skeleton(root: Path, theme: str = "black", align: str = "left") -> None:
    """hello 模板：一行旁白起步，不带任何素材（缺素材也不会白屏）。"""
    (root / "images").mkdir(parents=True)
    (root / "audio").mkdir()
    (root / "fonts").mkdir()
    (root / "script.gal").write_text(HELLO_TEMPLATE, encoding="utf-8")
    _write_project_meta(root, theme, align)


def _copy_moonlight_template(root: Path) -> None:
    """moonlight 模板：从 作品/副产物/月光漫步/ 复制全部游戏资源（排除 saves/、src/ Ren'Py 源码）。
    源目录定位：P44 起月光漫步位于 作品/副产物/（旧 games/ 位置兼容兜底）。
    """
    import shutil

    src = _resolve_moonlight_src()
    if src is None:
        raise ValueError("moonlight 模板源目录 作品/副产物/月光漫步/ 不存在，无法生成")
    root.mkdir(parents=True)
    for entry in src.iterdir():
        if entry.is_dir() and entry.name in _MOONLIGHT_EXCLUDE_DIRS:
            continue
        dest = root / entry.name
        if entry.is_dir():
            shutil.copytree(entry, dest)
        else:
            shutil.copy2(entry, dest)


def _resolve_moonlight_src() -> Path | None:
    """定位月光漫步模板源目录：P44 起月光漫步移出主线，位于 作品/副产物/月光漫步/（旧位置 games/ 兼容兜底）。"""
    repo_root = Path(__file__).resolve().parent.parent
    for rel in ("作品/副产物/月光漫步", "games/月光漫步"):
        candidate = repo_root / rel
        if candidate.is_dir():
            return candidate
    return None


def _standard_template_dir() -> Path | None:
    """内置 standard 模板目录；找不到返回 None。

    源码运行：engine/templates/standard；
    PyInstaller 冻结（editor.exe）：_MEIPASS/engine/templates/standard（由 editor.spec 打包），
    两种形态都要能找到，否则发行版「新建游戏」会退化成占位色块。
    """
    candidates = [Path(__file__).resolve().parent / "templates" / "standard"]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "engine" / "templates" / "standard")
    for path in candidates:
        if path.is_dir():
            return path
    return None


def _create_standard_skeleton(root: Path, theme: str = "black", align: str = "left") -> None:
    """standard 模板（P44-B1）：复制引擎内置成品素材与示例剧本 + 现代 UI 配置。

    素材（版权干净、程序生成）：engine/templates/standard/{images,audio}/。
    与 default 的区别：观感成品（渐变背景/剪影立绘/合成 BGM/三幕示例），无教学注释。
    """
    import shutil

    tpl = _standard_template_dir()
    if tpl is None:
        # 发行包漏带内置素材时不让「新建游戏」直接失败（用户只会看到白板）：
        # 退回程序化占位素材 + 教学剧本，至少能立刻跑起来。
        _create_default_skeleton(root, theme=theme, align=align)
        return
    root.mkdir(parents=True)
    for entry in tpl.iterdir():
        dest = root / entry.name
        if entry.is_dir():
            shutil.copytree(entry, dest)
        else:
            shutil.copy2(entry, dest)
    _write_project_meta(root, theme, align)


@dummy_video
def make_placeholder_assets(root, overwrite: bool = False) -> list:
    """生成占位素材：2 背景（1280×720 纯色块）+ 2 立绘（512×1024 纯色块+名字）。

    只写入游戏目录 images/；同名文件已存在且 overwrite=False 时跳过（不覆盖用户素材）。
    返回实际生成的文件路径列表。
    """
    import pygame

    pygame.font.init()
    root = Path(root)
    img_dir = root / "images"
    img_dir.mkdir(parents=True, exist_ok=True)
    made = []
    for name, rgb in _BG_SPECS:
        out = img_dir / f"{name}.png"
        if out.exists() and not overwrite:
            continue
        surf = pygame.Surface(_BG_SIZE)
        surf.fill(rgb)
        pygame.image.save(surf, str(out))
        made.append(out)
    for name, rgb in _SPRITE_SPECS:
        out = img_dir / f"{name}.png"
        if out.exists() and not overwrite:
            continue
        surf = pygame.Surface(_SPRITE_SIZE)
        surf.fill(rgb)
        _blit_name(surf, name, rgb, root)
        pygame.image.save(surf, str(out))
        made.append(out)
    return made


@dummy_video
def make_default_icon(root, overwrite: bool = False) -> Path:
    """生成 256×256 的默认游戏图标（渐变底 + 首字），供打包直接嵌入 exe。

    开发者可随时用自己的 icon.png 覆盖；打包工具也会自动把 PNG 转成 ICO。
    """
    import pygame

    pygame.font.init()  # 幂等：standard 模板不跑占位素材路径时也保证可用
    root = Path(root)
    out = root / "icon.png"
    if out.exists() and not overwrite:
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    size = 256
    surf = pygame.Surface((size, size))
    # 竖向渐变：从主题蓝到深紫，形成现代 App 图标质感
    top, bottom = (104, 156, 255), (74, 56, 156)
    for y in range(size):
        t = y / max(1, size - 1)
        surf.fill(
            (int(top[0] * (1 - t) + bottom[0] * t),
             int(top[1] * (1 - t) + bottom[1] * t),
             int(top[2] * (1 - t) + bottom[2] * t)),
            pygame.Rect(0, y, size, 1),
        )
    pygame.draw.circle(surf, (255, 205, 130), (196, 56), 74, 0)
    pygame.draw.circle(surf, (255, 231, 190), (196, 56), 52, 0)
    # 首字（中文名取第一个字，英文名取首字母大写）
    label = (root.name or "S")[0].upper()
    surf.blit(_cjk_font(root, 92).render(label, True, (255, 255, 255)), (72, 70))
    pygame.image.save(surf, str(out))
    return out


def _text_color(rgb) -> tuple:
    """按背景亮度选对比文字色。"""
    r, g, b = rgb
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    return (30, 30, 40) if lum > 140 else (245, 245, 250)


def _cjk_font(root, size: int):
    """取中文字体（游戏 fonts/ → 系统字体）；找不到退回 pygame 默认字体。"""
    import pygame

    from .data import DataError, find_cjk_font

    try:
        path = find_cjk_font(str(root))
    except DataError:
        path = None
    try:
        return pygame.font.Font(path, size) if path else pygame.font.Font(None, size)
    except Exception:
        return pygame.font.Font(None, size)


def _blit_name(surf, name: str, rgb, root=None) -> None:
    """立绘上居中写名字：「林晚_微笑」→ 大字「林晚」+ 小字「微笑」。"""
    char, _, expr = name.partition("_")
    w, h = surf.get_size()
    color = _text_color(rgb)
    font_big = _cjk_font(root, 72)
    font_small = _cjk_font(root, 40)
    lines = [(font_big, char)]
    if expr:
        lines.append((font_small, expr))
    total_h = sum(f.size(t)[1] for f, t in lines) + 12 * (len(lines) - 1)
    y = (h - total_h) // 2
    for font, text in lines:
        img = font.render(text, True, color)
        rect = img.get_rect(centerx=w // 2, top=y)
        surf.blit(img, rect)
        y += img.get_height() + 12
