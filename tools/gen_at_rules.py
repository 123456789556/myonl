# -*- coding: utf-8 -*-
"""生成 tests/golden/at_rules.json：手机端与电脑端解析器的双端对拍基准。

为什么要有这一份：
    规则存在两份实现（engine/parser.py 与 engine/parser.js），历史上已经漂移过
    （手机端一度连 @cg 都写不出来）。靠人工比字段在 5 条 × 多参数的组合下必漏，
    所以把「同一份剧本 → 同一条指令序列」固化成文件：Python 侧产出期望值，
    JS 侧读同一份跑断言，谁单方面改规则都会让 CI 变红。

用法：
    py -3 tools/gen_at_rules.py          # 规则改了就重跑，刷新 json
    py -3 -m pytest tests/test_p192_at_rules_golden.py -q

不要手改 at_rules.json —— 它由本脚本产出，手改会和 CASES 失去对应关系。
"""
import json
import sys
from pathlib import Path

# 直接 `py -3 tools/gen_at_rules.py` 时 sys.path[0] 是 tools/，engine 包在仓库根下
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.parser import GalSyntaxError, parse_text  # noqa: E402

# 每条用例：(名字, 剧本中间那几行)。@label/@end 是给解析器一个好走的壳，
# 也让跳转目标校验有落点。@voice 必须紧跟台词（parser.py:193 的约束），
# 所以它前面要带一条台词，不能裸写。
CASES = [
    ("voice_basic", ["@[林晚] 你又迟到了。", "@voice a.ogg"]),
    ("cg_basic", ["@cg cg_雨夜"]),
    ("fg_basic", ["@fg fg_雨"]),
    ("fg_xy_alpha", ["@fg fg_雨 x=10 y=-8 alpha=0.5"]),
    ("fg_none_clear", ["@fg 无"]),
    ("fg_none_alias", ["@fg none"]),
    ("camera_pan_cn", ["@camera pan 左 1.5"]),
    ("camera_pan_en", ["@camera pan left 1.5"]),
    ("camera_zoom", ["@camera zoom 1.0 1.3"]),
    ("camera_shake", ["@camera shake 0.5 8"]),
    ("camera_reset", ["@camera reset 0.8"]),
    ("transition_dissolve", ["@transition dissolve 0.4"]),
    ("transition_wipe", ["@transition wipe 左 0.4"]),
    ("transition_slide", ["@transition slide right 0.6"]),
]

OUT = Path(__file__).resolve().parents[1] / "tests" / "golden" / "at_rules.json"
ERR_OUT = Path(__file__).resolve().parents[1] / "tests" / "golden" / "at_rules_errors.json"

# 负例：这些写法必须被拒，且两端的报错文案要逐字一样。
# 只比成功路径的字段不够 —— 参数校验（个数 / 范围 / 类型）全在报错分支里。
ERROR_CASES = [
    ("fg_too_many_args", "@fg a b c d e"),
    ("fg_alpha_out_of_range", "@fg fg_雨 alpha=1.5"),
    ("fg_x_not_int", "@fg fg_雨 x=1.5"),
    ("camera_unknown_kind", "@camera dolly 1"),
    ("voice_without_say", "@voice a.ogg"),
    ("cg_too_many_args", "@cg a b"),
    ("transition_unknown_kind", "@transition fade 1"),
    ("camera_pan_zero_secs", "@camera pan 左 0"),
]


def strip_file(node):
    """去掉 file 字段：JS 端是单文件，没有跨文件定位（parser.js 头部明写允许不同）。"""
    if isinstance(node, dict):
        return {k: strip_file(v) for k, v in node.items() if k != "file"}
    if isinstance(node, list):
        return [strip_file(x) for x in node]
    return node


def build_errors() -> list[dict]:
    out = []
    for name, line in ERROR_CASES:
        script = "@label start\n" + line + "\n@end\n"
        try:
            parse_text(script)
        except GalSyntaxError as e:
            # 存纯文案（不带「<string> 第 N 行：」前缀），JS 侧 error.message 就是这个
            out.append({"name": name, "script": script,
                        "line": int(e.line or 0), "message": str(getattr(e, "message", e))})
        else:
            raise SystemExit(f"{name} 本该报错却解析通过了（负例失效）")
    return out


def main() -> int:
    out = []
    for name, lines in CASES:
        script = "@label start\n" + "\n".join(lines) + "\n@end\n"
        ins = parse_text(script)
        out.append({"name": name, "script": script, "expect": strip_file(ins)})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps({"version": 1, "cases": out}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8", newline="\n",
    )
    errors = build_errors()
    ERR_OUT.write_text(
        json.dumps({"version": 1, "cases": errors}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8", newline="\n",
    )
    print(f"写出 {OUT}：{len(out)} 条正例")
    print(f"写出 {ERR_OUT}：{len(errors)} 条负例")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

