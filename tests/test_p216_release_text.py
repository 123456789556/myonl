# -*- coding: utf-8 -*-
"""P216：对外文字不许与磁盘脱节。

抓到的真实脱节：
- README 的 release 徽章停在 v1.2.28，而 Release 已经到 v1.2.39（差 11 个版本）。
- 两条发版流水线都往同一个 Release 写 name/body，却写得不一样：
  谁后跑完谁覆盖，页面上的标题与说明会来回翻烧饼。
- Release 正文里还写着「这一版只做了安卓」「平板…没专门适配过大屏」「把 .gal 导出带走」，
  三条都已过期（exe 已同发、大屏已适配、备份格式已是 .myonl）。
"""
from __future__ import annotations

import pathlib
import re

import pytest

pytestmark = [pytest.mark.unit]

ROOT = pathlib.Path(__file__).resolve().parents[1]
WF = ROOT / ".github" / "workflows"


def _norm(p: pathlib.Path) -> str:
    return p.read_text(encoding="utf-8").replace("\r\n", "\n")


def _version() -> str:
    m = re.search(r'^VERSION\s*=\s*"([^"]+)"', _norm(ROOT / "engine" / "_version.py"), re.M)
    assert m, "读不出真源 VERSION"
    return m.group(1)


def _release_block(text: str) -> str:
    i = text.index('name: "MYONL ${{ github.ref_name }}')
    j = text.index("files: out/", i)
    return text[i:j]


def test_README徽章与真源同版本():
    ver = _version()
    m = re.search(r"img\.shields\.io/badge/release-v([0-9.]+)-blue", _norm(ROOT / "README.md"))
    assert m, "README 没有 release 徽章"
    assert m.group(1) == ver, (
        "README 徽章 v%s 落后于真源 v%s —— 发版时跑 tools/sync_readme_version.py" % (m.group(1), ver)
    )


def test_两条流水线的Release文案逐字一致():
    a = _release_block(_norm(WF / "android-apk.yml"))
    b = _release_block(_norm(WF / "windows-exe.yml"))
    assert a == b, "两条流水线写同一个 Release 的 name/body，必须一字不差，否则谁后跑完谁覆盖"


def test_Release正文两个包都写到():
    body = _release_block(_norm(WF / "android-apk.yml"))
    assert ".apk" in body and "-editor-win.zip" in body
    assert ".myonl" in body, "跨端作品格式要写进 Release 说明"


def test_Release正文没有过期说法():
    body = _release_block(_norm(WF / "android-apk.yml"))
    for stale in ("这一版只做了安卓", "没专门适配过大屏", "把 `.gal` 导出带走"):
        assert stale not in body, "Release 正文还留着过期说法：" + stale


def test_README写清两端下载与互通():
    text = _norm(ROOT / "README.md")
    assert "-editor-win.zip" in text, "README 要写 Windows 包怎么拿"
    assert ".myonl" in text, "README 要写跨端作品格式"
    assert "engine/_version.py" in text, "README 要写版本号只有一个来源"