"""P30-S3 配置前哨：config.json 只读配置（窗口标题/字号/色板/遮罩 alpha/键位）。

覆盖：
1. 默认值与 P29 前的硬编码常量一致（不写 config.json 时行为零变化）
2. config.json 覆盖窗口标题/字号/色板/遮罩 alpha
3. 局部覆盖只改指定键，其余保留默认（深合并）
4. 文件损坏 / 顶层不是对象 → 回落默认 + 中文警告，不崩
5. 非法颜色长度、alpha 超界 → 回落默认 / 裁剪到 0~255
6. 键位覆盖生效；不存在的键名忽略并记录警告
7. Renderer 真正消费 config（窗口标题、色板、字号、键位表）
"""

import json
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")  # 无头模式，须在 import pygame 前生效
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402
import pytest  # noqa: E402

from engine import config as C  # noqa: E402
from engine import renderer as R  # noqa: E402

pytestmark = [pytest.mark.unit, pytest.mark.ui]


def test_pixelated_兼容字符串布尔():
    """旧编辑器曾把 "false" 字符串写进 config；必须按假处理，不能 bool("false")=True。"""
    assert C.Config({"ui": {"pixelated": "false"}}).pixelated() is False
    assert C.Config({"ui": {"pixelated": "true"}}).pixelated() is True
    assert C.Config({"ui": {"pixelated": False}}).pixelated() is False


def _write(root, payload) -> str:
    path = os.path.join(str(root), "config.json")
    with open(path, "w", encoding="utf-8") as f:
        if isinstance(payload, str):
            f.write(payload)
        else:
            json.dump(payload, f, ensure_ascii=False)
    return path


def test_默认配置_与旧常量一致():
    """不写 config.json 时，窗口标题/字号/色板/遮罩 alpha 与 P29 硬编码值完全相同。"""
    cfg = C.load("不存在的目录")
    assert cfg.window_title == "MYONL"
    assert cfg.font("body") == R.FONT_SIZE == 28
    assert cfg.font("title") == R.TITLE_FONT_SIZE == 72
    assert cfg.font("mid") == 40
    assert cfg.font("small") == 22
    assert cfg.color("selected_bg") == R.UI_SELECTED_BG
    assert cfg.color("selected_border") == R.UI_SELECTED_BORDER
    assert cfg.color("dialog_fg_dim") == R.DIALOG_FG_DIM
    assert cfg.alpha("selected_bg") == R.UI_SELECTED_BG_ALPHA
    assert cfg.alpha("idle_bg") == R.UI_IDLE_BG_ALPHA
    assert cfg.alpha("menu") == 235
    assert cfg.warnings == []


def test_config_json覆盖窗口标题与字号(tmp_path):
    _write(tmp_path, {"window_title": "月光漫步", "font": {"body": 32}})
    cfg = C.load(str(tmp_path))
    assert cfg.window_title == "月光漫步"
    assert cfg.font("body") == 32
    assert cfg.font("title") == 72  # 未覆盖的保留默认


def test_局部覆盖保留其余默认(tmp_path):
    _write(tmp_path, {"colors": {"selected_bg": [1, 2, 3]}, "alphas": {"menu": 200}})
    cfg = C.load(str(tmp_path))
    assert cfg.color("selected_bg") == (1, 2, 3)
    assert cfg.color("selected_fg") == (255, 255, 255)  # 同段其他键保留默认
    assert cfg.alpha("menu") == 200
    assert cfg.alpha("slots") == 240


def test_配置文件损坏回落默认并给中文警告(tmp_path):
    _write(tmp_path, "{ 这不是合法 JSON")
    cfg = C.load(str(tmp_path))
    assert cfg.window_title == "MYONL"
    assert cfg.warnings and "读取失败" in cfg.warnings[0]


def test_顶层不是对象回落默认(tmp_path):
    _write(tmp_path, [1, 2, 3])
    cfg = C.load(str(tmp_path))
    assert cfg.window_title == "MYONL"
    assert cfg.warnings and "顶层不是对象" in cfg.warnings[0]


