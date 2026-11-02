# -*- coding: utf-8 -*-
"""tests/test_renderer.py：renderer.py / demo.py 验收（无头 dummy 模式）。"""
import os
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")  # 无头模式，须在 import pygame 前生效

import pygame
import pytest

from engine.demo import run
from engine.renderer import Renderer

pytestmark = [pytest.mark.ui]

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


@pytest.fixture
def ren(tmp_path):
    """空资源根的渲染器（所有素材走占位逻辑），用毕关闭。"""
    r = Renderer((1280, 720), str(tmp_path))
    yield r
    r.close()


def _full_state():
    """含 bg/sprites/history/pending_choice 的完整 GameState。"""
    return {
        "bg": "classroom",
        "music": None,
        "sprites": [{"char": "lin", "expr": "normal"}],
        "vars": {"好感": 1},
        "characters": {"林晚": {"color": "#aaccff"}},
        "history": [{"char": "林晚", "text": "你来了。今天天气不错，适合在教室里聊聊天。"}],
        "pending_choice": {"options": [
            {"text": "打招呼", "target": "label_hello", "available": True},
            {"text": "不理她", "target": "label_ignore", "available": False},
        ], "line": 15},
        "finished": False,
    }


def _make_images(root):
    """造真图片：images/classroom.png 与 images/lin_normal.png。"""
    images = os.path.join(root, "images")
    os.makedirs(images, exist_ok=True)
    bg = pygame.Surface((640, 360))
    bg.fill((60, 90, 140))
    sp = pygame.Surface((200, 400), pygame.SRCALPHA)
    sp.fill((200, 120, 120, 255))
    pygame.image.save(bg, os.path.join(images, "classroom.png"))
    pygame.image.save(sp, os.path.join(images, "lin_normal.png"))


# ---------- 4. 初始化 ----------

def test_init_与_close_不抛异常(tmp_path):
    r = Renderer((1280, 720), str(tmp_path))
    assert r._screen.get_size() == (1280, 720)
    r.close()


# ---------- 5/6/7. render 不崩 ----------

def test_render_空状态不崩(ren):
    ren.render({})


def test_render_完整状态不崩(tmp_path):
    _make_images(str(tmp_path))
    r = Renderer((1280, 720), str(tmp_path))
    try:
        r.render(_full_state())
    finally:
        r.close()


def test_render_素材缺失走占位不崩(ren):
    # bg/sprites 指向不存在的图片 → 占位色块 + 中文标签，不得抛异常
    ren.render(_full_state())


# ---------- 8. screenshot ----------

def test_screenshot_返回存在的_png(ren, tmp_path):
    ren.render(_full_state())
    path = ren.screenshot(str(tmp_path / "shot" / "a.png"))
    assert os.path.isfile(path)
    with open(path, "rb") as f:
        assert f.read(8) == b"\x89PNG\r\n\x1a\n"  # PNG 文件头


# ---------- P19 目标 2：@cg 双查（新名优先，旧 cg_ 前缀兜底） ----------

def _save_cg(root, filename, color):
    images = os.path.join(root, "images")
    os.makedirs(images, exist_ok=True)
    surf = pygame.Surface((40, 30))
    surf.fill(color)
    pygame.image.save(surf, os.path.join(images, filename))


def test_cg_new_name_first(ren, tmp_path):
    _save_cg(str(tmp_path), "星空.png", (255, 0, 0))
    _save_cg(str(tmp_path), "cg_星空.png", (0, 0, 255))
    img = ren._load_cg("星空")
    assert img is not None and tuple(img.get_at((0, 0)))[:3] == (255, 0, 0)


def test_cg_old_prefix_fallback(ren, tmp_path):
    _save_cg(str(tmp_path), "cg_星空.png", (0, 0, 255))
    img = ren._load_cg("星空")
    assert img is not None and tuple(img.get_at((0, 0)))[:3] == (0, 0, 255)


def test_cg_missing_returns_none(ren):
    assert ren._load_cg("不存在") is None


# ---------- P19 目标 3：立绘 pos / scale 布局 ----------

def test_sprite_rect_pos_left_right(ren):
    size = (200, 200)
    left = ren._sprite_rect(size, {"pos": "左"}, 0, 2)
    assert left.x == 20 and left.bottom == 540          # 左边距 20px，脚踩对话框上沿
    right = ren._sprite_rect(size, {"pos": "右"}, 0, 2)
    assert right.right == 1280 - 20                     # 右缘贴边留 20px
    mid = ren._sprite_rect(size, {"pos": "中"}, 0, 2)
    assert mid.centerx == 640


def test_sprite_rect_scale(ren):
    half = ren._sprite_rect((200, 200), {"scale": 0.5}, 0, 1)
    assert half.size == (100, 100)                      # 目标宽 = 原宽 × 0.5
    double = ren._sprite_rect((200, 200), {"scale": 2.0}, 0, 1)
    assert double.size == (400, 400)


