# -*- coding: utf-8 -*-
"""P258：`.myonl` 单作品包的版本门。

包格式现在是 `{myonl:"proj", v:1, name, text, ctime, mtime, assets, audio, movies, kinds}`。
写出去永远是 v:1；但**读**要有门：等到 v2 加了新字段（素材笔记、章节树）那天，
旧版设备直接把包吞下去会静默丢字段 —— 那种 bug 用户只会说「导进来少了一半」，
查起来要命。所以认不出的版本必须当场说清，不许假装导入成功。

这里守三件事：
  1. 导出的包仍然写 v:1（写端没有偷偷升版本）；
  2. 读端有门：v > 1 时明确报「更新版本导出」，并且直接返回（不走导入）；
  3. 门在 importText 的分派之前 —— 门放在分派之后（比如放在 importProj 里）就等于没门，
     因为那时已经按旧格式建好作品了。
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

ROOT = Path(__file__).resolve().parents[1]
EXPORT_JS = ROOT / "editor" / "mobile" / "editor_export.js"


def _text() -> str:
    return EXPORT_JS.read_text(encoding="utf-8")


def test_writer_keeps_v1() -> None:
    text = _text()
    # 三处写包的地方（导出单作品 / 桌面导入回写 / 合并回写）都必须是 v: 1
    assert text.count('myonl: "proj", v: 1') >= 3, "写包的地方少了，或者版本号被改了：%d 处" % text.count('myonl: "proj", v: 1')


def test_reader_has_version_gate() -> None:
    text = _text()
    assert "Number(obj.v || 1) > 1" in text, "读端没有版本门：更新版本的包会被静默吞掉"
    assert "更新版本（v" in text, "版本门要把话说清楚，不能只 return"


def test_gate_before_dispatch() -> None:
    text = _text()
    gate = text.index("Number(obj.v || 1) > 1")
    dispatch = text.index('if (obj && obj.myonl === "proj") return deskOn()')
    assert gate < dispatch, "版本门在分派之后 = 没门（那时已经按旧格式建好作品了）"


def test_gate_is_documented() -> None:
    text = _text()
    assert "P258 包版本门" in text, "门旁边要留一句为什么，不然后人当它是多余代码删掉"