def test_非法颜色与alpha回落与裁剪(tmp_path):
    _write(tmp_path, {"colors": {"selected_bg": [1, 2]}, "alphas": {"menu": 999, "slots": -5}})
    cfg = C.load(str(tmp_path))
    assert cfg.color("selected_bg") == (40, 54, 96)  # 长度非法 → 默认
    assert cfg.alpha("menu") == 255  # 超界裁剪
    assert cfg.alpha("slots") == 0


def test_键位覆盖生效(tmp_path):
    _write(tmp_path, {"keymap": {"back": ["K_F1"]}})
    cfg = C.load(str(tmp_path))
    table = C.keymap(cfg)
    assert table.get(pygame.K_F1) == "back"
    assert pygame.K_ESCAPE not in table  # 默认的 Esc 被覆盖掉


def test_不存在的键名忽略并记录警告(tmp_path):
    _write(tmp_path, {"keymap": {"back": ["K_NOT_A_REAL_KEY"]}})
    cfg = C.load(str(tmp_path))
    table = C.keymap(cfg)
    assert "back" not in table.values()
    assert any("不存在的键名" in w for w in cfg.warnings)


def test_键位写错类型忽略并记录警告(tmp_path):
    _write(tmp_path, {"keymap": {"back": [123]}})
    cfg = C.load(str(tmp_path))
    C.keymap(cfg)
    assert any("不存在的键名" in w for w in cfg.warnings)


def test_renderer消费config(tmp_path):
    """Renderer 真正读 config.json：窗口标题、色板、字号、键位表都跟着变。"""
    _write(tmp_path, {
        "window_title": "月光测试",
        "font": {"body": 32},
        "colors": {"selected_bg": [7, 8, 9]},
        "keymap": {"back": ["K_F1"]},
    })
    ren = R.Renderer((1280, 720), str(tmp_path))
    try:
        assert ren.config.window_title == "月光测试"
        assert pygame.display.get_caption()[0] == "月光测试"
        assert ren.config.color("selected_bg") == (7, 8, 9)
        assert ren.config.font("body") == 32
        assert R._ui_key(pygame.K_F1, ren._keymap) == "back"
        assert R._ui_key(pygame.K_ESCAPE, ren._keymap) is None
    finally:
        ren.close()


def test_ui_key_不传键位表时走内置默认():
    """旧调用点（不传 keymap）行为不变。"""
    assert R._ui_key(pygame.K_RETURN) == "confirm"
    assert R._ui_key(pygame.K_0) == "slot10"


def test_类型防护_非dict覆盖dict保留默认(tmp_path, capsys):
    """config.json 里写 "font": "large"（字符串而非字典）时，保留默认值并打印警告。"""
    _write(tmp_path, {"font": "large"})  # 错误类型：应为 dict
    cfg = C.load(str(tmp_path))
    captured = capsys.readouterr()
    assert "配置警告" in captured.err
    assert "font" in captured.err
    # 默认值应保留
    assert cfg.font("body") == 28
    assert cfg.font("title") == 72


def test_类型防护_colors写错类型保留默认(tmp_path, capsys):
    """config.json 里写 "colors": "blue" 时，保留默认颜色并打印警告。"""
    _write(tmp_path, {"colors": "blue"})  # 错误类型
    cfg = C.load(str(tmp_path))
    captured = capsys.readouterr()
    assert "配置警告" in captured.err
    # 默认值应保留
    assert cfg.color("text") == (255, 255, 255)


def test_类型防护_嵌套dict类型错误(tmp_path, capsys):
    """config.json 里写 "dialogue": {"default": "wrong"} 时，嵌套类型防护生效。"""
    _write(tmp_path, {"dialogue": {"default": "wrong"}})  # default 应为 dict
    cfg = C.load(str(tmp_path))
    captured = capsys.readouterr()
    assert "配置警告" in captured.err
    # 默认值应保留
    assert cfg.dialogue("default")["height"] == 180


