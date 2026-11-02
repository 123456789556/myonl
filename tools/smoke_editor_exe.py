# -*- coding: utf-8 -*-
"""编辑器发行包冒烟（M1 验收用）：验证 dist/editor/editor.exe 可启动、能在冻结形态跑引擎。

检查：
1. `editor.exe -h` 退出码 0 —— exe 依赖能加载（未被缺 DLL / 杀软拦截）
2. `editor.exe --demo-worker <示例剧本> --assets <资源根> --auto --max-frames 30` 退出码 0
   —— 验证 PyInstaller 冻结后 engine.demo 真能跑（编辑器「运行」走的就是这条路径）
   （用 SDL dummy 驱动，不弹窗）

用法：
    py -3 tools/smoke_editor_exe.py
    py -3 tools/smoke_editor_exe.py --exe dist/editor/editor.exe --project games/标准示例

退出码：0 = 通过；1 = 失败；2 = 找不到 exe 或示例工程。
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(cmd: list[str], timeout: int) -> tuple[int, float]:
    env = dict(os.environ)
    env.setdefault("SDL_VIDEODRIVER", "dummy")
    env.setdefault("SDL_AUDIODRIVER", "dummy")
    env.setdefault("PYTHONUTF8", "1")
    started = time.perf_counter()
    try:
        proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, timeout=timeout, env=env)
        return proc.returncode, time.perf_counter() - started
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"  运行失败：{type(exc).__name__}: {exc}")
        return 1, time.perf_counter() - started


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="编辑器发行包冒烟")
    ap.add_argument("--exe", default=str(ROOT / "dist" / "editor" / "editor.exe"))
    ap.add_argument("--project", default=str(ROOT / "games" / "标准示例"))
    args = ap.parse_args(argv)

    exe = Path(args.exe)
    project = Path(args.project)
    script = project / "script.gal"
    if not exe.is_file():
        print(f"错误：找不到 {exe}（先跑 build_editor.bat 或 py -3 -m PyInstaller --noconfirm --clean editor.spec）")
        return 2
    if not script.is_file():
        print(f"错误：找不到示例剧本 {script}")
        return 2

    print(f"冒烟对象：{exe}（{exe.stat().st_size / 1024 / 1024:.1f} MB）")
    print(f"示例工程：{project}")

    code, secs = _run([str(exe), "-h"], timeout=60)
    print(f"[1/2] editor.exe -h            → exit {code}（{secs:.1f}s）")
    if code != 0:
        print("失败：exe 连参数解析都起不来，检查 PyInstaller 依赖/杀软拦截")
        return 1

    cmd = [str(exe), "--demo-worker", str(script), "--assets", str(project),
           "--auto", "--max-frames", "30"]
    code, secs = _run(cmd, timeout=180)
    print(f"[2/2] editor.exe --demo-worker → exit {code}（{secs:.1f}s）")
    if code != 0:
        print("失败：冻结形态跑不了 engine.demo，编辑器「运行」按钮在发行包里会失效")
        return 1

    print("冒烟通过：发行包可启动，且冻结形态能跑引擎 demo。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
