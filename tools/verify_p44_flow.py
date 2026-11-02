# -*- coding: utf-8 -*-
"""P44 交互链验证：用引擎真渲染空包 5 个菜单按钮的每一步界面，存 PNG。

链条：标题 → 开始新游戏(playing) / 读档(slots) / 设置(settings) / 退出(quit 动作) / 继续(无存档灰置)。
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
from engine.demo import _read_script_title
from engine.renderer import Renderer
from engine.runtime import Runtime
from engine.ui import UI

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "flow")
os.makedirs(OUT, exist_ok=True)


def snap(ren, ui, rt, name, state=None, warmup=0):
    """渲染当前帧并存 PNG。warmup>0：先预渲染 N 帧（跳过背景淡入/打字机起始黑帧）。"""
    view = ui.view()
    st = state if state is not None else (rt.snapshot() if rt is not None else {})
    for _ in range(warmup):
        ren.render(st, view)
    ren.render(st, view)
    path = os.path.join(OUT, name)
    pygame.image.save(ren._screen, path)
    print("SAVED:", name, "| mode:", view.get("mode"))
    return path


def main():
    root = newgame.create_game("测试空包", tempfile.mkdtemp(), template="standard")
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
        # ① 标题（初始，光标在"开始新游戏"）
        snap(ren, ui, None, "01_title.png")

        # ② 开始新游戏 → playing（第一幕，需剧本已加载并推进到有画面）
        rt.load(script)
        for _ in range(8):  # 推进到第二幕：站台近景 + 女学生立绘 + 打招呼台词
            rt.step()
        ui.handle("confirm")
        state = rt.snapshot()
        print("DBG_BG:", state.get("bg"), "| DBG_HIST:", len(state.get("history") or []))
        snap(ren, ui, rt, "02_start_playing.png", state, warmup=30)

        # ③ 回标题 → 读档 → slots load
        rt2 = Runtime()  # 重新加载，方便独立分支
        rt2.load(script)
        ui2 = UI(config=cfg)
        ui2.settings_path = ui.settings_path
        save_api.set_saves_dir(str(root / "saves"))
        ui2.set_gallery_config(load_gallery_config(str(root)))
        ui2.set_script_title(_read_script_title(script))
        ui2.refresh()
        ui2.handle("down")  # 继续
        ui2.handle("down")  # 读档
        ui2.handle("confirm")
        snap(ren, ui2, rt2, "03_load_slots.png")

        # ④ 设置
        ui3 = UI(config=cfg)
        ui3.settings_path = ui.settings_path
        ui3.set_gallery_config(load_gallery_config(str(root)))
        ui3.set_script_title(_read_script_title(script))
        ui3.refresh()
        for _ in range(3):  # 0 开始 → 1 继续 → 2 读档 → 3 设置
            ui3.handle("down")
        ui3.handle("confirm")
        snap(ren, ui3, None, "04_settings.png")

        # ⑤ 继续：无存档灰置验证（enabled=False）
        ui4 = UI(config=cfg)
        ui4.settings_path = ui.settings_path
        ui4.refresh()
        items = ui4.view()["items"]
        print("CONTINUE_ENABLED:", items[1]["enabled"], "(无存档应为 False)")

        # ⑥ 退出：动作语义验证（标题 Esc / 退出菜单 → quit）
        ui5 = UI(config=cfg)
        ui5.settings_path = ui.settings_path
        ui5.refresh()
        for _ in range(4):
            ui5.handle("down")
        action = ui5.handle("confirm")
        print("QUIT_ACTION:", action)
        assert action == {"action": "quit"}
        print("FLOW-OK")
    finally:
        ren.close()


if __name__ == "__main__":
    main()
