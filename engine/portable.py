"""P56 可迁移导出：把同一个工程导成「别的引擎能吃的文件」。

为什么要有这一层：
    前几轮把 MYONL 做成手机 H5 播放器，作者一旦想「换个引擎」「拿到桌面端」「给别人用」，
    剧本和素材就被锁在 MYONL 自己的 web/ 包里了。这一层解决锁死问题，输出两样东西：

    1. Ren'Py 工程（`game/script.rpy` + `game/images/`）：解压后丢进 Ren'Py SDK 就能跑；
    2. 通用 JSON（`game.json` + `assets/`）：任何引擎/脚本都能读的中间层
       （格式见输出里的 README.md，字段就是 MYONL 的 IR，op 名一一对应）。

不做什么：
    - 不实现「完美的 Ren'Py 复刻」。桌面专属指令（音乐/视频/镜头/转场/插件）在
      Ren'Py 里语义不同，这里只记进 unsupported，不假造效果；
    - 不改原文剧本。转换只是投影，随时可以重新导。

用法：
    py -3 -m engine.portable "games\\教程示例" -o "dist\\portable\\教程示例" --engine both
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys

from . import parser as parser_mod
from .data import DataError, resolve_image
from .webpack import _collect_image_names, _load_config, _pick_script, _walk

# Ren'Py 里语义对不上的桌面专属指令：如实标记，不假装支持
UNSUPPORTED_OPS = ("music", "play", "stop", "video", "cg", "fg", "camera", "shake",
                   "anim", "transition", "chapter", "plug", "voice")


# ─────────────────────────── 公共：素材与配置 ───────────────────────────


def _copy_assets(root: str, images: list, dst_dir: str, prefix: str = "") -> tuple[dict, list]:
    """把引用到的图拷到 dst_dir，返回 {原名: 相对路径} 与缺失清单。"""
    os.makedirs(dst_dir, exist_ok=True)
    manifest: dict[str, str] = {}
    missing: list[str] = []
    for name in images:
        try:
            src = resolve_image(root, name)
        except DataError:
            missing.append(name)
            continue
        ext = os.path.splitext(src)[1].lower()
        dst_name = name + ext
        shutil.copyfile(src, os.path.join(dst_dir, dst_name))
        manifest[name] = prefix + dst_name
    return manifest, missing


def _unsupported(ins: list) -> list:
    seen: list[str] = []

    def walk(node):
        if isinstance(node, dict):
            op = node.get("op")
            if op in UNSUPPORTED_OPS and op not in seen:
                seen.append(op)
            for key in ("body", "else", "options"):
                val = node.get(key)
                if isinstance(val, list):
                    for child in val:
                        walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(ins)
    return seen


def _ir_images(ins: list) -> list[str]:
    """只取剧本真正引用的图（不含皮肤贴图），Ren'Py 侧不需要 textbox/paper。"""
    names: list[str] = []

    def add(n):
        n = str(n or "").strip()
        if n and n not in names:
            names.append(n)

    for item in ins:
        _walk(item, add)
    return names


# ─────────────────────────── Ren'Py 投影 ───────────────────────────


def _q(text) -> str:
    body = str(text).replace("\\", "\\\\").replace('"', '\\"')  # noqa: W605
    return '"' + body + '"'


def _lit(value) -> str:
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, (int, float)):
        return repr(value)
    return _q(value)


def _cond_text(cond) -> str:
    """把 IR 的条件对象翻成 Python/Ren'Py 表达式。"""
    if not isinstance(cond, dict):
        return "True"
    return f"{cond.get('var') or '0'} {cond.get('op') or '=='} {_lit(cond.get('value'))}"


