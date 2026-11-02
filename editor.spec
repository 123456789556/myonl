# -*- mode: python ; coding: utf-8 -*-
"""MYONL 编辑器打包配置（PyInstaller onedir）。

产物：dist/editor/editor.exe（与 dist/<游戏名>/ 同级，互不影响）。
PyInstaller 通过 pywebview / pythonnet 自带的 hook 收集 WebView2 与 .NET 运行时文件。
"""
import os

from PyInstaller.utils.hooks import collect_data_files

ROOT = os.path.abspath(SPECPATH)

datas = [
    (os.path.join(ROOT, "editor", "index.html"), "editor"),
    (os.path.join(ROOT, "editor", "editor.css"), "editor"),
]
# 前端模块（拆分后的主脚本 / 场景 / 角色 / 档位）：漏掉任何一个，发行包打开编辑器即 500
datas += [
    (os.path.join(ROOT, "editor", name), "editor")
    for name in ("editor_pro.js", "editor_main.js", "editor_scene.js",
                 "editor_characters.js", "editor_level.js",
                 "editor_uidesign.js", "editor_shell.js")
]
# M1.5：内嵌教程（编辑器「帮助 → 教程 / 说明书」在发行包里也要能看）
datas += [
    (os.path.join(ROOT, "docs", name), "docs")
    for name in ("快速上手.md", "开发者使用指南.md", "素材导入指南.md",
                 "engine_spec.md", "插件开发指南.md", "打包使用指南.md")
]
# 引擎自带素材与空包模板：缺了它，发行包里「新建游戏」拿不到内置背景/立绘/音效，
# 新建出来的工程就是白板（用户反馈：素材只在别的示例工程里）。
datas += [(os.path.join(ROOT, "engine", "templates"), "engine/templates")]
# 桌宠分层素材：发行版 editor.exe --pet 与源码版必须是同一只 Mooki（缺图会退回代码绘制）
datas += [(os.path.join(ROOT, "brand", "mooki_layers"), "brand/mooki_layers")]
datas += collect_data_files("pythonnet")
datas += collect_data_files("clr_loader")

hiddenimports = [
    "webview.platforms.edgechromium",
    "webview.platforms.winforms",
    "clr",
    "clr_loader",
    "pythonnet",
    "engine.parser",
    "engine.runtime",
    "engine.renderer",
    "engine.data",
    "engine.save",
    "engine.demo",
    "engine.newgame",
    "engine.expr",
    "engine.ui",
    "engine.pet",   # 桌宠（编辑器实验功能；frozen 时 editor.exe --pet 启动，不进游戏包）
]

a = Analysis(
    [os.path.join(ROOT, "engine", "editor_app.py")],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="editor",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="editor",
)
