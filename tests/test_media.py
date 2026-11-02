# -*- coding: utf-8 -*-
"""tests/test_media.py：P11 媒体增强验收。

配音 @voice / 帧序列视频 @video / 动画立绘 show.anim / 存档 v1→v2 迁移 /
渲染层资源管理（LRU + 帧滑动窗口 + BGM 流式）。无头 dummy 模式。
"""
import json
import os
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")  # 无头模式，须在 import pygame 前生效

import pygame
import pytest

from engine import save as save_api
from engine.demo import run
from engine.parser import GalSyntaxError, dump_text, parse_text
from engine.renderer import FRAME_WINDOW, Renderer
from engine.runtime import Runtime
from engine.save import SaveError

pytestmark = [pytest.mark.ui]


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


def _write_script(tmp_path, script: str, name="media.gal") -> str:
    path = tmp_path / name
    path.write_text(script, encoding="utf-8")
    return str(path)


def _make_rt(tmp_path, script: str) -> Runtime:
    rt = Runtime()
    rt.load(_write_script(tmp_path, script))
    return rt


def _png(root, relpath, color=(120, 60, 60)) -> str:
    """生成一张真实 PNG，返回绝对路径。"""
    path = Path(root) / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    surf = pygame.Surface((64, 48), pygame.SRCALPHA)
    surf.fill(color)
    pygame.image.save(surf, str(path))
    return str(path)


def _counting_load(monkeypatch):
    """给 pygame.image.load 装计数器，返回调用路径列表。"""
    calls = []
    real = pygame.image.load

    def spy(path, *a, **k):
        calls.append(str(path))
        return real(path, *a, **k)

    monkeypatch.setattr(pygame.image, "load", spy)
    return calls


class _FakeChannel:
    """可控时长的假声道：busy 由测试直接拨动。"""

    def __init__(self):
        self.busy = False
        self.played = []

    def play(self, snd):
        self.played.append(snd)
        self.busy = True

    def get_busy(self):
        return self.busy

    def stop(self):
        self.busy = False


# ==================== 1. voice 解析与合并 ====================

def test_voice_解析与合并进say事件(tmp_path):
    prog = parse_text("@character 林晚 #aaccff\n@ 林晚 你来了。\n@voice 林晚_你来了\n"
                      "@ 深夜的便利店。\n@voice 旁白_深夜\n")
    assert [i["op"] for i in prog] == ["character", "say", "voice", "say", "voice"]
    assert prog[2]["op"] == "voice" and prog[2]["sound"] == "林晚_你来了" and prog[2]["line"] == 3

    rt = _make_rt(tmp_path, "@character 林晚 #aaccff\n@ 林晚 你来了。\n@voice 林晚_你来了\n"
                            "@ 深夜的便利店。\n@voice 旁白_深夜\n")
    ev = rt.step()  # say（紧跟的 @voice 被同一步合并消费）
    assert ev["type"] == "say" and ev["voice"] == "林晚_你来了"
    snap = rt.snapshot()
    assert snap["history"][-1] == {"char": "林晚", "text": "你来了。", "voice": "林晚_你来了"}
    ev2 = rt.step()  # 旁白配音
    assert ev2["voice"] == "旁白_深夜"
    assert rt.snapshot()["history"][-1] == {"char": None, "text": "深夜的便利店。", "voice": "旁白_深夜"}


def test_voice_dump_text还原(tmp_path):
    text = "@character 林晚 #aaccff\n@ 林晚 你来了。\n@voice 林晚_你来了\n"
    prog = parse_text(text)
    dumped = dump_text(prog)
    assert "@voice 林晚_你来了" in dumped.splitlines()
    prog2 = parse_text(dumped)
    assert [(i["op"], i.get("sound")) for i in prog2] == [(i["op"], i.get("sound")) for i in prog]


# ==================== 2. voice 报错 ====================

