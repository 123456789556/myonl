# -*- coding: utf-8 -*-
"""复杂分支网络全遍历验证（P19 表达式改造版）：5 层选择点 × 2 选项 = 32 条路径。

本轮额外覆盖 P19 目标 6：
- `@set x = x + 1` / `x + 10` 走安全表达式求值（不再用 +=）
- 结局分派用组合条件（and / <）与台词插值 `${score}`

每条路径验证：
1. 都能跑完到某个结局（finished=True）
2. 变量 score 与路径选择一致（选"加1"→+1，选"加10"→+10）
3. 结局标签按变量正确分派（5/50/混合）
4. 台词插值输出真实 score
5. 无死循环（runtime 自带 MAX_STEPS 兜底）

用法：py tools/verify_complex_branches.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.runtime import Runtime  # noqa: E402

LAYERS = 5  # 选择点层数 → 2^5 = 32 条路径
TMP = ROOT / "games" / "_complex_bench.gal"


def build_script() -> str:
    lines = ["@character 主角 #ffcc88", "@character 她 #aaccff",
             "@label start", "@set score = 0"]
    for k in range(LAYERS):
        lines.append(f"@label 层{k}")
        lines.append("@choice:")
        lines.append(f"    > 选加1 -> 层{k}一")
        lines.append(f"    > 选加10 -> 层{k}十")
        lines.append(f"@label 层{k}一")
        lines.append("@set score = score + 1")
        lines.append(f"@jump 层{k + 1}")
        lines.append(f"@label 层{k}十")
        lines.append("@set score = score + 10")
        lines.append(f"@jump 层{k + 1}")
    lines.append("@label 层5")
    lines.append("@if score == 5:")
    lines.append("    @ 旁白 全选加1。")
    lines.append("    @jump 结局小")
    lines.append("@if score == 50:")
    lines.append("    @ 旁白 全选加10。")
    lines.append("    @jump 结局大")
    lines.append("@if score >= 21 and score < 50:")
    lines.append("    @ 旁白 混合偏大。")
    lines.append("    @jump 结局混")
    lines.append("    @ 旁白 混合偏小。")
    lines.append("    @jump 结局小")
    lines.append("@label 结局小")
    lines.append("@ 她 结局：小数值（score=${score}）。")
    lines.append("@end")
    lines.append("@label 结局大")
    lines.append("@ 她 结局：大数值（score=${score}）。")
    lines.append("@end")
    lines.append("@label 结局混")
    lines.append("@ 她 结局：混合（score=${score}）。")
    lines.append("@end")
    return "\n".join(lines)


def run_path(choice_seq: tuple) -> tuple:
    """按 choice_seq（每层选 0=加1 / 1=加10）跑一条路径，返回 (结局文本, score, ok)。"""
    rt = Runtime()
    rt.load(str(TMP))
    steps = 0
    while not rt.snapshot().get("finished"):
        s = rt.snapshot()
        if s.get("pending_choice"):
            if steps >= len(choice_seq):
                return ("卡在选项", None, False)
            rt.choose(choice_seq[steps])
            steps += 1
        else:
            rt.step()
    st = rt.snapshot()
    hist = st.get("history") or []
    end_text = str(hist[-1].get("text", "")) if hist else ""
    score = st.get("vars", {}).get("score")
    return (end_text, score, True)


def main() -> int:
    TMP.write_text(build_script(), encoding="utf-8")
    total = 2 ** LAYERS
    ok = 0
    fails = []
    t0 = time.time()
    for mask in range(total):
        seq = tuple(1 if (mask >> k) & 1 else 0 for k in range(LAYERS))
        end_text, score, ran = run_path(seq)
        # 期望分数 = 选1个数×1 + 选10个数×10
        expect = sum(1 if c == 0 else 10 for c in seq)
        exp_end = ("结局：小数值" if expect == 5 else
                   "结局：大数值" if expect == 50 else
                   "结局：混合" if expect >= 21 else "结局：小数值")
        expect_text = f"{exp_end}（score={expect}）。"
        if ran and score == expect and end_text == expect_text:
            ok += 1
        else:
            fails.append((seq, score, expect, end_text, expect_text, ran))
    t1 = time.time()
    print(f"路径总数：{total}（{LAYERS} 层 × 2 选项）")
    print(f"通过：{ok}/{total}，耗时 {t1 - t0:.2f}s")
    if fails:
        for f in fails:
            print(f"FAIL 路径 {f}")
        return 1
    print("结论：32 条路径全部正确——表达式累计、组合条件分派、台词插值、无死循环。")
    TMP.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
