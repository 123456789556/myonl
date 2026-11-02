"""P23 剧本修复验证：双结局收束 + 尾声差分 + 旁白干净（一次性脚本，跑完即弃）。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.runtime import Runtime

SCRIPT = r"games/示例故事/script.gal"


def run_line(choice_idx: int):
    rt = Runtime()
    rt.load(SCRIPT)
    all_texts = []
    seen_ending = set()
    while True:
        st = rt.snapshot()
        if st.get("pending_choice"):
            rt.choose(choice_idx)
            continue
        ev = rt.step()
        if ev.get("type") == "end":
            break
        if ev.get("type") == "say":
            all_texts.append(ev.get("text", ""))
            if "结局 · 遗憾" in all_texts[-1]:
                seen_ending.add("遗憾")
            if "结局 · 成全" in all_texts[-1]:
                seen_ending.add("成全")
    said_value = rt.snapshot().get("vars", {}).get("说出")
    # 尾声最后三句
    tail = [t for t in all_texts if t][-3:]
    return said_value, seen_ending, tail, all_texts


ok = True
# 线A：成全（选项1）
v, endings, tail, texts = run_line(0)
leak_a = any("这句话，我说了好久好久" in t for t in texts)  # 成全线应有的台词
print(f"[成全线] 说出={v}  经过结局={endings}  尾声={tail}")
if v != 1 or endings != {"成全"}:
    ok = False
    print("  ❌ 成全线：变量/结局异常")

# 线B：遗憾（选项2）
v, endings, tail, texts = run_line(1)
leak_b = any("这句话，我说了好久好久" in t or "真的？" in t for t in texts)  # 成全线台词不该出现在遗憾线
print(f"[遗憾线] 说出={v}  经过结局={endings}  尾声={tail}  成全线台词泄漏={leak_b}")
if v != 0 or endings != {"遗憾"}:
    ok = False
    print("  ❌ 遗憾线：变量/结局异常")
if leak_b:
    ok = False
    print("  ❌ 遗憾线泄漏了成全线内容（bug①未修复）")

# 旁白干净验证：无名台词文本不应以"旁白"开头
bad_narr = [t for t in texts if t.startswith("旁白")]
print(f"旁白前缀残留={len(bad_narr)} 处")
if bad_narr:
    ok = False
    print("  ❌ bug③未修复：", bad_narr[:3])

print("=== 验证结果:", "PASS ✅" if ok else "FAIL ❌", "===")
sys.exit(0 if ok else 1)
