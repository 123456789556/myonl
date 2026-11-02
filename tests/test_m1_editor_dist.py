# -*- coding: utf-8 -*-
"""M1 引擎发行：编辑器双击兜底工程的选择逻辑（不启动 GUI）。

双击 editor.exe 时没有 --project 参数，需要自动挑一个能打开的示例工程；
这一步决定「陌生人下载后双击能不能直接看到东西」，是 M1 的 P0 路径。

覆盖：
1. 发行包目录结构下（games/<示例>/）能按优先级找到工程
2. 未知示例目录名也能被扫描命中（排序确定性）
3. 没有 games/ 时回退到当前目录（不崩、不报错）
4. 已存在的优先名（教程示例 > 标准示例）顺序正确
"""
from __future__ import annotations

from pathlib import Path

import pytest

from engine import editor_app

pytestmark = [pytest.mark.unit]


def _make_project(root: Path, name: str) -> Path:
    project = root / "games" / name
    (project / "images").mkdir(parents=True)
    (project / "script.gal").write_text("@label start\n@ 旁白 你好。\n@end\n", encoding="utf-8")
    return project


def test_双击兜底_优先教程示例(tmp_path, monkeypatch):
    _make_project(tmp_path, "标准示例")
    tutorial = _make_project(tmp_path, "教程示例")
    monkeypatch.chdir(tmp_path)
    assert editor_app._resolve_project(None) == str(tutorial.resolve())


def test_双击兜底_未知示例名也能命中(tmp_path, monkeypatch):
    project = _make_project(tmp_path, "我的第一个游戏")
    monkeypatch.chdir(tmp_path)
    assert editor_app._resolve_project(None) == str(project.resolve())


def test_双击兜底_没有games时回退当前目录(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert editor_app._resolve_project(None) == str(tmp_path.resolve())


def test_双击兜底_显式参数优先(tmp_path, monkeypatch):
    _make_project(tmp_path, "标准示例")
    monkeypatch.chdir(tmp_path)
    explicit = tmp_path / "elsewhere"
    explicit.mkdir()
    assert editor_app._resolve_project(str(explicit)) == str(explicit.resolve())