def test_sprite_rect_default_unchanged(ren):
    # 不写 pos/scale：旧行为（单立绘居中、等比收进对话框以上区域）
    rect = ren._sprite_rect((200, 400), {}, 0, 1)
    assert rect.centerx == 640 and rect.bottom == 540
    # 双立绘仍按等宽槽位从右往左（旧的均分行为不变）
    assert ren._sprite_rect((200, 200), {}, 0, 2).centerx == 960
    assert ren._sprite_rect((200, 200), {}, 1, 2).centerx == 320


def test_screenshot_默认路径带时间戳(ren, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # 默认存 ./screenshots/，切到 tmp 避免污染项目目录
    ren.render({})
    path = ren.screenshot()
    assert os.path.isfile(path)
    assert path.endswith(".png")


# ---------- 9. 打字机推进 ----------

def test_打字机_已显示字符数随帧增长(ren):
    state = _full_state()
    state["pending_choice"] = None
    ren.render(state)
    first = ren._tw_shown
    time.sleep(0.1)  # text_speed 默认 30 字符/秒 → 约增长 3 字
    ren.render(state)
    assert ren._tw_shown > first


def test_打字机_history变化时重置(ren):
    state = _full_state()
    state["pending_choice"] = None
    ren.render(state)
    time.sleep(0.05)
    ren.render(state)
    assert ren._tw_shown > 0
    state2 = dict(state)
    state2["history"] = state["history"] + [{"char": None, "text": "新的一句旁白。"}]
    ren.render(state2)
    assert ren._tw_shown < len("新的一句旁白。")  # 重置后重新起算


# ---------- 10. 输入映射 ----------

def test_输入_关闭窗口与Esc_返回quit(ren):
    ren.render({})
    pygame.event.post(pygame.event.Event(pygame.QUIT))
    assert ren.handle_input() == {"action": "quit"}
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
    assert ren.handle_input() == {"action": "quit"}


def test_输入_空格_打字机未完返回reveal(ren):
    state = _full_state()
    state["pending_choice"] = None
    ren.render(state)  # 长文本刚起头，打字机未完
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE))
    assert ren.handle_input() == {"action": "reveal"}
    assert ren.typewriter_complete()  # reveal 已由 renderer 内部处理（直接显示全文）


def test_输入_空格_打字机已完返回advance(ren):
    ren.render({})  # 无对话，打字机视为已完成
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE))
    assert ren.handle_input() == {"action": "advance"}


def test_输入_鼠标左键等同推进(ren):
    ren.render({})
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(640, 360)))
    assert ren.handle_input() == {"action": "advance"}


def test_输入_数字键选择选项(ren):
    ren.render(_full_state())
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_1))
    assert ren.handle_input() == {"action": "choose", "index": 0}
    # 第 2 项 available=false → 数字键直选无效
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_2))
    assert ren.handle_input() == {"action": "none"}


def test_输入_方向键加回车选择选项(ren):
    ren.render(_full_state())
    # 初始高亮第 0 项；按下应跳过不可选项循环回第 0 项
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DOWN))
    assert ren.handle_input() == {"action": "none"}
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
    assert ren.handle_input() == {"action": "choose", "index": 0}


def test_输入_鼠标点击选项(ren):
    ren.render(_full_state())
    rect, idx, available = ren._choice_rects[0]
    assert available
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=rect.center))
    assert ren.handle_input() == {"action": "choose", "index": idx}


def test_输入_无输入返回none(ren):
    ren.render({})
    assert ren.handle_input() == {"action": "none"}


# ---------- UI 模式键位分发 ----------

def test_输入_UI模式_翻译成统一键名(ren):
    ren.render({}, {"mode": "menu"})  # render 捕获 UI 模式
    for key, name in [(pygame.K_UP, "up"), (pygame.K_DOWN, "down"),
                      (pygame.K_RETURN, "confirm"), (pygame.K_SPACE, "confirm"),
                      (pygame.K_ESCAPE, "back"), (pygame.K_3, "slot3"),
                      (pygame.K_0, "slot10")]:
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=key))
        assert ren.handle_input() == {"action": name}


def test_输入_playing模式_Esc开菜单_无选项时上键开回看(ren):
    ren.render({}, {"mode": "playing"})
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
    assert ren.handle_input() == {"action": "back"}
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_UP))
    assert ren.handle_input() == {"action": "backlog"}


def test_输入_选项模式优先于回看(ren):
    ren.render(_full_state(), {"mode": "playing"})  # 带 pending_choice
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_UP))
    assert ren.handle_input() == {"action": "none"}  # ↑ 移动选项高亮，不开回看


