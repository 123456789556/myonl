# -*- coding: utf-8 -*-
"""P30-C-c 验收：@anim 立绘补间（解析 / 运行时 / 渲染三层）。

渲染层用固定时间源 + 纯色素材做像素与显示值断言。
"""
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")  # 无头模式，须在 import pygame 前生效

import pygame
import pytest

from engine.parser import GalSyntaxError, dump_text, parse_text
from engine.renderer import Renderer
from engine.runtime import Runtime

pytestmark = [pytest.mark.ui]


# ==================== 1. parser ====================

def test_parse_anim_补间与dump往返():
    ins = parse_text("@anim 玛丽 x=-100~0 1.5\n")[0]
    assert (ins["op"], ins["char"], ins["param"], ins["from"], ins["to"], ins["secs"]) == (
        "anim", "玛丽", "x", -100, 0, 1.5)
    assert ins["ease"] == "linear"
    assert dump_text([ins]).strip() == "@anim 玛丽 x=-100~0 1.5"


def test_parse_anim_直达不带起始():
    ins = parse_text("@anim 玛丽 alpha=0 0\n")[0]
    assert "from" not in ins and ins["to"] == 0 and ins["secs"] == 0
    assert dump_text([ins]).strip() == "@anim 玛丽 alpha=0 0"


def test_parse_anim_ease与dump往返():
    ins = parse_text("@anim 玛丽 scale=1~1.5 2 ease=ease_in\n")[0]
    assert ins["ease"] == "ease_in"
    assert dump_text([ins]).strip() == "@anim 玛丽 scale=1~1.5 2 ease=ease_in"


@pytest.mark.parametrize("text", [
    "@anim 玛丽\n",                        # 参数不足
    "@anim 玛丽 旋转=0 1\n",               # 不支持的参数
    "@anim 玛丽 x 1\n",                    # 缺 "="
    "@anim 玛丽 alpha=2 1\n",              # alpha 越界
    "@anim 玛丽 scale=5 1\n",              # scale 越界
    "@anim 玛丽 x=一~0 1\n",               # 数值非数字
    "@anim 玛丽 x=0 -1\n",                 # 秒数为负
    "@anim 玛丽 x=0 1 ease=弹跳\n",        # 不支持的缓动
    "@anim 玛丽 x=0 1 很快\n",             # 第四个参数不是 ease=
])
def test_parse_anim_非法报错(text):
    with pytest.raises(GalSyntaxError):
        parse_text(text)


# ==================== 2. runtime ====================

def test_runtime_anim事件不进state(tmp_path):
    script = tmp_path / "s.gal"
    script.write_text("@anim 玛丽 y=-40~0 1.2 ease=ease_out\n@end\n", encoding="utf-8")
    rt = Runtime()
    rt.load(str(script))
    ev = rt.step()
    assert {k: ev[k] for k in ("type", "char", "param", "from", "to", "secs", "ease")} == {
        "type": "anim", "char": "玛丽", "param": "y", "from": -40, "to": 0,
        "secs": 1.2, "ease": "ease_out"}
    assert "anim" not in rt.snapshot()   # 纯展示层，不进 state / 存档


# ==================== 3. 渲染层 ====================

def _mk_assets(root):
    img_dir = os.path.join(root, "images")
    os.makedirs(img_dir, exist_ok=True)
    surf = pygame.Surface((100, 100), pygame.SRCALPHA)
    surf.fill((255, 0, 0, 255))
    pygame.image.save(surf, os.path.join(img_dir, "玛丽_微笑.png"))


@pytest.fixture()
def ren(tmp_path, monkeypatch):
    _mk_assets(str(tmp_path))
    box = [0]
    monkeypatch.setattr(Renderer, "_now_ms", lambda self: box[0])
    renderer = Renderer((1280, 720), str(tmp_path))
    renderer.box = box
    try:
        yield renderer
    finally:
        renderer.close()


SPRITE = {"char": "玛丽", "expr": "微笑", "pos": "中"}
STATE = {"bg": None, "sprites": [SPRITE], "history": [], "pending_choice": None,
         "characters": {}, "gallery": []}


def _px(ren, x, y):
    return tuple(ren._screen.get_at((x, y)))[:3]


def test_渲染层_x补间按时间移动(ren):
    ren.render(STATE)
    assert _px(ren, 640, 490) == (255, 0, 0)      # 基准位置
    ren.play_anim("玛丽", "x", -100, 0, 1.0)
    ren.box[0] = 500
    ren.render(STATE)
    assert _px(ren, 590, 490) == (255, 0, 0)      # 左移 50px 后仍在
    assert _px(ren, 685, 490) == (0, 0, 0)        # 右侧已让出
    ren.box[0] = 1000
    ren.render(STATE)
    assert ren._sprite_anim["玛丽"]["x"] == 0      # 播完回到目标值，轨被收掉
    assert not ren.timeline.has("anim:玛丽:x")


def test_渲染层_alpha直达当帧生效(ren):
    ren.render(STATE)
    ren.play_anim("玛丽", "alpha", None, 0, 0)    # 秒数 0 = 直达
    ren.render(STATE)
    assert _px(ren, 640, 490) == (0, 0, 0)        # 当帧就看不见了


def test_渲染层_scale补间放大(ren):
    ren.render(STATE)
    assert _px(ren, 640, 400) == (0, 0, 0)        # 原尺寸只有 100 高，够不到 y=400
    ren.play_anim("玛丽", "scale", 1, 2, 1.0)
    ren.box[0] = 500
    ren.render(STATE)
    assert _px(ren, 640, 400) == (255, 0, 0)      # 放大到 1.5 倍后覆盖 y=400


def test_渲染层_角色退场清掉补间偏移(ren):
    ren.play_anim("玛丽", "x", -100, -100, 1.0)
    ren.render(STATE)
    assert "玛丽" in ren._sprite_anim
    ren.render({**STATE, "sprites": []})          # @hide 掉最后一个角色
    assert "玛丽" not in ren._sprite_anim
    assert not ren.timeline.has("anim:玛丽:x")


def test_渲染层_无anim时画面不受影响(ren):
    """旧剧本零改动：不写 @anim 就不该有任何显示值。"""
    ren.render(STATE)
    assert ren._sprite_anim == {}
    assert _px(ren, 640, 490) == (255, 0, 0)