class _RpyNames:
    """IR 里的中文名 → Ren'Py 安全标识符（图名/标签名/角色变量）。

    中文在 Python 里是合法标识符，但 Ren'Py 的图像名与 label 在部分工具链/编辑器里
    会被当成更严格的统计，所以这里统一换成 s1/bg1/label_1/c1 这类英文名，
    原名写进注释，作者想改回来一眼能看到。
    """

    def __init__(self):
        self.bg: dict[str, str] = {}
        self.sprite: dict[str, str] = {}
        self.label: dict[str, str] = {}
        self.char: dict[str, str] = {}

    def bg_name(self, name: str) -> str:
        if name not in self.bg:
            self.bg[name] = f"bg{len(self.bg) + 1}"
        return self.bg[name]

    def sprite_name(self, key: str) -> str:
        if key not in self.sprite:
            self.sprite[key] = f"s{len(self.sprite) + 1}"
        return self.sprite[key]

    def label_name(self, name: str) -> str:
        if name not in self.label:
            self.label[name] = f"label_{len(self.label) + 1}"
        return self.label[name]

    def char_var(self, name: str) -> str:
        if name not in self.char:
            self.char[name] = f"c{len(self.char) + 1}"
        return self.char[name]


def _rpy_script(ins: list, cfg: dict, manifest: dict, names: _RpyNames,
                characters: list, title: str) -> tuple[str, list[str]]:
    """生成 game/script.rpy 的正文；返回 (文本, 告警)。"""
    warns: list[str] = []
    out: list[str] = [
        "# 由 MYONL 导出（engine.portable）——这是投影，不是原文；改动请回 MYONL 改剧本。",
        f"# 工程：{title}",
        "",
    ]

    # 1) 角色定义
    for char in characters:
        var = names.char_var(char["name"])
        color = char.get("color") or "#ffffff"
        out.append(f'define {var} = Character({_q(char["name"])}, who_color={_q(color)})  # {char["name"]}')
    if characters:
        out.append("")

    # 2) 图像定义（背景与立绘；皮肤贴图不是场景图，不声明）
    images: dict[str, str] = {}
    for key in sorted(manifest):
        if key.startswith("bg_"):
            images[key] = names.bg_name(key)
        elif "_" in key:
            images[key] = names.sprite_name(key)
    for key, var in images.items():
        out.append(f'image {var} = "images/{manifest[key]}"  # {key}')
    if images:
        out.append("")

    # 3) 正文：先登记 label 名，再输出
    has_start = any(isinstance(i, dict) and i.get("op") == "label" and i.get("name") == "start"
                    for i in ins)
    first_label = next((n for n, i in enumerate(ins)
                        if isinstance(i, dict) and i.get("op") == "label"), len(ins))
    prelude = ins[:first_label]
    rest = ins[first_label:]

    if has_start and prelude:
        # 剧本在 start 之前还有指令：Ren'Py 不允许顶层散语句，所以统一收进合成的 label start
        names.label["start"] = "start_orig"
    elif has_start:
        names.label["start"] = "start"  # 保留原名，Ren'Py 正好从 start 起跑
    for item in rest:
        if isinstance(item, dict) and item.get("op") == "label":
            names.label_name(str(item.get("name") or ""))

    body: list[str] = []
    _emit(rest, body, names, images, characters, warns, 4)
    head: list[str] = []
    _emit(prelude, head, names, images, characters, warns, 4)

    if has_start and prelude:
        out.append("label start:  # 原剧本在 label start 之前的指令")
        out.extend(head or [f"    pass"])
        out.append(f"    jump {names.label['start']}")
        out.extend(body)
    elif has_start:
        out.extend(body)
    else:
        out.append("label start:")
        out.extend(head + body if head else (body or ["    return"]))
    out.append("")
    return "\n".join(out), warns


