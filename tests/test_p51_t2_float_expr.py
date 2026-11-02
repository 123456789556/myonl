"""P51-T2：表达式浮点支持（`@set 概率=0.5`、`@set 概率 = 0.5 + 0.25`）。

T2 来自八大技术方向 8.2（表达式浮点支持）+ 8.1（字符串支持，P28 已交付）。
本文件覆盖浮点部分：字面量、四则、比较、与整型混用、@set/@if 端到端；
字符串变量已有 test_p28 E5 覆盖，不重复。
"""

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest  # noqa: E402

from engine.expr import ExprError, evaluate, validate  # noqa: E402
from engine.parser import parse_text  # noqa: E402
from engine.runtime import Runtime  # noqa: E402

pytestmark = [pytest.mark.unit]


def test_expr_浮点字面量求值():
    assert evaluate("0.5") == 0.5
    assert evaluate("1.0") == 1.0
    assert evaluate("-0.25") == -0.25
    assert evaluate(".5") == 0.5  # 不带整数位的小数


def test_expr_浮点四则与整型混用():
    assert evaluate("0.5 + 0.25") == 0.75
    assert evaluate("1 - 0.5") == 0.5
    assert evaluate("2 * 0.5") == 1.0
    assert evaluate("1 / 2") == 0.5
    assert evaluate("3 + 0.5") == 3.5


def test_expr_浮点比较():
    assert evaluate("0.5 > 0.25") is True
    assert evaluate("0.5 < 1") is True
    assert evaluate("0.5 == 0.5") is True
    assert evaluate("0.5 != 0.6") is True


def test_expr_浮点与变量混用():
    assert evaluate("x + 0.5", {"x": 2}) == 2.5
    assert evaluate("x > 0.5", {"x": 1}) is True


# 注：表达式内字符串字面量/拼接/比较已由 P51-T3 放开，见 test_p51_t3_str_expr.py。


def test_expr_布尔仍被禁止():
    with pytest.raises(ExprError):
        validate("True")
    with pytest.raises(ExprError):
        validate("False")


def test_parse_set_浮点字面量():
    ins = parse_text("@set 概率=0.5\n")[0]
    assert ins["op"] == "set"
    assert ins["var"] == "概率"
    assert ins["operator"] == "="
    assert ins["value"] == 0.5


def test_runtime_set_浮点变量(tmp_path):
    script = tmp_path / "s.gal"
    script.write_text("@set 概率=0.5\n@end\n", encoding="utf-8")
    rt = Runtime()
    rt.load(str(script))
    rt.step()
    assert rt.snapshot()["vars"]["概率"] == 0.5


def test_runtime_set_浮点表达式(tmp_path):
    script = tmp_path / "s.gal"
    script.write_text("@set 概率 = 0.5 + 0.25\n@end\n", encoding="utf-8")
    rt = Runtime()
    rt.load(str(script))
    rt.step()
    assert rt.snapshot()["vars"]["概率"] == 0.75


def test_runtime_if_浮点比较(tmp_path):
    script = tmp_path / "s.gal"
    script.write_text(
        "@set 概率 = 0.6\n"
        "@if 概率 >= 0.5:\n"
        "    @ 命中！\n"
        "@else:\n"
        "    @ 未命中。\n"
        "@end\n",
        encoding="utf-8",
    )
    rt = Runtime()
    rt.load(str(script))
    texts = []
    while not rt.snapshot()["finished"]:
        ev = rt.step()
        if ev and ev.get("type") == "say":
            texts.append(ev["text"])
    assert texts == ["命中！"]


def test_runtime_if_浮点边界(tmp_path):
    script = tmp_path / "s.gal"
    script.write_text(
        "@set 概率 = 0.5\n"
        "@if 概率 >= 0.5:\n"
        "    @ 及格\n"
        "@end\n",
        encoding="utf-8",
    )
    rt = Runtime()
    rt.load(str(script))
    texts = []
    while not rt.snapshot()["finished"]:
        ev = rt.step()
        if ev and ev.get("type") == "say":
            texts.append(ev["text"])
    assert texts == ["及格"]
