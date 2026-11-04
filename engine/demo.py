"""MYONL 集成主循环：runtime + renderer 串起来，能开窗口跑剧本。

用法：
    python -m engine.demo 剧本.gal [--assets 资源根] [--max-frames N] [--auto] [--profile]

资源缺失预检（业界经验 B 条）：load 剧本后、进入主循环前，扫描全部指令引用的
图片/音频，缺失的不崩不阻塞，打印中文缺失清单（带行号）到 stderr。

主循环前置一层玩家外壳 UI（engine/ui.py）——
标题画面 → 新游戏/继续/读档 → 游戏中 → Esc 菜单（存档/读档/回标题/设置/退出）→ 标题。
renderer 只负责把按键翻译成统一键名，UI 只负责状态机，业务动作（读存档/写设置）在这里执行。
"""
from __future__ import annotations

import argparse
import os
import sys
import time

import pygame  # noqa: E402 — demo 主循环直接读键位修饰（Ctrl 快进）

from . import profiling
from . import save as save_api
from .config import CONFIG_FILE, load as load_config
from .data import (DEFAULT_SETTINGS, DataError, audio_hint, data_root, image_hint,
                   load_gallery_config, load_settings, resolve_audio, resolve_image,
                   save_settings)
from . import hotload
from . import pet_host
from .parser import parse_file
from .renderer import CAM_ZOOM_SECONDS, Renderer
from .runtime import Runtime
from .save import SaveError
from .ui import SETTINGS_ITEMS, UI, auto_interval_ms, next_value

# renderer 翻译出来的 UI 统一键名（UI 自己消费，不进业务动作）
# left/right：存档九宫格左右移动、画廊切页签/轮播换图——主循环必须转给 UI，
# 否则 UI 里实现了按键语义、真实游戏里却按不动。
_UI_KEYS = {"up", "down", "left", "right", "confirm", "back", "backlog", "quicksave"}

# P26 T1：序幕节奏（毫秒）——台词读完的停顿 / CG 停留
_SPLASH_HOLD_MS = 1200
_SPLASH_CG_HOLD_MS = 2500
SPLASH_SCRIPT_NAME = "开场.gal"  # 序幕脚本：与 script.gal 同目录，缺失则无序幕


