# -*- coding: utf-8 -*-
"""P51-T8 验收：字体 Surface 缓存（engine/render_text.py，八大方向 6.3）。

验收口径（计划-P51 T8）：字体 Surface 缓存生效、对话场景帧率提升 ≥20%（对比基线）。
本文件覆盖正确性：命中复用 / 键隔离（文本·颜色·字体·抗锯齿）/ LRU 上限 / 与直出像素一致 /
对话与角色名绘制链路确实走缓存且两次绘制像素完全相同。
性能基准用 `py -3 tools/bench_font_cache.py`（数字留档迭代-02 执行记录）。
"""
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")  # 无头模式，须在 import pygame 前生效
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402
import pytest  # noqa: E402

from engine.render_text import TEXT_CACHE_MAX  # noqa: E402
from engine.renderer import Renderer  # noqa: E402

pytestmark = [pytest.mark.ui]


@pytest.fixture()
def ren(tmp_path):
    r = Renderer((1280, 720), str(tmp_path))
    yield r
    r.close()


def _cached_texts(ren):
    """缓存里出现过的文本（键的第 2 位），用于断言淘汰。"""
    return [key[1] for key in ren._text_cache]


# ==================== 1. 命中与键隔离 ====================

def test_同文本同色命中复用(ren):
    font = ren._font
    first = ren._cached_font_surface(font, "你好，世界", True, (255, 255, 255))
    count = len(ren._text_cache)
    second = ren._cached_font_surface(font, "你好，世界", True, (255, 255, 255))
    assert second is first                     # 同一 Surface 直接复用
    assert len(ren._text_cache) == count       # 命中不产生新条目


def test_文本颜色抗锯齿不同互不复用(ren):
    font = ren._font
    a = ren._cached_font_surface(font, "好感度", True, (255, 255, 255))
    b = ren._cached_font_surface(font, "好感度+1", True, (255, 255, 255))
    c = ren._cached_font_surface(font, "好感度", True, (255, 0, 0))
    d = ren._cached_font_surface(font, "好感度", False, (255, 255, 255))
    assert len({id(a), id(b), id(c), id(d)}) == 4


def test_不同字体对象互不复用(ren):
    a = ren._cached_font_surface(ren._font, "测试", True, (255, 255, 255))
    b = ren._cached_font_surface(ren._small_font, "测试", True, (255, 255, 255))
    assert a is not b
    assert a.get_height() > b.get_height()     # 正文字号 > 小字号


def test_命中内容与直出像素一致(ren):
    font = ren._font
    cached = ren._cached_font_surface(font, "林晚：今晚月色真美", True, (200, 210, 255))
    ren._cached_font_surface(font, "挤一挤缓存", True, (255, 255, 255))  # 加个邻居，防"必然唯一"
    again = ren._cached_font_surface(font, "林晚：今晚月色真美", True, (200, 210, 255))
    direct = font.render("林晚：今晚月色真美", True, (200, 210, 255))
    assert again is cached
    assert cached.get_size() == direct.get_size()
    assert pygame.image.tobytes(cached, "RGBA") == pygame.image.tobytes(direct, "RGBA")


# ==================== 2. 上限与 LRU ====================

def test_默认上限来自常量(ren):
    assert ren._text_cache_max == TEXT_CACHE_MAX == 500
    assert len(ren._text_cache) == 0


def test_超上限淘汰最久未用(ren):
    ren._text_cache_max = 3
    font = ren._font
    for text in ("A", "B", "C"):
        ren._cached_font_surface(font, text, True, (255, 255, 255))
    assert len(ren._text_cache) == 3
    ren._cached_font_surface(font, "A", True, (255, 255, 255))  # 把 A 提为最近使用
    ren._cached_font_surface(font, "D", True, (255, 255, 255))  # 淘汰最久未用的 B
    cached = _cached_texts(ren)
    assert len(ren._text_cache) == 3
    assert "B" not in cached and {"A", "C", "D"} <= set(cached)


# ==================== 3. 对话绘制链路 ====================

def test_富文本台词两次绘制像素相同且第二次全命中(ren):
    rich_line = ren._rich_segments("你好，世界。", ["你好，世界。"])[0]

    first = pygame.Surface(ren.size, pygame.SRCALPHA)
    width1 = ren._blit_rich_line(rich_line, 10, 10, (255, 255, 255), target=first)
    assert width1 > 0 and len(ren._text_cache) > 0
    count = len(ren._text_cache)

    second = pygame.Surface(ren.size, pygame.SRCALPHA)
    width2 = ren._blit_rich_line(rich_line, 10, 10, (255, 255, 255), target=second)
    assert width2 == width1
    assert len(ren._text_cache) == count       # 第二次绘制全部命中，不新增条目
    assert pygame.image.tobytes(first, "RGBA") == pygame.image.tobytes(second, "RGBA")


def test_关闭缓存后画面与开启时一致(ren):
    """缓存只省时间不改画面：绕过缓存直出，像素必须逐字节相同。"""
    rich_line = ren._rich_segments("缓存不能改变画面", ["缓存不能改变画面"])[0]

    with_cache = pygame.Surface(ren.size, pygame.SRCALPHA)
    ren._blit_rich_line(rich_line, 0, 0, (255, 255, 255), target=with_cache)

    original = ren._cached_font_surface
    ren._cached_font_surface = lambda font, text, aa, color: font.render(text, aa, color)
    try:
        without_cache = pygame.Surface(ren.size, pygame.SRCALPHA)
        ren._blit_rich_line(rich_line, 0, 0, (255, 255, 255), target=without_cache)
    finally:
        ren._cached_font_surface = original
    assert pygame.image.tobytes(with_cache, "RGBA") == \
        pygame.image.tobytes(without_cache, "RGBA")


