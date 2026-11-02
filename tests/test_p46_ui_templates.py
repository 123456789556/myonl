# -*- coding: utf-8 -*-
"""P46：UI 主题模板（黑/紫/白）+ 正文对齐配置 + 台词富文本标记。"""
import json
import os

import pytest

from engine import config as C
from engine import richtext
from engine.newgame import ALIGNS, THEMES, create_game

pytestmark = [pytest.mark.unit]


# ---------- 富文本解析 ----------

def test_richtext_纯文本原样():
    segs = richtext.parse("你好，世界。")
    assert segs == [("你好，世界。", richtext.BASE_STYLE)]
    assert richtext.strip("你好，世界。") == "你好，世界。"


def test_richtext_粗斜色字号():
    segs = richtext.parse("前{b}粗{/b}{i}斜{/i}{color=#ff6666}红{/color}{size=40}大{/size}后")
    plain = "".join(s for s, _ in segs)
    assert plain == "前粗斜红大后"
    styles = {s: st for s, st in segs}
    assert styles["粗"] == (True, False, None, None)
    assert styles["斜"] == (False, True, None, None)
    assert styles["红"][2] == "#ff6666"
    assert styles["大"][3] == 40


def test_richtext_嵌套与恢复():
    segs = richtext.parse("{b}粗{color=red}粗红{/color}粗{/b}")
    styles = [st for _, st in segs]
    assert styles[0] == (True, False, None, None)
    assert styles[1] == (True, False, "red", None)
    assert styles[2] == (True, False, None, None)  # {/color} 后恢复粗体无色


def test_richtext_未闭合自动闭合_不识别标签按原文():
    assert richtext.strip("{b}没闭合") == "没闭合"
    assert richtext.strip("这是{unknown}标签") == "这是{unknown}标签"
    assert richtext.strip("{size=abc}坏{/size}") == "{size=abc}坏{/size}"


def test_richtext_转义花括号():
    assert richtext.strip("{{b}}不是标签") == "{b}不是标签"


def test_richtext_可视前缀不按标签计数():
    raw = "你好{b}粗体{/b}尾"
    assert richtext.strip(richtext.visible_prefix(raw, 3)) == "你好粗"
    # 截在标签中间：标签完整保留或不取，绝不切碎
    assert richtext.strip(richtext.visible_prefix(raw, 0)) == ""
    assert richtext.strip(richtext.visible_prefix(raw, 99)) == "你好粗体尾"


def test_richtext_分行映射与纯文本折行一致():
    from engine.render_utils import _wrap_text

    class FakeFont:
        def size(self, t):
            return (len(t) * 10, 20)

    raw = "一{b}二三{/b}四{color=red}五六七{/color}八"
    plain = richtext.strip(raw)
    lines = _wrap_text(plain, FakeFont(), 40)  # 每行 4 字
    rich = richtext.split_rich_lines(richtext.parse(raw), lines)
    assert ["".join(s for s, _ in rl) for rl in rich] == lines  # 行内容不变
    assert rich[0][1][1] == (True, False, None, None)           # 样式随字走


# ---------- config 对齐 ----------

def test_config_dialogue_默认左对齐():
    cfg = C.Config()
    assert cfg.dialogue("default")["align"] == "left"
    assert cfg.dialogue("nvl")["align"] == "left"


def test_config_dialogue_字符串覆盖生效_非法类型仍丢弃():
    cfg = C.Config({"dialogue": {"default": {"align": "right", "height": "abc"}}})
    d = cfg.dialogue("default")
    assert d["align"] == "right"
    assert d["height"] == 180  # 非法字符串不覆盖数字默认


# ---------- 渲染层集成（无头） ----------

@pytest.fixture
def ren(tmp_path):
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    from engine.renderer import Renderer
    r = Renderer((1280, 720), str(tmp_path))
    yield r
    r.close()


def _say(ren, text, char="林"):
    history = [{"char": char, "text": text}]
    ren._update_typewriter(history, 0, False)
    ren.reveal_all()
    return history


def test_布局_标记不占可视字数且lines为纯文本(ren):
    history = _say(ren, "你好{b}粗体{/b}尾巴")
    layout = ren._dialog_layout(history, {}, False)
    assert layout["lines"] == ["你好粗体尾巴"]
    assert layout["rich"][0][1][1] == (True, False, None, None)
    assert layout["align"] == "left"
    assert ren.typewriter_complete()  # 打字机按可视字数判定完成


def test_布局_对齐可配(tmp_path):
    (tmp_path / "config.json").write_text(
        '{"dialogue": {"default": {"align": "right"}}}', encoding="utf-8")
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    from engine.renderer import Renderer
    r = Renderer((1280, 720), str(tmp_path))
    try:
        history = _say(r, "右对齐的一句台词。")
        layout = r._dialog_layout(history, {}, False)
        assert layout["align"] == "right"
        r.render({"history": history, "characters": {}}, None)  # 渲染不崩
    finally:
        r.close()


def test_渲染_三对齐与富文本不崩(ren):
    for align in ("left", "center", "right"):
        ren.config.data["dialogue"]["default"]["align"] = align
        history = _say(ren, "混合{b}粗体{/b}与{color=#ff6666}红字{/color}渲染。")
        ren.render({"history": history, "characters": {}}, None)
    # 非法对齐回落 left 不崩
    ren.config.data["dialogue"]["default"]["align"] = "weird"
    history = _say(ren, "非法对齐回落。")
    assert ren._dialog_layout(history, {}, False)["align"] == "left"


def test_打字机_标记文本按可视字符推进(ren):
    history = [{"char": "林", "text": "ab{b}cd{/b}e"}]
    ren._update_typewriter(history, 0, False)
    ren._tw_shown = 3.0
    layout = ren._dialog_layout(history, {}, False)
    assert layout["lines"] == ["abc"]  # 可视 3 字
    assert not ren.typewriter_complete()
    ren.reveal_all()
    layout = ren._dialog_layout(history, {}, False)
    assert layout["lines"] == ["abcde"]


# ---------- 新建游戏：主题 + 对齐 ----------

def test_newgame_标准版唯一配色(tmp_path):
    """2026-11-01 用户决定：只有一套标准版 UI，不再带 purple/white 风格。"""
    assert THEMES == ("black",)
    root = create_game("测标准版", str(tmp_path))
    cfg = json.loads((root / "config.json").read_text(encoding="utf-8"))
    assert tuple(cfg["theme"]["primary"]) == (130, 140, 160)  # 标准版主色
    assert cfg["dialogue"]["default"]["align"] == "left"


def test_newgame_对齐写入配置(tmp_path):
    for align in ALIGNS:
        root = create_game(f"对齐{align}", str(tmp_path), align=align)
        cfg = json.loads((root / "config.json").read_text(encoding="utf-8"))
        assert cfg["dialogue"]["default"]["align"] == align
        assert cfg["dialogue"]["nvl"]["align"] == align


def test_newgame_非法主题与对齐报中文错(tmp_path):
    with pytest.raises(ValueError, match="未知主题"):
        create_game("坏主题", str(tmp_path), theme="pink")
    with pytest.raises(ValueError, match="未知对齐"):
        create_game("坏对齐", str(tmp_path), align="top")


def test_newgame_默认参数向后兼容(tmp_path):
    """不传 theme/align 时与旧行为一致：黑主题 + 左对齐。"""
    root = create_game("老项目", str(tmp_path))
    cfg = json.loads((root / "config.json").read_text(encoding="utf-8"))
    assert cfg["theme"]["primary"] == [130, 140, 160]
    assert cfg["dialogue"]["default"]["align"] == "left"