def test_voice_不紧跟台词报错():
    with pytest.raises(GalSyntaxError, match="紧跟在一条台词之后"):
        parse_text("@voice 林晚_你来了\n@ 林晚 你来了。\n")  # 首条即 voice
    with pytest.raises(GalSyntaxError, match="紧跟在一条台词之后"):
        parse_text("@bg classroom\n@voice x\n")  # 前一条是 bg
    with pytest.raises(GalSyntaxError, match="紧跟在一条台词之后"):
        parse_text("@ 林晚 你来了。\n@set x = 1\n@voice x\n")  # 中间隔了指令
    with pytest.raises(GalSyntaxError, match="紧跟在一条台词之后"):
        parse_text("@if x == 1:\n    @voice x\n")  # if 块内首条（上一句在块外不算紧跟）


# ==================== 3. voice 存档 ====================

def test_voice_存档读档后保留(tmp_path):
    rt = _make_rt(tmp_path, "@character 林晚 #aaccff\n@ 林晚 你来了。\n@voice 林晚_你来了\n@ 下一句。\n")
    rt.step()
    rt.save(1)
    rt2 = Runtime()
    snap = rt2.load_save(1)
    assert snap["history"][-1]["voice"] == "林晚_你来了"
    # 读档后继续推进，事件序列不受影响
    assert rt2.step()["text"] == "下一句。"


# ==================== 4. video 解析与切换 ====================

def test_video_解析与bg切换清除(tmp_path):
    prog = parse_text("@video 雨夜\n@video 雪 fps=24\n@bg classroom\n")
    assert prog[0]["op"] == "video" and prog[0]["name"] == "雨夜" and prog[0]["fps"] == 30
    assert prog[1]["fps"] == 24

    rt = _make_rt(tmp_path, "@video 雨夜 fps=24\n@ 旁白。\n@bg classroom\n")
    ev = rt.step()
    assert ev == {"type": "video", "name": "雨夜", "fps": 24, "line": 1, "seq": 1}
    assert rt.snapshot()["video"] == {"name": "雨夜", "fps": 24}
    rt.step()  # say
    assert rt.snapshot()["video"] == {"name": "雨夜", "fps": 24}  # 台词不影响视频
    rt.step()  # @bg → 清除视频
    assert rt.snapshot()["bg"] == "classroom"
    assert rt.snapshot()["video"] is None


def test_video_参数报错():
    with pytest.raises(GalSyntaxError, match="fps=正整数"):
        parse_text("@video 雨夜 fps=0\n")
    with pytest.raises(GalSyntaxError, match="fps=正整数"):
        parse_text("@video 雨夜 fps=abc\n")
    with pytest.raises(GalSyntaxError, match="@video 需要 1 个参数"):
        parse_text("@video\n")
    with pytest.raises(GalSyntaxError, match="@video 需要 1 个参数"):
        parse_text("@video 雨夜 fps=24 多余参数\n")


def test_video_dump_text还原():
    prog = parse_text("@video 雨夜\n@video 雪 fps=24\n")
    lines = dump_text(prog).splitlines()
    assert "@video 雨夜" in lines        # 默认 30 帧不冗余输出
    assert "@video 雪 fps=24" in lines
    prog2 = parse_text(dump_text(prog))
    assert [(i["op"], i.get("name"), i.get("fps")) for i in prog2] == \
           [("video", "雨夜", 30), ("video", "雪", 24)]


# ==================== 5. show anim ====================

def test_show_anim_解析与状态(tmp_path):
    rt = _make_rt(tmp_path, "@character 林晚 #aaccff\n@show 林晚 smile anim=walk\n@show 林晚 happy\n")
    ev = rt.step()
    assert ev["type"] == "show" and ev["anim"] == "walk"
    assert rt.snapshot()["sprites"] == [{"char": "林晚", "expr": "smile", "anim": "walk"}]
    rt.step()  # 默认 anim=呼吸
    assert rt.snapshot()["sprites"] == [{"char": "林晚", "expr": "happy", "anim": "呼吸"}]


