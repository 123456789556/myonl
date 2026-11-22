# -*- coding: utf-8 -*-
"""把 README 的 release 徽章同步到 engine/_version.py 的 VERSION。

为什么需要它：README 的徽章一度停在 v1.2.28，而 Release 已经发到 v1.2.39 ——
中间 11 个版本没人改那一行。徽章是静态 markdown，没法自动取真源，
所以发版时跑一次这个脚本，把它写对。

用法：
    py -3 tools/sync_readme_version.py          # 改写 README.md
    py -3 tools/sync_readme_version.py --check  # 只检查，不一致返回 1

发版铁律（四步，缺一不可）：
    1. 改 engine/_version.py 的 VERSION
    2. py -3 tools/sync_readme_version.py
    3. 提交
    4. 打同名 tag 并 push（tag 与 VERSION 不一致，CI 直接红）
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
BADGE = re.compile(r"(img\.shields\.io/badge/release-v)([0-9]+\.[0-9]+\.[0-9]+)(-blue)")
# 「装它」那一段是写死版本号的直链（tests/test_p100 守着「徽章和下载链同一个包」），
# 所以徽章和直链必须一起改，只改一个就会红。
DL = re.compile(r"(releases/download/v)([0-9]+\.[0-9]+\.[0-9]+)(/MYONL-v)([0-9]+\.[0-9]+\.[0-9]+)")
DL_NAME = re.compile(r"(⬇ 下载 MYONL-v)([0-9]+\.[0-9]+\.[0-9]+)")


def real_version() -> str:
    text = (ROOT / "engine" / "_version.py").read_text(encoding="utf-8")
    m = re.search(r'^VERSION\s*=\s*"([^"]+)"', text, re.M)
    if not m:
        raise SystemExit("读不出 engine/_version.py 的 VERSION")
    return m.group(1)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="同步 README release 徽章")
    ap.add_argument("--check", action="store_true", help="只检查不改写")
    args = ap.parse_args(argv)

    ver = real_version()
    text = README.read_text(encoding="utf-8")
    m = BADGE.search(text)
    if not m:
        print("README 里找不到 release 徽章", file=sys.stderr)
        return 2

    def synced(s: str) -> str:
        s = BADGE.sub(lambda g: g.group(1) + ver + g.group(3), s)
        s = DL.sub(lambda g: g.group(1) + ver + g.group(3) + ver, s)
        return DL_NAME.sub(lambda g: g.group(1) + ver, s)

    new = synced(text)
    if new == text:
        print("README 徽章与下载链已是 v%s" % ver)
        return 0
    if args.check:
        print("README 的徽章/下载链与真源 v%s 不一致" % ver, file=sys.stderr)
        return 1
    README.write_text(new, encoding="utf-8")
    print("README 徽章与下载链 → v%s（原徽章 v%s）" % (ver, m.group(2)))
    return 0


if __name__ == "__main__":
    sys.exit(main())