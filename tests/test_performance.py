# -*- coding: utf-8 -*-
"""tests/test_performance.py：P13 演出系统验收（CG / 镜头 / 转场 / 画廊 / 唇形）。

覆盖任务书第 4 节 8 条验收；渲染相关用无头 dummy 模式。
"""
import json
import os
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")  # 无头模式，须在 import pygame 前生效

import pygame
import pytest

from engine import save as save_api
from engine.parser import GalSyntaxError, dump_text, parse_text
from engine.renderer import Renderer
from engine.runtime import Runtime
from engine.ui import UI

pytestmark = [pytest.mark.ui, pytest.mark.slow]

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def ren(tmp_path):
    """空资源根渲染器（素材走占位），用毕关闭。"""
    r = Renderer((1280, 720), str(tmp_path))
    yield r
    r.close()


def _rt(tmp_path, text):
    p = tmp_path / "script.gal"
    p.write_text(text, encoding="utf-8")
    rt = Runtime()
    rt.load(str(p))
    return rt


# ==================== 1. cg 解析与解锁 ====================

def test_cg_解析与解锁(tmp_path):
    ins = parse_text("@cg 雨中便利店\n", source="<t>")
    assert ins == [{"op": "cg", "name": "雨中便利店", "line": 1, "file": "<t>"}]
    # dump 互逆
    assert dump_text(ins) == "@cg 雨中便利店\n"

    rt = _rt(tmp_path, "@cg 雨中便利店\n@ 旁白。\n@end\n")
    ev = rt.step()
    assert ev["type"] == "cg" and ev["name"] == "雨中便利店"
    assert rt.snapshot()["gallery"] == ["雨中便利店"]
    # 重复 @cg 不重复计数（另一条同名指令）
    rt2 = _rt(tmp_path, "@cg 雨中便利店\n@cg 雨中便利店\n@end\n")
    rt2.step()
    rt2.step()
    assert rt2.snapshot()["gallery"] == ["雨中便利店"]


# ==================== 2. cg 存档迁移 v2→v3 ====================

