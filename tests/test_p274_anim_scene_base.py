# -*- coding: utf-8 -*-
"""P274 验收：@anim 手机端打通 + 场景页「底板」一行。

为什么有这一组：
1. @anim 以前挂在手机端的「暂时写不了」名单里，但播放器（myonl-core.js / myonl-player.js）
   早就会演。只差解析这一层 —— 也就是作者在手机上连写都写不出来。
2. 用户反馈「每个场景先放背景/视频/音乐再放人再放字」，但背景/音乐/视频三个下拉
   藏在「场景设置」折叠里，一打开根本看不见。P274 把它们提成「底板」一行。
3. 电脑端有 22 条缓动曲线，手机端以前一律线性 —— 同一行 @anim 两边观感不同。这里把
   两端曲线名与公式对齐，名字对不上就等于双端不一致。

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


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _strip_file(node):
    if isinstance(node, dict):
        return {k: _strip_file(v) for k, v in node.items() if k != "file"}
    if isinstance(node, list):
        return [_strip_file(x) for x in node]
    return node


OK_SCRIPTS = [
    "@label start\n@anim 玛丽 x=-100~0 1.5\n@end",
    "@label start\n@anim 玛丽 alpha=0 0\n@end",
    "@label start\n@anim 玛丽 scale=1~1.5 2 ease=ease_in\n@end",
    "@label start\n@anim 玛丽 y=-40~0 1.2 ease=ease_out_back\n@end",
]

BAD_SCRIPTS = [
    "@label start\n@anim 玛丽\n@end",
    "@label start\n@anim 玛丽 旋转=0 1\n@end",
    "@label start\n@anim 玛丽 x 1\n@end",
    "@label start\n@anim 玛丽 alpha=2 1\n@end",
    "@label start\n@anim 玛丽 scale=5 1\n@end",
    "@label start\n@anim 玛丽 x=一~0 1\n@end",
    "@label start\n@anim 玛丽 x=0 -1\n@end",
    "@label start\n@anim 玛丽 x=0 1 ease=弹跳\n@end",
    "@label start\n@anim 玛丽 x=0 1 很快\n@end",
]

EASE_NAMES = [
    "linear", "ease_in", "ease_out", "none",
    "ease_in_quad", "ease_out_quad", "ease_in_out_quad",
    "ease_in_cubic", "ease_out_cubic", "ease_in_out_cubic",
    "ease_in_quart", "ease_out_quart", "ease_in_out_quart",
    "ease_in_sine", "ease_out_sine", "ease_in_out_sine",
    "ease_in_expo", "ease_out_expo", "ease_in_out_expo",
    "ease_in_back", "ease_out_back", "ease_in_out_back",
]


def _js():
    if not shutil.which("node"):
        pytest.skip("本机没有 node，跳过 JS 侧实跑")
    out = subprocess.run(
        ["node", str(ROOT / "tools" / "p274_check.js")],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
    )
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


# ---------- 1：源码级 ----------


def test_parser_js_has_anim_branch():
    js = _read("engine/parser.js")
    assert 'head === "anim"' in js, "parser.js 缺 @anim 的解析分支"
    assert "ANIM_PARAMS" in js and "animValue" in js, "数值校验要按参数分别卡范围"
    for name in EASE_NAMES:
        assert f'"{name}"' in js, f"缓动名单缺 {name}（必须与 timeline.py 的 22 条一致）"


def test_unsupported_list_no_longer_contains_anim():
    js = _read("engine/parser.js")
    assert 'var UNSUPPORTED_DIRECTIVES = ["plug", "include"]' in js
    assert "@include 的成品在手机上能演" in js, "@include 的边界说明不能丢"
    assert "@plug 连成品也不演" in js, "@plug 的边界说明不能丢"


def test_player_has_all_easings_and_uses_them():
    js = _read("web/myonl-player.js")
    for name in EASE_NAMES:
        assert f"{name}:" in js or f"{name}: " in js, f"播放器缺缓动曲线 {name}"
    assert "EASE[a.ease]" in js, "animDisp 要按 ease 走，不能一律线性"
    core = _read("web/myonl-core.js")
    assert 'ease: ins.ease || "linear"' in core, "补间记录必须带 ease，否则播放器取不到"


def test_perf_card_has_anim_fields():
    js = _read("editor/editor_perf.js")
    assert 'OPS = ["voice", "cg", "fg", "camera", "transition", "anim"]' in js
    for cls in ("sf-p-char", "sf-p-param", "sf-p-ease", "sf-p-from", "sf-p-to"):
        assert cls in js, f"演出卡缺 anim 的字段 {cls}"


def test_scene_form_has_base_strip_and_no_duplicate_bg_writer():
    js = _read("editor/editor_scene.js")
    assert 'class="sf-base"' in js, "场景页缺「底板」一行"
    # 三个下拉各只能有一个写手：搬出折叠后不许在折叠里再留一份
    assert js.count('id="sfBg"') == 1
    assert js.count('id="sfMusic"') == 1
    assert js.count('id="sfVideo"') == 1
    css = _read("editor/ui-fix.css")
    assert ".sf-base-cell" in css and "height: 44px" in css, "底板的 select 要 44 高，不许缩成小方块"


# ---------- 2：双端逐字段对拍 ----------


@pytest.mark.parametrize("script", OK_SCRIPTS)
def test_python_parses_anim(script):
    ins = [i for i in parse_text(script) if i["op"] == "anim"]
    assert len(ins) == 1
    assert ins[0]["param"] in ("x", "y", "alpha", "scale")
    assert ins[0]["ease"] in EASE_NAMES


@pytest.mark.parametrize("script", BAD_SCRIPTS)
def test_python_rejects_bad_anim(script):
    with pytest.raises(GalSyntaxError):
        parse_text(script)


def test_js_matches_python_for_anim():
    data = _js()
    for script, got in zip(OK_SCRIPTS, data["parse"]):
        assert got["ok"], f"JS 解析失败：{script} → {got.get('error')}"
        assert _strip_file(got["instructions"]) == _strip_file(parse_text(script)), (
            f"字段不一致：{script}"
        )


def test_js_error_messages_match_python_word_for_word():
    data = _js()
    for script, got in zip(BAD_SCRIPTS, data["errors"]):
        with pytest.raises(GalSyntaxError) as ei:
            parse_text(script)
        assert got["ok"] is False, f"JS 没拦住：{script}"
        assert got["message"] == ei.value.message, (
            f"报错文案不一致：{script}\n  JS: {got['message']}\n  PY: {ei.value.message}"
        )
        assert got["line"] == ei.value.line


# ---------- 3：演出表单写回 ----------


def test_perf_scan_line_roundtrip():
    data = _js()
    assert "anim" in data["perfOps"]
    for item in data["perfRoundtrip"]:
        assert item["parsed"], f"scan 认不出：{item['input']}"
        assert item["parsed"]["op"] == "anim"
        assert item["back"] == item["input"], f"写回与原行不一致：{item['input']} → {item['back']}"
