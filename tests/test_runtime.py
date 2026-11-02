"""runtime.py 验收测试。

测试里直接构造/加载剧本：临时剧本用 tmp_path，标准剧本用 tests/fixtures/。
"""
import json
from pathlib import Path

import pytest

from engine.runtime import _COMMANDS, Runtime, register_command

pytestmark = [pytest.mark.unit]

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def write_script(tmp_path, script: str) -> str:
    p = tmp_path / "test.gal"
    p.write_text(script, encoding="utf-8")
    return str(p)


def make_rt(tmp_path, script: str) -> Runtime:
    rt = Runtime()
    rt.load(write_script(tmp_path, script))
    return rt


def load_fixture(name: str) -> Runtime:
    rt = Runtime()
    rt.load(str(FIXTURES / name))
    return rt


def texts(rt: Runtime):
    """已说出的台词文本序列。"""
    return [e["text"] for e in rt.trace() if e["type"] == "say"]


# 1. 对话与旁白
def test_say_and_narration(tmp_path):
    rt = make_rt(tmp_path, "@character 林晚 #aaccff\n@ 林晚 你来了。\n@ 一阵风吹过。\n")
    e1 = rt.step()
    assert e1["type"] == "say" and e1["char"] == "林晚" and e1["text"] == "你来了。"
    e2 = rt.step()
    assert e2["type"] == "say" and e2["char"] is None  # 旁白
    snap = rt.snapshot()
    assert snap["history"] == [{"char": "林晚", "text": "你来了。"},
                               {"char": None, "text": "一阵风吹过。"}]
    assert snap["characters"] == {"林晚": {"color": "#aaccff", "kind": "default"}}


def test_say事件带已浏览标记_支持skip_viewed规则(tmp_path):
    """P44-D：首次台词 read=False，循环回到同一行 read=True（SKIP 仅已浏览据此停止）。"""
    rt = make_rt(tmp_path, "@label 开始\n@ 循环台词。\n@jump 开始\n")
    e1 = rt.step()
    assert e1["type"] == "say" and e1["read"] is False
    ev = None
    for _ in range(4):
        ev = rt.step()
        if ev.get("type") == "say":
            break
    assert ev is not None and ev["type"] == "say" and ev["read"] is True


# 2. 状态指令：bg/music/show/hide；show 重复更新不追加；hide 移除
def test_state_instructions(tmp_path):
    rt = make_rt(tmp_path, "@bg classroom\n@music bgm_main\n"
                           "@show lin normal\n@show lin happy\n@show mei sad\n@hide lin\n")
    assert rt.step() == {"type": "scene", "bg": "classroom", "line": 1, "seq": 1}
    assert rt.step()["type"] == "music"
    rt.step()  # show lin normal
    rt.step()  # show lin happy（更新）
    assert rt.snapshot()["sprites"] == [{"char": "lin", "expr": "happy", "anim": "呼吸"}]
    rt.step()  # show mei sad
    assert len(rt.snapshot()["sprites"]) == 2
    rt.step()  # hide lin
    snap = rt.snapshot()
    assert snap["bg"] == "classroom" and snap["music"] == "bgm_main"
    assert snap["sprites"] == [{"char": "mei", "expr": "sad", "anim": "呼吸"}]


# 3. 变量：+=/-=/=、未定义默认 0、负数与小数
def test_set_operations(tmp_path):
    rt = make_rt(tmp_path, "@set 好感 += 1\n@set 好感 += 2.5\n@set 好感 -= 1\n"
                           "@set 好感 = 10\n@set 负债 += -3\n")
    for _ in range(5):
        rt.step()
    assert rt.snapshot()["vars"] == {"好感": 10, "负债": -3}


