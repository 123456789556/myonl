"""P125：三处「手机上会出事」的地方。

一、导入存档写不进去时静默算成功
   localStorage 在手机上只有 5 MB 左右，一份带素材的备份很容易撞满。
   原来 catch(e){} 空着，n 只数成功的，界面照样报「已导入 N 项」并刷新 ——
   玩家以为换机恢复了，实际少了存档。现在失败的键计数、报出来、且不刷新。

二、静态图运行期不回收
   预热封顶 96 MB 只管"一进来别一次吃光"，解出来的图永不释放。
   玩到第 40 个场景时前面几十张背景还都在内存里，长游戏在低端安卓上会被系统杀掉。
   现在按"最久没画到"淘汰，当前这一帧在用的（背景/立绘/CG/封面）绝不淘汰。

三、平板横屏立绘撑满
   tablet 这个标志在 layout 里算了却没人用。1280×800 横屏按 0.92 撑满就是一堵墙，
   面板再压上来只剩一张脸 —— 这才是"平板没适配"最直观的那一条。
"""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PLAYER = (ROOT / "web" / "myonl-player.js").read_text(encoding="utf-8")
LAYOUT = (ROOT / "web" / "myonl-layout.js").read_text(encoding="utf-8")

pytestmark = [pytest.mark.unit]


def test_import_counts_failed_keys():
    """写不进去的键必须计数 —— 空 catch 就是"假装成功"。"""
    assert "let n = 0, bad = 0;" in PLAYER
    assert "try { localStorage.setItem(k, String(obj.data[k])); n++; } catch (e) { bad++; }" in PLAYER
    assert "return {ok: true, n: n, bad: bad};" in PLAYER


def test_import_with_failures_does_not_reload():
    """部分失败就刷新，等于把「哪几项没写进去」也刷没了。"""
    assert "if (r.bad) {" in PLAYER
    assert '本机存储已满' in PLAYER
    # 失败分支必须 return，不能走到 reload
    seg = PLAYER.split("if (r.bad) {", 1)[1].split("}", 1)[0]
    assert "return;" in seg
    assert "reload" not in seg


def test_runtime_asset_sweep_exists():
    assert "const ASSET_KEEP_BYTES = 160 * 1024 * 1024;" in PLAYER
    assert "function sweepAssets()" in PLAYER
    assert "function assetInUse()" in PLAYER
    assert "const assetAt = {};" in PLAYER
    # 每 60 帧扫一次（不是每帧扫，那样太费）
    assert "if (++assetSweepTick >= 60) { assetSweepTick = 0; sweepAssets(); }" in PLAYER


def test_sweep_never_drops_what_is_on_screen():
    """正在画的那几张被删掉就是当场一块空 —— 必须跳过。"""
    assert "if (state.bg) { keep[state.bg] = 1; keep[state.bg + \"_p\"] = 1; }" in PLAYER
    assert "if (state.cg) keep[state.cg] = 1;" in PLAYER
    assert ".filter((n) => !keep[n] && !assetPending[n]" in PLAYER


def test_get_asset_marks_use_time():
    """淘汰按"最久没画到"排序，取用就得记时间。"""
    assert "if (a && a.complete && a.naturalWidth) { assetAt[name] = performance.now(); return a; }" in PLAYER


def test_tablet_landscape_sprite_is_smaller():
    """平板横屏单独收一档；手机横屏保持原来的 0.92。"""
    assert "(landscape ? (tablet ? 0.82 : 0.92) : 0.86)" in LAYOUT
    assert "(tablet ? 0.36 : 0.42)" in LAYOUT
    assert "tablet ? 640 : 720" in LAYOUT
