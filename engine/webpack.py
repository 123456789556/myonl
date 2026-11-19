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
from . import pwa
from .data import resolve_audio
from .data import resolve_image
from .data import find_variant_image
from .data import DataError

# 启动遮罩：加载 pack.json 与素材的那一两秒不能给一块纯黑（手机上看像卡死）。
# 两套模板共用这一段，所以抽成常量：f-string 里插入变量，大括号不用双写。
_BOOT_CSS = """
  #boot { position: fixed; inset: 0; z-index: 9; background: #0b0d12;
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    gap: 14px; transition: opacity .32s ease; }
  #boot.gone { opacity: 0; pointer-events: none; }
  #boot .dot { width: 10px; height: 10px; border-radius: 50%; background: #4f8cff;
    animation: bootpulse 1.5s ease-out infinite; }
  #boot .bt { max-width: 78vw; text-align: center;
    font: 500 15px/1.5 -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
    color: #8a90a2; letter-spacing: .05em; }
  @keyframes bootpulse {
    0% { box-shadow: 0 0 0 0 rgba(79,140,255,.42); }
    100% { box-shadow: 0 0 0 18px rgba(79,140,255,0); }
  }
"""

# 单文件（file://）也能被 iOS / Android 当成 App：apple-mobile-web-app 这套 meta
# 在 file:// 下照常生效，service worker 不行（那需要 https）。
_APPLE_META = """<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="{short}">
<meta name="format-detection" content="telephone=no">"""


def _boot_html(title: str) -> str:
    safe = (title or "MYONL").replace("<", "&lt;").replace(">", "&gt;")
    return f'<div id="boot"><span class="dot"></span><span class="bt">{safe}</span></div>'

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
               "ui", "dialogue", "focal")


def _clean_focal(raw) -> dict:
    """收 config.json 的 "focal": {"背景名": [x, y]}，只留 0–1 的合法项。

    语义是「裁切窗口落在哪」：0 贴左/上、0.5 居中、1 贴右/下。
    没有这项就走居中 —— 老工程不用改任何东西也不会坏。
    """
    out: dict[str, list] = {}
    if not isinstance(raw, dict):
        return out
    for key, val in raw.items():
        if not isinstance(val, (list, tuple)) or len(val) != 2:
            continue
        try:
            x = float(val[0])
            y = float(val[1])
        except (TypeError, ValueError):
            continue
        if 0 <= x <= 1 and 0 <= y <= 1:
            out[str(key)] = [round(x, 3), round(y, 3)]
    return out


def _strip_local_paths(node) -> None:
    """把产物里每条指令的 `file` 从本机绝对路径洗成文件名。

    解析器给每个 op 记了来源文件（编辑器报错要指到具体行），那是对的。
    但这个 op 列表会原样内联进成品 HTML —— 成品是发给玩家玩的，
    玩家看到 `C:\\Users\\me\\my-game\\script.gal` 一头雾水；
    更严重的是，等于把开发机的目录结构跟着游戏一起发出去。

    就地递归，只动 `file` 这一个键，别的字段不碰。
    """
    if isinstance(node, list):
        for item in node:
            _strip_local_paths(item)
    elif isinstance(node, dict):
        f = node.get("file")
        if isinstance(f, str) and ("\\" in f or "/" in f):
            node["file"] = os.path.basename(f)
        for value in node.values():
            _strip_local_paths(value)


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
        elif op == "fg":
            # P73：前景贴图（雨雪/光效/蒙版），手机端已能画，图片必须一起带走
            # @fg 无 是「清掉前景」，不是素材名，别当缺失报给作者
            nm = str(node.get("name") or "")
            if not node.get("reset") and nm not in ("无", "none"):
                add(nm)
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
            elif op == "voice":
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


def _collect_video_names(ins: list) -> list[str]:
    """从 IR 里收集帧序列视频名（`@video 名 fps=`）—— 帧在 images/videos/名_001.png 起。

    P131：`file` 真视频走 movies 通道，不再往帧序列名单里放。
    """
    names: list[str] = []

    def walk(node):
        if isinstance(node, dict):
            if node.get("op") == "video" and not node.get("movie_file"):
                n = str(node.get("name") or "").strip()
                if n and n not in names:
                    names.append(n)
            for key in ("body", "else", "options", "ins"):
                val = node.get(key)
                if isinstance(val, (list, dict)):
                    walk(val)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(ins)
    return names


