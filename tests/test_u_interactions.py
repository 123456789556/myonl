# -*- coding: utf-8 -*-
"""U7/U9/U10/U12：玩家可调交互与章节演出。

U7 对话框透明度：设置页滑条 → render_dialog 乘 bg_alpha（1.0 = 完全跟随项目配置）
U9 减少动效：设置页开关 → 关震动、不闪烁
U10 确认键方案：both / space / enter
U12 @chapter：章节/幕间演出卡（黑场 + 标题），播放期间暂停推进
"""
import os
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame
import pytest

from engine import data, ui
from engine.parser import dump_text, parse_text
from engine.runtime import Runtime

pytestmark = [pytest.mark.unit]

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _setting(key):
    return next((it for it in ui.SETTINGS_ITEMS if it["key"] == key), None)


# ---------- 默认值与设置项登记 ----------

def test_新增设置键都有默认值():
    for key in ("dialog_alpha_scale", "reduce_effects", "confirm_key"):
        assert key in data.DEFAULT_SETTINGS, f"DEFAULT_SETTINGS 缺 {key}"


def test_设置项登记与分组():
    for key in ("dialog_alpha_scale", "reduce_effects", "confirm_key"):
        item = _setting(key)
        assert item is not None, f"设置页缺 {key}"
        assert item["group"] == "高级", f"{key} 应归高级组（不挤占基础页）"


def test_透明度滑条范围不改变默认观感():
    """默认 1.0 = 跟随项目 config，老工程视觉零变化。"""
    assert data.DEFAULT_SETTINGS["dialog_alpha_scale"] == 1.0
    item = _setting("dialog_alpha_scale")
    assert item["kind"] == "volume"
    assert item["min"] < 1.0 <= item["max"] + 1e-9


def test_减少动效默认关闭():
    assert data.DEFAULT_SETTINGS["reduce_effects"] == 0
    assert _setting("reduce_effects")["kind"] == "switch"


# ---------- U10 确认键三档 ----------

@pytest.fixture
def ren(tmp_path):
    from engine.renderer import Renderer

    r = Renderer((1280, 720), str(tmp_path))
    yield r
    r.close()


def _ok(ren, key):
    from engine.render_utils import is_confirm_key

    return is_confirm_key(ren.settings, key)


def test_确认键默认空格与回车都认(ren):
    assert _ok(ren, pygame.K_SPACE)
    assert _ok(ren, pygame.K_RETURN)
    assert _ok(ren, pygame.K_KP_ENTER)
    assert not _ok(ren, pygame.K_a)


def test_确认键仅空格(ren):
    ren.settings["confirm_key"] = "space"
    assert _ok(ren, pygame.K_SPACE)
    assert not _ok(ren, pygame.K_RETURN)


def test_确认键仅回车(ren):
    ren.settings["confirm_key"] = "enter"
    assert _ok(ren, pygame.K_RETURN)
    assert _ok(ren, pygame.K_KP_ENTER)
    assert not _ok(ren, pygame.K_SPACE)


def test_确认键非法值回落both(ren):
    ren.settings["confirm_key"] = "什么鬼"
    assert _ok(ren, pygame.K_SPACE)
    assert _ok(ren, pygame.K_RETURN)


# ---------- U9 减少动效 ----------

def test_减少动效设置生效(ren):
    ren.settings["reduce_effects"] = 0
    assert ren._reduce_effects() is False
    ren.settings["reduce_effects"] = 1
    assert ren._reduce_effects() is True


# ---------- U7 透明度 ----------

def test_透明度倍率写进对话框几何(ren, monkeypatch):
    """滑条 0.5 → 绘制用的 bg_alpha 减半；1.0 时原值不动。"""
    base = ren.config.dialogue("default")["bg_alpha"]
    captured = {}
    real = ren.config.dialogue

    def spy(kind="default"):
        d = real(kind)
        captured[kind] = d          # 存引用：_dialog_layout 会就地改 bg_alpha
        return d

    monkeypatch.setattr(ren.config, "dialogue", spy)
    history = [{"char": None, "text": "测试"}]

    ren.settings["dialog_alpha_scale"] = 1.0
    ren._dialog_layout(history, {}, False)
    assert captured["default"]["bg_alpha"] == base     # 默认不覆盖项目配置

    captured.clear()
    ren.settings["dialog_alpha_scale"] = 0.5
    ren._dialog_layout(history, {}, False)
    assert captured["default"]["bg_alpha"] == max(16, int(base * 0.5))


