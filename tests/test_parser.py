"""parser.py 单元测试：正确剧本 3 个 + 故意写错的 2 个（验证报错行号）+ 附加边界用例。"""
from pathlib import Path

import pytest

from engine.parser import GalSyntaxError, dump_text, parse_file, parse_text

pytestmark = [pytest.mark.unit]

FIXTURES = Path(__file__).resolve().parent / "fixtures"

# ---- 正确剧本 ----

FULL_SCRIPT = """
# 教室相遇（占位剧本）
@character 林晚 #aaccff
@character 主角 #ffcc88

@bg classroom
@music bgm_main
@show lin normal
@ 这是旁白，没有角色名。
@ 主角 你好。   # 行内注释
@ 林晚 你来了。
@sfx knock
@set 好感 += 1
@choice:
    > 打招呼: 好感 >= 1 -> label_hello
    > 不理她 -> label_ignore
@label label_hello
@if 好感 >= 1:
    @ 林晚 你已经很信任我了。
    @jump label_end
@label label_ignore
@hide lin
@label label_end
@end
"""


def _ops(instrs):
    return [i["op"] for i in instrs]


def _no_line(instrs):
    """递归去掉 line/file 字段，便于往返比较（dump_text 不输出文件信息）。"""
    out = []
    for ins in instrs:
        ins = {k: v for k, v in ins.items() if k not in ("line", "file")}
        if ins["op"] == "if":
            ins["body"] = _no_line(ins["body"])
        out.append(ins)
    return out


def test_full_script():
    instrs = parse_text(FULL_SCRIPT, source="test.gal")
    assert _ops(instrs) == [
        "character", "character", "bg", "music", "show",
        "say", "say", "say", "sfx", "set",
        "choice", "label", "if", "label", "hide", "label", "end",
    ]
    # 角色定义
    assert instrs[0] == {"op": "character", "name": "林晚", "color": "#aaccff",
                         "kind": "default", "line": 3, "file": "test.gal"}
    # 旁白 char 为 None；角色对话带 char
    assert instrs[5]["char"] is None
    assert instrs[6] == {"op": "say", "char": "主角", "text": "你好。",
                         "line": 10, "file": "test.gal"}
    # 选项：第一个带条件，第二个不带
    opts = instrs[10]["options"]
    assert opts[0] == {"text": "打招呼", "target": "label_hello",
                       "cond": {"var": "好感", "op": ">=", "value": 1}}
    assert opts[1] == {"text": "不理她", "target": "label_ignore"}
    # if 块嵌套两条指令
    if_ins = instrs[12]
    assert if_ins["cond"] == {"var": "好感", "op": ">=", "value": 1}
    assert _ops(if_ins["body"]) == ["say", "jump"]


def test_旁白前缀不进入正文():
    """`@ 旁白 文本` 是文档写法：前缀「旁白」不显示在正文里；不是独立前缀时不剥离。"""
    instrs = parse_text("@ 旁白 天台上风更大。\n@ 旁白的声音很轻。\n")
    assert instrs[0]["char"] is None
    assert instrs[0]["text"] == "天台上风更大。"
    assert instrs[1]["text"] == "旁白的声音很轻。"


def test_括号台词与整屏独白():
    """[] 标角色、[[]] 标整屏；括号/冒号都不进正文。"""
    script = (
        "@[林晚] 你好。\n"
        "@[林晚]: 冒号不会显示。\n"
        "@[旁白甲]\n"          # 括号后换行 = 下一行是台词
        "下一行也是台词。\n"
        "@[[林晚]] 那年夏天，风很长。\n"
        "@[[我忽然想起那年夏天。]]\n"
        "@ 注意：请勿靠近。\n"   # 旁白里的冒号不再有特殊含义
        "@\n"
        "hello world!\n"
    )
    instrs = parse_text(script)
    assert instrs[0]["char"] == "林晚" and instrs[0]["text"] == "你好。"
    assert instrs[0].get("layout") is None
    assert instrs[1]["text"] == "冒号不会显示。"
    assert instrs[2]["char"] == "旁白甲" and instrs[2]["text"] == "下一行也是台词。"
    assert instrs[3]["char"] == "林晚" and instrs[3]["text"] == "那年夏天，风很长。"
    assert instrs[3]["layout"] == "nvl"
    assert instrs[4]["char"] is None and instrs[4]["text"] == "我忽然想起那年夏天。"
    assert instrs[4]["layout"] == "nvl"
    assert instrs[5]["char"] is None and instrs[5]["text"] == "注意：请勿靠近。"
    assert instrs[6]["char"] is None and instrs[6]["text"] == "hello world!"


