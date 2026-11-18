"""P111 契约：横屏首页不许把「最近编辑」藏掉（编辑器只绑 127.0.0.1 也在这里锁住）。

横屏（max-height:520）首页原来把 178 高的大卡 display:none。
理由成立（390 高扛不住），但它是首页唯一"一键回去接着做"的入口，
藏掉等于砍掉最常用那条路。改成一行 96px 窄条（左封面 + 中文字 + 右按钮）。

另外锁一条边界：编辑器服务只绑 127.0.0.1。
那套接口能改剧本、删文件，不该交给整个局域网；手机端编游戏走离线内核，
不靠这条网络路径（曾经加过 --lan + token，按用户要求砍了，见 CHANGELOG P112）。

:meta private:
"""

import re
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

ROOT = Path(__file__).resolve().parents[1]
EDITOR_PY = ROOT / "engine" / "editor.py"
CSS = ROOT / "editor" / "editor.css"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def test_serve_binds_localhost_only():
    """不许再出现可配置的对外绑定：局域网那套已经明确砍了。"""
    src = _read(EDITOR_PY)
    m = re.search(r"def serve\((.+?)\) -> None:", src, re.S)
    assert m, "serve() 签名变了"
    assert "host" not in m.group(1), "serve() 又长出 host 参数了"
    assert 'ThreadingHTTPServer(("127.0.0.1", port)' in src, "绑定的不是 127.0.0.1"
    assert "--lan" not in src, "--lan 又被加回来了"
    assert "_lan_gate" not in src and "lan_token" not in src


def test_landscape_home_keeps_recent_entry():
    """横屏首页不再隐藏「最近编辑」，而是收成 96px 窄条。"""
    css = _read(CSS)
    assert "横屏（手机躺下" in css, "横屏首页那段被删了"
    tail = css.split("横屏（手机躺下")[-1]
    assert re.search(r"\.m-home-hero\s*\{\s*display: flex !important;", tail), \
        "横屏又把大卡藏了（或没改成窄条）"
    assert "height: 96px !important" in tail
    for sel in (".m-hero-cover", ".m-hero-text", ".m-hero-go"):
        assert sel in tail, f"窄条漏了 {sel}"


def test_old_hide_rule_is_gone():
    """旧的 display:none 规则不能还留着。"""
    css = _read(CSS)
    assert not re.search(
        r"@media \(max-height: 520px\) \{\s*\.m-home-hero \{ display: none !important; \}", css
    ), "旧的「横屏隐藏大卡」规则还在"
