# -*- coding: utf-8 -*-
"""P13 真机截图脚本（无头 dummy 模式生成，人工核对用）。

生成 screenshots/p13_*.png：
  p13_gallery_grid.png     画廊 CG 网格
  p13_cg_fullscreen.png    CG 大图展示
  p13_camera_zoom_out.png  镜头推拉前
  p13_camera_zoom_in.png   镜头推拉到一半
  p13_transition_dissolve.png  转场溶解过程
  p13_menu_entry.png       菜单画廊入口
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

ASSETS = ROOT / "示例游戏"
OUT = ROOT / "screenshots"
OUT.mkdir(exist_ok=True)


def make_cg_image():
    """造一张 CG 图（示例游戏没有 cg_*，现场生成到示例游戏 images/）。"""
    img = pygame.Surface((1280, 720))
    for y in range(720):
        c = (int(20 + 60 * y / 720), int(30 + 40 * y / 720), int(80 + 100 * y / 720))
        pygame.draw.line(img, c, (0, y), (1280, y))
    pygame.draw.circle(img, (255, 220, 120), (1000, 150), 60)  # 月亮
    pygame.image.save(img, str(ASSETS / "images" / "cg_星空告白.png"))


def base_state():
    return {
        "bg": "classroom", "music": None, "video": None,
        "sprites": [{"char": "林晚", "expr": "smile", "anim": "呼吸"}],
        "vars": {}, "characters": {"林晚": {"color": "#aaccff"}},
        "history": [{"char": "林晚", "text": "今晚的星空，真美啊。"}],
        "pending_choice": None, "finished": False, "gallery": ["星空告白"],
    }


def shot(ren, name):
    path = str(OUT / name)
    ren.screenshot(path)
    print("saved", path)


def main():
    make_cg_image()
    ren = Renderer((1280, 720), str(ASSETS))
    ui = UI()
    try:
        state = base_state()

        # 1. 菜单画廊入口
        ui.mode = "playing"
        ui.handle("back")  # 菜单
        ui.handle("down"); ui.handle("down")  # 光标停在“画廊”
        ui.set_gallery(["星空告白"], ["林晚_smile"])
        ren.render(state, ui.view())
        shot(ren, "p13_menu_entry.png")

        # 2. 画廊网格
        ui.handle("confirm")  # 进画廊
        ui.set_gallery(["星空告白"], ["林晚_smile"])
        ren.render(state, ui.view())
        shot(ren, "p13_gallery_grid.png")

        # 3. CG 大图（画廊详情）
        ui.handle("confirm")  # 选中第一张
        ren.render(state, ui.view())
        shot(ren, "p13_cg_detail.png")

        # 4. 游戏中 CG 全屏展示
        ui.mode = "playing"
        ren.play_cg("星空告白")
        ren.render(state, ui.view())
        shot(ren, "p13_cg_fullscreen.png")
        ren._cg_showing = None

        # 5. 镜头推拉两帧
        ui.handle("back")  # 回 playing（从 menu？不，playing 模式直接画）
        ui._mode = "playing"
        ren.render(state, None)
        shot(ren, "p13_camera_zoom_before.png")
        ren.play_camera("zoom", [1.0, 1.5])
        # 快进到一半
        ren._cam_t0 = ren._now_ms() - 500  # 0.5s / 1.0s = t 0.5
        ren.render(state, None)
        shot(ren, "p13_camera_zoom_mid.png")
        ren.play_camera("reset", [0.01])
        ren._cam_t0 = ren._now_ms() - 100
        ren.render(state, None)

        # 6. 转场溶解过程
        ren.play_transition("dissolve", [0.8])
        state2 = dict(state)
        state2["bg"] = "classroom_night"
        ren.render(state2)  # 触发转场（_trans_old 记录旧画面）
        ren._trans_t0 = ren._now_ms() - 400  # 播到一半
        ren.render(state2)
        shot(ren, "p13_transition_dissolve.png")
    finally:
        ren.close()


if __name__ == "__main__":
    main()
