# -*- coding: utf-8 -*-
"""临时切换 SDL 驱动（无头预览/生成素材），调用结束立刻恢复原环境。

为什么必须恢复：编辑器进程会反复做无头预览；如果直接 `os.environ.setdefault`
把 SDL_VIDEODRIVER 改成 dummy，之后它 spawn 的「▶ 运行」子进程会继承 dummy，
于是游戏进程永远不弹窗（看起来像点了没反应）。用装饰器把改动限制在本次调用内。
"""
from __future__ import annotations

import functools
import os

_DUMMY_KEYS = ("SDL_VIDEODRIVER", "SDL_AUDIODRIVER")


def dummy_video(func):
    """装饰一个需要 dummy SDL 的函数：进入设 dummy，退出恢复原值。"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        saved = {key: os.environ.get(key) for key in _DUMMY_KEYS}
        os.environ["SDL_VIDEODRIVER"] = "dummy"
        os.environ["SDL_AUDIODRIVER"] = "dummy"
        try:
            return func(*args, **kwargs)
        finally:
            for key, value in saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    return wrapper