def run(script_path: str, assets_root=".", max_frames=None, auto=True,
        profile=False, hot_reload=False) -> None:
    """主循环：load 剧本 → 资源预检 → 循环 [render → handle_input → 按动作驱动 runtime/UI] → close。

    max_frames：测试用，跑 N 帧后退出；None 表示一直跑到结束或用户退出。
    auto：测试钩子（Python 接口默认 True，命令行默认 False）。auto 模式下跳过标题画面、
          无玩家输入时自动执行「打字机完成 → advance → 选项自动选第一个可选项」，直到 finished。
    profile：迭代-01 任务2 帧耗时 profiling，退出时打印 视图/渲染/输入/业务/IO 分布。
    hot_reload：P51-T6 热重载（默认关）——剧本改完自动从当前 label 重播、config.json 改完即时生效。
    """
    prof = profiling.PROFILER
    prof.enabled = profile
    prof.reset()  # 同进程可多次 run（测试场景），互不继承上次的样本
    rt = Runtime()
    ren = Renderer(assets_root=assets_root)  # T10：画布尺寸从 config.json 读取
    settings_path = os.path.join(assets_root, "settings.json")
    # 桌宠：默认关；玩家在设置页「界面 → 桌宠」打开后，游戏运行期间拉起独立进程
    _boot_settings = load_settings(settings_path)
    pet_host.sync(_boot_settings.get("pet_enabled"))
    # 存档目录跟随数据根（settings.data_dir：随游戏 / AppData / 自定义绝对路径）：
    # 统一走 data_root()，否则 data_dir=appdata 会被这里覆盖回游戏目录。
    save_api.set_saves_dir(os.path.join(data_root(assets_root), "saves"))
    ui = UI(config=load_config(assets_root))  # P44：标题菜单 items 覆盖读 config.json
    ui.settings_path = settings_path  # UI 与 renderer 读写同一个 settings.json
    # P28 E1/E3：画廊固定格子 + 幻灯片序列（文件缺省时为空 = 旧行为）
    ui.set_gallery_config(load_gallery_config(assets_root))
    ui.set_script_title(_read_script_title(script_path))  # ⑪ 作品名二级：剧本首行 # 注释
    ui.refresh()
    # 标题画面不加载剧本：auto 测试钩子跳过标题直接进游戏，保持无 UI 时的原有语义
    game_loaded = False
    in_splash = False       # P26 T1：序幕播放中
    ending_hold_t0 = None   # P30-S2-3：终幕停留计时起点（到点才淡出）
    if auto:
        rt.load(script_path)
        ui.mode = "playing"
        game_loaded = True
    else:
        # P26 T1：序幕（settings.splash 开启且同目录有 开场.gal）→ 先播序幕再进标题
        splash_script = _find_splash_script(script_path, settings_path)
        if splash_script is not None:
            try:
                rt.load(splash_script)
            except Exception as e:  # 序幕坏了不能挡住游戏：中文警告后跳过
                print(f"[序幕警告] 开场剧本加载失败，已跳过序幕：{e}", file=sys.stderr)
            else:
                _precheck_resources(splash_script, assets_root)
                ui.mode = "playing"      # 序幕复用游戏画面的渲染路径（不画对话框）
                ren.set_splash(True)
                game_loaded = True
                in_splash = True
    _precheck_resources(script_path, assets_root)  # 启动时预检，只做一次
    title_prev_mode = None  # P33：标题音乐跟随 UI 模式切换（进标题淡入 / 离开淡出）
    auto_t0 = 0              # P34-T1：AUTO 自动播放的推进节拍计时（ms）
    # M1.5：快捷栏首次使用提示（只提示一次，写 settings；不弹窗、不打断）
    quickbar_hint_done = bool(load_settings(settings_path).get("quickbar_hint_seen"))
    skip_halt = False        # P44-D：viewed 模式下遇到未浏览内容时中断本轮快进
    frames = 0
    # P51-T6：热重载监视器（默认关；只 stat 文件 mtime，每 500ms 一次）
    hot_script = hotload.FileWatch([script_path]) if hot_reload else None
    hot_config = (hotload.FileWatch([os.path.join(assets_root, CONFIG_FILE)])
                  if hot_reload else None)
    if hot_script is not None and game_loaded:
        hot_script.set_paths(rt.script_files())
    _wall_t0 = time.perf_counter()  # profiling 墙钟只计主循环段（不含启动加载）
    try:
        while True:
            _t0 = time.perf_counter()  # 帧起点（profiling 关闭时也可忽略的开销）
            if hot_script is not None:
                _hot_tick(hot_script, hot_config, rt, ren, ui, script_path,
                          assets_root, game_loaded)
            state = rt.snapshot() if game_loaded else {}
            ui.set_history(state.get("history"))
            if game_loaded:
                # P26 T4：画廊数据 = 全局解锁 ∪ 当前档解锁
                ui.set_gallery(save_api.gallery_union(state.get("gallery") or []),
                               rt.seen_sprites())
            view = ui.view(now_ms=ren._now_ms())
            if (not auto and game_loaded and not quickbar_hint_done
                    and view["mode"] == "playing"):
                quickbar_hint_done = True
                hint_settings = load_settings(settings_path)
                hint_settings["quickbar_hint_seen"] = True
                try:
                    save_settings(hint_settings, settings_path)
                except OSError:
                    pass
                ren.toast("按 Insert / X 显示或隐藏界面按钮", 3.5)
            _t1 = time.perf_counter()  # 视图构建完毕
            # P33：标题音乐——config.title_music 非空时，进标题淡入播放、离开标题淡出停止
            # （auto 无头模式不进标题不播；读档/回标题/结局淡出回标题均自动跟随）
            if view["mode"] != title_prev_mode:
                if view["mode"] == "title" and not auto:
                    tm = str(ren.config.data.get("title_music") or "").strip()
                    if tm:
                        ren.play_music(tm, fadein=1.0)
                elif title_prev_mode == "title":
                    ren.play_music(None, fadeout=0.8)
                title_prev_mode = view["mode"]
            ren.render(state, view)
            _t2 = time.perf_counter()  # 渲染完毕
            act = ren.handle_input()
            _t3 = time.perf_counter()  # 输入处理完毕（之后到帧末为业务分发）
            action = act.get("action")
            if action == "quit":
                break
            if in_splash:
                # P26 T1 序幕：任意键跳过（淡出回标题）；无输入则按固定节奏自动推进
                if ren._ending_fade_t0 is None and not ren._ending_fade_done:
                    if action != "none":
                        in_splash = False
                        ren.timeline.cancel("splash")  # 跳过序幕：丢掉未走完的停留轨
                        ren.trigger_ending_fade()  # 跳过序幕也走淡出，避免硬切
                    else:
                        _drive_splash(rt, ren, state)
            elif _is_ui_key(action) or action in ("click", "drag"):
                # P31-b：鼠标点击/按住拖动与键盘走同一套 UI 逻辑（click 只多一步命中区域→语义）
                business = (ui.click(act.get("hit"), pos=act.get("pos")) if action in ("click", "drag")
                            else ui.handle(action))
                if business:
                    status = _apply_business(business, rt, ren, ui, script_path, settings_path)
                    if status == "quit":
                        break
                    if status == "loaded":
                        game_loaded = True
                        if hot_script is not None:
                            hot_script.set_paths(rt.script_files())
                    elif status == "unloaded":
                        game_loaded = False
            elif view["mode"] == "playing" and game_loaded:
                # ⑩ 结尾淡出期间：拦截 advance/choose；Esc/back/quit 跳过淡出直接回标题
                if ren._ending_fade_t0 is not None:
                    if action in ("quit",) or _is_ui_key(action) and action == "back":
                        # 跳过淡出直接回标题
                        ren._ending_fade_t0 = None
                        ren._ending_fade_done = False
                        ending_hold_t0 = None
                        game_loaded = False
                        ui.mode = "title"
                    # 淡出期间拦截 advance/choose，什么都不做
                else:
                    # P34-T1：SKIP 开关 / Ctrl 快进——打字机放完 + 跳过 @wait + 自动推进；遇选项/UI 停
                    # P44-D：skip 默认禁（config.skip.enabled 或旧键 ui.quickbar.skip_enabled 开启后生效）
                    # skip.mode="viewed" 时只快进已浏览内容，遇到新台词自动停下
                    ctrl_held = bool(pygame.key.get_mods() & pygame.KMOD_CTRL)
                    if not ctrl_held and not ui.skip_on:
                        skip_halt = False  # 松开 Ctrl / 关闭 SKIP 后解除中断锁
                    if (ren._options is None and ui.skip_allowed and not skip_halt
                            and (ctrl_held or ui.skip_on)):
                        ren.reveal_all()
                        if rt.pending_wait_seconds() > 0:
                            rt.advance_wait(999.0)
                        else:
                            ev = _step(rt, ren)
                            if (ui.skip_mode == "viewed" and ev.get("type") == "say"
                                    and not ev.get("read")):
                                ui.skip_on = False
                                skip_halt = True
                    # P34-T1：AUTO 自动播放——打字机放完 → 每 700ms 推进一条；遇选项/手动输入停
                    elif ren._options is None and ui.auto_on:
                        if not ren.typewriter_complete():
                            ren.reveal_all()
                        elif rt.pending_wait_seconds() > 0:
                            rt.advance_wait(999.0)
                        elif ren._now_ms() - auto_t0 >= auto_interval_ms(
                                ren.settings, ren._pacing("auto_advance_ms", 900)):
                            auto_t0 = ren._now_ms()
                            _step(rt, ren)
                    elif action in ("advance", "choose") and ui.auto_on:
                        ui.auto_on = False  # P34-T1：玩家手动推进/选择 → 停 AUTO
                    # @wait 暂停：demo 倒计时完才能调 step()；倒计时期间只渲染不推进
                    elif rt.pending_wait_seconds() > 0:
                        dt = float(getattr(ren, "_last_dt_ms", 0)) / 1000.0
                        rt.advance_wait(dt)
                    elif action == "advance":
                        # P30-S2-3：终幕停留期间空格/点击跳过直接触发淡出
                        if ending_hold_t0 is not None:
                            ending_hold_t0 = None
                            ren.trigger_ending_fade()
                        else:
                            _step(rt, ren)
                    elif action == "choose":
                        try:
                            rt.choose(act["index"])
                        except Exception as e:  # noqa: BLE001 — 选项异常不崩游戏
                            print(f"[输入警告] {e}", file=sys.stderr)
            # ⑩ 非 auto 模式检测 finished → 先停留终幕画面（P30-S2-3，默认 1.5s），到点再淡出
            if (not auto and game_loaded and ren._ending_fade_t0 is None
                    and state.get("finished")):
                if ending_hold_t0 is None:
                    ending_hold_t0 = ren._now_ms()
                if ren._now_ms() - ending_hold_t0 >= ren.ending_hold_ms():
                    ending_hold_t0 = None
                    ren.trigger_ending_fade()
            # ⑩ 淡出完成 → 回标题
            if ren._ending_fade_done:
                ren._ending_fade_t0 = None
                ren._ending_fade_done = False
                game_loaded = False
                ui.mode = "title"
                if in_splash or ren._splash_mode:  # 序幕结束：恢复普通画面渲染
                    in_splash = False
                    ren.set_splash(False)
            # reveal：交给 renderer 内部处理（打字机直接显示全文），这里不用动
            if auto and action == "none" and game_loaded and view["mode"] == "playing":
                _auto_drive(rt, ren, state)
            frames += 1
            _t4 = time.perf_counter()  # 帧末
            # profiling：quit 帧不计（样本缺业务段，且是最后一帧）；各段均为每帧毫秒
            prof.add("视图", (_t1 - _t0) * 1000.0)
            prof.add("渲染", (_t2 - _t1) * 1000.0)
            prof.add("输入", (_t3 - _t2) * 1000.0)
            prof.add("业务", (_t4 - _t3) * 1000.0)
            prof.add("帧总", (_t4 - _t0) * 1000.0)
            if max_frames is not None and frames >= max_frames:
                break
            if game_loaded and state.get("finished") and auto:
                break  # auto 模式跑完即退出；正常游玩停在终幕等玩家退出
    finally:
        ren.close()
        pet_host.stop()  # 游戏退出不留孤儿桌宠窗口
        save_api.reset_saves_dir()  # 恢复默认 ./saves，避免污染同进程后续调用
        if profile:
            print(prof.report(wall_ms=(time.perf_counter() - _wall_t0) * 1000.0,
                              frames=frames))
        prof.enabled = False
        prof.reset()  # 不污染同进程后续调用（与 reset_saves_dir 同理）


