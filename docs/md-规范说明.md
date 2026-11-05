# MYONL 项目 Markdown 规范说明

> 版本：v1.0　日期：2026-10-28　状态：已生效
> 用途：统一本项目所有 .md 文档的书写格式，作为新建与修改文档的强制检查项。
> 依据：2026-10-28 全量扫描 59 个 md 的现状与修复（唯一问题已清理）。

## 1. 硬性规范（不满足即视为不合规）

| 项 | 标准 | 检查方法 |
|---|---|---|
| 编码 | UTF-8（无 BOM） | 见 §3 检查脚本 |
| 行尾 | LF（`\n`），禁止 CRLF 与混合行尾 | 见 §3 检查脚本 |
| 尾随空格 | 行尾不允许 ` ` / `\t` | 见 §3 检查脚本 |
| 文件末尾 | 最后一行以 `\n` 结尾 | `text.endswith("\n")` |
| 文档级标题 | **全文档唯一一个 H1**（`# `）；代码块内的 `# 注释` 不算 | 排除 ``` 围栏后计数 == 1 |
| 章节层级 | 文档 H1 之下依次用 `##` → `###` → `####` | 目视/审阅 |

## 2. 书写约定（建议，不强制）

- 计划书/变更说明/任务单类文档：标题下紧跟一行元信息块：
  `> 版本：vX.X　日期：YYYY-MM-DD　状态：待评审/已生效`
  多版本时在元信息块内追加 `> vX.Y 变更：…` 行。
- 表格统一用 GFM 管道表，表头用 `|---|---|` 分隔行。
- 命令示例统一用 ```powershell 围栏；运行结果中的注释写行内 `# …`，不单起一行 `# `（避免被 H1 扫描误报）。
- 正文中文，不混用全角/半角标点（每份文档保持一贯即可）。

## 3. 检查脚本（复现用）

```python
# 一键扫描项目根所有 md 的合规性（输出违规项）
import os, re, glob
ROOT = os.path.abspath("MYONL引擎")  # 在 D:\娱乐工作区\自研项目 下运行
for f in sorted(glob.glob(os.path.join(ROOT, "*.md"))):
    b = open(f, "rb").read()
    text = b.decode("utf-8", errors="replace")
    bad = []
    if b.count(b"\r\n") > 0:
        bad.append("CRLF")
    if text.endswith((" ", "\t")):
        bad.append("TAIL")
    if not text.endswith("\n"):
        bad.append("NO-EOL")
    in_code, h1 = False, 0
    for ln in text.split("\n"):
        if ln.strip().startswith("```"):
            in_code = not in_code
        elif not in_code and re.match(r"^# ", ln):
            h1 += 1
    if h1 != 1:
        bad.append(f"H1={h1}")
    if bad:
        print(os.path.basename(f), ",".join(bad))
print("扫描完成")
```

## 4. 适用范围

- 项目根 `*.md`（含 P 系列规划、交付变更说明、任务单、指南、报告）。
- 子目录（games/、engine/ 等）内如出现 .md 同样适用。
- 例外：素材源文件（.txt/.gal）不适用本文档。