def _emit(ins: list, out: list[str], names: _RpyNames, images: dict,
          characters: list, warns: list[str], indent: int) -> None:
    pad = " " * indent
    sprite_of: dict[str, str] = {}
    for item in ins or []:
        if not isinstance(item, dict):
            continue
        op = item.get("op")
        if op == "character":
            continue  # 已在开头 define
        if op == "bg":
            key = str(item.get("image") or "")
            if key in images:
                out.append(f"{pad}scene {images[key]}")
            else:
                warns.append(f"背景没找到：{key}")
        elif op == "show":
            char = str(item.get("char") or "")
            expr = str(item.get("expr") or "")
            key = f"{char}_{expr}" if char and expr else char
            if key in images:
                sprite_of[char] = images[key]
                out.append(f"{pad}show {images[key]}")
            else:
                warns.append(f"立绘没找到：{key}")
        elif op == "hide":
            char = str(item.get("char") or "")
            if char in sprite_of:
                out.append(f"{pad}hide {sprite_of[char]}")
            else:
                warns.append(f"hide 找不到对应立绘：{char}")
        elif op == "label":
            out.append("")
            out.append(f"label {names.label_name(str(item.get('name') or ''))}:  # {item.get('name')}")
        elif op == "say":
            char = item.get("char")
            text = str(item.get("text") or "")
            if char and str(char) in names.char:
                out.append(f"{pad}{names.char_var(str(char))} {_q(text)}")
            else:
                out.append(f"{pad}{_q(text)}")
        elif op == "choice":
            out.append(f"{pad}menu:")
            for opt in item.get("options") or []:
                target = names.label_name(str(opt.get("target") or ""))
                cond = opt.get("cond")
                head = _q(str(opt.get("text") or ""))
                if cond:
                    head += " if " + _cond_text(cond)
                out.append(f"{pad}    {head}:")
                out.append(f"{pad}        jump {target}")
        elif op == "jump":
            out.append(f"{pad}jump {names.label_name(str(item.get('target') or ''))}")
        elif op == "set":
            var = str(item.get("var") or "")
            opr = str(item.get("operator") or "=")
            if "value" in item:
                val = _lit(item.get("value"))
            else:
                val = str(item.get("expr") or "0")
            out.append(f"{pad}$ {var} {opr} {val}")
        elif op == "if":
            out.append(f"{pad}if {_cond_text(item.get('cond'))}:")
            sub: list[str] = []
            _emit(item.get("body") or [], sub, names, images, characters, warns, indent + 4)
            out.extend(sub or [f"{pad}    pass"])
            els = item.get("else")
            if els:
                out.append(f"{pad}else:")
                sub2: list[str] = []
                _emit(els if isinstance(els, list) else [], sub2, names, images,
                      characters, warns, indent + 4)
                out.extend(sub2 or [f"{pad}    pass"])
        elif op == "wait":
            out.append(f"{pad}pause {item.get('seconds') or 0.5}")
        elif op == "nvl":
            out.append(f"{pad}nvl clear")
            text = str(item.get("text") or "")
            if text:
                out.append(f"{pad}{_q(text)} version 2:  # 整屏旁白")
                out[-1] = f"{pad}{_q(text)} version 2"
        elif op == "end":
            out.append(f"{pad}return")
        elif op in UNSUPPORTED_OPS:
            continue  # 已汇总到 unsupported，不在这里造假效果


def build_renpy(project_root: str, out_dir: str) -> dict:
    """导出一个能直接扔进 Ren'Py SDK 的工程；返回统计。"""
    root = os.path.abspath(project_root)
    if not os.path.isdir(root):
        raise FileNotFoundError(f"项目目录不存在：{root}")
    ins = parser_mod.parse_file(_pick_script(root))
    cfg = _load_config(root)
    title = str(cfg.get("window_title") or os.path.basename(root))

    out = os.path.abspath(out_dir)
    game = os.path.join(out, "game")
    images_dir = os.path.join(game, "images")
    manifest, missing = _copy_assets(root, _ir_images(ins), images_dir)

    names = _RpyNames()
    script, warns = _rpy_script(ins, cfg, manifest, names, _chars(ins), title)
    _write(os.path.join(game, "script.rpy"), script)
    _write(os.path.join(game, "options.rpy"), _rpy_options(title, cfg))
    _write(os.path.join(out, "README.md"), _renpy_readme(title, names, warns, missing))

    return {
        "engine": "renpy",
        "out": out,
        "instructions": len(ins),
        "images": len(manifest),
        "missing": missing,
        "unsupported": _unsupported(ins),
        "warnings": warns,
    }