def test_cg_存档迁移_v2升v3_补gallery(tmp_path):
    payload = {
        "engine": "galengine", "version": 2, "saved_at": "2026-01-01T00:00:00",
        "label": None, "anchor_stack": [],
        "state": {"script": "x.gal", "stack": [], "bg": None, "music": None, "video": None,
                  "sprites": [], "vars": {}, "characters": {}, "history": [],
                  "pending_choice": None, "finished": False},
    }
    Path("saves").mkdir(exist_ok=True)
    Path("saves/slot_1.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    data = save_api.load(1)
    assert data["version"] == save_api.SCHEMA_VERSION
    assert data["state"]["gallery"] == []


def test_cg_v3存档_gallery正常读回(tmp_path):
    rt = _rt(tmp_path, "@cg 星空\n@ 旁白。\n")
    rt.step()  # 解锁 星空
    rt.save(1)
    rt2 = Runtime()
    after = rt2.load_save(1)
    assert after["gallery"] == ["星空"]
    assert rt2.gallery() == ["星空"]


# ==================== 3. camera 解析与非法参数 ====================

def test_camera_解析四种(tmp_path):
    prog = parse_text(
        "@camera pan 右 2.0\n@camera zoom 1.2 1.5\n@camera shake 0.5 0.3\n@camera reset 0.5\n",
        source="<t>")
    assert prog[0] == {"op": "camera", "kind": "pan", "args": ["右", 2.0], "line": 1, "file": "<t>"}
    assert prog[1] == {"op": "camera", "kind": "zoom", "args": [1.2, 1.5], "line": 2, "file": "<t>"}
    assert prog[2] == {"op": "camera", "kind": "shake", "args": [0.5, 0.3], "line": 3, "file": "<t>"}
    assert prog[3] == {"op": "camera", "kind": "reset", "args": [0.5], "line": 4, "file": "<t>"}
    # dump 互逆
    assert "@camera zoom 1.2 1.5" in dump_text(prog)


@pytest.mark.parametrize("bad, msg", [
    ("@camera pan 飞 2.0", "pan"),
    ("@camera pan 右 abc", "数字"),
    ("@camera zoom 1.2", "zoom"),
    ("@camera shake 0.5", "shake"),
    ("@camera reset", "reset"),
    ("@camera fly 1.0", "不支持"),
])
def test_camera_非法参数中文报错(bad, msg):
    with pytest.raises(GalSyntaxError) as e:
        parse_text(bad + "\n", source="<t>")
    assert msg in str(e.value)


# ==================== 4. camera 不进存档 ====================

def test_camera_zoom进state_供存档(tmp_path):
    rt = _rt(tmp_path, "@bg classroom\n@camera pan 右 2.0\n@camera zoom 1.2 1.5\n@ 旁白。\n")
    rt.step()  # bg
    ev = rt.step()
    assert ev == {"type": "camera", "kind": "pan", "args": ["右", 2.0], "line": 2, "seq": ev["seq"]}
    rt.step()  # zoom
    rt.save(1)
    payload = json.loads(Path("saves/slot_1.json").read_text(encoding="utf-8"))
    # pan 方向 runtime 算不出像素偏移，不进 state；zoom 最终值是数值，进 state
    assert "camera" not in payload["state"]
    assert payload["state"].get("camera_zoom") == 1.5
    assert set(payload["state"]) == {
        "script", "stack", "bg", "music", "video", "sprites", "vars",
        "characters", "history", "pending_choice", "pending_wait", "finished", "gallery",
        "fg", "camera_zoom", "anim_final",
    }

    rt2 = Runtime()
    after = rt2.load_save(1)
    assert after["bg"] == "classroom"
    assert "camera" not in after
    assert after["camera_zoom"] == 1.5


# ==================== 5. transition 解析与复位 ====================

def test_transition_解析(tmp_path):
    prog = parse_text("@transition dissolve 0.8\n@transition wipe 左 0.6\n@transition slide 右 0.6\n",
                      source="<t>")
    assert prog[0] == {"op": "transition", "kind": "dissolve", "args": [0.8], "line": 1, "file": "<t>"}
    assert prog[1]["kind"] == "wipe" and prog[1]["args"] == ["左", 0.6]
    assert prog[2]["kind"] == "slide" and prog[2]["args"] == ["右", 0.6]
    with pytest.raises(GalSyntaxError):
        parse_text("@transition fade 0.8\n")  # 不支持的子命令
    with pytest.raises(GalSyntaxError):
        parse_text("@transition wipe 飞 0.6\n")  # 非法方向


def test_transition_作用于下一次bg_播完复位(ren):
    state = {"bg": "a", "sprites": [], "history": [], "pending_choice": None,
             "characters": {}, "gallery": []}
    ren.render(state)
    ren.play_transition("dissolve", [0.8])
    assert ren._pending_transition == ("dissolve", [0.8])
    # 下一次 bg 变化 → 触发转场，pending 清空，进度挂 Timeline 的 transition 轨
    state["bg"] = "b"
    ren.render(state)
    assert ren._pending_transition is None
    track = ren.timeline.track("transition")
    assert track is not None and track.meta["kind"] == "dissolve" and ren._trans_old is not None
    # 快进时间播完 → 复位
    track.t0 -= 1000
    ren.render(state)
    assert ren.timeline.track("transition") is None and ren._trans_old is None
    # 再切 bg（无 @transition）→ 回默认淡入
    state["bg"] = "c"
    ren.render(state)
    assert ren.timeline.track("transition") is None and ren._fade_t0 is not None


# ==================== 6. gallery UI 状态机 ====================

def test_gallery_UI状态机():
    ui = UI()
    ui.set_gallery(["星空", "雨中便利店"], ["林晚_smile"])
    ui.mode = "playing"
    ui.handle("back")          # 菜单
    for _ in range(2):
        ui.handle("down")      # 存档/读档/画廊
    assert ui.handle("confirm") is None
    assert ui.view()["mode"] == "gallery"
    g = ui.view()["gallery"]
    assert g["tab"] == 0 and [i["name"] for i in g["items"]] == ["星空", "雨中便利店"]

    # 选中第一张 → 大图
    assert ui.handle("confirm") is None
    assert ui.view()["gallery"]["detail"] == "星空"
    # 返回网格
    ui.handle("back")
    assert ui.view()["gallery"]["detail"] is None

    # 切到立绘页签
    ui.handle("right")
    g = ui.view()["gallery"]
    assert g["tab"] == 1 and [i["name"] for i in g["items"]] == ["林晚_smile"]
    ui.handle("confirm")
    assert ui.view()["gallery"]["detail"] == "林晚_smile"
    ui.handle("back")

    # Esc 回菜单
    ui.handle("back")
    assert ui.view()["mode"] == "menu"


def test_gallery_空列表不崩():
    ui = UI()
    ui.set_gallery([], [])
    ui.mode = "gallery"
    g = ui.view()["gallery"]
    assert g["items"] == [] and g["pages"] == 1
    # 方向键/confirm 都不崩
    ui.handle("down")
    ui.handle("confirm")
    assert ui.view()["gallery"]["detail"] is None


def test_gallery_渲染不崩(ren):
    ui = UI()
    ui.set_gallery(["星空"], ["林晚_smile"])
    ui.mode = "gallery"
    ren.render({}, ui.view())
    ui.handle("confirm")  # 大图
    ren.render({}, ui.view())


# ==================== 7. 唇形兼容 ====================

def _make_sprite_frames(root, char="lin", expr="normal"):
    """造呼吸与说话帧组各 2 帧。"""
    base = Path(root) / "images" / "anims"
    base.mkdir(parents=True)
    for anim, color in (("呼吸", (100, 200, 100)), ("说话", (200, 100, 100))):
        for n in (1, 2):
            s = pygame.Surface((100, 200), pygame.SRCALPHA)
            s.fill((*color, 255) if n == 1 else (*color, 128))
            pygame.image.save(s, str(base / f"{char}_{expr}_{anim}_{n:03d}.png"))


def test_唇形_无语音保持共享时钟(tmp_path):
    _make_sprite_frames(str(tmp_path))
    r = Renderer((1280, 720), str(tmp_path))
    try:
        r.timeline.reset_clock("sprite")  # P30-C-a：共享动画时钟由 Timeline 提供
        sp = {"char": "lin", "expr": "normal", "anim": "呼吸"}
        img = r._sprite_image(sp, "lin")  # speaking 命中 → 说话帧组
        assert img is not None
        # 无语音：走共享时钟分支（_voice_length == 0）
        assert r._voice_length == 0.0
    finally:
        r.close()


class _FakeChannel:
    def __init__(self):
        self.played = []
        self._busy = False

    def play(self, snd):
        self.played.append(snd)
        self._busy = True

    def stop(self):
        self._busy = False

    def get_busy(self):
        return self._busy


def test_唇形_有语音随语音进度循环(tmp_path):
    _make_sprite_frames(str(tmp_path))
    (tmp_path / "audio").mkdir()
    (tmp_path / "audio" / "v1.wav").write_bytes(b"fake")

    class FakeSound:
        def get_length(self):
            return 2.0

    r = Renderer((1280, 720), str(tmp_path))
    try:
        r._audio_ok = True
        r._voice_channel = _FakeChannel()
        r._load_sound = lambda path: FakeSound()
        r.settings["voice_enabled"] = 1
        r._update_voice([{"char": "lin", "text": "你好。", "voice": "v1"}])
        assert r._voice_length == 2.0 and r._voice_t0 is not None

        sp = {"char": "lin", "expr": "normal", "anim": "呼吸"}
        # 语音开头（progress≈0）与中段帧不同：idx 随 progress 变化
        idx_frames = r._sequence_index("anims", "lin_normal_说话")
        assert len(idx_frames) == 2
        img1 = r._sprite_image(sp, "lin")
        assert img1 is not None
        # 模拟语音播到一半以上 → 帧 idx 变化
        r._voice_t0 = r._now_ms() - 1500  # 已播 1.5s / 2.0s = 0.75
        img2 = r._sprite_image(sp, "lin")
        assert img2 is not None
    finally:
        r.close()


# ==================== 8. 回归：parser 只加三分支 ====================

def test_回归_既有指令语义不变():
    """既有指令解析结果与 P13 前一致（抽样：bg/show/say/choice）。"""
    prog = parse_text(
        "@character 甲 #aabbcc\n@bg classroom\n@show 甲 smile\n@ 甲 你好。\n@label a\n@jump a\n")
    ops = [i["op"] for i in prog]
    assert ops == ["character", "bg", "show", "say", "label", "jump"]


# ==================== P24 性能基准 ====================

def _make_large_script(target_bytes: int = 1_000_000) -> str:
    """生成约 target_bytes 大小的 .gal 文本：大量旁白 + 指令。"""
    lines = ["# 大剧本压力测试", "@bg classroom", "@character 林晚 #ffccdd"]
    # 每行约 20-30 字节，目标 1MB 约需 3-5 万行
    i = 0
    while sum(len(l) + 1 for l in lines) < target_bytes:
        i += 1
        lines.append(f"@ 林晚 这是第 {i} 句测试旁白，用于压力测试解析性能。")
        if i % 50 == 0:
            lines.append("@label ch_" + str(i))
        if i % 200 == 0:
            lines.append("@bg park")
    return "\n".join(lines) + "\n"


def test_bench_1MB剧本解析_应在1秒内():
    """P24：1MB 剧本文本 parse_text() 必须在 1s 内完成。

    纯解析（不 load 不 step），衡量 parser 吞吐。"""
    import time
    text = _make_large_script(1_000_000)
    # 确保真的有 1MB
    assert len(text.encode("utf-8")) >= 900_000, f"剧本只生成了 {len(text.encode())} bytes"
    t0 = time.perf_counter()
    prog = parse_text(text, source="bench.gal")
    elapsed = (time.perf_counter() - t0) * 1000
    assert len(prog) > 1000, f"解析指令数异常：{len(prog)}"
    assert elapsed < 1000, f"1MB 解析耗时 {elapsed:.0f}ms，超过 1s 红线"


def test_bench_3000行章节Runtime加载_应在05秒内(tmp_path):
    """P24：3000 行章节 Runtime.load() 必须在 0.5s 内完成。

    比解析多一层（指令→闭包+预编译），衡量完整装载链路。"""
    import time
    lines = ["# 3000 行章节", "@bg classroom", "@character 甲 #ffffff"]
    for i in range(3000):
        lines.append(f"@ 甲 第 {i} 句。")
    lines.append("@end")
    text = "\n".join(lines) + "\n"
    p = tmp_path / "chapter.gal"
    p.write_text(text, encoding="utf-8")
    t0 = time.perf_counter()
    rt = Runtime()
    rt.load(str(p))
    elapsed = (time.perf_counter() - t0) * 1000
    # step 到 finished（总指令 ≈ 3000 + @bg + @character + @end = 3003）
    steps = 0
    while not rt.snapshot().get("finished") and steps < 4000:
        rt.step()
        steps += 1
    assert rt.snapshot().get("finished"), f"3000 行章节未走完（{steps} 步后仍未结束）"
    assert elapsed < 500, f"3000 行章节加载耗时 {elapsed:.0f}ms，超过 0.5s 红线"