FRAME_EXTS = (".png", ".webp")

# P131：真视频文件（@video 名 file）。项目根 videos/ 下按名找候选后缀。
MOVIE_EXTS = (".mp4", ".webm", ".mov")


def _collect_movie_names(ins: list) -> list[str]:
    """从 IR 里收集真视频名（@video 名 file，IR 字段 movie_file=True）。"""
    names: list[str] = []

    def walk(node):
        if isinstance(node, dict):
            if node.get("op") == "video" and node.get("movie_file"):
                n = str(node.get("name") or "").strip()
                if n and n not in names:
                    names.append(n)
            for key in ("body", "else", "options", "ins"):
                val = node.get(key)
                if isinstance(val, (list, dict)):
                    walk(val)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(ins)
    return names


def _resolve_movie(root: str, name: str) -> str:
    """root/videos/<名>.mp4|.webm|.mov，找到返回路径，都没有抛 DataError。"""
    vdir = os.path.join(root, "videos")
    for ext in MOVIE_EXTS:
        p = os.path.join(vdir, name + ext)
        if os.path.isfile(p):
            return p
    tried = "、".join(name + e for e in MOVIE_EXTS)
    raise DataError(f"找不到视频文件：{os.path.join(vdir, name)}（尝试过：{tried}）")


def _copy_video_frames(root: str, assets_dir: str, names: list[str]):
    """拷帧序列进网页包：assets/videos/名_001.png…；返回 (manifest, 缺帧名)。"""
    seq_root = os.path.join(root, "images", "videos")
    manifest: dict[str, list[str]] = {}
    missing: list[str] = []
    for name in names:
        frames: list[str] = []
        idx = 1
        while True:
            hit = None
            for ext in FRAME_EXTS:
                p = os.path.join(seq_root, f"{name}_{idx:03d}{ext}")
                if os.path.isfile(p):
                    hit = p
                    break
            if not hit:
                break
            frames.append(hit)
            idx += 1
        if not frames:
            missing.append(name)
            continue
        dst_dir = os.path.join(assets_dir, "videos")
        os.makedirs(dst_dir, exist_ok=True)
        rels: list[str] = []
        for i, path in enumerate(frames, 1):
            ext = os.path.splitext(path)[1].lower()
            dst_name = f"{name}_{i:03d}{ext}"
            shutil.copyfile(path, os.path.join(dst_dir, dst_name))
            rels.append("assets/videos/" + dst_name)
        manifest[name] = rels
    return manifest, missing


