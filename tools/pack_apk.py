"""把作品打成一个能独立安装的 APK —— 手机端那套"壳 + 替换资源 + 重签"的电脑版实现。

原理（一句话）：模板 APK 里的 `assets/game.html` 就是作品本体，
换掉这一个文件、再按同一张证书重签 v2，包就是新作品。

需要：
  - Java 运行时（JRE 17+）。没装就去 https://adoptium.net 下个 zip 版解压即可。
  - 模板 APK：`android/template.apk`（从 Release 里扒的 v1.2.0，2.2 MB）
  - 签名器：`tools/vendor/uber-apk-signer.jar`（内置官方 apksig，重签走它）

用法：
  python tools/pack_apk.py --game path/to/game.html --out 作品.apk
  python tools/pack_apk.py --game path/to/game.html --name 我的游戏
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "android" / "template.apk"
SIGNER = ROOT / "tools" / "vendor" / "uber-apk-signer.jar"
KEYSTORE = ROOT / "android" / "keystore" / "myonl-test.p12"
KS_ALIAS = "myonl"
KS_PASS = os.environ.get("MYONL_STORE_PASS", "").strip()

# 模板里作品本体就这一个文件
GAME_ENTRY = "assets/game.html"


def find_java() -> str:
    """先看环境变量，再找常见安装位置。"""
    java_home = os.environ.get("JAVA_HOME", "").strip()
    if java_home:
        exe = Path(java_home) / "bin" / ("java.exe" if os.name == "nt" else "java")
        if exe.exists():
            return str(exe)
    which = shutil.which("java")
    if which:
        return which
    # 项目里自带的（调试时解压过）
    for p in Path("D:/娱乐工作区/_tools/tmp/apkwork").glob("jdk*/**/bin/java.exe"):
        return str(p)
    raise SystemExit(
        "找不到 java。\n"
        "  装一个就行：https://adoptium.net/temurin/releases/ 选 zip 包解压，\n"
        "  然后把 bin 目录加进 PATH，或设 JAVA_HOME 指向解压出来的目录。"
    )


def replace_game(template: Path, game_html: Path, out_unsigned: Path,
                 extra: dict | None = None) -> None:
    """复制模板、换掉 assets/game.html，再补进额外素材。其余字节原样保留。

    extra 是 {"assets/bg.png": 本地路径} 这样的表。键按"相对 APK 的 assets/ 根"
    来理解，所以 assets/ 下的素材在包里的真实位置是 assets/assets/bg.png——
    因为 game.html 也躺在 assets/ 里，它写 src="assets/bg.png" 时，
    浏览器相对的就是自己那一层。这个双 assets 不是笔误。
    """
    payload = game_html.read_bytes()
    # extra 的键按"相对 APK 的 assets/ 根"来理解；模板里可能已经有同名条目
    # （比如 myonl-player.js 编辑器自己就带一份），那就**换成新的**，
    # 不能追加——ZIP 里同名条目重复，apksig 会直接拒签。
    merged = {"assets/" + rel: Path(src) for rel, src in (extra or {}).items()}
    merged[GAME_ENTRY] = None  # 占位，下面单独走 payload
    with zipfile.ZipFile(template) as zin, zipfile.ZipFile(out_unsigned, "w") as zout:
        for item in zin.infolist():
            if item.filename == GAME_ENTRY:
                data = payload
            elif item.filename in merged and merged[item.filename] is not None:
                data = merged.pop(item.filename).read_bytes()
            else:
                data = zin.read(item.filename)
            info = zipfile.ZipInfo(item.filename, date_time=item.date_time)
            info.compress_type = item.compress_type
            info.external_attr = item.external_attr
            info.internal_attr = item.internal_attr
            info.create_system = item.create_system
            zout.writestr(info, data)
        # 模板里没有的，补进去
        for name, src in merged.items():
            if src is None:
                continue
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            zout.writestr(info, src.read_bytes())


def sign(java: str, unsigned: Path, out_apk: Path) -> str:
    """用 uber-apk-signer 重签。它会自己丢掉旧签名块，再写 v2 + v3。"""
    if not KS_PASS:
        raise SystemExit(
            "缺 MYONL_STORE_PASS。签名密码不从代码里读，走环境变量：\n"
            '  $env:MYONL_STORE_PASS="..."   然后重跑'
        )
    # 输出目录就用输入所在目录：uber 在 Windows 上对 Temp 目录写文件会报拒绝访问
    workdir = unsigned.parent
    cmd = [
        java, "-jar", str(SIGNER),
        "--apks", str(unsigned),
        "--ks", str(KEYSTORE),
        "--ksAlias", KS_ALIAS,
        "--ksPass", KS_PASS,
        "--ksKeyPass", KS_PASS,
        "--allowResign",
        "--skipZipAlign",          # zipalign 只是对齐优化，不影响能不能装
        "--out", str(workdir),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    log = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0 or "signature verified" not in log:
        raise SystemExit("签名失败：\n" + log[-2000:])
    produced = sorted(workdir.glob("*-signed.apk"))
    if not produced:
        raise SystemExit("签名成功但没找到产物：\n" + log[-1500:])
    shutil.move(str(produced[0]), str(out_apk))
    # 从日志里把验签结论摘出来，回给人看
    for line in log.splitlines():
        if "signature verified" in line or "SHA256:" in line:
            print("  " + line.strip())
    return log


def safe_name(text: str) -> str:
    return re.sub(r"[^\w\u4e00-\u9fff]+", "_", text).strip("_") or "game"


def main() -> None:
    ap = argparse.ArgumentParser(description="把作品打成一个独立 APK")
    ap.add_argument("--game", default="", help="作品 html 路径（单文件内联那种）")
    ap.add_argument("--web-dir", default="",
                    help="build_web 出的目录（含 index.html + assets/）。素材走外链，"
                         "作品体积不再受单文件内存限制——这是大作品那条路")
    ap.add_argument("--out", default="", help="输出的 .apk 路径，不给就按作品名放在 dist/")
    ap.add_argument("--name", default="", help="作品名，用于默认输出文件名")
    args = ap.parse_args()

    if not args.game and not args.web_dir:
        raise SystemExit("要给 --game <单文件 html> 或者 --web-dir <目录>，二选一")

    extra: dict = {}
    if args.web_dir:
        d = Path(args.web_dir)
        idx = d / "index.html"
        if not idx.is_file():
            raise SystemExit(f"目录里没有 index.html：{d}")
        game = idx
        # web 包是「壳 + 清单 + 播放器 + 素材」四层：
        #   index.html（2 KB 壳）→ 改成 assets/game.html
        #   pack.json / myonl-*.js  → 放 assets/ 根下，跟 game.html 同级
        #   assets/                 → 放 assets/assets/（相对 game.html 那一层）
        # PWA 那几样（manifest / icons / apple-touch-icon）在 APK 里没有意义，跳过。
        skip = {"index.html", "manifest.json", "apple-touch-icon.png"}
        for f in sorted(d.rglob("*")):
            if not f.is_file():
                continue
            rel = f.relative_to(d).as_posix()
            if rel in skip or rel.startswith("icons/"):
                continue
            extra[rel] = f
        if not extra:
            print("  提示：这个 web 目录是空的，打出来会是白屏")
    else:
        game = Path(args.game)
        if not game.exists():
            raise SystemExit(f"找不到作品文件：{game}")

    if not TEMPLATE.exists():
        raise SystemExit(
            f"缺模板 APK：{TEMPLATE}\n"
            "  去 Release 页下载 v1.2.0 的 apk，改名放到 android/template.apk"
        )
    if not SIGNER.exists():
        raise SystemExit(f"缺签名器：{SIGNER}")

    java = find_java()
    name = safe_name(args.name or (game.parent.name if args.web_dir else game.stem))
    if args.out:
        out_apk = Path(args.out)
    else:
        out_apk = ROOT / "dist" / "apk" / f"{name}.apk"
    out_apk.parent.mkdir(parents=True, exist_ok=True)

    print(f"作品  : {game}  ({game.stat().st_size:,} B)")
    if extra:
        total = sum(p.stat().st_size for p in extra.values())
        print(f"素材  : {len(extra)} 个文件，合计 {total:,} B（走外链，不进 HTML）")
    print(f"模板  : {TEMPLATE}  ({TEMPLATE.stat().st_size:,} B)")
    print(f"签名器: {SIGNER.name}")

    # Java 侧处理中文文件名会乱码（apksig 用本地编码打开文件），
    # 所以进出签名器这一段一律用 ASCII 名，签完再改回中文。
    unsigned = out_apk.parent / "wip-unsigned.apk"
    print("1/2  换掉 assets/game.html …")
    replace_game(TEMPLATE, game, unsigned, extra)
    print(f"      换完 {unsigned.stat().st_size:,} B")

    print("2/2  重签 v2 …")
    signed_tmp = out_apk.parent / "wip-signed.apk"
    sign(java, unsigned, signed_tmp)
    unsigned.unlink(missing_ok=True)
    if signed_tmp != out_apk:
        shutil.move(str(signed_tmp), str(out_apk))

    print(f"\n完成：{out_apk}  ({out_apk.stat().st_size:,} B)")
    print("传到手机上点开就能装。第一次装会提示「未知来源」，允许一次即可。")


if __name__ == "__main__":
    main()
