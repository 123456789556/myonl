# -*- coding: utf-8 -*-
"""P137-A4 守护：dbRun 事务中止时 Promise 必须 settle，不能挂死。

背景：IndexedDB 事务被 abort（配额满、约束冲突、并发写冲突）时只触发 abort
事件，不一定走 onerror。原 dbRun 只挂 oncomplete/onerror，onabort 无人接收，
Promise 既不 resolve 也不 reject，调用方（persistAsset/restore/remove/
importShared）一直 pending，界面进度卡在「导入中」，表现像卡死。

静态读源码断言 + node 语法门禁，不起浏览器、不联网。
"""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
OFFLINE = (ROOT / "editor" / "gal_offline.js").read_text(encoding="utf-8")
NODE = shutil.which("node")

pytestmark = [pytest.mark.unit]


def _db_run_block():
    i = OFFLINE.index("function dbRun(")
    j = OFFLINE.index("function dataUrlToResponse", i)
    return OFFLINE[i:j]


def test_dbRun挂了_onabort_分支():
    block = _db_run_block()
    assert "tx.onabort = function" in block, "dbRun 没监听事务中止事件"


def test_onabort必须reject而不是静默():
    block = _db_run_block()
    abort_i = block.index("tx.onabort = function")
    seg = block[abort_i:abort_i + 260]
    assert "rej" in seg, "onabort 分支没有 reject 通道"
    assert "素材库事务中止" in seg


def test_settle只能走一次():
    """onerror 与 onabort 可能先后触发，必须有一次性守卫，不能重复 settle。"""
    block = _db_run_block()
    assert "settled" in block
    assert "if (settled) return" in block


def test_oncomplete_onerror仍在():
    """补 onabort 不能挤掉原来的成功 / 错误分支。"""
    block = _db_run_block()
    assert "tx.oncomplete = function" in block
    assert "tx.onerror = function" in block


@pytest.mark.skipif(not NODE, reason="本机没有 node")
def test_js_syntax_check():
    r = subprocess.run([NODE, "--check", str(ROOT / "editor" / "gal_offline.js")],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, f"gal_offline.js 语法有问题：{r.stderr}"
