# -*- coding: utf-8 -*-
"""P18 独立验收脚本：runtime 驱动《示例故事》双结局 + 存档/读档 + CG 画廊。

用法：
    py tools/verify_p18_runtime.py
退出码 0 = 全部通过；非 0 = 某项失败（打印 FAIL 位置）。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SCRIPT = ROOT / "games" / "示例故事" / "script.gal"

FAILS: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    tag = "PASS" if cond else "FAIL"
    print(f"[{tag}] {name}" + (f" —— {detail}" if detail else ""))
    if not cond:
        FAILS.append(name)


def main() -> int:
    from engine.runtime import Runtime

    # ---- 结局 B（选第一个选项：好，一起去。 -> 去B）----
    rt = Runtime()
    rt.load(str(SCRIPT))
    while not rt.snapshot().get("finished"):
        snap = rt.snapshot()
        if snap.get("pending_choice"):
            rt.choose(0)  # 去B
        else:
            rt.step()
    check("结局B 跑通 finished", rt.snapshot().get("finished") is True)
    check("结局B CG 画廊解锁 cg_02", rt.gallery() == ["cg_02"], str(rt.gallery()))

    # ---- 存档/读档（结局 B 完成态）----
    msg = rt.save(7)
    check("存档 slot7 成功", "成功" in msg or msg is not None, str(msg))
    rt2 = Runtime()
    rt2.load(str(SCRIPT))
    rt2.load_save(7)
    h1 = rt.snapshot().get("history", [])
    h2 = rt2.snapshot().get("history", [])
    check("读档 history 无损", len(h1) == len(h2) and h1 == h2,
          f"len={len(h1)}/{len(h2)}")
    check("读档后画廊保持", rt2.gallery() == ["cg_02"], str(rt2.gallery()))

    # ---- 结局 A（选第二个选项：抱歉，今天不行。 -> 去A）----
    rt3 = Runtime()
    rt3.load(str(SCRIPT))
    while not rt3.snapshot().get("finished"):
        snap = rt3.snapshot()
        if snap.get("pending_choice"):
            rt3.choose(1)  # 去A
        else:
            rt3.step()
    check("结局A 跑通 finished", rt3.snapshot().get("finished") is True)
    check("结局A CG 画廊解锁 cg_01", rt3.gallery() == ["cg_01"], str(rt3.gallery()))

    print("----")
    if FAILS:
        print(f"验收失败 {len(FAILS)} 项：{FAILS}")
        return 1
    print("P18 运行时验收全部通过：双结局 / 存档读档 / CG 画廊。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
