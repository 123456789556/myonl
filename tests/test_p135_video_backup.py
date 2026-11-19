# -*- coding: utf-8 -*-
"""P135 守护：手机端「拿出全部作品（.json）」备份不再把视频还原成图片。

背景（真丢用户数据）：以前导出只带 assets、audio 两个桶，导入又把 assets 里每个
键一律标成 image。而 allSplit() 里真视频（mp4）同时留在 assets，于是带视频的作品
换机恢复后，视频全部被播放器当图片处理 —— 用户以为备份成功，素材其实已经丢了。

这里钉住三件事：
1. 新格式导出带 movies（真视频）和 kinds（类型索引），视频不被标成 image；
2. 导入按桶 + kinds 还原，movies 里的名字 kindOf 仍是 "video"；
3. 旧两桶 JSON（只有 assets+audio）照样能导入，图/音频计数正确，提示说实话。

风格对齐 test_p93_mobile_backup.py / test_p131_movie_video.py：读源码文本断言
契约字面量，外加一份纯 Python 镜像分类逻辑跑计数与类型，不起浏览器、不联网。
"""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
OFFLINE = (ROOT / "editor" / "gal_offline.js").read_text(encoding="utf-8")
NODE = shutil.which("node")

pytestmark = [pytest.mark.unit]


def _block(start_marker, end_marker):
    i = OFFLINE.index(start_marker)
    j = OFFLINE.index(end_marker, i)
    return OFFLINE[i:j]


EXPORT = _block("window.__myonlExportLib = function", "window.__myonlExportPack = function")
IMPORT = _block("window.__myonlImportLib = function", "// 导出条")


# ---------- 1. 导出：视频进 movies + kinds，不再被当图 ----------

def test_export_payload_carries_movies_and_kinds():
    """新格式第三类信息必须落进 JSON：movies 桶和 kinds 类型索引都在。"""
    assert "movies: movies" in EXPORT
    assert "kinds: kinds" in EXPORT
    assert "v: 3" in EXPORT


def test_export_video_labeled_video_not_image():
    """movies 里的名字类型记成 video；从 assets 摘出去，不留在图片桶。"""
    assert "delete assets[k]" in EXPORT
    assert "kinds[k] = \"video\"" in EXPORT
    # 旧 bug 写法：assets 遍历里一律 kinds[k] = "image"，不许再出现在导出侧
    assert 'Object.keys(assets).forEach(function (k) { all[k] = assets[k]; kinds[k] = "image"; });' not in OFFLINE


def test_export_audio_and_image_kinds():
    assert "kinds[k] = \"audio\"" in EXPORT
    assert "kinds[k] = \"image\"" in EXPORT


# ---------- 2. 导入：真视频还原成 video ----------

def test_import_movies_restored_as_video():
    """movies 桶的名字进 restore 时类型必须是 video，kindOf 才会返回 video。"""
    assert "put(k, movies[k], \"video\")" in IMPORT
    assert "restore(all, kinds)" in IMPORT


def test_import_movies_wins_over_assets_on_collision():
    """同一名字既在 assets 又在 movies 时，movies 优先，不能被覆盖回图片。"""
    assert "if (all[k] !== undefined) return;" in IMPORT
    # 遍历顺序：audio → movies → assets，后写的 assets 覆盖不了先写的 movies
    audio_i = IMPORT.index('put(k, audio[k]')
    movies_i = IMPORT.index('put(k, movies[k]')
    assets_i = IMPORT.index('put(k, assets[k]')
    assert audio_i < movies_i < assets_i


# ---------- 3. 旧两桶 JSON：能导入、计数对、提示不撒谎 ----------

def test_import_legacy_two_bucket_path_exists():
    """旧格式没有 kinds / movies：assets 按图、audio 按音频，且明确提示救不回视频。"""
    assert "var legacy = !kindsIn && !Object.keys(movies).length;" in IMPORT
    assert "旧格式备份：视频类型没带走，若有视频会按图片还原" in IMPORT
    # 旧桶读取不能丢
    assert "lib.assets" in IMPORT
    assert "lib.audio" in IMPORT


# ---------- 纯逻辑镜像：分类规则与计数 ----------

def _mirror_export(split):
    """对齐导出侧规则：movies 从 assets 摘出，kinds 按桶记。"""
    assets = dict(split.get("assets", {}))
    audio = dict(split.get("audio", {}))
    movies = dict(split.get("movies", {}))
    kinds = {}
    for k in movies:
        assets.pop(k, None)
        kinds[k] = "video"
    for k in audio:
        kinds[k] = "audio"
    for k in assets:
        kinds[k] = "image"
    return {"assets": assets, "audio": audio, "movies": movies, "kinds": kinds}