def test_透明度倍率非法值不崩(ren):
    ren.settings["dialog_alpha_scale"] = "abc"
    ren.render({"bg": None, "history": [], "sprites": []}, None)


def test_对话框位置设置与文本():
    item = _setting("dialog_offset_y")
    assert item is not None and item["kind"] == "offset"
    assert item["min"] == -80 and item["max"] == 80
    assert data.DEFAULT_SETTINGS["dialog_offset_y"] == 0
    assert ui.next_value("dialog_offset_y", 0) == 10

    from engine.render_utils import _format_setting

    assert _format_setting(0, "offset") == "默认"
    assert _format_setting(-30, "offset") == "上移 30"
    assert _format_setting(40, "offset") == "下移 40"


def test_位置偏移写进对话框几何(ren, monkeypatch):
    base = ren.config.dialogue("default")["offset_y"]
    captured = {}
    real = ren.config.dialogue

    def spy(kind="default"):
        d = real(kind)
        captured[kind] = d
        return d

    monkeypatch.setattr(ren.config, "dialogue", spy)
    ren.settings["dialog_offset_y"] = 40
    ren._dialog_layout([{"char": None, "text": "测试"}], {}, False)
    assert captured["default"]["offset_y"] == base + 40


# ---------- U12 @chapter ----------

def test_chapter解析与序列化():
    src = "@label a\n@chapter 第一章 雨夜\n@ 你好\n@chapter 幕间 secs=0.8\n@end\n"
    instrs = parse_text(src)
    chapters = [i for i in instrs if i["op"] == "chapter"]
    assert chapters[0]["title"] == "第一章 雨夜"
    assert chapters[0]["secs"] is None
    assert chapters[1]["title"] == "幕间"
    assert chapters[1]["secs"] == 0.8
    assert "@chapter 第一章 雨夜" in dump_text(instrs)
    assert "secs=0.8" in dump_text(instrs)


def test_chapter参数错误有中文提示():
    for bad in ("@chapter\n", "@chapter 标题 foo=1\n", "@chapter 标题 secs=abc\n",
                "@chapter 标题 secs=0\n", "@chapter secs=1\n"):
        with pytest.raises(Exception) as ei:
            parse_text(bad)
        assert "@chapter" in str(ei.value)


def test_chapter运行期发事件并暂停推进(tmp_path):
    p = tmp_path / "t.gal"
    p.write_text("@chapter 第一章\n@ 台词\n@end\n", encoding="utf-8")
    rt = Runtime()
    rt.load(str(p))
    ev = rt.step()
    assert ev["type"] == "chapter"
    assert ev["title"] == "第一章"
    assert ev["secs"] == 1.2
    assert rt.pending_wait_seconds() == pytest.approx(1.2)
    rt.advance_wait(5.0)
    assert rt.pending_wait_seconds() == 0.0


def test_chapter自定义时长(tmp_path):
    p = tmp_path / "t.gal"
    p.write_text("@chapter 幕间 secs=0.5\n@end\n", encoding="utf-8")
    rt = Runtime()
    rt.load(str(p))
    ev = rt.step()
    assert ev["secs"] == pytest.approx(0.5)
    assert rt.pending_wait_seconds() == pytest.approx(0.5)


def test_chapter卡绘制会自己结束(ren):
    ren.play_chapter("第一章", 0.05)
    assert ren._chapter is not None
    assert ren._draw_chapter() is True
    ren._chapter["t0"] -= 5000  # 快进 5 秒
    assert ren._draw_chapter() is False
    assert ren._chapter is None


# ---------- V1 素材库「角色」分类 ----------

def test_素材库有角色分类():
    """角色分类页与图片/音频并列：可搜索、可拖拽生成指令、可点开角色库。"""
    html = open(os.path.join(ROOT, "editor", "index.html"), encoding="utf-8").read()
    js = open(os.path.join(ROOT, "editor", "editor_main.js"), encoding="utf-8").read()
    css = open(os.path.join(ROOT, "editor", "editor.css"), encoding="utf-8").read()
    assert 'data-cat="characters"' in html, "index.html 缺角色分类页签"
    for token in ("renderCharacterAssets", "characterAvatar", "ensureCharacters",
                  'category: "characters"', 'category === "characters"',
                  "__openCharacterManager"):
        assert token in js, f"editor_main.js 缺 {token}"
    assert ".asset-card" in css


