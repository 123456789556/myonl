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


def test_发行包打包清单覆盖前端全部模块():
    """PyInstaller datas 漏文件时，exe 里打开编辑器就 404（真发生过两次）。

    第二次是 editor_link.js / editor_mobile.js 已经加进 index.html，却没人加进 spec
    —— 打包不报错，发行版里「手机连接」「手机预览」整块坏掉。
    所以这里不写死名单，直接以 index.html 实际引用的脚本为准。
    """
    import re

    html = _read("index.html")
    refs = sorted(set(re.findall(r'src="/([^"?]+\.js)', html)))
    assert refs, "index.html 没有引用任何脚本"
    spec = (ROOT / "editor.spec").read_text(encoding="utf-8")
    py = (ROOT / "engine" / "editor.py").read_text(encoding="utf-8")
    whole_dir = '(os.path.join(ROOT, "editor"), "editor")' in spec
    for name in refs:
        # P114：parser.js / pack.js 是内核，住在 engine/（电脑端和手机端共用同一份），
        # 由 engine/editor.py 的 _serve_editor_file 回落服务；其余仍在 editor/。
        # P193c 起 editor/mobile/ 这类子目录也会收纳"只服务一端"的模块（URL 不变），
        # 所以这里按文件名递归找，不写死目录层级。
        assert (EDITOR / name).is_file() or any(EDITOR.rglob(name)) \
            or (ROOT / "engine" / name).is_file(), \
            f"index.html 引用了不存在的 editor/{name}（含子目录）或 engine/{name}"
        assert f'"/{name}"' in py, f"engine/editor.py 未注册 /{name} 路由"
        assert whole_dir or f'"{name}"' in spec, f"editor.spec 打包清单缺 {name}"
