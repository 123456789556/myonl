"""P55 安卓打包脚手架：把一个「手机网页包」包成 Capacitor 安卓工程。

分工照旧：**不重写播放器**，只给 web/ 里的 H5 套一个原生壳。Android 端要做的事全部
集中在「壳」和「Manifest」上：

  1. 把网页包原样拷进 `www/`（Capacitor 从这个目录加载页面，性能与 H5 完全一致）；
  2. `capacitor.config.json` 定 appId / appName / 深色背景 / 允许竖屏横屏；
  3. `cap add android` 生成原生工程后，改 `AndroidManifest.xml`：
     `screenOrientation="fullSensor"`（竖屏横屏都跟传感器走，不锁死），
     `configChanges` 补全（转屏不重建 Activity，剧本不会因为转屏被重载打死）；
  4. 可选 `--build` 直接出 debug APK。

为什么要走 Capacitor 而不是自己写 WebView：作者不需要装 Android Studio 就能改网页，
壳每年跟着系统更新换一次就行；而且 CI（GitHub Actions）里 `npx cap add android` +
`gradlew assembleDebug` 一条命令就能出 APK，见 `.github/workflows/android-apk.yml`。

用法（本地需要 Node + JDK + Android SDK）：
    py -3 tools\\build_android.py --www dist\\web\\教程示例 --out android-app \\
        --app-name 教程示例 --app-id com.myonl.demo
    py -3 tools\\build_android.py ... --install      # npm install + cap add android
    py -3 tools\\build_android.py ... --install --build   # 再编译出 debug APK

只生成工程不下载依赖（CI 之外的快速检查）：--scaffold-only
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys

APP_ID_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]*(\.[a-zA-Z][a-zA-Z0-9_]*)+$")
REQUIRED_WWW = ("index.html", "pack.json")
CAPACITOR_VERSION = "6.2.0"


class ScaffoldError(Exception):
    """参数或输入不合法；给作者一句人话。"""


def check_www(www: str) -> None:
    """网页包必须带 index.html 和 pack.json，否则壳里一开就是白屏。"""
    if not os.path.isdir(www):
        raise ScaffoldError(f"网页包目录不存在：{www}")
    missing = [n for n in REQUIRED_WWW if not os.path.isfile(os.path.join(www, n))]
    if missing:
        raise ScaffoldError("网页包不完整，缺：" + "、".join(missing) +
                            "（先跑 py -3 -m engine.webpack）")


def validate_app_id(app_id: str) -> str:
    app_id = (app_id or "").strip()
    if not APP_ID_RE.match(app_id):
        raise ScaffoldError(f"appId 不合法：{app_id}（要像 com.myonl.demo，每段以字母开头）")
    return app_id


def _write_json(path: str, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def write_scaffold(out: str, www: str, app_name: str, app_id: str) -> dict:
    """生成 Capacitor 工程骨架（不下载依赖）。返回关键路径。"""
    check_www(www)
    app_id = validate_app_id(app_id)
    os.makedirs(out, exist_ok=True)

    package_json = {
        "name": re.sub(r"[^A-Za-z0-9_-]", "_", app_name).lower() or "myonl-game",
        "version": "1.0.0",
        "private": True,
        "description": "MYONL 手机版（H5 播放器 + Capacitor 安卓壳）",
        "dependencies": {
            "@capacitor/android": CAPACITOR_VERSION,
            "@capacitor/core": CAPACITOR_VERSION,
        },
        "devDependencies": {"@capacitor/cli": CAPACITOR_VERSION},
    }
    _write_json(os.path.join(out, "package.json"), package_json)

    cap_config = {
        "appId": app_id,
        "appName": app_name,
        "webDir": "www",
        "android": {"backgroundColor": "#0b0d12", "allowMixedContent": False},
    }
    _write_json(os.path.join(out, "capacitor.config.json"), cap_config)

    www_dst = os.path.join(out, "www")
    if os.path.isdir(www_dst):
        shutil.rmtree(www_dst)
    shutil.copytree(www, www_dst)
    return {"out": out, "www": www_dst, "app_id": app_id, "app_name": app_name}


def patch_manifest(xml: str) -> str:
    """给 AndroidManifest 的 MainActivity 打开横竖屏自由切换。

    - `screenOrientation="fullSensor"`：四个方向都跟传感器走（竖屏横屏都能转）；
    - `configChanges` 追加 orientation|screenSize：转屏时不重建 Activity，
      否则 WebView 会重载、剧本回到标题页。
    幂等：已经有这两个设置就不重复加。
    """
    out = xml
    # 1) 屏幕方向
    if "android:screenOrientation" not in out:
        out = re.sub(r"(<activity\b[^>]*?)(\s*android:name=\"\.MainActivity\")",
                     r'\1 android:screenOrientation="fullSensor"\2', out, count=1)
        if "android:screenOrientation" not in out:
            # 兜底：MainActivity 写法不同（自定义类名）时，直接给第一个 activity 加
            out = re.sub(r"(<activity\b)", r'\1 android:screenOrientation="fullSensor"',
                         out, count=1)
    # 2) configChanges
    need = ["orientation", "screenSize", "keyboardHidden"]
    m = re.search(r'android:configChanges="([^"]*)"', out)
    if m:
        have = [c for c in m.group(1).split("|") if c]
        merged = have + [c for c in need if c not in have]
        out = out.replace(m.group(0), 'android:configChanges="' + "|".join(merged) + '"', 1)
    else:
        out = re.sub(r"(<activity\b[^>]*?)(\s*android:name=\"\.MainActivity\")",
                     r'\1 android:configChanges="' + "|".join(need) + r'"\2', out, count=1)
    return out


def patch_project_manifest(android_dir: str) -> str:
    """把补丁写到 android/app/src/main/AndroidManifest.xml，返回文件路径。"""
    path = os.path.join(android_dir, "app", "src", "main", "AndroidManifest.xml")
    if not os.path.isfile(path):
        raise ScaffoldError(f"找不到 AndroidManifest.xml：{path}（cap add android 没跑成？）")
    with open(path, encoding="utf-8") as f:
        xml = f.read()
    patched = patch_manifest(xml)
    if patched != xml:
        with open(path, "w", encoding="utf-8") as f:
            f.write(patched)
    return path


def _run(cmd: list[str], cwd: str) -> None:
    print("$ " + " ".join(cmd))
    proc = subprocess.run(cmd, cwd=cwd, shell=(os.name == "nt"))
    if proc.returncode != 0:
        raise ScaffoldError(f"命令失败（exit {proc.returncode}）：" + " ".join(cmd))


def install_and_add_android(out: str) -> str:
    """npm install + cap add android，然后打 Manifest 补丁。返回 android 目录。"""
    _run(["npm", "install"], out)
    _run(["npx", "cap", "add", "android"], out)
    android_dir = os.path.join(out, "android")
    patch_project_manifest(android_dir)
    _run(["npx", "cap", "sync", "android"], out)
    return android_dir


def build_debug_apk(out: str) -> str:
    """gradlew assembleDebug，返回 APK 路径。"""
    android_dir = os.path.join(out, "android")
    gradlew = os.path.join(android_dir, "gradlew.bat" if os.name == "nt" else "gradlew")
    if os.path.isfile(gradlew):
        _run([gradlew, "assembleDebug"], android_dir)
    else:
        _run(["gradle", "assembleDebug"], android_dir)
    apk = os.path.join(android_dir, "app", "build", "outputs", "apk", "debug", "app-debug.apk")
    if not os.path.isfile(apk):
        raise ScaffoldError("编译结束但没找到 app-debug.apk")
    return apk


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="把手机网页包包成 Capacitor 安卓工程")
    ap.add_argument("--www", required=True, help="网页包目录（engine.webpack 的产物）")
    ap.add_argument("--out", required=True, help="安卓工程输出目录")
    ap.add_argument("--app-name", default="MYONL 游戏", help="桌面图标下显示的名字")
    ap.add_argument("--app-id", default="com.myonl.game", help="包名，如 com.myonl.demo")
    ap.add_argument("--install", action="store_true", help="跑 npm install + cap add android")
    ap.add_argument("--build", action="store_true", help="再编译 debug APK（需要 Android SDK）")
    ap.add_argument("--scaffold-only", action="store_true", help="只生成工程骨架，不下载依赖")
    args = ap.parse_args(argv)
    try:
        info = write_scaffold(args.out, args.www, args.app_name, args.app_id)
        print(f"已生成安卓工程骨架：{info['out']}（appId={info['app_id']}，www={info['www']}）")
        if args.scaffold_only:
            print("只生成骨架，未下载依赖（--install 才会 npm install + cap add android）")
            return 0
        if args.install or args.build:
            install_and_add_android(args.out)
            print("已生成 android/ 并打好 Manifest 补丁（fullSensor + configChanges）")
        if args.build:
            apk = build_debug_apk(args.out)
            print("APK：" + apk)
        return 0
    except ScaffoldError as e:
        print("失败：" + str(e))
        return 1


if __name__ == "__main__":
    sys.exit(main())
