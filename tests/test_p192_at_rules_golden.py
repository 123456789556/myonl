# -*- coding: utf-8 -*-
"""P192 双端对拍：@voice @cg @fg @camera @transition 放开后，JS 与 Python 必须同一条指令序列。

为什么有这一条：
    「规则存在两份实现」是当前最大的结构风险（README 已写明）。靠人工比字段，
    在 5 条 × 多参数的组合下必漏。所以把对拍固化成 tests/golden/at_rules.json：
    Python 侧产出期望值，JS 侧读同一份跑断言，谁单方面改规则都会让 CI 变红。

守护点：
1. golden 里的期望值与当前 Python 解析结果逐字段相等（golden 不会悄悄过期）；
2. node 跑 engine/parser.js 解析同一份剧本，结果与 Python 完全相等；
3. @voice 孤立出现时两端都拦（不许一边放行一边报错）；
4. 仍然写不了的只有 @plug / @include，报错文案说清这一点（P274 已放开 @anim）。

本机没有 node 时，JS 实跑部分跳过；源码级断言照跑。
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from engine.parser import GalSyntaxError, parse_text

pytestmark = [pytest.mark.unit]

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "tests" / "golden" / "at_rules.json"


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _cases() -> list[dict]:
    return json.loads(GOLDEN.read_text(encoding="utf-8"))["cases"]


def _strip_file(node):
    """去掉 file 字段：JS 端单文件，没有跨文件定位（parser.js 头部明写允许不同）。"""
    if isinstance(node, dict):
        return {k: _strip_file(v) for k, v in node.items() if k != "file"}
    if isinstance(node, list):
        return [_strip_file(x) for x in node]
    return node


# ---------- 1：golden 与 Python 同步 ----------


def test_golden_file_exists_and_has_cases():
    assert GOLDEN.is_file(), "缺少 tests/golden/at_rules.json（跑 tools/gen_at_rules.py 生成）"
    assert len(_cases()) >= 14


def test_golden_matches_python_parser():
    for case in _cases():
        got = _strip_file(parse_text(case["script"]))
        assert got == case["expect"], f"golden 过期：{case['name']}（重跑 tools/gen_at_rules.py）"


# ---------- 2：五条新分支在 JS 源码里真的存在 ----------


def test_parser_js_has_five_new_branches():
    js = _read("engine/parser.js")
    for op in ("voice", "cg", "fg", "camera", "transition"):
        assert f'head === "{op}"' in js, f"parser.js 缺 @{op} 的解析分支"
    # 方向别名表与 parser.py 的 _DIR_ALIAS 同源
    assert "left: \"左\"" in js and "down: \"下\"" in js


def test_parser_js_no_longer_pushes_these_to_desktop():
    js = _read("engine/parser.js")
    assert "请到电脑端打包" not in js, "旧文案把人推给另一台设备，已改成「暂时写不了」"
    assert "UNSUPPORTED_DIRECTIVES" in js, "未支持名单要单一来源，别把条数写死进句子"
    assert "@plug 连成品也不演" in js, "文案不能对 @plug 过度承诺：播放器没有插件实现"


# ---------- 3：@voice 前置约束两端一致 ----------


def test_python_voice_requires_say():
    with pytest.raises(GalSyntaxError) as ei:
        parse_text("@label start\n@voice a.ogg\n@end\n")
    assert "紧跟在一条台词之后" in str(ei.value)


@pytest.mark.skipif(not shutil.which("node"), reason="本机没有 node，跳过 JS 侧实跑")
def test_js_voice_also_requires_say():
    code = (
        "const P=require('./engine/parser.js');"
        "const r=P.parseText('@label start\\n@voice a.ogg\\n@end');"
        "process.stdout.write(JSON.stringify(r));"
    )
    out = subprocess.run(
        ["node", "-e", code], cwd=ROOT, capture_output=True, text=True, encoding="utf-8"
    )
    assert out.returncode == 0, out.stderr
    r = json.loads(out.stdout)
    assert r["ok"] is False
    assert "紧跟在一条台词之后" in r["error"]["message"]


# ---------- 4：节点实跑，逐条对字段 ----------


@pytest.mark.skipif(not shutil.which("node"), reason="本机没有 node，跳过 JS 侧对拍")
def test_js_matches_python_golden_case_by_case():
    out = subprocess.run(
        ["node", str(ROOT / "tools" / "at_rules_check.js")],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
    )
    assert out.returncode == 0, f"JS 侧有解析失败：{out.stdout} {out.stderr}"
    data = json.loads(out.stdout)
    js_cases = data["cases"]
    cases = _cases()
    assert len(js_cases) == len(cases)
    for case, got in zip(cases, js_cases):
        assert got["ok"], f"{case['name']} JS 解析失败：{got.get('error')}"
        assert got["got"] == case["expect"], f"字段不一致：{case['name']}"


# ---------- 5：负例（参数个数 / 范围 / 类型）两端逐字一致 ----------


def _err_cases() -> list[dict]:
    p = ROOT / "tests" / "golden" / "at_rules_errors.json"
    assert p.is_file(), "缺少 tests/golden/at_rules_errors.json（跑 tools/gen_at_rules.py）"
    return json.loads(p.read_text(encoding="utf-8"))["cases"]


def test_error_golden_matches_python():
    for case in _err_cases():
        with pytest.raises(GalSyntaxError) as ei:
            parse_text(case["script"])
        assert ei.value.message == case["message"], f"负例文案变了：{case['name']}"
        assert ei.value.line == case["line"]


@pytest.mark.skipif(not shutil.which("node"), reason="本机没有 node，跳过 JS 侧负例对拍")
def test_js_error_messages_match_python_word_for_word():
    out = subprocess.run(
        ["node", str(ROOT / "tools" / "at_rules_check.js")],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
    )
    assert out.returncode == 0, out.stderr
    data = json.loads(out.stdout)
    for case, got in zip(_err_cases(), data["errors"]):
        assert got["ok"] is False, f"{case['name']} JS 没拦住（该报错却过了）"
        assert got["message"] == case["message"], (
            f"报错文案不一致：{case['name']}\n  JS: {got['message']}\n  PY: {case['message']}"
        )
        assert got["line"] == case["line"], f"{case['name']} 报的行号不一致"