def build_web(project_root: str, out_dir: str, *, title: str = "") -> dict:
    """编译一个项目成竖屏网页包；返回统计（含缺失素材清单）。"""
    root = os.path.abspath(project_root)
    if not os.path.isdir(root):
        raise FileNotFoundError(f"项目目录不存在：{root}")
    script_path = _pick_script(root)
    ins = parser_mod.parse_file(script_path)
    _strip_local_paths(ins)
    cfg = _load_config(root)

    out = os.path.abspath(out_dir)
    assets_dir = os.path.join(out, "assets")
    os.makedirs(assets_dir, exist_ok=True)

    images = _collect_image_names(ins, cfg)
    manifest: dict[str, str] = {}
    missing: list[str] = []
    # 标题页封面：拿工程里**最大的那张背景图**（按文件体积判断）。
    # 之前播放器自己按名字猜（第一个带 bg 的），猜中的常常是程序画的占位图 ——
    # 标题页是玩家看到的第一眼，不能拿一张几百字节的纯色图当封面。
    cover_name = ""
    cover_size = 0
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
        # 可选竖版构图：images/{name}_p.png 一并打包成 {name}_p，
        # 播放器按当前是横是竖挑一张；没有就回退主图 + 锚点裁切。
        var = find_variant_image(root, name)
        if var:
            vext = os.path.splitext(var)[1].lower()
            shutil.copyfile(var, os.path.join(assets_dir, name + "_p" + vext))
            manifest[name + "_p"] = "assets/" + name + "_p" + vext
        low = name.lower()
        if ("bg" in low or low.startswith("cg")) and "title" not in low:
            try:
                size = os.path.getsize(src)
            except OSError:
                size = 0
            if size > cover_size:
                cover_size = size
                cover_name = name

    # 只回填存在的那部分配置（缺的走播放器默认，避免前端处理空对象）
    picked = {k: cfg[k] for k in CONFIG_KEYS if k in cfg}
    picked["focal"] = _clean_focal(cfg.get("focal"))
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

    # P73：@video 帧序列背景。之前手机端直接不支持，导出来那段就是黑的。
    video_manifest, video_missing = _copy_video_frames(
        root, assets_dir, _collect_video_names(ins))
    missing.extend(video_missing)

    # P131：@video 名 file 真视频文件，拷进 assets/movies/。缺文件进 missing，不崩。
    movie_manifest: dict[str, str] = {}
    for name in _collect_movie_names(ins):
        try:
            src = _resolve_movie(root, name)
        except DataError:
            missing.append(name)
            continue
        ext = os.path.splitext(src)[1].lower()
        dst_name = name + ext
        os.makedirs(os.path.join(assets_dir, "movies"), exist_ok=True)
        shutil.copyfile(src, os.path.join(assets_dir, "movies", dst_name))
        movie_manifest[name] = "assets/movies/" + dst_name

    log = []
    # P62：music / sfx；P63：cg；P64：camera（zoom/pan/shake/reset）；
    # P73：fg 前景贴图、anim 立绘补间、video 帧序列 都已在播放器实现，不再列缺
    # play / stop 是空壳 op（parser 从不产出），列进去只会让人以为砍了功能
    pack = {
        "version": 1,
        "title": title or str(cfg.get("window_title") or os.path.basename(root)),
        "script": os.path.basename(script_path),
        "characters": _characters(ins),
        "config": picked,
        "assets": manifest,
        "audio": audio_manifest,
        "videos": video_manifest,
        "movies": movie_manifest,
        "ins": ins,
        # P67：作者选定的画面方向（any / portrait / landscape），播放器据此提示转屏
        "orientation": str(cfg.get("orientation") or "any"),
        # 标题页封面（挑体积最大的背景图；空 = 工程里没有像样的背景，播放器走渐变）
        "cover": cover_name,
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

    # P72：PWA —— 主屏图标 + manifest。导出的网页包丢到任意静态服务，
    # 玩家「添加到主屏幕」后就是全屏 App（没有地址栏挤画面）。
    pwa_files: list[str] = []
    try:
        pwa_files = list(pwa.write_bundle(out, pack["title"],
                                         str(cfg.get("orientation") or "any"))["files"])
    except Exception:  # noqa: BLE001 —— 图标生不出来不该拦导出
        pwa_files = []

    return {
        "out": out,
        "title": pack["title"],
        "instructions": len(ins),
        "images": len(manifest),
        "audio": len(audio_manifest),
        "movies": len(movie_manifest),
        "missing": missing,
        "unsupported": log,
        "pwa": pwa_files,
    }


MIME_BY_EXT = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".webp": "image/webp", ".gif": "image/gif", ".svg": "image/svg+xml",
    ".bmp": "image/bmp",
    ".ogg": "audio/ogg", ".mp3": "audio/mpeg", ".wav": "audio/wav",
    ".m4a": "audio/mp4", ".aac": "audio/aac",
    ".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime",
}

# P62：单文件里图片多大就够用。超过阈值的图缩到 SHRINK_MAX_EDGE 内重编码。
SHRINK_OVER_BYTES = 300 * 1024
SHRINK_MAX_EDGE = 1600
SHRINK_QUALITY = 82

# P101（手机内存预算）：只限单张长边是不够的——张数没有上限。
# 解码后的位图按 w*h*4 字节算，一张 1600×900 就是 5.6 MB，40 张背景直接 220 MB，
# 低端安卓的 WebView 在这个量级会白屏/闪退。所以打包时先量总解码量，
# 超了就自动换更小的长边重压，压到不能再压就明确报出来，别让玩家手机去扛。
DECODE_BUDGET = 96 * 1024 * 1024          # 超过这个，自动加狠压缩
DECODE_WARN = 64 * 1024 * 1024            # 超过这个，只提醒不动作
DECODE_EDGE_LADDER = (SHRINK_MAX_EDGE, 1280, 1024, 800)   # 逐级加狠