def test_角色名阴影绘制走缓存(ren):
    """角色名每帧都画（正文 + 阴影两色），必须命中缓存。"""
    ren._draw_text_with_shadow("林晚", ren._font, (255, 255, 255), (10, 10))
    count = len(ren._text_cache)
    assert count >= 2                          # 正文与阴影各一条
    ren._draw_text_with_shadow("林晚", ren._font, (255, 255, 255), (10, 10))
    assert len(ren._text_cache) == count


# ==================== 4. 字体度量缓存（折行量宽） ====================

_CORPUS = [
    "雨停在站台尽头，风把旧车票吹到手心。林晚抬头看我，说今晚的车比往常晚。",
    "「MYONL」引擎 v1.0 — 1280×720 / 60 FPS，test 混合中英与标点。",
    "短句。",
    "带换行的第一行\n带换行的第二行更长一些，需要折行处理。",
    "",
    "  前后空格  ",
]


@pytest.mark.parametrize("text", _CORPUS)
@pytest.mark.parametrize("max_width", (120, 260, 480, 760))
def test_度量缓存折行与纯函数逐字等价(ren, text, max_width):
    """缓存版折行必须与 render_utils._wrap_text 结果完全一致（断言逐行相等）。"""
    from engine.render_utils import _wrap_text
    assert ren._wrap_text_cached(text, ren._font, max_width) == \
        _wrap_text(text, ren._font, max_width)


def test_度量缓存命中不重复量宽(ren):
    width = ren._font_width(ren._font, "雨停在")
    assert width == ren._font.size("雨停在")[0]
    count = len(ren._text_width_cache)
    assert ren._font_width(ren._font, "雨停在") == width
    assert len(ren._text_width_cache) == count


def test_度量缓存LRU上限(ren):
    ren._text_width_max = 2
    font = ren._font
    for text in ("甲", "乙"):
        ren._font_width(font, text)
    ren._font_width(font, "甲")            # 甲 → 最近使用
    ren._font_width(font, "丙")            # 淘汰最久未用的乙
    cached = [key[1] for key in ren._text_width_cache]
    assert "乙" not in cached and {"甲", "丙"} <= set(cached)


def test_打字机前缀每帧只多量一条(ren):
    """打字机推进 1 个字时，折行只需新量 1 个前缀（其余命中），这是缓存收益来源。"""
    text = "雨停在站台尽头，风把旧车票吹到手心。"
    ren._wrap_text_cached(text[:12], ren._font, 700)
    before = len(ren._text_width_cache)
    ren._wrap_text_cached(text[:13], ren._font, 700)
    assert len(ren._text_width_cache) - before == 1

# ==================== 4. UI 层绘制链路（T8 接线：横幅/菜单/设置页/回看/画廊） ====================

def test_居中逐行绘制第二次全命中(ren):
    """_blit_centered_lines 原先每次 font.render；接线后第二次绘制不新增缓存条目。"""
    lines = ["缓存不能改变画面", "第二行也要一致"]
    rect = pygame.Rect(0, 0, *ren.size)
    first = pygame.Surface(ren.size, pygame.SRCALPHA)
    ren._blit_centered_lines(lines, rect, (255, 255, 255), target=first)
    count = len(ren._text_cache)
    second = pygame.Surface(ren.size, pygame.SRCALPHA)
    ren._blit_centered_lines(lines, rect, (255, 255, 255), target=second)
    assert len(ren._text_cache) == count
    assert pygame.image.tobytes(first, "RGBA") == pygame.image.tobytes(second, "RGBA")


def test_字距标题第二次绘制全命中(ren):
    """spacing>0 的标题逐字渲染，接缓存后第二次不再逐字 font.render。"""
    first = ren._render_spaced_text("标题", ren._title_font, (255, 255, 255), spacing=6)
    count = len(ren._text_cache)
    second = ren._render_spaced_text("标题", ren._title_font, (255, 255, 255), spacing=6)
    assert len(ren._text_cache) == count
    assert pygame.image.tobytes(first, "RGBA") == pygame.image.tobytes(second, "RGBA")


def test_无字距标题返回缓存同一Surface(ren):
    """spacing=0 且无阴影时直接返回缓存 Surface（调用方只 blit，禁止修改返回值）。"""
    a = ren._render_spaced_text("标题", ren._title_font, (255, 255, 255), spacing=0)
    b = ren._render_spaced_text("标题", ren._title_font, (255, 255, 255), spacing=0)
    assert b is a


def test_UI文案绘制后缓存条目有上限(ren):
    """一轮 UI 文案（菜单/设置/存档行）不应把缓存撑爆。"""
    for i in range(200):
        ren._blit_centered_text(f"设置项 {i}", 10 + i, ren._small_font,
                                (255, 255, 255) if i % 2 else (200, 200, 200))
    assert len(ren._text_cache) <= ren._text_cache_max
