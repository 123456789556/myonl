# -*- coding: utf-8 -*-
"""P44-B1 标准模板验证截图：标准示例游戏（standard 模板成品）各界面。

  p44_std_title.png     标题界面
  p44_std_dialogue.png  对话界面（天台背景+林晚立绘+对话框）
  p44_std_choice.png    选项分支界面
  p44_std_settings.png  设置界面
  p44_std_saves.png     存档界面
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pygame

from engine.renderer import Renderer
from engine.ui import UI

ASSETS = ROOT / "games" / "标准示例"
OUT = ROOT / "screenshots"
OUT.mkdir(exist_ok=True)


def shot(ren, name):
    path = str(OUT / name)
    ren.screenshot(path)
    print("saved", path, os.path.getsize(path), "bytes")


def main():
    pygame.init()
    ren = Renderer((1280, 720), str(ASSETS))
    ui = UI()
    state = {
        "bg": "bg_天台", "music": None, "video": None,
        "sprites": [{"char": "林晚", "expr": "微笑", "anim": "呼吸"}],
        "vars": {}, "characters": {"林晚": {"color": "#ffb3c8"}, "我": {"color": "#8ecae6"}},
        "history": [{"char": "林晚", "text": "不过……今天夕阳很好看，我就不计较了。"}],
        "pending_choice": {"options": [
            {"text": "一起看日落", "target": "结局_看日落", "available": True},
            {"text": "说出那个约定", "target": "结局_约定", "available": True},
        ]},
        "finished": False,
    }

    # 1 标题界面
    ui.mode = "title"
    ren.render(state, ui.view())
    shot(ren, "p44_std_title.png")

    # 2 对话界面
    ui.mode = "playing"
    ren.render(state, ui.view())
    shot(ren, "p44_std_dialogue.png")

    # 3 选项界面
    state["pending_choice"]["options"][0]["available"] = True
    ren.render(state, ui.view())
    shot(ren, "p44_std_choice.png")

    # 4 设置界面
    ui.click({"kind": "quickbar", "index": 5})
    ren.render(state, ui.view())
    shot(ren, "p44_std_settings.png")

    # 5 存档界面
    ui.click({"kind": "quickbar", "index": 0})
    ren.render(state, ui.view())
    shot(ren, "p44_std_saves.png")


if __name__ == "__main__":
    main()
