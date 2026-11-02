# -*- coding: utf-8 -*-
"""P40：数据目录可配置（data_dir 三档）测试。

- "" / "game"    → 随游戏目录（删游戏 = 数据删干净，默认行为，零回归）
- "appdata"      → %APPDATA%/Moyul/<游戏名>（删游戏数据保留）
- 绝对路径       → 开发者自定义数据位置

存档目录 save.saves_dir() 在未手动 set 时跟随 data_root()。
"""
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import data as data_api
from engine import save as save_api

pytestmark = [pytest.mark.unit]


def _write_settings(root: Path, data_dir: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "settings.json").write_text(
        json.dumps({"data_dir": data_dir}, ensure_ascii=False),
        encoding="utf-8")


def test_data_root_default_follows_game(tmp_path):
    # 未写 data_dir：数据根 = 游戏根（删游戏 = 删干净）
    _write_settings(tmp_path, "")
    assert data_api.data_root(str(tmp_path)) == str(tmp_path)
    _write_settings(tmp_path, "game")
    assert data_api.data_root(str(tmp_path)) == str(tmp_path)


def test_data_root_appdata(tmp_path, monkeypatch):
    _write_settings(tmp_path, "appdata")
    fake_appdata = tmp_path / "AppData"
    monkeypatch.setenv("APPDATA", str(fake_appdata))
    expected = str(fake_appdata / "Moyul" / tmp_path.name)
    assert data_api.data_root(str(tmp_path)) == expected


def test_data_root_custom_abs(tmp_path):
    _write_settings(tmp_path, "D:/custom/moyul_data")
    assert data_api.data_root(str(tmp_path)) == "D:/custom/moyul_data"


def test_saves_dir_follows_data_root(tmp_path, monkeypatch):
    # 未手动 set_saves_dir 时，saves_dir() 跟随 data_root()
    _write_settings(tmp_path, "appdata")
    fake_appdata = tmp_path / "AppData"
    monkeypatch.setenv("APPDATA", str(fake_appdata))
    monkeypatch.chdir(tmp_path)
    try:
        expected = Path(fake_appdata / "Moyul" / tmp_path.name) / "saves"
        assert save_api.saves_dir() == expected
    finally:
        save_api.reset_saves_dir()


def test_存档实际写入数据根(tmp_path, monkeypatch):
    """data_dir=appdata 时，save()/list_slots() 必须真的落到 AppData，而不只是 saves_dir() 好看。"""
    _write_settings(tmp_path, "appdata")
    fake_appdata = tmp_path / "AppData"
    monkeypatch.setenv("APPDATA", str(fake_appdata))
    monkeypatch.chdir(tmp_path)
    try:
        path = save_api.save({"script": "x.gal", "stack": [[0, 0]]}, 1)
        expected = Path(fake_appdata / "Moyul" / tmp_path.name) / "saves" / "slot_1.json"
        assert Path(path) == expected and expected.is_file()
        assert [e["slot"] for e in save_api.list_slots()] == ["1"]
    finally:
        save_api.reset_saves_dir()


def test_save_settings_writes_to_data_root(tmp_path, monkeypatch):
    # data_dir 非空时，save_settings() 落数据根（并自动建目录）
    _write_settings(tmp_path, "appdata")
    fake_appdata = tmp_path / "AppData"
    monkeypatch.setenv("APPDATA", str(fake_appdata))
    monkeypatch.chdir(tmp_path)
    try:
        data_api.save_settings({"data_dir": "appdata", "text_speed": 55})
        d = Path(fake_appdata / "Moyul" / tmp_path.name)
        p = d / "settings.json"
        assert p.is_file()
        loaded = json.loads(p.read_text(encoding="utf-8"))
        assert loaded.get("text_speed") == 55
        assert loaded.get("data_dir") == "appdata"
    finally:
        save_api.reset_saves_dir()


def test_engine_data_root_appdata(tmp_path, monkeypatch):
    # P41：引擎级数据根固定为 %APPDATA%/Moyul（与游戏无关，删引擎重下数据接回）
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert data_api.engine_data_root() == str(tmp_path / "Moyul")
    # 子目录预留（plugins/mods/cache）由调用方创建，此处只保证根路径正确


def test_engine_data_root_fallback_home(monkeypatch):
    # APPDATA 缺失时回退 ~/AppData/Roaming，不崩
    monkeypatch.delenv("APPDATA", raising=False)
    root = data_api.engine_data_root()
    assert root.endswith(os.path.join("AppData", "Roaming", "Moyul"))
