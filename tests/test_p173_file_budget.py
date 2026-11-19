# -*- coding: utf-8 -*-
"""P173：单文件体积预算 —— 只许降，不许涨。

为什么有这一条：引擎已经长到 `editor_main.js` 3394 行、`editor.py` 2992 行、
`editor.css` 3322 行。这类文件继续膨胀的代价不是「看着烦」：

- 改一处要通读全篇，改错的风险随行数线性涨；
- 测试失败时定位不到是哪块逻辑，只能 grep；
- 新人（包括以后的我自己）不敢动，于是所有新功能继续往同一个文件里塞，越滚越大。

所以把**今天每个大文件的行数**记成天花板。任何一次提交让某个文件比记录更高，
这条就红 —— 逼着要么拆，要么把新东西放到新文件里。

怎么降：拆出去之后把数字跟着往下调。**不许往上调**，
涨了说明又往老文件里塞东西了，那不是"这次特殊"，那是没守规矩。

参考线（不是硬指标，是提醒）：
    800 行   —— 一个模块还看得完
    1500 行  —— 开始需要目录/分节注释才能导航
    3000 行  —— 已经到了该拆的地步
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

ROOT = Path(__file__).resolve().parents[1]

# 上限 = 记账当天的实际行数 + 一点注释余量。降了要跟着降。
#
# 唯一允许的例外：新增确实是修复所必需（比如版面错位非加几行 CSS 不可）。
# 那时候调高上限可以，但必须做到两件事：
#   1) 提交信息里写清为什么涨、涨了几行；
#   2) 先找过"能不能顺手删掉等价行数"——找不到才涨。
# 不许做的：为了让自己这次的提交变绿，把上限一把抬高几十行。那这条测试就白设了。
FILE_BUDGET: dict[str, int] = {
    "editor/editor_main.js": 3400,
    "editor/editor_pro.js": 2160,
    "editor/editor_uidesign.js": 1520,
    "editor/gal_offline.js": 1580,
    "editor/editor_scene.js": 1215,  # P175 背景缺失占位 +5 行（修复用户提过的空白预览）
    "editor/editor_shell.js": 870,
    "editor/editor.css": 3330,   # 回滚 P177 模式改动，从 3340 降回 3330
    "engine/editor.py": 3000,
    "engine/parser.py": 1080,
}


def _lines(p: Path) -> int:
    return len(p.read_text(encoding="utf-8").splitlines())


def test_大文件不超预算():
    """超预算 = 又往老文件里堆了东西。要加功能就加在新文件里。"""
    over: list[str] = []
    for rel, cap in FILE_BUDGET.items():
        f = ROOT / rel
        assert f.is_file(), f"预算表里的文件不存在了：{rel}（改名或删了要同步这张表）"
        n = _lines(f)
        if n > cap:
            over.append(f"{rel} {n} 行 > 预算 {cap}（超 {n - cap} 行）")
    assert not over, (
        "文件超预算，只许降不许涨：\n  " + "\n  ".join(over)
        + "\n正确做法：把新增逻辑放进新文件；或者先把这块拆出去再降预算数字。"
    )


def test_预算表里的路都真实存在():
    """防呆：预算表写错路径会静默放过（上面那条已经断言，这里再单拎出来说明后果）。"""
    missing = [rel for rel in FILE_BUDGET if not (ROOT / rel).is_file()]
    assert not missing, f"预算表指向了不存在的文件：{missing}"