# 单文件体积：解码内存预算管的是「同时摊在画面上要多少」，管不到「这个 HTML 自身多重」。
# 手机 WebView 打开单文件版要先把整个 <script> 读进内存才出第一句，
# base64 内联本身还比原图胖 37%。40 MB 开始明显慢，80 MB 大概率直接白屏。
FILE_SOFT_WARN = 40 * 1024 * 1024
FILE_HARD_WARN = 80 * 1024 * 1024


def _estimate_decode(blob: bytes, edge: int) -> int:
    """按「将会缩到 edge」估算解码后位图字节（w*h*4）。读不到图头就返回 0。"""
    try:
        import io

        from PIL import Image
    except ImportError:
        return 0
    try:
        im = Image.open(io.BytesIO(blob))
        w, h = im.size
        if max(w, h) > edge:
            s = edge / float(max(w, h))
            w, h = max(1, int(w * s)), max(1, int(h * s))
        return w * h * 4
    except Exception:   # noqa: BLE001 — 读不动就当不算，绝不因为估算把导出搞挂
        return 0


def _pick_edge(blobs: list[bytes]) -> tuple[int, int]:
    """在所有候选图里挑一个「总解码量不超预算」的最大长边。返回 (edge, 总解码字节)。"""
    for edge in DECODE_EDGE_LADDER:
        total = sum(_estimate_decode(b, edge) for b in blobs)
        if total <= DECODE_BUDGET:
            return edge, total
    edge = DECODE_EDGE_LADDER[-1]
    return edge, sum(_estimate_decode(b, edge) for b in blobs)


def _over_edge(blob: bytes, edge: int) -> bool:
    """这张图的长边是否超过 edge（超了就该缩，哪怕文件本身不大）。"""
    try:
        import io

        from PIL import Image
    except ImportError:
        return False
    try:
        im = Image.open(io.BytesIO(blob))
        return max(im.size) > edge
    except Exception:   # noqa: BLE001
        return False



