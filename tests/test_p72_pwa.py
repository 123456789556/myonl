"""P72 PWA：主屏图标 + manifest + iOS 全屏 meta + 启动遮罩。

覆盖：
1. manifest 的方向映射与 short_name 截断
2. write_bundle 真的落盘（图标是 PNG、manifest 可解析）
3. inline_manifest 是 data URI 且能解回同一份配置（单文件版走这条）
4. 两套模板都带 manifest / apple meta / #boot
5. 真编一次单文件，产物里搜得到 apple-mobile-web-app-capable 与 #boot
"""

import base64
import json
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")  # 无头，须在 import pygame 前
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest  # noqa: E402

from engine import pwa  # noqa: E402
from engine import webpack as W  # noqa: E402

pytestmark = [pytest.mark.unit]


def test_manifest_orientation_and_short_name():
    m = pwa.manifest_dict("这是一个名字特别长的视觉小说作品标题", "portrait")
    assert m["orientation"] == "portrait"
    assert m["display"] == "standalone"
    assert m["start_url"] == "./"
    assert len(m["short_name"]) <= 12
    # 非法方向回落 any，别把 manifest 写成浏览器认不出的值
    assert pwa.manifest_dict("x", "diagonal")["orientation"] == "any"
    assert pwa.manifest_dict("x", "landscape")["orientation"] == "landscape"


def test_write_bundle_files(tmp_path):
    out = str(tmp_path)
    info = pwa.write_bundle(out, "教程示例", "portrait")
    for rel in ("manifest.json", "icons/icon-192.png", "icons/icon-512.png",
                "icons/icon-512-maskable.png", "apple-touch-icon.png"):
        assert rel in info["files"], rel
        assert os.path.isfile(os.path.join(out, rel)), rel
    with open(os.path.join(out, "manifest.json"), encoding="utf-8") as f:
        man = json.load(f)
    assert man["name"] == "教程示例"
    assert [i["sizes"] for i in man["icons"]] == ["192x192", "512x512", "512x512"]
    assert man["icons"][-1]["purpose"] == "maskable"
    # PNG 头：89 50 4E 47
    with open(os.path.join(out, "icons/icon-512.png"), "rb") as f:
        assert f.read(4) == b"\x89PNG"


def test_inline_manifest_roundtrip():
    uri = pwa.inline_manifest("标题", "landscape")
    assert uri.startswith("data:application/manifest+json;base64,")
    raw = base64.b64decode(uri.split(",", 1)[1])
    man = json.loads(raw.decode("utf-8"))
    assert man["name"] == "标题"
    assert man["orientation"] == "landscape"
    assert man["icons"][0]["src"].startswith("data:image/png;base64,")


def test_web_template_has_pwa_head():
    html = W._render_html("标题", "portrait")
    assert 'rel="manifest" href="manifest.json"' in html
    assert 'rel="apple-touch-icon"' in html
    assert "apple-mobile-web-app-capable" in html
    assert 'id="boot"' in html
    assert "bootpulse" in html


def test_single_template_has_pwa_head():
    html = W._render_single_html("标题", "{}", "", "any")
    assert 'rel="manifest" href="data:application/manifest+json;base64,' in html
    assert "apple-mobile-web-app-capable" in html
    assert 'rel="apple-touch-icon" href="data:image/png;base64,' in html
    assert 'id="boot"' in html


def test_single_export_really_contains_pwa(tmp_path):
    """真编一次：确认开关不是只在模板里，产物文件里得有。"""
    root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)),
                                              ), "games", "教程示例")
    if not os.path.isdir(root):
        pytest.skip("示例作品不在这台机器上")
    out = os.path.join(str(tmp_path), "demo.html")
    W.build_single(root, out, title="教程示例")
    with open(out, encoding="utf-8") as f:
        html = f.read()
    assert "apple-mobile-web-app-capable" in html
    assert 'id="boot"' in html
    assert "data:application/manifest+json;base64," in html
