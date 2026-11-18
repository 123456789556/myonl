"""P111 契约：编辑器能被手机打开（局域网 + token），横屏首页不许把「最近编辑」藏掉。

两件事分开说清楚，免得以后被"顺手简化"掉：

1. 手机做游戏的真实形态 = 手机浏览器打开电脑上跑的编辑器。
   `serve()` 一直硬绑 127.0.0.1，同 WiFi 的手机根本连不上 —— 这是"手机端做游戏"
   过不去的第二道坎（第一道是编辑器入口，见 test_p110）。
   现在加 `--lan`：显式开启才绑 0.0.0.0 并生成一次性 token，默认仍是只绑本机。
   裸奔不行 —— 那套接口能改剧本、删文件。
   实测（局域网 IP + 手机视口 390×844，playwright）：裸地址 401 / 带 ?t= 302 种 cookie /
   带 cookie 200 → 首页与场景页全绿。

2. 横屏（max-height:520）首页原来把 178 高的大卡 display:none。
   理由成立（390 高扛不住），但它是首页唯一"一键回去接着做"的入口，
   藏掉等于砍掉最常用那条路。改成一行 96px 窄条（左封面 + 中文字 + 右按钮）。

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


def test_serve_defaults_to_localhost_only():
    """默认必须是只绑本机：局域网开放要人明确点头。"""
    src = _read(EDITOR_PY)
    m = re.search(r"def serve\((.+?)\) -> None:", src, re.S)
    assert m, "serve() 签名变了"
    assert 'host: str = "127.0.0.1"' in m.group(1), "serve() 默认 host 不是 127.0.0.1"


def test_lan_flag_is_explicit_and_carries_token():
    src = _read(EDITOR_PY)
    assert '"--lan"' in src, "--lan 开关没了"
    assert 'host, token = "0.0.0.0"' in src, "--lan 没有切到 0.0.0.0"
    # token 每次启动现生成，长度 4 字节 hex（8 字符）
    assert "os.urandom(4)" in src
    # 启动时要把"手机该输的那条地址"打印出来，否则用户不知道输什么
    assert "?t={lan_token}" in src or "t={lan_token}" in src


def test_gate_covers_get_and_post_when_token_set():
    """POST 能改剧本、能删文件，闸门漏一边就白做。"""
    src = _read(EDITOR_PY)
    gates = len(re.findall(r"if not self\._lan_gate\(parsed\):", src))
    assert gates >= 2, f"do_GET/do_POST 只有 {gates} 处闸门"
    # token 为空（默认本地模式）必须直接放行：不能给本地开发加负担
    m = re.search(r"tok = getattr\(self\.app, \"lan_token\", \"\"\) or \"\"\n\s+if not tok:\n\s+return True", src)
    assert m, "本地模式（无 token）没有被放行"


def test_landscape_home_keeps_recent_entry():
    """横屏首页不再隐藏「最近编辑」，而是收成 96px 窄条。"""
    css = _read(CSS)
    tail = css.split("横屏（手机躺下")[-1]
    assert "横屏（手机躺下" in css, "横屏首页那段被删了"
    # 那段里必须是 flex + 96px，而不是 display:none
    assert re.search(r"\.m-home-hero\s*\{\s*display: flex !important;", tail), \
        "横屏又把大卡藏了（或没改成窄条）"
    assert "height: 96px !important" in tail
    # 窄条里三个件都得在：封面 / 文字 / 继续编辑按钮
    for sel in (".m-hero-cover", ".m-hero-text", ".m-hero-go"):
        assert sel in tail, f"窄条漏了 {sel}"


def test_old_hide_rule_is_gone():
    """旧的 display:none 规则不能还留着（同特异性下会被它先命中）。"""
    css = _read(CSS)
    assert not re.search(r"@media \(max-height: 520px\) \{\s*\.m-home-hero \{ display: none !important; \}", css), \
        "旧的「横屏隐藏大卡」规则还在"