# 4. if 成立 / 不成立
def test_if_taken_and_skipped(tmp_path):
    rt = make_rt(tmp_path, "@character 甲 #ffffff\n@set 好感 = 2\n"
                           "@if 好感 >= 2:\n    @ 甲 成立。\n"
                           "@if 好感 >= 5:\n    @ 甲 不该出现。\n@ 甲 结束。\n")
    events = []
    while not rt.snapshot()["finished"]:
        events.append(rt.step())
    ifs = [e for e in events if e["type"] == "if"]
    assert [e["taken"] for e in ifs] == [True, False]
    assert texts(rt) == ["成立。", "结束。"]


# 4a. P19 目标 5：六种运算符的真/假分支
@pytest.mark.parametrize("op,value,taken", [
    ("==", 5, True), ("==", 4, False),
    ("!=", 4, True), ("!=", 5, False),
    (">", 4, True), (">", 5, False),
    ("<", 6, True), ("<", 5, False),
    (">=", 5, True), (">=", 6, False),
    ("<=", 5, True), ("<=", 4, False),
])
def test_if_six_operators_execute(tmp_path, op, value, taken):
    rt = make_rt(tmp_path, "@character 甲 #ffffff\n@set score = 5\n"
                           f"@if score {op} {value}:\n    @ 甲 真。\n@ 甲 尾。\n")
    while not rt.snapshot()["finished"]:
        rt.step()
    assert texts(rt) == (["真。", "尾。"] if taken else ["尾。"])


# 4b. P19 目标 6：@set 表达式求值
def test_set_expression_eval(tmp_path):
    rt = make_rt(tmp_path, "@set 次数 = 3\n@set 好感 = 1 + 次数 * 2\n")
    rt.step()
    rt.step()
    assert rt.snapshot()["vars"] == {"次数": 3, "好感": 7}


# 4c. P19 目标 6：组合条件 and / or / not
def test_combined_condition_execute(tmp_path):
    rt = make_rt(tmp_path, "@character 甲 #ffffff\n@set 好感 = 5\n@set 见过 = 1\n"
                           "@if 好感 >= 5 and 见过 == 1:\n    @ 甲 走真。\n"
                           "@if 好感 < 5 or 见过 == 0:\n    @ 甲 走假。\n"
                           "@if not (好感 == 0):\n    @ 甲 取反真。\n")
    while not rt.snapshot()["finished"]:
        rt.step()
    assert texts(rt) == ["走真。", "取反真。"]


# 4d. P19 目标 6：台词插值 ${变量}（旧写法 {变量} 仍兼容）
def test_say_interpolation(tmp_path):
    rt = make_rt(tmp_path, "@character 她 #ffffff\n@set 好感 = 7\n@ 她 好感度是 ${好感}。\n")
    rt.step()
    ev = rt.step()
    assert ev["text"] == "好感度是 7。"
    assert rt.snapshot()["history"][-1]["text"] == "好感度是 7。"


def test_say_interpolation_legacy_braces(tmp_path):
    """旧写法 {变量} 继续可用（已定义变量时才替换）。"""
    rt = make_rt(tmp_path, "@character 她 #ffffff\n@set 好感 = 7\n@ 她 好感度是 {好感}。\n")
    rt.step()
    assert rt.step()["text"] == "好感度是 7。"


def test_rich_text_tags_not_eaten_by_interpolation(tmp_path, capsys):
    """{b} 等富文本标记不能被插值层吃掉（这是 rc4 的严重回归）。"""
    rt = make_rt(tmp_path, "@ 这是{b}粗体{/b}和{color=#ff6666}红字{/color}测试。\n")
    assert rt.step()["text"] == "这是{b}粗体{/b}和{color=#ff6666}红字{/color}测试。"
    assert "变量" not in capsys.readouterr().err


def test_undefined_legacy_brace_left_alone(tmp_path, capsys):
    """未定义的旧写法 {缺} 原样保留（不警告、不吞字），避免和富文本/字面花括号打架。"""
    rt = make_rt(tmp_path, "@ 旁白 值 {缺} 尾巴。\n")
    assert rt.step()["text"] == "值 {缺} 尾巴。"
    assert "变量" not in capsys.readouterr().err