def test_show_anim_参数报错与还原():
    with pytest.raises(GalSyntaxError, match="anim=动画名"):
        parse_text("@show 林晚 smile walk\n")  # 第三参数必须是 anim=xxx
    prog = parse_text("@show 林晚 smile anim=walk\n@show 林晚 happy\n")
    lines = dump_text(prog).splitlines()
    assert "@show 林晚 smile anim=walk" in lines
    assert "@show 林晚 happy" in lines  # 默认“呼吸”不冗余输出


# ==================== 6. renderer 全流程不崩 ====================

def test_renderer_媒体全流程不崩(tmp_path):
    """voice/video/anim 全部走占位与静音路径：dummy 模式跑通，无异常。"""
    _write_script(tmp_path, "@character 林晚 #aaccff\n@video 雨夜\n@show 林晚 smile anim=walk\n"
                            "@ 林晚 你来了。\n@voice 林晚_你来了\n@bg classroom\n@end\n")
    run(str(tmp_path / "media.gal"), assets_root=str(tmp_path), max_frames=30)


def test_renderer_视频缺帧走占位并警告一次(tmp_path, capsys):
    r = Renderer((1280, 720), str(tmp_path))
    try:
        state = {"bg": None, "video": {"name": "不存在", "fps": 30}, "sprites": [], "history": []}
        r.render(state)
        r.render(state)  # 第二次渲染不重复警告
        err = capsys.readouterr().err
        assert err.count("没有帧序列") == 1
    finally:
        r.close()


# ==================== 7. 语音等待（voice_auto_advance） ====================

def _voice_state():
    return {"bg": None, "sprites": [],
            "history": [{"char": "林晚", "text": "你来了。", "voice": "林晚_你来了"}],
            "pending_choice": None}


def test_语音等待_播完前advance被拦(ren, tmp_path, monkeypatch):
    (tmp_path / "audio").mkdir()
    (tmp_path / "audio" / "林晚_你来了.wav").write_bytes(b"fake")  # 只供 resolve 找到
    fake = _FakeChannel()
    ren._audio_ok = True
    ren._voice_channel = fake
    monkeypatch.setattr(ren, "_load_sound", lambda path: object())  # 不真的解码
    ren.settings["voice_auto_advance"] = 1
    ren.settings["voice_enabled"] = 1

    ren.render(_voice_state())
    assert len(fake.played) == 1 and fake.busy  # 配音起播
    ren.reveal_all()  # 打字机已完成，只剩语音未播完
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE))
    assert ren.handle_input() == {"action": "none"}  # 语音未播完：advance 被拦

    fake.busy = False  # 语音播完
    assert ren.handle_input() == {"action": "advance"}  # 无输入也自动推进


def test_语音等待_开关关闭时不拦(ren, tmp_path, monkeypatch):
    (tmp_path / "audio").mkdir()
    (tmp_path / "audio" / "林晚_你来了.wav").write_bytes(b"fake")
    fake = _FakeChannel()
    ren._audio_ok = True
    ren._voice_channel = fake
    monkeypatch.setattr(ren, "_load_sound", lambda path: object())
    ren.settings["voice_auto_advance"] = 0  # 关：玩家自由推进

    ren.render(_voice_state())
    ren.reveal_all()
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE))
    assert ren.handle_input() == {"action": "advance"}  # 语音还在播也不拦


def test_配音开关关闭时不播放(ren, tmp_path, monkeypatch):
    fake = _FakeChannel()
    ren._audio_ok = True
    ren._voice_channel = fake
    monkeypatch.setattr(ren, "_load_sound", lambda path: object())
    ren.settings["voice_enabled"] = 0
    ren.render(_voice_state())
    assert fake.played == []


# ==================== 8. 版本迁移 v1→v2 ====================

