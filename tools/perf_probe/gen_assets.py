# -*- coding: utf-8 -*-
"""性能实测素材生成：PNG 图（dataURI）+ 一段真视频（mp4 dataURI）。

只写给 tools/perf_probe 下的临时 pack 用，不进 games/ 正式素材库。
产物落在 outDir：
  images.json  {名: dataURI}   images 模式
  movies.json  {名: {src, mime}}  movie 模式

图片规格：1280x720，纯色 + 渐变横条，每张解码后位图 ≈ 1280*720*4 = 3.51 MB。
视频规格：640x360，3 秒，h264，便于在桌面 Chromium 里真解码。

用法：
  python tools/perf_probe/gen_assets.py --out <dir> --mode images --count 60
  python tools/perf_probe/gen_assets.py --out <dir> --mode movie
"""
from __future__ import annotations

import argparse
import base64
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FFMPEG = Path(r"D:\ffmpeg\bin\ffmpeg.exe")

try:
    from PIL import Image, ImageDraw
except ImportError:  # pragma: no cover
    print("[gen_assets] 需要 Pillow：pip install pillow", file=sys.stderr)
    raise


def _png_data_uri(img: Image.Image) -> str:
    import io
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=False)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return "data:image/png;base64," + b64


def gen_images(out_dir: Path, count: int) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    assets: dict[str, str] = {}
    W, H = 1280, 720
    for i in range(count):
        # 每张一个色相，保证浏览器不会把同一张图去重成一个解码对象
        hue = (i * 137) % 360
        # HSL 转 RGB（简化：用固定明暗，色相轮换）
        import colorsys
        r, g, b = colorsys.hsv_to_rgb(hue / 360.0, 0.45, 0.85)
        base = (int(r * 255), int(g * 255), int(b * 255))
        img = Image.new("RGB", (W, H), base)
        d = ImageDraw.Draw(img)
        # 几条横条 + 编号，制造可区分的像素内容（避免压缩成同一张）
        for band in range(6):
            y0 = band * H // 6
            shade = 0.75 + 0.1 * band
            c = tuple(min(255, int(x * shade)) for x in base)
            d.rectangle([0, y0, W, y0 + H // 6], fill=c)
        d.text((40, 40), f"bg_{i:03d}", fill=(20, 24, 34))
        assets[f"bg_{i:03d}"] = _png_data_uri(img)
    (out_dir / "images.json").write_text(
        json.dumps(assets, ensure_ascii=False), encoding="utf-8")
    print(f"[gen_assets] images={count} -> {out_dir / 'images.json'}")


def gen_movie(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = out_dir / "probe_movie.mp4"
    # 3 秒 640x360，h264，yuv420p，无音频；纯色 + 移动色块便于确认在真解码
    cmd = [
        str(FFMPEG), "-y",
        "-f", "lavfi", "-i",
        "color=c=0x223355:s=640x360:d=3:r=24",
        "-f", "lavfi", "-i",
        "color=c=0x4f8cff:s=200x120:d=3:r=24",
        "-filter_complex", "[0][1]overlay=x='(W-w)/2+60*sin(t*3)':y='(H-h)/2'",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-t", "3",
        "-an", str(tmp),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    b64 = base64.b64encode(tmp.read_bytes()).decode("ascii")
    movies = {"mov1": {"src": "data:video/mp4;base64," + b64, "mime": "video/mp4"}}
    (out_dir / "movies.json").write_text(
        json.dumps(movies, ensure_ascii=False), encoding="utf-8")

    # 帧序列视频（@video 纯名字，走 Image 帧池）：12 帧 640x360 PNG，色块逐帧偏移。
    # 转屏 t0 重置验证用：帧号可从 t0 推算，转屏前后对比帧号是否连续。
    frames: dict[str, list[str]] = {"seq1": []}
    W, H = 640, 360
    for i in range(12):
        img = Image.new("RGB", (W, H), (34, 51, 85))
        d = ImageDraw.Draw(img)
        x = int((W - 200) * i / 11)
        d.rectangle([x, (H - 120) // 2, x + 200, (H + 120) // 2], fill=(79, 140, 255))
        d.text((20, 20), f"frame {i:02d}", fill=(230, 240, 255))
        frames["seq1"].append(_png_data_uri(img))
    (out_dir / "videos.json").write_text(
        json.dumps(frames, ensure_ascii=False), encoding="utf-8")
    print(f"[gen_assets] movie -> {out_dir / 'movies.json'} "
          f"({tmp.stat().st_size} bytes); frames seq1={len(frames['seq1'])}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--mode", choices=["images", "movie"], required=True)
    ap.add_argument("--count", type=int, default=20)
    args = ap.parse_args()
    out_dir = Path(args.out)
    if args.mode == "images":
        gen_images(out_dir, args.count)
    else:
        gen_movie(out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
