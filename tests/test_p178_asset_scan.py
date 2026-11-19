"""作品体积体检的测试。"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.asset_scan import band_for, human_size, scan  # noqa: E402

pytestmark = [pytest.mark.unit]


def _mk(root, rel, content=b"x"):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(content)
    return path


def test_分档阈值():
    assert band_for(1 << 20)[0] == "single"
    assert band_for(30 << 20)[0] == "single"
    assert band_for((30 << 20) + 1)[0] == "apk"
    assert band_for(300 << 20)[0] == "apk"
    assert band_for((300 << 20) + 1)[0] == "external"
    assert band_for(5 << 30)[0] == "download"


def test_人读体积():
    assert human_size(512) == "512 B"
    assert human_size(2048) == "2.0 KB"
    assert human_size(5 << 20) == "5.0 MB"
    assert human_size(3 << 30) == "3.00 GB"


def test_剧本不计入素材体积(tmp_path):
    root = str(tmp_path)
    _mk(root, "script.gal", b"a" * 1000)
    _mk(root, "config.json", b"{}")
    _mk(root, "images/bg.png", b"b" * 2048)
    out = scan(root)
    # 剧本单独算，不混进 asset_bytes
    assert out["asset_bytes"] == 2048
    assert out["script_bytes"] == 1000 + 2
    assert out["counts"].get("图片") == 1
    assert out["band"] == "single"


def test_最大文件能报出来(tmp_path):
    root = str(tmp_path)
    _mk(root, "images/a.png", b"a" * 100)
    _mk(root, "video/big.mp4", b"v" * 5000)
    out = scan(root)
    assert out["largest"]["path"] == "video/big.mp4"
    assert out["largest"]["bytes"] == 5000
    assert out["counts"].get("视频") == 1


def test_跳过产物目录(tmp_path):
    root = str(tmp_path)
    _mk(root, "images/a.png", b"a" * 100)
    _mk(root, "dist/out.html", b"z" * 9000)
    out = scan(root)
    # dist 是导出产物，不算作品素材，否则体积体检会自己把自己撑爆
    assert out["asset_bytes"] == 100
    assert out["band"] == "single"


def test_大作品会掉出单文件档(tmp_path):
    root = str(tmp_path)
    _mk(root, "audio/voice.mp3", b"x" * (31 << 20))
    out = scan(root)
    assert out["band"] == "apk"
    assert "APK" in out["advice"]
