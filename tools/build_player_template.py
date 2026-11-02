# -*- coding: utf-8 -*-
"""构建「玩家模板」——编辑器发行版打包游戏时复制的预构建运行库。

背景：发行版 editor.exe 里没有 Python/PyInstaller，不能像源码版 pack.py 那样
现场调用 PyInstaller。做法是预构建一份通用玩家运行库：

    engine/templates/player/
      MYONLPlayer.exe     ← engine/player_app.py（从 exe 旁读 script.gal）
      _internal/          ← Python + pygame 运行库

打包游戏 = 复制模板 + 替换游戏资源，不需要任何编译环境。

用法：
    py -3 tools/build_player_template.py            # 构建
    py -3 tools/build_player_template.py --check    # 只检查模板是否存在

模板是生成物（约 23MB / 140 文件），不进 git；打编辑器发行包前必须先跑一次。
build_editor.bat 会在缺失时自动调用本脚本。
"""
from __future__ import annotations

import argparse
import importlib.util
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "engine" / "templates" / "player"
EXE_NAME = "MYONLPlayer.exe"


def _pack_module():
    """加载 pack.py，复用排除清单与 SDL 去重逻辑（不执行打包）。"""
    spec = importlib.util.spec_from_file_location("myonl_pack_for_template", ROOT / "pack.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def template_ready(path: Path = TARGET) -> bool:
    return (path / EXE_NAME).is_file() and (path / "_internal").is_dir()


def build() -> int:
    if not (ROOT / "engine" / "player_app.py").is_file():
        print("错误：缺少 engine/player_app.py", file=sys.stderr)
        return 2
    pack = _pack_module()
    tmp = Path(tempfile.mkdtemp(prefix="myonl_player_tpl_"))
    try:
        dist = tmp / "dist"
        cmd = [
            sys.executable, "-m", "PyInstaller",
            "--noconfirm", "--clean", "--onedir", "--windowed",
            "--name", "MYONLPlayer",
            "--distpath", str(dist),
            "--workpath", str(tmp / "work"),
            "--specpath", str(tmp),
            "--paths", str(ROOT),
            "--hidden-import", "engine.demo",
            "--optimize", "2",
        ]
        for module in pack._EXCLUDE_MODULES:  # noqa: SLF001 — 与游戏打包共用同一份排除清单
            cmd += ["--exclude-module", module]
        cmd.append(str(ROOT / "engine" / "player_app.py"))
        print("构建玩家模板（首次约 1~2 分钟）……", flush=True)
        import subprocess
        proc = subprocess.run(cmd)
        if proc.returncode != 0:
            print(f"错误：PyInstaller 失败（退出码 {proc.returncode}）", file=sys.stderr)
            return proc.returncode
        src = dist / "MYONLPlayer"
        if not template_ready(src):
            print(f"错误：构建产物不完整：{src}", file=sys.stderr)
            return 3
        if TARGET.exists():
            shutil.rmtree(TARGET)
        TARGET.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, TARGET)
        pack._slim_internal(TARGET)  # noqa: SLF001 — 去除重复 SDL 运行库
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    files = [p for p in TARGET.rglob("*") if p.is_file()]
    size_mb = sum(p.stat().st_size for p in files) / 1024 / 1024
    print(f"玩家模板：{TARGET}（{size_mb:.1f} MB，{len(files)} 个文件）")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="构建 MYONL 玩家模板")
    ap.add_argument("--check", action="store_true", help="只检查模板是否已就绪")
    args = ap.parse_args(argv)
    if args.check:
        ok = template_ready()
        print(f"玩家模板：{'已就绪' if ok else '缺失'}（{TARGET}）")
        return 0 if ok else 1
    return build()


if __name__ == "__main__":
    raise SystemExit(main())
