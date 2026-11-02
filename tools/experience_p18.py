# -*- coding: utf-8 -*-
"""P18 开发者体验脚本：dummy 驱动《示例故事》，关键帧截图。

用法：py tools/experience_p18.py
输出：screenshots/p18_experience/ 下若干 PNG（序章/选项/结局终幕/CG 尽力帧）。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.runtime import Runtime  # noqa: E402
from engine.renderer import Renderer  # noqa: E402
from engine.ui import UI  # noqa: E402


def my_step(rt: Runtime, ren: Renderer) -> None:
    """推进一条指令；sfx/cg/camera/transition 事件分发到 renderer（等价 demo._step）。"""
    ev = rt.step()
    kind = ev.get("type")
    if kind == "sfx":
        ren.play_sfx(ev.get("sound"))
    elif kind == "cg":
        ren.play_cg(ev.get("name"))
    elif kind == "camera":
        ren.play_camera(ev.get("kind"), ev.get("args"))
    elif kind == "transition":
        ren.play_transition(ev.get("kind"), ev.get("args"))

SCRIPT = ROOT / "games" / "示例故事" / "script.gal"
ASSETS = ROOT / "games" / "示例故事"
OUT = ROOT / "screenshots" / "p18_experience"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    rt = Runtime()
    rt.load(str(SCRIPT))
    ren = Renderer((1280, 720), str(ASSETS))
    ui = UI()
    ui.settings_path = str(ASSETS / "settings.json")
    ui.refresh()
    ui.mode = "playing"

    def snap(shot_name: str):
        st = rt.snapshot()
        ui.set_history(st.get("history"))
        ui.set_gallery(st.get("gallery") or [], rt.seen_sprites())
        view = ui.view()
        # 等待转场/打字机动画走完：真实时间推进后重渲染，避免截到中间帧
        import time
        for _ in range(6):
            ren.render(st, view)
            time.sleep(0.2)
        ren.reveal_all()
        ren.render(st, view)
        p = OUT / f"{shot_name}.png"
        ren.screenshot(str(p))
        print(f"[帧] {shot_name} —— history={len(st.get('history') or [])}")

    snap("00_标题画面")  # 空 state：标题菜单
    # 进入游戏（等价点「开始游戏」）
    ui.mode = "playing"
    snap("01_序章第一句")

    guard = 0
    cg_done = False
    while True:
        st = rt.snapshot()
        if st.get("pending_choice"):
            snap("02_选项界面")
            rt.choose(1)  # 结局A：抱歉，今天不行
            continue
        if st.get("finished"):
            snap("04_结局A_终幕")
            break
        hist = st.get("history") or []
        last = hist[-1] if hist else {}
        text = str(last.get("text", "")) if isinstance(last, dict) else ""
        if "明天见" in text and not cg_done:
            snap("03_结局A_关键台词")
            my_step(rt, ren)  # @voice voice_01
            my_step(rt, ren)  # @cg cg_01 → renderer 进入 CG 展示
            snap("07_结局A_CG全屏")
            cg_done = True
            continue
        if "结局 · 平常的一天" in text:
            snap("04_结局A_终幕")
        my_step(rt, ren)
        guard += 1
        if guard > 500:
            print("guard 超限，异常终止")
            return 1

    # 结局B：重载，选第一个
    rt2 = Runtime()
    rt2.load(str(SCRIPT))
    ren2 = Renderer((1280, 720), str(ASSETS))
    ui2 = UI()
    ui2.settings_path = str(ASSETS / "settings.json")
    ui2.refresh()
    ui2.mode = "playing"

    def snap2(name):
        st = rt2.snapshot()
        ui2.set_history(st.get("history"))
        ui2.set_gallery(st.get("gallery") or [], rt2.seen_sprites())
        v = ui2.view()
        import time
        for _ in range(6):
            ren2.render(st, v)
            time.sleep(0.2)
        ren2.reveal_all()
        ren2.render(st, v)
        ren2.screenshot(str(OUT / f"{name}.png"))
        print(f"[帧] {name}")

    guard = 0
    while True:
        st = rt2.snapshot()
        if st.get("pending_choice"):
            rt2.choose(0)  # 结局B：好，一起去
            continue
        if st.get("finished"):
            snap2("05_结局B_终幕")
            break
        hist = st.get("history") or []
        last = hist[-1] if hist else {}
        text = str(last.get("text", "")) if isinstance(last, dict) else ""
        if "走吧" in text:
            snap2("06_结局B_关键台词")
        if "结局 · 一起回家" in text:
            snap2("05_结局B_终幕")
        my_step(rt2, ren2)
        guard += 1
        if guard > 500:
            print("guard 超限")
            return 1

    print("体验帧已生成：", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
