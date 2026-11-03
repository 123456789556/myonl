# -*- coding: utf-8 -*-
"""游戏内桌宠宿主：按玩家设置拉起 / 关闭桌宠子进程。

为什么单独成模块：桌宠是独立 pygame 进程（engine/pet.py），游戏主循环只负责
「开 / 关」；做成极薄的宿主，游戏退出时可统一清理，不会留下孤儿窗口。

范围说明：桌宠按历史决定只进引擎、不进游戏包（pack.py 排除 engine.pet），
所以这里只支持源码模式；发行版游戏里开关只保存设置，并给出明确中文提示。

安全阀：
- 环境变量 MYONL_NO_PET=1 时完全不启动（测试 / 无显示环境用）
- SDL 驱动为 dummy（无头测试）时同样不启动
- 启动失败只打印中文警告，绝不影响游戏主循环
"""
from __future__ import annotations

import os
import subprocess
import sys

_PROC: subprocess.Popen | None = None


def _blocked() -> bool:
    """无头/测试环境不启动桌宠。"""
    if os.environ.get("MYONL_NO_PET", "") not in ("", "0", "false", "False"):
        return True
    return os.environ.get("SDL_VIDEODRIVER", "").lower() == "dummy"


def is_running() -> bool:
    return bool(_PROC and _PROC.poll() is None)


def start() -> tuple[bool, str]:
    """启动桌宠；已运行直接返回成功。返回 (是否在运行, 中文说明)。"""
    global _PROC
    if is_running():
        return True, "桌宠已在运行"
    if _blocked():
        return False, "当前环境不支持桌宠（无头/已禁用）"
    if getattr(sys, "frozen", False):
        return False, "当前游戏包未包含桌宠（仅源码模式可用）"
    try:
        _PROC = subprocess.Popen(
            [sys.executable, "-m", "engine.pet"],
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as e:
        _PROC = None
        return False, f"桌宠启动失败：{e}"
    return True, "桌宠已打开"


def stop() -> None:
    """关闭桌宠；未运行时什么也不做。"""
    global _PROC
    proc = _PROC
    _PROC = None
    if proc is None or proc.poll() is not None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=3)
    except (OSError, subprocess.TimeoutExpired):
        try:
            proc.kill()
        except OSError:
            pass


def sync(enabled) -> None:
    """按玩家开关同步桌宠状态：开 → 拉起，关 → 关闭。失败只告警。"""
    if enabled in (True, 1, "1", "true", "True", "on", "yes"):
        ok, message = start()
        if not ok:
            print(f"[桌宠] {message}", file=sys.stderr)
    else:
        stop()
