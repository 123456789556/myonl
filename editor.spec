# -*- mode: python ; coding: utf-8 -*-
"""MYONL 编辑器打包配置（PyInstaller onedir）。

产物：dist/editor/editor.exe（与 dist/<游戏名>/ 同级，互不影响）。
PyInstaller 通过 pywebview / pythonnet 自带的 hook 收集 WebView2 与 .NET 运行时文件。
"""
import os

from PyInstaller.utils.hooks import collect_data_files

ROOT = os.path.abspath(SPECPATH)

datas = [
    # 整个 editor/ 目录一起带：原来是一个个列文件，新加了 editor_link.js / editor_mobile.js
    # 却忘了加到名单里 —— 发行版里这两个 URL 直接 404，「手机连接」「手机预览」整块坏掉，
    # 而且当时打包不报错，只有用户点到才知道。目录整体带就不会再有这种漏。
    (os.path.join(ROOT, "editor"), "editor"),
]
# P114：JS 内核（parser.js / pack.js）住在 engine/，由 editor.py 回落到那个目录服务。
# 漏了它们，发行版里手机端「做成成品」按钮点了没反应（素材/解析器全缺）。
datas += [
    (os.path.join(ROOT, "engine", name), "engine")
    for name in ("parser.js", "pack.js")
]
# M1.5：内嵌教程（编辑器「帮助 → 教程 / 说明书」在发行包里也要能看）
#
# 这里原先是一个个列文件名，而且列的是 docs/ 根下的「开发者使用指南.md」等 ——
# 那三份早就搬到 docs/desktop/ 了，spec 没跟着改。后果不是「帮助里少一篇」，
# 而是 PyInstaller 直接拿不到文件、整个打包以 ERROR 退出（v1.2.36 的 exe CI 就死在这）。
# 同 editor/ 一样改成目录整体带：文档改名、加一篇、挪子目录都不用再动 spec。
# 整个 docs 也才 1.2 MB（大头是配图），不值当为这点体积再赌一次漏带。
datas += [(os.path.join(ROOT, "docs"), "docs")]
# 引擎自带素材与空包模板：缺了它，发行包里「新建游戏」拿不到内置背景/立绘/音效，
# 新建出来的工程就是白板（用户反馈：素材只在别的示例工程里）。
datas += [(os.path.join(ROOT, "engine", "templates"), "engine/templates")]
# P54：手机版播放器（导出手机版要把它拷进产物目录；漏了发行包里就导出失败）
datas += [
    (os.path.join(ROOT, "web", name), "web")
    for name in ("myonl-core.js", "myonl-layout.js", "myonl-player.js")
]
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
    "engine.webpack",   # P54：导出手机版（懒加载，frozen 下必须显式声明）
    "engine.portable",  # P56：导出可迁移包（同上）
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