def _hot_tick(script_watch, config_watch, rt: Runtime, ren: Renderer, ui: UI,
              script_path: str, assets_root: str, game_loaded: bool) -> None:
    """P51-T6：每帧热重载检查（监视层到点才 stat，这里只做应用）。

    - 剧本变了：重新解析 → Runtime.reload（从当前 label 重播，变量/历史/解锁保留）；
      解析失败只中文告警 + 弹 toast，**继续用旧版本**，不打断正在玩的游戏。
    - 配置变了：重建配置视图与字体（画布尺寸变更热应用不了，提示重启）。
    """
    now = ren._now_ms()
    if script_watch.changed(now) and game_loaded:
        try:
            instructions = parse_file(script_path)
        except Exception as e:  # noqa: BLE001 — 热重载失败不能影响正在玩的游戏
            print(f"[热重载] 剧本解析失败，继续用旧版本：{e}", file=sys.stderr)
            # 发行版没有控制台：不能只说「见控制台」，要直接把行号与原因带上
            ren.toast("剧本重载失败，继续用旧版本：" + _err_brief(e), 4.0)
        else:
            rt.reload(instructions)
            script_watch.set_paths(rt.script_files())
            ren.toast("剧本已重载")
    if config_watch.changed(now):
        new_config = load_config(assets_root)
        if ren.apply_config(new_config):
            ui.set_config(new_config)
            ren.toast("配置已重载")
        else:
            ren.toast("画布尺寸变更需重启")


