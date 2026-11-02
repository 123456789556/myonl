"""场景视图 B：@show 位置参数（pos / x / y）与渲染差异的单元测试。"""
from __future__ import annotations

import os

import pytest

from engine.parser import GalSyntaxError, parse_text
from engine.runtime import Runtime

pytestmark = [pytest.mark.unit]


def test_show解析_pos与xy():
    ins = parse_text("@show 林晚 微笑 pos=左 x=120 y=-40\n@ 你好\n")[0]
    assert ins["op"] == "show"
    assert ins["pos"] == "左"
    assert ins["x"] == 120
    assert ins["y"] == -40


def test_show解析_xy越界或不合法():
    with pytest.raises(GalSyntaxError):
        parse_text("@show 林晚 微笑 x=abc\n")
    with pytest.raises(GalSyntaxError):
        parse_text("@show 林晚 微笑 y=99999\n")


def test_runtime_sprites携带位置并在下次show时清掉():
    ins = parse_text("@show 林晚 微笑 pos=右 x=30 y=10\n")[0]
    st = {"sprites": []}
    Runtime._show(st, ins)
    sp = st["sprites"][0]
    assert (sp["pos"], sp["x"], sp["y"]) == ("右", 30, 10)
    Runtime._show(st, {"char": "林晚", "expr": "微笑", "anim": "呼吸"})
    sp = st["sprites"][0]
    assert "pos" not in sp and "x" not in sp and "y" not in sp   # 本次没写→回缺省


def test_预览渲染_不同位置像素不同(tmp_path):
    """pos=左/右 与 x= 偏移应产生不同画面（引擎层端到端）。"""
    from engine.editor import _preview_png

    root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "games", "教程示例")
    def render(extra: str) -> bytes:
        p = tmp_path / ("s_" + str(abs(hash(extra))) + ".gal")
        p.write_text("@bg bg_教室\n@show 林晚 微笑 " + extra + "\n@ 测试台词\n@end\n", encoding="utf-8")
        return _preview_png(str(p), root)

    left = render("pos=左")
    right = render("pos=右")
    shifted = render("x=200")
    assert left != right, "pos=左/右 渲染结果应不同"
    assert left != shifted, "x= 像素偏移应影响渲染"
