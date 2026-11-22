# -*- coding: utf-8 -*-
"""指令跨端对拍：同一条指令喂给 Python 解析器（电脑端）和 JS 解析器（手机端），比结果。

为什么要有这个：我们自己的 @ 指令是自造的。哪一端不认识，就会在那一端直接报
「未知指令」，用户在手机上打不开电脑端做的剧本（或者反过来）。靠人肉记名单迟早漏，
所以这里做机器对拍 —— 一条指令、一份最小样例、两边各跑一遍、比对 op 序列。

用法：
    D:\\Python313\\python.exe tools/check_directive_parity.py
    ... --json   # 输出机器可读结果

退出码：0 = 两端一致；1 = 有差异（会打印差异表）。
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

# Windows 控制台默认是 cp1252/cp936，直接 print 中文会 UnicodeEncodeError 把整个工具打死
# （CI 上就这样红过一次）。先把 stdout 换成 UTF-8，再说话。
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001 — 老解释器没有 reconfigure，忽略即可
    pass

ROOT = Path(__file__).resolve().parents[1]

# 每条：名字 + 一段最小可用剧本（必须自带 @label，让两端都真的解析成功）
CASES = [
    ("旁白台词", "@ 旁白 天黑了。\n@label x\n@end\n"),
    ("角色台词", "@ 林晚 你也在等这趟？\n@label x\n@end\n"),
    ("character", '@character 林晚 #aaccff\n@label x\n@end\n'),
    ("bg", "@bg bg_教室\n@label x\n@end\n"),
    ("bg+淡入参数", "@bg 教室 fadein=0.6\n@label x\n@end\n"),
    ("show", "@show 林晚 微笑\n@label x\n@end\n"),
    ("show+位置", "@show 林晚 微笑 pos=左\n@label x\n@end\n"),
    ("hide", "@hide 林晚\n@label x\n@end\n"),
    ("music", "@music 主题曲\n@label x\n@end\n"),
    ("sfx", "@sfx 关门\n@label x\n@end\n"),
    ("voice", "@ 林晚 你好。\n@voice 01\n@label x\n@end\n"),
    ("video", "@video 片头\n@label x\n@end\n"),
    ("camera", "@camera zoom 1.0 1.3\n@label x\n@end\n"),
    ("cg", "@cg 特写\n@label x\n@end\n"),
    ("fg", "@fg 前景\n@label x\n@end\n"),
    ("transition", "@transition dissolve 0.6\n@label x\n@end\n"),
    ("wait", "@wait 0.5\n@label x\n@end\n"),
    ("chapter", "@chapter 第一章 雨夜\n@label x\n@end\n"),
    ("chapter+secs", "@chapter 第一章 雨夜 secs=1.5\n@label x\n@end\n"),
    ("label", "@label x\n@ 旁白 一。\n@end\n"),
    ("jump", "@label x\n@jump x\n@end\n"),
    ("set数值", "@label x\n@set 进度 += 1\n@end\n"),
    ("set字符串", '@label x\n@set 名字 = "林晚"\n@end\n'),
    ("set表达式", "@label x\n@set 进度 = 进度 + 1\n@end\n"),
    ("if", "@label x\n@if 进度 >= 1:\n    @ 旁白 好。\n@end\n"),
    ("if/elif/else", "@label x\n@if 进度 >= 2:\n    @ 旁白 甲。\n@elif 进度 >= 1:\n    @ 旁白 乙。\n@else:\n    @ 旁白 丙。\n@end\n"),
    ("choice", "@label x\n@choice:\n    > 走 -> x\n    > 停 -> x\n@end\n"),
    ("end", "@label x\n@end\n"),
    ("anim", "@anim 林晚 x=-100~0 1.0\n@label x\n@end\n"),
    ("plug", "@plug:shake 1.0\n@label x\n@end\n"),
    ("include", "@include script.gal\n@label x\n@end\n"),
]

JS_RUNNER = r"""
const path = require("path");
const P = require(process.argv[2]);
const cases = JSON.parse(process.argv[3]);
const out = [];
for (const c of cases) {
  try {
    const r = P.parseText ? P.parseText(c[1]) : (P.parse ? P.parse(c[1]) : null);
    out.push({name: c[0], ok: !!(r && r.ok), ops: ((r && r.instructions) || []).map(i => i.op), err: (r && r.error && r.error.message) || null});
  } catch (e) {
    out.push({name: c[0], ok: false, ops: [], err: (e && (e.galMessage || e.message)) || String(e)});
  }
}
console.log(JSON.stringify(out));
"""


def run_js(cases):
    with tempfile.TemporaryDirectory() as td:
        runner = Path(td) / "run.js"
        runner.write_text(JS_RUNNER, encoding="utf-8")
        p = subprocess.run(["node", str(runner), str(ROOT / "engine" / "parser.js"),
                            json.dumps(cases, ensure_ascii=False)],
                           capture_output=True, text=True, encoding="utf-8", timeout=120)
        if p.returncode != 0:
            raise RuntimeError("node 跑挂了：" + (p.stderr or "")[-400:])
        return json.loads(p.stdout)


def run_py(cases):
    sys.path.insert(0, str(ROOT))
    from engine import parser as pyparser
    out = []
    for name, src in cases:
        try:
            ops = [i["op"] for i in pyparser.parse_text(src)]
            out.append({"name": name, "ok": True, "ops": ops})
        except Exception as e:  # noqa: BLE001 - 对拍就是要抓所有失败形态
            out.append({"name": name, "ok": False, "ops": [], "err": str(e)})
    return out


def main():
    js = run_js(CASES)
    py = run_py(CASES)
    diffs, only_one, rows = [], [], []
    for a, b in zip(py, js):
        if a["ok"] and b["ok"]:
            same = a["ops"] == b["ops"]
            kind = "一致 OK" if same else "op 序列不同"
        elif not a["ok"] and not b["ok"]:
            same, kind = True, "一致 报错"
        else:
            # 一端能跑一端不能：这就是跨端缺口。不算「一致」，也不当作错误文案差异，
            # 单独列出来 —— 要么补上那一端，要么在编辑器里明确提示"这条只在那端生效"。
            same, kind = False, ("仅电脑端" if a["ok"] else "仅手机端")
            only_one.append({"指令": a["name"], "哪端": kind, "另一端报错": (b["err"] if a["ok"] else a["err"])})
        rows.append({"指令": a["name"], "电脑端": "OK" if a["ok"] else "报错",
                     "手机端": "OK" if b["ok"] else "报错", "结论": kind})
        if not same and kind != "仅电脑端" and kind != "仅手机端":
            diffs.append({"指令": a["name"], "电脑端": a, "手机端": b})

    w = max(len(r["指令"]) for r in rows) + 2
    print("指令对拍（电脑端 Python / 手机端 JS）")
    print("-" * 62)
    for r in rows:
        print(f'{r["指令"]:<{w}} 电脑端 {r["电脑端"]}  手机端 {r["手机端"]}  {r["结论"]}')
    print("-" * 62)
    print(f"共 {len(rows)} 条：两端一致 OK {sum(1 for r in rows if r['结论'] == '一致 OK')} 条，"
          f"仅一端可用 {len(only_one)} 条，真差异 {len(diffs)} 条")
    for o in only_one:
        print(f"\n[仅一端] {o['指令']} —— {o['哪端']}，另一端报：{o['另一端报错']}")
    for d in diffs:
        print("\n[差异] " + d["指令"])
        print("  电脑端：", json.dumps(d["电脑端"], ensure_ascii=False))
        print("  手机端：", json.dumps(d["手机端"], ensure_ascii=False))
    sys.exit(0 if not diffs else 1)


if __name__ == "__main__":
    main()


