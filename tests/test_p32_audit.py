"""tests/test_p32_audit.py：P32 全面 bug 审计后的回归用例。

覆盖本次修复：
1. 带 BOM（记事本 UTF-8）的 .gal / settings.json / gallery_config.json 可正常读取
2. 存档目录跟随资源根（assets_root/saves），不再固定当前工作目录，跨游戏不互相污染
3. demo.run 退出后复位默认存档目录（同进程多次运行互不影响）
4. settings.json 原子写：无残留 .tmp，未知键保留，无 BOM
5. 资源预检覆盖 @cg / @fg / @voice / 分层立绘
"""

import json
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")  # 无头模式，须在 import pygame 前生效
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest  # noqa: E402

from engine import data  # noqa: E402
from engine import demo  # noqa: E402
from engine import save as save_api  # noqa: E402
from engine.parser import parse_file  # noqa: E402
from engine.runtime import Runtime  # noqa: E402

pytestmark = [pytest.mark.integration]


@pytest.fixture(autouse=True)
def _reset_saves_dir():
    """每个用例前后都确保存档目录是默认值，避免用例间串味。"""
    save_api.reset_saves_dir()
    yield
    save_api.reset_saves_dir()


# ---------------- 1. BOM 兼容 ----------------

def test_带BOM的剧本可解析(tmp_path):
    p = tmp_path / "bom.gal"
    p.write_bytes("\ufeff@bg 夜景\n@ 你好\n".encode("utf-8"))
    ins = parse_file(str(p))
    assert [i["op"] for i in ins if i["op"] != "label"] == ["bg", "say"]


def test_带BOM的settings可读取且写回无BOM(tmp_path):
    p = tmp_path / "settings.json"
    p.write_bytes(("\ufeff" + json.dumps({"title": "月光漫步", "splash": True},
                                        ensure_ascii=False)).encode("utf-8"))
    s = data.load_settings(str(p))
    assert s["title"] == "月光漫步" and bool(s["splash"]) is True

    data.save_settings(s, str(p))
    raw = p.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert json.loads(raw.decode("utf-8"))["title"] == "月光漫步"


def test_带BOM的gallery_config可读取(tmp_path):
    p = tmp_path / "gallery_config.json"
    p.write_bytes(("\ufeff" + json.dumps({"cg_dark": ["a"]}, ensure_ascii=False)).encode("utf-8"))
    cfg = data.load_gallery_config(str(tmp_path))
    assert cfg == [{"name": "cg_dark", "images": ["a"], "require": []}]


# ---------------- 2/3. 存档目录归属 ----------------

def test_存档目录跟随资源根而不是cwd(tmp_path, monkeypatch):
    game = tmp_path / "game"
    game.mkdir()
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    script = game / "s.gal"
    script.write_text("@ 第一句\n", encoding="utf-8")

    save_api.set_saves_dir(game / "saves")
    rt = Runtime()
    rt.load(str(script))
    rt.save(1)

    assert (game / "saves" / "slot_1.json").is_file()
    assert not (cwd / "saves" / "slot_1.json").exists()
    # UI 读的是同一个目录
    assert [str(e["slot"]) for e in save_api.list_slots()] == ["1"]


def test_demo_run结束后复位默认存档目录(tmp_path, monkeypatch):
    game = tmp_path / "game"
    game.mkdir()
    (game / "settings.json").write_text(json.dumps({"title": "T", "splash": False},
                                                   ensure_ascii=False), encoding="utf-8")
    (game / "script.gal").write_text("@ 第一句\n@end\n", encoding="utf-8")
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)

    demo.run(str(game / "script.gal"), assets_root=str(game), max_frames=30, auto=True)

    assert str(save_api.SAVES_DIR) == "saves"  # finally 复位
    assert not (cwd / "saves").exists()        # 没往 cwd 写存档目录


# ---------------- 4. settings 原子写 ----------------
def test_存档卡片缩略图落在资源根的saves(tmp_path, monkeypatch):
    """@save 后补写的缩略图/卡片必须落在 assets_root/saves，且 JSON 只记文件名。"""
    from engine.renderer import Renderer

    game = tmp_path / "game"
    (game / "images").mkdir(parents=True)
    (game / "audio").mkdir()
    script = game / "s.gal"
    script.write_text("@ 第一句台词\n@end\n", encoding="utf-8")
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)

    save_api.set_saves_dir(game / "saves")
    rt = Runtime()
    rt.load(str(script))
    rt.step()
    rt.save(1)
    ren = Renderer((1280, 720), str(game))
    try:
        demo._post_save_enrich(1, rt, ren, str(script))
    finally:
        ren.close()

    saved = json.loads((game / "saves" / "slot_1.json").read_text(encoding="utf-8"))
    assert saved["thumbnail_path"] == "thumb_1.png"
    assert (game / "saves" / "thumb_1.png").is_file()
    assert not (cwd / "saves").exists()


def test_settings原子写无残留临时文件(tmp_path):
    p = tmp_path / "settings.json"
    data.save_settings({"title": "测试作品", "my_custom": 42}, str(p))
    assert not (tmp_path / "settings.json.tmp").exists()
    saved = json.loads(p.read_text(encoding="utf-8"))
    assert saved["title"] == "测试作品"
    assert saved["my_custom"] == 42  # 未知键保留（P31-c 回归）


# ---------------- 5. 资源预检覆盖面 ----------------

def test_预检覆盖cg_fg_voice与分层立绘(tmp_path, capsys):
    game = tmp_path / "game"
    (game / "images").mkdir(parents=True)
    (game / "audio").mkdir()
    script = game / "s.gal"
    script.write_text(
        "@cg 不存在的CG\n"
        "@fg 不存在的前景\n"
        "@show 双叶 身体:默认 表情:微笑\n"
        "@ 台词\n"
        "@voice 不存在的配音\n",
        encoding="utf-8",
    )
    demo._precheck_resources(str(script), str(game))
    err = capsys.readouterr().err
    assert "@cg" in err and "@fg" in err and "@voice" in err
    assert "身体:默认" in err and "表情:微笑" in err
