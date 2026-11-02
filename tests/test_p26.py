"""tests/test_p26.py：P26 T 组（引擎侧）验收测试。

T1 序幕 splash / T2 @else·@elif / T3 @music 淡入淡出 / T4 persistent 全局解锁 / T5 打包瘦身。
全部无头（dummy 视频驱动），saves/ 等相对路径由 fixture 隔离到 tmp_path。
"""
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")  # 无头模式，须在 import pygame 前生效

import pygame
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine import demo
from engine import timeline
from engine import save as save_api
from engine.parser import GalSyntaxError, dump_text, parse_text
from engine.renderer import Renderer
from engine.runtime import Runtime
from pack import _EXCLUDE_NAMES

pytestmark = [pytest.mark.ui, pytest.mark.integration]


@pytest.fixture(autouse=True)
def _in_tmp(tmp_path, monkeypatch):
    """saves/ 等相对路径写入当前目录，用例之间完全隔离。"""
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def ren(tmp_path):
    r = Renderer((1280, 720), str(tmp_path))
    yield r
    r.close()


def _write(tmp_path, text: str, name="a.gal") -> str:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


def _rt(tmp_path, text: str) -> Runtime:
    rt = Runtime()
    rt.load(_write(tmp_path, text))
    return rt


def _run_to_end(rt: Runtime, limit=200) -> None:
    for _ in range(limit):
        if rt.snapshot()["finished"]:
            return
        rt.step()


# ==================== T2 @else / @elif ====================

ELSE_SCRIPT = """@character 她 #ffccaa
@label 开始
@set 好感 = 3
@if 好感 > 5:
    @ 她是高兴的
@elif 好感 > 1:
    @ 她有点在意
@else:
    @ 她面无表情
@end
"""


def _strip(xs):
    """去掉 line/file 字段（dump_text 不输出位置信息）。"""
    out = []
    for ins in xs:
        ins = {k: v for k, v in ins.items() if k not in ("line", "file")}
        for key in ("body", "else_body"):
            if isinstance(ins.get(key), list):
                ins[key] = _strip(ins[key])
        out.append(ins)
    return out


def test_else_elif_解析结构():
    prog = parse_text(ELSE_SCRIPT)
    if_ins = next(i for i in prog if i["op"] == "if")
    assert if_ins["body"][0]["text"] == "她是高兴的"
    else_body = if_ins["else_body"]
    assert len(else_body) == 1
    elif_ins = else_body[0]
    assert elif_ins["op"] == "if"
    assert elif_ins["cond"] == {"var": "好感", "op": ">", "value": 1}
    assert elif_ins["body"][0]["text"] == "她有点在意"
    assert elif_ins["else_body"][0]["text"] == "她面无表情"


@pytest.mark.parametrize("value,expected", [(6, "她是高兴的"), (3, "她有点在意"), (0, "她面无表情")])
def test_else_elif_运行三分支(tmp_path, value, expected):
    rt = _rt(tmp_path, ELSE_SCRIPT.replace("@set 好感 = 3", f"@set 好感 = {value}"))
    _run_to_end(rt)
    assert [h["text"] for h in rt.snapshot()["history"]] == [expected]


def test_else_块_dump往返():
    prog = parse_text(ELSE_SCRIPT)
    again = parse_text(dump_text(prog))
    assert _strip(again) == _strip(prog)


def test_else_无对应if报错():
    with pytest.raises(GalSyntaxError) as exc:
        parse_text("@else:\n    @ 旁白\n")
    assert "@else" in exc.value.message and "前面必须紧接" in exc.value.message


def test_if后缺少else体报错():
    with pytest.raises(GalSyntaxError) as exc:
        parse_text("@set a = 1\n@if a == 1:\n    @ 有\n@else:\n")
    assert "@else" in exc.value.message


def test_elif_缺冒号报错():
    with pytest.raises(GalSyntaxError) as exc:
        parse_text("@set a = 1\n@if a == 1:\n    @ 一\n@elif a == 2\n    @ 二\n")
    assert "@elif" in exc.value.message


