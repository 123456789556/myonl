# -*- coding: utf-8 -*-
"""P258：手机壳判据「只许有一份说法」的守卫。

问题：这条判据在仓库里散着，而且**两种写法**——
    CSS：`@media (max-width: 860px), (max-height: 520px), (pointer: coarse) …`（带空格，27+ 处）
    JS ：`"(max-width:860px), (max-height:520px), (pointer:coarse) …"`（不带空格，5 处）
只要有人改一处（比如把 860 调成 900）而没改完全部，就会出现「CSS 按手机排版、
JS 还按旧宽度判断」的半手机半桌面怪胎 —— P215 已经踩过一次（navCount=0）。

这条测试不做重写，只做**冻结计数**：总数一旦变化就红，逼着改的人当场把每一处都数清楚。
红了怎么处理：
  1) 确定是「新加了一处手机壳样式」→ 更新下面的 EXPECT，并在提交信息里写清加在哪；
  2) 检查是不是手打了新变体 → 用 `tools/sync_shell_predicate.py` 统一回标准串。

判据发生变化（真的改断点）时，改 `tools/sync_shell_predicate.py` 里的 CANON 然后
`python tools/sync_shell_predicate.py --apply` 一次性重写全部站点，再更新这里的 EXPECT。
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

ROOT = Path(__file__).resolve().parents[1]
EDITOR = ROOT / "editor"

# 标准串（去掉所有空白/引号/加号/续行符之后的样子）——
# 这样「一行写完」和「两行用 + 拼起来」（editor_home.js 就是这么写的）算同一份说法。
CANON = "(max-width:860px),(max-height:520px),(pointer:coarse)and(hover:none)and(max-width:1400px)"

STRIP_CHARS = set(" \t\r\n\"'+\\")

# 冻结计数：= 记账当天的实际处数。只许降，涨了要先想清楚为什么。
EXPECT = {
    "editor/editor.css": 27,
    "editor/editor_main.js": 3,
    "editor/editor_shell.js": 1,
    "editor/index.html": 1,
    "editor/mobile/editor_home.js": 1,
    "editor/mobile/editor_mobile.js": 1,
    "editor/mobile/ui_polish.js": 1,
    "editor/strip.css": 1,
    "editor/ui-fix.css": 3,
}
EXPECT_TOTAL = 39

# 允许「提到 860 但不是整串」的文件白名单（都是有意只取半条的局部判断）。
# 有新文件出现在这里 = 有人又手打了一份断点，先问清楚再决定是合并还是登记。
LOOSE_OK = {
    "editor/editor.css",
    "editor/editor_main.js",
    "editor/editor_find.js",
    "editor/editor_shell.js",
    "editor/index.html",
    "editor/strip.css",
    "editor/ui-fix.css",
    "editor/mobile/editor_home.js",
    "editor/mobile/editor_mobile.js",
    "editor/mobile/ui_polish.js",
}


def _norm(text: str) -> str:
    return "".join(ch for ch in text if ch not in STRIP_CHARS)


def _sources() -> list[Path]:
    return sorted(p for p in EDITOR.rglob("*") if p.suffix in (".css", ".js", ".html"))


def _counts() -> dict[str, int]:
    out: dict[str, int] = {}
    for p in _sources():
        n = _norm(p.read_text(encoding="utf-8", errors="ignore")).count(CANON)
        if n:
            out[str(p.relative_to(ROOT)).replace("\\", "/")] = n
    return out


def test_shell_predicate_count_is_frozen() -> None:
    got = _counts()
    assert got == EXPECT, "手机壳判据的分布变了：实际 %r，期望 %r。涨了要说清加在哪，降了就把期望跟着降。" % (got, EXPECT)


def test_shell_predicate_total() -> None:
    assert sum(_counts().values()) == EXPECT_TOTAL


def test_no_new_hand_typed_breakpoint() -> None:
    """每个提到 max-width:860 的文件都必须是登记过的；新面孔说明又手打了一份。"""
    offenders = []
    for p in _sources():
        rel = str(p.relative_to(ROOT)).replace("\\", "/")
        if "max-width:860" in _norm(p.read_text(encoding="utf-8", errors="ignore")) and rel not in LOOSE_OK:
            offenders.append(rel)
    assert not offenders, "这些文件里出现了手打的手机壳断点，先并入标准串或登记进 LOOSE_OK：%r" % (offenders,)


def test_sync_tool_exists_and_matches() -> None:
    """重写工具必须在，且它里面的标准串与本测试一致（免得工具把判据改成另一个值）。"""
    tool = ROOT / "tools" / "sync_shell_predicate.py"
    assert tool.is_file(), "tools/sync_shell_predicate.py 不见了"
    assert CANON in _norm(tool.read_text(encoding="utf-8")), "工具里的标准串与本测试不一致"
