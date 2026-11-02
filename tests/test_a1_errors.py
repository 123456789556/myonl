"""A1：结构化错误对象（summary/detail/hint/line/file）单元测试。

验收点：新字段齐全、detail 带文件与行号、hint 可传可选、
旧字段 message/source/line 行为不变（老调用方与老测试不受影响）。
"""
from __future__ import annotations

import pytest

from engine.errors import error_dict, suggest_hint
from engine.parser import GalSyntaxError, parse_text

pytestmark = [pytest.mark.unit]


def test_error_dict_缺省值():
    d = error_dict("缺少参数")
    assert d["summary"] == "缺少参数"
    assert d["detail"] == "缺少参数"          # detail 缺省回落 summary
    assert d["hint"] == ""
    assert d["line"] == 0
    assert d["file"] == "<string>"


def test_语法错误结构化字段():
    e = GalSyntaxError(7, "指令 @bg 缺少图片名", "chapter1.gal", hint="你是不是想写 @bg 背景名")
    assert e.summary == "指令 @bg 缺少图片名"
    assert e.detail == "chapter1.gal 第 7 行：指令 @bg 缺少图片名"
    assert e.hint == "你是不是想写 @bg 背景名"
    d = e.to_dict()
    assert d["summary"] == e.summary
    assert d["detail"] == e.detail
    assert d["hint"] == e.hint
    # 旧字段兼容
    assert d["message"] == e.message
    assert d["file"] == "chapter1.gal"
    assert d["line"] == 7


@pytest.mark.parametrize("text", ["@bg\n@end\n", "@unknown 玩意\n@end\n"])
def test_真实解析错误也带结构化字段(text):
    """解析器抛出的真错误同样能 to_dict，且 summary 不含文件前缀。"""
    with pytest.raises(GalSyntaxError) as exc:
        parse_text(text)
    e = exc.value
    d = e.to_dict()
    assert d["summary"] and d["detail"].startswith(d["file"])
    assert str(e).startswith(f"{e.source} 第 {e.line} 行：")


# ==================== A3：常见错误猜测（10 类） ====================

_CASES = [
    ("未知指令写错", "@bgm 歌.mp3\n@end\n", "拼错"),
    ("颜色格式", "@character 林晚 aaccff\n@end\n", "#aaccff"),
    ("@voice 位置", "@voice 1.ogg\n@end\n", "@voice 移到台词"),
    ("@include 文件不存在", "@include 不存在.gal\n@end\n", "检查文件名"),
    ("意外缩进", "@bg 海边.png\n  @bg 海边.png\n@end\n", "多缩进了"),
    ("缺少缩进块", "@if flag > 1\n@bg 海边.png\n@end\n", "要以冒号结尾"),
    ("@choice 冒号", "@choice\n> 走 -> 结局\n@end\n", "@choice:"),
    ("选项缺标签", "@choice:\n> 走走\n@end\n", "->"),
    ("label 参数", "@label 有 空格\n@end\n", "补齐参数"),
    ("参数应为数字", "@bg 海边.png fadein=abc\n@end\n", "要写数字"),
    ("不支持的参数", "@bg 海边.png foo=1\n@end\n", "参数名拼写"),
    ("时长必须大于 0", "@wait 0\n@end\n", "大于 0"),
    ("缺参数", "@bg\n@end\n", "补齐参数"),
]


@pytest.mark.parametrize("name,text,expect", _CASES)
def test_常见错误给出建议(name, text, expect):
    """A3：每类常见错误都能给出可操作建议（写进 GalSyntaxError.hint / to_dict）。"""
    with pytest.raises(GalSyntaxError) as exc:
        parse_text(text)
    hint = exc.value.hint
    assert hint, f"{name} 没有给出建议"
    assert expect in hint, f"{name} 建议不含「{expect}」：{hint}"


def test_猜不到时不给建议():
    """兜底：未收录的错误不给似是而非的建议。"""
    assert suggest_hint("某个没收录的错误") == ""
    assert suggest_hint("") == ""


def test_名字不合法建议():
    """标签/变量名写错时的提示（该消息不一定由解析器在行内产生，单测覆盖规则本身）。"""
    hint = suggest_hint('标签名 "a b" 不合法：只能含中英文、数字和下划线')
    assert "下划线" in hint


def test_缺at时按原文猜指令名():
    """「你是不是想写 @bg」：把漏了 @ 的首词补回去。"""
    assert suggest_hint("每条指令必须以 \"@\" 开头", "bg 海边.png") == \
        '你是不是想写 "@bg"？每条指令必须以 @ 开头；台词写成 "@[角色] 文本"（角色）或 "@ 文本"（旁白）'

