"""P54 移动端编译：把项目编成「竖屏网页包」，丢给 web/ 里的 JS 播放器跑。

分工（这是这次转向的核心）：
    Python 端 = 编译器（剧本语法只有这一份实现，parser 复用，不重复造）
    JS 端     = 播放器（只执行 IR，不管语法）

产出（一个可直接上传的静态包）：
    <out>/index.html     入口（引用同目录的 *.js）
    <out>/pack.json      剧本 IR + 角色表 + 视觉配置 + 素材清单
    <out>/assets/*.png   视图用到的素材（只拷引用到的，不整目录搬）
    <out>/myonl-core.js  web/ 里的内核与播放器
    <out>/myonl-player.js

用法：
    py -3 -m engine.webpack "games\\教程示例" -o "dist\\web\\教程示例"
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys

from . import parser as parser_mod
from .data import resolve_image
from .data import DataError

def _web_src() -> str:
    """播放器源码目录：源码版在仓库 web/，打 exe 后在 PyInstaller 的 _MEIPASS/web。"""
    bundle = getattr(sys, "_MEIPASS", "")
    if bundle:
        cand = os.path.join(str(bundle), "web")
        if os.path.isdir(cand):
            return cand
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")


WEB_SRC = _web_src()
PLAYER_FILES = ("myonl-core.js", "myonl-layout.js", "myonl-player.js")

# 播放器用得上的 config 子集（整份丢过去会让 pack 变大，也没必要）
CONFIG_KEYS = ("window_title", "theme", "colors", "alphas", "font", "line_height")


def _pick_script(root: str) -> str:
    """找主剧本：优先 script.gal，其次任意 *.gal（按名字排序取第一个）。"""
    direct = os.path.join(root, "script.gal")
    if os.path.isfile(direct):
        return direct
    cands = sorted(f for f in os.listdir(root) if f.endswith(".gal"))
    if not cands:
        raise FileNotFoundError(f"{root} 里没有剧本（需要 script.gal 或 *.gal）")
    return os.path.join(root, cands[0])


def _load_config(root: str) -> dict:
    path = os.path.join(root, "config.json")
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _collect_image_names(ins: list, cfg: dict) -> list[str]:
    """从 IR + 配置里收集要用到的图片名（去重，保持出现顺序）。"""
    names: list[str] = []

    def add(n):
        n = str(n or "").strip()
        if n and n not in names:
            names.append(n)

    for item in ins:
        _walk(item, add)
    for group in ("default", "nvl"):
        dlg = (cfg.get("dialogue") or {}).get(group) or {}
        add(dlg.get("panel_image"))
        add(dlg.get("panel_texture"))
    return names


def _walk(node, add) -> None:
    if isinstance(node, dict):
        op = node.get("op")
        if op == "bg":
            add(node.get("image"))
        elif op == "show":
            char = str(node.get("char") or "")
            expr = str(node.get("expr") or "")
            add(f"{char}_{expr}" if char and expr else char)
        for key in ("body", "else", "options", "ins"):
            val = node.get(key)
            if isinstance(val, list):
                for child in val:
                    _walk(child, add)
            elif isinstance(val, dict):
                _walk(val, add)
    elif isinstance(node, list):
        for child in node:
            _walk(child, add)


def build_web(project_root: str, out_dir: str, *, title: str = "") -> dict:
    """编译一个项目成竖屏网页包；返回统计（含缺失素材清单）。"""
    root = os.path.abspath(project_root)
    if not os.path.isdir(root):
        raise FileNotFoundError(f"项目目录不存在：{root}")
    script_path = _pick_script(root)
    ins = parser_mod.parse_file(script_path)
    cfg = _load_config(root)

    out = os.path.abspath(out_dir)
    assets_dir = os.path.join(out, "assets")
    os.makedirs(assets_dir, exist_ok=True)

    images = _collect_image_names(ins, cfg)
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
        shutil.copyfile(src, os.path.join(assets_dir, dst_name))
        manifest[name] = "assets/" + dst_name

    # 只回填存在的那部分配置（缺的走播放器默认，避免前端处理空对象）
    picked = {k: cfg[k] for k in CONFIG_KEYS if k in cfg}
    picked["dialogue"] = {
        g: d for g, d in (cfg.get("dialogue") or {}).items() if isinstance(d, dict)
    }

    log = []
    for op in ("music", "play", "stop", "video", "cg", "fg", "camera", "shake", "anim"):
        if _has_op(ins, op):
            log.append(op)

    pack = {
        "version": 1,
        "title": title or str(cfg.get("window_title") or os.path.basename(root)),
        "script": os.path.basename(script_path),
        "characters": _characters(ins),
        "config": picked,
        "assets": manifest,
        "ins": ins,
        # 桌面端有、移动端暂不实现的指令：告给作者，不假装支持
        "unsupported": log,
    }
    with open(os.path.join(out, "pack.json"), "w", encoding="utf-8") as f:
        json.dump(pack, f, ensure_ascii=False, separators=(",", ":"))

    for name in PLAYER_FILES:
        src = os.path.join(WEB_SRC, name)
        if not os.path.isfile(src):
            raise FileNotFoundError(f"播放器源码缺失：{src}")
        shutil.copyfile(src, os.path.join(out, name))

    html = _render_html(pack["title"])
    with open(os.path.join(out, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)

    return {
        "out": out,
        "title": pack["title"],
        "instructions": len(ins),
        "images": len(manifest),
        "missing": missing,
        "unsupported": log,
    }


def _characters(ins: list) -> list:
    """@character 登记的角色（颜色/风格），给播放器决定名字颜色。"""
    out = []
    for item in ins:
        if isinstance(item, dict) and item.get("op") == "character":
            entry = {"name": item.get("name") or "", "color": item.get("color") or "#ffffff"}
            if item.get("kind") and item.get("kind") != "default":
                entry["kind"] = item["kind"]
            if entry["name"]:
                out.append(entry)
    return out


def _has_op(node, op) -> bool:
    if isinstance(node, dict):
        if node.get("op") == op:
            return True
        return any(_has_op(v, op) for k, v in node.items() if k in ("body", "else", "options"))
    if isinstance(node, list):
        return any(_has_op(v, op) for v in node)
    return False


def _render_html(title: str) -> str:
    safe = (title or "MYONL").replace("<", "&lt;").replace(">", "&gt;")
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover,user-scalable=no">
<meta name="theme-color" content="#14161f">
<title>{safe}</title>
<style>
  html, body {{ margin: 0; padding: 0; background: #0b0d12; overflow: hidden;
    -webkit-tap-highlight-color: transparent; user-select: none; }}
  #stage {{ position: fixed; inset: 0; display: flex; align-items: center; justify-content: center; }}
  #game {{ display: block; background: #000; box-shadow: 0 0 40px rgba(0,0,0,.6); }}
</style>
</head>
<body>
<div id="stage"><canvas id="game"></canvas></div>
<script src="myonl-core.js"></script>
<script src="myonl-layout.js"></script>
<script src="myonl-player.js"></script>
</body>
</html>
"""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="编译项目成竖屏网页包（移动端播放器用）")
    ap.add_argument("project", help="项目目录，如 games\\\\教程示例")
    ap.add_argument("-o", "--out", default="", help="输出目录，默认 dist\\\\web\\\\<项目名>")
    ap.add_argument("--title", default="", help="覆盖标题")
    args = ap.parse_args(argv)
    out = args.out or os.path.join("dist", "web", os.path.basename(os.path.abspath(args.project)))
    try:
        stat = build_web(args.project, out, title=args.title)
    except FileNotFoundError as e:
        print(f"失败：{e}")
        return 1
    print(f"已生成竖屏网页包：{stat['out']}")
    print(f"  标题：{stat['title']}　指令 {stat['instructions']} 条　素材 {stat['images']} 张")
    if stat["missing"]:
        print(f"  [缺素材 {len(stat['missing'])}]：" + "、".join(stat["missing"]))
    if stat["unsupported"]:
        print(f"  [桌面端有、移动端暂不支持]：" + "、".join(stat["unsupported"]))
    print("  本地预览：双击 index.html，或起个静态服务再看（视频/音频需要 http）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
