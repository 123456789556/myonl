# -*- coding: utf-8 -*-
"""P28 引擎层验收：E1 画廊锁格 / E2 序幕镜头停留 / E3 幻灯片 / E5 字符串变量。

E4（存档底部留白）是纯视觉项，由 screenshots/p28_* 人工复核，不新增用例。
"""
import json
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")  # 无头模式，须在 import pygame 前生效

import pygame
import pytest

from engine import data, demo, timeline
from engine.parser import dump_text, parse_text
from engine.renderer import CAM_ZOOM_SECONDS, Renderer
from engine.runtime import Runtime
from engine.ui import GALLERY_SLIDE_MS, UI

pytestmark = [pytest.mark.ui]

CELLS = [
    {"name": "cg_dark", "images": ["bg_beach2", "bg_beach1b"]},
    {"name": "cg_dawn", "images": ["bg_dawn1"]},
    {"name": "cg_end1", "images": ["bg_moonpic", "bg_girlpic", "bg_badending"]},
    {"name": "cg_end2", "images": []},
]


# ==================== E1/E3：配置解析 ====================

def test_load_gallery_config_缺省返回空(tmp_path):
    assert data.load_gallery_config(str(tmp_path)) == []


def test_load_gallery_config_正常映射与备注字段(tmp_path):
    (tmp_path / data.GALLERY_CONFIG_NAME).write_text(json.dumps({
        "_说明": "备注不参与格子",
        "cg_dark": ["bg_beach2", "bg_dawn1"],
        "cg_end1": "bg_moonpic",
        "坏值": 123,
    }, ensure_ascii=False), encoding="utf-8")
    cells = data.load_gallery_config(str(tmp_path))
    assert [c["name"] for c in cells] == ["cg_dark", "cg_end1"]
    assert cells[0]["images"] == ["bg_beach2", "bg_dawn1"]
    assert cells[1]["images"] == ["bg_moonpic"]  # 单字符串兼容成单图序列


def test_load_gallery_config_损坏与非法顶层(tmp_path):
    path = tmp_path / data.GALLERY_CONFIG_NAME
    path.write_text("{不是 JSON", encoding="utf-8")
    assert data.load_gallery_config(str(tmp_path)) == []
    path.write_text("[1, 2]", encoding="utf-8")
    assert data.load_gallery_config(str(tmp_path)) == []


# ==================== E1：锁格 ====================

def _gallery_ui(unlocked=("cg_dark",)):
    ui = UI()
    ui.set_gallery_config(CELLS)
    ui.set_gallery(list(unlocked), [])
    ui.mode = "playing"
    ui.handle("back")                       # 进菜单
    ui.handle("down"); ui.handle("down")   # 光标移到"画廊"
    ui.handle("confirm")
    return ui


def test_画廊固定格子_未解锁标记与锁格提示():
    ui = _gallery_ui(unlocked=("cg_dark",))
    v = ui.view(now_ms=0)["gallery"]
    assert [it["name"] for it in v["items"]] == [c["name"] for c in CELLS]
    assert [it["unlocked"] for it in v["items"]] == [True, False, False, False]
    assert v["locked_selected"] is False   # 光标在第一格（已解锁）


def test_画廊光标移到锁格_回车不进入大图():
    ui = _gallery_ui(unlocked=("cg_dark",))
    ui._cursor = 1                         # 第二格 cg_dawn：未解锁
    v = ui.view(now_ms=0)["gallery"]
    assert v["locked_selected"] is True
    assert ui.handle("confirm") is None
    assert ui.view(now_ms=0)["gallery"]["detail"] is None


def test_画廊无配置_保持只列已解锁旧行为():
    ui = UI()
    ui.set_gallery(["cg_x", "cg_y"], [])
    ui.mode = "gallery"
    v = ui.view(now_ms=0)["gallery"]
    assert [it["name"] for it in v["items"]] == ["cg_x", "cg_y"]
    assert all(it["unlocked"] for it in v["items"])
    assert v["locked_selected"] is False


# ==================== E3：幻灯片 ====================

def test_幻灯片自动切换与循环():
    ui = _gallery_ui(unlocked=("cg_end1",))
    ui._cursor = 2                          # cg_end1（3 张）
    ui.handle("confirm")
    v = ui.view(now_ms=1000)["gallery"]
    assert v["detail"] == "cg_end1" and v["detail_index"] == 0
    assert len(v["detail_images"]) == 3
    v = ui.view(now_ms=1000 + GALLERY_SLIDE_MS)["gallery"]
    assert v["detail_index"] == 1
    v = ui.view(now_ms=1000 + GALLERY_SLIDE_MS * 2)["gallery"]
    assert v["detail_index"] == 2
    v = ui.view(now_ms=1000 + GALLERY_SLIDE_MS * 3)["gallery"]
    assert v["detail_index"] == 0            # 循环


def test_幻灯片手动左右切换并重置计时():
    ui = _gallery_ui(unlocked=("cg_end1",))
    ui._cursor = 2
    ui.handle("confirm")
    ui.view(now_ms=0)
    ui.handle("right")
    v = ui.view(now_ms=10)["gallery"]
    assert v["detail_index"] == 1
    ui.handle("left")
    v = ui.view(now_ms=20)["gallery"]
    assert v["detail_index"] == 0
    # 手动切换后计时重置：再过 4.9s 不换图
    assert ui.view(now_ms=20 + GALLERY_SLIDE_MS - 100)["gallery"]["detail_index"] == 0


