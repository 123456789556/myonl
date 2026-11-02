# -*- coding: utf-8 -*-
"""自带素材（模板/示例工程）守护。

用户反馈：软件自带素材太少，看到的很多是实验素材。这里守住三件事：
1. 模板必须有成规模的背景/立绘/音效/BGM（程序生成、可复现）；
2. 模板剧本引用的每个素材都真实存在（@bg/@music/@sfx/@show 表情）；
3. 角色库 characters.json 与立绘文件一一对应。

另守住「空包」的两条底线：
4. 新建游戏必须自带内置素材（不能只给纯色占位块）；
5. 用户把 images/audio 全删掉也不白屏、不卡启动（缺素材走占位 + 标题菜单可用）。
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")  # 无头渲染，须在 import pygame 前生效
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

from engine import data
from engine.parser import parse_file

pytestmark = [pytest.mark.unit]

ROOT = Path(__file__).resolve().parents[1]
TPL = ROOT / "engine" / "templates" / "standard"


def _names(folder: Path, suffix: str) -> set[str]:
    return {p.stem for p in folder.glob(f"*{suffix}")}


def test_模板素材规模():
    images = _names(TPL / "images", ".png")
    audio = _names(TPL / "audio", ".ogg")
    bgs = {n for n in images if n.startswith("bg_")}
    sprites = {n for n in images if not n.startswith("bg_")}
    assert len(bgs) >= 9, f"背景只有 {len(bgs)} 张：{sorted(bgs)}"
    assert len(sprites) >= 5, f"立绘只有 {len(sprites)} 张：{sorted(sprites)}"
    assert sum(1 for n in audio if n.startswith("bgm_")) >= 2, "BGM 至少 2 首"
    assert len([n for n in audio if not n.startswith("bgm_")]) >= 4, "音效至少 4 个"


def test_角色库与立绘对应():
    lib = json.loads((TPL / "characters.json").read_text(encoding="utf-8"))
    ids = [c["id"] for c in lib["characters"]]
    assert "林晚" in ids and "苏晴" in ids
    images = _names(TPL / "images", ".png")
    for c in lib["characters"]:
        assert c["avatars"], f"{c['id']} 没有表情映射"
        for expr, asset in c["avatars"].items():
            assert asset in images, f"{c['id']} 的 {expr} 指向不存在的立绘 {asset}"


def test_模板空包只演示三张背景且不配声音():
    """初始空包保持简单：三张背景、无 BGM/音效，第二幕只有旁白。"""
    instrs = parse_file(str(TPL / "script.gal"))
    bgs = [i["image"] for i in instrs if i["op"] == "bg"]
    assert len(bgs) == 3, f"空包模板应只用三张背景，实际 {bgs}"
    assert not [i for i in instrs if i["op"] in ("music", "sfx")], "空包模板不配声音"
    # 第二段（第二幕）只有旁白
    acts = [[]]
    seen_bg = False
    for ins in instrs:
        if ins["op"] == "bg":
            if seen_bg:
                acts.append([])
            seen_bg = True
        acts[-1].append(ins)
    second = [i for i in acts[1] if i["op"] == "say"]
    assert second and all(i.get("char") in (None, "旁白") for i in second), \
        f"第二幕应只有旁白：{[i.get('char') for i in second]}"


def test_示例剧本引用的素材都存在():
    lib = json.loads((TPL / "characters.json").read_text(encoding="utf-8"))
    avatars = {c["id"]: c["avatars"] for c in lib["characters"]}
    sample = ROOT / "games" / "标准示例"
    instrs = parse_file(str(sample / "script.gal"))
    assert len(instrs) > 30
    for ins in instrs:
        op = ins["op"]
        if op == "bg":
            data.resolve_image(str(TPL), ins["image"])
        elif op == "music":
            data.resolve_audio(str(TPL), ins["track"])
        elif op == "sfx":
            data.resolve_audio(str(TPL), ins["sound"])
        elif op == "show":
            expr = ins.get("expr") or ""
            assert expr in avatars.get(ins["char"], {}), \
                f"@show {ins['char']} {expr} 不在角色库里"
            data.resolve_image(str(TPL), avatars[ins["char"]][expr])


def test_三个自带工程素材一致():
    """标准示例 / 新游戏模板 / 新游戏 都要能直接用上同一套素材。"""
    names = _names(TPL / "images", ".png")
    for game in ("标准示例", "新游戏模板"):
        folder = ROOT / "games" / game / "images"
        missing = names - _names(folder, ".png")
        assert not missing, f"{game} 缺素材：{sorted(missing)}"


def test_新建游戏自带内置素材(tmp_path):
    """编辑器「新建游戏」用 standard 模板：空包里直接有背景/立绘/音效，不是纯色占位块。"""
    from engine.newgame import create_game

    root = create_game("自带素材", str(tmp_path), template="standard")
    images = _names(root / "images", ".png")
    assert {"bg_走廊", "bg_天台", "bg_房间"} <= images
    audio = _names(root / "audio", ".ogg")
    assert {"click", "rain", "bgm_day"} <= audio
    # 剧本引用的背景都能解析（空包一打开就有画面）
    for ins in parse_file(str(root / "script.gal")):
        if ins["op"] == "bg":
            data.resolve_image(str(root), ins["image"])


def test_编辑器新建游戏是极简hello_world(tmp_path):
    """普通玩家新建游戏 = 一行可改可删的旁白；不预置任何图片/音频。"""
    from engine.newgame import create_game

    root = create_game("极简", str(tmp_path), template="hello")
    text = (root / "script.gal").read_text(encoding="utf-8")
    assert "@ hello world!" in text
    assert not list((root / "images").glob("*.*"))
    assert not list((root / "audio").glob("*.*"))
    for name in ("config.json", "settings.json", "gallery_config.json",
                 "pack_config.json", "icon.png"):
        assert (root / name).is_file(), f"极简空包缺少 {name}"


def test_打包补白底占位图并写缺失文件名(tmp_path):
    """打包产物里缺的背景补白底图（深灰字写文件名），已有素材不动。"""
    import importlib.util

    from PIL import Image

    spec = importlib.util.spec_from_file_location("moyul_pack_test", ROOT / "pack.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)

    out = tmp_path / "dist"
    (out / "images").mkdir(parents=True)
    (out / "script.gal").write_text("@bg bg_走廊\n@bg bg_已有\n@end\n", encoding="utf-8")
    existing = out / "images" / "bg_已有.png"
    existing.write_bytes(b"keep-me")

    module._fill_missing_backgrounds(out)

    made = out / "images" / "bg_走廊.png"
    assert made.is_file()
    with Image.open(made) as im:
        assert im.size == (1280, 720)
        assert im.convert("RGB").getpixel((10, 10)) == (255, 255, 255)
    assert existing.read_bytes() == b"keep-me"


def test_发行包配置带上内置模板():
    """存档的发行包必须含 engine/templates，否则发行版里新建游戏拿不到素材。"""
    spec = (ROOT / "editor.spec").read_text(encoding="utf-8")
    assert '"engine", "templates"' in spec or '"engine/templates"' in spec


@pytest.mark.ui
def test_素材全删也不白屏且能开始新游戏(tmp_path):
    """用户把 images/audio 全删掉：标题页仍是深色渐变、菜单可用、首帧走占位背景。"""
    import pygame

    from engine.config import load as load_config
    from engine.newgame import create_game
    from engine.renderer import Renderer
    from engine.runtime import Runtime
    from engine.ui import UI

    root = create_game("删素材", str(tmp_path), template="standard")
    shutil.rmtree(root / "images", ignore_errors=True)
    shutil.rmtree(root / "audio", ignore_errors=True)

    ren = Renderer((1280, 720), str(root))
    try:
        ui = UI(config=load_config(str(root)))
        rt = Runtime()
        rt.load(str(root / "script.gal"))
        ren.render(rt.snapshot(), ui.view())
        # 标题页：不能是白幕（四角与中心都应是深色）
        for pos in ((4, 4), (1275, 4), (640, 360), (4, 715), (1275, 715)):
            r, g, b, *_ = ren._screen.get_at(pos)
            assert (r + g + b) < 600, f"标题页 {pos} 偏白：{(r, g, b)}"
        items = {i["label"]: i["enabled"] for i in ui.view()["items"]}
        assert items.get("开始新游戏") is True
        assert ui.handle("confirm") == {"action": "start_game"}
        # 进入游戏：缺背景走占位渐变，不抛异常、不白屏
        rt.step()
        ren.render(rt.snapshot(), ui.view())
        r, g, b, *_ = ren._screen.get_at((4, 4))
        assert (r + g + b) < 200, f"缺背景时应为深色占位，实际 {(r, g, b)}"
        assert ren._screen.get_at((640, 40)) != pygame.Color(255, 255, 255, 255)
    finally:
        ren.close()