# ---------- U10 完整键位自定义 ----------

def test_键位设置项齐全():
    keys = [i["key"] for i in ui.SETTINGS_ITEMS if i["kind"] == "key"]
    assert keys == ["key_up", "key_down", "key_left", "key_right", "key_confirm", "key_back"]
    for k in keys:
        assert k in data.DEFAULT_SETTINGS, f"DEFAULT_SETTINGS 缺 {k}"
        assert data.DEFAULT_SETTINGS[k] == "", f"{k} 默认应为空（沿用项目配置）"


def test_键位覆盖重建键位表():
    from engine import config as cfgapi

    cfg = cfgapi.Config()
    base = cfgapi.keymap(cfg)
    assert pygame.K_RETURN in base and base[pygame.K_RETURN] == "confirm"
    custom = cfgapi.keymap(cfg, {"key_confirm": "f", "key_up": "w"})
    assert custom.get(pygame.K_f) == "confirm"
    assert pygame.K_RETURN not in custom      # 覆盖后旧键失效
    assert custom.get(pygame.K_w) == "up"


def test_确认键方案与自定义键不打架():
    """confirm_key 只过滤默认键；自定义 key_confirm 优先且旧确认键失效。"""
    from engine import config as cfgapi

    cfg = cfgapi.Config()
    space_only = cfgapi.keymap(cfg, {"confirm_key": "space"})
    assert space_only.get(pygame.K_SPACE) == "confirm"
    assert pygame.K_RETURN not in space_only

    custom = cfgapi.keymap(cfg, {"confirm_key": "space", "key_confirm": "f"})
    assert custom.get(pygame.K_f) == "confirm"
    assert pygame.K_SPACE not in custom


def test_非法键名忽略并保留默认():
    import warnings

    from engine import config as cfgapi

    cfg = cfgapi.Config()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")   # 无头环境下 key_code 会提示未 init，与本断言无关
        custom = cfgapi.keymap(cfg, {"key_confirm": "不存在的键"})
    assert custom.get(pygame.K_RETURN) == "confirm"


def test_设置页键位项进入捕获():
    u = ui.UI()
    u.mode = "settings"
    u._settings = dict(data.DEFAULT_SETTINGS)
    visible = u._visible_settings()
    groups = []
    for it in visible:
        g = it.get("group", "基础")
        if g not in groups:
            groups.append(g)
    u._settings_tab = groups.index("键位")
    u._cursor = next(i for i, it in enumerate(visible) if it["key"] == "key_confirm")
    assert u._handle_settings("confirm") == {"action": "settings_capture",
                                             "key": "key_confirm"}
    assert ui.next_value("key_confirm", "f") == "f"   # 键位项不会被 next_value 循环改写


def test_改键捕获下一键写回(ren):
    ren.begin_key_capture("key_confirm")
    act = ren._capture_key_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_f))
    assert act == {"action": "settings_set_key", "key": "key_confirm", "code": "f"}
    assert ren._key_capture is None


def test_改键按Esc恢复默认(ren):
    ren.begin_key_capture("key_confirm")
    act = ren._capture_key_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
    assert act["code"] == ""


def test_非捕获态不拦截按键(ren):
    assert ren._capture_key_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_f)) is None


# ---------- V4 角色库：引用计数 / 语音 / 分层立绘 ----------

def test_角色引用计数跨文件(tmp_path):
    from engine import characters

    (tmp_path / "a.gal").write_text(
        "@character 林晚 #ffffff\n@show 林晚 微笑\n@ 林晚 你好\n@ 旁白一句\n",
        encoding="utf-8")
    sub = tmp_path / "章节"
    sub.mkdir()
    (sub / "b.gal").write_text("@ 林晚 又见面了\n@hide 林晚\n", encoding="utf-8")

    usage = characters.usage_in_project(str(tmp_path), ["林晚"])
    assert usage["林晚"]["lines"] == 5      # character/show/台词/hide/台词
    assert usage["林晚"]["files"] == 2
    assert "旁白一句" not in usage          # 旁白不按角色计


def test_角色库保留语音与分层字段():
    from engine import characters

    data = characters.normalize({"characters": [
        {"id": "林晚", "voice": "林晚_", "layers": {"身体": "林晚_身体", "表情": "林晚_微笑"}},
    ]})
    c = data["characters"][0]
    assert c["voice"] == "林晚_"
    assert c["layers"] == {"身体": "林晚_身体", "表情": "林晚_微笑"}