def test_整屏独白布局进入事件与历史(tmp_path):
    """@[[...]] 的布局标记要进事件和历史，渲染层才知道走 NVL。"""
    rt = make_rt(tmp_path, "@[[林晚]] 那年夏天。\n@[[整屏旁白。]]\n@end\n")
    e1 = rt.step()
    assert e1["type"] == "say" and e1["char"] == "林晚" and e1["text"] == "那年夏天。"
    assert e1["layout"] == "nvl"
    assert rt.snapshot()["history"][0]["layout"] == "nvl"
    e2 = rt.step()
    assert e2["char"] is None and e2["text"] == "整屏旁白。" and e2["layout"] == "nvl"


def test_say_interpolation_missing_var_warns(tmp_path, capsys):
    rt = make_rt(tmp_path, "@ 旁白 ${缺}尾巴。\n")
    ev = rt.step()
    assert ev["text"] == "尾巴。"  # 「旁白」是前缀，不进正文
    assert "变量" in capsys.readouterr().err


def test_choice_all_unavailable_auto_advance(tmp_path, capsys):
    """全部选项不可选时不能死锁：自动走第一项并告警。"""
    rt = make_rt(tmp_path, "@choice:\n    > A: 0 == 1 -> a\n    > B: 0 == 1 -> b\n"
                           "@label a\n@ 到了A。\n@end\n@label b\n@ 到了B。\n@end\n")
    ev = rt.step()
    assert ev["type"] == "choice" and ev["forced"] == "a"
    assert rt.snapshot()["pending_choice"] is None
    while not rt.snapshot()["finished"]:
        rt.step()
    assert texts(rt) == ["到了A。"]
    assert "所有选项都不可选" in capsys.readouterr().err


# 5. if 嵌套：内层 body 走完后弹栈回外层继续
def test_nested_if(tmp_path):
    rt = make_rt(tmp_path, "@character 甲 #ffffff\n@set a = 1\n@set b = 3\n"
                           "@if a == 1:\n    @if b >= 3:\n        @ 甲 内层成立。\n    @ 甲 外层继续。\n")
    while not rt.snapshot()["finished"]:
        rt.step()
    assert texts(rt) == ["内层成立。", "外层继续。"]


# 6. choice 暂停与选择：pending 非空、下标不推进、available 标记、choose 跳转
def test_choice_pause_and_choose(tmp_path):
    rt = make_rt(tmp_path, "@character 林晚 #aaccff\n@set 好感 = 0\n"
                           "@choice:\n    > 打招呼: 好感 >= 1 -> hello\n    > 离开 -> leave\n"
                           "@label hello\n@ 林晚 你好呀。\n@label leave\n@ 林晚 再见。\n")
    rt.step()  # set（character 被静默跳过）
    ev = rt.step()  # choice 暂停
    assert ev["type"] == "choice"
    assert ev["options"][0]["available"] is False  # 条件不满足
    assert ev["options"][1]["available"] is True
    snap = rt.snapshot()
    assert snap["pending_choice"] is not None
    assert snap["stack"] == [[0, 2]]  # 下标停在 choice 指令上，没推进
    # 暂停期间 step 报错；错误选择报错
    with pytest.raises(RuntimeError, match="choose"):
        rt.step()
    with pytest.raises(RuntimeError, match="不可选"):
        rt.choose(0)
    with pytest.raises(RuntimeError, match="越界"):
        rt.choose(5)
    # 选择「离开」→ 跳到 leave 标签
    snap = rt.choose(1)
    assert snap["pending_choice"] is None
    assert snap["stack"] == [[0, 5]]
    assert rt.step()["text"] == "再见。"


# 7. jump：前向跳过、后向回跳（配合 if 出循环）
def test_jump_forward_and_backward(tmp_path):
    rt = make_rt(tmp_path, "@character 甲 #ffffff\n@jump middle\n@ 甲 不该出现。\n"
                           "@label middle\n@set 次数 = 0\n@label loop\n@set 次数 += 1\n"
                           "@if 次数 >= 3:\n    @jump over\n@jump loop\n"
                           "@label over\n@ 甲 跳出来了。\n")
    while not rt.snapshot()["finished"]:
        rt.step()
    assert texts(rt) == ["跳出来了。"]
    assert rt.snapshot()["vars"]["次数"] == 3


