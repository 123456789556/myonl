# -*- coding: utf-8 -*-
"""玩家侧全交互走查：按真实玩家操作顺序驱动键盘/鼠标，逐屏截图并断言。

做法（不伪造截图）：
- 无头窗口（SDL dummy），真实 Renderer + Runtime + UI；
- 每个操作都先 post 真实 pygame 事件，再走 Renderer.handle_input()，
  键盘键位映射、鼠标命中检测、UI 状态机、业务动作全部按正式主循环执行；
- 每一步截图后立刻断言「当前模式 / 光标 / 数值 / 存档文件」等可验证结果；
- 最后生成 screenshots/walkthrough/report.html（含交互顺序图与逐步截图）
  与 walkthrough.gif（按操作顺序的动图）。

用法：
    py -3 tools/ui_walkthrough.py

退出码 0 = 全部断言通过；1 = 有失败项（中文清单打印在末尾）。
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pygame  # noqa: E402

from engine import save as save_api  # noqa: E402
from engine.config import load as load_config  # noqa: E402
from engine.data import (load_gallery_config, load_settings,  # noqa: E402
                         save_settings)
from engine.demo import (_apply_business, _is_ui_key, _read_script_title,  # noqa: E402
                         _step)
from engine.renderer import Renderer  # noqa: E402
from engine.runtime import Runtime  # noqa: E402
from engine.ui import UI  # noqa: E402

# 素材：作品示例《星海回声》——带 CG、选项、转场、镜头与画廊门控，覆盖面最全
SRC_GAME = ROOT / "作品" / "副产物" / "作品示例" / "星海回声"
OUT = ROOT / "screenshots" / "walkthrough"


class Walk:
    """走查驱动器：一帧 = 推进时钟 → 取快照 → 渲染；一个操作 = 真实事件 → 主循环分发。"""

    def __init__(self, game_root: Path, out_dir: Path):
        self.game = game_root
        self.out = out_dir
        self.script = str(game_root / "script.gal")
        self.settings_path = str(game_root / "settings.json")
        self.clock = 2000
        self.steps: list[dict] = []
        self.failures: list[str] = []
        self.quit = False
        self.loaded = False
        self._state: dict = {}
        self._view: dict = {}
        self._dirty = True
        self._hover_override = None  # 截图/点击时把鼠标"按"在指定画布坐标
        self.gif_frames: list = []

        self.rt = Runtime()
        self.ren = Renderer((1280, 720), str(game_root))
        self.ren._now_ms = self._now  # 可控时钟：淡入/打字机/幻灯片才能稳定复现
        self.ui = UI(config=load_config(str(game_root)))
        self.ui.settings_path = self.settings_path
        self.ui.set_gallery_config(load_gallery_config(str(game_root)))
        self.ui.set_script_title(_read_script_title(self.script))
        self.ui.refresh()
        self.ui.mode = "title"

    # ---------------- 基础 ----------------

    def _now(self) -> int:
        return self.clock

    def tick(self, ms: int = 16) -> None:
        self.clock += ms

    @property
    def view(self) -> dict:
        """当前 UI 视图；有未落地的操作时先补一帧（断言读到的永远是最新状态）。"""
        if self._dirty:
            self.frame()
        return self._view

    @property
    def state(self) -> dict:
        """当前 GameState 快照；同样保证最新。"""
        if self._dirty:
            self.frame()
        return self._state

    def frame(self, ms: int = 16) -> None:
        self.tick(ms)
        self._state = self.rt.snapshot() if self.loaded else {}
        self.ui.set_history(self._state.get("history"))
        if self.loaded:
            self.ui.set_gallery(save_api.gallery_union(self._state.get("gallery") or []),
                                self.rt.seen_sprites())
        self._view = self.ui.view(now_ms=self.ren._now_ms())
        real = pygame.mouse.get_pos
        if self._hover_override is not None:
            wpos = self._window_pos(self._hover_override)
            pygame.mouse.get_pos = lambda: wpos
        try:
            self.ren.render(self._state, self._view)
        finally:
            pygame.mouse.get_pos = real
        self._dirty = False

    def expect(self, cond, desc: str) -> bool:
        ok = bool(cond)
        if not ok:
            self.failures.append(desc)
        return ok

    def _settle_visual(self, max_ms: int = 4000, step: int = 100) -> None:
        """截图前把仍在播放的转场/背景淡入推完，避免新旧两帧叠加在截图里。"""
        waited = 0
        while waited < max_ms and (self.ren._trans_old is not None
                                   or self.ren._fade_t0 is not None):
            self.frame(step)
            waited += step

    def shot(self, name: str, action: str, expect: str, checks=()) -> None:
        """渲染并保存当前帧；checks = [(断言描述, 布尔/可调用)]。"""
        self._settle_visual()
        self.frame()
        path = self.out / name
        pygame.image.save(self.ren._screen, str(path))
        results = [{"desc": d, "ok": bool(v() if callable(v) else v)} for d, v in checks]
        for r in results:
            if not r["ok"]:
                self.failures.append(f"{name}：{r['desc']}")
        self.steps.append({
            "file": name,
            "action": action,
            "expect": expect,
            "mode": self._view.get("mode"),
            "ok": all(r["ok"] for r in results),
            "checks": results,
        })
        try:
            from PIL import Image
            self.gif_frames.append(Image.open(path).convert("RGB"))
        except Exception:  # noqa: BLE001 — 没装 Pillow 时只是没有动图
            pass

    # ---------------- 事件 ----------------

    def _window_pos(self, canvas_pos) -> tuple:
        """逻辑画布坐标 → 窗口坐标（走一遍真实缩放/黑边换算）。"""
        v = self.ren._view
        lw, lh = self.ren.size
        if v.width <= 0 or v.height <= 0:
            return (int(canvas_pos[0]), int(canvas_pos[1]))
        return (int(v.x + canvas_pos[0] * v.width / lw),
                int(v.y + canvas_pos[1] * v.height / lh))

    def _post(self, event) -> dict:
        pygame.event.clear()
        pygame.event.post(event)
        act = self.ren.handle_input()
        self._dispatch(act)
        self.tick(20)
        self._dirty = True
        return act

    def key(self, name: str) -> dict:
        code = getattr(pygame, name)
        return self._post(pygame.event.Event(
            pygame.KEYDOWN, key=code, unicode="", mod=0, scancode=0))

    def _dispatch(self, act: dict) -> None:
        action = act.get("action")
        if action in (None, "none", "reveal"):
            return
        if action in ("settings_set_key", "settings_set"):
            self._business(act)  # renderer 直接捕获的改键/滑条动作
            return
        if action == "advance":
            if not self.loaded:
                return
            if self.rt.pending_wait_seconds() > 0:
                self.rt.advance_wait(999.0)
            else:
                _step(self.rt, self.ren)
            return
        if action == "choose":
            try:
                self.rt.choose(act["index"])
            except Exception as e:  # noqa: BLE001 — 选项异常不崩
                self.failures.append(f"选项执行失败：{e}")
            return
        if action == "quit":
            self.quit = True
            return
        if _is_ui_key(action):
            self._business(self.ui.handle(action))

    def _business(self, business) -> None:
        if not isinstance(business, dict):
            return
        status = _apply_business(business, self.rt, self.ren, self.ui,
                                 self.script, self.settings_path)
        if status == "loaded":
            self.loaded = True
        elif status == "unloaded":
            self.loaded = False
        self._dirty = True

    def click(self, pred, desc: str, pos=None) -> dict:
        """点击命中的 UI 区域：先渲染收集命中区，再走 _ui_hit_at 校验后派发。"""
        self.frame()
        match = None
        for rect, payload in self.ren._ui_hits:
            if pred(payload):
                match = (rect, payload)
                break
        if match is None:
            self.failures.append(f"点击失败：找不到目标区域（{desc}）")
            return {"action": "none"}
        rect, _payload = match
        return self._click_canvas(pos or rect.center, desc)

    def _click_canvas(self, canvas_pos, desc: str) -> dict:
        self.frame()
        wpos = self._window_pos(canvas_pos)
        hit = self.ren._ui_hit_at(self.ren._to_canvas(wpos))
        if hit is None:
            self.failures.append(f"点击失败：命中检测为空（{desc} @ {canvas_pos}）")
            return {"action": "none"}
        act = self._post(pygame.event.Event(
            pygame.MOUSEBUTTONDOWN, pos=wpos, button=1, touch=False))
        # ▼ 播放推进等控件会直接返回 advance/reveal，其余 UI 控件返回 click
        self.expect(act.get("action") in ("click", "advance", "reveal", "choose"),
                    f"点击应有响应（{desc}，实际 {act.get('action')}）")
        if act.get("action") == "click":
            business = self.ui.click(act.get("hit"), pos=act.get("pos"))
            self._business(business)
        # 抬起鼠标（复位按住状态）
        pygame.event.clear()
        pygame.event.post(pygame.event.Event(
            pygame.MOUSEBUTTONUP, pos=wpos, button=1, touch=False))
        self.ren.handle_input()
        self.tick(20)
        self._dirty = True
        return act

    def hover(self, canvas_pos) -> None:
        """让鼠标悬停到画布坐标（悬停态只影响绘制，不产生业务动作）。"""
        self._hover_override = canvas_pos
        try:
            self.frame()
        finally:
            self._hover_override = None

    def shot_hover(self, canvas_pos, name: str, action: str, expect: str, checks=()) -> None:
        """悬停状态下截图（快捷栏等「hover 才显现」的控件）。"""
        self._hover_override = canvas_pos
        try:
            self.shot(name, action, expect, checks)
        finally:
            self._hover_override = None

    def quickbar_point(self) -> tuple:
        lay = self.ren._quickbar_layout(6)
        total = 6 * (lay["bw"] + lay["gap"]) - lay["gap"]
        return (lay["x0"] + total - 4, lay["y0"] + lay["bh"] // 2)

    def click_quickbar(self, index: int, desc: str) -> dict:
        """快捷栏默认隐藏：先按住 hover 让按钮显现并登记命中区，再点击。"""
        self._hover_override = self.quickbar_point()
        try:
            return self.click(lambda p: p.get("kind") == "quickbar" and p.get("index") == index,
                              desc)
        finally:
            self._hover_override = None


def _prepare_game(tmp_root: Path) -> Path:
    """复制作品到临时目录并补标题（不改动原工程与真实存档）。"""
    game = tmp_root / "星海回声"
    shutil.copytree(SRC_GAME, game,
                    ignore=shutil.ignore_patterns("saves", "__pycache__"))
    settings = load_settings(str(game / "settings.json"))
    settings.update({"title": "星海回声", "splash": False, "title_text_visible": True})
    save_settings(settings, str(game / "settings.json"))
    return game


def _run(w: Walk) -> None:
    ui = w.ui
    rt = w.rt

    # ==================== 一、标题画面 ====================
    w.shot("01_title.png", "启动游戏", "标题画面 + 六项菜单；无存档时「继续」灰置",
           [("模式=title", w.view["mode"] == "title"),
            ("光标在开始新游戏", w.view["cursor"] == 0),
            ("无存档：继续灰置", w.view["items"][1]["enabled"] is False)])

    for _ in range(3):
        w.key("K_DOWN")
    w.shot("02_title_keyboard.png", "按 ↓ 三次", "键盘焦点移到「设置」，左缘主题色竖线跟随",
           [("光标=3（设置）", w.view["cursor"] == 3)])

    # 鼠标悬停反馈（标题项 hover 才出现细边框）
    w.frame()
    item0 = next(rect for rect, p in w.ren._ui_hits
                 if p.get("kind") == "item" and p.get("index") == 0)
    w.hover(item0.center)
    w.shot("03_title_hover.png", "鼠标移到「开始新游戏」", "悬停项出现主题色细边框",
           [("命中=item 0", (w.ren._ui_hit_at(item0.center) or {}).get("index") == 0)])

    # 标题 → 画廊（空）→ Esc 回标题（验证返回层级）
    w.click(lambda p: p.get("kind") == "item" and p.get("index") == 4, "标题-画廊")
    w.shot("04_gallery_empty.png", "点击「画廊」（尚未解锁 CG）", "固定格子全部灰锁，Esc 可回标题",
           [("模式=gallery", w.view["mode"] == "gallery"),
            ("有固定格子", bool((w.view.get("gallery") or {}).get("items"))),
            ("全部未解锁", all(not it.get("unlocked")
                              for it in (w.view.get("gallery") or {}).get("items") or []))])
    w.key("K_ESCAPE")
    w.shot("05_title_back.png", "按 Esc 返回", "回到标题（不是钻进游戏内菜单）",
           [("模式=title", w.view["mode"] == "title")])

    # ==================== 二、设置页 ====================
    w.click(lambda p: p.get("kind") == "item" and p.get("index") == 3, "标题-设置")
    w.shot("06_settings_basic.png", "点击「设置」", "设置页：左侧分组导航 + 右侧当前分组项",
           [("模式=settings", w.view["mode"] == "settings"),
            ("默认在基础组", w.view.get("settings_tab") == 0),
            ("分组数>=4", len(w.view.get("settings_groups") or []) >= 4)])

    # 点击左侧「音频」分组
    w.click(lambda p: p.get("kind") == "settings_nav" and p.get("index") == 1,
            "设置-音频分组")
    w.shot("07_settings_audio.png", "点击左侧「音频」", "切到音频分组，光标落到组首项",
           [("分组页=1（音频）", w.view.get("settings_tab") == 1)])

    # 音量滑条：按住拖动到 35%（真实 MOUSEBUTTONDOWN + MOUSEMOTION）
    w.frame()
    slider = next((rect, p) for rect, p in w.ren._ui_hits
                  if p.get("kind") == "settings_slider" and p.get("key") == "bgm_volume")
    srect, spay = slider
    bar_x, bar_w = spay["bar"]
    start = (int(bar_x + bar_w * 0.6), srect.centery)
    target = (int(bar_x + bar_w * 0.35), srect.centery)
    pygame.event.clear()
    pygame.event.post(pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, pos=w._window_pos(start), button=1, touch=False))
    down = w.ren.handle_input()
    w.expect((down.get("hit") or {}).get("kind") == "settings_slider",
             "按下滑条应命中 settings_slider")
    w._business(ui.click(down.get("hit"), pos=down.get("pos")))
    pygame.event.clear()
    pygame.event.post(pygame.event.Event(
        pygame.MOUSEMOTION, pos=w._window_pos(target), rel=(0, 0), buttons=(1, 0, 0)))
    drag = w.ren.handle_input()
    w.expect(drag.get("action") == "drag", "按住移动应产生 drag 动作")
    w._business(ui.click(drag.get("hit"), pos=drag.get("pos")))
    pygame.event.clear()
    pygame.event.post(pygame.event.Event(
        pygame.MOUSEBUTTONUP, pos=w._window_pos(target), button=1, touch=False))
    w.ren.handle_input()
    w._dirty = True
    w.shot("08_settings_slider.png", "拖动「音乐音量」滑条到 35%", "滑条实时跟随并落盘",
           [("音乐音量≈0.35", abs(float(ui._settings.get("bgm_volume", -1)) - 0.35) <= 0.02)])

    # 键盘跨分组：连续 ↓ 从音频末项跨到语音组
    w.key("K_DOWN")
    w.key("K_DOWN")
    w.shot("09_settings_cross_page.png", "按 ↓ 两次跨分组", "到底自动跨到「语音」分组首页",
           [("分组页=2（语音）", w.view.get("settings_tab") == 2)])

    # 点「键位」分组 → 改键捕获 → 按 W → 恢复默认
    groups = w.view.get("settings_groups") or []
    w.click(lambda p: p.get("kind") == "settings_nav" and p.get("index") == 15,
            "设置-键位分组")
    w.shot("10_settings_keys.png", "点击左侧「键位」", "显示 6 个可改键项",
           [("分组页=末组（键位）", w.view.get("settings_tab") == len(groups) - 1)])

    w.key("K_RETURN")
    w.shot("11_settings_capture.png", "在「上」按回车", "进入「请按键…」捕获态",
           [("捕获键=key_up", ui.capturing == "key_up"),
            ("视图暴露捕获态", w.view.get("capturing") == "key_up")])

    w.key("K_w")
    w.shot("12_settings_rebind.png", "按 W 完成改键", "「上」绑定为 W 并立即写盘",
           [("key_up=w", str(ui._settings.get("key_up")) == "w")])

    w.key("K_RETURN")
    w.key("K_ESCAPE")  # 捕获态按 Esc = 恢复默认
    w.expect(str(ui._settings.get("key_up") or "") == "", "改键后 Esc 应恢复默认")
    w.key("K_ESCAPE")
    w.shot("13_title_after_settings.png", "Esc 返回标题", "设置持久化，回到标题",
           [("模式=title", w.view["mode"] == "title"),
            ("音量仍是 0.35", abs(float(ui._settings.get("bgm_volume", -1)) - 0.35) <= 0.02)])

    # ==================== 三、读档页（空） ====================
    w.click(lambda p: p.get("kind") == "item" and p.get("index") == 2, "标题-读档")
    w.shot("14_slots_load_empty.png", "点击「读档」（无存档）", "10 个空档位全部灰置不可选",
           [("模式=slots", w.view["mode"] == "slots"),
            ("用途=load", w.view.get("slots_mode") == "load"),
            ("10 格", len(w.view.get("slots") or []) == 10),
            ("全部灰置", all(not r["enabled"] for r in w.view.get("slots") or []))])
    w.click(lambda p: p.get("kind") == "item" and p.get("index") == 0, "空档位")
    w.expect(w.view["mode"] == "slots", "点击空档位不应进入读档")
    w.key("K_ESCAPE")

    # ==================== 四、开始新游戏 ====================
    w.click(lambda p: p.get("kind") == "item" and p.get("index") == 0, "开始新游戏")
    # 背景淡入 2.5s：先把淡入推完再截「首句正在打出」，避免截到全黑一帧
    w._settle_visual()
    w.ren._tw_shown = 1.0
    w._dirty = True
    w.shot("15_game_first_line.png", "点击「开始新游戏」", "立即出现第一句台词（不再先给空画面）",
           [("模式=playing", w.view["mode"] == "playing"),
            ("已有第一句", len(w.state.get("history") or []) == 1)])

    w.key("K_SPACE")  # 第一下：打字机一次性补完
    w.shot("16_dialogue_revealed.png", "按空格（打字机未完）", "本句全文立即显示，不再逐字等待",
           [("打字机已完成", w.ren.typewriter_complete())])

    w.key("K_SPACE")  # 第二下：推进到下一句
    w.shot("17_dialogue_next.png", "再按空格", "推进到下一句，历史累加",
           [("历史>=2", len(w.state.get("history") or []) >= 2)])

    # 鼠标点对话框底部 ▼：与空格同一条「补完打字机 → 推进」逻辑
    before_n = len(w.state.get("history") or [])
    for _ in range(5):  # 中间可能夹 @wait，按到出现新台词为止
        w.click(lambda p: p.get("kind") == "next_arrow", "对话框 ▼")
        if len(w.rt.snapshot().get("history") or []) > before_n:
            break
    w.shot("17b_next_arrow.png", "点击对话框底部 ▼", "鼠标点 ▼ 也能推进到下一句",
           [("历史已增加", len(w.state.get("history") or []) > before_n)])

    # 回看（↑）→ 点击任意处关闭
    w.key("K_UP")
    w.shot("18_backlog.png", "按 ↑ 打开回看", "回看面板列出已读台词",
           [("模式=backlog", w.view["mode"] == "backlog"),
            ("回看有内容", bool(w.view.get("history")))])
    w._click_canvas((640, 360), "回看-点击任意处")
    w.expect(w.view["mode"] == "playing", "点击回看面板应关闭回看")

    # 截图模式 Insert：隐藏全部 UI，再按恢复
    w.key("K_INSERT")
    w.shot("19_ui_hidden.png", "按 Insert", "隐藏对话框/快捷栏，只留干净画面",
           [("UI 已隐藏", w.ren._ui_hidden is True)])
    w.key("K_INSERT")
    w.expect(w.ren._ui_hidden is False, "再按 Insert 应恢复 UI")

    # 快捷栏 hover 显现 + AUTO 开关
    w.shot_hover(w.quickbar_point(), "20_quickbar_hover.png", "鼠标移到快捷栏带区",
                 "SAVE/LOAD/LOG/AUTO/SKIP/CONFIG 显现",
                 [("快捷栏命中 6 个", lambda: sum(1 for _r, p in w.ren._ui_hits
                                                 if p.get("kind") == "quickbar") == 6)])
    w.click_quickbar(3, "快捷栏-AUTO")
    w.shot("21_auto_on.png", "点击 AUTO", "自动播放开启，按钮高亮常驻",
           [("auto_on", ui.auto_on is True)])
    w.click_quickbar(3, "快捷栏-AUTO 关闭")
    w.expect(ui.auto_on is False, "再点 AUTO 应关闭自动播放")

    # F5 快速存档（独立 quick 槽）
    w.key("K_F5")
    quick_file = Path(save_api.saves_dir()) / "slot_quick.json"
    w.shot("22_quicksave.png", "按 F5 快速存档", "写入独立快存位并弹出提示",
           [("快存文件存在", quick_file.is_file())])

    # ==================== 五、存档 / 读档 ====================
    w.click_quickbar(0, "快捷栏-SAVE")
    w.shot("23_slots_save.png", "点击快捷栏 SAVE", "打开 10 格存档网格（全部可选）",
           [("模式=slots", w.view["mode"] == "slots"),
            ("用途=save", w.view.get("slots_mode") == "save"),
            ("全部可选", all(r["enabled"] for r in w.view.get("slots") or []))])
    w.key("K_2")  # 数字键直选第 2 格
    w.shot("24_slot_saved.png", "按数字键 2", "存入存档 2，卡片显示时间/章节/末句",
           [("存档 2 文件存在", (Path(save_api.saves_dir()) / "slot_2.json").is_file()),
            ("存档 2 有缩略图", any(e["slot"] == "2" and e.get("thumbnail_path")
                                    for e in save_api.list_slots()))])
    w.key("K_ESCAPE")
    w.shot("25_back_to_game.png", "按 Esc 返回游戏", "回到剧情画面，进度不丢",
           [("模式=playing", w.view["mode"] == "playing")])

    w.click_quickbar(1, "快捷栏-LOAD")
    w.shot("26_slots_load.png", "点击快捷栏 LOAD", "有存档的格子可选，空位灰置",
           [("模式=slots", w.view["mode"] == "slots"),
            ("用途=load", w.view.get("slots_mode") == "load"),
            ("第 2 格可选", (w.view.get("slots") or [])[1]["enabled"] is True),
            ("第 1 格灰置", (w.view.get("slots") or [])[0]["enabled"] is False)])
    w.key("K_2")
    w.shot("27_slot_loaded.png", "按数字键 2 读档", "读档成功回到游戏画面",
           [("模式=playing", w.view["mode"] == "playing"),
            ("历史已恢复", bool(w.state.get("history")))])

    # ==================== 六、选项分支 ====================
    for _ in range(80):
        if w.state.get("pending_choice") or w.state.get("finished"):
            break
        w.key("K_SPACE")
    w.shot("28_choices.png", "推进到选项", "两个分支选项，默认高亮第一项",
           [("有待选分支", bool(w.state.get("pending_choice"))),
            ("渲染层拿到选项", bool(w.ren._options))])

    # 选项锁：选项刚出现时的误触被忽略，锁定结束后再点才生效
    w.ren._choice_key = None  # 让渲染层把它当成"刚出现的新选项组"重新起锁
    w.frame()
    first_rect = w.ren._choice_rects[0][0]
    before = w.rt.snapshot().get("pending_choice")
    w.tick(40)  # 起锁有 30ms 延迟，跨过之后再点即落在锁定窗口内
    w._post(pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                               pos=w._window_pos(first_rect.center), button=1,
                               touch=False))
    w.expect(w.rt.snapshot().get("pending_choice") == before,
             "选项刚出现时的点击应被锁定期忽略")
    w.tick(400)
    w._post(pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                               pos=w._window_pos(first_rect.center), button=1,
                               touch=False))
    w.shot("29_branch_selected.png", "锁定结束后点击第一个选项", "进入「等流星」分支",
           [("分支已选定", w.rt.snapshot().get("pending_choice") is None)])

    # ==================== 七、CG 与画廊 ====================
    for _ in range(80):
        if w.ren._cg_showing is not None or w.state.get("finished"):
            break
        w.key("K_SPACE")
    w.shot("30_cg.png", "推进到 CG", "CG 全屏展示，按空格/点击继续",
           [("CG 正在展示", w.ren._cg_showing is not None)])
    w.key("K_SPACE")
    w.shot("31_after_cg.png", "按空格关闭 CG", "回到剧情并推进一句",
           [("CG 已关闭", w.ren._cg_showing is None)])

    w.key("K_ESCAPE")
    w.shot("32_menu.png", "按 Esc 打开游戏内菜单", "存档/读档/画廊/回标题/设置/退出",
           [("模式=menu", w.view["mode"] == "menu"),
            ("6 项", len(w.view.get("items") or []) == 6)])

    w.click(lambda p: p.get("kind") == "item" and p.get("index") == 2, "菜单-画廊")
    gv = w.view.get("gallery") or {}
    unlocked = [it.get("unlocked") for it in gv.get("items") or []]
    w.shot("33_gallery_grid.png", "点击「画廊」", "固定格子：已解锁 CG 亮、未解锁灰锁",
           [("模式=gallery", w.view["mode"] == "gallery"),
            ("至少 1 格解锁", any(unlocked)),
            ("存在未解锁格", any(not u for u in unlocked))])
    w.click(lambda p: p.get("kind") == "item" and p.get("index") == 0, "画廊-CG 格")
    w.shot("34_gallery_detail.png", "点击已解锁 CG", "进入大图鉴赏（可轮播）",
           [("详情名=cg_star", (w.view.get("gallery") or {}).get("detail") == "cg_star"),
            ("轮播图非空", bool((w.view.get("gallery") or {}).get("detail_images")))])
    w.key("K_RIGHT")
    w.shot("35_gallery_slide.png", "按 → 切换幻灯片", "大图切到下一张",
           [("轮播下标=1", (w.view.get("gallery") or {}).get("detail_index") == 1)])
    w.key("K_ESCAPE")
    w.expect(w.view["mode"] == "gallery", "Esc 应先关闭大图回到网格")
    w.key("K_ESCAPE")
    w.shot("36_back_to_menu.png", "再按 Esc", "返回游戏内菜单（不是标题）",
           [("模式=menu", w.view["mode"] == "menu")])

    w.click(lambda p: p.get("kind") == "item" and p.get("index") == 4, "菜单-设置")
    w.shot("37_settings_from_menu.png", "点击「设置」", "游戏内设置页，Esc 回菜单",
           [("模式=settings", w.view["mode"] == "settings")])
    w.key("K_ESCAPE")
    w.expect(w.view["mode"] == "menu", "设置 Esc 应回游戏内菜单")

    w.click(lambda p: p.get("kind") == "item" and p.get("index") == 3, "菜单-回标题")
    w.shot("38_title_with_saves.png", "点击「回标题」", "回到标题；有存档后「继续」可选",
           [("模式=title", w.view["mode"] == "title"),
            ("继续已可选", w.view["items"][1]["enabled"] is True)])

    # ==================== 八、继续游戏 → 终幕 ====================
    w.click(lambda p: p.get("kind") == "item" and p.get("index") == 1, "标题-继续")
    w.shot("39_continue_game.png", "点击「继续」", "读取最近存档继续游玩",
           [("模式=playing", w.view["mode"] == "playing"),
            ("历史已恢复", bool(w.state.get("history")))])

    for _ in range(300):
        st = w.rt.snapshot()
        if st.get("finished"):
            break
        if st.get("pending_choice"):
            for i, o in enumerate(st["pending_choice"].get("options") or []):
                if o.get("available"):
                    w.rt.choose(i)
                    break
            continue
        w.key("K_SPACE")
    w.frame()
    w.shot("40_ending_hint.png", "推进到剧本结束", "终幕停留 + 右下角「即将返回标题」提示",
           [("已结束", w.state.get("finished") is True)])
    w.ren.trigger_ending_fade()
    w.tick(1600)
    w.frame()
    w.shot("41_ending_fade.png", "停留结束", "画面淡出，准备回标题",
           [("淡出已触发", w.ren._ending_fade_t0 is not None
             or w.ren._ending_fade_done is True)])
    w.loaded = False
    w.ui.mode = "title"
    # 模拟 demo 主循环：淡出完成后复位遮罩状态，否则标题会被残留黑幕盖住
    w.ren._ending_fade_t0 = None
    w.ren._ending_fade_done = False
    w._dirty = True
    w.shot("42_title_final.png", "回到标题", "标题画面，可继续新一轮",
           [("模式=title", w.view["mode"] == "title")])


def _write_report(w: Walk, elapsed: float) -> Path:
    total = len(w.steps)
    passed = sum(1 for s in w.steps if s["ok"])
    rows = []
    for i, s in enumerate(w.steps, 1):
        cls = "ok" if s["ok"] else "bad"
        mark = "通过" if s["ok"] else "失败"
        checks = "；".join(("✓ " if c["ok"] else "✗ ") + c["desc"] for c in s["checks"])
        rows.append(f"""
        <article class="step {cls}">
          <div class="no">{i:02d}</div>
          <div class="body">
            <div class="act">{s['action']}</div>
            <div class="exp">{s['expect']}</div>
            <div class="meta">模式 {s['mode']} · {mark}{(' · ' + checks) if checks else ''}</div>
            <a href="{s['file']}" target="_blank"><img src="{s['file']}" loading="lazy" alt="{s['action']}"></a>
          </div>
        </article>""")
    flow = "<i>›</i>".join(
        f"<span title=\"{s['expect']}\">{i:02d} {s['action']}</span>"
        for i, s in enumerate(w.steps, 1))
    fixes = [
        "点「开始新游戏」后先看到空画面，要再按一次空格才出现第一句 → 加载后立即推进到首句",
        "标题 → 画廊 → Esc 会钻进「游戏内菜单」→ 记住来路，返回标题",
        "游戏中快捷栏 / ◀ 回看 / ▼ 推进看得见却点不动（鼠标只被当成推进剧情）→ 命中后再判定语义",
        "存档页 10 格只画出 3 格（行列写反 + 越界 break）→ 5×2 全部可见、可点",
        "方向键左右在真实主循环里被丢弃 → 存档九宫格、画廊页签/轮播都能左右操作",
    ]
    fix_items = "".join(f"<li>{x}</li>" for x in fixes)
    html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>MYONL 全交互走查报告</title>
<style>
  :root {{ color-scheme: dark; }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; background: #0d1017; color: #e6ebf5;
         font: 15px/1.6 "Microsoft YaHei", system-ui, sans-serif; }}
  header {{ padding: 40px 48px 24px; border-bottom: 1px solid #222a3a;
            background: radial-gradient(900px 300px at 20% 0, #1b2740, transparent); }}
  h1 {{ margin: 0 0 8px; font-size: 28px; letter-spacing: .5px; }}
  .sub {{ color: #93a0b8; }}
  .stats {{ display: flex; gap: 14px; margin-top: 22px; flex-wrap: wrap; }}
  .stat {{ background: #141a26; border: 1px solid #222a3a; border-radius: 12px;
           padding: 12px 18px; min-width: 130px; }}
  .stat b {{ display: block; font-size: 24px; color: #8ab4ff; }}
  .stat span {{ color: #8492ab; font-size: 13px; }}
  main {{ padding: 28px 48px 80px; max-width: 1180px; margin: 0 auto; }}
  h2 {{ font-size: 18px; margin: 34px 0 14px; color: #cfe0ff; }}
  .flow {{ display: flex; flex-wrap: wrap; gap: 6px; align-items: center;
           background: #121826; border: 1px solid #222a3a; border-radius: 12px;
           padding: 14px 16px; }}
  .flow span {{ display: inline-flex; padding: 5px 11px; border-radius: 999px;
                background: #1e2940; color: #9fb6dd; font-size: 12px; }}
  .flow i {{ color: #45516a; font-style: normal; font-size: 14px; }}
  .fixes {{ background: #111722; border: 1px solid #1f2735; border-radius: 12px;
            padding: 14px 22px 14px 38px; color: #b9c6da; }}
  .fixes li {{ margin: 6px 0; }}
  .step {{ display: grid; grid-template-columns: 52px 1fr; gap: 16px;
           background: #111722; border: 1px solid #1f2735; border-radius: 14px;
           padding: 16px 18px; margin-bottom: 14px; }}
  .step.bad {{ border-color: #5c2a3a; background: #1b1218; }}
  .no {{ font: 600 18px/1.2 ui-monospace, monospace; color: #6f7f9c; }}
  .step.ok .no {{ color: #5fd0a0; }}
  .step.bad .no {{ color: #ff8fa3; }}
  .act {{ font-weight: 700; font-size: 16px; }}
  .exp {{ color: #a9b6cc; margin-top: 2px; }}
  .meta {{ color: #7d8ba5; font-size: 13px; margin: 6px 0 10px; }}
  img {{ width: 100%; border-radius: 10px; border: 1px solid #263144;
         display: block; background: #000; }}
  .gif {{ width: 100%; border-radius: 12px; border: 1px solid #263144; }}
  footer {{ color: #6d7a92; font-size: 12px; padding: 0 48px 40px; }}
</style></head><body>
<header>
  <h1>MYONL 全交互走查报告</h1>
  <div class="sub">真实事件驱动（pygame KEYDOWN / MOUSEBUTTONDOWN · MOUSEMOTION）→ Renderer.handle_input → UI 状态机 → 业务动作</div>
  <div class="stats">
    <div class="stat"><b>{passed}/{total}</b><span>步骤通过</span></div>
    <div class="stat"><b>{len(w.failures)}</b><span>失败断言</span></div>
    <div class="stat"><b>{elapsed:.1f}s</b><span>走查耗时</span></div>
    <div class="stat"><b>1280×720</b><span>逻辑画布</span></div>
  </div>
</header>
<main>
  <h2>交互顺序</h2>
  <div class="flow">{flow}</div>
  <h2>本次修掉的交互问题</h2>
  <ul class="fixes">{fix_items}</ul>
  <h2>动态走查</h2>
  <img class="gif" src="walkthrough.gif" alt="交互流程动图">
  <h2>逐屏证据</h2>
  {''.join(rows)}
</main>
<footer>生成时间 {time.strftime('%Y-%m-%d %H:%M:%S')} · 素材：作品示例《星海回声》（临时副本，未改动原工程）</footer>
</body></html>"""
    path = w.out / "report.html"
    path.write_text(html, encoding="utf-8")
    return path


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.png"):
        old.unlink()
    tmp_root = Path(tempfile.mkdtemp(prefix="myonl_walk_"))
    save_api.set_saves_dir(str(tmp_root / "saves"))
    game = _prepare_game(tmp_root)
    t0 = time.perf_counter()
    w = Walk(game, OUT)
    try:
        _run(w)
    finally:
        elapsed = time.perf_counter() - t0
        gif_path = OUT / "walkthrough.gif"
        if w.gif_frames:
            try:
                from PIL import Image
                frames = [f.resize((640, 360)) for f in w.gif_frames]
                frames[0].save(str(gif_path), save_all=True, append_images=frames[1:],
                               duration=1200, loop=0, optimize=True)
            except Exception as e:  # noqa: BLE001
                print(f"[动图] 生成失败：{e}", file=sys.stderr)
        report = _write_report(w, elapsed)
        w.ren.close()
        save_api.reset_saves_dir()
        shutil.rmtree(tmp_root, ignore_errors=True)

    passed = sum(1 for s in w.steps if s["ok"])
    print(f"走查完成：{passed}/{len(w.steps)} 步通过，{len(w.failures)} 条失败断言")
    print(f"报告：{report}")
    print(f"动图：{gif_path if gif_path.is_file() else '（未生成）'}")
    if w.failures:
        print("失败项：")
        for f in w.failures:
            print("  -", f)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
