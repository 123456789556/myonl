# -*- coding: utf-8 -*-
"""P30-C-b 验收：多层 z 序合成 + @fg 前景层 + @show z=。

解析/运行时/渲染三层各自断言；渲染层用自制纯色素材断言"谁盖住谁"的像素结果。
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

def test_parse_show_z参数与dump往返():
    ins = parse_text("@show 玛丽 微笑 z=-1\n")[0]
    assert ins["z"] == -1
    assert dump_text([ins]).strip() == "@show 玛丽 微笑 z=-1"


def test_parse_show_无z时与旧版一致():
    ins = parse_text("@show 玛丽 微笑 pos=左\n")[0]
    assert "z" not in ins
    assert dump_text([ins]).strip() == "@show 玛丽 微笑 pos=左"


@pytest.mark.parametrize("text", ["@show 玛丽 微笑 z=一\n", "@show 玛丽 微笑 z=1.5\n"])
def test_parse_show_z非法报错(text):
    with pytest.raises(GalSyntaxError):
        parse_text(text)


def test_parse_fg_缺省参数与dump往返():
    ins = parse_text("@fg 雨\n")[0]
    assert (ins["op"], ins["name"], ins["x"], ins["y"], ins["alpha"]) == ("fg", "雨", 0, 0, 1.0)
    assert dump_text([ins]).strip() == "@fg 雨"


def test_parse_fg_带参数与dump往返():
    ins = parse_text("@fg 雨 x=-20 y=30 alpha=0.5\n")[0]
    assert (ins["x"], ins["y"], ins["alpha"]) == (-20, 30, 0.5)
    assert dump_text([ins]).strip() == "@fg 雨 x=-20 y=30 alpha=0.5"


def test_parse_fg_无等于清除():
    ins = parse_text("@fg 无\n")[0]
    assert ins["name"] == "无"


@pytest.mark.parametrize("text", [
    "@fg\n",                      # 缺素材名
    "@fg 雨 alpha=1.5\n",         # alpha 越界
    "@fg 雨 x=一\n",              # x 非整数
    "@fg 雨 强=1\n",              # 未知参数
    "@fg 雨 10\n",                # 无 "=" 的裸参数
])
def test_parse_fg_非法报错(text):
    with pytest.raises(GalSyntaxError):
        parse_text(text)


# ==================== 2. runtime ====================

def test_runtime_show把z写进state并进事件(tmp_path):
    script = tmp_path / "s.gal"
    script.write_text(
        "@character 玛丽 #ffffff\n"
        "@show 玛丽 微笑 pos=中 z=3\n"
        "@show 玛丽 微笑 pos=中\n"
        "@end\n", encoding="utf-8")
    rt = Runtime()
    rt.load(str(script))
    ev = rt.step()                      # @character 不 emit，第一步就是 @show z=3
    assert ev["type"] == "show" and ev["z"] == 3
    assert rt.snapshot()["sprites"][0]["z"] == 3
    ev = rt.step()                      # 同角色再 @show，未写 z → 回缺省（不留上次的）
    assert "z" not in ev
    assert "z" not in rt.snapshot()["sprites"][0]


def test_runtime_fg进state供存档(tmp_path):
    script = tmp_path / "s.gal"
    script.write_text("@fg 雨 x=1 y=2 alpha=0.5\n@end\n", encoding="utf-8")
    rt = Runtime()
    rt.load(str(script))
    ev = rt.step()
    # 只比展示字段（事件还带 line / seq 等元信息）
    assert {k: ev[k] for k in ("type", "name", "x", "y", "alpha")} == {
        "type": "fg", "name": "雨", "x": 1, "y": 2, "alpha": 0.5}
    # P32：@fg 进 state（持久化展示层），读档复原前景
    assert rt.snapshot()["fg"] == {"name": "雨", "x": 1, "y": 2, "alpha": 0.5}


# ==================== 3. 渲染层（像素断言） ====================

def _mk_assets(root):
    img_dir = os.path.join(root, "images")
    os.makedirs(img_dir, exist_ok=True)
    for name, color in (("a_b", (255, 0, 0)), ("c_d", (0, 0, 255)), ("雨", (0, 255, 0))):
        surf = pygame.Surface((100, 100), pygame.SRCALPHA)
        surf.fill((*color, 255))
        pygame.image.save(surf, os.path.join(img_dir, f"{name}.png"))


def _state(sprites, **extra):
    state = {"bg": None, "sprites": sprites, "history": [], "pending_choice": None,
             "characters": {}, "gallery": []}
    state.update(extra)
    return state


@pytest.fixture()
def ren(tmp_path):
    _mk_assets(str(tmp_path))
    renderer = Renderer((1280, 720), str(tmp_path))
    try:
        yield renderer
    finally:
        renderer.close()


def _center_px(ren):
    """取双立绘重叠区中心（立绘区底部之上，避开底部渐隐）。"""
    return tuple(ren._screen.get_at((640, 490)))[:3]


def test_渲染层_z大的立绘画在上面(ren):
    red = {"char": "a", "expr": "b", "pos": "中", "z": 1}
    blue = {"char": "c", "expr": "d", "pos": "中", "z": 0}
    ren.render(_state([blue, red]))
    assert _center_px(ren) == (255, 0, 0)      # z=1 的红在上面
    ren.render(_state([red, blue]))
    assert _center_px(ren) == (255, 0, 0)      # 换出场顺序不影响：大小由 z 定
    ren.render(_state([{**red, "z": 0}, {**blue, "z": 1}]))
    assert _center_px(ren) == (0, 0, 255)      # 交换 z 即交换遮挡关系


def test_渲染层_无z时按出场顺序(ren):
    """旧剧本零改动：不写 z 时后出场的画在上面，与旧版一致。"""
    red = {"char": "a", "expr": "b", "pos": "中"}
    blue = {"char": "c", "expr": "d", "pos": "中"}
    ren.render(_state([red, blue]))
    assert _center_px(ren) == (0, 0, 255)
    ren.render(_state([blue, red]))
    assert _center_px(ren) == (255, 0, 0)


def test_渲染层_fg画在立绘之上(ren):
    sprites = [{"char": "a", "expr": "b", "pos": "中"}]
    ren.render(_state(sprites))
    assert _center_px(ren) == (255, 0, 0)      # 只有立绘
    ren.play_fg("雨", 590, 440)                # 100×100 绿块盖住立绘重叠区
    ren.render(_state(sprites))
    assert _center_px(ren) == (0, 255, 0)      # 前景层在立绘之上


def test_渲染层_fg的alpha与清除(ren):
    sprites = [{"char": "a", "expr": "b", "pos": "中"}]
    ren.play_fg("雨", 590, 440, 0.5)
    ren.render(_state(sprites))
    r, g, _b = _center_px(ren)
    assert 100 < r < 155 and 100 < g < 155     # 红绿各半
    ren.play_fg("无")
    ren.render(_state(sprites))
    assert _center_px(ren) == (255, 0, 0)      # 清除后回立绘


def test_渲染层_fg素材缺失不崩(ren):
    ren.play_fg("不存在的素材")
    ren.render(_state([{"char": "a", "expr": "b", "pos": "中"}]))
    assert _center_px(ren) == (255, 0, 0)      # 缺失静默跳过，不糊占位