def test_括号名字里也能带方括号():
    """名字和台词都带方括号时不用加层：只认第一对「配平」的方括号。"""
    instrs = parse_text("@[林晚[老师]] [小声]你好。\n")
    assert instrs[0]["char"] == "林晚[老师]"
    assert instrs[0]["text"] == "[小声]你好。"


def test_括号台词回写与错误():
    """dump_text 能还原 [[...]]；未闭合/空括号/缺台词都有中文报错。"""
    instrs = parse_text("@[[林晚]] 独白。\n@[[整屏旁白。]]\n")
    text = dump_text(instrs)
    assert "@[[林晚]] 独白。" in text and "@[[整屏旁白。]]" in text
    again = parse_text(text)
    assert _no_line(again) == _no_line(instrs)

    with pytest.raises(GalSyntaxError, match="括号没有闭合"):
        parse_text("@[林晚 你好。\n")
    with pytest.raises(GalSyntaxError, match="缺少角色名"):
        parse_text("@[] 你好。\n")
    with pytest.raises(GalSyntaxError, match="缺少文本"):
        parse_text("@[林晚]\n")


def test_set_variants():
    instrs = parse_text("@set 好感 = 0\n@set 好感 += 1.5\n@set 体力 -= 2\n")
    assert instrs[0] == {"op": "set", "var": "好感", "operator": "=", "value": 0,
                         "line": 1, "file": "<string>"}
    assert instrs[1]["value"] == 1.5
    assert instrs[2] == {"op": "set", "var": "体力", "operator": "-=", "value": 2,
                         "line": 3, "file": "<string>"}


def test_nested_if_and_comments():
    script = (
        "@character 甲 #ffffff\n"
        "@label a\n"
        "@if 好感 == 3:\n"  # 嵌套 if + 等值条件
        "    @if 勇气 >= 2:\n"
        "        @ 甲 嵌套对话。\n"
        "@jump a\n"
    )
    instrs = parse_text(script)
    body = instrs[2]["body"]
    assert _ops(body) == ["if"]
    assert body[0]["cond"] == {"var": "勇气", "op": ">=", "value": 2}
    assert body[0]["body"][0]["text"] == "嵌套对话。"


def test_roundtrip():
    """dump_text 与 parse_text 互逆（忽略 line 字段）。"""
    instrs = parse_text(FULL_SCRIPT)
    again = parse_text(dump_text(instrs))
    assert _no_line(again) == _no_line(instrs)


def test_dump_wait_kind_show_xy_and_bracket_say():
    """2026-11-02：dump 补齐 wait/kind/x/y，角色台词统一方括号写法（卡片视图不再降级成旁白）。"""
    src = ("@character 林晚 #ffcc00 kind=nvl\n"
           "@show 林晚 微笑 anim=walk x=12 y=-3 头:帽子\n"
           "@[林晚] 你好。\n"
           "@wait 0.5\n")
    text = dump_text(parse_text(src))
    assert "@character 林晚 #ffcc00 kind=nvl" in text
    assert "@show 林晚 微笑 anim=walk x=12 y=-3 头:帽子" in text
    assert "@[林晚] 你好。" in text          # 不再输出 @ 林晚 你好（未登记时会变旁白）
    assert "@wait 0.5" in text

    again = parse_text(text)
    assert again[1]["x"] == 12 and again[1]["y"] == -3
    assert again[2]["char"] == "林晚" and again[2]["text"] == "你好。"
    assert again[3]["op"] == "wait" and again[3]["seconds"] == 0.5


# ---- 故意写错的剧本（验证报错行号）----

def test_unknown_instruction_reports_line():
    with pytest.raises(GalSyntaxError) as exc:
        parse_text("@bg classroom\n\n@foo bar\n", source="bad.gal")
    assert exc.value.line == 3
    assert "未知指令" in exc.value.message
    assert "bad.gal" in str(exc.value)