def _chars(ins: list) -> list:
    out = []
    for item in ins:
        if isinstance(item, dict) and item.get("op") == "character" and item.get("name"):
            out.append({"name": str(item["name"]), "color": item.get("color") or "#ffffff"})
    return out


def _rpy_options(title: str, cfg: dict) -> str:
    theme = cfg.get("theme") if isinstance(cfg.get("theme"), dict) else {}
    accent = str((theme or {}).get("primary") or "#4f8cff")
    return "\n".join([
        "# 由 MYONL 导出：只带了标题与主色，其余 UI 用 Ren'Py 默认，避免假装还原。",
        f'define config.name = {_q(title)}',
        f'define gui.accent_color = {_q(accent)}',
        "define config.has_sound = True",
        "define config.has_music = True",
        "",
        "label splashscreen:",
        "    return",
        "",
    ])


def _renpy_readme(title: str, names: _RpyNames, warns: list, missing: list) -> str:
    lines = [
        f"# {title} · Ren'Py 工程（MYONL 导出）",
        "",
        "## 怎么跑",
        "1. 装 Ren'Py SDK，打开 Ren'Py Launcher；",
        "2. 把这个目录整个放进 SDK 的 projects 目录（或 Launcher → 偏好设置 → 项目目录指到这里）；",
        "3. Launcher 里选它 → Launch Project。",
        "",
        "## 名字对照（IR 原名 → Ren'Py 标识符）",
        "",
        "| 原名 | Ren'Py |",
        "|---|---|",
    ]
    for key, val in list(names.bg.items()) + list(names.sprite.items()):
        lines.append(f"| {key} | `{val}` |")
    for key, val in names.label.items():
        lines.append(f"| label {key} | `{val}` |")
    for key, val in names.char.items():
        lines.append(f"| 角色 {key} | `{val}` |")
    lines.append("")
    lines.append("## 对不上的地方（如实记）")
    lines.append("")
    lines.append("- 中文名统一换成英文标识符，因为 Ren'Py 的图像名/label 名走的是标识符规则；")
    lines.append("- 桌面专属指令（音乐/视频/镜头/转场/插件）没有投影，Ren'Py 里需要自己补；")
    lines.append("- 对话框皮肤（九宫格贴图）没有投影，Ren'Py 用自家的 textbox 机制。")
    if warns:
        lines.append("")
        lines.append("## 转换告警")
        lines.append("")
        lines += [f"- {w}" for w in warns]
    if missing:
        lines.append("")
        lines.append("## 缺素材")
        lines.append("")
        lines += [f"- {m}" for m in missing]
    lines.append("")
    return "\n".join(lines)


# ─────────────────────────── 通用 JSON 投影 ───────────────────────────


def build_json(project_root: str, out_dir: str) -> dict:
    """导出「谁都能读」的中间层：game.json + assets/ + README（格式说明）。"""
    root = os.path.abspath(project_root)
    if not os.path.isdir(root):
        raise FileNotFoundError(f"项目目录不存在：{root}")
    script_path = _pick_script(root)
    ins = parser_mod.parse_file(script_path)
    cfg = _load_config(root)
    title = str(cfg.get("window_title") or os.path.basename(root))

    out = os.path.abspath(out_dir)
    manifest, missing = _copy_assets(root, _collect_image_names(ins, cfg),
                                     os.path.join(out, "assets"), prefix="assets/")

    payload = {
        "format": "myonl-ir/1",
        "title": title,
        "source_script": os.path.basename(script_path),
        "characters": _chars(ins),
        "config": cfg,
        "assets": manifest,
        "ins": ins,
    }
    _write(os.path.join(out, "game.json"),
           json.dumps(payload, ensure_ascii=False, indent=2))
    _write(os.path.join(out, "README.md"), _json_readme(title, missing))
    return {
        "engine": "json",
        "out": out,
        "instructions": len(ins),
        "images": len(manifest),
        "missing": missing,
        "unsupported": _unsupported(ins),
        "warnings": [],
    }