# 8. run_to：跑到指定标签停止；目标在分支内也能跑到
def test_run_to(tmp_path):
    rt = make_rt(tmp_path, "@character 甲 #ffffff\n@ 甲 开头。\n@label middle\n@ 甲 中段。\n"
                           "@set 好感 = 5\n@label late\n@if 好感 >= 5:\n"
                           "    @label inner\n    @ 甲 分支内。\n")
    rt.run_to("middle")
    assert rt.step()["text"] == "中段。"
    rt.run_to("inner")  # 标签在 if body 里
    assert rt.step()["text"] == "分支内。"


def test_jump_into_if_body_continues_after_block(tmp_path):
    """跳到 @if 块内的 label：执行完 body 要回到 if 之后，而不是直接结束整部游戏。"""
    rt = make_rt(tmp_path, "@jump inner\n@ 不该执行。\n@if 1 > 0:\n"
                           "    @label inner\n    @ 分支内。\n@ 尾部二。\n@end\n")
    while not rt.snapshot()["finished"]:
        rt.step()
    assert texts(rt) == ["分支内。", "尾部二。"]


# 9. trace：连续 step 后顺序与 seq 正确
def test_trace_order(tmp_path):
    rt = make_rt(tmp_path, "@character 甲 #ffffff\n@bg classroom\n@ 甲 你好。\n@set 好感 += 1\n")
    for _ in range(3):
        rt.step()
    tr = rt.trace()
    assert [e["type"] for e in tr] == ["scene", "say", "set"]
    assert [e["seq"] for e in tr] == [1, 2, 3]


# 10. snapshot 可 JSON 序列化；新 Runtime 独立运行互不影响
def test_snapshot_serializable_and_isolated(tmp_path):
    path = write_script(tmp_path, "@character 甲 #ffffff\n@ 甲 你好。\n")
    rt1 = Runtime()
    rt1.load(path)
    rt1.step()
    json.dumps(rt1.snapshot(), ensure_ascii=False)  # 不抛异常即可序列化
    rt2 = Runtime()
    rt2.load(path)
    rt2.step()
    rt2.step()  # rt2 多走一步（自然结束）
    assert len(rt1.snapshot()["history"]) == 1  # rt1 不受影响
    assert rt2.snapshot()["finished"] is True


# 11. 完整剧本：fixtures/基础流程.gal（engine_spec 3.4）完整执行轨迹
def test_full_script_classroom():
    rt = load_fixture("基础流程.gal")
    types = []
    while True:
        ev = rt.step()
        types.append(ev["type"])
        if ev["type"] == "choice":
            break
    rt.choose(0)  # 打招呼（好感=1，条件满足）
    while not rt.snapshot()["finished"]:
        types.append(rt.step()["type"])
    assert types == ["scene", "music", "show", "say", "say", "say", "sfx", "set",
                     "choice", "if", "say", "jump", "hide", "end"]
    assert rt.snapshot()["history"][-1] == {"char": "林晚", "text": "你已经很信任我了。"}


# 12. end 与栈空：@end 正常结束；无 @end 跑完后自动 finished
def test_end_and_auto_finish(tmp_path):
    rt = make_rt(tmp_path, "@character 甲 #ffffff\n@ 甲 一句。\n@end\n@ 甲 永不出现。\n")
    while not rt.snapshot()["finished"]:
        rt.step()
    assert texts(rt) == ["一句。"]  # @end 之后的内容不执行
    assert rt.step()["type"] == "end"  # finished 后再 step 安全返回 end

    rt2 = make_rt(tmp_path, "@character 甲 #ffffff\n@ 甲 唯有一句。\n")
    assert rt2.step()["type"] == "say"
    ev = rt2.step()
    assert ev == {"type": "end", "line": None, "seq": 2}  # 栈空自动结束
    assert rt2.snapshot()["finished"] is True


