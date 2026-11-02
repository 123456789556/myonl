# -*- coding: utf-8 -*-
"""P50 UI 批验证：B+D 结合——半透明圆角文字框 + 快捷栏默认隐藏/hover 显现 + 细纱句号。

帧输出 tools/ui_p50/（真实项目 games\\新游戏 配置）：
  01_dialog_normal.png   正常态（无鼠标）：圆角半透明文字框；快捷栏不可见
  02_quickbar_hover.png  鼠标移到快捷栏带区：小文字按钮显现
  03_curtain_hover.png   正常态：顶部细纱线 + 中央句号（hover 显现）
  04_hidden.png          隐藏态：hover 顶缘细纱（截图不可见态）
"""
import os
import sys

os.environ["SDL_VIDEODRIVER"] = "dummy"
ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "games", "新游戏")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame

from engine import save as save_api
from engine.config import load as load_config
from engine.data import load_gallery_config
from engine.demo import _read_script_title, _step
from engine.renderer import Renderer
from engine.runtime import Runtime
from engine.ui import UI

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui_p50")
os.makedirs(OUT, exist_ok=True)


def snap(ren, ui, name, state=None, mouse=(0, 0)):
    view = ui.view()
    st = state if state is not None else {}
    real_get_pos = pygame.mouse.get_pos
    pygame.mouse.get_pos = lambda: mouse
    try:
        for _ in range(30):
            ren.render(st, view)
    finally:
        pygame.mouse.get_pos = real_get_pos
    path = os.path.join(OUT, name)
    pygame.image.save(ren._screen, path)
    print("SAVED:", name, "| mode:", view.get("mode"))
    return path


def advance(rt, ren, steps, dt=0.15):
    for _ in range(steps):
        rt.advance_wait(dt)
        _step(rt, ren)


def probe(ren, points, label):
    vals = []
    for p in points:
        vals.append((p, ren._screen.get_at(p)[:3]))
    line = f"PROBE {label} -> {vals}"
    print(line)
    with open(os.path.join(OUT, "probe.txt"), "a", encoding="utf-8") as f:
        f.write(line + "\n")


def main():
    script = os.path.join(ROOT, "script.gal")
    cfg = load_config(ROOT)

    rt = Runtime()
    ren = Renderer((1280, 720), ROOT)
    ui = UI(config=cfg)
    ui.settings_path = os.path.join(ROOT, "settings.json")
    save_api.set_saves_dir(os.path.join(ROOT, "saves"))
    ui.set_gallery_config(load_gallery_config(ROOT))
    ui.set_script_title(_read_script_title(script))
    ui.refresh()

    try:
        rt.load(script)
        ui._enter("playing")
        advance(rt, ren, 20)
        state = rt.snapshot()
        hist = state.get("history") or []
        print("DBG hist:", len(hist), "| last:", (hist[-1].get("text") or "")[:22])

        # ① 正常态（无鼠标）：文字框圆角半透明；快捷栏隐藏
        snap(ren, ui, "01_dialog_normal.png", state, mouse=(0, 0))
        # 文字框区 y≈700（半透明底，非纯黑）& 快捷栏区 y=690（应为背景无按钮）
        probe(ren, [(640, 700), (640, 690), (1100, 690)], "normal")

        # ② 鼠标移到快捷栏带区（bottom: y0=720-26-10=684；带区 670..714）
        snap(ren, ui, "02_quickbar_hover.png", state, mouse=(1150, 690))
        probe(ren, [(1150, 690)], "quickbar-hover")

        # ③ 正常态：顶部「矩形顶边」细线+中央圆点 hover（文字框顶 y=544；线 541..544）
        snap(ren, ui, "03_curtain_hover.png", state, mouse=(640, 530))
        probe(ren, [(600, 542), (640, 542)], "curtain-hover")

        # ④ 隐藏态：hover 顶缘细线（截图不可见态）
        ren._ui_hidden = True
        snap(ren, ui, "04_hidden.png", state, mouse=(640, 530))
        probe(ren, [(600, 542), (640, 542)], "hidden")

        print("UI-P50-OK")
    finally:
        ren.close()


if __name__ == "__main__":
    main()
