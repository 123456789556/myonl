"""P127：编辑器收了四种图片格式，运行时只认两种。

editor.py 的导入白名单是 .png/.jpg/.jpeg/.webp，但 data.py 的 _IMAGE_EXTS 只有
.png/.jpg —— 玩家拖一张 .webp 进去，编辑器里看得见、能预览，
打包或运行的时候却报「缺素材」。同一个格式在两侧说法不同，这种不一致最伤人。
"""
from pathlib import Path

import pytest

from engine import data as data_mod

ROOT = Path(__file__).resolve().parents[1]
EDITOR_PY = (ROOT / "engine" / "editor.py").read_text(encoding="utf-8")
WEBPACK_PY = (ROOT / "engine" / "webpack.py").read_text(encoding="utf-8")

pytestmark = [pytest.mark.unit]


def test_runtime_accepts_what_editor_imports():
    """两侧白名单必须能对上：编辑器能导进来的格式，运行时就得能找到。"""
    for ext in (".png", ".jpg", ".jpeg", ".webp"):
        assert ext in data_mod._IMAGE_EXTS, f"运行时还没认 {ext}"


def test_editor_and_runtime_lists_agree():
    # editor.py 里那行写死的四种，和运行时这份必须一致
    assert '_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")' in EDITOR_PY
    assert data_mod._IMAGE_EXTS == (".png", ".jpg", ".jpeg", ".webp")


def test_missing_hint_follows_the_list():
    """缺素材提示随白名单自动生成，不是另抄一份。"""
    hint = data_mod.image_hint("bg")
    for ext in data_mod._IMAGE_EXTS:
        assert f"images/bg{ext}" in hint


def test_webp_gets_shrunk_like_the_others():
    """webp 也得过大图缩一道 —— 不然一张 3000px 的 webp 原样进单文件包。"""
    assert '".webp") \\' in WEBPACK_PY or '".bmp", ".webp"' in WEBPACK_PY
    assert '".png", ".jpg", ".jpeg", ".bmp", ".webp"' in WEBPACK_PY


def test_webp_is_found_on_disk(tmp_path):
    """真放一个 .webp 到 images/，运行时能解析到它。"""
    images = tmp_path / "images"
    images.mkdir(parents=True)
    (images / "走廊.webp").write_bytes(b"RIFF0000WEBPVP8 ")
    got = data_mod.resolve_image(str(tmp_path), "走廊")
    assert got is not None
    assert str(got).endswith(".webp")
