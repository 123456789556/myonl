# -*- coding: utf-8 -*-
"""A4：照片转立绘（纯色背景抠透明）。

覆盖 tools/make_sprite_transparent.py：
1. 纯色背景被抠成透明（四角 alpha=0），角色主体保留（中心 alpha=255）
2. 自动裁掉四周空白（输出尺寸小于原图）
3. 目录输入批量处理
4. 边缘羽化默认开启、可关闭
"""
from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from tools.make_sprite_transparent import make_transparent

pytestmark = [pytest.mark.unit]


def _photo_with_bg(path: Path) -> None:
    """白底 + 中间红色圆（模拟「人物 + 纯色背景」）。"""
    img = Image.new("RGB", (400, 600), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.ellipse((100, 120, 300, 520), fill=(200, 60, 60))
    img.save(path)


def test_纯色背景抠透明并裁边(tmp_path):
    src = tmp_path / "photo.jpg"
    _photo_with_bg(src)
    dst = tmp_path / "sprite.png"
    out = make_transparent(src, dst)

    assert out == dst and dst.is_file()
    img = Image.open(dst).convert("RGBA")
    w, h = img.size
    assert w < 400 and h < 600, "四周空白应被裁掉"
    assert img.getpixel((0, 0))[3] == 0, "角上应为透明"
    assert img.getpixel((w // 2, h // 2))[3] == 255, "主体应保留不透明"


def test_可关闭羽化(tmp_path):
    src = tmp_path / "photo.png"
    _photo_with_bg(src)
    hard = make_transparent(src, tmp_path / "hard.png", feather=False)
    soft = make_transparent(src, tmp_path / "soft.png", feather=True)
    assert hard.is_file() and soft.is_file()
    # 羽化后边缘像素存在半透明（0 < a < 255）
    img = Image.open(soft).convert("RGBA")
    hist = img.getchannel("A").histogram()
    assert sum(hist[1:255]) > 0, "羽化应产生半透明边缘"


def test_目录批量处理(tmp_path):
    src_dir = tmp_path / "in"
    src_dir.mkdir()
    for i in range(3):
        _photo_with_bg(src_dir / f"p{i}.jpg")
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    done = 0
    for p in sorted(src_dir.glob("*.jpg")):
        make_transparent(p, out_dir / (p.stem + ".png"))
        done += 1
    assert done == 3
    assert len(list(out_dir.glob("*.png"))) == 3
