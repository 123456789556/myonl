# -*- coding: utf-8 -*-
"""P51-T6 验收：剧本 / 配置热重载（八大方向 5.1 / 5.2）。

覆盖：
1. FileWatch：首次登记不算变化 / 到轮询点才检查 / 同一窗口不重复 / 删除算变化 / 重新登记
2. Runtime.reload：当前 label 重播、变量与解锁保留、待选项清空、找不到 label 时从头来
3. demo._hot_tick：剧本改完即时生效、解析失败保留旧版本 + toast、config 改完即时生效
4. Renderer.apply_config：字号重建字体并清 T8 缓存、画布尺寸变更拒绝热应用
5. UI.set_config：skip 策略跟随新配置
"""
import json
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")  # 无头模式，须在 import pygame 前生效
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402
import pytest  # noqa: E402

from engine import config as cfgapi  # noqa: E402
from engine import demo, hotload  # noqa: E402
from engine.parser import parse_text  # noqa: E402
from engine.renderer import Renderer  # noqa: E402
from engine.runtime import Runtime  # noqa: E402
from engine.ui import UI  # noqa: E402

pytestmark = [pytest.mark.ui, pytest.mark.integration]

SCRIPT_V1 = """# 热重载测试剧本
@character 林晚 #aaccff

@set 好感 = 3

@label start
@bg classroom
@ 林晚 第一版台词。
@jump second

@label second
@ 林晚 第二幕第一版。
@end
"""

SCRIPT_V2 = SCRIPT_V1.replace("第一版台词。", "第二版台词。").replace(
    "第二幕第一版。", "第二幕第二版。")


_CLOCK = [1000.0]  # 递增的假 mtime：Windows 文件时间粒度约 15ms，连续写可能同 mtime


def _write(path, text: str, mtime: float | None = None) -> None:
    """写文件并显式落一个单调递增的 mtime，保证热重载测试不受文件时间粒度影响。"""
    path.write_text(text, encoding="utf-8")
    if mtime is None:
        _CLOCK[0] += 1.0
        mtime = _CLOCK[0]
    ns = int(mtime * 1_000_000_000)
    os.utime(path, ns=(ns, ns))


def _play_into_second(rt: Runtime) -> None:
    """推进到 second 标签的那句台词（当前 label = second）。"""
    for _ in range(50):
        st = rt.snapshot()
        if st["history"] and st["history"][-1].get("text") == "第二幕第一版。":
            return
        rt.step()
    raise AssertionError("没能推进到 second 标签")


# ==================== 1. FileWatch ====================

def test_登记后未改动不报变化(tmp_path):
    f = tmp_path / "a.gal"
    _write(f, "v1", mtime=1000)
    watch = hotload.FileWatch([f])
    assert watch.changed(0) is False
    assert watch.changed(10 ** 9) is False


def test_到轮询点才发现变化且同一窗口只报一次(tmp_path):
    f = tmp_path / "a.gal"
    _write(f, "v1", mtime=1000)
    watch = hotload.FileWatch([f], interval_ms=500)
    assert watch.changed(0) is False      # 首次轮询：无变化，下次 500 之后
    _write(f, "v2", mtime=2000)
    assert watch.changed(100) is False    # 没到轮询点：不 stat，也不丢变化
    assert watch.changed(500) is True     # 到点：报告变化
    assert watch.changed(600) is False    # 同一轮询窗内不重复报告
    assert watch.changed(1000) is False   # 再轮询：文件没再变


def test_文件被删也算变化(tmp_path):
    f = tmp_path / "a.gal"
    _write(f, "v1", mtime=1000)
    watch = hotload.FileWatch([f], interval_ms=0)
    assert watch.changed(0) is False
    f.unlink()
    assert watch.changed(10) is True


def test_重新登记不会把新文件当变化(tmp_path):
    a, b = tmp_path / "a.gal", tmp_path / "b.gal"
    _write(a, "a1", mtime=1000)
    _write(b, "b1", mtime=1000)
    watch = hotload.FileWatch([a], interval_ms=0)
    watch.changed(0)
    watch.set_paths([a, b])
    assert watch.changed(10) is False     # 刚登记：基线即当前 mtime
    _write(b, "b2", mtime=3000)
    assert watch.changed(20) is True