def _mirror_import(lib):
    """对齐导入侧规则：movies 优先，kinds 索引次之，assets 兜底 image。"""
    assets = lib.get("assets") if isinstance(lib.get("assets"), dict) else {}
    audio = lib.get("audio") if isinstance(lib.get("audio"), dict) else {}
    movies = lib.get("movies") if isinstance(lib.get("movies"), dict) else {}
    kinds_in = lib.get("kinds") if isinstance(lib.get("kinds"), dict) else None
    legacy = kinds_in is None and not movies
    all_map, kinds = {}, {}

    def put(k, v, kind):
        if k in all_map:
            return
        all_map[k] = v
        kinds[k] = kind

    for k in audio:
        put(k, audio[k], "audio")
    for k in movies:
        put(k, movies[k], "video")
    for k in assets:
        kind = kinds_in[k] if kinds_in and kinds_in[k] in ("audio", "video") else "image"
        put(k, assets[k], kind)
    counts = {"image": 0, "audio": 0, "video": 0}
    for k in kinds.values():
        counts[k] += 1
    return all_map, kinds, legacy, counts


def test_mirror_export_mixed_bag():
    split = {
        "assets": {"bg1.jpg": "data:image/jpeg;base64,x", "clip1.mp4": "data:video/mp4;base64,y"},
        "audio": {"bgm1.mp3": "data:audio/mpeg;base64,z"},
        "movies": {"clip1.mp4": "data:video/mp4;base64,y"},
    }
    out = _mirror_export(split)
    # 视频不在图片桶，类型是 video
    assert "clip1.mp4" not in out["assets"]
    assert out["kinds"]["clip1.mp4"] == "video"
    assert out["kinds"]["bg1.jpg"] == "image"
    assert out["kinds"]["bgm1.mp3"] == "audio"
    assert len(out["assets"]) == 1
    assert len(out["audio"]) == 1
    assert len(out["movies"]) == 1


def test_mirror_import_v3_restores_video():
    lib = {
        "projects": [{"name": "p"}],
        "assets": {"bg1.jpg": "img"},
        "audio": {"bgm1.mp3": "aud"},
        "movies": {"clip1.mp4": "vid"},
        "kinds": {"bg1.jpg": "image", "bgm1.mp3": "audio", "clip1.mp4": "video"},
    }
    all_map, kinds, legacy, counts = _mirror_import(lib)
    assert kinds["clip1.mp4"] == "video"
    assert kinds["bg1.jpg"] == "image"
    assert kinds["bgm1.mp3"] == "audio"
    assert legacy is False
    assert counts == {"image": 1, "audio": 1, "video": 1}
    assert len(all_map) == 3


def test_mirror_import_collision_movies_wins():
    # 旧 bug 场景的重演：视频名字同时混在 assets 里，导入后必须仍是 video
    lib = {
        "projects": [{"name": "p"}],
        "assets": {"clip1.mp4": "wrong-image-bytes"},
        "movies": {"clip1.mp4": "real-video-bytes"},
        "kinds": {"clip1.mp4": "video"},
    }
    _, kinds, _, counts = _mirror_import(lib)
    assert kinds["clip1.mp4"] == "video"
    assert counts["video"] == 1
    assert counts["image"] == 0


def test_mirror_import_legacy_two_bucket_counts():
    lib = {
        "projects": [{"name": "p1"}, {"name": "p2"}],
        "assets": {"a.jpg": "img1", "b.png": "img2"},
        "audio": {"c.mp3": "aud"},
    }
    all_map, kinds, legacy, counts = _mirror_import(lib)
    assert legacy is True
    assert counts == {"image": 2, "audio": 1, "video": 0}
    assert len(all_map) == 3
    # 旧文件没有类型索引，assets 兜底 image，不抛异常
    assert all(kinds[k] == "image" for k in ("a.jpg", "b.png"))
    assert kinds["c.mp3"] == "audio"


# ---------- JS 语法门禁（node 不在就 skip） ----------

@pytest.mark.skipif(not NODE, reason="本机没有 node")
def test_js_syntax_check():
    r = subprocess.run([NODE, "--check", str(ROOT / "editor" / "gal_offline.js")],
                      capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, f"gal_offline.js 语法有问题：{r.stderr}"
