"""P51-T3：表达式字符串支持（八大方向 8.1）——字面量、+ 拼接、比较。

P28 已交付 `@set 名字 = "林晚"` 整串赋值（_SET_STR 分支）与 `${变量}` 插值；
本文件覆盖表达式内的字符串能力：evaluate/validate 层、类型纪律（中文报错）、
@set/@if 端到端。沙箱纪律不变：f-string、True/False、函数调用、属性访问仍禁止。
"""

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest  # noqa: E402

from engine.expr import ExprError, evaluate, validate  # noqa: E402
from engine.parser import parse_text  # noqa: E402
from engine.runtime import Runtime  # noqa: E402

pytestmark = [pytest.mark.unit]


def _run(script_path):
    rt = Runtime()
    rt.load(str(script_path))
    events = []
    while not rt.snapshot()["finished"]:
        ev = rt.step()
        if ev:
            events.append(ev)
    return rt, events


# ==================== 字面量与拼接 ====================

def test_expr_字符串字面量():
    assert evaluate('"林晚"') == "林晚"
    assert evaluate("'林晚'") == "林晚"  # 单引号同效
    assert evaluate('""') == ""
    validate('"林晚"')  # 不抛


def test_expr_字符串拼接():
    assert evaluate('"林" + "晚"') == "林晚"
    assert evaluate('姓 + "晚"', {"姓": "林"}) == "林晚"
    assert evaluate('"说：" + 台词', {"台词": "你好"}) == "说：你好"
    assert evaluate('"a" + "b" + "c"') == "abc"


def test_expr_字符串混合运算中文报错():
    for bad in ('"a" + 1', '1 + "a"', '"a" - "b"', '"a" * 3', '"a" / 2'):
        with pytest.raises(ExprError):
            evaluate(bad)
    with pytest.raises(ExprError):  # 未定义变量缺省 0，与字符串相加同样报类型错
        evaluate('名字 + "！"')


def test_expr_字符串正负号报错_not可用():
    with pytest.raises(ExprError):
        evaluate('-"a"')
    assert evaluate('not "a"') is False
    assert evaluate('not ""') is True


# ==================== 比较 ====================

def test_expr_字符串比较():
    assert evaluate('"林晚" == "林晚"') is True
    assert evaluate('"林晚" != "林早"') is True
    assert evaluate('"b" > "a"') is True  # 字符串之间比大小放行（字典序）
    assert evaluate('名字 == "林晚"', {"名字": "林晚"}) is True


def test_expr_字符串与数字等值放行_比大小报错():
    assert evaluate('"a" == 1') is False  # == / != 混用不崩，按不相等
    assert evaluate('"a" != 1') is True
    assert evaluate('名字 == "林晚"') is False  # 未定义缺省 0，等值比较安全得 False
    for bad in ('"a" > 1', '1 < "a"', '"a" >= 1'):
        with pytest.raises(ExprError):
            evaluate(bad)


# ==================== 沙箱纪律不变 ====================

def test_expr_沙箱仍禁止危险语法():
    for bad in ('f"{x}"', 'True', 'False', '"a".upper()', 'upper("a")', '__import__("os")'):
        with pytest.raises(ExprError):
            validate(bad)


# ==================== @set / @if 端到端 ====================

def test_runtime_set_字符串表达式(tmp_path):
    script = tmp_path / "s.gal"
    script.write_text('@set 名字 = "林" + "晚"\n@end\n', encoding="utf-8")
    rt = Runtime()
    rt.load(str(script))
    rt.step()
    assert rt.snapshot()["vars"]["名字"] == "林晚"


def test_runtime_set_单引号走表达式分支(tmp_path):
    # _SET_STR 只认双引号整串；单引号经表达式分支同样可用
    script = tmp_path / "s.gal"
    script.write_text("@set 名字 = '林晚'\n@end\n", encoding="utf-8")
    rt = Runtime()
    rt.load(str(script))
    rt.step()
    assert rt.snapshot()["vars"]["名字"] == "林晚"


def test_runtime_if_字符串比较(tmp_path):
    script = tmp_path / "s.gal"
    script.write_text(
        '@set 名字 = "林" + "晚"\n'
        '@if 名字 == "林晚":\n'
        '    @ 是她。\n'
        '@else:\n'
        '    @ 不是她。\n'
        '@end\n',
        encoding="utf-8",
    )
    _, events = _run(script)
    texts = [e["text"] for e in events if e.get("type") == "say"]
    assert texts == ["是她。"]


def test_runtime_表达式赋值后台词插值(tmp_path):
    script = tmp_path / "s.gal"
    script.write_text(
        '@set 名字 = "林" + "晚"\n'
        '@ 你好，${名字}！\n'
        '@end\n',
        encoding="utf-8",
    )
    _, events = _run(script)
    texts = [e["text"] for e in events if e.get("type") == "say"]
    assert texts == ["你好，林晚！"]


def test_parse_set_字符串表达式入expr字段():
    ins = parse_text('@set 名字 = "林" + "晚"\n')[0]
    assert ins["op"] == "set"
    assert ins["operator"] == "="
    assert ins["expr"] == '"林" + "晚"'