def test_undefined_label_reports_line():
    with pytest.raises(GalSyntaxError) as exc:
        parse_text("@bg classroom\n@jump nowhere\n")
    assert exc.value.line == 2
    assert "nowhere" in exc.value.message


# ---- 附加边界用例 ----

def test_choice_missing_arrow():
    with pytest.raises(GalSyntaxError) as exc:
        parse_text("@choice:\n    > 没有箭头\n")
    assert exc.value.line == 2
    assert "->" in exc.value.message


def test_bad_if_condition():
    with pytest.raises(GalSyntaxError, match="条件") as exc:
        parse_text("@if 好感 >> 3:\n    @end\n")  # 右移不在白名单内（> > < 等六种比较合法）
    assert exc.value.line == 1


def test_unexpected_indent():
    with pytest.raises(GalSyntaxError) as exc:
        parse_text("@bg classroom\n    @end\n")
    assert exc.value.line == 2
    assert "缩进" in exc.value.message


def test_tab_indentation_accepted():
    """行首 Tab 按 4 空格算：从记事本/IDE 里用 Tab 缩进的剧本也能解析。"""
    instrs = parse_text("@set 好感 = 1\n@if 好感 > 0:\n\t@ 真。\n@end\n")
    body = [i for i in instrs if i["op"] == "if"][0]["body"]
    assert body[0]["op"] == "say" and body[0]["text"] == "真。"


def test_tab_and_spaces_same_block():
    """同一块里 Tab 与 4 空格混排视为同一层级。"""
    instrs = parse_text("@if 1 > 0:\n\t@bg a\n    @bg b\n@end\n")
    body = [i for i in instrs if i["op"] == "if"][0]["body"]
    assert [i["image"] for i in body] == ["a", "b"]


def test_color_not_eaten_by_comment():
    """#aaccff 是颜色不是注释；其后的 # 注释仍被去掉。"""
    instrs = parse_text("@character 林晚 #aaccff  # 定义角色\n")
    assert instrs[0]["color"] == "#aaccff"


# ---- @include 多文件剧本 ----

def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_include_basic_inline(tmp_path):
    child = _write(tmp_path / "子.gal", "@bg room\n@ 旁白一。\n@ 旁白二。\n")
    main = _write(tmp_path / "主.gal",
                  "@character 甲 #ffffff\n@ 甲 开场。\n@include 子.gal\n@ 甲 收尾。\n")
    instrs = parse_file(main)
    assert _ops(instrs) == ["character", "say", "bg", "say", "say", "say"]
    assert [i["text"] for i in instrs if i["op"] == "say"] == ["开场。", "旁白一。", "旁白二。", "收尾。"]
    assert Path(instrs[0]["file"]).resolve() == main.resolve()
    assert Path(instrs[2]["file"]).resolve() == child.resolve()
    assert all(i["op"] != "include" for i in instrs)  # include 是解析期指令，不进指令流


def test_include_multilevel(tmp_path):
    _write(tmp_path / "c.gal", "@ C。\n")
    _write(tmp_path / "b.gal", "@include c.gal\n@ B。\n")
    main = _write(tmp_path / "a.gal", "@include b.gal\n@ A。\n")
    instrs = parse_file(main)
    assert [i["text"] for i in instrs] == ["C。", "B。", "A。"]


def test_include_cycle_reports_error(tmp_path):
    a = tmp_path / "a.gal"
    b = tmp_path / "b.gal"
    _write(a, "@include b.gal\n")
    _write(b, "@include a.gal\n")
    with pytest.raises(GalSyntaxError, match="循环") as exc:
        parse_file(a)
    assert "a.gal" in str(exc.value) and exc.value.line


def test_include_missing_file(tmp_path):
    main = _write(tmp_path / "主.gal", "@include 没有这个文件.gal\n")
    with pytest.raises(GalSyntaxError, match="不存在") as exc:
        parse_file(main)
    assert "没有这个文件.gal" in exc.value.message


def test_include_only_top_level(tmp_path):
    _write(tmp_path / "子.gal", "@ 旁白。\n")
    main = _write(tmp_path / "主.gal", "@if x == 1:\n    @include 子.gal\n")
    with pytest.raises(GalSyntaxError, match="顶层"):
        parse_file(main)