def test_字幕隐藏条默认配置():
    """curtain 配置项有合理的默认值。"""
    cfg = C.load("不存在的目录")
    curtain = cfg.dialogue("default").get("curtain", {})
    assert curtain["capture_height"] == 24  # 捕获区 24px
    assert curtain["line_height"] == 2      # 顶边线 2px
    assert curtain["alpha_normal"] == 160   # 正常态 α160
    assert curtain["alpha_hidden"] == 200   # 隐藏态 α200
    assert curtain["symbol"] == "."         # 默认句号
    assert curtain["symbol_size"] == 10     # 符号 10px
    assert curtain["full_width"] is True    # 拉通整屏


def test_字幕隐藏条可配置(tmp_path):
    """开发者可在 config.json 里自定义 curtain 参数。"""
    _write(tmp_path, {"dialogue": {"default": {"curtain": {
        "capture_height": 32,
        "alpha_normal": 120,
        "symbol": "▼",
    }}}})
    cfg = C.load(str(tmp_path))
    curtain = cfg.dialogue("default").get("curtain", {})
    assert curtain["capture_height"] == 32
    assert curtain["alpha_normal"] == 120
    assert curtain["symbol"] == "▼"
    # 未覆盖的值保留默认
    assert curtain["line_height"] == 2
    assert curtain["alpha_hidden"] == 200


# ==================== P51：UI 三层配置（引擎默认/项目/玩家） ====================


def test_p51_ui_默认像素化与偏圆矩形():
    """P51：ui 段提供引擎默认——像素化开关、像素块大小、偏圆圆角。"""
    cfg = C.load("不存在的目录")
    assert cfg.pixelated() is True        # 默认像素化（Python 程序化）
    assert cfg.pixel_scale() == 4         # 默认 4px 像素块
    assert cfg.corner_radius() == 10      # 默认偏圆矩形（与 dialogue.default.radius 同源语义）
    # dialogue 默认几何：radius 10 / bg_alpha 150 / 偏移与面板宽默认 0（贴边全宽）
    d = cfg.dialogue("default")
    assert d["radius"] == 10
    assert d["bg_alpha"] == 150
    assert d["offset_x"] == 0 and d["offset_y"] == 0
    assert d["panel_width"] == 0


def test_p51_项目配置可覆盖像素化参数(tmp_path):
    """P51：config.json 可覆盖 ui 段（像素开关/块大小/圆角）——项目级默认独立。"""
    _write(tmp_path, {
        "ui": {"pixelated": False, "pixel_scale": 8, "corner_radius": 20},
        "dialogue": {"default": {"radius": 20, "panel_width": 900}},
    })
    cfg = C.load(str(tmp_path))
    assert cfg.pixelated() is False
    assert cfg.pixel_scale() == 8
    assert cfg.corner_radius() == 20
    d = cfg.dialogue("default")
    assert d["radius"] == 20
    assert d["panel_width"] == 900
    # 未覆盖的默认键保留（引擎默认 ← 项目覆盖 ← 玩家覆盖的三层回落）
    assert d["bg_alpha"] == 150


def test_p51_玩家ui几何覆盖三层合并():
    """P51：玩家 settings.json 的 ui_geometry 并入配置视图（引擎默认←项目←玩家）。"""
    cfg = C.load("不存在的目录")
    assert cfg.dialogue("default")["radius"] == 10      # 玩家覆盖前 = 引擎默认
    cfg.apply_player_ui({"radius": 16, "offset_x": 40, "offset_y": -20,
                         "panel_width": 1000, "height": 200, "unknown": 999})
    d = cfg.dialogue("default")
    assert d["radius"] == 16        # 玩家覆盖生效
    assert d["offset_x"] == 40
    assert d["offset_y"] == -20
    assert d["panel_width"] == 1000
    assert d["height"] == 200
    assert "unknown" not in d       # 未知键忽略
    # 未覆盖键保留引擎默认（三层缺省回落）
    assert d["bg_alpha"] == 150
    assert d["margin"] == 24
