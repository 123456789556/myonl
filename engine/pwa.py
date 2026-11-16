"""PWA 支持：主屏图标 + manifest + iOS 全屏 meta。

手机端是主线：作者把网页包丢到任意静态服务（或 GitHub Pages）后，玩家「添加到主屏幕」
就能像 App 一样全屏跑 —— 没有地址栏、没有状态栏挤压画面。这是网页包和 APK 之间最省的形态。

单文件版（双击 .html / file:// 打开）拿不到 service worker，但 apple-mobile-web-app
与内联 manifest 仍然能让 iOS / Android 建一个全屏图标 —— 微信里发过去的 .html 也能装。
"""

from __future__ import annotations

import base64
import io
import json
import os

# 与 theme-color 一致的深底，图标里不要出现橙黄（作者方的审美基线）
BG = (20, 22, 31, 255)
MARK = (79, 140, 255, 255)
INK = (244, 246, 255, 255)

ICON_SIZES = (192, 512)
APPLE_TOUCH_SIZE = 180


def _icon_png(size: int, maskable: bool = False) -> bytes:
    """画一枚图标：上面半透明「立绘」，中间蓝对话框，下面两枚选项胶囊。

    纯几何，不依赖字体（这机器上的中文字体不一定有，图标里放字会变豆腐块）。
    maskable 版本把内容缩到 78% —— Android 自适应图标会裁掉外圈。
    """
    from PIL import Image, ImageDraw

    ss = 4
    px = size * ss
    # 必须用 RGB 画板：ImageDraw 在 RGBA 画板上是把像素直接替换（alpha 不混合），
    # 半透明的立绘/胶囊会变成纯白实心。
    img = Image.new("RGB", (px, px), (BG[0], BG[1], BG[2]))
    d = ImageDraw.Draw(img, "RGBA")
    k = 0.78 if maskable else 1.0
    mid = px * 0.5

    def xy(x0: float, y0: float, x1: float, y1: float) -> tuple[float, float, float, float]:
        return (mid + (x0 - 0.5) * k * px, mid + (y0 - 0.5) * k * px,
                mid + (x1 - 0.5) * k * px, mid + (y1 - 0.5) * k * px)

    def rr(x0: float, y0: float, x1: float, y1: float, r: float, *,
           fill=None, outline=None, width: float = 0.0) -> None:
        d.rounded_rectangle(xy(x0, y0, x1, y1), radius=int(r * px * k),
                            fill=fill, outline=outline,
                            width=int(width * px * k) if width else 0)

    # 立绘占位（头 + 肩，只用淡白，缩小后是一团浅影）
    d.ellipse(xy(0.42, 0.20, 0.58, 0.34), fill=(INK[0], INK[1], INK[2], 120))
    rr(0.34, 0.335, 0.66, 0.44, 0.03, fill=(INK[0], INK[1], INK[2], 78))

    # 对话框（主体色块：缩到 32px 也认得出这是「说话的地方」）
    rr(0.18, 0.44, 0.82, 0.665, 0.045, fill=MARK)
    rr(0.255, 0.495, 0.62, 0.518, 0.012, fill=(BG[0], BG[1], BG[2], 225))
    rr(0.255, 0.548, 0.49, 0.571, 0.012, fill=(BG[0], BG[1], BG[2], 200))

    # 两枚选项胶囊
    rr(0.18, 0.715, 0.82, 0.782, 0.034, fill=(INK[0], INK[1], INK[2], 58),
       outline=(INK[0], INK[1], INK[2], 150), width=0.009)
    rr(0.18, 0.803, 0.82, 0.87, 0.034, fill=(INK[0], INK[1], INK[2], 58),
       outline=(INK[0], INK[1], INK[2], 150), width=0.009)

    img = img.resize((size, size), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def icon_data_uri(size: int = 192, maskable: bool = False) -> str:
    """data URI 版图标（单文件导出内联用，省得再带一堆附属文件）。"""
    return "data:image/png;base64," + base64.b64encode(_icon_png(size, maskable)).decode("ascii")


def _orientation_value(orientation: str) -> str:
    return orientation if orientation in ("portrait", "landscape") else "any"


def manifest_dict(title: str, orientation: str = "any",
                  icons: list[dict] | None = None) -> dict:
    """构造 manifest。start_url 用 "./" —— 部署到子目录（GitHub Pages 项目页）也能开。"""
    name = (title or "MYONL").strip() or "MYONL"
    # 主屏图标下面的小字，太长会被系统截断成一坨，先自己截
    short = name if len(name) <= 12 else name[:11] + "…"
    body: dict = {
        "name": name,
        "short_name": short,
        "start_url": "./",
        "scope": "./",
        "display": "standalone",
        "display_override": ["standalone", "fullscreen"],
        "orientation": _orientation_value(orientation),
        "background_color": "#0b0d12",
        "theme_color": "#14161f",
        "lang": "zh-CN",
    }
    if icons:
        body["icons"] = icons
    return body


def write_bundle(out_dir: str, title: str, orientation: str = "any") -> dict:
    """网页包用：把图标与 manifest.json 落盘到输出目录。返回写出的相对路径。"""
    icons_dir = os.path.join(out_dir, "icons")
    os.makedirs(icons_dir, exist_ok=True)
    written: list[str] = []
    icons: list[dict] = []
    try:
        for size in ICON_SIZES:
            rel = f"icons/icon-{size}.png"
            with open(os.path.join(out_dir, rel), "wb") as f:
                f.write(_icon_png(size))
            written.append(rel)
            icons.append({"src": rel, "sizes": f"{size}x{size}", "type": "image/png",
                          "purpose": "any"})
        rel = "icons/icon-512-maskable.png"
        with open(os.path.join(out_dir, rel), "wb") as f:
            f.write(_icon_png(512, maskable=True))
        written.append(rel)
        icons.append({"src": rel, "sizes": "512x512", "type": "image/png",
                      "purpose": "maskable"})
        rel = "apple-touch-icon.png"
        with open(os.path.join(out_dir, rel), "wb") as f:
            f.write(_icon_png(APPLE_TOUCH_SIZE))
        written.append(rel)
    except Exception:  # noqa: BLE001 —— 没有 PIL 时不拦导出，只是图标缺一张
        icons = []
    man = manifest_dict(title, orientation, icons)
    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(man, f, ensure_ascii=False, indent=2)
    written.append("manifest.json")
    return {"files": written, "icons": icons, "manifest": man}


def inline_manifest(title: str, orientation: str = "any") -> str:
    """单文件用：manifest 走 data URI 内联，图标一起塞进去（约 6 KB，值得）。"""
    try:
        icons = [
            {"src": icon_data_uri(192), "sizes": "192x192", "type": "image/png",
             "purpose": "any"},
            {"src": icon_data_uri(512), "sizes": "512x512", "type": "image/png",
             "purpose": "any"},
        ]
    except Exception:  # noqa: BLE001
        icons = []
    man = manifest_dict(title, orientation, icons)
    raw = json.dumps(man, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return "data:application/manifest+json;base64," + base64.b64encode(raw).decode("ascii")