def test_角色引用路由与前端入口():
    py = open(os.path.join(ROOT, "engine", "editor.py"), encoding="utf-8").read()
    assert '"/api/characters/usage"' in py and "_characters_usage" in py
    js = open(os.path.join(ROOT, "editor", "editor_characters.js"), encoding="utf-8").read()
    for token in ("charVoice", "charAddLayer", "layerRow", "loadUsage",
                  "/api/characters/usage", "处引用"):
        assert token in js, f"editor_characters.js 缺 {token}"
    css = open(os.path.join(ROOT, "editor", "editor.css"), encoding="utf-8").read()
    assert ".char-layer-row" in css


# ---------- UI 设计区：预览放大 + 参数行间距 ----------

def test_ui设计区预览放大与间距():
    html = open(os.path.join(ROOT, "editor", "index.html"), encoding="utf-8").read()
    js = open(os.path.join(ROOT, "editor", "editor_uidesign.js"), encoding="utf-8").read()
    css = open(os.path.join(ROOT, "editor", "editor.css"), encoding="utf-8").read()
    for token in ('id="uidZoom"', 'id="uidZoomMask"', 'id="uidZoomImg"'):
        assert token in html, f"index.html 缺 {token}"
    for token in ("openZoom", "closeZoom", "lastPreviewUrl", "uidZoomMask"):
        assert token in js, f"editor_uidesign.js 缺 {token}"
    # 参数行统一间距 + 预览棋盘底 + 放大遮罩样式
    for token in (".ui-dl.row + .ui-dl.row", ".uid-zoom-mask",
                  ".ui-design-preview { flex: 1; min-width: 0; position: sticky"):
        assert token in css, f"editor.css 缺 {token}"


# ---------- E4 入门任务进度（可折叠、自动勾选、不弹窗） ----------

def test_入门任务面板结构():
    html = open(os.path.join(ROOT, "editor", "index.html"), encoding="utf-8").read()
    js = open(os.path.join(ROOT, "editor", "editor_shell.js"), encoding="utf-8").read()
    css = open(os.path.join(ROOT, "editor", "editor.css"), encoding="utf-8").read()
    for token in ("fpTaskHead", "fpTaskChev", "fpTaskCount", 'id="fpTask"'):
        assert token in html, f"index.html 缺 {token}"
    for token in ("gal_tasks_done", "gal_tasks_collapsed", "__taskDone",
                  "fp-task-item", "mark(\"bg\")", "mark(\"choice\")"):
        assert token in js, f"editor_shell.js 缺 {token}"
    for token in (".fp-task-head", ".fp-task.hidden", ".fp-task-item.done"):
        assert token in css, f"editor.css 缺 {token}"


# ---------- 1080p 预设：UI 设计区画布尺寸 ----------

def test_画布尺寸下拉与读写入口():
    html = open(os.path.join(ROOT, "editor", "index.html"), encoding="utf-8").read()
    js = open(os.path.join(ROOT, "editor", "editor_uidesign.js"), encoding="utf-8").read()
    assert 'id="uidCanvas"' in html and "1920x1080" in html
    for token in ("uidCanvas", "out.canvas", "canvas: {size"):
        assert token in js, f"editor_uidesign.js 缺 {token}"
    py = open(os.path.join(ROOT, "engine", "editor.py"), encoding="utf-8").read()
    assert 'resp["canvas"]' in py and 'cfg["canvas_size"]' in py


# ---------- 素材热重载：同名文件替换后自动重读 ----------

def test_图片素材替换后自动重载(ren, tmp_path):
    p = tmp_path / "bg.png"
    pygame.image.save(pygame.Surface((2, 2)), str(p))
    first = ren._load_image_path(str(p))
    assert first is not None and first.get_width() == 2

    time.sleep(0.02)
    pygame.image.save(pygame.Surface((4, 4)), str(p))
    os.utime(str(p), (time.time() + 5, time.time() + 5))   # 保证 mtime 变化

    again = ren._load_image_path(str(p))
    assert again is not None and again.get_width() == 4
    assert again is not first


def test_音频缓存也记录mtime(ren):
    assert hasattr(ren, "_load_sound")
    src = open(os.path.join(ROOT, "engine", "render_media.py"), encoding="utf-8").read()
    assert "_sfx_mtime" in src, "音效缓存没有 mtime 热重载"
    assert "_img_mtime" in src, "图片缓存没有 mtime 热重载"


# ---------- 桌宠：位置 / 大小记忆 ----------

