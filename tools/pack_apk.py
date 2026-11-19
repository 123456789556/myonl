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


def replace_game(template: Path, game_html: Path, out_unsigned: Path) -> None:
    """复制模板、只换 assets/game.html 一个条目。其余字节原样保留。"""
    payload = game_html.read_bytes()
    with zipfile.ZipFile(template) as zin, zipfile.ZipFile(out_unsigned, "w") as zout:
        for item in zin.infolist():
            if item.filename == GAME_ENTRY:
                data = payload
            else:
                data = zin.read(item.filename)
            info = zipfile.ZipInfo(item.filename, date_time=item.date_time)
            info.compress_type = item.compress_type
            info.external_attr = item.external_attr
            info.internal_attr = item.internal_attr
            info.create_system = item.create_system
            zout.writestr(info, data)


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
    ap.add_argument("--game", required=True, help="作品 html 路径（导出的那个 game.html）")
    ap.add_argument("--out", default="", help="输出的 .apk 路径，不给就按作品名放在 dist/")
    ap.add_argument("--name", default="", help="作品名，用于默认输出文件名")
    args = ap.parse_args()

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
    name = safe_name(args.name or game.stem)
    if args.out:
        out_apk = Path(args.out)
    else:
        out_apk = ROOT / "dist" / "apk" / f"{name}.apk"
    out_apk.parent.mkdir(parents=True, exist_ok=True)

    print(f"作品  : {game}  ({game.stat().st_size:,} B)")
    print(f"模板  : {TEMPLATE}  ({TEMPLATE.stat().st_size:,} B)")
    print(f"签名器: {SIGNER.name}")

    # Java 侧处理中文文件名会乱码（apksig 用本地编码打开文件），
    # 所以进出签名器这一段一律用 ASCII 名，签完再改回中文。
    unsigned = out_apk.parent / "wip-unsigned.apk"
    print("1/2  换掉 assets/game.html …")
    replace_game(TEMPLATE, game, unsigned)
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
