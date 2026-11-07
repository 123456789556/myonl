# -*- coding: utf-8 -*-
"""打引擎发行包（M1：引擎可被使用）。

产物：dist/release/MYONL引擎-<版本>.zip，解压即用、不需要 Python：
    MYONL引擎-v1.0.0-rc1/
      editor/editor.exe        ← 双击打开编辑器
      games/教程示例/            ← 打开就能改的第一个工程
      快速上手.md / README.md / LICENSE / NOTICE
      文档/                    ← 开发者指南 / engine_spec / 插件指南
      tools/win_env_check.bat  ← 零帮助抽测第 2 步的环境体检（只读不改）

用法：
    py -3 tools/build_release_zip.py                    # 打包
    py -3 tools/build_release_zip.py --verify           # 打包并从解压目录冒烟

前置：先构建编辑器发行包（build_editor.bat 或 py -3 -m PyInstaller --noconfirm --clean editor.spec）。
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VERSION = "v1.0.0-rc7"

# 发行包专用 README：只讲双击即用的五步，绝不出现源码/ Python 指令，
# 避免新用户照着源码版 README 去 pip install 而误以为包坏了。
RELEASE_README = """# MYONL 引擎 · 发行版

双击即用：不需要安装 Python，也不需要配置任何环境。

## 五步做出第一个 demo

1. 双击 `editor/editor.exe` 打开编辑器；
2. 左栏点 `script.gal`，改一句台词；
3. `Ctrl+S` 保存（或点顶部 `💾 保存`）；
4. 点顶部 `▶ 运行` 看效果（或菜单 运行 → 运行游戏）；
5. 点顶部 `📦 打包发布`（或 文件 → 打包发布，快捷键 `Ctrl+P`），产出的游戏在工程目录的 `dist/<游戏名>/`。

> 打包约 1 秒：发行版内置玩家运行库，不需要安装 Python，也不需要联网。

## 教程工程

`games/教程示例/` 就是默认打开的示例工程，剧本写在 `script.gal` 里。
想换自己的工程：点顶部齿轮（设置），把「工程目录」指到你的文件夹即可。

## 常见问题

- **双击没反应 / 提示缺少 WebView2**：安装微软 Edge WebView2 Runtime（免费，Win10/11 多数已自带）：https://developer.microsoft.com/microsoft-edge/webview2/
- **杀毒软件拦截**：这是未签名的自研引擎，选择「允许运行」或加入白名单即可。
- **工程放在中文路径**：可以；但建议不要放在网盘同步目录，避免保存冲突。
- **我改的文件在哪**：剧本与素材都在你的工程目录里；打包产物在工程下的 `dist/<游戏名>/`。

## 文档

