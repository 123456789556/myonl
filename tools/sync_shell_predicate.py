# -*- coding: utf-8 -*-
"""P258：手机壳判据「一条命令统一全部站点」。

判据（宽 ≤860 或 高 ≤520 或 触屏且宽 ≤1400）在仓库里有 35 处，分两种写法：
    CSS：`@media (max-width: 860px), (max-height: 520px), (pointer: coarse) and (hover: none) and (max-width: 1400px)`
    JS ：`"(max-width:860px), (max-height:520px), (pointer:coarse) and (hover:none) and (max-width:1400px)"`
（editor_home.js 那份是两行用 `+` 拼的，也算同一份说法。）

为什么要工具：P215 踩过 —— CSS 已经按手机壳排版、首页 JS 还按老判据 return，
结果是半手机半桌面（navCount=0）。改断点时人手去翻 35 处必漏。

用法：
    python tools/sync_shell_predicate.py            # 只报告：每处是标准写法还是野写法
    python tools/sync_shell_predicate.py --apply    # 把野写法统一成标准写法（会改文件）
退出码：0 = 全部一致；1 = 有不一致的（此时 --apply 能修）。

注意：真要改断点（比如 860→900），先改本文件的 W/H/W_TALL，再 --apply，
然后 pytest tests/test_p258_shell_predicate.py 会红，照着把 EXPECT 更新掉。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EDITOR = ROOT / "editor"

# 断点（唯一真源）
W = 860        # 窄屏宽
H = 520        # 矮屏高（横屏手机）
W_TALL = 1400  # 触屏再加一道宽度上限，挡住 2560×1600 那种大平板

CANON_CSS = "(max-width: %dpx), (max-height: %dpx), (pointer: coarse) and (hover: none) and (max-width: %dpx)" % (W, H, W_TALL)
CANON_JS = "(max-width:%dpx), (max-height:%dpx), (pointer:coarse) and (hover:none) and (max-width:%dpx)" % (W, H, W_TALL)

# 宽松匹配：任意空白 + 可选引号/加号续行，CSS 带空格、JS 不带空格两种都能命中
_SEP = r"[\s\"']*(?:\+[\s\"']*)?"
PATTERN = re.compile(
    r"\(\s*max-width\s*:\s*\d+px\s*\)\s*,"
    + _SEP + r"\(\s*max-height\s*:\s*\d+px\s*\)\s*,"
    + _SEP + r"\(\s*pointer\s*:\s*coarse\s*\)\s*and\s*"
    + r"\(\s*hover\s*:\s*none\s*\)\s*and\s*"
    + r"\(\s*max-width\s*:\s*\d+px\s*\)"
)


def sources() -> list[Path]:
    return sorted(p for p in EDITOR.rglob("*") if p.suffix in (".css", ".js", ".html"))


def desired(path: Path) -> str:
    return CANON_CSS if path.suffix == ".css" else CANON_JS


def _numbers(s: str) -> str:
    """把一处判据压成「只留数字」的指纹：改断点时漏掉的那处，指纹就对不上。"""
    return ",".join(re.findall(r"\d+", s))


WANT_FP = _numbers(CANON_JS)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="把野写法改写成标准写法（会改文件）")
    args = ap.parse_args()

    stale = 0        # 断点数字与真源不一致 —— 这才是会出事的
    unstyled = 0     # 数字对但写法乱（引号/空格/加号续行）—— 只是不好看
    total_sites = 0
    for p in sources():
        text = p.read_text(encoding="utf-8")
        want = desired(p)
        hits = list(PATTERN.finditer(text))
        if not hits:
            continue
        total_sites += len(hits)
        rel = str(p.relative_to(ROOT)).replace("\\", "/")
        bad_fp = [h.group(0) for h in hits if _numbers(h.group(0)) != WANT_FP]
        off = [h.group(0) for h in hits if h.group(0) != want]
        tag = "OK  "
        if bad_fp:
            tag = "断点不一致"
            stale += 1
        elif off:
            tag = "写法不标准"
            unstyled += len(off)
        print("%-30s %2d 处  %s" % (rel, len(hits), tag))
        for o in bad_fp[:3]:
            print("      实际: %r" % (" ".join(o.split()))[:140])
        if bad_fp:
            print("      应为: %r" % (want,))
        if args.apply and off:
            p.write_text(PATTERN.sub(want, text), encoding="utf-8")
            print("      -> 已统一成标准写法（%d 处）" % len(off))

    print("")
    print("合计 %d 处；断点与真源不一致的文件 %d 个；写法不统一 %d 处" % (total_sites, stale, unstyled))
    if stale:
        print("这些地方的断点跟真源（%d / %d / %d）对不上，先 --apply 修掉再说。" % (W, H, W_TALL))
    elif unstyled and not args.apply:
        print("数字全对，只是写法有空格/引号差异；想统一就加 --apply（不影响行为）。")
    return 0 if stale == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
