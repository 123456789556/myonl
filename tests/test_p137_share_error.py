# -*- coding: utf-8 -*-
"""P137-A5 守护：SW 分享失败能区分「没给文件」与「解析 / 写库失败」。

背景：原 handleShare 的 catch 是空实现，multipart 解析失败或写 inbox 失败
都被吞掉，照样 303 回编辑器；导入侧只看 inbox 键，收不到就提示「没拿到
能用的素材」，分不清是用户真没给文件还是写库失败。

修法：SW 失败时写一条 inbox:error:<ts> 记录，stage 区分 parse（解析失败）
/ write（写库失败）；importShared 读出错误标记随 {names, error} 回传，
页面按 stage 给不同提示。

注意（审计 O2）：本链路未在真机 / 真 Chromium PWA 环境跑过，这里只做到
「失败可区分」，两种失败分支的真机表现未复现验证。

静态读源码断言 + 纯 Python 镜像分类，不起浏览器、不联网。
"""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SW = (ROOT / "editor" / "sw.js").read_text(encoding="utf-8")
OFFLINE = (ROOT / "editor" / "gal_offline.js").read_text(encoding="utf-8")
NODE = shutil.which("node")

pytestmark = [pytest.mark.unit]


# ---------- SW 侧：两种失败分别留标记 ----------

def test_sw写错误记录键():
    assert "function putError(" in SW
    assert '"inbox:error:" + ts' in SW
    assert "stage:" in SW
    assert "message:" in SW


def test_sw解析失败标parse():
    i = SW.index("function handleShare")
    seg = SW[i:]
    parse_i = seg.index('putError(ts, "parse"')
    write_i = seg.index('putError(ts, "write"')
    # 解析 catch 在外层，写库 catch 在 chain 内层
    assert parse_i > write_i
    assert 'putError(ts, "parse", err)' in seg
    assert 'putError(ts, "write", err)' in seg


def test_sw失败仍303回编辑器不卡死入口():
    assert "Response.redirect(dest, 303)" in SW
    # 错误记录自身写不进也要兜底，不能再抛
    err_i = SW.index("function putError")
    err_seg = SW[err_i:SW.index("function handleShare")]
    assert "tx.onerror" in err_seg
    assert "tx.onabort" in err_seg


# ---------- 导入侧：读出错误标记并区分提示 ----------

def test_importShared分离错误键与文件键():
    i = OFFLINE.index("importShared: function")
    seg = OFFLINE[i:i + 1600]
    assert '"inbox:error:"' in seg
    assert "errKeys" in seg
    assert "inbox.length" in seg


def test_importShared回传names与error结构():
    i = OFFLINE.index("importShared: function")
    seg = OFFLINE[i:i + 1600]
    assert "resolve({ names: names, error: error })" in seg


def test_页面按stage给不同提示():
    i = OFFLINE.index("importShared().then")
    seg = OFFLINE[i:i + 700]
    assert 'error.stage === "parse"' in seg
    assert "解析分享文件失败" in seg
    assert "写入素材库失败" in seg
    # 真没给文件仍是另一条提示
    assert "这次分享里没拿到能用的素材" in seg


def test_兼容旧的纯数组返回():
    i = OFFLINE.index("importShared().then")
    seg = OFFLINE[i:i + 700]
    assert "Array.isArray(res)" in seg


# ---------- 纯逻辑镜像：键分类与提示分流 ----------

def _mirror_classify(keys):
    err_keys = [k for k in keys if k.startswith("inbox:error:")]
    inbox = [k for k in keys if not k.startswith("inbox:error:")]
    return {"err": err_keys, "inbox": inbox}


def _mirror_toast(error, names):
    if error:
        return "解析分享文件失败" if error["stage"] == "parse" else "写入素材库失败"
    return "从分享收下" if names else "没拿到能用的素材"


def test_mirror只给文件无错误():
    r = _mirror_classify(["inbox:1:1", "inbox:1:2"])
    assert r["err"] == [] and len(r["inbox"]) == 2
    assert _mirror_toast(None, ["a"]) == "从分享收下"


def test_mirror错误键被分离():
    r = _mirror_classify(["inbox:error:9", "inbox:1:1"])
    assert r["err"] == ["inbox:error:9"]
    assert r["inbox"] == ["inbox:1:1"]


def test_mirror两种stage提示不同():
    assert _mirror_toast({"stage": "parse"}, []) == "解析分享文件失败"
    assert _mirror_toast({"stage": "write"}, []) == "写入素材库失败"
    assert _mirror_toast(None, []) == "没拿到能用的素材"


@pytest.mark.skipif(not NODE, reason="本机没有 node")
@pytest.mark.parametrize("path", ["editor/sw.js", "editor/gal_offline.js"])
def test_js_syntax_check(path):
    r = subprocess.run([NODE, "--check", str(ROOT / path)],
                      capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, f"{path} 语法有问题：{r.stderr}"
