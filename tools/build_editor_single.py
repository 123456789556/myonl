"""把编辑器打成一个独立 HTML —— 手机上不接电脑也能编。

编辑器本来就是纯前端（HTML + CSS + JS），没有后端时靠 editor/gal_offline.js
在浏览器里顶替 /api/*。所以只要把所有 js/css 内联进一个文件，
手机浏览器（或 APK 的 assets）打开它就能编游戏。

和内联之前的行为差别只有一个：没有 Python 后端，
作品存在这台设备的 localStorage 里，还能导出 .gal。

用法： py -3 tools/build_editor_single.py [输出路径]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EDITOR = ROOT / "editor"


def _read(name: str) -> str:
    return (EDITOR / name).read_text(encoding="utf-8")


def build(out_file: Path) -> dict:
    html = _read("index.html")

    # <script src="/x.js?v=p98"></script> → 内联
    def inline_js(m: re.Match) -> str:
        fname = m.group(1)
        # 找文件的三条路：editor/ 根、editor/mobile/（P194 起手机端单独住）、engine/（内核共用）
        path = EDITOR / fname
        if not path.is_file():
            path = EDITOR / "mobile" / fname
        if not path.is_file():
            path = ROOT / "engine" / fname
        if not path.is_file():
            raise SystemExit("单文件打包：找不到 %s，别让它静默变成 404" % fname)
        body = path.read_text(encoding="utf-8")
        body = body.replace("</script>", "<\\/script>")   # 防止提前闭合
        return "<script>\n/* ==== %s ==== */\n%s\n</script>" % (fname, body)

    html, n_js = re.subn(
        r'<script src="/((?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_]+\.js)(?:\?v=[^"]*)?"[^>]*></script>',
        inline_js,
        html,
    )

    # <link rel="stylesheet" href="/editor.css"> → 内联（P197c 起允许 mobile/ 这种子目录路径）
    def inline_css(m: re.Match) -> str:
        fname = m.group(1)
        path = EDITOR / fname
        if not path.is_file():
            raise SystemExit("单文件打包：找不到样式 %s" % fname)
        return "<style>\n%s\n</style>" % path.read_text(encoding="utf-8")

    html, n_css = re.subn(
        r'<link[^>]*href="/((?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_-]+\.css)(?:\?v=[^"]*)?"[^>]*>',
        inline_css,
        html,
    )

    # 剩下的指向本站的绝对资源（图标/manifest/字体）在单文件里不存在，
    # 去掉它们，免得手机上每次打开都刷一串 404。
    html = re.sub(r'<link[^>]*href="/(?:icon-\d+\.png|manifest\.webmanifest)"[^>]*>', "", html)

    # 版本号写进单文件：手机上没有后端，拿不到 /api/version，
    # 设置页要显示"这台设备上是哪一版"就只能靠这里烙进去。
    ver = "dev"
    vfile = ROOT / "engine" / "_version.py"
    if vfile.is_file():
        mv = re.search(r'^VERSION\s*=\s*"([^"]+)"', vfile.read_text(encoding="utf-8"), re.M)
        if mv:
            ver = mv.group(1)
    html = html.replace("__MYONL_VERSION__", ver)

    title = "MYONL 编辑器"
    m = re.search(r"<title>(.*?)</title>", html, re.S)
    if m:
        title = m.group(1).strip()

    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(html, encoding="utf-8")
    return {"path": str(out_file), "bytes": out_file.stat().st_size,
            "scripts": n_js, "styles": n_css, "title": title}


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    out = Path(argv[0]) if argv else (ROOT / "dist" / "web" / "editor-single.html")
    info = build(out)
    print("已生成 %s（%.2f MB，内联 %d 个脚本 / %d 个样式）"
          % (info["path"], info["bytes"] / 1048576, info["scripts"], info["styles"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