# 13. 空剧本：只含 @end 正常跑完；空文件直接 finished
def test_empty_scripts(tmp_path):
    rt = make_rt(tmp_path, "@end\n")
    assert rt.step() == {"type": "end", "line": 1, "seq": 1}
    assert rt.snapshot()["finished"] is True

    rt2 = make_rt(tmp_path, "")
    assert rt2.step()["type"] == "end"
    assert rt2.snapshot()["finished"] is True


# 14. 死循环防护：@jump 跳回自身，到上限抛 RuntimeError 而不是卡死
def test_infinite_loop_guard(tmp_path):
    rt = make_rt(tmp_path, "@label a\n@jump a\n")
    rt.MAX_STEPS = 500  # 测试用小上限（默认 100 万）
    with pytest.raises(RuntimeError, match="死循环"):
        for _ in range(600):
            rt.step()


# 15. set_var 边界：非数字抛 RuntimeError（中文）；新变量自动创建
def test_set_var_validation(tmp_path):
    rt = make_rt(tmp_path, "@end\n")
    with pytest.raises(RuntimeError, match="数字"):
        rt.set_var("好感", "很多")
    snap = rt.set_var("好感", 3)
    assert snap["vars"] == {"好感": 3}


# 16. inject 生效：step 前注入 @set，后续执行能看到变量变化
def test_inject(tmp_path):
    rt = make_rt(tmp_path, "@character 甲 #ffffff\n@ 甲 第一句。\n@ 甲 第二句。\n")
    snap = rt.inject([{"op": "set", "var": "好感", "operator": "=", "value": 5, "line": 0}])
    assert snap["stack"] == [[0, 0]]  # 插在当前指令（@character）之前，位置指向注入指令
    assert rt.step()["type"] == "set"  # 注入的指令先执行
    assert rt.snapshot()["vars"]["好感"] == 5
    assert rt.step()["text"] == "第一句。"  # 原指令继续
    with pytest.raises(RuntimeError, match="list"):
        rt.inject("不是列表")
    with pytest.raises(NotImplementedError):
        rt.inject([], at="end")


# 17. run_to 不存在的标签：抛 RuntimeError（中文）
def test_run_to_missing_label(tmp_path):
    rt = make_rt(tmp_path, "@end\n")
    with pytest.raises(RuntimeError, match="找不到标签"):
        rt.run_to("ghost")


# 附加：fixtures 另外两个标准剧本可完整跑通（供 --check/--run 手工验证的底账）
def test_fixture_branch_endings():
    rt = load_fixture("分支多结局.gal")
    while rt.step()["type"] != "choice":
        pass
    rt.choose(1)  # 走右边
    while not rt.snapshot()["finished"]:
        rt.step()
    assert "山巅" in texts(rt)[-1]
    assert rt.snapshot()["bg"] == "mountain"


def test_fixture_nested_if_boundaries():
    rt = load_fixture("if嵌套边界.gal")
    while not rt.snapshot()["finished"]:
        rt.step()
    assert texts(rt) == ["外层成立、内层也成立。", "外层成立收尾。", "全部结束。"]


# 18. 存档：save → 新 Runtime load_save → GameState 深度一致
def test_save_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # 存档写入临时目录
    rt = load_fixture("基础流程.gal")
    for _ in range(5):
        rt.step()
    rt.save(1)
    before = rt.snapshot()

    rt2 = Runtime()
    after = rt2.load_save(1)
    assert after == before
    assert after["bg"] == "classroom" and after["music"] == "bgm_main"


