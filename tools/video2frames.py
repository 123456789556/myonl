# -*- coding: utf-8 -*-
"""video2frames：把任意视频转成 MYONL 帧序列（@video 视频背景用）。

用法：
    python tools/video2frames.py 输入.mp4 --name 雨夜 --fps 30 --out images/videos
    python tools/video2frames.py 输入.mp4 --name 雨夜 --webp   # 体积小 5~10 倍

输出：<out>/<名称>_001.png（或 .webp），001 起连续编号——引擎运行时按该约定播放。

依赖：ffmpeg 命令行（作者侧工具，游戏运行时零依赖）。
    Windows 安装：winget install ffmpeg 或官网下载后把 bin 加入 PATH。
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="video2frames",
        description="把视频转成 MYONL 帧序列：python tools/video2frames.py 输入.mp4 --name 雨夜 --fps 30")
    ap.add_argument("input", help="输入视频文件（ffmpeg 支持的格式均可）")
    ap.add_argument("--name", default=None, help="帧序列名称（默认取输入文件名）；引擎里写 @video 名称")
    ap.add_argument("--fps", type=int, default=30, help="抽帧帧率（默认 30，需与剧本里 fps= 一致）")
    ap.add_argument("--out", default="images/videos", help="输出目录（默认 images/videos）")
    ap.add_argument("--webp", action="store_true", help="输出 .webp（体积小 5~10 倍，pygame-ce 可直接加载）")
    args = ap.parse_args(argv)

    src = Path(args.input)
    if not src.is_file():
        print(f"错误：输入视频不存在：{src}", file=sys.stderr)
        return 2
    if args.fps <= 0:
        print(f"错误：fps 必须是正整数，实际为 {args.fps}", file=sys.stderr)
        return 2
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        print("错误：找不到 ffmpeg 命令。请先安装 ffmpeg 并加入 PATH"
              "（Windows：winget install ffmpeg）。", file=sys.stderr)
        return 2

    name = args.name or src.stem
    ext = "webp" if args.webp else "png"
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    pattern = str(out_dir / f"{name}_%03d.{ext}")

    cmd = [ffmpeg, "-y", "-i", str(src), "-vf", f"fps={args.fps}"]
    if args.webp:
        cmd += ["-c:v", "libwebp", "-q:v", "90"]
    cmd.append(pattern)

    print(f"抽帧中：{src} → {pattern}（fps={args.fps}）")
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        tail = (proc.stderr or "").strip().splitlines()[-5:]
        print("错误：ffmpeg 抽帧失败：\n" + "\n".join(tail), file=sys.stderr)
        return 1

    count = len(list(out_dir.glob(f"{name}_*.{ext}")))
    if count == 0:
        print("错误：ffmpeg 跑完了但没有产出任何帧，请检查输入视频内容。", file=sys.stderr)
        return 1
    print(f"完成：共 {count} 帧 → {out_dir}/{name}_001.{ext} ~ {name}_{count:03d}.{ext}")
    print(f'剧本里写：@video {name}' + ("" if args.fps == 30 else f" fps={args.fps}"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