def _is_ui_key(action) -> bool:
    """是否为 UI 统一键名（slot1~slot10 也算）。"""
    return action in _UI_KEYS or (str(action).startswith("slot") and str(action)[4:].isdigit())


_TOAST_CHARS = 56


def _toast_fit(text, limit: int = _TOAST_CHARS) -> str:
    """toast 是左下角单行提示：过长会画出屏幕，这里压成一行并截断加省略号。"""
    one = " ".join(str(text or "").split())
    return one if len(one) <= limit else one[: limit - 1] + "…"


def _err_brief(exc, limit: int = _TOAST_CHARS) -> str:
    """异常转成一句可定位的短提示：语法错误优先给「第 N 行：原因」，省掉长路径。"""
    line = getattr(exc, "line", 0) or 0
    message = getattr(exc, "message", None)
    if message and line:
        return _toast_fit(f"第 {line} 行：{message}", limit)
    return _toast_fit(exc, limit)


def _apply_business(business: dict, rt: Runtime, ren: Renderer, ui: UI,
                    script_path: str, settings_path: str) -> str | None:
    """执行 UI 返回的业务动作。

    返回状态："quit" 退出主循环 / "loaded" 游戏已加载（进 playing）/
    "unloaded" 游戏已卸载（回标题）/ None 其余情况。
    """
    kind = business.get("action")
    if kind == "start_game":
        try:
            rt.load(script_path)
        except Exception as e:  # 剧本语法/IO 错误：打印中文警告，回标题不崩主循环
            print(f"[启动警告] 剧本加载失败：{e}", file=sys.stderr)
            ui.mode = "title"
            # 发行版没有控制台：必须把原因（含文件名/行号）显示给玩家，否则像点了没反应
            ren.toast("剧本加载失败：" + _err_brief(e), 4.0)
            return None
        _prime_first_beats(rt, ren)  # 立即出第一句，避免点了新游戏先看空画面
        return "loaded"
    if kind == "continue_game":
        slots = save_api.list_slots()
        if not slots:
            ui.mode = "title"  # 无存档：标题已灰置，这里兜底回标题
            return None
        latest = max(slots, key=lambda e: e.get("saved_at") or "")
        return _do_load(rt, ui, latest["slot"], ren)
    if kind == "load_slot":
        return _do_load(rt, ui, business.get("slot"), ren)
    if kind == "save_slot":
        try:
            rt.save(business.get("slot"))
        except (SaveError, RuntimeError) as e:
            print(f"[存档警告] {e}", file=sys.stderr)
            ren.toast("存档失败：存档目录不可写", 3.0)  # 发行版无控制台，必须给可见反馈
        else:
            # ⑨ 存档后补三要素：缩略图 + 章节名 + 末句
            try:
                _post_save_enrich(business.get("slot"), rt, ren, script_path)
            except Exception as e2:
                print(f"[存档卡片警告] {e2}", file=sys.stderr)
        ui.refresh()  # 存档后刷新列表（仍停在列表里，可继续覆盖；3.3 不二次确认）
        return None
    if kind == "to_title":
        # 标题是纯 UI 状态（3.6）：不重新加载剧本，旧进度随 game_loaded 置 False 不再渲染
        return "unloaded"
    if kind == "settings_capture":
        # U10：设置页在键位项按回车 → 进入「按新键」捕获
        key = business.get("key")
        if key:
            ui.capturing = key
            ren.begin_key_capture(key)
        return None
    if kind == "settings_set_key":
        # U10：捕获到的键写回设置（code 为空 = 恢复默认）
        key = str(business.get("key") or "")
        code = str(business.get("code") or "")
        if key:
            settings = dict(ui.view().get("settings") or DEFAULT_SETTINGS)
            settings[key] = code
            try:
                save_settings(settings, settings_path)
            except OSError as e:
                print(f"[设置警告] 键位保存失败：{e}", file=sys.stderr)
                ren.toast("键位保存失败：设置目录不可写", 3.0)  # 无控制台发行版也能看见
            ren.update_settings({key: code})   # 立即重建键位表
            ui.set_settings(settings)
        ui.capturing = None
        ren.begin_key_capture(None)
        return None
    if kind == "settings_change":
        settings = dict(ui.view().get("settings") or DEFAULT_SETTINGS)
        key = business.get("key")
        settings[key] = next_value(key, settings.get(key))  # UI 提供「下一档」规则
        try:
            save_settings(settings, settings_path)  # 修改即写
        except OSError as e:
            print(f"[设置警告] 设置保存失败：{e}", file=sys.stderr)
            ren.toast("设置保存失败：设置目录不可写", 3.0)
        ren.update_settings(settings)  # 音量/打字速度实时生效
        if key == "display_mode":
            ren.apply_display_mode(settings.get("display_mode"))  # 立即切窗口；失败无副作用
        if key == "pet_enabled":
            pet_host.sync(settings.get(key))  # 开关即时生效（失败只中文告警）
        ui.set_settings(settings)      # UI 同步新值（下次进入设置即显示）
        return None
    if kind == "settings_set":
        # P49：滑条直接定值（鼠标点击/拖动）——value 为 0.0~1.0 比例
        settings = dict(ui.view().get("settings") or DEFAULT_SETTINGS)
        key = business.get("key")
        value = business.get("value")
        if key is not None and value is not None:
            try:
                ratio = max(0.0, min(1.0, float(value)))
                item = next((it for it in SETTINGS_ITEMS if it["key"] == key), None)
                if item and item.get("kind") == "offset":
                    # U7：位置滑条按 min~max 线性换算回真实像素（音量类仍直接存 0~1 比例）
                    lo = float(item["min"])
                    hi = float(item["max"])
                    step = float(item.get("step") or 1)
                    raw = lo + (hi - lo) * ratio
                    settings[key] = int(round(raw / step) * step)
                else:
                    settings[key] = ratio
                save_settings(settings, settings_path)  # 修改即写
            except (OSError, ValueError) as e:
                print(f"[设置警告] 滑条设置保存失败：{e}", file=sys.stderr)
                ren.toast("设置保存失败：修改未写入 settings.json", 3.0)
            ren.update_settings(settings)
            ui.set_settings(settings)
        return None
    if kind == "toggle_subtitles":
        # P48：截图模式开关（对话框顶部 ▼）——隐藏/恢复字幕栏与快捷栏
        ren._ui_hidden = not ren._ui_hidden
        return None
    if kind == "quit":
        return "quit"
    return None


