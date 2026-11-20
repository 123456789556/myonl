"""试玩退出契约：手机端点「试玩」之后必须能在游戏里退出来。

用户原话：「我要玩你的游戏，我说不定必须得退出软件，然后重新去点击，
而不能在试玩的那个游戏里面直接退出来」。

根因是编辑器首页的试玩入口用 `location.href = "./game.html"` 整页跳走：
编辑器被导航覆盖，游戏里又没有回程，安卓上只能杀掉应用重开。

P190 起编辑器首页不再内嵌试玩（改成「新手教程」：直接开一个能改的作品），
所以「编辑器侧内嵌层 / 来源校验」两条作废；玩家侧的退出契约继续有效，
以后要再嵌 game.html 得先把它恢复回来。
"""
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

ROOT = Path(__file__).resolve().parents[1]
HOME = ROOT / "editor" / "editor_home.js"
PLAYER = ROOT / "web" / "myonl-player.js"


def _home() -> str:
    return HOME.read_text(encoding="utf-8")


def _player() -> str:
    return PLAYER.read_text(encoding="utf-8")


def _code(src: str) -> str:
    """去掉整行注释。注释里会提到"以前的写法是 xxx"，不能让校验撞上自己。"""
    return "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("//"))


def _fn(src: str, name: str) -> str:
    start = src.index(f"function {name}(")
    nxt = src.index("\n  function ", start + 1)
    return src[start:nxt]


def test_home_does_not_open_the_demo_page_at_all():
    """P190：首页直接开作品，不再跳/嵌 game.html。

    只要这两条重新出现在代码里，就等于把「进得去出不来」的老路铺回去了。
    """
    src = _code(_home())
    assert 'location.href = "./game.html"' not in src, "试玩还在整页跳，用户退不回来"
    assert 'location.assign("./game.html")' not in src
    assert 'location.replace("./game.html")' not in src
    assert '"./game.html"' not in src, "首页又在加载 game.html 了"


def test_player_knows_when_it_is_embedded():
    src = _player()
    body = _fn(src, "isEmbedded")
    assert "window.parent" in body
    assert "try" in body, "跨域访问 parent 会抛，不接住整个渲染循环就断了"


def test_player_can_ask_parent_to_close():
    body = _fn(_player(), "exitDemo")
    assert "postMessage" in body and "myonl-exit-demo" in body


def test_exit_hit_is_checked_before_anything_that_swallows_taps():
    """退出键必须排在最前面。

    onTap 里首启向导、引导页、标题页「点哪都开始」都会把这一下吃掉；
    退出键排后面就永远点不到 —— 这正是第一版翻车的地方。
    """
    src = _player()
    body = _fn(src, "onTap")
    exit_at = body.index("state.exitRect && inRect")
    setup_at = body.index("if (state.setup) return onSetupTap")
    guide_at = body.index("if (state.guide)")
    title_at = body.index('state.scene === "title"')
    assert exit_at < setup_at, "退出键排在了首启向导后面，点不到"
    assert exit_at < guide_at, "退出键排在了引导页后面，点不到"
    assert exit_at < title_at, "退出键排在了「点哪都开始」后面，点不到"


def test_exit_chip_is_drawn_on_every_full_screen_layer():
    """向导和引导都是满屏浮层，只画在标题页上等于没画。"""
    src = _player()
    for fn in ("drawTitle", "drawSetup", "drawGuide"):
        assert "drawExitChip()" in _fn(src, fn), f"{fn} 上没画出退出键"


def test_game_screen_clears_stale_exit_hitbox():
    """正文里不画退出键，但上一屏留下的命中区要清掉，否则点右上角会误退。"""
    src = _player()
    seg = src[src.index("function render("):] if "function render(" in src else src
    assert "state.exitRect = null" in src


def test_menu_carries_exit_item_when_embedded():
    body = _fn(_player(), "menuItems")
    assert "isEmbedded()" in body, "菜单没按嵌入状态决定要不要加退出项"
    assert "exitDemo" in body


def test_embedded_demo_skips_first_run_wizard():
    """内嵌试玩不该先弹三屏首启向导 —— 盖住退出键，就是"进得去出不来"。"""
    src = _player()
    seg = src[src.index("if (!setupDone && !state.setup"):]
    seg = seg[:seg.index("}") + 1]
    assert "isEmbedded()" in seg, "内嵌试玩还是会弹首启向导"