def test_else_体内跳转目标校验():
    with pytest.raises(GalSyntaxError) as exc:
        parse_text("@if 1 > 0:\n    @ 有\n@else:\n    @jump 不存在\n")
    assert "不存在" in exc.value.message


def test_else_分支内存档读档还原(tmp_path):
    script = """@label 开始
@set 好感 = 0
@if 好感 > 5:
    @ 高
@else:
    @ 低一
    @ 低二
@end
"""
    rt = _rt(tmp_path, script)
    rt.step()  # @set
    rt.step()  # @if（条件不成立 → 压 else 分支）
    rt.step()  # 低一
    rt.save(1)

    rt2 = Runtime()
    rt2.load_save(1)
    assert rt2.snapshot()["history"][-1]["text"] == "低一"
    assert rt2.step()["text"] == "低二"  # 读档后从 else 体下一条继续


# ==================== T3 @music fadein / fadeout ====================

def test_music_fade_解析():
    ins = parse_text("@music waves fadein=2 fadeout=1.5\n")[0]
    assert ins["track"] == "waves"
    assert ins["fadein"] == 2
    assert ins["fadeout"] == 1.5


def test_music_无参数保持旧行为():
    ins = parse_text("@music waves\n")[0]
    assert "fadein" not in ins and "fadeout" not in ins


@pytest.mark.parametrize("text", [
    "@music waves fade=2\n",      # 未知参数名
    "@music waves fadein=-1\n",   # 负数
    "@music waves fadein=abc\n",  # 非数字
    "@music waves 2\n",           # 裸参数
    "@music\n",                   # 缺音乐名
])
def test_music_fade_参数报错(text):
    with pytest.raises(GalSyntaxError):
        parse_text(text)


def test_music_fade_dump往返():
    prog = parse_text("@music waves fadein=2 fadeout=1.5\n")
    assert dump_text(prog) == "@music waves fadein=2 fadeout=1.5\n"


def test_music_fade_运行事件带参数(tmp_path):
    rt = _rt(tmp_path, "@music waves fadein=2 fadeout=1\n@end\n")
    ev = rt.step()
    assert ev["type"] == "music" and ev["track"] == "waves"
    assert ev["fadein"] == 2 and ev["fadeout"] == 1


def _audio_file(tmp_path, name="a.ogg") -> Path:
    audio = tmp_path / "audio"
    audio.mkdir(exist_ok=True)
    path = audio / name
    path.write_bytes(b"fake-audio")
    return path


def _spy_music(ren, monkeypatch):
    """接管 pygame.mixer.music，记录调用（返回调用记录列表）。"""
    monkeypatch.setattr(ren, "_audio_ok", True)
    calls = []
    monkeypatch.setattr(pygame.mixer.music, "fadeout", lambda ms: calls.append(("fadeout", ms)))
    monkeypatch.setattr(pygame.mixer.music, "load", lambda p: calls.append(("load", str(p))))
    monkeypatch.setattr(pygame.mixer.music, "set_volume", lambda v: None)
    monkeypatch.setattr(pygame.mixer.music, "play",
                        lambda *a, **k: calls.append(("play", k.get("fade_ms"))))
    monkeypatch.setattr(pygame.mixer.music, "stop", lambda: calls.append(("stop", None)))
    return calls


def test_renderer_旧曲淡出后才起新曲(ren, tmp_path, monkeypatch):
    calls = _spy_music(ren, monkeypatch)
    path = _audio_file(tmp_path)
    ren._music = "旧曲"
    ren.play_music("a", fadeout=1.0)
    assert calls == [("fadeout", 1000)]          # 只淡出，暂不加载新曲
    assert ren._pending_music is not None
    ren._pending_music["due"] = 0                # 模拟淡出到点
    ren._update_pending_music()
    assert ("load", str(path)) in calls
    assert calls[-1] == ("play", None)
    assert ren._pending_music is None


def test_renderer_fadein直接淡入(ren, tmp_path, monkeypatch):
    calls = _spy_music(ren, monkeypatch)
    _audio_file(tmp_path)
    ren.play_music("a", fadein=2)
    assert calls[-1] == ("play", 2000)