_PRIME_MAX_EVENTS = 200


def _prime_first_beats(rt: Runtime, ren: Renderer, max_events: int = _PRIME_MAX_EVENTS) -> None:
    """新游戏加载后推进到第一条「玩家看得见 / 需要回应」的内容。

    只跳过后台指令（@bg/@music/@sfx/@show/@hide/@camera/@transition/@anim/@fg），
    遇到台词 / 选项 / @wait / CG / 结束即停。否则玩家点「开始新游戏」后先看到
    一个没有背景、没有对话框的空画面，必须再按一次空格才出现第一句。
    """
    for _ in range(max_events):
        st = rt.snapshot()
        if (st.get("history") or st.get("pending_choice") or st.get("pending_wait")
                or st.get("finished") or getattr(ren, "_cg_showing", None) is not None):
            return
        ev = _step(rt, ren)
        if ev.get("type") == "end":
            return


def _do_load(rt: Runtime, ui: UI, slot, ren=None) -> str | None:
    """读档公共逻辑：成功返回 "loaded"；失败打印中文警告、退回存档列表重选。"""
    try:
        rt.load_save(slot)
        return "loaded"
    except (SaveError, RuntimeError) as e:
        print(f"[读档警告] {e}", file=sys.stderr)
        if ren is not None:
            ren.toast("读档失败：存档损坏或无法读取", 3.0)
        ui.mode = "slots"  # 留在列表重选（back 可退出来处：标题或菜单）
        ui.refresh()
        return None


