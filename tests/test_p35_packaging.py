"""P35 打包发布与现代化默认 UI 的自动化测试。"""
import base64
import json
import os
import struct
import sys
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")  # 无头模式，须在 import pygame 前生效

from engine import newgame, packaging
from engine.config import Config
from engine.editor import EditorApp

pytestmark = [pytest.mark.integration, pytest.mark.slow]

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def _write_project(root: Path, name: str = "测试游戏", *, icon: bool = True,
                   publisher=None, version="1.0.0") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "script.gal").write_text("@bg bg_room\n@ 主角 你好。\n@end\n", encoding="utf-8")
    if icon:
        (root / "icon.png").write_bytes(PNG_1X1)
    packaging.save_profile(root, {
        "game_name": name,
        "version": version,
        "icon": "icon.png" if icon else "",
        "publisher": publisher if publisher is not None else {
            "name": "Moyul Studio", "account_id": "MOYUL-001",
            "channel": "本地发行", "contact": "",
        },
        "description": "测试项目",
        "release_notes": "首个版本",
    })
    return root


def _fake_builder(calls):
    def build(project, *, name, icon, version, publisher, description, release_notes):
        calls.append({"name": name, "icon": icon, "version": version})
        out = Path(project).parent.parent / "dist" / name
        out.mkdir(parents=True, exist_ok=True)
        (out / f"{name}.exe").write_bytes(b"fake exe")
        return out
    return build


def test_default_template_has_modern_ui_and_pack_profile(tmp_path):
    root = newgame.create_game("标准模板", tmp_path)
    cfg = json.loads((root / "config.json").read_text(encoding="utf-8"))
    assert cfg["window_title"] == "标准模板"
    assert cfg["theme"]["primary"] == [130, 140, 160]  # P44：标准模板默认黑主题
    assert cfg["ui"]["title"]["align"] == "left"       # P44：标题左列布局
    assert cfg["ui"]["title"]["items"] == ["开始新游戏", "继续", "读档", "设置", "退出"]  # P44：5 项主菜单
    assert cfg["ui"]["quickbar"]["position"] == "bottom"
    assert cfg["ui"]["choices"]["width"] >= 560
    assert cfg["font"]["title"] >= 72
    profile = json.loads((root / "pack_config.json").read_text(encoding="utf-8"))
    assert profile["game_name"] == "标准模板"
    assert profile["publisher"]["account_id"]
    assert (root / profile["icon"]).is_file()

    conf = Config(cfg)
    assert conf.theme_color("primary") == (130, 140, 160)
    assert conf.ui_section("quickbar")["position"] == "bottom"
    assert conf.ui_value("choices", "width") == 620


def test_profile_validation_lists_all_chinese_errors(tmp_path):
    errors = packaging.validate_profile({}, tmp_path)
    joined = "；".join(errors)
    assert "游戏名为空" in joined
    assert "版本号为空" in joined
    assert "运营号" in joined
    assert "游戏图标为空" in joined

    bad = packaging.validate_profile(
        {"game_name": "坏:名字", "version": "1.0", "icon": "nope.png",
         "publisher": {"name": "", "account_id": ""}}, tmp_path)
    joined = "；".join(bad)
    assert "不能包含" in joined
    assert "版本号格式不正确" in joined
    assert "图标不存在" in joined
    assert "运营号名称为空" in joined


def test_version_bump_semver():
    assert packaging.bump_version("1.0.0", "patch") == "1.0.1"
    assert packaging.bump_version("1.0.3", "minor") == "1.1.0"
    assert packaging.bump_version("1.4.9", "major") == "2.0.0"
    with pytest.raises(packaging.PackProfileError):
        packaging.bump_version("1.0", "patch")
    with pytest.raises(packaging.PackProfileError):
        packaging.bump_version("1.0.0", "bad")


def test_png_to_ico_wrapper(tmp_path):
    png = tmp_path / "a.png"
    png.write_bytes(PNG_1X1)
    ico = packaging.png_to_ico(png, tmp_path / "a.ico")
    data = ico.read_bytes()
    assert struct.unpack("<HHH", data[:6]) == (0, 1, 1)
    assert data[22:] == PNG_1X1

    too_big = tmp_path / "big.png"
    too_big.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\r" + b"IHDR" +
                        struct.pack(">II", 512, 512))
    with pytest.raises(packaging.PackProfileError):
        packaging.png_to_ico(too_big, tmp_path / "big.ico")