def test_include_relative_paths_fixture():
    """主文件 → 章节/第一章.gal → 子/插曲.gal → ../第二章.gal，全部按各自目录解析。"""
    main = FIXTURES / "多文件" / "主剧本.gal"
    instrs = parse_file(main)
    assert _ops(instrs) == ["character", "label", "say", "say", "label", "say",
                            "jump", "jump", "label", "say", "end"]
    assert [i["text"] for i in instrs if i["op"] == "say"] == \
        ["第一章。", "第二章的旁白。", "插曲里的旁白。", "回到主线。"]
    assert Path(instrs[3]["file"]).name == "第二章.gal"
    assert Path(instrs[5]["file"]).name == "插曲.gal"
    assert Path(instrs[-1]["file"]).resolve() == main.resolve()


def test_include_error_reports_child_file(tmp_path):
    child = _write(tmp_path / "子.gal", "@ 旁白一。\n\n@foo\n")
    main = _write(tmp_path / "主.gal", "@include 子.gal\n")
    with pytest.raises(GalSyntaxError) as exc:
        parse_file(main)
    assert exc.value.line == 3
    assert "未知指令" in exc.value.message
    assert "子.gal" in str(exc.value)


def test_include_if_body_file_field(tmp_path):
    child = _write(tmp_path / "子.gal", "@if x == 1:\n    @ 旁白 子文件。\n")
    main = _write(tmp_path / "主.gal", "@include 子.gal\n@ 旁白 主文件。\n")
    instrs = parse_file(main)
    assert instrs[0]["op"] == "if"
    assert Path(instrs[0]["body"][0]["file"]).resolve() == child.resolve()
    assert Path(instrs[1]["file"]).resolve() == main.resolve()


def test_single_file_instructions_carry_file():
    """单文件剧本：所有指令（含 if body）的 file 都是主文件路径。"""
    path = FIXTURES / "基础流程.gal"
    instrs = parse_file(path)

    def walk(items):
        for ins in items:
            assert Path(ins["file"]).resolve() == path.resolve()
            if ins["op"] == "if":
                walk(ins["body"])

    walk(instrs)


# ---- @plug: 插件指令解析 ----


def test_plug_parse():
    """@plug:shake 1.0 → plug 指令；无参数 → args 空列表。"""
    instrs = parse_text("@plug:shake 1.0 2.0\n@plug:flash\n")
    assert instrs[0] == {"op": "plug", "plugin": "shake", "args": ["1.0", "2.0"],
                         "line": 1, "file": "<string>"}
    assert instrs[1] == {"op": "plug", "plugin": "flash", "args": [],
                         "line": 2, "file": "<string>"}


def test_plug_parse_errors():
    """@plug: 空名字 / 非法名字 → GalSyntaxError 中文。"""
    with pytest.raises(GalSyntaxError, match="缺少插件指令名"):
        parse_text("@plug:\n")
    with pytest.raises(GalSyntaxError, match="插件指令名"):
        parse_text("@plug:my-shake 1.0\n")
    # 未知指令的报错应提示插件前缀写法
    with pytest.raises(GalSyntaxError, match=r"@plug:"):
        parse_text("@foo\n")


def test_plug_dump_roundtrip():
    """plug 指令 dump → 再解析，指令一致（忽略 line/file）。"""
    src = [{"op": "plug", "plugin": "shake", "args": ["1.0", "x"]},
           {"op": "plug", "plugin": "flash", "args": []}]
    text = dump_text(src)
    assert text == "@plug:shake 1.0 x\n@plug:flash\n"
    instrs = parse_text(text)
    for a, b in zip(src, instrs):
        assert {k: v for k, v in b.items() if k not in ("line", "file")} == a


# ---- P19 目标 1：@choice 选项缩进容错 ----

def test_choice_top_level_options():
    """选项行允许顶格（与 @choice: 同缩进），不再强制 4 空格。"""
    script = ("@character 甲 #ffffff\n@choice:\n> 去A -> a\n> 去B -> b\n"
              "@label a\n@end\n@label b\n@end\n")
    instrs = parse_text(script)
    choice = [i for i in instrs if i["op"] == "choice"][0]
    assert [o["text"] for o in choice["options"]] == ["去A", "去B"]