# 19. 锚点：存档后两个运行时继续推进，事件逐条一致
def test_save_load_continues_identically(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    rt = load_fixture("基础流程.gal")
    for _ in range(3):
        rt.step()
    rt.save(2)
    rt2 = Runtime()
    rt2.load_save(2)

    while not rt.snapshot()["finished"]:
        e1, e2 = rt.step(), rt2.step()
        if e1["type"] == "choice":
            rt.choose(0)
            rt2.choose(0)
        e1.pop("seq"), e2.pop("seq")
        assert e1 == e2


# 20. 多文件：include 展开后跨文件角色/跳转正常执行
def test_multi_file_include_execution():
    rt = load_fixture("多文件/主剧本.gal")
    while not rt.snapshot()["finished"]:
        rt.step()
    assert texts(rt) == ["第一章。", "第二章的旁白。", "插曲里的旁白。", "回到主线。"]
    assert rt.snapshot()["characters"] == {"林晚": {"color": "#aaccff", "kind": "default"}}


# 21. 多文件 + 存档：读档重新展开 include，锚点仍能定位
def test_multi_file_save_roundtrip(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    rt = load_fixture("多文件/主剧本.gal")
    rt.step()  # 第一句（第一章。）
    rt.save(1)
    before = rt.snapshot()

    rt2 = Runtime()
    assert rt2.load_save(1) == before
    assert rt2.step()["text"] == "第二章的旁白。"


# ==================== 插件指令（@plug:）====================


@pytest.fixture(autouse=False)
def clean_commands():
    """插件测试前后清空注册表，避免污染其他测试。"""
    _COMMANDS.clear()
    yield
    _COMMANDS.clear()


def write_plugin(tmp_path, filename: str, code: str) -> Path:
    """在 tmp_path/plugins/ 下写插件文件，返回插件目录。"""
    plugins = tmp_path / "plugins"
    plugins.mkdir(exist_ok=True)
    (plugins / filename).write_text(code, encoding="utf-8")
    return plugins


# 22. 执行：注册 handler → step 调用 handler、state 变化、返回事件进 trace（带 seq）
def test_plug_execute(tmp_path, clean_commands):
    calls = []

    def shake(state, args):
        calls.append(list(args))
        state["shake"] = {"power": float(args[0])}
        return {"type": "plug:shake", "power": state["shake"]["power"]}

    rt = make_rt(tmp_path, "@plug:shake 1.5\n@end\n")
    register_command("shake", shake)
    event = rt.step()
    assert calls == [["1.5"]]
    assert rt.snapshot()["shake"] == {"power": 1.5}
    assert event["type"] == "plug:shake" and event["power"] == 1.5
    assert event["seq"] == 1 and event["line"] == 1
    assert "op" not in event  # 插件事件不带 op 字段，避免与内置指令混淆
    assert rt.trace()[0]["type"] == "plug:shake"


# 23. 静默 handler：返回 None → 无事件、下标推进（同 step 内继续执行下一条）
def test_plug_silent_handler(tmp_path, clean_commands):
    def mark(state, args):
        state["vars"]["标记"] = 1
        return None

    rt = make_rt(tmp_path, "@plug:mark\n@ 旁白 下一句。\n@end\n")
    register_command("mark", mark)
    event = rt.step()  # 执行 @plug:mark（静默），同 step 内继续到 say
    assert event["type"] == "say" and event["text"] == "下一句。"
    assert rt.snapshot()["vars"]["标记"] == 1
    assert all(e["type"] != "plug:mark" for e in rt.trace())


# 24. 未注册：@plug:no_such → RuntimeError 中文（提示检查 plugins/ 目录）
def test_plug_unregistered(tmp_path, clean_commands):
    rt = make_rt(tmp_path, "@plug:no_such 1\n@end\n")
    with pytest.raises(RuntimeError, match=r"@plug:no_such.*未注册"):
        rt.step()


# 25. 插件目录加载：plugins/shake.py → load 后 @plug:shake 可执行
def test_plug_dir_loading(tmp_path, clean_commands):
    write_plugin(tmp_path, "shake.py", (
        "from engine.runtime import register_command\n"
        "def shake(state, args):\n"
        "    state['shake'] = {'power': float(args[0]) if args else 1.0}\n"
        "    return {'type': 'plug:shake', 'power': state['shake']['power']}\n"
        "register_command('shake', shake)\n"
    ))
    rt = make_rt(tmp_path, "@plug:shake 2.0\n@end\n")
    assert rt.step()["power"] == 2.0
    assert rt.snapshot()["shake"]["power"] == 2.0


# 26. 坏插件不崩：语法错误的插件 → load 打印中文警告、不抛错，其他指令正常
def test_plug_broken_file(tmp_path, clean_commands, capsys):
    write_plugin(tmp_path, "bad.py", "def broken(:\n")  # 语法错误
    write_plugin(tmp_path, "good.py", (
        "from engine.runtime import register_command\n"
        "register_command('good', lambda state, args: {'type': 'plug:good'})\n"
    ))
    rt = make_rt(tmp_path, "@plug:good\n@end\n")
    assert "[插件警告]" in capsys.readouterr().err
    assert rt.step()["type"] == "plug:good"  # 好插件不受影响


# 27. handler 抛异常不崩：stderr 中文警告 + plug:error 事件 + 游戏继续
def test_plug_handler_raises(tmp_path, clean_commands, capsys):
    def boom(state, args):
        raise ValueError("插件内部出错")

    rt = make_rt(tmp_path, "@plug:boom\n@ 旁白 继续。\n@end\n")
    register_command("boom", boom)
    event = rt.step()
    assert event["type"] == "plug:error" and event["plugin"] == "boom"
    assert "[插件错误]" in capsys.readouterr().err
    assert rt.step()["text"] == "继续。"  # 游戏继续推进


# 28. 重 load 换插件：加载 A → 删掉 → 重新 load → @plug:a 未注册
def test_plug_reload_swaps(tmp_path, clean_commands):
    write_plugin(tmp_path, "a.py", (
        "from engine.runtime import register_command\n"
        "register_command('a', lambda state, args: {'type': 'plug:a'})\n"
    ))
    script = write_script(tmp_path, "@plug:a\n@end\n")
    rt = Runtime()
    rt.load(script)
    assert rt.step()["type"] == "plug:a"

    (tmp_path / "plugins" / "a.py").unlink()
    rt.load(script)  # 重新 load 重扫 plugins/
    with pytest.raises(RuntimeError, match="未注册"):
        rt.step()


# 29. 存档含插件字段：插件写 state → save → load_save → 字段还原
def test_plug_state_in_save(tmp_path, monkeypatch, clean_commands):
    monkeypatch.chdir(tmp_path)
    rt = load_fixture("插件示例/main.gal")  # 剧本目录下的 plugins/shake.py 自动加载
    rt.step()  # @bg classroom
    rt.step()  # @plug:shake 1.0 → state["shake"]
    assert rt.snapshot()["shake"] == {"power": 1.0}
    rt.save(1)

    rt2 = Runtime()
    rt2.load_save(1)
    assert rt2.snapshot()["shake"] == {"power": 1.0}
    assert rt2.step()["text"] == "刚才屏幕是不是晃了一下！"


# 30. 字符串变量参与数值比较时 TypeError 被捕获，不崩溃
def test_if_type_error_caught(tmp_path, capsys):
    """@if 条件中字符串变量与数字比较时，TypeError 被捕获并打印警告，不崩溃。"""
    script = write_script(tmp_path, (
        '@set 名字 = "Alice"\n'
        '@if 名字 > 5:\n'
        '    @ 不会执行\n'
        '@end\n'
    ))
    rt = Runtime()
    rt.load(script)
    rt.step()  # @set 名字 = "Alice"
    # @if 名字 > 5 会触发 TypeError（字符串 vs 数字）
    event = rt.step()
    captured = capsys.readouterr()
    assert "剧本警告" in captured.err
    assert "类型不匹配" in captured.err or "条件求值失败" in captured.err
    # 条件求值失败应跳过 if 块，继续执行
    assert event["type"] == "end"