# ==================== 2. Runtime.reload ====================

def test_重载从当前label重播且变量保留(tmp_path):
    script = tmp_path / "script.gal"
    _write(script, SCRIPT_V1)
    rt = Runtime()
    rt.load(str(script))
    _play_into_second(rt)
    assert rt.current_label() == "second"
    assert rt.snapshot()["vars"]["好感"] == 3

    rt.reload(parse_text(SCRIPT_V2, source=str(script)))
    st = rt.snapshot()
    assert rt.current_label() == "second"          # 接续锚点不变
    assert st["vars"]["好感"] == 3                 # 变量保留
    assert st["stack"] == [list(rt._labels["second"])]  # 回到 label 起点
    rt.step()                                       # 跳过 label → 执行新台词
    assert rt.snapshot()["history"][-1]["text"] == "第二幕第二版。"


def test_重载清空待选项(tmp_path):
    src = """# 选项暂停
@character 林晚 #aaccff
@label start
@choice:
    > 选项甲 -> a
    > 选项乙 -> b
@label a
@ 林晚 A
@end
@label b
@ 林晚 B
@end
"""
    script = tmp_path / "choice.gal"
    _write(script, src)
    rt = Runtime()
    rt.load(str(script))
    for _ in range(10):
        rt.step()
        if rt.snapshot()["pending_choice"] is not None:
            break
    assert rt.snapshot()["pending_choice"] is not None
    rt.reload(parse_text(src, source=str(script)))
    assert rt.snapshot()["pending_choice"] is None


def test_重载找不到当前label时从头开始(tmp_path):
    script = tmp_path / "script.gal"
    _write(script, SCRIPT_V1)
    rt = Runtime()
    rt.load(str(script))
    _play_into_second(rt)
    rt.reload(parse_text("@label 别的\n@ 林晚 新剧本\n@end\n", source=str(script)))
    assert rt.current_label() is None
    assert rt.snapshot()["stack"] == [[0, 0]]


def test_script_files列出include的文件(tmp_path):
    (tmp_path / "a.gal").write_text("@label a\n@ 林晚 A\n@end\n", encoding="utf-8")
    main = tmp_path / "main.gal"
    main.write_text("@include a.gal\n@end\n", encoding="utf-8")
    rt = Runtime()
    rt.load(str(main))
    files = {os.path.basename(p) for p in rt.script_files()}
    assert "main.gal" in files


# ==================== 3. demo._hot_tick 集成 ====================

@pytest.fixture()
def hot_game(tmp_path):
    """真实 tmp 游戏目录 + Runtime/Renderer/UI，模拟 demo 主循环。"""
    script = tmp_path / "script.gal"
    _write(script, SCRIPT_V1)
    rt = Runtime()
    rt.load(str(script))
    _play_into_second(rt)
    ren = Renderer(size=(1280, 720), assets_root=str(tmp_path))
    ui = UI(config=cfgapi.load(str(tmp_path)))
    ui.settings_path = str(tmp_path / "settings.json")
    yield script, rt, ren, ui
    ren.close()


def test_剧本改动后热重载生效(hot_game, tmp_path):
    script, rt, ren, ui = hot_game
    watch = hotload.FileWatch(rt.script_files(), interval_ms=0)
    watch.changed(0)                       # 建立基线
    _write(script, SCRIPT_V2)
    demo._hot_tick(watch, hotload.FileWatch([]), rt, ren, ui,
                   str(script), str(tmp_path), True)
    assert "第二幕第二版。" in json.dumps(rt._lists[0], ensure_ascii=False)
    assert rt.current_label() == "second"  # 从当前场景重播
    assert ren._toast_text == "剧本已重载"


def test_剧本写坏时保留旧版本并提示(hot_game, tmp_path, capsys):
    script, rt, ren, ui = hot_game
    watch = hotload.FileWatch(rt.script_files(), interval_ms=0)
    watch.changed(0)
    _write(script, "@foo 未知指令\n")
    demo._hot_tick(watch, hotload.FileWatch([]), rt, ren, ui,
                   str(script), str(tmp_path), True)
    assert "第二幕第一版。" in json.dumps(rt._lists[0], ensure_ascii=False)  # 旧版本还在
    assert ren._toast_text == "剧本重载失败（见控制台）"
    assert "热重载" in capsys.readouterr().err