def test_桌宠位置大小记忆(tmp_path, monkeypatch):
    from engine import pet

    cfg_path = tmp_path / "mooki.json"
    monkeypatch.setattr(pet, "_CFG_PATH", str(cfg_path))
    monkeypatch.setattr(pet, "get_window_rect", lambda hwnd: (120, 240))
    pet._remember(object(), 1.2)
    cfg = pet._load_cfg()
    assert cfg["pos"] == [120, 240]
    assert cfg["scale"] == 1.2


def test_桌宠记忆文件损坏不崩(tmp_path, monkeypatch):
    from engine import pet

    cfg_path = tmp_path / "mooki.json"
    cfg_path.write_text("{坏 json", encoding="utf-8")
    monkeypatch.setattr(pet, "_CFG_PATH", str(cfg_path))
    assert pet._load_cfg() == {}


class _PetFakeHandler:
    """只实现 _pet_control 用到的两个方法，避免起真实 HTTP 服务。"""

    def __init__(self, payload):
        self.payload = payload
        self.result = None

    def _read_json(self):
        return self.payload

    def _send_json(self, code, data):
        self.result = (code, data)


def test_桌宠默认关闭():
    """编辑器启动时桌宠必须是关的：/api/pet status 返回 running=False。"""
    from engine import editor

    old = editor._PET_PROC
    editor._PET_PROC = None
    try:
        h = _PetFakeHandler({"action": "status"})
        editor._EditorHandler._pet_control(h)
        assert h.result == (200, {"ok": True, "running": False})
    finally:
        editor._PET_PROC = old


def test_桌宠启动命令区分冻结版与源码版(monkeypatch):
    """发行版必须用 editor.exe --pet；源码版才用 python -m engine.pet。"""
    import sys

    from engine import editor

    calls = []

    class _Proc:
        def poll(self):
            return None

    monkeypatch.setattr(editor.subprocess, "Popen",
                        lambda cmd, **kw: calls.append(cmd) or _Proc())
    old = editor._PET_PROC
    editor._PET_PROC = None
    try:
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        h = _PetFakeHandler({"action": "start"})
        editor._EditorHandler._pet_control(h)
        assert calls[-1] == [sys.executable, "--pet"]
        assert h.result[1]["running"] is True

        editor._PET_PROC = None
        monkeypatch.setattr(sys, "frozen", False, raising=False)
        h = _PetFakeHandler({"action": "start"})
        editor._EditorHandler._pet_control(h)
        assert calls[-1][1:] == ["-m", "engine.pet"]
    finally:
        editor._PET_PROC = old


class _PetFakeUser32:
    def __init__(self, cmd):
        self.cmd = cmd

    def CreatePopupMenu(self):
        return 1

    def AppendMenuW(self, *args):
        pass

    def GetCursorPos(self, ref):
        pass

    def SetForegroundWindow(self, hwnd):
        pass

    def TrackPopupMenu(self, *args):
        return self.cmd

    def DestroyMenu(self, menu):
        pass


def test_桌宠右键打开引擎_冻结版与源码版命令(monkeypatch):
    """右键菜单「打开 MYONL 引擎」在冻结版不能拼 -m（editor.exe 不支持）。"""
    import subprocess
    import sys

    from engine import pet

    calls = []
    monkeypatch.setattr(pet, "user32", _PetFakeUser32(1))
    monkeypatch.setattr(subprocess, "Popen",
                        lambda cmd, **kw: calls.append((cmd, kw)))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    pet.show_menu(object(), 1.0)
    assert calls[-1][0] == [sys.executable]

    calls.clear()
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    pet.show_menu(object(), 1.0)
    assert calls[-1][0][1:] == ["-m", "engine.editor_app"]


# ---------- 设置页布局：高级组变多后不能掉出屏幕 ----------