def test_pack_project_and_version_iteration(tmp_path):
    root = tmp_path
    project = _write_project(root / "games" / "测试游戏", "测试游戏")
    calls = []
    history = root / "build" / "pack_history.json"

    first = packaging.pack_project(project, version="1.0.0", build_func=_fake_builder(calls),
                                   root=root, history_path=history, verbose=False)
    assert first["version"] == "1.0.0"
    assert first["build_number"] == 1
    assert first["publisher"]["account_id"] == "MOYUL-001"
    info = json.loads(Path(first["info_path"]).read_text(encoding="utf-8"))
    assert info["version"] == "1.0.0"
    assert info["publisher"]["name"] == "Moyul Studio"
    assert Path(first["icon"]).suffix == ".ico"

    # 模拟开发者改剧本后重新打包：内容修改不影响版本历史，patch 递增
    (project / "script.gal").write_text("@ 主角 修改后的内容。\n@end\n", encoding="utf-8")
    second = packaging.pack_project(project, bump="patch", build_func=_fake_builder(calls),
                                    root=root, history_path=history, verbose=False)
    assert second["version"] == "1.0.1"
    assert second["build_number"] == 2
    assert calls[-1]["version"] == "1.0.1"

    rows = packaging.list_projects(root / "games", root=root, history_path=history)
    assert rows[0]["packaged"] is True
    assert rows[0]["build_count"] == 2
    assert rows[0]["version"] == "1.0.1"
    assert rows[0]["folder"] == "测试游戏"
    assert packaging.next_version(project, "minor", root, history) == "1.1.0"


def test_pack_project_blocks_on_missing_required_fields(tmp_path):
    project = _write_project(tmp_path / "games" / "缺少配置", "缺少配置",
                             icon=False, publisher={})
    calls = []
    with pytest.raises(packaging.PackProfileError) as err:
        packaging.pack_project(project, version="1.0.0",
                               build_func=_fake_builder(calls),
                               root=tmp_path, verbose=False)
    message = str(err.value)
    assert "运营号名称为空" in message
    assert "游戏图标为空" in message
    assert calls == []


def test_quickbar_defaults_to_screen_bottom(tmp_path):
    root = newgame.create_game("布局测试", tmp_path)
    from engine.renderer import Renderer

    ren = Renderer((1280, 720), str(root))
    lay = ren._quickbar_layout(6)
    assert lay["enabled"] is True
    assert lay["y0"] == 720 - lay["bh"] - 10
    assert lay["x0"] + 6 * lay["bw"] + 5 * lay["gap"] <= 1280
    assert ren._dialog_bottom_reserve() == lay["bh"] + 10 + 4


def test_editor_pack_api_lists_projects_and_blocks_incomplete_build(tmp_path):
    games = tmp_path / "games"
    project = _write_project(games / "接口测试", "接口测试", icon=False, publisher={})
    app = EditorApp(str(project))
    server = ThreadingHTTPServer(("127.0.0.1", 0), app.make_handler())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with urllib.request.urlopen(base + "/api/pack/projects", timeout=5) as r:
            data = json.loads(r.read().decode("utf-8"))
        assert data["ok"] is True
        assert data["projects"][0]["folder"] == "接口测试"

        req = urllib.request.Request(
            base + "/api/pack/build", method="POST",
            data=json.dumps({"project": "接口测试", "bump": "patch"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            urllib.request.urlopen(req, timeout=5)
            raise AssertionError("缺少必填项时不应启动打包")
        except urllib.error.HTTPError as e:
            body = json.loads(e.read().decode("utf-8"))
            assert e.code == 400
            assert body["ok"] is False
            assert any("运营号" in x for x in body["errors"])
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_editor_pack_api_version_preview(tmp_path):
    games = tmp_path / "games"
    project = _write_project(games / "版本预览", "版本预览")
    app = EditorApp(str(project))
    server = ThreadingHTTPServer(("127.0.0.1", 0), app.make_handler())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with urllib.request.urlopen(
                base + "/api/pack/version?project=%E7%89%88%E6%9C%AC%E9%A2%84%E8%A7%88&bump=minor",
                timeout=5) as r:
            data = json.loads(r.read().decode("utf-8"))
        assert data["ok"] is True
        assert data["version"] == "1.1.0"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_p44d_打包资源裁剪_只保留被引用素材(tmp_path):
    """P44-D：产物里的未引用图片/音频被删；硬编码 title_bg/cg_locked 保留。"""
    import pack

    out = tmp_path / "dist_game"
    (out / "images").mkdir(parents=True)
    (out / "audio").mkdir(parents=True)
    (out / "script.gal").write_text(
        "@bg bg_教室群像\n@music bgm_白天\n@ 旁白。\n@end\n", encoding="utf-8")
    # 被引用 / 未引用；前缀包含不应误判为引用
    (out / "images" / "bg_教室群像.jpg").write_bytes(b"x")
    (out / "images" / "bg_教室.png").write_bytes(b"unused")
    (out / "images" / "title_bg.png").write_bytes(b"keep")
    (out / "images" / "cg_locked.png").write_bytes(b"keep")
    (out / "audio" / "bgm_白天.wav").write_bytes(b"x")
    (out / "audio" / "bgm_night.wav").write_bytes(b"unused")

    pack._prune_unused_assets(out)

    assert (out / "images" / "bg_教室群像.jpg").is_file()
    assert (out / "images" / "title_bg.png").is_file()
    assert (out / "images" / "cg_locked.png").is_file()
    assert (out / "audio" / "bgm_白天.wav").is_file()
    assert not (out / "images" / "bg_教室.png").exists()
    assert not (out / "audio" / "bgm_night.wav").exists()
