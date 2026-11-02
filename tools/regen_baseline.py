# 重算 tools/pyright-baseline.json：全量扫 engine/，按 file|rule 计数写回（带 BOM，与 check_types.ps1 对齐）。
import json, os, re, subprocess, sys
from collections import Counter

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(root)

out = subprocess.run(
    # 与 check_types.ps1 完全同参（--pythonpath 缺了会多出一批 reportMissingImports 环境噪音）
    [sys.executable, "-m", "pyright", "engine", "--pythonpath", sys.executable, "--outputjson"],
    capture_output=True, text=True, encoding="utf-8", errors="replace",
).stdout
scan = json.loads(out)

counts = Counter()
for d in scan["generalDiagnostics"]:
    rule = d.get("rule") or "unrule"
    counts[f"{os.path.basename(d['file'])}|{rule}"] += 1

path = os.path.join("tools", "pyright-baseline.json")
base = json.load(open(path, encoding="utf-8-sig"))
old_total = base["_total"]
new_total = scan["summary"]["errorCount"]
base["_total"] = new_total
base["counts"] = dict(sorted(counts.items()))
note = (
    f"2026-11-01 修 M1.5 遗留：SceneMixin/WindowMixin 补宿主属性 TYPE_CHECKING 声明、"
    f"demo.py AUTO 真 bug（ui.auto_interval_ms 改模块函数调用）、ui.py settings_path 注解、"
    f"capability.py stdout getattr、timeline.value() 标 Any 后下调至 {new_total}。"
)
base["_comment"] = re.sub(r"2026-11-01 修 M1\.5 遗留：.*?。", "", base["_comment"]) + note
with open(path, "w", encoding="utf-8-sig", newline="\n") as f:
    json.dump(base, f, ensure_ascii=False, indent=2)
    f.write("\n")
print(f"baseline {old_total} -> {new_total}，counts {len(counts)} 键")