def test_幻灯片确认返回网格():
    ui = _gallery_ui(unlocked=("cg_end1",))
    ui._cursor = 2
    ui.handle("confirm")
    assert ui.view(now_ms=0)["gallery"]["detail"] == "cg_end1"
    ui.handle("back")
    assert ui.view(now_ms=0)["gallery"]["detail"] is None


def test_renderer_幻灯片缺图向后跳过(tmp_path):
    images = tmp_path / "images"
    images.mkdir()
    pygame.image.save(pygame.Surface((64, 36)), str(images / "bg_ok.png"))
    ren = Renderer((1280, 720), str(tmp_path))
    try:
        idx, shown, img = ren._detail_image(0, "cg_end1", ["不存在", "bg_ok"], 0)
        assert (idx, shown) == (1, "bg_ok") and img is not None
        # 全部缺失：回退格名单图，也没有则 None（不崩）
        idx, shown, img = ren._detail_image(0, "cg_end1", ["缺1", "缺2"], 0)
        assert idx == 0 and shown == "cg_end1" and img is None
    finally:
        ren.close()


def test_renderer_锁格与详情页不崩(tmp_path):
    images = tmp_path / "images"
    images.mkdir()
    pygame.image.save(pygame.Surface((200, 150)), str(images / "cg_locked.png"))
    ren = Renderer((1280, 720), str(tmp_path))
    try:
        ui = _gallery_ui(unlocked=("cg_end1",))
        ui._cursor = 1                     # cg_dawn：未解锁
        ren.render({}, ui.view(now_ms=0))   # 锁格网格
        ui._cursor = 2
        ui.handle("confirm")               # 详情页幻灯片
        ren.render({}, ui.view(now_ms=0))
    finally:
        ren.close()


# ==================== E2：序幕镜头停留 ====================

class _FakeRen:
    def __init__(self):
        self._cg_showing = None
        self.t0 = 0
        self.complete = True
        self.timeline = timeline.Timeline()  # P30-C-a：序幕停留改挂在时间轴上

    def _now_ms(self):
        return self.t0

    def typewriter_complete(self):
        return self.complete

    def play_sfx(self, *_a, **_k):
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
    def __init__(self, events):
        self.steps = 0
        self.events = list(events)

    def step(self):
        self.steps += 1
        return self.events.pop(0) if self.events else {"type": "say"}


def test_splash_镜头停留时长(monkeypatch):
    monkeypatch.setattr(demo, "_SPLASH_HOLD_MS", 1200)
    assert demo._splash_hold_ms({"type": "camera", "kind": "pan",
                                 "args": ["下", 13.0]}) == 13000
    assert demo._splash_hold_ms({"type": "camera", "kind": "reset",
                                 "args": [2.5]}) == 2500
    assert demo._splash_hold_ms({"type": "camera", "kind": "zoom",
                                 "args": [1.0, 1.2]}) == int(CAM_ZOOM_SECONDS * 1000)
    assert demo._splash_hold_ms({"type": "camera", "kind": "shake",
                                 "args": [1.0, 1.0]}) == 0
    assert demo._splash_hold_ms({"type": "say"}) == 1200


def test_drive_splash_Pan播完才推下一条(monkeypatch):
    monkeypatch.setattr(demo, "_SPLASH_HOLD_MS", 1200)
    ren = _FakeRen()
    rt = _FakeRt([{"type": "camera", "kind": "pan", "args": ["下", 13.0]},
                  {"type": "say", "text": "献辞"}])
    demo._drive_splash(rt, ren, {})
    assert rt.steps == 1 and ren.timeline.track("splash").dur == 13000
    ren.t0 = 12_999
    demo._drive_splash(rt, ren, {})
    assert rt.steps == 1                    # Pan 未播完不续文字
    ren.t0 = 13_000
    demo._drive_splash(rt, ren, {})
    assert rt.steps == 2 and ren.timeline.track("splash").dur == 1200


# ==================== E5：字符串变量 ====================

def test_parse_set_字符串与dump往返():
    ins = parse_text('@set 结局名 = "光"\n')[0]
    assert {k: ins[k] for k in ("op", "var", "operator", "value", "line")} == {
        "op": "set", "var": "结局名", "operator": "=", "value": "光", "line": 1}
    text = dump_text([ins])
    assert '"光"' in text
    assert parse_text(text)[0]["value"] == "光"


def test_parse_set_空字符串():
    ins = parse_text('@set 备注 = ""\n')[0]
    assert ins["value"] == ""


def test_runtime_字符串变量台词插值(tmp_path):
    script = tmp_path / "s.gal"
    script.write_text('@set 结局名 = "光"\n@ 结局是${结局名}\n@end\n', encoding="utf-8")
    rt = Runtime()
    rt.load(str(script))
    rt.step()                               # @set
    ev = rt.step()                          # 台词
    assert ev["type"] == "say"
    assert ev["text"] == "结局是光"
    assert rt.snapshot()["vars"]["结局名"] == "光"
