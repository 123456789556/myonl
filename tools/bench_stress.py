# -*- coding: utf-8 -*-
"""压力测试：大剧本的解析/加载/执行性能。

用法：
  py tools/bench_stress.py           # 默认：5000 句 + 20 分支 + 变量条件
  py tools/bench_stress.py --mb 1    # 生成约 1MB 纯旁白剧本
  py tools/bench_stress.py --mb 5    # 生成约 5MB 纯旁白剧本
临时文件 games/_stress_bench.gal 跑完自动删除。
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.parser import parse_file  # noqa: E402
from engine.runtime import Runtime  # noqa: E402

TMP = ROOT / "games" / "_stress_bench.gal"


def _build_branchy_script() -> str:
    """默认：5000 句 + 20 分支 + 变量条件（P22 原始基准）。"""
    lines = ["@character 主角 #ffcc88", "@character 她 #aaccff",
             "@label start", "@set 好感 += 0"]
    for i in range(5000):
        if i > 0 and i % 250 == 0:
            lines.append("@choice:")
            lines.append(f"    > 选项A{i} -> 去{i}")
            lines.append(f"    > 选项B{i} -> 去{i}")
            lines.append(f"@label 去{i}")
            lines.append("@set 好感 += 1")
            lines.append("@if 好感 >= 3:")
            lines.append("    @ 她 好感够高了。")
            lines.append("    @jump 结局")
            lines.append(f"@label 去{i}bis")
            lines.append("@jump 结局")
        lines.append(f"@ 她 第{i}句台词，今天天气不错。")
    lines.append("@label 结局")
    lines.append("@ 她 这就是结局。")
    lines.append("@end")
    return "\n".join(lines) + "\n"


def _build_mb_script(target_mb: float) -> str:
    """纯旁白压力：生成约 target_mb MB 的 .gal 文本（每行一句旁白）。"""
    target_bytes = int(target_mb * 1_000_000)
    lines = ["# 大剧本压力测试", "@bg classroom", "@character 林晚 #ffccdd"]
    i = 0
    while sum(len(l) + 1 for l in lines) < target_bytes:
        i += 1
        lines.append(f"@ 林晚 这是第 {i} 句测试旁白，用于压力测试解析性能。")
        if i % 50 == 0:
            lines.append("@label ch_" + str(i))
        if i % 200 == 0:
            lines.append("@bg park")
    lines.append("@end")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mb", type=float, default=0.0,
                    help="生成约 N MB 的纯旁白剧本（0=默认 5000 句分支剧本）")
    args = ap.parse_args()

    if args.mb > 0:
        text = _build_mb_script(args.mb)
    else:
        text = _build_branchy_script()

    TMP.write_text(text, encoding="utf-8")
    size_kb = len(text.encode("utf-8")) / 1024
    line_count = text.count("\n")
    print(f"剧本规模：{line_count} 行 / {size_kb:.1f} KB")

    t0 = time.time()
    ins = parse_file(str(TMP))
    t1 = time.time()
    print(f"解析：{t1 - t0:.3f}s，顶层指令 {len(ins)} 条")

    rt = Runtime()
    t2 = time.time()
    rt.load(str(TMP))
    t3 = time.time()
    print(f"加载：{t3 - t2:.3f}s")

    t4 = time.time()
    steps = 0
    while not rt.snapshot().get("finished"):
        s = rt.snapshot()
        if s.get("pending_choice"):
            rt.choose(0)
        else:
            rt.step()
        steps += 1
    t5 = time.time()
    st = rt.snapshot()
    print(f"全流程跑完：{t5 - t4:.3f}s，执行 {steps} 步")
    print(f"结局达成={st.get('finished')}")

    TMP.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
