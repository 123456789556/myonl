# -*- coding: utf-8 -*-
"""P44 空包验证：newgame 生成标准模板 → 渲染标题帧存 PNG（无头），检查黑·左列·5 项。"""
import os
import sys
import tempfile

os.environ["SDL_VIDEODRIVER"] = "dummy"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # 项目根

from engine import newgame
from engine.config import load as load_config
from engine.renderer import Renderer
from engine.ui import UI

root = newgame.create_game("测试空包", tempfile.mkdtemp(), template="standard")
cfg = load_config(str(root))
ui = UI(config=cfg)
ui.settings_path = os.path.join(str(root), "settings.json")  # 作品名从本游戏 settings.json 读
ui.refresh()
view = ui.view()
ren = Renderer((1280, 720), str(root))
try:
    ren.render({}, view)
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "p44_title_black_left.png")
    import pygame
    pygame.image.save(ren._screen, out)
    print("SAVED:", out)
    print("ITEMS:", [it["label"] for it in view["items"]])
    print("ALIGN:", cfg.ui_value("title", "align"))
    print("PRIMARY:", cfg.theme_color("primary"))
finally:
    ren.close()
