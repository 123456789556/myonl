# -*- coding: utf-8 -*-
"""发行包清单守护：零帮助抽测第 2 步要双击的 tools/win_env_check.bat 必须随包。

背景（2026-11-07 实测）：rc7 发行包里没有该脚本，而 docs/计划/00-总览.md §三
的抽测清单第 2 步直接要求双击 `tools/win_env_check.bat` —— 陌生人照清单走到
第 2 步就会找不到文件。本测试防止打包脚本再漏掉它。
"""
from __future__ import annotations

import importlib.util
import os
import zipfile

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 纯文件/ZIP 逻辑，不渲染不打包，属 unit 层
pytestmark = [pytest.mark.unit]


def _load_builder():
    spec = importlib.util.spec_from_file_location(
        "build_release_zip", os.path.join(REPO, "tools", "build_release_zip.py"))
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _make_min_repo(tmp_path):
    """构造 build() 需要的最小目录：编辑器产物用空文件占位，文档/工程只给最小内容。"""
    root = tmp_path / "repo"
    editor = root / "dist" / "editor"
    editor.mkdir(parents=True)
    (editor / "editor.exe").write_bytes(b"stub")
    project = root / "games" / "教程示例"
    project.mkdir(parents=True)
    (project / "script.gal").write_text("@label start\n", encoding="utf-8")
    docs = root / "docs"
    docs.mkdir()
    for name in ("快速上手.md", "开发者使用指南.md", "engine_spec.md", "插件开发指南.md"):
        (docs / name).write_text("# 占位\n", encoding="utf-8")
    for name in ("LICENSE", "NOTICE"):
        (root / name).write_text("占位\n", encoding="utf-8")
    tools = root / "tools"
    tools.mkdir()
    (tools / "win_env_check.bat").write_text("@echo off\necho 占位\n", encoding="utf-8")
    return root


def test_发行包必须带上抽测用的环境体检脚本(tmp_path, monkeypatch):
    builder = _load_builder()
    root = _make_min_repo(tmp_path)
    monkeypatch.setattr(builder, "ROOT", root)
    out = tmp_path / "release.zip"
    builder.build("vtest", out)
    with zipfile.ZipFile(out) as zf:
        names = zf.namelist()
    assert "MYONL引擎-vtest/tools/win_env_check.bat" in names, names
