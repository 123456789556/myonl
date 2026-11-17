"""P95 守护：横竖两套构图（`_p` 变体）+ 构图锚点。

约定只有两条，都是**可选**的：
  · images/{名字}_p.png  —— 另一种构图的同一场景，播放器按当前是横是竖挑一张
  · config.json 的 "focal": {"名字": [x, y]} —— 裁切窗口落在哪，0 贴左/上、0.5 居中

这两条一旦坏掉不会报错，只会静默退回"横图硬塞进竖屏、裁掉七成宽度"，
而那正是玩家一眼能看出来的劣质感 —— 所以要有测试盯着。
"""

import json
import os
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.data import DataError, find_variant_image, resolve_image  # noqa: E402
from engine.webpack import _clean_focal, build_web  # noqa: E402


def _png(path: Path, size=(8, 8), color=(20, 30, 40)) -> None:
    """造一张真 PNG（PIL 是打包链的硬依赖，这里不额外引入）。"""
    from PIL import Image

    Image.new("RGB", size, color).save(path)


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    proj = tmp_path / "proj"
    (proj / "images").mkdir(parents=True)
    (proj / "script.gal").write_text("@bg 教室\n", encoding="utf-8")
    _png(proj / "images" / "教室.png", (64, 36), (90, 80, 70))
    (proj / "config.json").write_text(
        json.dumps({"window_title": "测试", "focal": {"教室": [0.3, 0.45]}},
                   ensure_ascii=False),
        encoding="utf-8")
    return proj


def test_find_variant_image_hits_and_misses(project):
    _png(project / "images" / "教室_p.png", (36, 64), (10, 10, 10))
    assert find_variant_image(str(project), "教室") is not None
    # 没有竖版的老工程必须静默返回 None，不能抛
    assert find_variant_image(str(project), "天台") is None
    assert find_variant_image(str(project), "") is None


def test_resolve_image_still_raises_on_missing(project):
    with pytest.raises(DataError):
        resolve_image(str(project), "不存在的图")


def test_clean_focal_keeps_only_valid():
    out = _clean_focal({"a": [0.2, 0.8], "b": [1.5, 0.5], "c": "x",
                        "d": [0.5], "e": [-0.1, 0.5], "f": [0, 1]})
    assert out == {"a": [0.2, 0.8], "f": [0, 1]}
    assert _clean_focal(None) == {}
    assert _clean_focal(["x"]) == {}


def test_variant_is_packaged_next_to_main(project, tmp_path):
    _png(project / "images" / "教室_p.png", (36, 64), (10, 10, 10))
    out = tmp_path / "web"
    stat = build_web(str(project), str(out))
    pack = json.loads((out / "pack.json").read_text(encoding="utf-8"))
    assert "教室" in pack["assets"]
    assert "教室_p" in pack["assets"], "有竖版图却没打包，竖屏就永远只能用横图"
    assert os.path.isfile(out / "assets" / "教室_p.png")
    assert pack["config"]["focal"] == {"教室": [0.3, 0.45]}
    assert stat["missing"] == []


def test_pack_without_variant_is_unchanged(project, tmp_path):
    out = tmp_path / "web"
    build_web(str(project), str(out))
    pack = json.loads((out / "pack.json").read_text(encoding="utf-8"))
    assert [n for n in pack["assets"] if n.endswith("_p")] == []
    # 没有 focal 的老工程：键在但为空字典，播放器走居中
    assert pack["config"]["focal"] == {"教室": [0.3, 0.45]}


def test_player_picks_by_orientation():
    src = (ROOT / "web" / "myonl-player.js").read_text(encoding="utf-8")
    assert "function pickBgName" in src
    assert 'assets[name + "_p"]' in src
    assert "function blitNamed" in src
    assert "FOCAL = pack.focal" in src
    # 背景绘制必须走带锚点的版本，否则锚点等于没接
    assert "blitNamed(bgName" in src
    assert "blitCover(bgName" not in src, "背景还在走旧的无锚点 cover"


def test_desktop_uses_variant_and_focal():
    media = (ROOT / "engine" / "render_media.py").read_text(encoding="utf-8")
    scene = (ROOT / "engine" / "render_scene.py").read_text(encoding="utf-8")
    assert "def _bg_image" in media
    assert "def _bg_focal" in media
    assert "find_variant_image" in media
    assert "self._bg_image(bg" in scene
    assert "self._bg_focal(bg)" in scene
