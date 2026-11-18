"""P102：解码并发必须受控。

打包器管的是「素材总量」——超了就把长边降下来。但总量达标不等于启动没事：
三十张图一次性 `new Image()`，解码峰值是**同时**解压出来的，那一瞬间的占用
可以是稳态的好几倍。低端机上表现就是白屏、闪退，而打包体检一切正常。

所以这两道门禁是一对：
  P101（打包期）问「这个包有多大」
  P102（运行期）问「它是不是一次性全解开」

只做前者，等于只量了体重没量一口气能憋多久。
"""
import re

import pytest

pytestmark = [pytest.mark.unit]

from pathlib import Path  # noqa: E402

PLAYER = Path(__file__).resolve().parent.parent / "web" / "myonl-player.js"


def _src():
    return PLAYER.read_text(encoding="utf-8")


def _load_body():
    src = _src()
    at = src.index("function loadAssets")
    return src[at:at + 1800]


def test_解码有并发上限():
    """必须是一个明确的常数，不能是「有多少解多少」。"""
    src = _src()
    m = re.search(r"DECODE_CONCURRENCY\s*=\s*(\d+)", src)
    assert m, "没有解码并发常量——启动时又变成一次性全解"
    value = int(m.group(1))
    assert 1 <= value <= 8, f"并发 {value} 不合理：太小启动慢，太大峰值又压不住"


def test_启动循环按上限起跑():
    """起跑的那个循环不能被批成 names.length。"""
    body = _load_body()
    m = re.search(r"for\s*\(([^)]*)\)[\s\S]{0,80}?startOne\s*\(", body)
    assert m, "找不到受控的起跑循环（for ... startOne）"
    head = m.group(1)
    assert "DECODE_CONCURRENCY" in head, f"起跑没受并发上限约束：{head}"
    # names.length 出现在条件里是对的（素材少于上限时不能越界），
    # 但它不能当上限本身用 —— 所以要求 DECODE_CONCURRENCY 是一级条件。
    assert re.search(r"i\s*<\s*DECODE_CONCURRENCY", head), (
        f"上限必须直接写 DECODE_CONCURRENCY：{head}")


def test_完成一个补一个():
    """腾出槽位要立刻补位，否则并发上限变成串行，几十张图等到天亮。"""
    body = _load_body()
    at = body.index("const settle")
    seg = body[at:body.index("};", at)]
    assert "startOne()" in seg, "settle 里没有补位，并发会被拖成串行"
    # 两个出口（解好了 / 解坏了）都得走 settle，不能各自 resolve
    assert body.count("flying--; settle()") >= 2, "onload/onerror 没有都交回 settle"


def test_预热到预算就停手():
    """全摊开会把手机压死。必须有个字节门禁，到量就停，剩下的按需解。"""
    src = _src()
    m = re.search(r"ASSET_WARM_BYTES\s*=\s*(\d+)\s*\*\s*1024\s*\*\s*1024", src)
    assert m, "没有预解上限——启动时又会把几十张图全摊开"
    assert 32 <= int(m.group(1)) <= 256, f"预解上限 {m.group(1)} MB 不在合理区间"
    body = _load_body()
    assert "bytes > ASSET_WARM_BYTES" in body, "预算没有接进起跑判断"
    assert "assetMostlyDone = true" in body, "停手后要能通知出去"
    # 到量以后不能傻等：必须把 promise 结掉，否则首屏永远不出来
    assert "stopped" in body and "resolve()" in body


def test_按需解码有兜底():
    """没预解到的图，第一次画到时必须能自己解出来，不能永远空白。"""
    src = _src()
    assert "function getAsset" in src
    body = src[src.index("function getAsset"):]
    body = body[:body.index("function loadAssets")]
    assert "new Image()" in body, "getAsset 不会自己起解码"
    assert "delete assets[name]" in body, "坏图必须连占位一起撤，否则整局都是空的"


def test_封面先解():
    """首屏要用的排在最前面，否则点进去先看一片黑。"""
    body = _load_body()
    assert "pack.cover" in body, "没有把封面提到最前"
    cover_at = body.index("pack.cover")
    push_at = body.index("names.push")
    assert cover_at < push_at, "封面优先必须写在铺其余素材之前"
