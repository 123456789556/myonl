# -*- coding: utf-8 -*-
"""P28 视觉验收：画廊锁格网格 / 幻灯片详情 / 存档列表底部留白（无头截图）。

用法（项目根目录）：py tools/p28_verify_ui.py
输出：screenshots/p28_*.png
"""
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pygame  # noqa: E402

from engine import data, save  # noqa: E402
from engine.renderer import Renderer  # noqa: E402
from engine.ui import UI  # noqa: E402

GAME = ROOT / "games" / "月光漫步"
OUT = ROOT / "screenshots"


def _shot(ren, ui, name, now_ms=0):
    ren.render({}, ui.view(now_ms=now_ms))
    OUT.mkdir(exist_ok=True)
    pygame.image.save(ren._screen, str(OUT / name))
    print(f"[ok] {OUT / name}")


def main():
    pygame.init()
    ren = Renderer((1280, 720), str(GAME))
    try:
        # E1：固定 8 格，前 3 格已解锁，光标停在未解锁的 cg_end4
        ui = UI()
        cells = data.load_gallery_config(str(GAME))
        ui.set_gallery_config(cells)
        ui.set_gallery(["cg_dark", "cg_dawn", "cg_end3"], [])
        ui.mode = "gallery"
        ui._cursor = 5  # cg_end4 未解锁
        _shot(ren, ui, "p28_gallery_locked.png")

        # E3：幻灯片详情（cg_end4 第 1/4 张）
        ui._open_detail("cg_end4")
        _shot(ren, ui, "p28_gallery_detail.png")
        # 第 2 张（bg_hospital2）
        ui._open_detail("cg_end4")
        _shot(ren, ui, "p28_gallery_detail_2.png", now_ms=5000 + 1)

        # E4：存档列表 11 张卡片，光标停在第 6 张（存档 5）
        tmp = ROOT / "screenshots" / "_tmp_saves"
        tmp.mkdir(parents=True, exist_ok=True)
        thumb = str(GAME / "images" / "bg_dawn1.png")
        for key in ["quick"] + [str(n) for n in range(1, 11)]:
            (tmp / f"slot_{key}.json").write_text(json.dumps({
                "state": {"vars": {}},
                "saved_at": "2026-10-27 20:00",
                "label": f"存档 {key} · 黄昏的海边",
                "chapter_name": "第二章 黄昏",
                "last_text": "明明约好了……",
                "thumbnail_path": thumb,
            }, ensure_ascii=False), encoding="utf-8")
        old_saves = save.SAVES_DIR
        save.SAVES_DIR = str(tmp)
        try:
            ui2 = UI()
            ui2.mode = "playing"    # UI 默认在标题，先进游戏
            ui2.handle("back")      # 游戏中 → 菜单
            ui2.handle("confirm")   # 菜单：存档
            ui2._cursor = 6         # 第 6 张卡片
            _shot(ren, ui2, "p28_slots.png")
        finally:
            save.SAVES_DIR = old_saves
            for p in tmp.glob("slot_*.json"):
                p.unlink()
            tmp.rmdir()
    finally:
        ren.close()
        pygame.quit()


if __name__ == "__main__":
    main()