def _step(rt: Runtime, ren: Renderer) -> dict:
    """推进一条指令；sfx/music/cg/camera/transition 事件分发到 renderer 对应方法。

    返回该条指令产生的事件（序幕驱动要靠事件类型决定节奏）。

    P29 P0-2：runtime.step() 已兜底 set/if/choice 的剧本错误，这里再兜一层
    （未知 opcode / renderer 边界异常 / 插件意外抛错），保证单条指令失败不崩游戏。
    """
    try:
        ev = rt.step()
    except Exception as e:  # noqa: BLE001 — 故意兜住所有异常，不让玩家闪退
        print(f'[剧本警告] 指令执行失败，已跳过：{e}', file=sys.stderr)
        return {"type": "noop"}
    kind = ev.get("type")
    if kind == "scene":
        ren.play_bg(ev.get("fadein"))  # P33：@bg fadein= 一次性淡入时长
    elif kind == "sfx":
        ren.play_sfx(ev.get("sound"))
    elif kind == "music":  # P26 T3：带淡入淡出参数切曲（无参数=立即切，旧行为）
        ren.play_music(ev.get("track"), ev.get("fadein"), ev.get("fadeout"))
    elif kind == "cg":
        ren.play_cg(ev.get("name"))
    elif kind == "camera":
        ren.play_camera(ev.get("kind"), ev.get("args"))
    elif kind == "transition":
        ren.play_transition(ev.get("kind"), ev.get("args"))
    elif kind == "fg":  # P30-C-b：前景/特效层贴图（纯展示层）
        ren.play_fg(ev.get("name"), ev.get("x"), ev.get("y"), ev.get("alpha"))
    elif kind == "anim":  # P30-C-c：立绘参数补间（纯展示层）
        ren.play_anim(ev.get("char"), ev.get("param"), ev.get("from"), ev.get("to"),
                      ev.get("secs"), ev.get("ease") or "linear")
    elif kind == "chapter":  # U12：章节/幕间演出卡（黑场 + 标题）
        ren.play_chapter(str(ev.get("title") or ""), ev.get("secs"))
    return ev


def _read_script_title(script_path: str):
    """⑪ 作品名二级：读剧本首行 `#` 注释（去掉 `#` 前缀）。

    跳过空行；遇到第一个非空且非 `#` 开头的行即停止（说明没有首行注释标题）。"""
    try:
        with open(script_path, encoding="utf-8") as f:
            for _ in range(80):  # 最多扫前 80 行，避免超长文件无注释时空转
                line = f.readline()
                if not line:
                    break
                text = line.strip().lstrip("\ufeff").strip()
                if not text:
                    continue
                if not text.startswith("#"):
                    break
                title = text.lstrip("#").strip()
                if title:
                    return title
    except OSError:
        pass
    return None


