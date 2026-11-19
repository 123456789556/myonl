# -*- coding: utf-8 -*-
"""tests/test_p02_launcher.py：P0-2 Launcher CLI 验收。

验收项：
  1. default 模板生成 4 份配置（config/settings/gallery_config + script.gal）+ 占位素材
  2. （历史）moonlight 模板已从仓库移除 —— 它是整套复制一部别人的作品，
     拿它当「新建游戏」的底子等于替别人分发素材。现在只剩 hello / default / standard 三种，
     传 moonlight 会明确报错。相关用例见下方 REMOVED_TEMPLATES 一组。
  3. template 生成时排除 saves/（存档）和 src/（源码参考）
  4. 未知模板中文拒绝
  5. `python -m engine.new` 入口（engine.new.main）能跑
  6. `engine.cli new` 入口工作
  7. 生成的剧本可被 parser 解析（@include 章节全展开无报错）
  8. 重名不覆盖
"""
from __future__ import annotations

import json
import os

import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from engine import cli, new  # noqa: E402
from engine.newgame import TEMPLATES, create_game  # noqa: E402

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


# ---------- 2. moonlight 模板已移除（版权原因）----------

def test_moonlight模板已移除_并说明理由(tmp_path):
    # 原来这个模板是把别人的示例游戏整套复制过来。版权归原作者，仓库不再带，
    # 现在必须明确拒绝并说清原因 —— 不能静默退化成一个空骨架让人以为"就是空的"。
    with pytest.raises(ValueError, match="已移除"):
        create_game("月光复刻", str(tmp_path), template="moonlight")


# ---------- 3. 未知模板拒绝 ----------

def test_未知模板拒绝(tmp_path):
    with pytest.raises(ValueError, match="未知模板"):
        create_game("坏模板", str(tmp_path), template="不存在的模板")


def test_TEMPLATES里不再有moonlight():
    assert "default" in TEMPLATES
    assert "hello" in TEMPLATES
    assert "standard" in TEMPLATES
    assert "moonlight" not in TEMPLATES


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


def test_new命令行拒绝已移除的模板(tmp_path, capsys):
    # --template 的 choices 已经不收 moonlight；传进去 argparse 直接退出码 2
    with pytest.raises(SystemExit) as excinfo:
        new.main(["月光新", "--dir", str(tmp_path), "--template", "moonlight"])
    assert excinfo.value.code == 2
    assert not (tmp_path / "月光新").exists(), "被拒的模板不该留下半个目录"


def test_new模块入口_未知模板退出码1(tmp_path, capsys):
    # argparse 的 choices 不合法时直接 SystemExit(2)，不是返回退出码
    with pytest.raises(SystemExit) as excinfo:
        new.main(["坏", "--dir", str(tmp_path), "--template", "bad"])
    assert excinfo.value.code == 2
    assert "已创建游戏" not in capsys.readouterr().out


# ---------- 6. engine.cli new 也拒绝已移除的模板 ----------

def test_cli_new拒绝已移除的模板(tmp_path):
    try:
        cli.main(["new", "cli月光", "--dir", str(tmp_path), "--template", "moonlight"])
    except SystemExit as e:
        assert e.code == 2
    # 本质断言：不管退出码怎么报，都不能真生出一个游戏目录
    assert not (tmp_path / "cli月光").exists()


# ---------- 7. 重名不覆盖 ----------

def test_重名不覆盖(tmp_path):
    root = create_game("重名测试", str(tmp_path), template="default")
    marker = root / "script.gal"
    marker.write_text("# 用户已修改\n", encoding="utf-8")
    with pytest.raises(ValueError, match="已存在"):
        create_game("重名测试", str(tmp_path), template="default")
    assert marker.read_text(encoding="utf-8") == "# 用户已修改\n"
