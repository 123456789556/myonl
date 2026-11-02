# -*- coding: utf-8 -*-
"""素材批量导入（大量照片 / 短视频）测试。

覆盖 tools/import_assets.py：
1. 照片 → 背景：裁切到画布尺寸、文件名清洗、内容去重、清单/片段落盘
2. 立绘 → 透明 PNG（按高度缩放，保留 alpha）
3. 同名冲突策略（rename）
4. 短视频 → 帧序列（@video 格式、实际 fps、帧数）
5. dry-run 不落盘
"""
from __future__ import annotations

import json
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

from tools.import_assets import import_folder  # noqa: E402

pytestmark = [pytest.mark.unit]


def test_JPG质量预设影响体积(tmp_path):
    """A3：--quality 低值输出更小（PNG 无损，JPG 受质量影响）。"""
    src = tmp_path / "src"
    src.mkdir()
    noisy = Image.new("RGB", (1280, 720))
    draw = ImageDraw.Draw(noisy)
    for i in range(0, 1280, 6):
        draw.line([(i, 0), (i, 720)], fill=(i % 255, (i * 3) % 255, (i * 7) % 255))
    noisy.save(src / "图.png")

    low = _project(tmp_path)
    import_folder(src, low, quality=25)
    high = tmp_path / "game_high"
    (high / "images").mkdir(parents=True)
    (high / "config.json").write_text(json.dumps({"canvas_size": [1280, 720]}),
                                      encoding="utf-8")
    import_folder(src, high, quality=95)

    low_bytes = (low / "images" / "bg_图.jpg").stat().st_size
    high_bytes = (high / "images" / "bg_图.jpg").stat().st_size
    assert low_bytes < high_bytes, f"质量 25 应比 95 更小（{low_bytes} vs {high_bytes}）"


def _project(tmp_path: Path) -> Path:
    project = tmp_path / "game"
    (project / "images").mkdir(parents=True)
    (project / "config.json").write_text(json.dumps({"canvas_size": [1280, 720]}),
                                         encoding="utf-8")
    return project


def _photo(path: Path, color, size=(800, 600)) -> None:
    Image.new("RGB", size, color).save(path, "JPEG")


def test_照片导入_裁切_清洗_去重_清单(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    _photo(src / "日落 一.jpg", (255, 140, 60))
    _photo(src / "教室.jpg", (60, 120, 200))
    (src / "副本.jpg").write_bytes((src / "日落 一.jpg").read_bytes())
    project = _project(tmp_path)

    result = import_folder(src, project)

    assert result["summary"] == {"ok": 2, "total": 3}
    files = sorted(p.name for p in (project / "images").glob("*.jpg"))
    # 去重保留「先扫到」的那份（排序后 副本.jpg 在 日落 一.jpg 之前），内容相同即等价
    assert len(files) == 2 and "bg_教室.jpg" in files
    assert any(name in ("bg_副本.jpg", "bg_日落_一.jpg") for name in files)
    with Image.open(project / "images" / "bg_教室.jpg") as im:
        assert im.size == (1280, 720)

    report = json.loads((project / "import_report.json").read_text(encoding="utf-8"))
    assert report["summary"] == {"ok": 2, "total": 3}
    assert any(item["status"] == "skipped" for item in report["items"])

    manifest = json.loads((project / "asset_manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["assets"]) == 2 and "bg_教室" in {a["name"] for a in manifest["assets"]}
    snippets = (project / "import_snippets.gal").read_text(encoding="utf-8")
    assert "@bg bg_教室" in snippets


def test_立绘导入_透明png且按高度缩放(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    im = Image.new("RGBA", (400, 800), (0, 0, 0, 0))
    ImageDraw.Draw(im).rectangle((100, 100, 300, 700), fill=(200, 80, 120, 255))
    im.save(src / "微笑.png")
    project = _project(tmp_path)

    result = import_folder(src, project, kind="sprite", prefix="林晚_", fmt="png")

    assert result["summary"]["ok"] == 1
    out = project / "images" / "林晚_微笑.png"
    assert out.is_file()
    with Image.open(out) as got:
        assert got.mode == "RGBA"
        assert got.size[1] == 720


def test_同名冲突默认改名(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    _photo(src / "教室.jpg", (60, 120, 200))
    project = _project(tmp_path)
    import_folder(src, project)
    import_folder(src, project)
    names = sorted(p.name for p in (project / "images").glob("*.jpg"))
    assert names == ["bg_教室.jpg", "bg_教室_2.jpg"]


def _make_video(path: Path, frames: int = 10, rate: int = 10, size=(160, 90)) -> None:
    av = pytest.importorskip("av")
    container = av.open(str(path), "w")
    stream = container.add_stream("mpeg4", rate=rate)
    stream.width, stream.height, stream.pix_fmt = size[0], size[1], "yuv420p"
    for n in range(frames):
        img = Image.new("RGB", size, (n * 20 % 255, 40, 90))
        frame = av.VideoFrame.from_image(img)
        for packet in stream.encode(frame):
            container.mux(packet)
    for packet in stream.encode():
        container.mux(packet)
    container.close()


def test_短视频转帧序列(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    _make_video(src / "教室开场.mp4")
    project = _project(tmp_path)

    result = import_folder(src, project, include_images=False)

    assert result["summary"]["ok"] == 1
    frames = sorted((project / "images" / "videos").glob("教室开场_*.png"))
    assert len(frames) >= 5
    assert frames[0].name == "教室开场_001.png"
    with Image.open(frames[0]) as im:
        assert im.size == (1280, 720)
    manifest = json.loads((project / "asset_manifest.json").read_text(encoding="utf-8"))
    video = [a for a in manifest["assets"] if a["type"] == "video"][0]
    assert video["frames"] == len(frames)
    assert 5 <= video["fps"] <= 12  # 源 10fps，实际输出 fps 按帧数/时长反算
    snippets = (project / "import_snippets.gal").read_text(encoding="utf-8")
    assert "@video 教室开场 fps=" in snippets


def test_dry_run不落盘(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    _photo(src / "教室.jpg", (60, 120, 200))
    project = _project(tmp_path)
    result = import_folder(src, project, dry_run=True)
    assert result["summary"]["ok"] == 1
    assert not any((project / "images").glob("*.jpg"))
    assert not (project / "import_report.json").exists()


def test_竖屏照片自动模糊填充(tmp_path):
    """抖音式 9:16 照片：默认不裁掉大半，而是模糊背景 + 完整内容居中（16:9 画面）。"""
    src = tmp_path / "src"
    src.mkdir()
    im = Image.new("RGB", (1080, 1920), (30, 90, 160))
    ImageDraw.Draw(im).rectangle((340, 700, 740, 1220), fill=(255, 220, 120))
    im.save(src / "抖音截图.jpg", "JPEG")
    project = _project(tmp_path)

    import_folder(src, project)

    out = project / "images" / "bg_抖音截图.jpg"
    assert out.is_file()
    with Image.open(out) as got:
        assert got.size == (1280, 720)
        r, g, b = got.convert("RGB").getpixel((2, 2))
        # 角落是模糊背景，不是 letterbox 纯黑
        assert r + g + b > 40


def test_竖屏短视频自动模糊填充(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    _make_video(src / "抖音片段.mp4", frames=8, rate=10, size=(120, 220))
    project = _project(tmp_path)

    import_folder(src, project, include_images=False)

    frames = sorted((project / "images" / "videos").glob("抖音片段_*.png"))
    assert frames
    with Image.open(frames[0]) as got:
        assert got.size == (1280, 720)
        r, g, b = got.convert("RGB").getpixel((2, 2))
        assert r + g + b > 20
