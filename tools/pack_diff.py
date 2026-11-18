# -*- coding: utf-8 -*-
"""对拍：同一份 .gal，Python 解析器与 JS 解析器的产出必须逐字段一致。

跑法：
    py -3 tools/pack_diff.py            # 只比对结果
    py -3 tools/pack_diff.py --dump 3   # 顺手打印第 3 条指令的两侧 JSON

不一致就是 JS 侧的 bug（Python 是基准，它已经被 1200 条测试和 5 个真实工程验证过）。
唯一允许忽略的字段是 file：JS 端单文件，没有跨文件定位。
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from engine import parser  # noqa: E402


def strip_file(ins):
    """递归去掉 file 字段（if.body / else_body / choice 也一样处理）。"""
    if isinstance(ins, list):
        return [strip_file(i) for i in ins]
    if not isinstance(ins, dict):
        return ins
    out = {k: strip_file(v) for k, v in ins.items() if k != "file"}
    return out


def canon(ins):
    return json.dumps(strip_file(ins), ensure_ascii=False, sort_keys=True)


def diff_at(a, b, where="根"):
    """返回第一个差异的人话描述；一致返回 None。"""
    if type(a) is not type(b):
        return f"{where}: 类型不同 Python={type(a).__name__} JS={type(b).__name__}"
    if isinstance(a, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a:
                return f"{where}: JS 多出字段 {k}={b[k]!r}"
            if k not in b:
                return f"{where}: JS 少了字段 {k}（Python={a[k]!r}）"
            d = diff_at(a[k], b[k], f"{where}.{k}")
            if d:
                return d
        return None
    if isinstance(a, list):
        if len(a) != len(b):
            return f"{where}: 条数不同 Python={len(a)} JS={len(b)}"
        for idx, (x, y) in enumerate(zip(a, b)):
            d = diff_at(x, y, f"{where}[{idx}]")
            if d:
                return d
        return None
    if a != b:
        return f"{where}: Python={a!r} JS={b!r}"
    return None


def main():
    games = sorted(p.parent for p in ROOT.glob("games/*/script.gal"))
    dump_idx = None
    if "--dump" in sys.argv:
        dump_idx = int(sys.argv[sys.argv.index("--dump") + 1])

    ok = fail = 0
    for g in games:
        f = g / "script.gal"
        text = f.read_text(encoding="utf-8-sig")
        py_ins = parser.parse_text(text, str(f))

        r = subprocess.run(
            ["node", str(ROOT / "tools" / "_pack_node.js"), str(f)],
            capture_output=True, text=True, encoding="utf-8", cwd=str(ROOT),
        )
        if r.returncode != 0:
            print(f"[FAIL] {g.name}: node 跑挂了\n{r.stderr[:400]}")
            fail += 1
            continue
        try:
            js = json.loads(r.stdout)
        except json.JSONDecodeError:
            print(f"[FAIL] {g.name}: node 输出不是 JSON\n{r.stdout[:200]}")
            fail += 1
            continue
        if not js.get("ok"):
            err = js.get("error") or {}
            print(f"[FAIL] {g.name}: JS 报错 第{err.get('line')}行 {err.get('message')}")
            fail += 1
            continue

        js_ins = strip_file(js["instructions"])
        py_ins = strip_file(py_ins)
        d = diff_at(py_ins, js_ins, g.name)
        if d:
            print(f"[FAIL] {g.name}: {d}")
            fail += 1
            continue
        ok += 1
        print(f"[ OK ] {g.name}  {len(py_ins)} 条  逐字段一致")

        if dump_idx is not None and dump_idx < len(py_ins):
            print("   Python:", canon(py_ins[dump_idx]))
            print("   JS    :", canon(js_ins[dump_idx]))

    print(f"\n{ok} 个一致 / {fail} 个不一致")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