def test_存档迁移_v1升v2_补默认值(tmp_path):
    payload = {
        "engine": "galengine", "version": 1, "saved_at": "2026-01-01T00:00:00",
        "label": None, "anchor_stack": [],
        "state": {"script": "x.gal", "stack": [], "bg": "classroom", "music": None,
                  "sprites": [{"char": "lin", "expr": "normal"}], "vars": {},
                  "characters": {}, "history": [], "pending_choice": None, "finished": False},
    }
    Path("saves").mkdir()
    Path("saves/slot_1.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    data = save_api.load(1)
    assert data["version"] == save_api.SCHEMA_VERSION  # v1→v2→v3→（补⑨）→v4
    assert data["state"]["video"] is None
    assert data["state"]["sprites"] == [{"char": "lin", "expr": "normal", "anim": "呼吸"}]
    assert data["state"]["gallery"] == []
    assert data["state"]["bg"] == "classroom"  # 既有数据不动


def test_存档迁移_未来版本拦截(tmp_path):
    rt = _make_rt(tmp_path, "@ 旁白。\n")
    Path("saves").mkdir()
    Path("saves/slot_3.json").write_text(json.dumps({
        "engine": "galengine", "version": save_api.SCHEMA_VERSION + 1, "saved_at": "2026-01-01T00:00:00",
        "label": None, "state": rt.snapshot(), "anchor_stack": [],
    }, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(SaveError, match="更新的引擎版本"):
        save_api.load(3)


# ==================== 9. 动画立绘 ====================

def test_立绘_呼吸与说话帧组切换(ren, tmp_path, monkeypatch):
    calls = _counting_load(monkeypatch)
    # 呼吸 2 帧 + 说话 1 帧
    _png(tmp_path, "images/anims/林晚_smile_呼吸_001.png", (200, 100, 100, 255))
    _png(tmp_path, "images/anims/林晚_smile_呼吸_002.png", (180, 100, 100, 255))
    _png(tmp_path, "images/anims/林晚_smile_说话_001.png", (100, 200, 100, 255))
    sprite = {"char": "林晚", "expr": "smile", "anim": "呼吸"}

    # 台词打字机进行中 → 说话帧组
    state = {"bg": None, "sprites": [sprite], "pending_choice": None,
             "history": [{"char": "林晚", "text": "这是一句足够长的台词，打字机不会立刻放完。"}]}
    ren.render(state)
    assert any("_说话_" in p for p in calls)

    # 打字机放完 → 回到呼吸帧组
    calls.clear()
    ren.reveal_all()
    ren.render(state)
    assert any("_呼吸_" in p for p in calls)
    assert not any("_说话_" in p for p in calls)


def test_立绘_缺说话帧保持当前动画(ren, tmp_path, monkeypatch):
    calls = _counting_load(monkeypatch)
    _png(tmp_path, "images/anims/林晚_smile_呼吸_001.png")
    sprite = {"char": "林晚", "expr": "smile", "anim": "呼吸"}
    state = {"bg": None, "sprites": [sprite], "pending_choice": None,
             "history": [{"char": "林晚", "text": "说话时没有说话帧组，保持呼吸。"}]}
    ren.render(state)  # 打字机未完，但无“说话”帧组 → 不切
    assert any("_呼吸_" in p for p in calls)
    assert not any("_说话_" in p for p in calls)


def test_立绘_缺动画帧回退静态立绘(ren, tmp_path, monkeypatch):
    calls = _counting_load(monkeypatch)
    static = _png(tmp_path, "images/林晚_smile.png")
    sprite = {"char": "林晚", "expr": "smile", "anim": "呼吸"}
    ren.render({"bg": None, "sprites": [sprite], "history": [], "pending_choice": None})
    assert static in calls


# ==================== 10. 资源管理（20GB 级） ====================

def test_资源_同一张图只加载一次(ren, tmp_path, monkeypatch):
    calls = _counting_load(monkeypatch)
    bg = _png(tmp_path, "images/classroom.png")
    state = {"bg": "classroom", "sprites": [], "history": []}
    ren.render(state)
    ren.render(state)
    ren.render(state)
    assert calls.count(bg) == 1  # 缓存命中，不重复加载


def test_资源_LRU超限释放最久未用(ren, tmp_path, monkeypatch):
    calls = _counting_load(monkeypatch)
    ren._img_cache_max = 2
    paths = [_png(tmp_path, f"images/bg{i}.png") for i in range(3)]
    for i in range(3):
        ren.render({"bg": f"bg{i}", "sprites": [], "history": []})
    assert paths[0] not in ren._img_cache  # 最久未用被释放
    ren.render({"bg": "bg0", "sprites": [], "history": []})
    assert calls.count(paths[0]) == 2  # 再次用到 → 重新加载


def test_资源_播放中的图片不被LRU释放(ren, tmp_path, monkeypatch):
    _counting_load(monkeypatch)
    ren._img_cache_max = 2
    _png(tmp_path, "images/bg1.png")
    _png(tmp_path, "images/bg2.png")
    sp = _png(tmp_path, "images/lin_normal.png")
    sprite = {"char": "lin", "expr": "normal"}
    ren.render({"bg": "bg1", "sprites": [sprite], "history": []})
    ren.render({"bg": "bg2", "sprites": [sprite], "history": []})  # bg1 被挤出
    assert sp in ren._img_cache  # 仍在显示的立绘每帧被取用，保持最新不被释放


def test_资源_帧序列滑动窗口(ren, tmp_path, monkeypatch):
    calls = _counting_load(monkeypatch)
    # 20 帧视频：窗口外帧必须释放，内存中本序列帧 ≤ 2*FRAME_WINDOW+1
    for i in range(1, 21):
        _png(tmp_path, f"images/videos/雨夜_{i:03d}.png", (i * 10 % 255, 60, 60))
    t = [0]
    monkeypatch.setattr(ren, "_now_ms", lambda: t[0])
    state = {"bg": None, "video": {"name": "雨夜", "fps": 30}, "sprites": [], "history": []}
    window_max = 2 * FRAME_WINDOW + 1
    for _ in range(12):  # 播放约 1.1 秒，跨越多帧
        ren.render(state)
        seq_cached = [p for p in ren._img_cache if f"videos{os.sep}雨夜_" in p]
        assert len(seq_cached) <= window_max
        # 当前帧一定在缓存里（播放中的资源不释放）
        idx = int(t[0] / 1000.0 * 30) % 20
        assert str(Path(tmp_path) / "images" / "videos" / f"雨夜_{idx + 1:03d}.png") in ren._img_cache
        t[0] += 100


def test_资源_BGM走mixer_music流式(ren, tmp_path, monkeypatch):
    (tmp_path / "audio").mkdir()
    (tmp_path / "audio" / "bgm_main.ogg").write_bytes(b"fake")
    loaded = []
    sounds = []
    ren._audio_ok = True
    monkeypatch.setattr(pygame.mixer.music, "load", lambda p: loaded.append(str(p)))
    monkeypatch.setattr(pygame.mixer.music, "play", lambda *a, **k: None)
    monkeypatch.setattr(pygame.mixer.music, "set_volume", lambda v: None)
    monkeypatch.setattr(pygame.mixer, "Sound", lambda p: sounds.append(str(p)))
    ren.render({"bg": None, "music": "bgm_main", "sprites": [], "history": []})
    assert loaded and loaded[0].endswith("bgm_main.ogg")  # 流式加载
    assert not any("bgm_main" in s for s in sounds)       # 不走 Sound 全量加载


def test_资源_帧序列支持webp(tmp_path):
    r = Renderer((1280, 720), str(tmp_path))
    try:
        _png(tmp_path, "images/videos/雨_001.png")
        # webp 帧也能被索引（与 png 同优先级查找）
        (tmp_path / "images" / "videos" / "雪_001.webp").write_bytes(b"fake")
        assert len(r._sequence_index("videos", "雨")) == 1
        assert r._sequence_index("videos", "雪")[0].endswith(".webp")
        assert r._sequence_index("videos", "无") == []
    finally:
        r.close()
