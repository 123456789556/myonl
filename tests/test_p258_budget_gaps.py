# -*- coding: utf-8 -*-
"""P258：把「不在预算表里的热文件」收进预算，并给每个区加总量上限。

诊断（P258 评价时说的那句「增长模型病态」）：
  `test_p173_file_budget.py` 的表是一张**冻结名单**——表里的文件只许降，
  于是新功能全被塞进「不在表里」的文件：`editor/mobile/` 9 个文件一天里从几百行滚到
  5222 行，`web/myonl-player.js` 长到 4160 行且从来没进过任何预算。
  「只许降」保护了老文件，却把增长赶到看不见的地方去了。

这里补两条：
  1. **单文件上限**：这些后面的热文件各自封顶（= 记账当天的行数）。
  2. **区总量上限**：`editor/mobile/` 与 `web/` 整体封顶。允许区内搬行（A 涨 B 降），
     但区总账不许涨 —— 这样「拆文件」不再是免检通道。

红了怎么办：
  - 真需要加行 → 先在同一个区里删掉等量行（区总量没涨就放行）；
  - 区总量也必须涨 → 那说明是新增能力，不是搬行：改下面的数字，并在提交信息里写清
    「涨了几行、涨在哪、为什么这次非涨不可」。
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

ROOT = Path(__file__).resolve().parents[1]

# 记账日期：2026-11-22（P258）。数字 = 当天实测行数。
HOT_FILES: dict[str, int] = {
    "web/myonl-player.js": 4203,          # P274 @anim 缓动曲线 22 条（照 timeline.py 公式抄，+43，4160→4203）；全仓最大代码文件
    "editor/mobile/editor_home.js": 1294,  # 首页 + 作品卡 + 上下文菜单的调用点
    "editor/mobile/editor_mobile.js": 713,
    "editor/mobile/editor_trash.js": 676,  # P257 一天内 131→676
    "editor/mobile/editor_export.js": 653,
    "editor/mobile/ui-layout.css": 647,
    "editor/mobile/home.css": 348,
    "editor/mobile/ui_layout.js": 643,   # P276 竖横排合一枚「当前方向 ⇄」+7（636→643）；  # P275 撤顶栏缩放三颗 + 空白处点两下回全局 +7（629→636）；P267 竖横排 + 小总览 +45；P265 蓝图式流程图 + 页头并进顶栏 +270（新文件接线面大，故放这里）
    "editor/mobile/editor_dialog.js": 157,
    "web/myonl-core.js": 413,   # P274 补间记录带 ease（+1）
    "web/myonl-layout.js": 150,
    "editor/editor_characters.js": 409,
    "editor/editor_snapshots.js": 242,
    "editor/editor_link.js": 179,
    "engine/webpack.py": 947,
}

# 区总量：允许区内互相搬行，区总不许涨。
AREA_CAP: dict[str, int] = {
    "editor/mobile": 5673,   # P276 ui_layout +7（见上）   # P275 ui_layout.js +7（见上）
    "web": 4766,   # P274 @anim 缓动 +44（player +43 / core +1），从 4722 涨到 4766
}

# 超过这个行数的 js/css 必须出现在某张预算表里，不许有「没人管的巨型文件」。
BIG_FILE_LINES = 400


def _lines(p: Path) -> int:
    return len(p.read_text(encoding="utf-8", errors="ignore").splitlines())


def _area_total(prefix: str) -> int:
    total = 0
    for p in ROOT.glob(prefix + "/*"):
        if p.is_file() and p.suffix in (".js", ".css"):
            total += _lines(p)
    return total


def _area_of(rel: str) -> str:
    if rel.startswith("web/"):
        return "web"
    if rel.startswith("editor/mobile/"):
        return "editor/mobile"
    return ""   # 不在任何有区总量上限的区里：只管自己那一行上限


@pytest.mark.parametrize("rel,cap", sorted(HOT_FILES.items()))
def test_hot_file_cap(rel: str, cap: int) -> None:
    p = ROOT / rel
    assert p.is_file(), "%s 不见了（挪走/改名就要同步这张表）" % rel
    n = _lines(p)
    if n <= cap:
        return
    area = _area_of(rel)
    if not area:
        assert False, "%s 涨到 %d 行，上限 %d（+%d）—— 这张表只许降。" % (rel, n, cap, n - cap)
    atotal = _area_total(area)
    assert atotal <= AREA_CAP[area], (
        "%s 涨到 %d 行（上限 %d），而且 %s 区总量 %d 也超了上限 %d —— 这不是搬行，是净增。"
        "要么在本区删掉等量行，要么改表并说明为什么非涨不可。" % (rel, n, cap, area, atotal, AREA_CAP[area])
    )


@pytest.mark.parametrize("area,cap", sorted(AREA_CAP.items()))
def test_area_total_cap(area: str, cap: int) -> None:
    got = _area_total(area)
    assert got <= cap, "%s 区总量 %d 行，超上限 %d（+%d）—— 区内搬行可以，净增不行。" % (
        area, got, cap, got - cap)


def test_no_giant_file_outside_budget() -> None:
    """任何一个 >400 行的 js/css，必须能在两张预算表里找到名字。"""
    from tests.test_p173_file_budget import FILE_BUDGET

    known = set(FILE_BUDGET) | set(HOT_FILES)
    stray = []
    for p in list((ROOT / "editor").rglob("*.js")) + list((ROOT / "editor").rglob("*.css")) + list((ROOT / "web").glob("*.js")):
        if _lines(p) > BIG_FILE_LINES:
            rel = str(p.relative_to(ROOT)).replace("\\", "/")
            if rel not in known:
                stray.append("%s(%d)" % (rel, _lines(p)))
    assert not stray, "这些大文件不在任何预算表里（又会变成没人看管的黑洞）：%r" % (stray,)