def test_choice_indent_mixed_reports_error():
    with pytest.raises(GalSyntaxError, match="缩进不一致"):
        parse_text("@choice:\n> 去A -> a\n    > 去B -> b\n@label a\n@end\n@label b\n@end\n")


def test_choice_stops_at_non_option_line():
    """非 > 行结束选项列表（随后正常解析下一指令）。"""
    instrs = parse_text("@choice:\n    > 去A -> a\n@label a\n@end\n")
    assert _ops(instrs) == ["choice", "label", "end"]


# ---- P19 目标 3：@show pos / scale ----

def test_show_pos_scale_parse():
    ins = parse_text("@show 她 smile pos=左 scale=0.5\n")[0]
    assert ins["pos"] == "左" and ins["scale"] == 0.5
    plain = parse_text("@show 她 smile\n")[0]
    assert "pos" not in plain and "scale" not in plain
    assert dump_text([plain]) == "@show 她 smile\n"


def test_show_scale_out_of_range():
    with pytest.raises(GalSyntaxError, match="scale 范围 0.5~2.0"):
        parse_text("@show 她 smile scale=3.0\n")


def test_show_pos_invalid():
    with pytest.raises(GalSyntaxError, match="pos 只能是 左/中/右"):
        parse_text("@show 她 smile pos=上\n")


# ---- P19 目标 5：六种条件运算符 ----

@pytest.mark.parametrize("op", ["==", "!=", ">", "<", ">=", "<="])
def test_if_six_operators_parse(op):
    instrs = parse_text(f"@if score {op} 3:\n    @ 旁白。\n")
    assert instrs[0]["cond"] == {"var": "score", "op": op, "value": 3}


def test_option_condition_six_operators_parse():
    instrs = parse_text("@choice:\n    > 去A: 好感 < 3 -> a\n    > 去B: 好感 != 0 -> b\n"
                        "@label a\n@end\n@label b\n@end\n")
    conds = [o["cond"] for o in instrs[0]["options"]]
    assert conds == [{"var": "好感", "op": "<", "value": 3},
                     {"var": "好感", "op": "!=", "value": 0}]


# ---- P19 目标 6：安全表达式 ----

def test_set_expression_parse():
    ins = parse_text("@set 好感 = 好感 + (次数 * 2)\n")[0]
    assert ins["operator"] == "=" and ins["expr"] == "好感 + (次数 * 2)"
    assert "value" not in ins


def test_if_combined_condition_parse():
    ins = parse_text("@if 好感 >= 5 and 见过 == 1:\n    @ 旁白。\n")[0]
    assert ins["cond"] == {"expr": "好感 >= 5 and 见过 == 1"}


# 注：P51-T3 起表达式支持字符串，`@set 好感 = "x" + 1` 语法合法，
# 类型错误推迟到运行时（ExprError 中文报错），见 test_p51_t3_str_expr.py。
@pytest.mark.parametrize("bad", ["@set 好感 = 好感.__class__\n",
                                 "@set 好感 = 好感[0]\n",
                                 "@set 好感 = __import__\n",
                                 "@set 好感 = len(好感)\n"])
def test_illegal_expression_rejected(bad):
    with pytest.raises(GalSyntaxError, match="非法表达式"):
        parse_text(bad)


def test_dump_expression_roundtrip():
    src = ("@set 好感 = 好感 + (次数 * 2)\n"
           "@if 好感 >= 5 and 见过 == 1:\n    @ 旁白。\n"
           "@choice:\n    > 去A: 好感 >= 3 or 见过 == 1 -> a\n"
           "@label a\n@end\n")
    instrs = parse_text(src)
    again = parse_text(dump_text(instrs))
    assert _no_line(again) == _no_line(instrs)


@pytest.mark.parametrize("bad", ["@set a.b = 5\n", "@set x@y = 1\n", "@set a-b = 1\n"])
def test_invalid_variable_name_rejected(bad):
    """@set 变量名必须为合法标识符（\\w+），非法名称在解析期报错。"""
    with pytest.raises(GalSyntaxError):
        parse_text(bad)