def _shrink_image(blob: bytes, max_edge: int = SHRINK_MAX_EDGE,
                  quality: int = SHRINK_QUALITY) -> tuple[bytes, str] | None:
    """把大图压小：缩到最大边 max_edge 内，存 WebP。不值得（压不下 10% / 没 PIL）返回 None。

    不改变逻辑尺寸，只降像素与码率——单文件里一张 2 MB 立绘能让整包卡在加载。
    """
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        import io

        im = Image.open(io.BytesIO(blob))
        if max(im.size) > max_edge:
            im.thumbnail((max_edge, max_edge),
                         Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "WEBP", quality=quality, method=4)
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

        # 先把图都读进来，量出「解码后要占多少手机内存」再决定压多狠。
        # 不这么做的话，大工程也能出包，但到了玩家手机上就是白屏。
        raws: list[tuple[str, bytes, str, str]] = []
        for name, rel in (pack.get("assets") or {}).items():
            path = os.path.join(tmp, rel.replace("/", os.sep))
            ext = os.path.splitext(path)[1].lower()
            mime = MIME_BY_EXT.get(ext, "application/octet-stream")
            try:
                with open(path, "rb") as f:
                    blob = f.read()
            except OSError:
                continue
            raws.append((name, blob, mime, ext))

        edge, decode_bytes = _pick_edge([b for _, b, _, _ in raws])
        if decode_bytes > DECODE_BUDGET:
            # 压到最小档还是超：照样出包（用户的作品不能被卡住），但必须说清后果。
            memory_warning = (
                f"素材解码后约 {decode_bytes // (1024 * 1024)} MB，"
                f"超过手机安全线 {DECODE_BUDGET // (1024 * 1024)} MB。"
                f"包能出，但低端机可能白屏——建议拆章，或把背景/立绘换小一点。"
            )
        elif decode_bytes > DECODE_WARN:
            memory_warning = (
                f"素材解码后约 {decode_bytes // (1024 * 1024)} MB（已自动把长边收到 {edge}）。"
                f"再往上加图就得注意低端机内存了。"
            )
        else:
            memory_warning = ""

        for name, blob, mime, ext in raws:
            # P62：大图压一道再内嵌。base64 本身还要再涨 37%，不压会更夸张。
            # P101：长边用上面按内存预算挑出来的 edge；哪怕文件不大，只要超了 edge 也缩。
            # P127：补 .webp。PIL 的 webp 读写都支持，但原先白名单里没有 ——
            # 一张 3000px 的 webp 背景就这么原样内联进单文件包，手机上解码就是大图。
            if ext in (".png", ".jpg", ".jpeg", ".bmp", ".webp") \
                    and (len(blob) > SHRINK_OVER_BYTES or _over_edge(blob, edge)):
                shrunk = _shrink_image(blob, max_edge=edge)
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

        # P73：@video 的帧序列同样要内联，否则单文件版里视频背景是空的
        videos: dict[str, list] = {}
        for name, rels in (pack.get("videos") or {}).items():
            arr: list[str] = []
            for rel in rels:
                path = os.path.join(tmp, rel.replace("/", os.sep))
                mime = MIME_BY_EXT.get(os.path.splitext(path)[1].lower(),
                                       "application/octet-stream")
                try:
                    with open(path, "rb") as f:
                        blob = f.read()
                except OSError:
                    continue
                if len(blob) > SHRINK_OVER_BYTES and mime == "image/png":
                    shrunk = _shrink_image(blob, max_edge=edge)
                    if shrunk:
                        blob, mime = shrunk
                arr.append(f"data:{mime};base64," + base64.b64encode(blob).decode("ascii"))
            videos[name] = arr
        pack["videos"] = videos

        # P131：真视频原样内联（不转码、不压帧），data URI 带 mime。
        movies: dict[str, dict] = {}
        for name, rel in (pack.get("movies") or {}).items():
            path = os.path.join(tmp, rel.replace("/", os.sep))
            mime = MIME_BY_EXT.get(os.path.splitext(path)[1].lower(),
                                   "video/mp4")
            try:
                with open(path, "rb") as f:
                    blob = f.read()
            except OSError:
                continue
            movies[name] = {
                "src": f"data:{mime};base64," + base64.b64encode(blob).decode("ascii"),
                "mime": mime,
            }
        pack["movies"] = movies
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
    file_mb = size / (1024 * 1024)
    # P131：movies 已内联进 pack_json，总体积自然计入；视频内联成 base64 比原文件再胖约 37%。
    if size > FILE_HARD_WARN:
        file_warning_level = "hard"
        file_warning = (
            f"单文件 {file_mb:.0f} MB，超过 {FILE_HARD_WARN // (1024 * 1024)} MB 硬线。"
            f"手机要先把整个文件读进内存才显示第一句，这个体积大概率白屏或闪退。"
            f"视频内联成 base64 会再胖约 37%，建议删素材，或者拆成多个章节包分开出。"
        )
    elif size > FILE_SOFT_WARN:
        file_warning_level = "soft"
        file_warning = (
            f"单文件 {file_mb:.0f} MB。低端机打开会明显慢一拍，还能用，但别再加素材了"
            f"（视频内联成 base64 会再胖约 37%）。"
        )
    else:
        file_warning_level = ""
        file_warning = ""
    return {
        "out": out,
        "title": pack["title"],
        "instructions": stat["instructions"],
        "images": len(assets),
        "audio": len(audio),
        "movies": len(movies),
        "saved": saved,
        "missing": stat["missing"],
        "unsupported": stat["unsupported"],
        "bytes": size,
        # P101：手机内存体检结果，给上层决定要不要提示用户
        "decode_mb": round(decode_bytes / (1024 * 1024), 1),
        "decode_edge": edge,
        "memory_warning": memory_warning,
        # P119：单文件自身体积（跟解码内存预算是两回事）
        "file_mb": round(file_mb, 1),
        "file_warning": file_warning,
        "file_warning_level": file_warning_level,
    }


