# -*- coding: utf-8 -*-
"""P137-A1 守护：备份导入素材部分失败时如实上报，不假装成功刷新。

背景：从 .json 备份恢复作品库时，IndexedDB 写入部分失败（配额满 / 事务
中止 / 单条损坏），原 restore 只回待写条数，外层 catch 后仍 return true；
editor_home.js 拿到 true 照常 location.reload()。刷新后作品在、素材缺，
用户以为备份恢复成功。

修法：restore 逐笔记成功 / 失败清单，回 {ok, fail}；导入侧有失败条目
返回 false 并明示「部分素材没恢复」，整条抛错也返回 false；调用方只在
全成功时 reload。

静态读源码断言 + 纯 Python 镜像计数，不起浏览器、不联网。
"""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
OFFLINE = (ROOT / "editor" / "gal_offline.js").read_text(encoding="utf-8")
HOME = (ROOT / "editor" / "editor_home.js").read_text(encoding="utf-8")
NODE = shutil.which("node")

pytestmark = [pytest.mark.unit]


def _restore_block():
    i = OFFLINE.index("restore: function")
    j = OFFLINE.index("totalBytes:", i)
    return OFFLINE[i:j]


def _import_block():
    i = OFFLINE.index("window.__myonlImportLib = function")
    j = OFFLINE.index("// 导出条", i)
    return OFFLINE[i:j]


# ---------- restore：逐笔计数，回成功 / 失败清单 ----------

def test_restore收集失败清单():
    block = _restore_block()
    assert "failed.push(n)" in block
    assert "return { ok: list.length - failed.length, fail: failed }" in block


def test_restore失败条目不进索引():
    block = _restore_block()
    assert "落库成功才进索引" in block
    # 有失败条目时不整体提交索引
    assert "if (!failed.length)" in block


# ---------- 导入侧：失败返回 false，成功才 true ----------

def test_部分失败返回false且提示说清楚():
    block = _import_block()
    assert "部分素材没恢复" in block
    partial_i = block.index("部分素材没恢复")
    seg = block[partial_i:block.index("}).catch", partial_i)]
    assert "return false;" in seg, "部分失败分支不能返回 true"


def test_catch分支也返回false():
    block = _import_block()
    catch_i = block.index("}).catch(function (e)")
    seg = block[catch_i:]
    assert "return false;" in seg, "整条链路抛错不能再当成功"


def test_全成功才返回true():
    block = _import_block()
    # 成功分支：在部分失败判断之后、catch 之前
    ok_i = block.rindex("return true;")
    fail_i = block.index("部分素材没恢复")
    assert ok_i > fail_i, "return true 必须在失败分支之后"


def test_素材链路没加载也不算成功():
    block = _import_block()
    miss_i = block.index("素材这条链路没加载")
    seg = block[miss_i:miss_i + 200]
    assert "return Promise.resolve(false)" in seg


def test_调用方只在ok时刷新():
    """home 侧：false 不能走到 reload，否则失败现场被刷没。"""
    assert "if (ok) setTimeout(function () { location.reload(); }, 600);" in HOME


# ---------- 纯逻辑镜像 ----------

def _mirror_restore(db_results):
    """db_results: [(name, db_ok), ...]；回 {ok, fail}。"""
    failed = [n for n, ok in db_results if not ok]
    return {"ok": len(db_results) - len(failed), "fail": failed}


def _mirror_import(r):
    return False if r["fail"] else True


def test_mirror_restore全成功():
    r = _mirror_restore([("a.jpg", True), ("b.mp3", True)])
    assert r == {"ok": 2, "fail": []}
    assert _mirror_import(r) is True


def test_mirror_restore部分失败计数与名单():
    r = _mirror_restore([("a.jpg", True), ("bad.png", False), ("c.mp3", False)])
    assert r["ok"] == 1
    assert r["fail"] == ["bad.png", "c.mp3"]
    assert _mirror_import(r) is False


def test_mirror_restore全失败():
    r = _mirror_restore([("x.jpg", False)])
    assert r["ok"] == 0
    assert r["fail"] == ["x.jpg"]
    assert _mirror_import(r) is False


@pytest.mark.skipif(not NODE, reason="本机没有 node")
def test_js_syntax_check():
    r = subprocess.run([NODE, "--check", str(ROOT / "editor" / "gal_offline.js")],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, f"gal_offline.js 语法有问题：{r.stderr}"
