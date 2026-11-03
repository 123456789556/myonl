"""P51 编辑器 UI 设计区：/api/ui-design 读/写 + /api/ui-design/preview 预览。

覆盖：
1. GET 读当前项目 ui + dialogue.default 几何段（未写键回落引擎默认）
2. POST 写回项目 config.json（白名单键，其余键保留）
3. POST preview 返回 PNG（不改磁盘配置）
"""

import json
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")  # 无头，须在 import pygame 前
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest  # noqa: E402

from engine import editor as E  # noqa: E402

pytestmark = [pytest.mark.integration]


def _make_project(tmp_path, ui=None, dlg=None) -> str:
    """造一个最小项目目录（config.json 可缺省），返回 root。"""
    root = str(tmp_path)
    cfg = {}
    if ui is not None:
        cfg["ui"] = ui
    if dlg is not None:
        cfg["dialogue"] = {"default": dlg}
    if cfg:
        cfg["_说明"] = "测试项目"
        with open(os.path.join(root, "config.json"), "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    return root


def test_ui_design_读项目配置回落引擎默认(tmp_path):
    """未写任何键 → 读回引擎默认（pixelated 开 / scale 4 / 圆角 10 / 无偏移）。"""
    root = _make_project(tmp_path)
    cfg = E._load_project_config(root)
    assert cfg == {}
    # 引擎默认（与 engine.config DEFAULTS 一致）
    from engine.config import DEFAULTS
    assert DEFAULTS["ui"]["pixelated"] is True
    assert DEFAULTS["ui"]["pixel_scale"] == 4
    assert DEFAULTS["ui"]["corner_radius"] == 10
    assert DEFAULTS["dialogue"]["default"]["radius"] == 10
    assert DEFAULTS["dialogue"]["default"]["offset_x"] == 0
    assert DEFAULTS["dialogue"]["default"]["offset_y"] == 0
    assert DEFAULTS["dialogue"]["default"]["panel_width"] == 0
    assert DEFAULTS["dialogue"]["default"]["height"] == 180


def test_ui_design_白名单键写回保留其余(tmp_path):
    """POST 只改白名单键，项目 config.json 其他键（_说明/ui.quickbar 等）原样保留。"""
    root = _make_project(tmp_path, ui={"quickbar": {"enabled": True}},
                         dlg={"name_y": 14, "align": "left"})
    # 模拟 handler 的补丁逻辑
    ui_patch = {"pixelated": False, "pixel_scale": 8, "corner_radius": 20}
    dlg_patch = {"radius": 16, "offset_x": 50, "offset_y": -20,
                 "panel_width": 1000, "height": 200}
    cfg = E._load_project_config(root)
    cfg = dict(cfg)
    ui = dict(cfg.get("ui") or {})
    for k in E._EditorHandler._UI_DESIGN_UI_KEYS:
        if k in ui_patch:
            ui[k] = ui_patch[k]
    cfg["ui"] = ui
    dlg = dict((cfg.get("dialogue") or {}).get("default") or {})
    for k in E._EditorHandler._UI_DESIGN_DLG_KEYS:
        if k in dlg_patch:
            dlg[k] = dlg_patch[k]
    cfg.setdefault("dialogue", {})["default"] = dlg
    E._write_project_config(root, cfg)

    back = E._load_project_config(root)
    assert back["ui"]["pixelated"] is False
    assert back["ui"]["pixel_scale"] == 8
    assert back["ui"]["corner_radius"] == 20
    assert back["ui"]["quickbar"]["enabled"] is True       # 未涉及键保留
    assert back["dialogue"]["default"]["radius"] == 16
    assert back["dialogue"]["default"]["offset_x"] == 50
    assert back["dialogue"]["default"]["offset_y"] == -20
    assert back["dialogue"]["default"]["panel_width"] == 1000
    assert back["dialogue"]["default"]["height"] == 200
    assert back["dialogue"]["default"]["name_y"] == 14      # 未涉及键保留
    assert back["dialogue"]["default"]["align"] == "left"
    assert back["_说明"] == "测试项目"


def test_ui_design_预览支持字号行距补丁(tmp_path):
    """B2：字号 / 行距补丁参与预览渲染，且不改磁盘配置。"""
    root = _make_project(tmp_path, dlg={"radius": 10})
    before = E._load_project_config(root)
    png = E._ui_design_png(root, {"pixelated": True, "pixel_scale": 4},
                           {"radius": 10}, {"body": 40}, {"body": 2.0})
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(png) > 1000
    assert E._load_project_config(root) == before


def test_ui_design_预览配色补丁不改磁盘(tmp_path):
    """2026-11-02 配色：theme 补丁参与预览（设置页场景），且不写磁盘。"""
    root = _make_project(tmp_path, ui={"quickbar": {"enabled": True}})
    before = E._load_project_config(root)
    png = E._ui_design_png(root, {}, {}, scene="settings",
                           theme_patch={"primary": [255, 0, 0], "surface": [10, 10, 10]})
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(png) > 1000
    assert E._load_project_config(root) == before


def test_ui_design_预览返回png不改磁盘(tmp_path):
    """POST preview 用给定几何渲染 PNG；磁盘 config.json 保持原样。"""
    root = _make_project(tmp_path, ui={"pixelated": True, "pixel_scale": 4},
                         dlg={"radius": 10})
    before = E._load_project_config(root)
    png = E._ui_design_png(root, {"pixelated": True, "pixel_scale": 4},
                           {"radius": 10, "offset_x": 0, "offset_y": 0,
                            "panel_width": 0, "height": 180})
    assert png[:8] == b"\x89PNG\r\n\x1a\n"   # PNG 魔数
    assert len(png) > 1000
    after = E._load_project_config(root)
    assert after == before                    # 预览不改配置


# ============ P52：游戏内 UI 设计器扩为六组（对话框/名字框/选项/快捷栏/菜单/设置页） ============


def test_ui_design_p52_白名单扩为六组():
    """P52：_UI_DESIGN_GROUPS 含 ui/dialogue/choices/quickbar/menu/settings/font/lh 八段。"""
    groups = E._EditorHandler._UI_DESIGN_GROUPS
    names = [g[2] for g in groups]
    assert names == ["ui", "dialogue", "choices", "quickbar", "menu",
                     "settings", "font", "line_height"]
    # 名字框键并入 dialogue 组
    dlg = E._EditorHandler._UI_DESIGN_DLG_KEYS
    assert "name_y" in dlg and "name_gap" in dlg
    # 各新组键齐
    assert set(E._EditorHandler._UI_DESIGN_CHOICES_KEYS) == {
        "width", "row_height", "dialog_gap", "radius"}
    assert set(E._EditorHandler._UI_DESIGN_QUICKBAR_KEYS) == {
        "button_width", "button_height", "gap", "margin_x", "margin_y",
        "alpha", "radius", "position", "align", "icons"}
    assert set(E._EditorHandler._UI_DESIGN_MENU_KEYS) == {
        "row_width", "row_height", "top", "radius"}
    assert set(E._EditorHandler._UI_DESIGN_SETTINGS_KEYS) == {
        "row_width", "row_height", "nav_width", "top"}


def test_ui_design_p52_嵌套组写回保留其余(tmp_path):
    """P52：POST 写 ui.choices/quickbar/menu/settings 嵌套组，白名单外键与顶层键保留。"""
    root = _make_project(
        tmp_path,
        ui={"quickbar": {"enabled": True, "position": "bottom"},
            "choices": {"width": 600, "extra": "keep-me"}},
        dlg={"name_y": 14, "align": "left"})
    # 模拟 handler 的补丁逻辑（与 _ui_design_set 相同的白名单合并）
    data = {"ui": {"pixelated": False},
            "dialogue": {"name_y": 20, "name_gap": 12},
            "choices": {"width": 500, "row_height": 60, "dialog_gap": 50, "radius": 12},
            "quickbar": {"button_width": 80, "button_height": 30, "gap": 10,
                         "margin_x": 40, "margin_y": 20, "alpha": 200,
                         "radius": 20, "position": "above_dialog", "align": "center"},
            "menu": {"row_width": 420, "row_height": 60, "top": 200, "radius": 16},
            "settings": {"row_width": 700, "row_height": 80, "nav_width": 200, "top": 180}}
    cfg = E._load_project_config(root)
    cfg = dict(cfg)
    ui_patch = data.get("ui") or {}
    ui = dict(cfg.get("ui") or {})
    for k in E._EditorHandler._UI_DESIGN_UI_KEYS:
        if k in ui_patch:
            ui[k] = ui_patch[k]
    cfg["ui"] = ui
    dlg_patch = data.get("dialogue") or {}
    dlg = dict((cfg.get("dialogue") or {}).get("default") or {})
    for k in E._EditorHandler._UI_DESIGN_DLG_KEYS:
        if k in dlg_patch:
            dlg[k] = dlg_patch[k]
    cfg.setdefault("dialogue", {})["default"] = dlg
    ui = dict(cfg.get("ui") or {})
    for _top, keys, name in E._EditorHandler._UI_DESIGN_GROUPS:
        if name in ("ui", "dialogue", "font", "line_height"):
            continue
        patch = data.get(name)
        if not isinstance(patch, dict):
            continue
        sec = dict(ui.get(name) or {})
        for k in keys:
            if k in patch:
                sec[k] = patch[k]
        ui[name] = sec
    cfg["ui"] = ui
    E._write_project_config(root, cfg)

    back = E._load_project_config(root)
    assert back["ui"]["pixelated"] is False
    assert back["ui"]["quickbar"]["enabled"] is True        # 未涉及键保留
    assert back["ui"]["quickbar"]["position"] == "above_dialog"
    assert back["ui"]["quickbar"]["button_width"] == 80
    assert back["ui"]["choices"]["width"] == 500
    assert back["ui"]["choices"]["extra"] == "keep-me"      # 白名单外保留
    assert back["ui"]["menu"] == {"row_width": 420, "row_height": 60,
                                  "top": 200, "radius": 16}
    assert back["ui"]["settings"] == {"row_width": 700, "row_height": 80,
                                      "nav_width": 200, "top": 180}
    assert back["dialogue"]["default"]["name_y"] == 20
    assert back["dialogue"]["default"]["name_gap"] == 12
    assert back["dialogue"]["default"]["align"] == "left"


def test_ui_design_p52_五场景预览均出png(tmp_path):
    """P52：dialog/choices/quickbar/menu/settings 五场景预览均返回有效 PNG。"""
    root = _make_project(tmp_path, dlg={"radius": 10})
    for scene in ("dialog", "choices", "quickbar", "menu", "settings"):
        png = E._ui_design_png(root, {}, {}, scene=scene)
        assert png[:8] == b"\x89PNG\r\n\x1a\n", f"{scene} 不是 PNG"
        assert len(png) > 1000, f"{scene} 太小"
    # 非法 scene 回落 dialog（不抛错）
    png = E._ui_design_png(root, {}, {}, scene="bogus")
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_ui_design_p52_嵌套组补丁参与预览不改磁盘(tmp_path):
    """P52：menu/settings/choices 几何补丁参与预览渲染；磁盘 config.json 不变。"""
    root = _make_project(tmp_path, ui={"menu": {"row_width": 380}})
    before = E._load_project_config(root)
    png = E._ui_design_png(root, {"pixelated": True, "pixel_scale": 4,
                                  "menu": {"row_width": 500, "row_height": 66,
                                           "top": 180, "radius": 18}},
                           {}, scene="menu")
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(png) > 1000
    assert E._load_project_config(root) == before


# ============ 第四步：界面开关（quickbar_enabled / pet_enabled）接入 UI 设计页 ============


def test_ui_design_界面开关读写(tmp_path):
    """界面开关读写项目 settings.json：缺省回落引擎默认，写入保留其余键。"""
    root = _make_project(tmp_path)
    settings_path = os.path.join(root, "settings.json")
    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump({"quickbar_enabled": 0, "title": "保留"}, f, ensure_ascii=False)

    # 未写的 pet_enabled 回落默认 0；已写的 quickbar_enabled 读回原值
    assert E._interface_settings(root) == {"quickbar_enabled": 0, "pet_enabled": 0}
    # 兼容 "1" / True 两种写法
    assert E._save_interface_settings(root, {"quickbar_enabled": "1",
                                             "pet_enabled": True}) == settings_path
    with open(settings_path, encoding="utf-8") as f:
        back = json.load(f)
    assert back["quickbar_enabled"] == 1
    assert back["pet_enabled"] == 1
    assert back["title"] == "保留"                    # 作者键原样保留
    assert E._interface_settings(root) == {"quickbar_enabled": 1, "pet_enabled": 1}
    # 脏值按开关语义归一：空串/off → 0
    assert E._as_switch("") == 0
    assert E._as_switch("off") == 0
    assert E._as_switch("on") == 1


def test_ui_design_界面开关参与预览不改磁盘(tmp_path):
    """界面开关补丁参与快捷栏预览；不写项目 settings.json。"""
    root = _make_project(tmp_path)
    settings_path = os.path.join(root, "settings.json")
    png = E._ui_design_png(root, {}, {}, scene="quickbar",
                           interface_patch={"quickbar_enabled": 0})
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(png) > 1000
    assert not os.path.exists(settings_path)          # 预览不落盘


def test_ui_design_界面开关前端接线():
    """前端有「界面开关」分页（控件由 JS 注入），且预览/保存 payload 带 interface。"""
    root = os.path.dirname(os.path.dirname(os.path.abspath(E.__file__)))
    html = open(os.path.join(root, "editor", "index.html"), encoding="utf-8").read()
    js = open(os.path.join(root, "editor", "editor_uidesign.js"), encoding="utf-8").read()
    assert 'id="uidPanelIface"' in html
    assert "uidBuildExtraPanels" in js
    for token in ('id="uidIfIfaceQb"', 'id="uidIfIfacePet"', "out.interface",
                  "uidIfIfaceQb", "uidIfIfacePet"):
        assert token in js, f"editor_uidesign.js 缺 {token}"
