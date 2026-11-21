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
    assert "return max(0, v)" in src, "显式 0 表示这类全清；没传时用默认值（安卓 3 / Windows 1）"
    assert '"DELETE"' in src and "/git/refs/tags/" in src, "删 Release 之后还要删 tag"
    assert 'v1\\.0\\.0-rc' in src, "Windows 发行候选也要能清，两类各自按数字排"
    # 真删那段曾经写成 for n, r in doomed（doomed 里是 dict）—— dry-run 全绿、一 --yes 就崩
    assert "for n, r in doomed" not in src, "doomed 里是 Release 字典，别按 (编号, 字典) 解包"


def test_清理脚本默认不动手():
    src = _read("tools", "gh_release_clean.py")
    assert "args.dry_run or not args.yes" in src, "没有 --yes 一律只说不做"
    # dry-run 不需要 token：先给出"会删谁"，再说没 token 删不了
    assert src.index("args.dry_run or not args.yes") < src.index('if not token:'), "dry-run 不能卡在 token 检查后面"


def test_CI_发完包自己清旧包():
    wf = _read(".github", "workflows", "android-apk.yml")
    assert "只保留最近 3 个安卓包" in wf, "CI 要在发 Release 之后清旧包"
    assert re.search(r"^\s+KEEP=3\s*$", wf, re.M), "保留数写死 3，别跟脚本默认值漂移"
    assert "continue-on-error: true" in wf, "清理失败不能把已经发好的包判红"
    assert "--cleanup-tag" in wf, "删 Release 要连 tag 一起删，否则 tag 残留像新包"
    assert re.search(r"sort -t- -k2 -n -r", wf), "CI 里也要按数字倒序，别按字符串"


_DOWNLOAD_RE = re.compile(r"releases/download/((?:apk-\d+)|(?:v\d+\.\d+\.\d+))/MYONL-\1\.apk")
_README_EN = os.path.join(ROOT, "README.en.md")
# 英文版 2026-11-21 停维护并删除。文件不在了就不再守它；哪天恢复了，这两条自动继续生效。
_NEEDS_EN = pytest.mark.skipif(not os.path.exists(_README_EN), reason="英文版已停维护")


def _tag_of(readme: str):
    m = _DOWNLOAD_RE.search(readme)
    return m.group(1) if m else None


@_NEEDS_EN
@pytest.mark.parametrize("path", ["README.md", "README.en.md"])
def test_README_指向的是当前最新的包(path):
    """有英文版的时候两份都要守：只校验中文那份，英文版就会悄悄指向旧包（P192 就是这么漏的：
    英文页下载链停在 v1.2.0，徽章写 v1.2.14，玩家点下载拿到十来个版本之前的东西）。"""
    readme = _read(path)
    tag = _tag_of(readme)
    assert tag, f"{path} 没有安卓包下载入口"
    assert f"release-{tag}" in readme, f"{path} 徽章里的版本号要和下载链接一致（链接是 {tag}）"


@_NEEDS_EN
def test_两份README的版本号必须一样():
    """发版只改一份、漏掉另一份，正是「徽章/下载链/实际能力三者不同步」的入口。"""
    zh, en = _tag_of(_read("README.md")), _tag_of(_read("README.en.md"))
    assert zh and en, "两份 README 都必须有下载入口"
    assert zh == en, f"中文 README 指向 {zh}，英文 README 指向 {en}，发版漏改一份"