- `文档/快速上手.md` — 三步上手
- `文档/开发者使用指南.md` — 指令与配置
- `LICENSE` / `NOTICE` — 许可与第三方组件
"""


def _release_readme() -> str:
    """发行版 README 内容（独立于根目录 README，避免把源码流程带进包里）。"""
    return RELEASE_README

# 控制台默认 GBK：子进程输出里的非 GBK 字符（emoji/箭头）会让 print 崩，统一 UTF-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def _add_tree(zf: zipfile.ZipFile, src: Path, arc_prefix: str) -> int:
    count = 0
    for path in sorted(src.rglob("*")):
        if path.is_dir():
            continue
        arc = f"{arc_prefix}/{path.relative_to(src).as_posix()}"
        zf.write(path, arc)
        count += 1
    return count


def build(version: str, out: Path) -> Path:
    editor = ROOT / "dist" / "editor" / "editor.exe"
    if not editor.is_file():
        print("错误：缺少 dist/editor/editor.exe，先跑：")
        print("  py -3 -m PyInstaller --noconfirm --clean editor.spec")
        raise SystemExit(2)
    tutorial = ROOT / "games" / "教程示例"
    if not tutorial.is_dir():
        print("错误：缺少 games/教程示例（先跑 tools/make_tutorial_project.py）")
        raise SystemExit(2)

    prefix = f"MYONL引擎-{version}"
    out.parent.mkdir(parents=True, exist_ok=True)
    entries = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        zf.writestr(f"{prefix}/README.md", _release_readme())
        entries += 1
        for name in ("LICENSE", "NOTICE"):
            zf.write(ROOT / name, f"{prefix}/{name}")
            entries += 1
        # 所有文档都放 文档/：快速上手里的相对链接（开发者使用指南.md 等）才能生效
        for doc in ("快速上手.md", "开发者使用指南.md", "engine_spec.md", "插件开发指南.md"):
            zf.write(ROOT / "docs" / doc, f"{prefix}/文档/{doc}")
            entries += 1
        entries += _add_tree(zf, ROOT / "dist" / "editor", f"{prefix}/editor")
        entries += _add_tree(zf, tutorial, f"{prefix}/games/教程示例")
        # 零帮助抽测清单第 2 步要双击 tools/win_env_check.bat（docs/计划/00-总览.md §三）；
        # 以前只在仓库里有、没进包，抽测走到第 2 步就找不到文件，故必须随包。
        zf.write(ROOT / "tools" / "win_env_check.bat", f"{prefix}/tools/win_env_check.bat")
        entries += 1
    size_mb = out.stat().st_size / 1024 / 1024
    print(f"发行包：{out}（{size_mb:.1f} MB，{entries} 个文件）")
    return out


def verify(zip_path: Path, version: str) -> int:
    work = Path(tempfile.mkdtemp(prefix="myonl_release_"))
    try:
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(work)
        base = work / f"MYONL引擎-{version}"
        exe = base / "editor" / "editor.exe"
        project = base / "games" / "教程示例"
        # T2：发行版 README 必须只讲双击即用，不能夹带源码流程
        readme = base / "README.md"
        if not readme.is_file():
            print("验证失败：发行包缺少 README.md")
            return 1
        text = readme.read_text(encoding="utf-8")
        for bad in ("pip install", "engine.demo", "build.bat", "py -3"):
            if bad in text:
                print(f"验证失败：发行版 README 含源码指令「{bad}」")
                return 1
        for need in ("editor.exe", "Ctrl+S", "运行", "打包发布"):
            if need not in text:
                print(f"验证失败：发行版 README 缺少「{need}」")
                return 1
        # 文档必须齐全，且快速上手里的相对 md 链接都能在包内找到
        docs = base / "文档"
        for name in ("快速上手.md", "开发者使用指南.md", "engine_spec.md", "插件开发指南.md"):
            if not (docs / name).is_file():
                print(f"验证失败：发行包缺少 文档/{name}")
                return 1
        quick = (docs / "快速上手.md").read_text(encoding="utf-8")
        for link in set(re.findall(r"\]\(([^)]+\.md)\)", quick)):
            if not (docs / link).is_file():
                print(f"验证失败：快速上手链接失效（包内找不到 文档/{link}）")
                return 1
        # 内置素材必须随编辑器进包，否则发行版里「新建游戏」是白板（素材只在示例工程里）
        tpl = base / "editor" / "_internal" / "engine" / "templates" / "standard"
        if not (tpl / "script.gal").is_file() or not (tpl / "images").is_dir():
            print(f"验证失败：发行包缺少内置素材模板 {tpl}")
            return 1
        # 玩家模板必须随编辑器进包，否则发行版「一键打包」没有运行库可复制
        player = base / "editor" / "_internal" / "engine" / "templates" / "player"
        if not (player / "MYONLPlayer.exe").is_file() or not (player / "_internal").is_dir():
            print(f"验证失败：发行包缺少玩家模板 {player}（先跑 tools/build_player_template.py）")
            return 1
        # 抽测清单第 2 步直接指向 tools/win_env_check.bat；缺了陌生人第 2 步就卡住
        envcheck = base / "tools" / "win_env_check.bat"
        if not envcheck.is_file():
            print("验证失败：发行包缺少 tools/win_env_check.bat（零帮助抽测第 2 步要用）")
            return 1
        script = ROOT / "tools" / "smoke_editor_exe.py"
        print(f"冒烟：从解压目录运行 {exe}")
        proc = subprocess.run([sys.executable, str(script), "--exe", str(exe),
                               "--project", str(project)], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=300)
        print(proc.stdout.strip() or proc.stderr.strip())
        return proc.returncode
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="打 MYONL 引擎发行包")
    ap.add_argument("--version", default=DEFAULT_VERSION)
    ap.add_argument("--out", default="")
    ap.add_argument("--verify", action="store_true", help="打包后解压并冒烟编辑器发行包")
    args = ap.parse_args(argv)

    out = Path(args.out) if args.out else ROOT / "dist" / "release" / f"MYONL引擎-{args.version}.zip"
    zip_path = build(args.version, out)
    if args.verify:
        code = verify(zip_path, args.version)
        if code != 0:
            print("验证失败：解压后的发行包冒烟未通过")
            return 1
        print("验证通过：发行包解压即可用")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
