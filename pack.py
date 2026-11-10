"""MYONL 一键打包工具：把「剧本 + 资源 + 插件 + 引擎」打成玩家双击即玩的目录。

用法：
    python pack.py <游戏目录>                       # 旧项目：按目录名直接打包
    python pack.py <游戏目录> --version 1.2.0       # 指定版本号
    python pack.py <游戏目录> --bump patch          # 版本迭代：1.0.0 → 1.0.1
    python pack.py <游戏目录> --icon icon.png       # 自定义图标（PNG 自动转 ICO）
    python pack.py <游戏目录> --publisher 名称 --account 运营号ID
    python pack.py --list                           # 列出可迭代打包的项目

读取游戏目录内的 pack_config.json（标准模板自带）：游戏名、版本、图标、
运营号四项必填；打包成功后写 build/pack_history.json 供版本管理。

产物：dist/<游戏名>/（内含 <游戏名>.exe + game_info.json + 剧本/资源/插件），
玩家解压后双击 exe 即可游玩，无需安装 Python、无需任何配置。

打包模式：PyInstaller onedir（目录模式）——资源外置可见可替换、存档生成在 exe 旁。
只用 Python 标准库 + PyInstaller；中文提示。
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent  # 引擎项目根（engine/ 所在目录）

# 不进打包产物的东西：开发/版本控制/测试/引擎源码/文档
_EXCLUDE_NAMES = {
    ".git", "__pycache__", ".pytest_cache", "build", "dist", "tests", "engine",
    "editor", "screenshots", ".screenshots", "pack.py", "conftest.py",
    ".gitignore", "requirements.txt", "requirements-dev.txt",
    "src",  # P26 T5：原始素材/原作参考不进产物（月光漫步省约 15MB）
    "saves",  # 开发者本地存档不进产物（玩家首次运行在 exe 旁自建）
    "pack_config.json",  # P35：打包档案含运营号等内部信息，不进玩家产物
    "game_info.json",    # 构建成功后自动生成，避免复制到源目录后被旧值覆盖
    "icon.png", "icon.ico",  # 图标已嵌入 exe，不再在产物根目录重复放一份
}

# P28 T6：引擎只依赖标准库 + pygame，开发机环境里的这些包会被 PyInstaller 误打包。
# numpy 本体+OpenBLAS 约 26MB，其余为无关依赖；排除后产物从 86MB 降到 60MB 级别。
_EXCLUDE_MODULES = (
    "numpy", "pythonnet", "clr_loader", "yaml", "psutil", "charset_normalizer",
    "win32", "win32ctypes", "pywin32_system32", "tkinter", "unittest", "pydoc",
    "doctest", "ssl", "_ssl",
    # P31-d：引擎全程不做哈希/加密（存档是纯 JSON，无校验和），
    # 这批模块会把 OpenSSL（libcrypto-3.dll，约 5MB）拖进产物。
    # 桌宠是编辑器/引擎功能，游戏包里不出现（用户 2026-11-01 决定：进引擎不进游戏）
    "engine.pet",
    "hashlib", "_hashlib", "_blake2", "_md5", "_sha1", "_sha256", "_sha512",
    "_sha3", "hmac", "secrets",
)


class PackError(Exception):
    """打包错误。中文提示。"""


def _check_game_dir(game_dir: Path) -> None:
    if not game_dir.is_dir():
        raise PackError(f"游戏目录不存在：{game_dir}")
    if not (game_dir / "script.gal").is_file():
        raise PackError(f"游戏目录里缺少 script.gal：{game_dir}")


def _write_entry(build_dir: Path) -> Path:
    """玩家入口统一用 engine/player_app.py（与编辑器内置模板共用同一份）。"""
    entry = ROOT / "engine" / "player_app.py"
    if not entry.is_file():
        raise PackError(f"缺少玩家入口：{entry}")
    return entry


def _run_pyinstaller(entry: Path, name: str, build_dir: Path, dist_dir: Path,
                     icon: Path | None = None) -> None:
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--onedir", "--windowed",
        "--name", name,
        "--distpath", str(dist_dir),
        "--workpath", str(build_dir / "work"),
        "--specpath", str(build_dir),
        "--paths", str(ROOT),
        "--hidden-import", "engine.demo",
        "--optimize", "2",  # P31-d：去掉断言与文档字符串（体积更小，运行行为不变）
    ]
    if icon is not None:
        cmd += ["--icon", str(icon)]
    for module in _EXCLUDE_MODULES:
        cmd += ["--exclude-module", module]
    cmd.append(str(entry))
    print("正在打包（首次较慢，请稍候）……", flush=True)
    proc = subprocess.run(cmd, cwd=str(ROOT))
    if proc.returncode != 0:
        raise PackError(f"PyInstaller 打包失败（退出码 {proc.returncode}），"
                        f"请检查上方输出；常见原因：依赖缺失或杀毒软件拦截")


def _slim_internal(out_dir: Path) -> None:
    """P31-d：清掉重复的 SDL 运行库。

    pygame-ce 的 wheel 自带一份 SDL2*.dll，PyInstaller 又在 _internal 根目录收一份，
    同名同字节、约 4.5MB。Windows 先在 _internal 根目录找 DLL，删 pygame/ 下那份不影响加载。
    """
    internal = out_dir / "_internal"
    pkg = internal / "pygame"
    if not pkg.is_dir():
        return
    saved = 0
    for dll in sorted(pkg.glob("*.dll")):
        twin = internal / dll.name
        if twin.is_file() and twin.stat().st_size == dll.stat().st_size:
            saved += dll.stat().st_size
            dll.unlink()
    if saved:
        print(f"  去重 SDL 运行库：省 {saved / 1024 / 1024:.2f} MB")


def _copytree_into(src: Path, dst: Path) -> None:
    """把 src 目录内容合并进 dst。"""
    shutil.copytree(src, dst, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))


def _copy_game(game_dir: Path, out_dir: Path) -> list[str]:
    """把游戏目录的剧本/资源/插件原样复制进产物目录（跳过开发与版本控制内容）。"""
    copied = []
    for item in sorted(game_dir.iterdir()):
        if item.name in _EXCLUDE_NAMES or item.name.endswith(".md"):
            continue
        target = out_dir / item.name
        if item.is_dir():
            _copytree_into(item, target)
        else:
            shutil.copy2(item, target)
        copied.append(item.name)
    return copied


# P44-D 体积优化：这些资源名由引擎硬编码引用，即使剧本没写也必须保留
_HARD_KEEP_ASSETS = {"title_bg", "cg_locked", "icon"}
_TEXT_EXTS = {".gal", ".json", ".txt", ".md", ".py", ".ini", ".yml", ".yaml"}
_IMAGE_MIN_BYTES = 160 * 1024  # 小于 160KB 的图不值得转码（转码收益低）


def _collect_game_text(out_dir: Path) -> str:
    """收集产物内所有剧本/配置/插件文本，用于判断资源是否被引用。"""
    parts = []
    for p in out_dir.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in _TEXT_EXTS:
            continue
        if "_internal" in p.parts:
            continue
        try:
            parts.append(p.read_text(encoding="utf-8-sig", errors="ignore"))
        except OSError:
            continue
    return "\n".join(parts)


def _asset_referenced(blob: str, name: str) -> bool:
    """按「完整资源名」匹配引用，避免 bg_教室 误命中 bg_教室群像 这类前缀包含。"""
    pattern = (r"(?<![A-Za-z0-9_\u4e00-\u9fff])" + re.escape(name)
               + r"(?![A-Za-z0-9_\u4e00-\u9fff])")
    return re.search(pattern, blob) is not None


def _prune_unused_assets(out_dir: Path) -> None:
    """P44-D：删掉产物里完全没有被剧本/配置/插件引用的图片与音频，避免冗余体积。

    只处理 images/ 与 audio/ 的顶层文件；多层素材（layers/、cg 序列目录）保持原样，
    避免误删按目录约定动态加载的资源。源工程不受影响。
    """
    blob = _collect_game_text(out_dir)
    saved = 0
    for folder in ("images", "audio"):
        d = out_dir / folder
        if not d.is_dir():
            continue
        for p in sorted(d.iterdir()):
            if not p.is_file():
                continue
            stem = p.stem
            base = re.sub(r"_\d+$", "", stem)  # 序列帧 xxx_01.png 视作 xxx 的引用
            if (base in _HARD_KEEP_ASSETS or _asset_referenced(blob, base)
                    or _asset_referenced(blob, stem)):
                continue
            saved += p.stat().st_size
            p.unlink()
    if saved:
        print(f"  清理未引用资源：省 {saved / 1024 / 1024:.2f} MB")


def _optimize_images(out_dir: Path) -> None:
    """P44-D：把体积较大的不透明 PNG 背景转为高质量 JPEG（质量 82，长边 ≤1920）。

    引擎按「先 png 后 jpg」自动回退，剧本无需改任何引用。带透明通道的立绘/UI
    素材保持 PNG 不转码。Pillow 缺失时静默跳过（不影响打包）。
    """
    try:
        from PIL import Image
    except Exception:
        return
    blob = _collect_game_text(out_dir)
    images = out_dir / "images"
    if not images.is_dir():
        return
    saved = 0
    for p in sorted(images.iterdir()):
        if not p.is_file() or p.suffix.lower() != ".png":
            continue
        if p.stat().st_size < _IMAGE_MIN_BYTES:
            continue
        if p.with_suffix(".jpg").exists():
            continue  # 已有同名 jpg，不覆盖原素材
        try:
            with Image.open(p) as im:
                if im.mode in ("RGBA", "LA") or "transparency" in im.info:
                    continue  # 透明素材保留 PNG
                rgb = im.convert("RGB")
                if max(rgb.size) > 1920:
                    ratio = 1920 / max(rgb.size)
                    rgb = rgb.resize((max(1, int(rgb.width * ratio)),
                                      max(1, int(rgb.height * ratio))), Image.LANCZOS)
                jpg = p.with_suffix(".jpg")
                rgb.save(jpg, "JPEG", quality=82, optimize=True, progressive=True)
        except Exception:
            continue
        old = p.stat().st_size
        new = jpg.stat().st_size if jpg.is_file() else old
        # 剧本显式写了 xxx.png 时保留原图（删掉刚生成的 jpg），避免引擎按名找不到
        explicit = (p.name in blob)
        if explicit or not jpg.is_file() or new >= old:
            if jpg.is_file():
                jpg.unlink()
        else:
            saved += old - new
            p.unlink()
    if saved:
        print(f"  压缩背景图：省 {saved / 1024 / 1024:.2f} MB")


_BG_REF = re.compile(r"^[ \t]*@bg[ \t]+([^\s]+)", re.MULTILINE)


def _referenced_backgrounds(out_dir: Path) -> set[str]:
    """产物里所有剧本引用到的背景名（@bg 名称，忽略 fadein= 等参数）。"""
    names: set[str] = set()
    for p in out_dir.rglob("*.gal"):
        if "_internal" in p.parts:
            continue
        try:
            text = p.read_text(encoding="utf-8-sig", errors="ignore")
        except OSError:
            continue
        names.update(_BG_REF.findall(text))
    return names


def _placeholder_font(size: int):
    """占位图字体：优先系统中文黑体；都没有时退回 Pillow 默认字体（只保证不崩）。"""
    from PIL import ImageFont

    for path in ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf",
                 "C:/Windows/Fonts/simsun.ttc"):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _fill_missing_backgrounds(out_dir: Path) -> None:
    """打包兜底：剧本写了但工程里没有的背景，补一张白底占位图并写上缺失文件名。

    只写进产物目录（dist/<游戏名>/images/），不改玩家工程；深灰字保证白底可读。
    Pillow 缺失时静默跳过（不影响打包，运行时会走深色占位）。
    """
    images = out_dir / "images"
    missing = []
    for name in sorted(_referenced_backgrounds(out_dir)):
        if (images / f"{name}.png").is_file() or (images / f"{name}.jpg").is_file():
            continue
        missing.append(name)
    if not missing:
        return
    try:
        from PIL import Image, ImageDraw
    except Exception:
        print(f"  注意：{len(missing)} 张背景缺失（Pillow 不可用，未生成白底占位）")
        return
    images.mkdir(parents=True, exist_ok=True)
    font = _placeholder_font(40)
    for name in missing:
        canvas = Image.new("RGB", (1280, 720), (255, 255, 255))
        draw = ImageDraw.Draw(canvas)
        text = f"缺少素材：{name}.png"
        box = draw.textbbox((0, 0), text, font=font)
        draw.text(((1280 - (box[2] - box[0])) // 2, (720 - (box[3] - box[1])) // 2),
                  text, fill=(60, 60, 60), font=font)
        canvas.save(images / f"{name}.png")
    print(f"  补充缺失背景占位：{len(missing)} 张（{'、'.join(missing)}）")


def pack(game_dir, name=None, icon=None, version=None, publisher=None,
         description=None, release_notes=None) -> Path:
    """打包游戏目录，返回产物目录路径（dist/<游戏名>/）。

    P35：icon 由打包档案解析为 .ico 后传入；version/publisher 等元数据写入
    game_info.json，让产物自带版本与运营号信息。
    """
    game_dir = Path(game_dir).resolve()
    _check_game_dir(game_dir)
    name = name or game_dir.name
    icon_path = Path(icon).resolve() if icon else None
    if icon_path is not None and not icon_path.is_file():
        raise PackError(f"图标文件不存在：{icon_path}")

    build_dir = ROOT / "build" / name
    dist_dir = ROOT / "dist"
    out_dir = dist_dir / name
    if out_dir.exists():
        shutil.rmtree(out_dir)  # 重新打包：清掉上次产物，避免残留旧资源

    entry = _write_entry(build_dir)
    _run_pyinstaller(entry, name, build_dir, dist_dir, icon_path)
    _slim_internal(out_dir)
    copied = _copy_game(game_dir, out_dir)
    # 缺背景兜底：先补白底占位图，再按引用关系清理体积（只动 dist 副本）
    _fill_missing_backgrounds(out_dir)
    # P44-D：产物级体积优化（只动 dist 副本，源工程资源不变）
    _prune_unused_assets(out_dir)
    _optimize_images(out_dir)

    exe = out_dir / f"{name}.exe"
    if not exe.is_file():
        raise PackError(f"打包产物里没有可执行文件：{exe}")
    if version is not None or publisher is not None:
        from engine import packaging

        packaging.write_game_info(out_dir, {
            "game_name": name,
            "version": version or "1.0.0",
            "publisher": publisher or {},
            "description": description or "",
            "release_notes": release_notes or "",
        }, 0)
    total = sum(p.stat().st_size for p in out_dir.rglob("*") if p.is_file())
    print(f"打包完成：{out_dir}")
    print(f"  可执行文件：{exe.name}")
    print(f"  产物体积：{total / 1024 / 1024:.2f} MB")
    print(f"  已复制内容：{'、'.join(copied)}")
    print("把整个目录发给玩家，双击 exe 即可游玩（存档会生成在 exe 旁的 saves/）。")
    return out_dir


def _print_project_list(rows: list[dict]) -> None:
    if not rows:
        print("没有发现可打包的游戏项目（games/ 下需要 script.gal）。")
        return
    print("可打包项目（已打包的优先，可直接用 --bump 迭代新版本）：")
    print(f"  {'状态':<6} {'版本':<10} {'构建':<4} 项目 / 游戏名")
    for row in rows:
        status = "已打包" if row["packaged"] else "未打包"
        latest = row.get("latest") or {}
        print(f"  {status:<6} v{row['version']:<8} #{row.get('build_count', 0):<3} "
              f"{row['project']}  （{row['game_name']}）")
        if latest:
            print(f"         上次产物：{latest.get('output_dir')}  {latest.get('built_at')}")
    print("\n继续打包示例：python pack.py games/<项目> --bump patch")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="pack.py", description="MYONL 一键打包（PyInstaller onedir）")
    ap.add_argument("game_dir", nargs="?", default=None,
                    help="游戏目录（内含 script.gal 与 images/ audio/ fonts/ plugins/）")
    ap.add_argument("--name", default=None, help="游戏名（默认读 pack_config.json，其次目录名）")
    ap.add_argument("--version", default=None, help="固定版本号（如 1.2.0）")
    ap.add_argument("--bump", choices=("patch", "minor", "major"), default=None,
                    help="版本迭代：patch/minor/major")
    ap.add_argument("--icon", default=None, help="自定义图标（游戏目录内 .png/.ico）")
    ap.add_argument("--publisher", default=None, help="运营号名称")
    ap.add_argument("--account", default=None, help="运营号 ID")
    ap.add_argument("--channel", default=None, help="发行渠道（如 Steam / itch.io / 本地）")
    ap.add_argument("--contact", default=None, help="运营联系方式")
    ap.add_argument("--list", action="store_true", help="列出可打包/已打包项目")
    args = ap.parse_args(argv)

    from engine import packaging

    packaging.ensure_tolerant_console()

    if args.list:
        _print_project_list(packaging.list_projects(ROOT / "games", root=ROOT))
        return 0

    if not args.game_dir:
        ap.error("缺少游戏目录（也可用 --list 查看项目）")
    project = Path(args.game_dir).resolve()
    pub_flags = any(x is not None for x in
                    (args.publisher, args.account, args.channel, args.contact))
    publisher = None
    if pub_flags:
        publisher = {
            "name": args.publisher,
            "account_id": args.account,
            "channel": args.channel,
            "contact": args.contact,
        }
    flow = (project / packaging.PROFILE_NAME).is_file() or any((
        args.version, args.bump, args.icon, pub_flags,
    ))

    try:
        if flow:
            result = packaging.pack_project(
                project, version=args.version, bump=args.bump, name=args.name,
                icon=args.icon, publisher=publisher, build_func=pack,
                root=ROOT,
            )
            print(f"  版本：v{result['version']} · 构建 #{result['build_number']}")
            print(f"  游戏名：{result['game_name']}")
            print(f"  运营号：{result['publisher'].get('name')} / "
                  f"{result['publisher'].get('account_id')}")
            print(f"  产物目录：{result['output_dir']}")
            print(f"  产物信息：{result['info_path']}")
            return 0
        pack(project, args.name)
    except (PackError, packaging.PackProfileError) as e:
        print(f"打包失败：{e}", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"打包失败：文件操作出错（{e}）", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
