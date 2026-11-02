# -*- coding: utf-8 -*-
"""打包后的玩家入口（pack.py 与内置玩家模板共用）。

打包产物 = 本入口 + 引擎运行库 + 游戏目录（script.gal / images / audio …）。
启动后以 exe 所在目录为游戏根：存档、设置都落在 exe 旁，双击即玩。

为什么单独成文件：编辑器发行版没有 Python/PyInstaller，运行时要打包游戏
只能复制一份**预构建的玩家模板**；模板与源码打包必须使用同一个入口，
否则两条路径的行为（工作目录、报错弹窗）会漂移。
"""
from __future__ import annotations

import os
import sys


def _game_root() -> str:
    """打包后 = exe 所在目录；开发时 = 本脚本所在目录。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _fail(message: str) -> None:
    """图形化报错（打包成窗口程序后没有控制台，用系统对话框提示）。"""
    print(message, file=sys.stderr)
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, message, "启动失败", 16)
    except Exception:  # noqa: BLE001 — 弹窗失败不影响退出
        pass


def main() -> int:
    from engine.demo import run

    root = _game_root()
    # 以游戏目录为工作目录：存档（saves/）、设置等相对路径资源都落在 exe 旁
    os.chdir(root)
    script = os.path.join(root, "script.gal")
    if not os.path.isfile(script):
        _fail("找不到剧本文件：" + script + "\n请确认 script.gal 与 exe 在同一个目录。")
        return 1
    try:
        run(script, assets_root=root, auto=False)
    except (OSError, RuntimeError) as e:
        _fail("运行失败：" + str(e))
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
