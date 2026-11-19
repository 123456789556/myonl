# -*- coding: utf-8 -*-
"""P136 技术债 2 / 3：安卓壳的「发给朋友」分享出口 + 接住「用本应用打开」的作品文件。

本机没有 JDK / Android SDK，APK 只能靠 GitHub Actions 编出来，所以这里守的是
壳层源码与 Manifest 配置是否按 Android 官方要求配齐；编译/真机行为未验证，报告里如实标注。

守护点：
- T2：FileProvider 注册、authority 与 paths 一致、分享桥走 ACTION_SEND + content URI + 读权限；
- T3：ACTION_VIEW intent-filter 合规（DEFAULT/BROWSABLE + MIME），Java 把 .json/.gal/.html
  接到已有导入链路 __myonlImportLib / __MYONLShareReceive。
"""
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "android" / "app" / "src" / "main"
JAVA = MAIN / "java" / "net" / "myonl" / "player" / "MainActivity.java"
MANIFEST = MAIN / "AndroidManifest.xml"
PATHS = MAIN / "res" / "xml" / "file_paths.xml"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


# ---------- T2：分享出口 ----------

def test_fileprovider_registered_with_matching_authority():
    manifest = _read(MANIFEST)
    java = _read(JAVA)
    authority = "net.myonl.player.fileprovider"
    assert f'android:authorities="{authority}"' in manifest, "Manifest 没注册 FileProvider"
    assert f'"{authority}"' in java, "Java 里的 authority 与 Manifest 不一致"
    assert "androidx.core.content.FileProvider" in manifest
    assert "android:exported=\"false\"" in manifest
    assert "android:grantUriPermissions=\"true\"" in manifest
    assert "@xml/file_paths" in manifest


def test_file_paths_xml_covers_cache_exports():
    xml = _read(PATHS)
    assert "<cache-path" in xml, "成品落在私有 cache，paths 必须配 cache-path"
    assert "exports" in xml


def test_share_bridge_uses_content_uri_and_grants_read():
    java = _read(JAVA)
    assert "FileProvider.getUriForFile" in java
    assert "ACTION_SEND" in java
    assert "EXTRA_STREAM" in java
    assert "FLAG_GRANT_READ_URI_PERMISSION" in java
    # 不能再把 file:// URI 直接塞给别的 App（7+ 会抛 FileUriExposedException）
    assert "Uri.fromFile" not in java


def test_frontend_calls_share_bridge_after_save():
    off = _read(ROOT / "editor" / "gal_offline.js")
    assert "bridge.share" in off, "保存落地后没有调分享桥"


# ---------- T3：VIEW 接收 ----------

def test_manifest_declares_view_filter_for_work_files():
    manifest = _read(MANIFEST)
    assert "android.intent.action.VIEW" in manifest
    assert "android.intent.category.BROWSABLE" in manifest
    for mime in ("text/html", "application/json", "text/plain"):
        assert f'android:mimeType="{mime}"' in manifest, f"VIEW 缺 {mime}"


def test_java_routes_view_to_existing_import():
    java = _read(JAVA)
    assert "ACTION_VIEW" in java
    assert "ingestView" in java
    # 接到已有导入链路，不新造一套存储
    assert "__myonlImportLib" in java, ".json/.gal 没接到作品库导入链路"
    assert "__MYONLShareReceive" in java, ".html 成品没接到素材接收回调"
    # 三种作品文件都要分流
    assert '.endsWith(".json")' in java
    assert '.endsWith(".gal")' in java
    assert '.endsWith(".html")' in java


def test_view_reads_uri_with_size_cap():
    java = _read(JAVA)
    assert "it.getData()" in java
    assert "readCapped" in java, "VIEW 进来的文件也要走 24MB 封顶，不能直接读全量"
