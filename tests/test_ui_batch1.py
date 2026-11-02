# -*- coding: utf-8 -*-
"""M1.5 UI 批 1：玩家设置项（显示模式 / AUTO 速度 / 静音 / 语音音量 / 默认值）。

覆盖：
1. 新默认值（打字 45、语音音量 0.9、静音关、AUTO 中速、显示模式窗口）
2. 设置项注册与 next_value 循环（choice / switch / volume）
3. AUTO 间隔 = pacing 基础值 × 玩家速度倍率
4. 音量/静音 helper（音乐/音效/配音独立，静音全 0）
5. 显示模式：窗口/无边框全屏/全屏切换 + 非法值兜底
6. 设备档位：quality_tier=low 时降级（跳效果 + 图片缓存上限 128MB）
7. 新建游戏按设备档位选窗口，老工程不动
"""
from __future__ import annotations

import json
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from pathlib import Path  # noqa: E402

import pytest  # noqa: E402

from engine import capability, data  # noqa: E402
from engine.newgame import create_game  # noqa: E402
from engine.renderer import Renderer  # noqa: E402
from engine.ui import auto_interval_ms, next_value  # noqa: E402

pytestmark = [pytest.mark.ui]


def _renderer(tmp_path: Path, settings: dict | None = None) -> Renderer:
    if settings is not None:
        (tmp_path / "settings.json").write_text(
            json.dumps(settings, ensure_ascii=False), encoding="utf-8")
    return Renderer(size=(1280, 720), assets_root=str(tmp_path))


# ==================== 1. 默认值 ====================

def test_新默认值():
    assert data.DEFAULT_SETTINGS["text_speed"] == 45
    assert data.DEFAULT_SETTINGS["voice_volume"] == 0.9
    assert data.DEFAULT_SETTINGS["muted"] is False
    assert data.DEFAULT_SETTINGS["auto_speed"] == "normal"
    assert data.DEFAULT_SETTINGS["display_mode"] == "window"
    assert data.DEFAULT_SETTINGS["font_scale"] == "medium"


def test_设置项已注册():
    from engine.ui import SETTINGS_ITEMS

    keys = {item["key"] for item in SETTINGS_ITEMS}
    assert {"display_mode", "auto_speed", "muted", "voice_volume", "font_scale"} <= keys


# ==================== 2. next_value 循环 ====================

def test_显示模式循环():
    assert next_value("display_mode", "window") == "borderless"
    assert next_value("display_mode", "borderless") == "fullscreen"
    assert next_value("display_mode", "fullscreen") == "window"


def test_自动速度循环():
    assert next_value("auto_speed", "normal") == "fast"
    assert next_value("auto_speed", "fast") == "slow"
    assert next_value("auto_speed", "slow") == "normal"


def test_静音与语音音量():
    assert next_value("muted", 0) == 1
    assert next_value("muted", 1) == 0
    assert next_value("voice_volume", 0.9) != 0.9


# ==================== 3. AUTO 间隔 ====================

def test_AUTO间隔按玩家倍率():
    assert auto_interval_ms({"auto_speed": "normal"}, 900) == 900
    assert auto_interval_ms({"auto_speed": "slow"}, 900) == 1440
    assert auto_interval_ms({"auto_speed": "fast"}, 900) == 540
    assert auto_interval_ms({}, 1000) == 1000        # 缺省中速
    assert auto_interval_ms({"auto_speed": "??"}, 900) == 900


# ==================== 4. 音量 / 静音 ====================

def test_音量helper与静音(tmp_path):
    ren = _renderer(tmp_path)
    try:
        assert ren._bgm_volume() == 0.7
        assert ren._sfx_volume() == 0.8
        assert ren._voice_volume() == 0.9
        ren.settings["voice_volume"] = 0.5
        assert ren._voice_volume() == 0.5
        ren.settings["muted"] = True
        assert ren._bgm_volume() == 0.0
        assert ren._sfx_volume() == 0.0
        assert ren._voice_volume() == 0.0
    finally:
        ren.close()


# ==================== 5. 显示模式 ====================

def test_显示模式_无边框(tmp_path):
    ren = _renderer(tmp_path, {"display_mode": "borderless"})
    try:
        assert ren._borderless is True
        assert ren._fullscreen is False
        assert ren.apply_display_mode("fullscreen") is True
        assert ren._fullscreen is True and ren._borderless is False
        saved = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
        assert saved["display_mode"] == "fullscreen"
        assert ren.apply_display_mode("不存在") is False
    finally:
        ren.close()


# ==================== 6. 设备档位降级 ====================

def test_低配降级跳过重效果(tmp_path):
    ren = _renderer(tmp_path, {"quality_tier": "low"})
    try:
        assert ren._capability_tier == "low"
        assert ren._reduce_effects() is True
        assert ren._img_cache_max_bytes <= 128 * 1024 * 1024
    finally:
        ren.close()


def test_高配不降级(tmp_path):
    ren = _renderer(tmp_path, {"quality_tier": "high"})
    try:
        assert ren._reduce_effects() is False
    finally:
        ren.close()


# ==================== 7. 新建游戏自适应窗口 ====================

def test_新建游戏按设备档位选窗口(tmp_path):
    root = create_game("自适应窗口", str(tmp_path))
    settings = json.loads((root / "settings.json").read_text(encoding="utf-8"))
    assert settings["window_size"] == list(capability.suggest_settings()["window_size"])
    assert settings["display_mode"] == "window"
    # 新工程模板只写少量键；text_speed 由 DEFAULT_SETTINGS 运行时兜底为 45
    assert settings.get("text_speed", data.DEFAULT_SETTINGS["text_speed"]) == 45


# ==================== 8. 玩家字号三档（M1.5-B） ====================

def test_字号三档循环():
    from engine.ui import FONT_SCALE_FACTORS, font_scale_factor

    assert FONT_SCALE_FACTORS == {"small": 0.85, "medium": 1.0, "large": 1.2}
    assert font_scale_factor({"font_scale": "small"}) == 0.85
    assert font_scale_factor({"font_scale": "large"}) == 1.2
    assert font_scale_factor({}) == 1.0
    assert font_scale_factor({"font_scale": "??"}) == 1.0
    assert next_value("font_scale", "medium") == "large"
    assert next_value("font_scale", "large") == "small"
    assert next_value("font_scale", "small") == "medium"


def test_字号切换重建全部字体(tmp_path):
    ren = Renderer(size=(1280, 720), assets_root=str(tmp_path))
    try:
        assert ren.settings["font_scale"] == "medium"
        body_mid = ren._font.get_height()
        name_mid = ren._mid_font.get_height()
        option_mid = ren._option_font.get_height()
        ren.update_settings({"font_scale": "large"})
        assert ren._font.get_height() > body_mid
        assert ren._mid_font.get_height() > name_mid
        assert ren._option_font.get_height() > option_mid
        ren.update_settings({"font_scale": "small"})
        assert ren._font.get_height() < body_mid
        ren.update_settings({"font_scale": "medium"})
        assert ren._font.get_height() == body_mid
    finally:
        ren.close()