def _render_single_html(title: str, pack_json: str, player_scripts: str,
                        orientation: str = "any") -> str:
    safe = (title or "MYONL").replace("<", "&lt;").replace(">", "&gt;")
    orient = orientation if orientation in ("portrait", "landscape") else "any"
    short = (title or "MYONL").strip()[:12] or "MYONL"
    short_esc = short.replace("<", "&lt;").replace(">", "&gt;")
    man_uri = pwa.inline_manifest(title or "MYONL", orient)
    icon_uri = ""
    try:
        icon_uri = pwa.icon_data_uri(pwa.APPLE_TOUCH_SIZE)
    except Exception:  # noqa: BLE001
        icon_uri = ""
    icon_link = (f'<link rel="apple-touch-icon" href="{icon_uri}">\n'
                 f'<link rel="icon" type="image/png" href="{icon_uri}">') if icon_uri else ""
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover,user-scalable=no">
<meta name="theme-color" content="#14161f">
<meta name="myonl-orientation" content="{orient}">
{_APPLE_META.format(short=short_esc)}
<link rel="manifest" href="{man_uri}">
{icon_link}
<title>{safe}</title>
<style>
  html, body {{ margin: 0; padding: 0; background: #0b0d12; overflow: hidden;
    -webkit-tap-highlight-color: transparent; user-select: none; }}
  #stage {{ position: fixed; inset: 0; display: flex; align-items: center; justify-content: center; }}
  #game {{ display: block; background: #000; box-shadow: 0 0 40px rgba(0,0,0,.6); }}{_BOOT_CSS}
</style>
</head>
<body>
{_boot_html(title)}
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


def _render_html(title: str, orientation: str = "any") -> str:
    safe = (title or "MYONL").replace("<", "&lt;").replace(">", "&gt;")
    orient = orientation if orientation in ("portrait", "landscape") else "any"
    short = (title or "MYONL").strip()[:12] or "MYONL"
    short_esc = short.replace("<", "&lt;").replace(">", "&gt;")
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover,user-scalable=no">
<meta name="theme-color" content="#14161f">
<meta name="myonl-orientation" content="{orient}">
{_APPLE_META.format(short=short_esc)}
<link rel="manifest" href="manifest.json">
<link rel="apple-touch-icon" href="apple-touch-icon.png">
<link rel="icon" type="image/png" href="icons/icon-192.png">
<title>{safe}</title>
<style>
  html, body {{ margin: 0; padding: 0; background: #0b0d12; overflow: hidden;
    -webkit-tap-highlight-color: transparent; user-select: none; }}
  #stage {{ position: fixed; inset: 0; display: flex; align-items: center; justify-content: center; }}
  #game {{ display: block; background: #000; box-shadow: 0 0 40px rgba(0,0,0,.6); }}{_BOOT_CSS}
</style>
</head>
<body>
{_boot_html(title)}
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
              + (f"　视频 {s['movies']} 段" if s.get("movies") else "")
              + f"　{s['bytes'] / 1024:.0f} KB")
        if s.get("saved"):
            print(f"  大图压缩省下 {s['saved'] / 1024:.0f} KB（原图每张超 "
                  f"{SHRINK_OVER_BYTES // 1024} KB 的会转 WebP）")
        if s["missing"]:
            print(f"  [缺素材 {len(s['missing'])}]：" + "、".join(s["missing"]))
        # P101：手机内存体检。这个数是「玩家打开时手机要摊多少位图」，不是文件大小。
        print(f"  手机内存：素材解码后约 {s.get('decode_mb', 0)} MB"
              f"（长边收到 {s.get('decode_edge', 0)}）")
        if s.get("memory_warning"):
            print(f"  [注意] {s['memory_warning']}")
        # P119：文件自身体积。跟上面那个解码内存不是一回事。
        print(f"  文件体积：{s.get('file_mb', 0)} MB")
        if s.get("file_warning"):
            print(f"  [注意] {s['file_warning']}")
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
          + (f"　音频 {stat['audio']} 条" if stat.get("audio") else "")
          + (f"　视频 {stat['movies']} 段" if stat.get("movies") else ""))
    if stat["missing"]:
        print(f"  [缺素材 {len(stat['missing'])}]：" + "、".join(stat["missing"]))
    if stat["unsupported"]:
        print(f"  [桌面端有、移动端暂不支持]：" + "、".join(stat["unsupported"]))
    print("  本地预览：双击 index.html，或起个静态服务再看（视频/音频需要 http）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