def _post_save_enrich(slot, rt: Runtime, ren: Renderer, script_path: str) -> None:
    """⑨ 存档后补三要素：缩略图 + 章节名 + 末句。

    rt.save() 只调 save_api.save(state, slot, anchor_stack)，不传新字段。
    此函数在 rt.save 之后，读回存档 JSON 补全 thumbnail_path/chapter_name/last_text，
    并让 renderer 截屏存缩略图文件到 saves/thumb_{slot}.png。
    """
    slot_key = str(slot)
    if slot_key == save_api.QUICK_SLOT:
        slot_key = save_api.QUICK_SLOT
    # 0. 先读回存档 JSON（payload 里已有 label=最近 anchor 的 label 名）
    import json as _json
    from pathlib import Path
    save_path = save_api.slot_path(slot_key)  # 跟随 save_api 的存档目录（资源根/saves）
    if not save_path.is_file():
        return
    try:
        data = _json.loads(save_path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return

    # 1. 生成缩略图（与存档同目录；存档里只记文件名，便于整目录搬移）
    import os as _os
    _os.makedirs(save_api.saves_dir(), exist_ok=True)
    thumb_name = f"thumb_{slot_key}.png"
    thumb_path = str(Path(save_api.saves_dir()) / thumb_name)
    ren.save_thumbnail(thumb_path)

    # 2. 取末句 + 章节名
    state = rt.snapshot()
    history = state.get("history") or []
    last_text = None
    if history:
        t = history[-1].get("text", "")
        if t:
            last_text = (t[:29] + "…") if len(t) > 30 else t
    # 章节名：优先 payload.label（_nearest_label 来自 anchor_stack），
    # 回退剧本首行 # 注释，最后回退 state.label（兜底）
    chapter_name = data.get("label")
    if not chapter_name:
        try:
            with open(script_path, encoding="utf-8") as f:
                first_line = f.readline().strip()
                if first_line.startswith("#"):
                    chapter_name = first_line.lstrip("#").strip() or None
        except OSError:
            pass
    if not chapter_name:
        chapter_name = state.get("label")

    # 3. 补全三个字段回写存档 JSON
    data["thumbnail_path"] = thumb_name
    data["chapter_name"] = chapter_name
    data["last_text"] = last_text
    save_path.write_text(_json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _find_splash_script(script_path: str, settings_path: str):
    """P26 T1：settings.splash 开启且剧本同目录有 开场.gal 时返回其路径，否则 None。

    缺省（无该文件 / splash=0）行为与旧版完全一致：直接进标题。
    """
    try:
        settings = load_settings(settings_path)
    except Exception:
        settings = dict(DEFAULT_SETTINGS)
    if not settings.get("splash"):
        return None
    candidate = os.path.join(os.path.dirname(os.path.abspath(script_path)), SPLASH_SCRIPT_NAME)
    return candidate if os.path.isfile(candidate) else None


def _splash_hold_ms(ev: dict) -> int:
    """P28 E2：序幕事件推完后需要停留的毫秒数（0 = 不停留，继续推下一条）。

    台词/换景/选项停留固定节奏；镜头动画按自身时长停留（pan/reset 取秒数参数，
    zoom 用 renderer 的默认时长）；shake 幅度小且以震动为主，不停留。
    """
    kind = ev.get("type")
    if kind in ("say", "scene", "choice"):
        return _SPLASH_HOLD_MS
    if kind == "cg":
        return _SPLASH_CG_HOLD_MS
    if kind == "camera":
        cam = ev.get("kind")
        args = ev.get("args") or []
        secs = None
        if cam in ("pan", "reset") and args:
            secs = args[-1]
        elif cam == "zoom":
            secs = CAM_ZOOM_SECONDS
        if secs is None:
            return 0
        try:
            return max(0, int(float(secs) * 1000))
        except (TypeError, ValueError):
            return 0
    return 0


def _drive_splash(rt: Runtime, ren: Renderer, state: dict) -> None:
    """P26 T1 序幕自动播放：台词/换景/CG/镜头动画必须被看见——停留够时间后才推下一条。

    P30-C-a：停留不再是 demo 里的 (t0, hold) 元组，而是 Renderer Timeline 上的 splash hold 轨，
    与镜头/转场共用同一个时钟；本轮不需要停留时该轨被取消。
    """
    if state.get("finished"):
        return  # 演完：交给主循环的 finished 检测触发淡出
    now = ren._now_ms()
    if ren._cg_showing is not None:
        if not ren.timeline.has("splash"):
            ren.timeline.hold("splash", _SPLASH_CG_HOLD_MS, t0=now)
        elif ren.timeline.done("splash", now):
            ren._cg_showing = None
            ren.timeline.cancel("splash")
        return
    if not ren.typewriter_complete():
        return  # 还在打字，先等它放完
    if ren.timeline.has("splash") and not ren.timeline.done("splash", now):
        return  # 本句/本张背景/本段镜头的停留时间还没到
    ren.timeline.cancel("splash")
    ev = _step(rt, ren)
    if not ev:
        return
    hold = _splash_hold_ms(ev)
    if hold > 0:
        # 停留起点 = 推完这条指令的时刻（与旧的 (t0, hold) 语义一致）
        ren.timeline.hold("splash", hold, t0=ren._now_ms())


def _auto_drive(rt: Runtime, ren: Renderer, state: dict) -> None:
    """auto 测试钩子：无输入时自动推进（打字机完成 → advance → 选第一个可选项）。"""
    # @wait 暂停：auto 模式直接跳过（推进到剩余秒数清零），不倒计时
    if rt.pending_wait_seconds() > 0:
        rt.advance_wait(999.0)
        return
    if ren._cg_showing is not None:
        ren._cg_showing = None  # CG 展示：auto 模式立即关闭并推进
        _step(rt, ren)
        return
    pc = state.get("pending_choice")
    if pc:
        for i, o in enumerate(pc.get("options") or []):
            if o.get("available"):
                try:
                    rt.choose(i)
                except Exception as e:  # noqa: BLE001 — 选项异常不崩游戏
                    print(f"[输入警告] {e}", file=sys.stderr)
                return
        return  # 全都不可选是剧本问题，等下一帧
    if state.get("finished"):
        return
    if not ren.typewriter_complete():
        ren.reveal_all()  # 先补完打字机，下一帧再 advance
        return
    if ren._next_page():
        return  # 长段落分页：auto 也逐页翻完再推进，否则会漏掉后半句
    _step(rt, ren)


def _precheck_resources(script_path: str, assets_root: str) -> None:
    """资源缺失提前预警：扫描剧本全部指令（含 if 嵌套 body）引用的图片/音频，
    缺失的不抛异常，打印中文缺失清单（带行号）到 stderr。预检只做一次。"""
    try:
        instructions = parse_file(script_path)
    except Exception:
        return  # 语法/IO 错误由 load 阶段报过，预检不重复

    missing = []

    def check_image(name, desc, line, file):
        try:
            resolve_image(assets_root, name)
        except DataError:
            # P29 A4：候选文件名随加载层实际后缀生成（.png/.jpg），转 JPG 后不误报
            missing.append(f"[资源缺失] {image_hint(name)} —— {desc}（{file} 第 {line} 行）")

    def check_audio(name, desc, line, file):
        try:
            resolve_audio(assets_root, name)
        except DataError:
            missing.append(f"[资源缺失] {audio_hint(name)} —— {desc}（{file} 第 {line} 行）")

    def walk(instrs):
        for ins in instrs:
            op = ins.get("op")
            line = ins.get("line")
            file = ins.get("file", script_path)  # 跨文件剧本定位到真实所在文件
            if op == "bg":
                check_image(ins.get("image"), f"@bg {ins.get('image')}", line, file)
            elif op == "cg":
                check_image(ins.get("name"), f"@cg {ins.get('name')}", line, file)
            elif op == "fg":
                check_image(ins.get("name"), f"@fg {ins.get('name')}", line, file)
            elif op == "show":
                char, expr = ins.get("char"), ins.get("expr")
                check_image(f"{char}_{expr}", f"@show {char} {expr}", line, file)
                # P32：分层立绘（@show 角色 部位:素材）逐个部位预检
                for part, value in (ins.get("layers") or {}).items():
                    check_image(f"layers/{char}/{part}_{value}",
                                f"@show {char} {part}:{value}", line, file)
            elif op == "music":
                check_audio(ins.get("track"), f"@music {ins.get('track')}", line, file)
            elif op == "sfx":
                check_audio(ins.get("sound"), f"@sfx {ins.get('sound')}", line, file)
            elif op == "voice":
                check_audio(ins.get("sound"), f"@voice {ins.get('sound')}", line, file)
            elif op == "if":
                walk(ins.get("body") or [])
                walk(ins.get("else_body") or [])  # P26 T2：@elif/@else 体也预检

    walk(instructions)
    for msg in missing:
        print(msg, file=sys.stderr)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="engine.demo", description="MYONL 演示主循环")
    ap.add_argument("script", help="剧本 .gal 文件路径")
    ap.add_argument("--assets", default=".", help="资源根目录（其下有 images/ audio/ fonts/）")
    ap.add_argument("--max-frames", type=int, default=None, help="跑 N 帧后退出（测试用）")
    ap.add_argument("--auto", action="store_true", help="测试钩子：无输入时自动推进到结束")
    ap.add_argument("--profile", action="store_true",
                    help="帧耗时 profiling：退出时打印 视图/渲染/输入/业务/IO 分布")
    ap.add_argument("--hot-reload", action="store_true",
                    help="P51-T6 热重载：改完 .gal 从当前场景重播、改完 config.json 即时生效（默认关）")
    args = ap.parse_args(argv)
    try:
        run(args.script, assets_root=args.assets, max_frames=args.max_frames,
            auto=args.auto, profile=args.profile, hot_reload=args.hot_reload)
    except (OSError, RuntimeError) as e:
        print(f"运行失败：{e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
