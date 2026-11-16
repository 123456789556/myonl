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
from .data import resolve_audio
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
# P70：ui（选项/快捷栏/菜单/设置页的几何与颜色）、dialogue（对话框皮肤）也要带上，
# 否则编辑器调完 UI 导出后手机端读不到，等于白调。
CONFIG_KEYS = ("window_title", "theme", "colors", "alphas", "font", "line_height",
               "ui", "dialogue")


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
        elif op == "cg":
            # P63：CG 是全屏大图，之前根本没收集，导到手机端就是一张空白
            add(node.get("name"))
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


def _collect_audio_names(ins: list) -> list[str]:
    """从 IR 里收集音乐/音效名（`@music 曲名` → music/track，`@sfx 名` → sfx/sound）。

    单文件版没声音是之前最大的短板：作者写了 @music，播出来是哑的。
    """
    names: list[str] = []

    def add(n):
        n = str(n or "").strip()
        if n and n not in names:
            names.append(n)

    def walk(node):
        if isinstance(node, dict):
            op = node.get("op")
            if op == "music":
                add(node.get("track"))
            elif op == "sfx":
                add(node.get("sound"))
            for key in ("body", "else", "options", "ins"):
                val = node.get(key)
                if isinstance(val, (list, dict)):
                    walk(val)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(ins)
    return names


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

    # P62：音频（@music / @sfx）也拷进来。之前只收图片，带音乐的工程编出来是哑的。
    audio_manifest: dict[str, str] = {}
    for name in _collect_audio_names(ins):
        try:
            src = resolve_audio(root, name)
        except DataError:
            missing.append(name)
            continue
        ext = os.path.splitext(src)[1].lower()
        dst_name = name + ext
        shutil.copyfile(src, os.path.join(assets_dir, dst_name))
        audio_manifest[name] = "assets/" + dst_name

    log = []
    # P62：music / sfx 已实现；P63：cg 全屏演出；P64：camera（zoom/pan/shake/reset）
    for op in ("play", "stop", "video", "fg", "shake", "anim"):
        if _has_op(ins, op):
            log.append(op)

    pack = {
        "version": 1,
        "title": title or str(cfg.get("window_title") or os.path.basename(root)),
        "script": os.path.basename(script_path),
        "characters": _characters(ins),
        "config": picked,
        "assets": manifest,
        "audio": audio_manifest,
        "ins": ins,
        # P67：作者选定的画面方向（any / portrait / landscape），播放器据此提示转屏
        "orientation": str(cfg.get("orientation") or "any"),
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

    html = _render_html(pack["title"], str(cfg.get("orientation") or "any"))
    with open(os.path.join(out, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)

    return {
        "out": out,
        "title": pack["title"],
        "instructions": len(ins),
        "images": len(manifest),
        "audio": len(audio_manifest),
        "missing": missing,
        "unsupported": log,
    }


MIME_BY_EXT = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".webp": "image/webp", ".gif": "image/gif", ".svg": "image/svg+xml",
    ".bmp": "image/bmp",
    ".ogg": "audio/ogg", ".mp3": "audio/mpeg", ".wav": "audio/wav",
    ".m4a": "audio/mp4", ".aac": "audio/aac",
}

# P62：单文件里图片多大就够用。超过阈值的图缩到 SHRINK_MAX_EDGE 内重编码。
SHRINK_OVER_BYTES = 300 * 1024
SHRINK_MAX_EDGE = 1600
SHRINK_QUALITY = 82


def _shrink_image(blob: bytes) -> tuple[bytes, str] | None:
    """把大图压小：缩到最大边 1600 内，存 WebP。不值得（压不下 10% / 没 PIL）返回 None。

    不改变逻辑尺寸，只降像素与码率——单文件里一张 2 MB 立绘能让整包卡在加载。
    """
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        import io

        im = Image.open(io.BytesIO(blob))
        if max(im.size) > SHRINK_MAX_EDGE:
            im.thumbnail((SHRINK_MAX_EDGE, SHRINK_MAX_EDGE), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "WEBP", quality=SHRINK_QUALITY, method=4)
        small = buf.getvalue()
    except Exception:   # noqa: BLE001 — 压不动就老实原样，别让导出因此失败
        return None
    if len(small) >= len(blob) * 0.9:
        return None
    return small, "image/webp"



def _js_safe(text: str) -> str:
    """内联进 <script> 的文本：先掐掉 </script> 这种会提前闭合的序列。"""
    return text.replace("</script", "<\\/script").replace("</SCRIPT", "<\\/SCRIPT")


def build_single(project_root: str, out_file: str, *, title: str = "") -> dict:
    """把整个游戏编成**一个 .html 文件**：图片转 base64 内嵌，播放器内联。

    为什么单独做一个：网页包是一堆文件（index.html + pack.json + 3 个 js + assets/），
    手机上没法"点开就玩"，也发不了微信。单文件版可以用手机浏览器直接打开，
    也能当作品发给别人看——这是「做完能交出去」的唯一形态。
    """
    import base64
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        stat = build_web(project_root, tmp, title=title)
        with open(os.path.join(tmp, "pack.json"), encoding="utf-8") as f:
            pack = json.load(f)

        assets: dict[str, str] = {}
        saved = 0
        for name, rel in (pack.get("assets") or {}).items():
            path = os.path.join(tmp, rel.replace("/", os.sep))
            ext = os.path.splitext(path)[1].lower()
            mime = MIME_BY_EXT.get(ext, "application/octet-stream")
            try:
                with open(path, "rb") as f:
                    blob = f.read()
            except OSError:
                continue
            # P62：大图压一道再内嵌。base64 本身还要再涨 37%，不压会更夸张。
            if len(blob) > SHRINK_OVER_BYTES and ext in (".png", ".jpg", ".jpeg", ".bmp"):
                shrunk = _shrink_image(blob)
                if shrunk:
                    saved += len(blob) - len(shrunk[0])
                    blob, mime = shrunk
            assets[name] = f"data:{mime};base64," + base64.b64encode(blob).decode("ascii")
        pack["assets"] = assets

        audio: dict[str, str] = {}
        for name, rel in (pack.get("audio") or {}).items():
            path = os.path.join(tmp, rel.replace("/", os.sep))
            mime = MIME_BY_EXT.get(os.path.splitext(path)[1].lower(),
                                   "application/octet-stream")
            try:
                with open(path, "rb") as f:
                    blob = f.read()
            except OSError:
                continue
            audio[name] = f"data:{mime};base64," + base64.b64encode(blob).decode("ascii")
        pack["audio"] = audio
        pack["single"] = True

        scripts = []
        for name in PLAYER_FILES:
            with open(os.path.join(tmp, name), encoding="utf-8") as f:
                scripts.append(f.read())

    pack_json = json.dumps(pack, ensure_ascii=False, separators=(",", ":"))
    body = "\n".join(
        "<script>" + _js_safe(s) + "</script>" for s in scripts
    )
    html = _render_single_html(pack["title"], _js_safe(pack_json), body,
                               str(pack.get("orientation") or "any"))

    out = os.path.abspath(out_file)
    parent = os.path.dirname(out)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)

    size = os.path.getsize(out)
    return {
        "out": out,
        "title": pack["title"],
        "instructions": stat["instructions"],
        "images": len(assets),
        "audio": len(audio),
        "saved": saved,
        "missing": stat["missing"],
        "unsupported": stat["unsupported"],
        "bytes": size,
    }