def test_配置改动后热重载生效(hot_game, tmp_path):
    script, rt, ren, ui = hot_game
    cfg_path = tmp_path / "config.json"
    _write(cfg_path, json.dumps({"dialogue": {"default": {"height": 200}}}))
    watch = hotload.FileWatch([cfg_path], interval_ms=0)
    watch.changed(0)
    _write(cfg_path, json.dumps({"dialogue": {"default": {"height": 260}},
                                 "font": {"body": 30}}))
    demo._hot_tick(hotload.FileWatch([]), watch, rt, ren, ui,
                   str(script), str(tmp_path), True)
    assert ren.config.dialogue()["height"] == 260
    assert ren._font.get_height() > 0
    assert ren._toast_text == "配置已重载"
    assert ui._config is ren.config
    assert len(ren._text_cache) == 0       # 字体重建后 T8 缓存必须清空


def test_画布尺寸改动拒绝热应用(hot_game, tmp_path):
    script, rt, ren, ui = hot_game
    cfg_path = tmp_path / "config.json"
    _write(cfg_path, json.dumps({"canvas_size": [1920, 1080]}))
    watch = hotload.FileWatch([cfg_path], interval_ms=0)
    watch.changed(0)
    _write(cfg_path, json.dumps({"canvas_size": [1600, 900]}))
    demo._hot_tick(hotload.FileWatch([]), watch, rt, ren, ui,
                   str(script), str(tmp_path), True)
    assert ren.size == (1280, 720)
    assert ren._toast_text == "画布尺寸变更需重启"


# ==================== 4. Renderer.apply_config / UI.set_config ====================

def test_apply_config重建字体并清缓存(tmp_path):
    (tmp_path / "config.json").write_text(
        json.dumps({"font": {"body": 20}}), encoding="utf-8")
    ren = Renderer(size=(1280, 720), assets_root=str(tmp_path))
    try:
        ren._font_width(ren._font, "缓存一条")     # 制造缓存条目
        assert len(ren._text_width_cache) > 0
        (tmp_path / "config.json").write_text(
            json.dumps({"font": {"body": 34}}), encoding="utf-8")
        assert ren.apply_config(cfgapi.load(str(tmp_path))) is True
        assert ren._font.get_height() > 20          # 字号变大
        ren._font_width(ren._font, "缓存一条")       # 新字体重新量宽，不命中旧 id
        assert len(ren._text_width_cache) == 1
    finally:
        ren.close()


def test_apply_config画布变更返回False(tmp_path):
    ren = Renderer(size=(1280, 720), assets_root=str(tmp_path))
    try:
        (tmp_path / "config.json").write_text(
            json.dumps({"canvas_size": [1920, 1080]}), encoding="utf-8")
        assert ren.apply_config(cfgapi.load(str(tmp_path))) is False
        assert ren.size == (1280, 720)              # 旧画布保持不变
    finally:
        ren.close()


def test_set_config刷新skip策略(tmp_path):
    ui = UI(config=cfgapi.Config())
    assert ui.skip_allowed is True                  # 2026-11-02：默认开启（viewed 仅跳已读）
    (tmp_path / "config.json").write_text(
        json.dumps({"skip": {"enabled": True, "mode": "all"}}), encoding="utf-8")
    ui.set_config(cfgapi.load(str(tmp_path)))
    assert ui.skip_allowed is True
    assert ui.skip_mode == "all"
    (tmp_path / "config.json").write_text(
        json.dumps({"skip": {"enabled": False}}), encoding="utf-8")
    ui.set_config(cfgapi.load(str(tmp_path)))
    assert ui.skip_allowed is False


# ==================== 5. toast ====================

def test_toast显示与过期(tmp_path):
    ren = Renderer(size=(1280, 720), assets_root=str(tmp_path))
    try:
        ren.toast("剧本已重载")
        assert ren._toast_text == "剧本已重载"
        ren._draw_toast()                           # 不崩、有画
        assert ren._toast_until > ren._now_ms()
        ren._toast_until = 0
        before = ren._screen.copy()
        ren._draw_toast()                           # 过期后不画
        assert pygame.image.tobytes(before, "RGBA") == \
            pygame.image.tobytes(ren._screen, "RGBA")
    finally:
        ren.close()
