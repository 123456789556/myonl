# -*- coding: utf-8 -*-
"""无头驱动开场.gal，关键帧截图验证 Pan/presents/文字节奏。"""
import os, sys
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, r"D:\娱乐工作区\自研项目\MYONL引擎")

from engine.runtime import Runtime
from engine.renderer import Renderer

ROOT = r"D:\娱乐工作区\自研项目\MYONL引擎\games\月光漫步"
OUT = r"D:\娱乐工作区\自研项目\MYONL引擎\screenshots"
os.makedirs(OUT, exist_ok=True)

rt = Runtime()
ren = Renderer((1280, 720), ROOT)
ren.set_splash(True)
rt.load(os.path.join(ROOT, "开场.gal"))
view = {"mode": "playing"}
shot_at = {0: "p28_开场_起始", 12: "p28_开场_pan中", 24: "p28_开场_presents", 38: "p28_开场_结尾"}

steps = 0
while steps < 120:
    state = rt.snapshot()
    ren.render(state, view)
    if steps in shot_at:
        p = os.path.join(OUT, shot_at[steps] + ".png")
        ren.save_thumbnail(p)
        print("截图:", shot_at[steps], p)
    if state.get("finished"):
        print("开场播完，总步数:", steps)
        break
    ev = rt.step()
    if not ev:
        break
    steps += 1
else:
    print("到 120 步未结束（可能卡住）")
ren.close()
print("完成")