def _render_single_html(title: str, pack_json: str, player_scripts: str,
                        orientation: str = "any") -> str:
    safe = (title or "MYONL").replace("<", "&lt;").replace(">", "&gt;")
    orient = orientation if orientation in ("portrait", "landscape") else "any"
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover,user-scalable=no">
<meta name="theme-color" content="#14161f">
<meta name="myonl-orientation" content="{orient}">
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
<script>window.__MYONL_PACK__={pack_json};</script>
{player_scripts}
</body>
</html>
"""


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


def _render_html(title: str, orientation: str = "any") -> str:
    safe = (title or "MYONL").replace("<", "&lt;").replace(">", "&gt;")
    orient = orientation if orientation in ("portrait", "landscape") else "any"
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover,user-scalable=no">
<meta name="theme-color" content="#14161f">
<meta name="myonl-orientation" content="{orient}">
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
    ap.add_argument("--single", default="", help="导出单文件 .html（可直接双击/发微信），传输出路径")
    args = ap.parse_args(argv)
    if args.single:
        try:
            s = build_single(args.project, args.single, title=args.title)
        except FileNotFoundError as e:
            print(f"失败：{e}")
            return 1
        print(f"已生成单文件游戏：{s['out']}")
        print(f"  标题：{s['title']}　指令 {s['instructions']} 条　素材 {s['images']} 张"
              + (f"　音频 {s['audio']} 条" if s.get("audio") else "")
              + f"　{s['bytes'] / 1024:.0f} KB")
        if s.get("saved"):
            print(f"  大图压缩省下 {s['saved'] / 1024:.0f} KB（原图每张超 "
                  f"{SHRINK_OVER_BYTES // 1024} KB 的会转 WebP）")
        if s["missing"]:
            print(f"  [缺素材 {len(s['missing'])}]：" + "、".join(s["missing"]))
        print("  玩法：手机浏览器直接打开这个 .html，或把它发给别人")
        return 0
    out = args.out or os.path.join("dist", "web", os.path.basename(os.path.abspath(args.project)))
    try:
        stat = build_web(args.project, out, title=args.title)
    except FileNotFoundError as e:
        print(f"失败：{e}")
        return 1
    print(f"已生成竖屏网页包：{stat['out']}")
    print(f"  标题：{stat['title']}　指令 {stat['instructions']} 条　素材 {stat['images']} 张"
          + (f"　音频 {stat['audio']} 条" if stat.get("audio") else ""))
    if stat["missing"]:
        print(f"  [缺素材 {len(stat['missing'])}]：" + "、".join(stat["missing"]))
    if stat["unsupported"]:
        print(f"  [桌面端有、移动端暂不支持]：" + "、".join(stat["unsupported"]))
    print("  本地预览：双击 index.html，或起个静态服务再看（视频/音频需要 http）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
