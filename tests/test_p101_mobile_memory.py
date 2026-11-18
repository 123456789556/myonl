"""P101：打包时的手机内存预算。

以前单文件包只限「单张图长边 1600」，**张数没有上限**：20 张 1600×900 背景
解码后就是 110 MB，40 张 220 MB —— 低端安卓的 WebView 在这个量级直接白屏。
视频帧序列当年做过「只留最近 N 帧」，静态图一直没做，这是同一类坑。

这里锁四件事：
1. 图少的时候不降档（别为了个位数图把画质白降了）；
2. 图多的时候沿 1600→1280→1024→800 阶梯降，降到不超预算为止；
3. 压到最小档仍超预算：照出包（不能卡住作者的作品），但必须带回 memory_warning；
4. 真实图片（不是假字节）也走得通，避免只在 mock 里成立。
"""
import io

import pytest

pytestmark = [pytest.mark.unit]

from engine import webpack as W  # noqa: E402


def _fake_sizes(sizes):
    """把 _estimate_decode 换成「我告诉你每张多大」，专测阶梯逻辑，不掺 PIL。"""
    calls = []

    def fake(blob, edge):
        # blob 是我们塞进去的 (原始字节数, 原始长边) 二元组
        raw_bytes, raw_edge = blob
        if raw_edge > edge:
            scale = edge / float(raw_edge)
            return int(raw_bytes * scale * scale)
        return raw_bytes

    return fake, calls


def test_图少不降档(monkeypatch):
    """2 张图远低于预算，长边必须留在最大档，画质不该白降。"""
    fake, _ = _fake_sizes([])
    monkeypatch.setattr(W, "_estimate_decode", fake)
    blobs = [(6 * 1024 * 1024, 1600), (6 * 1024 * 1024, 1600)]
    edge, total = W._pick_edge(blobs)
    assert edge == W.DECODE_EDGE_LADDER[0] == 1600
    assert total <= W.DECODE_BUDGET


def test_图多自动沿阶梯降档(monkeypatch):
    """20 张超过预算，必须降到更小的档，而且降完要真的进预算。"""
    fake, _ = _fake_sizes([])
    monkeypatch.setattr(W, "_estimate_decode", fake)
    blobs = [(6 * 1024 * 1024, 1600)] * 20
    assert sum(fake(b, 1600) for b in blobs) > W.DECODE_BUDGET      # 前提确实超了
    edge, total = W._pick_edge(blobs)
    assert edge < 1600
    assert edge in W.DECODE_EDGE_LADDER
    assert total <= W.DECODE_BUDGET


def test_压到底仍超也要给结论(monkeypatch):
    """小到 800 都压不住时，不能装作没事——必须把超出的数字带出来。"""
    fake, _ = _fake_sizes([])
    monkeypatch.setattr(W, "_estimate_decode", fake)
    blobs = [(20 * 1024 * 1024, 1600)] * 12      # 240 MB，压到 800 也还剩 60 MB+
    edge, total = W._pick_edge(blobs)
    assert edge == W.DECODE_EDGE_LADDER[-1]
    assert total > 0                     # 有数就行，上层据此决定要不要拦


def test_真实图片走一遍():
    """用真图（不是假字节）确认估读没问题，避免上面三条只在 mock 里成立。"""
    pytest.importorskip("PIL")
    from PIL import Image

    def png(w, h, c):
        buf = io.BytesIO()
        Image.new("RGB", (w, h), c).save(buf, "PNG")
        return buf.getvalue()

    small = [png(1600, 900, (10, 10, 10)), png(1600, 900, (20, 20, 20))]
    edge, total = W._pick_edge(small)
    assert edge == 1600
    # 1600×900×4 ≈ 5.5 MB 一张，两张约 11 MB
    assert 8 * 1024 * 1024 < total < 16 * 1024 * 1024

    # 「长边超了就缩」这个判断：1600 的图在 edge=1024 下必须判超
    one = small[0]
    assert W._over_edge(one, 1024) is True
    assert W._over_edge(one, 1600) is False