def test_render_UI覆盖层_各模式不崩(ren):
    # ui_view 各模式都不得抛异常（绘制效果由 screenshots/ 人工核对）
    state = _full_state()
    for view in [{"mode": "title", "title": "Moyul", "items": [], "cursor": 0},
                 {"mode": "menu", "items": [{"label": "存档", "enabled": True}], "cursor": 0},
                 {"mode": "slots", "slots_mode": "save", "cursor": 0,
                  "slots": [{"slot": "quick", "name": "快速存档", "label": None,
                             "saved_at": None, "empty": True, "enabled": True}]},
                 {"mode": "settings", "settings": {"text_speed": 30}, "cursor": 0},
                 {"mode": "backlog", "history": [{"char": "林晚", "text": "你好。"}],
                  "backlog_offset": 0}]:
        ren.render(state, view)


# ---------- 11/12. demo 冒烟与完整跑通 ----------

def test_demo_冒烟_10帧不崩(tmp_path):
    run(os.path.join(FIXTURES, "基础流程.gal"), assets_root=str(tmp_path),
        max_frames=10, auto=False)


def test_demo_完整跑通(tmp_path):
    # auto 默认 True：无输入自动推进到 finished
    run(os.path.join(FIXTURES, "基础流程.gal"), assets_root=str(tmp_path))


# ---------- 13. 资源缺失预检 ----------

def test_资源预检_打印中文缺失清单且不崩(tmp_path, capsys):
    script = tmp_path / "缺资源.gal"
    script.write_text(
        "@bg no_such_bg\n"
        "@music no_such_music\n"
        "@show ghost happy\n"
        "@sfx no_such_sfx\n"
        "@ 旁白一句。\n"
        "@end\n",
        encoding="utf-8")
    run(str(script), assets_root=str(tmp_path), max_frames=5)
    err = capsys.readouterr().err
    assert f"[资源缺失] images/no_such_bg.png 或 images/no_such_bg.jpg —— @bg no_such_bg（{script} 第 1 行）" in err
    assert (f"[资源缺失] audio/no_such_music.ogg 或 audio/no_such_music.mp3 或 audio/no_such_music.wav"
            f" —— @music no_such_music（{script} 第 2 行）") in err
    assert f"[资源缺失] images/ghost_happy.png 或 images/ghost_happy.jpg —— @show ghost happy（{script} 第 3 行）" in err
    assert (f"[资源缺失] audio/no_such_sfx.ogg 或 audio/no_such_sfx.mp3 或 audio/no_such_sfx.wav"
            f" —— @sfx no_such_sfx（{script} 第 4 行）") in err


def test_资源预检_多文件定位到子文件(tmp_path, capsys):
    """子文件里缺图时，清单显示子文件路径与该文件内的行号。"""
    chapter = tmp_path / "章节" / "第一章.gal"
    chapter.parent.mkdir(parents=True)
    chapter.write_text("@bg ghost_child\n", encoding="utf-8")
    main = tmp_path / "主.gal"
    main.write_text("@include 章节/第一章.gal\n@ 旁白一句。\n", encoding="utf-8")
    run(str(main), assets_root=str(tmp_path), max_frames=3)
    err = capsys.readouterr().err
    child_file = str(chapter.resolve())
    assert f"[资源缺失] images/ghost_child.png 或 images/ghost_child.jpg —— @bg ghost_child（{child_file} 第 1 行）" in err


# ---------- P37-T5 标题字距渲染 ----------

def test_render_spaced_text_零字距等同常规渲染(ren):
    font = ren._title_font
    normal = font.render("Moyul", True, (255, 255, 255))
    spaced = ren._render_spaced_text("Moyul", font, (255, 255, 255), spacing=0)
    assert spaced.get_width() == normal.get_width()
    assert spaced.get_height() == normal.get_height()


def test_render_spaced_text_正字距加宽(ren):
    font = ren._title_font
    normal_w = font.render("Moyul", True, (255, 255, 255)).get_width()
    spaced = ren._render_spaced_text("Moyul", font, (255, 255, 255), spacing=4)
    # 5 个字符 → 4 个间距，宽度应增加 4*4=16
    assert spaced.get_width() == normal_w + 4 * 4


def test_render_spaced_text_阴影加大尺寸(ren):
    font = ren._title_font
    no_shadow = ren._render_spaced_text("Hi", font, (255, 255, 255), spacing=0)
    with_shadow = ren._render_spaced_text("Hi", font, (255, 255, 255),
                                          spacing=0, shadow_color=(0, 0, 0, 100))
    assert with_shadow.get_width() == no_shadow.get_width() + 2
    assert with_shadow.get_height() == no_shadow.get_height() + 2


def test_render_spaced_text_空串不崩(ren):
    surf = ren._render_spaced_text("", ren._title_font, (255, 255, 255), spacing=3)
    assert surf is not None


def test_title_默认背景含星尘不崩(ren):
    """无 title_bg 图时，标题页走渐变 + 星尘，不得抛异常。"""
    ren.render({}, {"mode": "title", "title": "月光漫步", "items": [], "cursor": 0})