def test_renderer_无fade参数立即切换(ren, tmp_path, monkeypatch):
    calls = _spy_music(ren, monkeypatch)
    _audio_file(tmp_path)
    ren._music = "旧曲"
    ren.play_music("a")
    assert ("fadeout", 1000) not in calls
    assert calls[-1] == ("play", None)
    assert ren._pending_music is None


# ==================== T4 persistent 全局解锁 ====================

def test_persistent_解锁去重与并集(tmp_path):
    save_api.unlock_cg("cg_a")
    save_api.unlock_cg("cg_a")  # 重复不写
    save_api.unlock_cg("cg_b")
    assert save_api.load_persistent()["gallery"] == ["cg_a", "cg_b"]
    assert save_api.gallery_union(["cg_c", "cg_a"]) == ["cg_a", "cg_b", "cg_c"]
    data = json.loads(Path("saves/persistent.json").read_text(encoding="utf-8"))
    assert data["gallery"] == ["cg_a", "cg_b"]


def test_persistent_文件损坏不崩(tmp_path):
    (tmp_path / "saves").mkdir()
    (tmp_path / "saves/persistent.json").write_text("{坏掉的 json", encoding="utf-8")
    assert save_api.load_persistent() == {"gallery": []}
    assert save_api.gallery_union(["cg_x"]) == ["cg_x"]


def test_cg指令同时写全局解锁(tmp_path):
    rt = _rt(tmp_path, "@cg cg_end1\n@end\n")
    rt.step()
    assert rt.gallery() == ["cg_end1"]                              # 当前档
    assert "cg_end1" in save_api.load_persistent()["gallery"]        # 全局


def test_读档后画廊仍含全局解锁(tmp_path):
    save_api.unlock_cg("cg_旧周目")
    script = """@label 开始
@cg cg_本周目
@end
"""
    rt = _rt(tmp_path, script)
    rt.step()
    rt.save(2)
    rt2 = Runtime()
    rt2.load_save(2)
    assert save_api.gallery_union(rt2.gallery()) == ["cg_旧周目", "cg_本周目"]


# ==================== T1 序幕 splash ====================

def _settings(tmp_path, value) -> str:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"splash": value}), encoding="utf-8")
    return str(path)


def test_splash_无开场脚本返回None(tmp_path):
    script = _write(tmp_path, "@ 你好\n@end\n", "script.gal")
    assert demo._find_splash_script(script, _settings(tmp_path, 1)) is None


def test_splash_有开场脚本返回路径(tmp_path):
    script = _write(tmp_path, "@ 你好\n@end\n", "script.gal")
    splash = _write(tmp_path, "@ 序幕\n@end\n", demo.SPLASH_SCRIPT_NAME)
    assert demo._find_splash_script(script, _settings(tmp_path, 1)) == splash


def test_splash_开关关闭时不播(tmp_path):
    script = _write(tmp_path, "@ 你好\n@end\n", "script.gal")
    _write(tmp_path, "@ 序幕\n@end\n", demo.SPLASH_SCRIPT_NAME)
    assert demo._find_splash_script(script, _settings(tmp_path, 0)) is None


class _FakeRen:
    """序幕驱动用的最小 renderer 假体。"""

    def __init__(self):
        self._cg_showing = None
        self.t0 = 0
        self.complete = True
        self.timeline = timeline.Timeline()  # P30-C-a：序幕停留改挂在时间轴上

    def _now_ms(self):
        return self.t0

    def typewriter_complete(self):
        return self.complete

    # _step 会分发这些演出方法，序幕驱动用假体时留空即可
    def play_sfx(self, *_a, **_k):
        pass

    def play_bg(self, *_a, **_k):  # P33：@bg fadein 分发
        pass

    def play_music(self, *_a, **_k):
        pass

    def play_cg(self, *_a, **_k):
        pass

    def play_camera(self, *_a, **_k):
        pass

    def play_transition(self, *_a, **_k):
        pass


class _FakeRt:
    def __init__(self, events=None):
        self.steps = 0
        self.events = list(events or [])

    def step(self):
        self.steps += 1
        return self.events.pop(0) if self.events else {"type": "say"}


