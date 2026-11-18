# -*- coding: utf-8 -*-
"""P115：中文取值加英文别名 —— 输入两种都认，输出统一成中文。

为什么值得一个测试文件：这套语法是"英文指令 + 中文参数值"的混用体，
一旦某处只认中文、别处只认英文，作者写 left 会在这个指令上过、在那个指令上炸，
报错还看不出规律。这里把"两边都认、输出唯一"钉死。
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from engine import parser  # noqa: E402


def ins_of(text):
    return [i for i in parser.parse_text(text, "<t>") if i["op"] != "character"]


def test_pos_英文别名输出中文():
    for raw, want in (("left", "左"), ("center", "中"), ("mid", "中"),
                      ("right", "右"), ("左", "左"), ("中", "中"), ("右", "右")):
        got = ins_of(f"@character A #ffffff\n@show A 微笑 pos={raw}\n@end\n")[0]
        assert got["pos"] == want, f"pos={raw} 应统一成 {want}"


def test_pos_不认识的值仍然报错():
    with pytest.raises(parser.GalSyntaxError):
        parser.parse_text("@character A #ffffff\n@show A 微笑 pos=左边\n@end\n")


def test_camera_方向英文别名():
    for raw, want in (("left", "左"), ("右", "右"), ("up", "上"), ("down", "下")):
        got = ins_of(f"@camera pan {raw} 1.5\n@end\n")[0]
        assert got["args"][0] == want, f"camera pan {raw} 应统一成 {want}"


def test_transition_方向英文别名():
    got = ins_of("@transition wipe right 0.4\n@end\n")[0]
    assert got["args"][0] == "右"
    got = ins_of("@transition slide down 0.4\n@end\n")[0]
    assert got["args"][0] == "下"


def test_fg_none_与_无_等价():
    a = ins_of("@fg none\n@end\n")[0]
    b = ins_of("@fg 无\n@end\n")[0]
    assert a["name"] == b["name"] == "无"


def test_js侧_pos别名与python一致():
    """JS 解析器只覆盖手机上用得上的 15 种 op，所以这里只比 @show 的那一段。"""
    if not __import__("shutil").which("node"):
        pytest.skip("这台机器没有 node")
    text = ("@character 林晚 #ffb3c8\n"
            "@show 林晚 微笑 pos=left\n"
            "@show 林晚 微笑 pos=center z=2\n"
            "@show 林晚 微笑 pos=right scale=1.2\n"
            "@[林晚] 你好。\n"
            "@end\n")
    py = [i for i in parser.parse_text(text, "<t>") if i["op"] != "character"]

    with tempfile.NamedTemporaryFile("w", suffix=".gal", delete=False, encoding="utf-8") as f:
        f.write(text)
        tmp = f.name
    r = subprocess.run(["node", str(ROOT / "tools" / "_pack_node.js"), tmp],
                       capture_output=True, text=True, encoding="utf-8", cwd=str(ROOT))
    assert r.returncode == 0, r.stderr[:500]
    js = json.loads(r.stdout)
    assert js["ok"], js.get("error")
    # Python 每条指令带 file（跨文件定位用），JS 是单文件没有这个字段 —— 唯一允许的差异
    py_clean = [{k: v for k, v in i.items() if k != "file"} for i in py]
    js_ins = [i for i in js["instructions"] if i["op"] != "character"]
    assert js_ins == py_clean, "pos 别名在 JS 侧产出不一致"
