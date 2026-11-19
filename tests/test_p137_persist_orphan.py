# -*- coding: utf-8 -*-
"""P137-A2 守护：DB 写失败时索引不留孤儿项。

背景：原 persistAsset 先写 localStorage 名字 / 类型索引，后写 IndexedDB
素材体；put 失败（配额满 / 事务中止）时索引里已留下新名字，之后
/api/assets 列出名字、预览补丁去 DB 取不到，素材「看得见列表、打不开」。
另外 idxWrite/kindWrite 写失败是空 catch，失败路径不可观测。

修法：素材体 put 成功后才写索引；索引写失败回滚刚存的素材体；DB 失败
回滚内存里刚推的名字。索引写函数改为返回 true/false。

静态读源码断言 + 纯 Python 镜像计数，不起浏览器、不联网。
"""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
OFFLINE = (ROOT / "editor" / "gal_offline.js").read_text(encoding="utf-8")
NODE = shutil.which("node")

pytestmark = [pytest.mark.unit]


def _persist_block():
    i = OFFLINE.index("function persistAsset(")
    j = OFFLINE.index("function dataUrlToResponse", i)
    return OFFLINE[i:j]


def test_put先于索引写入():
    """DB put 必须排在 idxWrite/kindWrite 之前，put 失败才不会留幽灵索引。"""
    block = _persist_block()
    put_i = block.index("st.put(")
    idx_i = block.index("idxWrite(taken)")
    assert put_i < idx_i, "索引写在 DB put 之前：DB 失败会留孤儿索引项"


def test_DB失败回滚内存索引():
    block = _persist_block()
    assert "taken.splice(ti, 1)" in block, "DB 失败没把刚推的名字从索引撤掉"
    assert "delete kinds[name]" in block
    assert "throw e" in block


def test_索引写失败回滚素材体():
    block = _persist_block()
    assert "st.delete(name)" in block, "索引写失败没撤掉刚存的素材体"
    assert "素材索引写不进本机存储" in block


def test_索引写函数不再空catch():
    i = OFFLINE.index("function idxWrite(")
    j = OFFLINE.index("function kindOf(")
    seg = OFFLINE[i:j]
    assert "return true;" in seg
    assert "return false;" in seg
    # 空 catch 写法不许再回来
    assert "catch (e) {}" not in seg
    assert "catch(e){}" not in seg


def test_旧的先索引后落库写法已移除():
    block = _persist_block()
    assert "idxWrite(taken); kindWrite(kinds);" not in block


# ---------- 纯逻辑镜像：三种失败/成功路径下索引不留名字 ----------

def _mirror_persist(db_ok, index_ok):
    """对齐 persistAsset 顺序：DB put → 写索引 → 失败回滚。"""
    taken, kinds = [], {}
    name = "pic.jpg"
    if not db_ok:
        return {"taken": taken, "kinds": kinds, "ok": False}
    taken.append(name)
    kinds[name] = "image"
    if not index_ok:
        taken.pop()
        del kinds[name]
        return {"taken": taken, "kinds": kinds, "ok": False}
    return {"taken": taken, "kinds": kinds, "ok": True}


def test_mirror_db失败索引无孤儿():
    r = _mirror_persist(db_ok=False, index_ok=True)
    assert r["ok"] is False
    assert "pic.jpg" not in r["taken"]
    assert "pic.jpg" not in r["kinds"]


def test_mirror索引写失败回滚干净():
    r = _mirror_persist(db_ok=True, index_ok=False)
    assert r["ok"] is False
    assert "pic.jpg" not in r["taken"]
    assert "pic.jpg" not in r["kinds"]


def test_mirror全成功才进索引():
    r = _mirror_persist(db_ok=True, index_ok=True)
    assert r["ok"] is True
    assert r["taken"] == ["pic.jpg"]
    assert r["kinds"]["pic.jpg"] == "image"


@pytest.mark.skipif(not NODE, reason="本机没有 node")
def test_js_syntax_check():
    r = subprocess.run([NODE, "--check", str(ROOT / "editor" / "gal_offline.js")],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, f"gal_offline.js 语法有问题：{r.stderr}"
