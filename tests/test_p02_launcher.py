# -*- coding: utf-8 -*-
"""tests/test_p02_launcher.py：P0-2 Launcher CLI 验收。

验收项：
  1. default 模板生成 4 份配置（config/settings/gallery_config + script.gal）+ 占位素材
  2. moonlight 模板复刻月光漫步全量资源（剧本 + 开场 + 章节 + 配置 + 图片 + 音频）
  3. moonlight 模板排除 saves/（存档）和 src/（Ren'Py 源码参考）
  4. 未知模板中文拒绝
  5. `python -m engine.new` 入口（engine.new.main）default + moonlight 都能跑
  6. `engine.cli new --template moonlight` 入口工作
  7. moonlight 生成的剧本可被 parser 解析（@include 章节全展开无报错）
  8. 重名不覆盖（moonlight 模板同样遵守）
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from engine import cli, new  # noqa: E402
from engine.newgame import TEMPLATES, create_game  # noqa: E402
from engine.parser import parse_file  # noqa: E402

pytestmark = [pytest.mark.integration]


# ---------- 1. default 模板：配置文件 + 占位素材 ----------

def test_default模板生成配置文件(tmp_path):
    root = create_game("默认模板", str(tmp_path), template="default")
    assert (root / "config.json").is_file()
    assert (root / "settings.json").is_file()
    assert (root / "gallery_config.json").is_file()
    # 配置是合法 JSON
    for fn in ("config.json", "settings.json", "gallery_config.json"):
        json.loads((root / fn).read_text(encoding="utf-8"))
    # settings 默认 splash=true（与月光漫步一致）
    settings = json.loads((root / "settings.json").read_text(encoding="utf-8"))
    assert settings.get("splash") is True
    # 占位素材仍生成
    images = {p.name for p in (root / "images").iterdir() if p.is_file()}
    assert images == {"bg_教室.png", "bg_天台.png", "林晚_微笑.png", "林晚_生气.png"}


# ---------- 2. moonlight 模板：全量资源复刻 ----------

def test_moonlight模板复刻全量资源(tmp_path):
    root = create_game("月光复刻", str(tmp_path), template="moonlight")
    # 根目录关键文件
    for fn in ("script.gal", "开场.gal", "config.json", "settings.json", "gallery_config.json"):
        assert (root / fn).is_file(), f"缺少 {fn}"
    # 章节目录存在且非空
    chapter_dir = root / "章节"
    assert chapter_dir.is_dir()
    gal_files = list(chapter_dir.glob("*.gal"))
    assert len(gal_files) >= 10, f"章节 .gal 数量不足：{len(gal_files)}"
    # images 和 audio 非空
    assert any((root / "images").iterdir())
    assert any((root / "audio").iterdir())
    # gallery_config 是合法 JSON 且非空（月光漫步有 8 个 CG）
    gallery = json.loads((root / "gallery_config.json").read_text(encoding="utf-8"))
    assert len(gallery) >= 6
    # config.window_title 是月光漫步
    config = json.loads((root / "config.json").read_text(encoding="utf-8"))
    assert config.get("window_title") == "月光漫步"


# ---------- 3. moonlight 排除 saves/ 和 src/ ----------

def test_moonlight排除存档和源码(tmp_path):
    root = create_game("月光干净", str(tmp_path), template="moonlight")
    assert not (root / "saves").exists(), "不应复制 saves/ 存档目录"
    assert not (root / "src").exists(), "不应复制 src/ Ren'Py 源码参考目录"


# ---------- 4. 未知模板拒绝 ----------

def test_未知模板拒绝(tmp_path):
    with pytest.raises(ValueError, match="未知模板"):
        create_game("坏模板", str(tmp_path), template="不存在的模板")


def test_TEMPLATES常量包含两种模板():
    assert "default" in TEMPLATES
    assert "moonlight" in TEMPLATES


# ---------- 5. engine.new.main 入口 ----------

def test_new模块入口_default(tmp_path, capsys):
    rc = new.main(["新游戏", "--dir", str(tmp_path)])
    assert rc == 0
    root = tmp_path / "新游戏"
    assert (root / "script.gal").is_file()
    assert (root / "config.json").is_file()
    out = capsys.readouterr().out
    assert "已创建游戏" in out
    assert "模板：default" in out


def test_new模块入口_moonlight(tmp_path, capsys):
    rc = new.main(["月光新", "--dir", str(tmp_path), "--template", "moonlight"])
    assert rc == 0
    root = tmp_path / "月光新"
    assert (root / "script.gal").is_file()
    assert (root / "开场.gal").is_file()
    assert (root / "章节").is_dir()
    out = capsys.readouterr().out
    assert "模板：moonlight" in out


def test_new模块入口_未知模板退出码1(tmp_path, capsys):
    # argparse 的 choices 不合法时直接 SystemExit(2)，不是返回退出码
    with pytest.raises(SystemExit) as excinfo:
        new.main(["坏", "--dir", str(tmp_path), "--template", "bad"])
    assert excinfo.value.code == 2
    assert "已创建游戏" not in capsys.readouterr().out


# ---------- 6. engine.cli new --template moonlight ----------

def test_cli_new_moonlight模板(tmp_path):
    rc = cli.main(["new", "cli月光", "--dir", str(tmp_path), "--template", "moonlight"])
    assert rc == 0
    root = tmp_path / "cli月光"
    assert (root / "script.gal").is_file()
    assert (root / "章节").is_dir()
    assert (root / "gallery_config.json").is_file()


# ---------- 7. moonlight 剧本可解析（@include 全展开） ----------

def test_moonlight剧本可解析(tmp_path):
    root = create_game("月光解析", str(tmp_path), template="moonlight")
    instrs = parse_file(root / "script.gal")
    assert len(instrs) > 0
    # @include 展开后应该包含角色定义
    ops = {i["op"] for i in instrs}
    assert "character" in ops
    assert "say" in ops


# ---------- 8. 重名不覆盖（moonlight 模板） ----------

def test_moonlight重名不覆盖(tmp_path):
    root = create_game("月光重名", str(tmp_path), template="moonlight")
    marker = root / "script.gal"
    marker.write_text("# 用户已修改\n", encoding="utf-8")
    with pytest.raises(ValueError, match="已存在"):
        create_game("月光重名", str(tmp_path), template="moonlight")
    assert marker.read_text(encoding="utf-8") == "# 用户已修改\n"
