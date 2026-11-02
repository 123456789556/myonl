# -*- coding: utf-8 -*-
"""发行版「一键打包」：内置玩家模板复制路径验收。

发行版 editor.exe 没有 Python/PyInstaller，不能现场调用 PyInstaller；
打包 = 复制预构建的玩家模板（MYONLPlayer.exe + _internal）+ 游戏资源。
这组用例守住复制内容、排除项与「冻结模式优先模板」的分支。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from engine import packaging

pytestmark = [pytest.mark.unit]


def _fake_template(base: Path) -> Path:
    tpl = base / "engine" / "templates" / "player"
    (tpl / "_internal").mkdir(parents=True)
    (tpl / "MYONLPlayer.exe").write_bytes(b"MZfake-player")
    (tpl / "_internal" / "python313.dll").write_bytes(b"dll")
    return tpl


def _fake_project(base: Path) -> Path:
    proj = base / "games" / "演示"
    (proj / "images").mkdir(parents=True)
    (proj / "saves").mkdir()
    (proj / "script.gal").write_text("@ 你好\n@end\n", encoding="utf-8")
    (proj / "config.json").write_text("{}", encoding="utf-8")
    (proj / "icon.png").write_bytes(b"png")
    (proj / "pack_config.json").write_text("{}", encoding="utf-8")
    (proj / "saves" / "slot_1.json").write_text("{}", encoding="utf-8")
    (proj / "images" / "bg.png").write_bytes(b"png")
    return proj


def test_模板打包复制运行库与游戏资源(tmp_path):
    tpl = _fake_template(tmp_path)
    proj = _fake_project(tmp_path)
    build = packaging._template_builder(tpl, tmp_path)
    out = Path(build(str(proj), name="演示"))

    assert (out / "演示.exe").read_bytes() == b"MZfake-player"
    assert (out / "_internal" / "python313.dll").is_file()
    assert (out / "script.gal").is_file()
    assert (out / "images" / "bg.png").is_file()
    assert (out / "icon.png").is_file(), "窗口图标要保留（模板 exe 的通用图标靠它覆盖）"
    assert not (out / "saves").exists(), "开发机存档不能带进玩家包"
    assert not (out / "pack_config.json").exists(), "打包档案/运营号信息不进玩家包"


def test_模板打包会清掉旧产物(tmp_path):
    tpl = _fake_template(tmp_path)
    proj = _fake_project(tmp_path)
    stale = tmp_path / "dist" / "演示" / "stale.txt"
    stale.parent.mkdir(parents=True)
    stale.write_text("old", encoding="utf-8")

    build = packaging._template_builder(tpl, tmp_path)
    out = Path(build(str(proj), name="演示"))
    assert not (out / "stale.txt").exists(), "重打包不能留下上一版文件"


def test_玩家模板查找_缺exe视为不可用(tmp_path, monkeypatch):
    tpl = _fake_template(tmp_path)
    # 隔离真实源码树里的模板：把模块 __file__ 指到 tmp，避免 fallback 命中仓库模板
    monkeypatch.setattr(packaging, "__file__", str(tmp_path / "engine" / "packaging.py"))
    assert packaging.player_template_dir(tmp_path) == tpl
    (tpl / "MYONLPlayer.exe").unlink()
    assert packaging.player_template_dir(tmp_path) is None


def test_冻结模式缺模板时报中文错误(tmp_path, monkeypatch):
    """发行版里缺模板必须直接说清楚，不能落到 pack.py 后报 PyInstaller 退出码。"""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    monkeypatch.setattr(packaging, "player_template_dir", lambda root=None: None)
    with pytest.raises(packaging.PackProfileError) as err:
        packaging._default_builder(tmp_path)
    assert "玩家模板" in str(err.value)
