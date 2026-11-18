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
    """覆盖安装要求同一签名；签名一变玩家就得卸载，localStorage 一起没。

    keystore 本身**不**在仓库里 —— P104 之后它是从 CI secret 还原的。
    公开仓库里放 p12 + 明文密码，等于谁都能签一个 signature 相同的包，
    覆盖装到已装正版的手机上。所以这里改守另外三件事：

      1. 签名配置存在，且走 PKCS12
      2. 文件名固定 —— 不是每次构建现生成一个新的（换了就等于换签名）
      3. 密码来自环境变量，不是写死在文件里
    """
    gradle = _read(ANDROID / "app" / "build.gradle")
    assert "signingConfigs" in gradle
    assert "PKCS12" in gradle
    assert "myonl-test.p12" in gradle, "签名文件名不固定，换一个就等于换签名"
    assert "myonl-apk-2026" not in gradle, "明文签名密码回到了 build.gradle"
    assert "MYONL_STORE_PASS" in gradle, "密码没从环境变量读，等于又写死了"
    assert "canSign" in gradle, "没有条件式签名，缺 secret 时会静默出一个签不了名的包"


def test_ci_restores_keystore_from_secret():
    """keystore 不在仓库里，CI 就必须自己还原，且必须校验签名有效。

    没校验的话，CI 会开开心心发一个装不上的包 —— 下载的人点开只看到「解析失败」。
    """
    text = _read(ROOT / ".github" / "workflows" / "android-apk.yml")
    assert "MYONL_KEYSTORE_B64" in text, "CI 没从 secret 还原 keystore"
    assert "base64 -d" in text
    assert "apksigner" in text, "没校验签名，可能发出去一个装不上的包"
    assert "verify" in text


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
    for token in ("workflow_dispatch", "setup-java", "ANDROID_HOME",
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


def test_webview_can_show_page_dialogs():
    """没装 WebChromeClient，页面里的 alert/confirm/prompt 会被 WebView 直接吞掉。

    播放器「导入备份」那一步用的就是 confirm：没有 WebChromeClient 时点了没反应，
    玩家以为导入成功了，其实什么都没发生。三个回调必须都在。
    """
    src = _read(MAIN / "java" / "net" / "myonl" / "player" / "MainActivity.java")
    assert "setWebChromeClient" in src, "WebView 没装 WebChromeClient，页面弹窗全哑"
    assert "onJsAlert" in src
    assert "onJsConfirm" in src
    assert "onJsPrompt" in src
    # 玩家点确认必须真的传到 JS，取消也必须真的取消
    assert "result.confirm()" in src
    assert "result.cancel()" in src
    # 页面弹窗用的也是 confirm/prompt：确认这条依赖真实存在
    player = _read(ROOT / "web" / "myonl-player.js")
    assert "confirm(" in player, "播放器依赖 confirm，壳必须能弹"


def test_webview_reports_load_failure():
    """主页加载失败不能只留黑屏 —— 玩家只会以为 App 坏了。"""
    src = _read(MAIN / "java" / "net" / "myonl" / "player" / "MainActivity.java")
    assert "onReceivedError" in src
    assert "isForMainFrame" in src