def _json_readme(title: str, missing: list) -> str:
    missing_note = ""
    if missing:
        missing_note = "\n## 缺素材\n\n" + "\n".join(f"- {m}" for m in missing) + "\n"
    body = """## 结构

```
{
  "format": "myonl-ir/1",
  "title": "标题",
  "characters": [{"name": "林晚", "color": "#ffb3c8"}],
  "config": { ... 原 config.json ... },
  "assets": {"bg_教室": "assets/bg_教室.png"},
  "ins": [ ... 指令数组 ... ]
}
```

## 指令（op）表

| op | 字段 | 含义 |
|---|---|---|
| `character` | name, color | 登记角色（决定名字颜色） |
| `bg` | image | 换背景（原名即 `assets` 的键） |
| `show` | char, expr | 显示立绘（图名 `<char>_<expr>`） |
| `hide` | char | 收起立绘 |
| `say` | char（可为 null）, text | 台词；char 为 null 是旁白 |
| `choice` | options[text, target, cond 可选] | 选项，跳到 target 标签 |
| `jump` | target | 跳标签 |
| `label` | name | 标签 |
| `set` | var, operator（= += -= *= /=）, value 或 expr | 赋值 |
| `if` | cond（var, op, value）, body, else | 条件块 |
| `wait` | seconds | 停顿 |
| `nvl` | text | 整屏旁白 |
| `end` | 无 | 结束 |

`text` 里的 `{变量}` 是插值占位，读取方自行替换。

## 拿它做什么

- 自己写引擎/播放器：照上表实现 op 即可；
- 转成别的格式（Ren'Py / Unity / Godot / 网页）：字段够用，图名就是键；
- 做校对/统计：一条 op 一行记录。
"""
    return "# " + title + " · 通用剧本包（MYONL 导出）\n\n`game.json` 是 MYONL 的中间层（IR），任何语言/引擎都能读。`assets/` 里是剧本引用到的图。\n\n" + body + missing_note


# ─────────────────────────── 入口 ───────────────────────────


def _write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def build_portable(project_root: str, out_dir: str, *, engine: str = "both") -> dict:
    """engine: renpy | json | both。返回 {"stats": [...], "out": ...}。"""
    results = []
    if engine in ("json", "both"):
        results.append(build_json(project_root, os.path.join(out_dir, "json")))
    if engine in ("renpy", "both"):
        results.append(build_renpy(project_root, os.path.join(out_dir, "renpy")))
    if not results:
        raise ValueError(f"未知的导出目标：{engine}（可选 renpy / json / both）")
    return {"out": os.path.abspath(out_dir), "stats": results}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="把工程导成别的引擎能吃的文件（Ren'Py / 通用 JSON）")
    ap.add_argument("project", help="项目目录")
    ap.add_argument("-o", "--out", default="", help="输出目录，默认 dist/portable/<项目名>")
    ap.add_argument("--engine", default="both", choices=["renpy", "json", "both"],
                    help="导出目标，默认 both")
    args = ap.parse_args(argv)
    out = args.out or os.path.join("dist", "portable", os.path.basename(os.path.abspath(args.project)))
    try:
        res = build_portable(args.project, out, engine=args.engine)
    except FileNotFoundError as e:
        print(f"失败：{e}")
        return 1
    print(f"已导出：{res['out']}")
    for stat in res["stats"]:
        print(f"  [{stat['engine']}] {stat['out']}　指令 {stat['instructions']} 条　素材 {stat['images']} 张")
        if stat["missing"]:
            print(f"    缺素材：" + "、".join(stat["missing"]))
        if stat["unsupported"]:
            print(f"    没投影的桌面指令：" + "、".join(stat["unsupported"]))
        if stat["warnings"]:
            print(f"    告警 {len(stat['warnings'])} 条（详见该目录 README.md）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
