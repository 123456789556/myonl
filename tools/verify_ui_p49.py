# -*- coding: utf-8 -*-
"""P49 UI 批验证：设置三页分页 + 音量滑条 + 幕布矩形薄纱。

帧输出 tools/ui_p49/：
  01_settings_basic.png   基础页（仅打字速度）
  02_settings_audio.png   音频页（音乐/音效音量滑条）
  03_settings_voice.png   语音页（配音/自动推进/语言）
  04_curtain_hover.png    对话框正常态：顶部矩形薄纱 hover 显现（无三角）
  05_curtain_hidden.png   幕布隐藏态：hover 显现薄纱（截图不可见态）
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
from engine.demo import _read_script_title, _step
from engine.renderer import Renderer
from engine.runtime import Runtime
from engine.ui import UI

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui_p49")
os.makedirs(OUT, exist_ok=True)


def snap(ren, ui, name, state=None, mouse=(0, 0)):
    view = ui.view()
    st = state if state is not None else {}
    # dummy 驱动下 pygame.mouse.get_pos() 恒为 (0,0)；渲染层每帧从它取 hover 位置，
    # 这里 patch 成测试注入点来验证"鼠标到达捕获区"分支（不影响产品代码）
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


def main():
    root = newgame.create_game("新游戏", tempfile.mkdtemp(), template="standard")
    script = str(root / "script.gal")
    cfg = load_config(str(root))

    rt = Runtime()
    ren = Renderer((1280, 720), str(root))
    ui = UI(config=cfg)
    ui.settings_path = os.path.join(str(root), "settings.json")
    save_api.set_saves_dir(os.path.join(str(root), "saves"))
    ui.set_gallery_config(load_gallery_config(str(root)))
    ui.set_script_title(_read_script_title(script))
    ui.refresh()

    try:
        # ① 设置-基础页（tab=0：仅打字速度）
        ui._enter("settings")
        ui._settings_tab = 0
        ui._cursor = 0
        snap(ren, ui, "01_settings_basic.png")

        # ② 设置-音频页（tab=1：音乐/音效滑条）
        ui._settings_tab = 1
        ui._cursor = 1
        snap(ren, ui, "02_settings_audio.png")

        # ③ 设置-语音页（tab=2：配音/自动推进/语言）
        ui._settings_tab = 2
        ui._cursor = 3
        snap(ren, ui, "03_settings_voice.png")

        # ④ 对话框 + 幕布薄纱（正常态 hover 显现）：播放到有字幕的旁白
        rt.load(script)
        ui._enter("playing")
        advance(rt, ren, 20)
        state = rt.snapshot()
        hist = state.get("history") or []
        print("DBG hist:", len(hist), "| last:", (hist[-1].get("text") or "")[:22])
        # 薄纱捕获区：对话框顶上方全宽（模板 dialogue 高 200 → 顶 y=520，
        # 捕获区 y=494..520）。鼠标放区内 → hover 显现
        snap(ren, ui, "04_curtain_hover.png", state, mouse=(640, 507))

        # ⑤ 幕布隐藏态：整块拉下后，hover 顶部薄纱显现（截图不可见态）
        ren._ui_hidden = True
        snap(ren, ui, "05_curtain_hidden.png", state, mouse=(640, 507))

        print("UI-P49-OK")
    finally:
        ren.close()


if __name__ == "__main__":
    main()
