# -*- coding: utf-8 -*-
"""tests/test_data.py：data.py 验收（资源解析 / 设置往返 / 中文字体）。"""
import json
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")  # 无头模式，须在 import pygame 前生效

import pytest

import engine.data as data
from engine.data import (DataError, find_cjk_font, game_root, load_settings,
                         resolve_audio, resolve_font, resolve_image, save_settings,
                         DEFAULT_SETTINGS)

pytestmark = [pytest.mark.unit]


# ---------- 1. 资源路径解析 ----------

def test_resolve_image_拼接与缺失(tmp_path):
    images = tmp_path / "images"
    images.mkdir()
    (images / "classroom.png").write_bytes(b"\x89PNG\r\n\x1a\n")  # 内容无所谓，存在即可
    got = resolve_image(str(tmp_path), "classroom")
    assert got == str(images / "classroom.png")
    with pytest.raises(DataError) as e:
        resolve_image(str(tmp_path), "no_such")
    assert "找不到图片文件" in str(e.value)
    assert "no_such" in str(e.value)


def test_resolve_audio_三种后缀与优先级(tmp_path):
    audio = tmp_path / "audio"
    audio.mkdir()
    (audio / "knock.wav").write_bytes(b"RIFF")
    assert resolve_audio(str(tmp_path), "knock").endswith("knock.wav")
    (audio / "knock.mp3").write_bytes(b"ID3")
    assert resolve_audio(str(tmp_path), "knock").endswith("knock.mp3")
    (audio / "knock.ogg").write_bytes(b"OggS")
    assert resolve_audio(str(tmp_path), "knock").endswith("knock.ogg")  # ogg 优先
    with pytest.raises(DataError) as e:
        resolve_audio(str(tmp_path), "nothing")
    assert "找不到音频文件" in str(e.value)


def test_resolve_font_拼接与缺失(tmp_path):
    fonts = tmp_path / "fonts"
    fonts.mkdir()
    (fonts / "myfont.ttc").write_bytes(b"ttcf")
    assert resolve_font(str(tmp_path), "myfont").endswith("myfont.ttc")
    with pytest.raises(DataError) as e:
        resolve_font(str(tmp_path), "nope")
    assert "找不到字体文件" in str(e.value)


# ---------- 2. 中文字体 ----------

def test_find_cjk_font_能找到系统字体():
    path = find_cjk_font()  # Windows 必有 msyh.ttc 或 simhei.ttf；找不到会抛 DataError
    assert os.path.isfile(path)


def test_find_cjk_font_游戏目录fonts优先(tmp_path, monkeypatch):
    """打包发布用：游戏目录 fonts/ 里的字体优先于系统字体。"""
    fonts = tmp_path / "fonts"
    fonts.mkdir()
    mine = fonts / "NotoSansCJK.ttf"
    mine.write_bytes(b"\x00\x01\x00\x00")
    assert find_cjk_font(str(tmp_path)) == str(mine)
    # 不带参数时用 game_root()（开发时 = 当前工作目录）
    monkeypatch.chdir(tmp_path)
    assert find_cjk_font() == str(mine)


# ---------- 2.1 游戏根目录（打包路径基准） ----------

def test_game_root_开发时是当前目录(tmp_path, monkeypatch):
    monkeypatch.delattr(data.sys, "frozen", raising=False)
    monkeypatch.chdir(tmp_path)
    assert game_root() == str(tmp_path)


def test_game_root_打包后是exe所在目录(tmp_path, monkeypatch):
    exe = tmp_path / "dist" / "我的游戏" / "我的游戏.exe"
    exe.parent.mkdir(parents=True)
    monkeypatch.setattr(data.sys, "frozen", True, raising=False)
    monkeypatch.setattr(data.sys, "executable", str(exe), raising=False)
    assert game_root() == str(exe.parent)


# ---------- 3. settings 往返 ----------

def test_load_settings_缺文件返回默认(tmp_path):
    s = load_settings(str(tmp_path / "settings.json"))
    assert s == DEFAULT_SETTINGS
    assert s["text_speed"] == 45


def test_settings_保存后读取一致(tmp_path):
    p = str(tmp_path / "settings.json")
    save_settings({"text_speed": 60, "bgm_volume": 0.5}, p)
    s = load_settings(p)
    assert s["text_speed"] == 60
    assert s["bgm_volume"] == 0.5
    assert s["sfx_volume"] == DEFAULT_SETTINGS["sfx_volume"]  # 未指定的字段保持默认


def test_load_settings_损坏文件不崩(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text("{这不是合法 JSON", encoding="utf-8")
    assert load_settings(str(p)) == DEFAULT_SETTINGS


def test_load_settings_保留未知字段与错误类型(tmp_path):
    """P31-c：未知键要保留（title 等靠它读）；已知键类型不对仍回退默认。"""
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({"text_speed": "快", "unknown_key": 1, "sfx_volume": 0.3}),
                 encoding="utf-8")
    s = load_settings(str(p))
    assert s["text_speed"] == 45          # 类型不对回退默认
    assert s["sfx_volume"] == 0.3
    assert s["unknown_key"] == 1          # 未知键原样保留
