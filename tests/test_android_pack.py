"""安卓壳的落地检查：脚手架能生成、Manifest 补丁对、CI 工作流在。

APK 本身要 JDK + Android SDK 才编得出来，本机没有，所以这里只守「壳」这一层。
"""
from __future__ import annotations

import json
import os
import sys

import pytest

pytestmark = [pytest.mark.unit]

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import build_android as BA  # noqa: E402


def _make_www(tmp_path):
    www = tmp_path / "web"
    www.mkdir()
    (www / "index.html").write_text("<!doctype html><canvas id=game></canvas>", encoding="utf-8")
    (www / "pack.json").write_text('{"version":1}', encoding="utf-8")
    (www / "myonl-player.js").write_text("//player", encoding="utf-8")
    return www


def test_脚手架的三个文件都在(tmp_path):
    www = _make_www(tmp_path)
    out = tmp_path / "android-app"
    BA.write_scaffold(str(out), str(www), "教程示例", "com.myonl.demo")

    cfg = json.loads((out / "capacitor.config.json").read_text(encoding="utf-8"))
    assert cfg["appId"] == "com.myonl.demo"
    assert cfg["appName"] == "教程示例"
    assert cfg["webDir"] == "www"
    # 网页原样进 www：壳不许改播放器，改的只是外面这层
    assert (out / "www" / "index.html").is_file()
    assert (out / "www" / "pack.json").is_file()
    assert (out / "www" / "myonl-player.js").is_file()
    pkg = json.loads((out / "package.json").read_text(encoding="utf-8"))
    assert "@capacitor/core" in pkg["dependencies"]
    assert "@capacitor/android" in pkg["dependencies"]


def test_网页包缺文件要报人话(tmp_path):
    www = tmp_path / "web"
    www.mkdir()
    (www / "index.html").write_text("x", encoding="utf-8")
    with pytest.raises(BA.ScaffoldError) as e:
        BA.write_scaffold(str(tmp_path / "o"), str(www), "a", "com.myonl.demo")
    assert "pack.json" in str(e.value)


@pytest.mark.parametrize("bad", ["", "demo", "com..demo", "1demo.x", "com.演示"])
def test_包名不合法要拦(bad):
    with pytest.raises(BA.ScaffoldError):
        BA.validate_app_id(bad)


def test_Manifest补丁打开横竖屏():
    xml = (
        '<manifest><application><activity android:name=".MainActivity"\n'
        '            android:configChanges="orientation|keyboardHidden|keyboard|screenSize"\n'
        '            android:exported="true"></activity></application></manifest>'
    )
    out = BA.patch_manifest(xml)
    assert 'android:screenOrientation="fullSensor"' in out
    # 不锁 portrait，也不锁 landscape——四种方向都跟传感器走
    assert 'screenOrientation="portrait"' not in out
    assert 'screenOrientation="landscape"' not in out
    assert "orientation" in out and "screenSize" in out


def test_Manifest补丁可重复跑():
    xml = '<activity android:name=".MainActivity" android:exported="true"></activity>'
    once = BA.patch_manifest(xml)
    twice = BA.patch_manifest(once)
    assert twice == once
    assert once.count("screenOrientation") == 1


def test_Manifest补丁补全configChanges():
    xml = '<activity android:name=".MainActivity" android:configChanges="keyboard"></activity>'
    out = BA.patch_manifest(xml)
    assert "orientation" in out and "screenSize" in out and "keyboard" in out


def test_CI工作流存在且步骤齐全():
    path = os.path.join(ROOT, ".github", "workflows", "android-apk.yml")
    assert os.path.isfile(path), "缺 GitHub Actions 工作流"
    text = open(path, encoding="utf-8").read()
    for token in ("workflow_dispatch", "setup-java", "ANDROID_HOME", "engine.webpack",
                  "tools/build_android.py", "assembleDebug", "upload-artifact"):
        assert token in text, f"工作流缺 {token}"
    # 必须能手动指定工程，不然只有示例工程能出包
    assert "project:" in text


def test_脚手架脚本能当CLI跑(tmp_path):
    www = _make_www(tmp_path)
    out = tmp_path / "cli-out"
    code = BA.main(["--www", str(www), "--out", str(out), "--app-name", "示例",
                    "--app-id", "com.myonl.demo", "--scaffold-only"])
    assert code == 0
    assert (out / "capacitor.config.json").is_file()
