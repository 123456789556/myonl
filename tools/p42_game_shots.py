# -*- coding: utf-8 -*-
"""P42 打包游戏默认配置展示截图（无头 dummy 模式）。

用 games/newbie_demo（默认模板，素材自绘版权干净）渲染游戏运行各界面：
  p42_title.png      标题界面
  p42_dialogue.png   对话界面（背景+立绘+对话框）
  p42_choice.png     选项分支界面
  p42_settings.png   游戏设置界面
  p42_saves.png      存档界面
输出到 screenshots/，供产品说明书配图。
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

ASSETS = ROOT / "games" / "newbie_demo"
OUT = ROOT / "screenshots"
OUT.mkdir(exist_ok=True)


def base_state():
    return {
        "bg": "教室", "music": None, "video": None,
        "sprites": [{"char": "林晚", "expr": "微笑", "anim": "呼吸"}],
        "vars": {}, "characters": {"林晚": {"color": "#aaccff"}},
        "history": [{"char": "林晚", "text": "你好，我是林晚。带你 30 分钟做第一个游戏。"}],
        "pending_choice": {"options": [
            {"text": "接下来去哪？", "target": "教室", "available": True},
            {"text": "直接看结局吧", "target": "结局", "available": True},
        ]},
        "finished": False,
    }


def shot(ren, name):
    path = str(OUT / name)
    ren.screenshot(path)
    print("saved", path)


def main():
    pygame.init()
    ren = Renderer((1280, 720), str(ASSETS))
    ui = UI()
    try:
        state = base_state()

        # 1 标题界面
        ui.mode = "title"
        ren.render(state, ui.view())
        shot(ren, "p42_title.png")

        # 2 对话界面
        ui.mode = "playing"
        ren.render(state, ui.view())
        shot(ren, "p42_dialogue.png")

        # 3 选项界面（renderer 检测 pending_choice 自动进入选项态）
        ui.mode = "playing"
        ren.render(state, ui.view())
        shot(ren, "p42_choice.png")

        # 4 设置界面（快捷栏 CONFIG）
        ui.mode = "playing"
        ui.click({"kind": "quickbar", "index": 5})
        ren.render(state, ui.view())
        shot(ren, "p42_settings.png")

        # 5 存档界面（快捷栏 SAVE）
        ui.mode = "playing"
        ui.click({"kind": "quickbar", "index": 0})
        ren.render(state, ui.view())
        shot(ren, "p42_saves.png")
    finally:
        pygame.quit()
    print("done")


if __name__ == "__main__":
    main()
