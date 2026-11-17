"""P96 守护：自建 WebView 壳的三条命门。

APK 本身要 JDK + Android SDK 才编得出来，本机没有，所以这里守的是「壳」这一层。
三条都踩过或差点踩：origin 决定存档活不活、签名决定能不能覆盖安装、返回键不留就会一按退出。
"""

import os
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

ROOT = Path(__file__).resolve().parents[1]
ANDROID = ROOT / "android"
MAIN = ANDROID / "app" / "src" / "main"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def test_webview_uses_asset_loader_not_file_scheme():
    """用 file:// 加载 assets 时 localStorage 不保证持久 —— 存档会随壳一起没。

    必须走 WebViewAssetLoader，把 assets 挂到一个稳定的 https origin 上。
    """
    src = _read(MAIN / "java" / "net" / "myonl" / "player" / "MainActivity.java")
    assert "WebViewAssetLoader" in src
    assert "AssetsPathHandler" in src
    assert "https://appassets.androidplatform.net/assets/index.html" in src
    assert "file:///android_asset" not in src, "file:// 的 origin 存不住档"
    assert "setDomStorageEnabled(true)" in src


def test_signing_is_fixed_and_present():
    """覆盖安装要求同一签名；签名一变玩家就得卸载，localStorage 一起没。"""
    gradle = _read(ANDROID / "app" / "build.gradle")
    assert "signingConfigs" in gradle
    assert "PKCS12" in gradle
    assert "myonl-test.p12" in gradle
    store = ANDROID / "keystore" / "myonl-test.p12"
    assert store.is_file(), "固定签名的 keystore 没进仓库"
    assert store.stat().st_size > 1000


def test_manifest_allows_all_orientations():
    xml = _read(MAIN / "AndroidManifest.xml")
    assert 'android:screenOrientation="fullSensor"' in xml
    assert 'screenOrientation="portrait"' not in xml
    assert 'screenOrientation="landscape"' not in xml
    # 转屏不重建 Activity，否则 WebView 重载、剧本回到标题页
    for key in ("orientation", "screenSize", "screenLayout"):
        assert key in xml
    # 没联网需求，就不该申请网络权限
    assert "INTERNET" not in xml


def test_back_key_goes_through_game_first():
    src = _read(MAIN / "java" / "net" / "myonl" / "player" / "MainActivity.java")
    assert "myonlBack" in src
    player = _read(ROOT / "web" / "myonl-player.js")
    assert "window.myonlBack" in player, "壳里按返回键会直接退出游戏"


def test_workflow_builds_release_apk():
    text = _read(ROOT / ".github" / "workflows" / "android-apk.yml")
    for token in ("workflow_dispatch", "setup-java", "setup-android",
                  "engine.webpack", "assembleRelease", "upload-artifact"):
        assert token in text, f"工作流缺 {token}"
    assert "assembleDebug" not in text, "debug 包的签名每次都不同，装不上旧版本"
    assert "capacitor" not in text.lower()


def test_no_leftover_capacitor_route():
    """两条 APK 路线并存只会让人不知道该看哪条。"""
    assert not (ROOT / "tools" / "build_android.py").exists()
    assert not (ROOT / "tests" / "test_android_pack.py").exists()


def test_assets_html_is_generated_not_committed():
    """3 MB 的单文件 HTML 是 CI 产物，不该进仓库。"""
    ignore = _read(ROOT / ".gitignore")
    assert "android/app/src/main/assets/index.html" in ignore
