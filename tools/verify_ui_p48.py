# -*- coding: utf-8 -*-
"""P48 UI 批验证：标题（无横线/无框）、存档九宫格、对话框新样式 + 快捷栏对称三角。

帧输出 tools/ui_p48/：
  01_title_p48.png      标题（去横线、焦点项无框）
  02_slots_p48.png      存档 3×3 九宫格（缩略图卡片）
  03_dialog_p48.png     旁白对话框（无圆角加深区 + ▲ 把手 + 快捷栏 ◀▶）
"""
import os
import sys
import tempfile

os.environ["SDL_VIDEODRIVER"] = "dummy"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame

from engine import newgame, save as save_api
from engine.config import load as load_config
from engine.data import load_gallery_config
from engine.demo import _read_script_title, _step, _post_save_enrich
from engine.renderer import Renderer
from engine.runtime import Runtime
from engine.ui import UI

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui_p48")
os.makedirs(OUT, exist_ok=True)


def snap(ren, ui, name, state=None):
    view = ui.view()
    st = state if state is not None else {}
    for _ in range(30):
        ren.render(st, view)
    path = os.path.join(OUT, name)
    pygame.image.save(ren._screen, path)
    print("SAVED:", name, "| mode:", view.get("mode"))
    return path


def advance(rt, ren, steps, dt=0.15):
    for _ in range(steps):
        rt.advance_wait(dt)
        _step(rt, ren)


def main():
    root = newgame.create_game("新游戏", tempfile.mkdtemp(), template="standard")
    script = str(root / "script.gal")
    cfg = load_config(str(root))

    rt = Runtime()
    ren = Renderer((1280, 720), str(root))
    ui = UI(config=cfg)
    ui.settings_path = os.path.join(str(root), "settings.json")
    save_api.set_saves_dir(str(root / "saves"))
    ui.set_gallery_config(load_gallery_config(str(root)))
    ui.set_script_title(_read_script_title(script))
    ui.refresh()

    try:
        # ① 标题：无横线 + 焦点项无框（cursor=0 在"开始新游戏"）
        snap(ren, ui, "01_title_p48.png")

        # ② 存档九宫格：先写 1/3/5 号存档（含缩略图），再进存档界面
        rt.load(script)
        for slot in (1, 3, 5):
            rt.save(slot)
            _post_save_enrich(slot, rt, ren, script)
        ui.refresh()
        ui._enter_slots("save", return_mode="menu")
        snap(ren, ui, "02_slots_p48.png")

        # ③ 对话框新样式：推进到幕2 旁白（加深区 + ▲ 把手 + 快捷栏 ◀▶）
        ui._enter("playing")
        advance(rt, ren, 20)
        state = rt.snapshot()
        hist = state.get("history") or []
        print("DBG_DLG hist:", len(hist), "| last:", (hist[-1].get("text") or "")[:22],
              "| char:", hist[-1].get("char") if hist else None)
        snap(ren, ui, "03_dialog_p48.png", state)

        # ④ 设置界面：语言项与全部设置项渲染检查
        ui._enter("settings")
        snap(ren, ui, "04_settings_p48.png")

        print("UI-P48-OK")
    finally:
        ren.close()


if __name__ == "__main__":
    main()
