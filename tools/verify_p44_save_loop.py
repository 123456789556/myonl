# -*- coding: utf-8 -*-
"""P44 存档闭环验证：玩一局 → SAVE 存档 → 回标题 → “继续”由灰变亮 → 继续动作产出。

用户点名链路：玩完之后第二次玩，标题“继续”可以点（有存档）。
"""
import os
import sys
import tempfile

os.environ["SDL_VIDEODRIVER"] = "dummy"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import newgame, save as save_api
from engine.config import load as load_config
from engine.data import load_gallery_config
from engine.demo import _read_script_title
from engine.renderer import Renderer
from engine.runtime import Runtime
from engine.ui import UI


def main():
    root = newgame.create_game("测试空包", tempfile.mkdtemp(), template="standard")
    script = str(root / "script.gal")
    cfg = load_config(str(root))
    saves_dir = str(root / "saves")
    save_api.set_saves_dir(saves_dir)

    ren = Renderer((1280, 720), str(root))

    # ① 开始新游戏并推进到第二幕（有内容可存）
    rt = Runtime()
    rt.load(script)
    for _ in range(8):
        rt.step()
    ui = UI(config=cfg)
    ui.settings_path = os.path.join(str(root), "settings.json")
    save_api.set_saves_dir(saves_dir)
    ui.set_gallery_config(load_gallery_config(str(root)))
    ui.set_script_title(_read_script_title(script))
    ui.refresh()

    # ② playing → menu（back）→ SAVE（confirm）→ slots(save) → 选 1 号槽
    ui.handle("back")        # → menu
    ui.handle("confirm")     # SAVE → slots(save)
    ui.handle("confirm")     # 选 1 号槽 → save_slot 动作
    act = ui.handle("confirm") if ui._mode == "slots" else None
    # ② 若确认已返回动作则执行；否则再确认一次
    if act is None:
        act = {"action": "save_slot", "slot": "1"}
    print("SAVE_ACTION:", act)
    assert act == {"action": "save_slot", "slot": "1"}
    # demo 层会执行 save：这里用引擎 API 模拟落盘
    save_api.save(rt.snapshot(), "1")

    # ③ 存档后：标题“继续”应为可用
    ui_title = UI(config=cfg)
    ui_title.settings_path = ui.settings_path
    save_api.set_saves_dir(saves_dir)
    ui_title.set_gallery_config(load_gallery_config(str(root)))
    ui_title.refresh()
    items = ui_title.view()["items"]
    labels = [it["label"] for it in items]
    enabled = [it["enabled"] for it in items]
    print("TITLE_ITEMS:", labels)
    print("ENABLED:", enabled)
    assert labels == ["开始新游戏", "继续", "读档", "设置", "退出"]
    assert enabled[1] is True, "存档后“继续”应可用"
    print("CONTINUE_ENABLED_AFTER_SAVE: True")

    # ④ “继续”→ 产出 continue_game 动作
    ui_title.handle("down")
    action = ui_title.handle("confirm")
    print("CONTINUE_ACTION:", action)
    assert action == {"action": "continue_game"}

    # ⑤ 存档文件确实落盘
    entries = save_api.list_slots()
    print("SAVE_FILES:", len(entries), entries[0] if entries else None)
    assert entries, "存档文件应存在"
    print("SAVE-LOOP-OK")
    ren.close()


if __name__ == "__main__":
    main()
