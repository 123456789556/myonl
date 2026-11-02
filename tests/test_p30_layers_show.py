# -*- coding: utf-8 -*-
"""P30-C-d 验收：简化分层立绘（`@show 角色 表情 部位:素材 ...`）。

解析 / 运行时 / 渲染三层断言；渲染层用三张纯色薄片验证叠放顺序与兜底回落。
"""
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")  # 无头模式，须在 import pygame 前生效

import pygame
import pytest

from engine.parser import GalSyntaxError, dump_text, parse_text
from engine.renderer import LAYER_ORDER, Renderer
from engine.runtime import Runtime

pytestmark = [pytest.mark.ui]


# ==================== 1. parser ====================

def test_parse_show分层与dump往返():
    ins = parse_text("@show 玛丽 微笑 皮肤:常服 表情:惊讶\n")[0]
    assert ins["layers"] == {"皮肤": "常服", "表情": "惊讶"}
    dumped = dump_text([ins]).strip()
    assert dumped == "@show 玛丽 微笑 皮肤:常服 表情:惊讶"
    assert parse_text(dumped + "\n")[0]["layers"] == {"皮肤": "常服", "表情": "惊讶"}


def test_parse_show分层可与布局参数混用():
    ins = parse_text("@show 玛丽 微笑 pos=左 z=2 身体:泳装\n")[0]
    assert (ins["pos"], ins["z"], ins["layers"]) == ("左", 2, {"身体": "泳装"})


@pytest.mark.parametrize("text", [
    "@show 玛丽 微笑 皮肤:\n",        # 缺素材名
    "@show 玛丽 微笑 :常服\n",        # 缺部位名
    "@show 玛丽 微笑 皮肤:常 服\n",   # 素材名里带空格（拆成两个参数）
])
def test_parse_show分层非法报错(text):
    with pytest.raises(GalSyntaxError):
        parse_text(text)


# ==================== 2. runtime ====================

def test_runtime_layers进state与事件(tmp_path):
    script = tmp_path / "s.gal"
    script.write_text("@show 玛丽 微笑 皮肤:常服\n@end\n", encoding="utf-8")
    rt = Runtime()
    rt.load(str(script))
    ev = rt.step()
    assert ev["layers"] == {"皮肤": "常服"}
    assert rt.snapshot()["sprites"][0]["layers"] == {"皮肤": "常服"}


def test_runtime_再show不写layers则回整张(tmp_path):
    script = tmp_path / "s.gal"
    script.write_text("@show 玛丽 微笑 皮肤:常服\n@show 玛丽 微笑\n@end\n", encoding="utf-8")
    rt = Runtime()
    rt.load(str(script))
    rt.step()
    rt.step()
    assert "layers" not in rt.snapshot()["sprites"][0]


# ==================== 3. 渲染层（像素断言） ====================

def _mk_layers(root):
    """三张 100×100 纯色薄片：身体=红、皮肤=绿、表情=蓝。"""
    layer_dir = os.path.join(root, "images", "layers", "玛丽")
    os.makedirs(layer_dir, exist_ok=True)
    for name, color in (("身体_默认", (255, 0, 0)), ("皮肤_常服", (0, 255, 0)),
                        ("表情_默认", (60, 60, 60)), ("表情_惊讶", (0, 0, 255))):
        surf = pygame.Surface((100, 100), pygame.SRCALPHA)
        surf.fill((*color, 255))
        pygame.image.save(surf, os.path.join(layer_dir, f"{name}.png"))


def _state(layers):
    return {"bg": None, "history": [], "pending_choice": None, "characters": {}, "gallery": [],
            "sprites": [{"char": "玛丽", "expr": "微笑", "pos": "中", "layers": layers}]}


def _px(ren):
    return tuple(ren._screen.get_at((640, 490)))[:3]


@pytest.fixture()
def ren(tmp_path):
    _mk_layers(str(tmp_path))
    renderer = Renderer((1280, 720), str(tmp_path))
    try:
        yield renderer
    finally:
        renderer.close()


def test_渲染层_叠放顺序身体皮肤表情(ren):
    ren.render(_state({"身体": "默认", "皮肤": "常服", "表情": "惊讶"}))
    assert _px(ren) == (0, 0, 255)            # 表情在最上
    ren.render(_state({"身体": "默认", "皮肤": "常服"}))
    assert _px(ren) == (0, 255, 0)            # 无表情层 → 皮肤在最上


def test_渲染层_缺素材回退默认(ren):
    ren.render(_state({"身体": "默认", "表情": "不存在"}))
    assert _px(ren) == (60, 60, 60)           # 表情_不存在 → 表情_默认


def test_渲染层_一层都拼不出回退整张(ren):
    """全缺时不能糊黑：回退整张 角色ID_表情.png（此例不存在 → 占位框，但不是纯黑）。"""
    empty = os.path.join(str(ren.assets_root), "images")
    assert os.path.isdir(empty)
    ren.render(_state({"身体": "不存在", "皮肤": "也不存在"}))
    assert _px(ren) != (0, 0, 0)


def test_渲染层_合成结果被缓存(ren):
    ren.render(_state({"身体": "默认", "皮肤": "常服"}))
    first = ren._layer_composite("玛丽", {"身体": "默认", "皮肤": "常服"})
    second = ren._layer_composite("玛丽", {"身体": "默认", "皮肤": "常服"})
    assert first is second                     # 同一组合不重复拼图
    assert len(ren._layer_cache) == 1


def test_渲染层_固定顺序常量(ren):
    assert LAYER_ORDER == ("身体", "皮肤", "表情")   # 身体在下、表情在上
