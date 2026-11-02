# -*- coding: utf-8 -*-
"""P29 A1：图片加载多扩展名（png 优先、jpg 兜底）。
P29 P0：剧本写错不闪退（@set 类型错 / 表达式除零 → 跳过+中文警告，不冒泡）。
P29 P2：资源预检文案随实际后缀生成、多 Runtime 插件注册表互不影响。"""
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")  # 无头模式，须在 import pygame 前生效

import io
import contextlib

import pygame
import pytest

from engine import data, demo
from engine.runtime import Runtime
from engine.renderer import Renderer

pytestmark = [pytest.mark.ui]


def _mk(path, color=(120, 60, 30)):
    img = pygame.Surface((8, 6))
    img.fill(color)
    pygame.image.save(img, str(path))


@pytest.fixture
def images_dir(tmp_path):
    d = tmp_path / "images"
    d.mkdir()
    return tmp_path, d


def test_resolve_image_png优先jpg兜底(images_dir):
    root, d = images_dir
    _mk(d / "bg_a.png")
    _mk(d / "bg_b.jpg")
    assert data.resolve_image(str(root), "bg_a").endswith(".png")
    assert data.resolve_image(str(root), "bg_b").endswith(".jpg")


def test_resolve_image_两者都存在优先png(images_dir):
    root, d = images_dir
    _mk(d / "bg_c.png")
    _mk(d / "bg_c.jpg")
    assert data.resolve_image(str(root), "bg_c").endswith(".png")


def test_resolve_image_都没有抛DataError(images_dir):
    root, _ = images_dir
    with pytest.raises(data.DataError):
        data.resolve_image(str(root), "bg_none")


def test_renderer_load_image_jpg可加载(images_dir):
    root, d = images_dir
    _mk(d / "bg_j.jpg")
    ren = Renderer((1280, 720), str(root))
    try:
        assert ren._load_image("bg_j") is not None
        assert ren._load_image("不存在") is None  # 两者都无 → None 不崩
    finally:
        ren.close()


def test_renderer_load_cg_jpg兜底与旧前缀(images_dir):
    root, d = images_dir
    _mk(d / "cg_x.jpg")        # 新名直接 jpg
    _mk(d / "cg_旧名.jpg")     # 旧名兜底也走 jpg
    ren = Renderer((1280, 720), str(root))
    try:
        assert ren._load_cg("cg_x") is not None
        assert ren._load_cg("旧名") is not None
        assert ren._load_cg("不存在") is None
    finally:
        ren.close()


# ==================== P29 P0：剧本写错不闪退 ====================

def _run_until_say(tmp_path, src, max_steps=50):
    """加载剧本并逐步推进，收集所有 say 事件；遇到 end 停止。不应抛未捕获异常。"""
    f = tmp_path / "t.gal"
    f.write_text(src, encoding="utf-8")
    rt = Runtime()
    rt.load(str(f))
    says = []
    for _ in range(max_steps):
        ev = rt.step()
        if ev.get("type") == "say":
            says.append(ev.get("text"))
        elif ev.get("type") == "end":
            break
    return says


def test_P0_字符串变量加数字不闪退且继续执行(tmp_path):
    # @set x += 1 在 x 是字符串时原来会 TypeError 冒泡闪退；现在应跳过并继续
    src = '@set x = "光"\n@set x += 1\n@ 后续台词\n@end\n'
    says = _run_until_say(tmp_path, src)
    assert says == ["后续台词"]  # 出错的 set 被跳过，下一条台词正常推进


def test_P0_表达式除零不闪退且继续执行(tmp_path):
    # @set x = 1 / 0 原来 ExprError 冒泡闪退；现在应跳过并继续
    src = '@set x = 1 / 0\n@ 后续台词\n@end\n'
    says = _run_until_say(tmp_path, src)
    assert says == ["后续台词"]


def test_P0_if条件除零跳过不闪退(tmp_path):
    # if 块靠缩进出块（Python 风格），@end 是结束游戏指令，不能用来闭合 if
    src = '@if 1 / 0 > 0:\n    @ 分支内\n\n@ 后续\n@end\n'
    says = _run_until_say(tmp_path, src)
    # if 块被跳过，"分支内" 不应出现，"后续" 正常执行
    assert says == ["后续"]


def test_P0_警告信息中文且不影响正常set(tmp_path, capsys):
    # 正常的数字+=数字、字符串=赋值都不受影响；字符串 += 字符串需用 =（parser 不允许 += 字符串）
    src = '@set n = 1\n@set n += 2\n@set s = "ab"\n@ 结果{n}{s}\n@end\n'
    says = _run_until_say(tmp_path, src)
    assert says == ["结果3ab"]  # 正常运算不受影响
    err = capsys.readouterr().err
    assert "剧本警告" not in err  # 没有异常就不该有警告


# ==================== P29 P2：预检文案 / 多实例插件 ====================

def test_precheck_jpg素材不误报(tmp_path, capsys):
    """素材转 JPG（以及 .wav 音频）后，启动预检不应把存在资源报成缺失。"""
    root = tmp_path
    (root / "images").mkdir()
    (root / "audio").mkdir()
    _mk(root / "images" / "bg_a.jpg")
    _mk(root / "images" / "甲_smile.jpg")
    (root / "audio" / "m.wav").write_bytes(b"RIFF")
    script = root / "t.gal"
    script.write_text("@bg bg_a\n@show 甲 smile\n@music m\n@ 台词\n@end\n", encoding="utf-8")

    demo._precheck_resources(str(script), str(root))

    err = capsys.readouterr().err
    assert "资源缺失" not in err


def test_precheck_缺失文案列出所有候选后缀(tmp_path, capsys):
    """缺失时提示应列出 .png / .jpg（音频 .ogg/.mp3/.wav），不再只写死 .png/.ogg。"""
    root = tmp_path
    (root / "images").mkdir()
    (root / "audio").mkdir()
    script = root / "t.gal"
    script.write_text("@bg 没图\n@sfx 没声\n@ 台词\n@end\n", encoding="utf-8")

    demo._precheck_resources(str(script), str(root))

    err = capsys.readouterr().err
    assert "images/没图.png" in err and "images/没图.jpg" in err
    assert "audio/没声.ogg" in err and "audio/没声.wav" in err


def test_多Runtime插件注册表互不影响(tmp_path):
    """同进程两个 Runtime 各自加载插件：后加载的实例不应清空前一个实例的注册表。"""
    for tag in ("a", "b"):
        game = tmp_path / tag
        (game / "plugins").mkdir(parents=True)
        (game / "s.gal").write_text(f"@plug:{tag}\n@end\n", encoding="utf-8")
        (game / "plugins" / f"{tag}.py").write_text(
            "from engine.runtime import register_command\n"
            f"register_command('{tag}', lambda state, args: {{'type': 'plug:{tag}'}})\n",
            encoding="utf-8",
        )

    r1 = Runtime()
    r1.load(str(tmp_path / "a" / "s.gal"))
    r2 = Runtime()
    r2.load(str(tmp_path / "b" / "s.gal"))

    assert r1.step()["type"] == "plug:a"  # r1 的插件仍在
    assert r2.step()["type"] == "plug:b"
