"""tests/test_p32_wait_and_persist.py：P32 新增 @wait 指令 + 展示层状态持久化回归。"""
import json
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import json as _json  # noqa: E402

import pygame  # noqa: E402
import pytest  # noqa: E402

from engine import save as save_api  # noqa: E402
from engine.parser import parse_text  # noqa: E402
from engine.renderer import Renderer  # noqa: E402
from engine.runtime import Runtime  # noqa: E402

pytestmark = [pytest.mark.ui]


def _make_rt(tmp_path, script_text: str) -> Runtime:
    p = tmp_path / "s.gal"
    p.write_text(script_text, encoding="utf-8")
    rt = Runtime()
    rt.load(str(p))
    return rt


@pytest.fixture()
def ren(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text(_json.dumps({"title": "T", "splash": False}), encoding="utf-8")
    r = Renderer((1280, 720), str(tmp_path))
    yield r
    r.close()


@pytest.fixture(autouse=True)
def _reset_saves(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    save_api.reset_saves_dir()
    yield
    save_api.reset_saves_dir()


def _step_all(rt: Runtime, limit=5000):
    """跑完全部指令（跳过 @wait、自动选第一个选项），返回事件列表。"""
    evs = []
    while not rt.snapshot().get("finished") and len(evs) < limit:
        rt.advance_wait(999.0)  # 跳过 @wait
        pc = rt.snapshot().get("pending_choice")
        if pc:
            for i, o in enumerate(pc.get("options") or []):
                if o.get("available"):
                    rt.choose(i)
                    break
            continue
        ev = rt.step()
        evs.append(ev)
    return evs


# ---------------- F2: @wait 指令 ----------------

def test_wait解析_秒_毫秒_单位后缀():
    """DSL 三种写法都能正确解析为秒数。"""
    ins = parse_text("@wait 1.5\n@wait 500ms\n@wait 2s\n", source="<t>")
    assert ins[0]["op"] == "wait" and ins[0]["seconds"] == 1.5
    assert ins[1]["op"] == "wait" and ins[1]["seconds"] == 0.5
    assert ins[2]["op"] == "wait" and ins[2]["seconds"] == 2.0


def test_wait解析_缺参数抛中文():
    with pytest.raises(Exception) as ei:
        parse_text("@wait\n", source="<t>")
    assert "@wait 需要等待时长" in str(ei.value)


def test_wait运行时_暂停推进_倒计时完自动清零(tmp_path):
    rt = _make_rt(tmp_path, "@wait 2.0\n@ 你好\n@end\n")
    ev = rt.step()  # @wait
    assert ev["type"] == "wait" and ev["seconds"] == 2.0
    st = rt.snapshot()
    assert st["pending_wait"] == {"seconds": 2.0}
    # step() 不应在 pending_wait 时推进
    rt.step()  # 防御性返回 wait 事件
    assert rt.pending_wait_seconds() == 2.0
    # 倒计时
    rt.advance_wait(0.5)
    assert rt.pending_wait_seconds() == 1.5
    rt.advance_wait(3.0)  # 超过剩余
    assert rt.pending_wait_seconds() == 0.0
    assert rt.snapshot()["pending_wait"] is None
    # 倒计时完正常推进
    ev = rt.step()
    assert ev["type"] == "say" and ev["text"] == "你好"


def test_wait进存档_读档后续等(tmp_path):
    rt = _make_rt(tmp_path, "@wait 5.0\n@ 你好\n@end\n")
    rt.step()  # @wait
    rt.save(2)
    rt2 = Runtime()
    rt2.load_save(2)
    assert rt2.pending_wait_seconds() == 5.0
    # 倒计时一半存一半也能恢复
    rt2.advance_wait(2.0)
    rt2.save(3)
    rt3 = Runtime()
    rt3.load_save(3)
    assert rt3.pending_wait_seconds() == 3.0


# ---------------- F1: 展示层持久化 ----------------

def test_fg进存档_读档复原(tmp_path):
    rt = _make_rt(tmp_path, "@fg 雨 x=100 y=200 alpha=0.7\n@end\n")
    rt.step()
    assert rt.snapshot()["fg"] == {"name": "雨", "x": 100, "y": 200, "alpha": 0.7}
    rt.save(4)
    rt2 = Runtime()
    rt2.load_save(4)
    assert rt2.snapshot()["fg"] == {"name": "雨", "x": 100, "y": 200, "alpha": 0.7}


def test_cameraZoom进存档_读档复原(tmp_path):
    rt = _make_rt(tmp_path, "@camera zoom 1.0 1.8\n@end\n")
    rt.step()
    assert rt.snapshot()["camera_zoom"] == 1.8
    rt.save(5)
    rt2 = Runtime()
    rt2.load_save(5)
    assert rt2.snapshot()["camera_zoom"] == 1.8


def test_animFinal进存档_读档复原(tmp_path):
    rt = _make_rt(tmp_path, "@show 双叶 身体:默认\n@anim 双叶 x=-50 0.8\n@end\n")
    rt.step(); rt.step()
    assert rt.snapshot()["anim_final"] == {"双叶": {"x": -50.0}}
    rt.save(6)
    rt2 = Runtime()
    rt2.load_save(6)
    assert rt2.snapshot()["anim_final"] == {"双叶": {"x": -50.0}}


def test_hide清对应animFinal(tmp_path):
    rt = _make_rt(tmp_path, "@show 双叶 身体:默认\n@anim 双叶 x=-50 0.8\n@hide 双叶\n@end\n")
    rt.step(); rt.step(); rt.step()
    assert "双叶" not in rt.snapshot()["anim_final"]


def test_restorePersistentState不覆盖测试直接设的renderer内部状态(ren):
    """渲染层测试直接调 ren.play_fg 绕开 runtime 路径时，_restore_persistent_state
    不应把 self._fg 清回 None（因为测试手工构造的 state 没有 fg 键）。"""
    ren.play_fg("任何")
    assert ren._fg is not None
    state = {"bg": None, "sprites": [], "history": [], "characters": {}, "pending_choice": None}
    ren.render(state)   # state 没有 fg 键 → 不覆盖
    assert ren._fg is not None


def test_read档后renderer恢复持久状态(tmp_path):
    """完整链路：runtime 存 fg/zoom/anim → 存档 → 读档 → renderer 画面正确。"""
    img_dir = tmp_path / "images"
    img_dir.mkdir(parents=True)
    for name, color in (("a_b", (255, 0, 0)), ("rain", (0, 255, 0))):
        surf = pygame.Surface((100, 100), pygame.SRCALPHA)
        surf.fill((*color, 255))
        pygame.image.save(surf, str(img_dir / f"{name}.png"))
    rt = _make_rt(tmp_path,
                  "@show a b\n"
                  "@fg rain x=600 y=350\n"
                  "@camera zoom 1.0 1.3\n"
                  "@anim a alpha=0.8 0.5\n"
                  "@ 继续\n@end\n")
    _step_all(rt)
    rt.save(7)

    rt2 = Runtime()
    rt2.load_save(7)
    ren2 = Renderer((1280, 720), str(tmp_path))
    try:
        ren2.render(rt2.snapshot())
        assert ren2._fg == {"name": "rain", "x": 600, "y": 350, "alpha": 1.0}
        assert ren2._cam_scale == 1.3
        assert ren2._sprite_anim.get("a", {}).get("alpha") == 0.8
    finally:
        ren2.close()


def test_开始新游戏后立即出现第一句台词(tmp_path, ren):
    """点「开始新游戏」后立刻推进到第一句，而不是先给玩家一个空画面。"""
    from engine import demo
    from engine.ui import UI

    script = tmp_path / "s.gal"
    script.write_text("@bg 教室\n@ 第一句\n@ 第二句\n@end\n", encoding="utf-8")
    rt = Runtime()
    ui = UI()
    ui._mode = "title"
    status = demo._apply_business(
        {"action": "start_game"}, rt, ren, ui, str(script),
        str(tmp_path / "settings.json"))
    assert status == "loaded"
    history = rt.snapshot()["history"]
    assert len(history) == 1
    assert history[0]["text"] == "第一句"
