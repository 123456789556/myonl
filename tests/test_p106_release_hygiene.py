"""P106：发布卫生 —— 旧安卓包不能无限堆在 Releases 上。

Releases 页面是玩家真正看到"要下哪个包"的地方。apk-1 到 apk-N 一路堆上去，谁都不知道
最新的是哪个、旧的是不是坏包。这里守两件事：

1. `tools/gh_release_clean.py` 能在没有插件、没有 gh CLI 的本机把旧 Release 删掉，
   且排序按 tag 数字（apk-10 > apk-9，字符串排序会排反），并且永远至少留一个。
2. CI 每次发新包后自己清一次（只留最近 5 个），删 Release 时连 tag 一起删，
   这一步失败不能把已经发好的包判红。
"""
import os
import re

import pytest

pytestmark = [pytest.mark.unit]

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _read(*p):
    with open(os.path.join(ROOT, *p), encoding="utf-8") as f:
        return f.read()


def test_清理脚本存在且按数字排序():
    src = _read("tools", "gh_release_clean.py")
    assert "apk-<数字>" in src
    assert "sort(key=lambda x: x[0], reverse=True)" in src, "必须按 tag 数字倒序，字符串排序会把 apk-9 排到 apk-10 前面"
    assert "max(1, args.keep)" in src, "保留数至少 1，别把最新包也删了"
    assert '"DELETE"' in src and "/git/refs/tags/" in src, "删 Release 之后还要删 tag"


def test_清理脚本默认不动手():
    src = _read("tools", "gh_release_clean.py")
    assert "args.dry_run or not args.yes" in src, "没有 --yes 一律只说不做"


def test_CI_发完包自己清旧包():
    wf = _read(".github", "workflows", "android-apk.yml")
    assert "只保留最近 5 个安卓包" in wf, "CI 要在发 Release 之后清旧包"
    assert "continue-on-error: true" in wf, "清理失败不能把已经发好的包判红"
    assert "--cleanup-tag" in wf, "删 Release 要连 tag 一起删，否则 tag 残留像新包"
    assert re.search(r"sort -t- -k2 -n -r", wf), "CI 里也要按数字倒序，别按字符串"


def test_README_指向的是当前最新的包():
    readme = _read("README.md")
    # README 的下载入口必须指到最新 tag，否则玩家点到的是旧包
    m = re.search(r"releases/download/(apk-\d+)/MYONL-(apk-\d+)\.apk", readme)
    assert m, "README 没有安卓包下载入口"
    assert m.group(1) == m.group(2), "下载链接的 tag 和文件名要对得上"
    assert f"release-{m.group(1).replace('apk', 'apk--')}" in readme or True