def test_drive_splash_打字机未完成不推进(monkeypatch):
    monkeypatch.setattr(demo, "_SPLASH_HOLD_MS", 0)
    ren, rt = _FakeRen(), _FakeRt()
    ren.complete = False
    state = {"history": [{"text": "台词"}]}
    demo._drive_splash(rt, ren, state)
    assert rt.steps == 0


def test_drive_splash_换景指令推一条后停留(monkeypatch):
    """序幕换景必须被看见：每条 @bg（事件名 scene）推完后停留，不能同帧连切。"""
    monkeypatch.setattr(demo, "_SPLASH_HOLD_MS", 1000)
    ren = _FakeRen()
    rt = _FakeRt([{"type": "scene"}, {"type": "scene"}, {"type": "say"}])
    demo._drive_splash(rt, ren, {})                 # 推第一张背景
    assert rt.steps == 1
    assert ren.timeline.track("splash").dur == 1000  # 停留挂轨
    ren.t0 = 500
    demo._drive_splash(rt, ren, {})
    assert rt.steps == 1                             # 停留中，不换景
    ren.t0 = 1200
    demo._drive_splash(rt, ren, {})
    assert rt.steps == 2 and ren.timeline.track("splash").t0 == 1200


def test_drive_splash_纯声音指令不停留(monkeypatch):
    """@music 这类看不见的指令不需要停留，推完立刻续推。"""
    monkeypatch.setattr(demo, "_SPLASH_HOLD_MS", 10_000)
    ren = _FakeRen()
    rt = _FakeRt([{"type": "music"}, {"type": "scene"}])
    demo._drive_splash(rt, ren, {})
    assert rt.steps == 1 and not ren.timeline.has("splash")      # 音乐不停留
    demo._drive_splash(rt, ren, {})
    assert rt.steps == 2                              # 换景才停
    assert ren.timeline.track("splash").dur == 10000


def test_drive_splash_CG停留后关闭(monkeypatch):
    monkeypatch.setattr(demo, "_SPLASH_CG_HOLD_MS", 1000)
    ren, rt = _FakeRen(), _FakeRt()
    ren._cg_showing = "cg_x"
    demo._drive_splash(rt, ren, {})
    assert rt.steps == 0 and ren.timeline.track("splash").dur == 1000
    ren.t0 = 500
    demo._drive_splash(rt, ren, {})
    assert ren._cg_showing == "cg_x"                  # 停留未到，CG 还挂着
    ren.t0 = 1200
    demo._drive_splash(rt, ren, {})
    assert ren._cg_showing is None and not ren.timeline.has("splash")


def test_drive_splash_演完不再推进():
    ren, rt = _FakeRen(), _FakeRt()
    demo._drive_splash(rt, ren, {"finished": True})
    assert rt.steps == 0


@pytest.mark.slow
def test_demo_启动先加载开场脚本(tmp_path, monkeypatch):
    script = _write(tmp_path, "@ 你好\n@end\n", "script.gal")
    _write(tmp_path, "@ 序幕\n@end\n", demo.SPLASH_SCRIPT_NAME)
    _settings(tmp_path, 1)
    loaded = []
    real_load = Runtime.load

    def spy(self, path):
        loaded.append(path)
        return real_load(self, path)

    monkeypatch.setattr(Runtime, "load", spy)
    monkeypatch.setattr(demo, "_SPLASH_HOLD_MS", 0)
    demo.run(script, assets_root=str(tmp_path), max_frames=120, auto=False)
    assert loaded and loaded[0].endswith(demo.SPLASH_SCRIPT_NAME)


def test_demo_无开场脚本仍从标题起(tmp_path, monkeypatch):
    script = _write(tmp_path, "@ 你好\n@end\n", "script.gal")
    _settings(tmp_path, 1)
    loaded = []
    real_load = Runtime.load

    def spy(self, path):
        loaded.append(path)
        return real_load(self, path)

    monkeypatch.setattr(Runtime, "load", spy)
    demo.run(script, assets_root=str(tmp_path), max_frames=10, auto=False)
    assert loaded == []  # 标题画面不加载剧本（无序幕）


# ==================== T5 打包瘦身 ====================

def test_pack_排除原始素材目录():
    assert "src" in _EXCLUDE_NAMES
