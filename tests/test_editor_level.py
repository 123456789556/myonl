# -*- coding: utf-8 -*-
"""E9：编辑器三档模式 Level 1–3（结构守护）。

用户 2026-11-01 定名：Level 1 新手 / Level 2 默认 / Level 3 专业，选择要被记住。
这里守住四件事：
1. 档位模块存在且被 index.html 加载；
2. 档位裁剪规则在 CSS 里（L1 隐藏专业件、L3 开放视图页签）；
3. 菜单 / 命令面板按档位过滤（L1 看不到专业入口）；
4. 发行包打包清单包含全部前端模块（曾漏 editor_main.js，双击 exe 必 500）。
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

ROOT = Path(__file__).resolve().parents[1]
EDITOR = ROOT / "editor"


def _read(name: str) -> str:
    return (EDITOR / name).read_text(encoding="utf-8")


def test_档位模块与入口齐全():
    """三档状态必须自成模块，并由 index.html 加载（不能塞回主脚本）。"""
    html = _read("index.html")
    assert (EDITOR / "editor_level.js").is_file(), "缺少 editor/editor_level.js"
    assert "/editor_level.js" in html, "index.html 未加载 editor_level.js"

    js = _read("editor_level.js")
    for token in ("gal_editor_level", "DEFAULT_LEVEL = 2", "__editorLevel",
                  "editor-level-1", "editor-level-2", "editor-level-3",
                  "levelSelect", "localStorage.setItem"):
        assert token in js, f"editor_level.js 缺 {token}"
    for label in ("Level 1", "Level 2", "Level 3"):
        assert label in js, f"缺少档位名称 {label}"


def test_档位裁剪规则在CSS里():
    """L1 隐藏专业件、L3 开放源码/JSON/卡片页签——靠 CSS，不靠临时删 DOM。"""
    css = _read("editor.css")
    for token in (".mb-level", "body.editor-level-1 .inspector",
                  "body.editor-level-1 #richToolbar", "body.editor-level-1 #sbLang",
                  "body.editor-level-3 .tabs"):
        assert token in css, f"editor.css 缺档位规则 {token}"


def test_菜单与命令面板按档位过滤():
    """专业入口标 minLevel: 3，L1/L2 打开菜单与命令面板时都要被过滤掉。

    T16 域拆分后，菜单/命令面板/档位裁剪已移到 editor_shell.js。
    """
    js = _read("editor_shell.js")
    assert "minLevel: 3" in js, "专业菜单项未标注档位"
    assert "_menuVisible" in js and "_levelNow" in js, "缺少档位过滤函数"
    assert "(MENUS[key] || []).filter(_menuVisible)" in js, "视图菜单未按档位过滤"
    assert "arr.filter(_menuVisible)" in js, "命令面板未按档位过滤"
    for label in ("档位：Level 1 新手", "档位：Level 2 默认", "档位：Level 3 专业"):
        assert label in js, f"缺少档位命令 {label}"


def test_档位由后端路由提供():
    """发行包/源码都要能取到 /editor_level.js，否则档位开关静默失效。"""
    py = (ROOT / "engine" / "editor.py").read_text(encoding="utf-8")
    assert '"/editor_level.js"' in py, "编辑器路由未注册 editor_level.js"
    assert "_serve_level_js" in py, "缺少 _serve_level_js 处理方法"


def test_发行包打包清单包含全部前端模块():
    """PyInstaller datas 漏文件时，exe 里打开编辑器会 500（真发生过）。"""
    names = ("editor_pro.js", "editor_main.js", "editor_scene.js",
             "editor_characters.js", "editor_level.js",
             "editor_uidesign.js", "editor_shell.js")
    spec = (ROOT / "editor.spec").read_text(encoding="utf-8")
    html = _read("index.html")
    py = (ROOT / "engine" / "editor.py").read_text(encoding="utf-8")
    for name in names:
        assert f'"{name}"' in spec, f"editor.spec 打包清单缺 {name}"
        assert (EDITOR / name).is_file(), f"缺少 editor/{name}"
        assert f"/{name}" in html, f"index.html 未加载 {name}"
        assert f'"/{name}"' in py, f"engine/editor.py 未注册 /{name} 路由"
