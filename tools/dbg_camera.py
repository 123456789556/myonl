# -*- coding: utf-8 -*-
import os, sys, tempfile
os.environ["SDL_VIDEODRIVER"] = "dummy"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pygame
from engine import newgame
from engine.demo import _step
from engine.renderer import Renderer
from engine.runtime import Runtime

root = newgame.create_game("dbg", tempfile.mkdtemp(), template="standard")
ren = Renderer((1280, 720), str(root))
rt = Runtime()
rt.load(str(root / "script.gal"))
for i in range(24):
    rt.advance_wait(0.15)
    ev = _step(rt, ren)
    if ev.get("type") in ("scene", "camera", "wait", "sfx"):
        print(i, ev.get("type"), ev.get("kind"), ev.get("args"))
print("names:", ren.timeline.names())
ren.close()