def test_设置页高级组在720p不溢出(ren):
    groups = []
    for it in ui.SETTINGS_ITEMS:
        g = it.get("group", "基础")
        if g not in groups:
            groups.append(g)
    items = [
        {"label": it["label"], "key": it["key"], "kind": it["kind"],
         "group": it.get("group", "基础"), "enabled": True,
         "options": it.get("options"), "labels": it.get("labels"),
         "value": data.DEFAULT_SETTINGS[it["key"]]}
        for it in ui.SETTINGS_ITEMS
    ]
    view = {"mode": "settings", "items": items, "settings": dict(data.DEFAULT_SETTINGS),
            "cursor": 0, "settings_groups": groups,
            "settings_tab": groups.index("高级")}
    ren._draw_settings(view)          # 不崩

    count = len([it for it in items if it["group"] == "高级"])
    row_h, top = 72, 210
    avail = 720 - (top - 68) - 28 - 68 - 24
    if count * row_h > avail:
        row_h = max(44, avail // count)
    card_h = 68 + max(len(groups) * 54, count * row_h + 8) + 28
    assert (top - 68) + card_h <= 720, f"高级组 {count} 项时卡片底 {(top - 68) + card_h} 超出 720"


# ---------- 右键菜单：复制粘贴一幕 / 查看属性（用户 2026-11-01 要求） ----------

def test_场景右键菜单复制粘贴一幕与查看属性():
    js = open(os.path.join(ROOT, "editor", "editor_scene.js"), encoding="utf-8").read()
    css = open(os.path.join(ROOT, "editor", "editor.css"), encoding="utf-8").read()
    for token in ("contextmenu", "scene-ctx", "复制这一幕", "粘贴到这一幕下面",
                  "查看这一幕的属性", "gal_scene_clip", "copySceneAt", "pasteSceneAfter",
                  "不能整段复制", "ctxEl = el"):
        assert token in js, f"editor_scene.js 缺 {token}"
    # 源码区右键：文字复制/粘贴 + 所在幕操作
    for token in ("复制所在幕", "查看所在幕属性", "navigator.clipboard", "setRangeText"):
        assert token in js, f"源码右键缺 {token}"
    assert ".scene-ctx" in css and ".scene-ctx-sep" in css


def test_场景图层顺序面板可拖拽改z():
    js = open(os.path.join(ROOT, "editor", "editor_scene.js"), encoding="utf-8").read()
    css = open(os.path.join(ROOT, "editor", "editor.css"), encoding="utf-8").read()
    for token in ("图层顺序", "sf-layers", "layerPanelHtml", "reorderLayers",
                  "wireLayers", "draggable", "drag-over", "sf-layer-z"):
        assert token in js, f"editor_scene.js 缺 {token}"
    for token in (".sf-layers", ".sf-layer.draggable", ".sf-layer.drag-over", ".sf-layer-z"):
        assert token in css, f"editor.css 缺 {token}"


# ---------- 场景视图台词解析：必须与引擎括号语法一致（2026-11-02） ----------

def _extract_js_function(src, name):
    """从 JS 源码抠出具名函数（本项目这几个函数内没有花括号字符串，按深度匹配即可）。"""
    start = src.index("function " + name + "(")
    brace = src.index("{", start)
    depth = 0
    for k in range(brace, len(src)):
        if src[k] == "{":
            depth += 1
        elif src[k] == "}":
            depth -= 1
            if depth == 0:
                return src[start:k + 1]
    raise AssertionError("函数没闭合：" + name)


def test_场景视图台词解析与引擎括号语法一致():
    import json
    import shutil
    import subprocess

    node = shutil.which("node")
    if not node:
        pytest.skip("未安装 Node.js，跳过场景视图 JS 解析校验")
    js = open(os.path.join(ROOT, "editor", "editor_scene.js"), encoding="utf-8").read()
    code = (_extract_js_function(js, "stripLeadColon") + "\n" +
            _extract_js_function(js, "parseSayLine") + """
var cases = [
  "@[林晚[老师]] 你好。",
  "@[[林晚]] 那年夏天。",
  "@[林晚]: 冒号不显示",
  "@ 林晚 旧写法",
  "@[林晚]",
  "@[林晚] 文本 ] 尾巴"
];
console.log(JSON.stringify(cases.map(parseSayLine)));
""")
    out = subprocess.run([node, "-e", code], capture_output=True, text=True, encoding="utf-8")
    assert out.returncode == 0, out.stderr
    got = json.loads(out.stdout)
    assert got[0] == {"who": "林晚[老师]", "text": "你好。", "style": "bracket"}
    assert got[1] == {"who": "林晚", "text": "那年夏天。", "style": "bracket2"}
    assert got[2] == {"who": "林晚", "text": "冒号不显示", "style": "bracket"}
    assert got[3] == {"who": "林晚", "text": "旧写法", "style": "plain"}
    assert got[4] == {"who": "林晚", "text": "", "style": "bracket"}
    assert got[5] == {"who": "林晚", "text": "文本 ] 尾巴", "style": "bracket"}
