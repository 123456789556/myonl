"""P107：首启配置询问（一屏一问，问完直接进游戏）的源码契约。

这一层最容易犯的错不是画不好，而是「拦人」和「忘记落盘」：
第一版就漏了 setupDone，于是每次打开都要重答一遍；也漏了 tryFullscreen，
第一次玩的人反而进不了全屏。
"""
from pathlib import Path
import pytest

pytestmark = [pytest.mark.unit]

ROOT = Path(__file__).resolve().parents[1]


def _read(*parts):
    return (ROOT.joinpath(*parts)).read_text(encoding="utf-8")


def test_有三屏且第一屏是画面方向():
    src = _read("web", "myonl-player.js")
    assert "const SETUP_Q = [" in src, "问题表要独立出来，别散在函数里"
    assert 'key: "orient"' in src and "用哪种画面？" in src
    assert 'key: "dlg"' in src and "台词怎么排？" in src
    assert "怎么玩" in src, "第三屏把「怎么玩」并进来，省掉一张重复的引导卡"
    assert "setupStep" in src


def test_问完落盘且只问一次():
    src = _read("web", "myonl-player.js")
    assert "setupDone = true;" in src
    assert "setupDone: setupDone ? 1 : 0" in src, "必须写进 prefs，否则每次打开都重问"
    # 老玩家（看过引导 / 已问过）不弹
    assert "v.setupDone === 1 || helpSeen" in src


def test_向导期间不许点穿到标题页按钮():
    src = _read("web", "myonl-player.js")
    assert "if (state.setup) return onSetupTap(p);" in src
    i_setup = src.index("if (state.setup) return onSetupTap(p);")
    i_guide = src.index("if (state.guide) {")
    assert i_setup < i_guide, "setup 的判断要排在引导之前，否则会先被 guide 吃掉一下"
    assert "state.startRect" in src and "state.continueRect" in src


def test_开始这一下要顺手进全屏():
    src = _read("web", "myonl-player.js")
    i = src.index("function finishSetup(")
    seg = src[i:i + 900]
    assert "tryFullscreen();" in seg, "setup 拦住了标题页那次点击，全屏得在收尾时补上"
    assert "startGame(false);" in seg


def test_选择要真的写进偏好():
    src = _read("web", "myonl-player.js")
    i = src.index("function finishSetup(")
    seg = src[i:i + 900]
    assert "PREF.orient = state.setup.picks.orient;" in seg
    assert "PREF.dlg = Math.max(0, Math.min(2" in seg, "dlg 只有三档，写坏了会画出空面板"
