"""MYONL 运行时解释器 / 状态机。

无渲染：逐条执行 parser 输出的指令列表，维护 GameState。
- GameState 全程 JSON 可序列化（存档 = 序列化它），执行栈只存 [列表ID, 下标]，不存对象引用
- 接口与执行语义严格按 engine_spec.md 第 5 节
- 只用 Python 标准库；异常信息用中文
"""
from __future__ import annotations

import copy
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Callable

from . import expr as expr_api
from . import save as save_api
from .parser import GalSyntaxError, parse_file

MAX_STEPS = 1_000_000  # 死循环防护：单个 Runtime 最多执行的 step 次数

# 台词插值：${变量名} 为规范写法；{变量名} 为旧写法（仅已定义变量且不撞富文本标记时生效）
_PLACEHOLDER = re.compile(r"\$\{(\w+)\}|\{(\w+)\}", re.UNICODE)
_RICH_TAG_NAMES = frozenset({"b", "i", "color", "size"})  # 与 engine/richtext.py 的标记同名，不能当变量吃掉


def _fmt_value(value) -> str:
    """变量值 → 台词插值文本（整数不带小数点）。"""
    if isinstance(value, bool):
        return str(int(value))
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _interpolate(text: str, variables: dict, line) -> str:
    """台词插值：${变量名} → 当前值（缺变量替换为空串并中文警告，不崩）。

    兼容旧写法 {变量名}，但只在「是已定义变量」且「不是富文本标记名」时替换；
    其余情况原样保留——否则 {b}粗体{/b} 会被插值层吃掉，富文本直接失效。
    """
    if "{" not in text:
        return text

    def repl(m):
        name = m.group(1) or m.group(2)
        if m.group(1) is None:  # 旧写法 {变量名}
            if name in _RICH_TAG_NAMES or name not in variables:
                return m.group(0)
            return _fmt_value(variables[name])
        if name not in variables:
            print(f'[变量警告] 第 {line} 行：台词里的变量 "${{{name}}}" 未定义，已替换为空', file=sys.stderr)
            return ""
        return _fmt_value(variables[name])

    return _PLACEHOLDER.sub(repl, text)

# 插件指令注册表：指令名 -> handler。
# handler 签名：handler(state: GameState, args: list[str]) -> dict | None
#   返回 dict → 作为事件进 trace（自动附 seq）；返回 None → 静默（只改 state）
_COMMANDS: dict[str, Callable[[dict, list[str]], "dict | None"]] = {}


def register_command(name: str, handler) -> None:
    """注册插件指令（插件模块顶层调用）。同名重复注册 → 覆盖，后注册生效。"""
    _COMMANDS[name] = handler


class Runtime:
    """引擎控制原语载体。所有原语输入输出均为 JSON 可序列化的 dict / list。

    实例可复用：重复调用 load() 会重置为全新的 GameState。
    """

    MAX_STEPS = MAX_STEPS

    def __init__(self):
        self._state: dict | None = None           # GameState（只含 JSON 数据）
        self._lists: dict[int, list[dict]] = {}   # 指令列表索引：列表ID -> list[dict]（0 号为顶层）
        self._labels: dict[str, tuple[int, int]] = {}  # 标签名 -> (列表ID, 下标)
        self._events: list[dict] = []             # trace 缓存（不进 snapshot）
        self._step_count = 0                      # 已执行 step 数（死循环防护）
        self.MAX_STEPS = MAX_STEPS
        self._commands: dict = {}                 # P29 A4：本实例的插件注册表（多 Runtime 互不影响）
        self._current_label = None                # P51-T6：当前所在 label（热重载的接续锚点）

    # ==================== 控制原语 ====================

    def load(self, script_path: str) -> dict:
        """加载并解析剧本，初始化 GameState，返回 snapshot。"""
        instructions = parse_file(script_path)
        self._state = {
            "script": str(script_path),
            "stack": [[0, 0]],          # 栈帧：[列表ID, 当前下标]
            "bg": None,
            "music": None,
            "video": None,              # 帧序列视频背景：{"name":..., "fps":...}；@bg 时清除
            "sprites": [],              # [{"char":..., "expr":..., "anim":...}]，顺序即绘制顺序
            "vars": {},
            "characters": {},           # 角色名 -> {"color": ...}
            "history": [],              # [{"char":..., "text":...}]，char 为 None 是旁白
            "pending_choice": None,     # choice 暂停时非空
            "pending_wait": None,      # @wait 暂停时非空 {"seconds": float} 剩余等待秒数
            "finished": False,
            "gallery": [],              # 已解锁 CG 名列表（@cg 时记录，进存档）
            # ---- 持久化展示层状态（进存档，读档后 renderer 复原画面）----
            # 区分"持久状态"与"瞬时动画"：前者进存档，后者（shake 震动、补间动画过程）只在事件层
            "fg": None,                 # @fg 当前前景贴图 {"name","x","y","alpha"}；None=无
            "camera_zoom": 1.0,         # @camera zoom 持久缩放比（reset=1.0；pan/zoom 偏移 runtime 算不出，不进）
            "anim_final": {},           # char -> {param: final_value}；@anim to 值（最终态）
        }
        # 项目级角色库（characters.json）：角色=一等资产；剧本里的 @character 仍可覆盖同名条目
        try:
            from . import characters as characters_api
            for cid, meta in characters_api.load_for_script(str(script_path)).items():
                self._state["characters"][cid] = dict(meta)
        except Exception:  # noqa: BLE001 — 角色库损坏不阻断游戏
            pass
        self._seen_sprites: list[str] = []  # 已见过的角色立绘（"char_expr"，不进存档，当前会话有效）
        self._read_lines: set[int] = set()  # 已浏览过的台词行号（SKIP「仅已浏览」规则用，会话级）
        self._events = []
        self._step_count = 0
        self._current_label = None
        self._index_root(instructions)
        self._load_plugins()
        return self.snapshot()

    # ==================== P51-T6：剧本热重载 ====================

    def reload(self, instructions: list) -> dict:
        """热重载：换掉指令表，从**当前 label 开头**重播（变量 / 历史 / 解锁保留）。

        契约（刻意保守）：当前场景重来一遍——台词会重播、history 会多一份记录；
        待处理选项与 @wait 倒计时清空；解析由调用方完成，本方法假定指令表已合法。
        找不到当前 label（脚本结构大改 / 还没进过 label）→ 从头开始。
        """
        st = self._require_state()
        label = self._current_label
        self._index_root(instructions)
        if label and label in self._labels:
            st["stack"] = self._jump_stack(label, 0)
        else:
            st["stack"] = [[0, 0]]
            self._current_label = None
        st["pending_choice"] = None
        st["pending_wait"] = None
        st["finished"] = False
        return self.snapshot()

    def script_files(self) -> list:
        """当前指令表涉及的所有剧本文件（主剧本 + @include 展开的文件），热重载监视用。"""
        st = self._require_state()
        files = {str(st.get("script") or "")}
        for instrs in self._lists.values():
            for ins in instrs:
                path = ins.get("file")
                if path:
                    files.add(str(path))
        return sorted(f for f in files if f)

    def current_label(self):
        """当前所在 label 名（热重载接续锚点）；尚未进入任何 label 时为 None。"""
        return self._current_label


    def step(self) -> dict:
        """推进一条指令，返回本步事件（event 格式见 engine_spec.md 第 5.2 节）。

        label / character 无副作用无事件，在同一次 step 内直接跳过。
        choice 暂停：设置 pending_choice、不推进下标，等 choose()。
        """
        st = self._require_state()
        if st["pending_choice"] is not None:
            raise RuntimeError("当前有待处理的选项，请先调用 choose()")
        if st.get("pending_wait"):
            # @wait 暂停中：step() 不应被调（由 demo 在倒计时完了再调），这里防御性跳过
            return {"type": "wait", "line": None, "seq": len(self._events) + 1,
                    "seconds": st["pending_wait"]["seconds"]}
        if st["finished"]:
            return {"type": "end", "line": None, "seq": len(self._events) + 1}
        self._step_count += 1
        if self._step_count > self.MAX_STEPS:
            raise RuntimeError(f"执行超过 {self.MAX_STEPS} 步，疑似剧本死循环（@jump 循环），请检查")

        while True:
            self._pop_exhausted()
            if not st["stack"]:
                # 所有指令跑完（没有 @end 也自动视为完成）
                st["finished"] = True
                return self._emit({"type": "end", "line": None})

            frame = st["stack"][-1]
            ins = self._lists[frame[0]][frame[1]]
            op = ins.get("op")
            line = ins.get("line")

            if op == "label":  # 跳转锚点：无副作用，不产生事件
                self._current_label = ins.get("name")
                frame[1] += 1
                continue
            if op == "character":  # 登记角色，不产生玩家可见事件
                st["characters"][ins["name"]] = {
                    "color": ins["color"],
                    "kind": ins.get("kind") or "default",  # P0-1：对话框布局名
                }
                frame[1] += 1
                continue
            if op == "bg":
                st["bg"] = ins["image"]
                st["video"] = None  # 切回静态背景：停掉帧序列视频
                frame[1] += 1
                # P33：fadein 是瞬时演出参数（不进存档），事件带给 renderer
                ev = {"type": "scene", "bg": ins["image"], "line": line}
                if ins.get("fadein"):
                    ev["fadein"] = ins["fadein"]
                return self._emit(ev)
            if op == "video":
                st["video"] = {"name": ins["name"], "fps": ins["fps"]}
                frame[1] += 1
                return self._emit({"type": "video", "name": ins["name"], "fps": ins["fps"], "line": line})
            if op == "music":
                st["music"] = ins["track"]
                frame[1] += 1
                event = {"type": "music", "track": ins["track"], "line": line}
                if ins.get("fadein"):  # P26 T3：淡入秒数（缺省=立即切）
                    event["fadein"] = ins["fadein"]
                if ins.get("fadeout"):
                    event["fadeout"] = ins["fadeout"]
                return self._emit(event)
            if op == "sfx":  # 音效不存状态，只发事件
                frame[1] += 1
                return self._emit({"type": "sfx", "sound": ins["sound"], "line": line})
            if op == "cg":  # CG 全屏展示 + 解锁记录（进存档 + P26 T4 写全局跨周目记录）
                name = ins["name"]
                if name not in st["gallery"]:
                    st["gallery"].append(name)
                save_api.unlock_cg(name)
                frame[1] += 1
                return self._emit({"type": "cg", "name": name, "line": line})
            if op == "camera":
                # zoom 是纯数值（可持久化），pan 是方向+秒数（runtime 算不出最终像素偏移，
                # 让 renderer Timeline 自己跑；reset 把 zoom 复原）
                kind = ins["kind"]
                args = ins["args"]
                if kind == "zoom":
                    st["camera_zoom"] = float(args[1])  # 目标缩放
                elif kind == "reset":
                    st["camera_zoom"] = 1.0
                # pan / shake 瞬时，不进 state（shake 本身就是瞬时震动）
                frame[1] += 1
                return self._emit({"type": "camera", "kind": kind,
                                   "args": list(args), "line": line})
            if op == "transition":  # 纯展示层：作用于下一次背景切换，不进 state（读档后重放无意义）
                frame[1] += 1
                return self._emit({"type": "transition", "kind": ins["kind"],
                                   "args": list(ins["args"]), "line": line})
            if op == "show":  # 已在列表则更新表情，不重复追加
                self._show(st, ins)
                key = f'{ins["char"]}_{ins["expr"]}'
                if key not in self._seen_sprites:
                    self._seen_sprites.append(key)
                frame[1] += 1
                event = {"type": "show", "char": ins["char"], "expr": ins["expr"],
                         "anim": ins.get("anim") or "呼吸", "line": line}
                for extra in ("pos", "scale", "z", "x", "y"):
                    if extra in ins:
                        event[extra] = ins[extra]
                if ins.get("layers"):
                    event["layers"] = ins["layers"]
                return self._emit(event)
            if op == "anim":
                # 持久最终值进 state，读档复原画面（补间动画过程只在 Timeline，读档不重放）
                char = ins["char"]
                param = ins["param"]
                to_value = float(ins["to"])
                st["anim_final"].setdefault(char, {})[param] = to_value
                frame[1] += 1
                event = {"type": "anim", "char": char, "param": param,
                         "to": to_value, "secs": ins["secs"], "ease": ins["ease"],
                         "line": line}
                if "from" in ins:
                    event["from"] = ins["from"]
                return self._emit(event)
            if op == "fg":
                # @fg reset 不带 name，清前景；其余写进 state 保持当前画面
                if ins.get("reset"):
                    st["fg"] = None
                else:
                    st["fg"] = {"name": ins["name"], "x": ins["x"],
                                "y": ins["y"], "alpha": ins["alpha"]}
                frame[1] += 1
                return self._emit({"type": "fg", "name": ins.get("name"),
                                   "x": ins.get("x"), "y": ins.get("y"),
                                   "alpha": ins.get("alpha"), "line": line})
            if op == "hide":
                st["sprites"] = [s for s in st["sprites"] if s["char"] != ins["char"]]
                st["anim_final"].pop(ins["char"], None)   # 立绘消失 → 清其补间最终态
                frame[1] += 1
                return self._emit({"type": "hide", "char": ins["char"], "line": line})
            if op == "say":
                # 台词插值：${变量名} → 当前值（缺变量警告 + 空串，不崩；旧 {变量名} 兼容）
                text = _interpolate(ins["text"], st["vars"], line)
                entry = {"char": ins["char"], "text": text}
                if ins.get("layout"):   # 整屏独白（@[[...]]）：布局随台词进 history/事件
                    entry["layout"] = ins["layout"]
                # P44-D：标记该台词是否在本次会话中已浏览过（SKIP viewed 模式据此停止）
                already_read = line in self._read_lines
                self._read_lines.add(line)
                event = {"type": "say", "char": ins["char"], "text": text,
                         "line": line, "read": already_read}
                if ins.get("layout"):
                    event["layout"] = ins["layout"]
                frame[1] += 1
                # @voice 紧跟合并（parser 已保证相邻）：消费下一条 voice 指令，语音挂在台词上
                lst = self._lists[frame[0]]
                if frame[1] < len(lst) and lst[frame[1]].get("op") == "voice":
                    entry["voice"] = lst[frame[1]]["sound"]
                    event["voice"] = lst[frame[1]]["sound"]
                    frame[1] += 1
                st["history"].append(entry)
                return self._emit(event)
            if op == "set":
                frame[1] += 1  # 先推进下标：执行失败也跳过本条，避免反复重试同一条卡死
                try:
                    value = self._exec_set(st, ins)
                except RuntimeError as e:
                    print(f'[剧本警告] 第 {line} 行 @set 执行失败，已跳过：{e}', file=sys.stderr)
                    continue
                # 表达式赋值的 value 为求值结果；旧的数值写法保持原事件字段（ins["value"]）
                event_value = value if "expr" in ins else ins["value"]
                return self._emit({"type": "set", "var": ins["var"], "operator": ins["operator"],
                                   "value": event_value, "line": line})
            if op == "jump":
                st["stack"] = self._jump_stack(ins["target"], line)  # 重置整个栈（含 if 父帧）
                return self._emit({"type": "jump", "target": ins["target"], "line": line})
            if op == "if":
                frame[1] += 1  # 先推进：条件求值失败跳过整个 if 块，不卡死
                try:
                    taken = self._eval_cond(st, ins["cond"])
                except (RuntimeError, expr_api.ExprError, TypeError) as e:
                    print(f'[剧本警告] 第 {line} 行 @if 条件求值失败，已跳过该分支：{e}', file=sys.stderr)
                    continue
                if taken:
                    st["stack"].append([ins["_body_id"], 0])  # 压栈执行 body
                elif ins.get("_else_id") is not None:  # P26 T2：@elif/@else 链走 else 体
                    st["stack"].append([ins["_else_id"], 0])
                return self._emit({"type": "if", "cond": ins["cond"], "taken": taken, "line": line})
            if op == "choice":  # 暂停：不推进下标，等 choose()
                try:
                    options = [{"text": o["text"], "target": o["target"],
                                "available": o.get("cond") is None or self._eval_cond(st, o["cond"])}
                               for o in ins["options"]]
                except (RuntimeError, expr_api.ExprError, TypeError) as e:
                    print(f'[剧本警告] 第 {line} 行 @choice 选项条件求值失败，已跳过：{e}', file=sys.stderr)
                    frame[1] += 1
                    continue
                if not any(o["available"] for o in options):
                    # 全部不可选：不能把玩家卡死在选项界面。按第一项自动推进并告警。
                    first = options[0]
                    print(f'[剧本警告] 第 {line} 行：所有选项都不可选，已自动选择「{first["text"]}」'
                          f'（→ {first["target"]}），请检查选项条件', file=sys.stderr)
                    st["stack"] = self._jump_stack(first["target"], line)
                    return self._emit({"type": "choice", "options": copy.deepcopy(options),
                                       "line": line, "forced": first["target"]})
                st["pending_choice"] = {"options": options, "line": line}
                return self._emit({"type": "choice", "options": copy.deepcopy(options), "line": line})
            if op == "end":
                st["finished"] = True
                frame[1] += 1
                return self._emit({"type": "end", "line": line})
            if op == "plug":
                frame[1] += 1  # 一次性指令：先推进下标再执行，与 @set 一致
                name = ins["plugin"]
                handler = self._commands.get(name)
                if handler is None:
                    handler = _COMMANDS.get(name)  # 直接 register_command 注册的兜底
                if handler is None:
                    raise RuntimeError(
                        f'第 {line} 行：插件指令 "@plug:{name}" 未注册：'
                        f"请检查剧本目录下的 plugins/ 目录是否有注册该指令的插件")
                try:
                    result = handler(st, list(ins.get("args") or []))
                except Exception as e:  # 可中断铁律：一个坏插件不能卡死游戏
                    print(f'[插件错误] @plug:{name} 执行失败：{e}', file=sys.stderr)
                    return self._emit({"type": "plug:error", "plugin": name, "line": line})
                if result is None:  # 静默 handler：只改 state，不产生事件，同 step 内继续
                    continue
                if isinstance(result, dict):
                    result["line"] = line
                    return self._emit(result)
                print(f'[插件错误] @plug:{name} 的返回值必须是 dict 或 None，'
                      f"实际为 {type(result).__name__}，已忽略", file=sys.stderr)
                return self._emit({"type": "plug:error", "plugin": name, "line": line})
            if op == "chapter":
                # U12：章节卡——画面独占播放，同时借用 @wait 的暂停机制让剧情等它播完
                secs = float(ins.get("secs") or 1.2)
                st["pending_wait"] = {"seconds": secs}
                frame[1] += 1
                return self._emit({"type": "chapter", "title": ins["title"],
                                   "secs": secs, "line": line})
            if op == "wait":
                # @wait 暂停推进：设置 pending_wait，推进下标（下一条已就绪），等 demo 倒计时完再调 step()
                st["pending_wait"] = {"seconds": float(ins["seconds"])}
                frame[1] += 1
                return self._emit({"type": "wait", "seconds": float(ins["seconds"]), "line": line})
            if op == "voice":  # 正常已被上一条 say 合并消费；单独出现（如 inject）时静默跳过
                frame[1] += 1
                continue
            # spec 里没有的指令直接报错（红线：不新增 DSL 指令）
            raise RuntimeError(f'第 {line} 行：未知指令类型 "{op}"（runtime 无法执行）')

    def choose(self, index: int) -> dict:
        """pending_choice 非空时替玩家选择，跳转到目标标签，返回 snapshot。"""
        st = self._require_state()
        pc = st["pending_choice"]
        if pc is None:
            raise RuntimeError("当前没有待处理的选项")
        options = pc["options"]
        if isinstance(index, bool) or not isinstance(index, int) or not (0 <= index < len(options)):
            raise RuntimeError(f"选项序号 {index} 越界，可用范围 0~{len(options) - 1}")
        opt = options[index]
        if not opt["available"]:
            raise RuntimeError(f'选项 "{opt["text"]}" 当前不可选（条件未满足）')
        st["stack"] = self._jump_stack(opt["target"], pc["line"])
        st["pending_choice"] = None
        return self.snapshot()

    def run_to(self, label: str) -> dict:
        """执行到指定标签处暂停（停在标签上，下一条 step 从标签后开始）。

        到达目标前遇到 choice 暂停或剧本结束，也会停下并返回当前 state。
        """
        st = self._require_state()
        if label not in self._labels:
            raise RuntimeError(f'找不到标签 "{label}"')
        while not st["finished"]:
            if st["pending_choice"] is not None:
                break  # 可中断铁律：暂停等 choose
            ins = self._peek()
            if ins is None:
                self.step()  # 触发自然结束（emit end）
                break
            if ins.get("op") == "label":
                if ins.get("name") == label:
                    break  # 到达目标
                st["stack"][-1][1] += 1  # 跳过非目标标签（不占 step 名额、不进 trace）
                continue
            self.step()
        return self.snapshot()

    def set_var(self, name: str, value) -> dict:
        """直接改变量（AI 控制原语，不产生 trace 事件）。变量不存在时自动创建。"""
        st = self._require_state()
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise RuntimeError(f"set_var 的值必须是数字（收到 {type(value).__name__}: {value!r}）")
        st["vars"][name] = value
        return self.snapshot()

    def snapshot(self) -> dict:
        """导出完整 GameState 的深拷贝（JSON 可序列化）。内部索引与 trace 不进 snapshot。"""
        return copy.deepcopy(self._require_state())

    def seen_sprites(self) -> list[str]:
        """当前会话已见过的角色立绘（"char_expr"，不进存档，读档后重置）。"""
        return list(self._seen_sprites)

    def gallery(self) -> list[str]:
        """已解锁 CG 名列表（进存档）。"""
        return list(self._require_state().get("gallery") or [])

    def pending_wait_seconds(self) -> float:
        """当前等待剩余秒数（无等待返回 0.0）。demo 主循环每帧调一次 advance_wait(dt) 推进倒计时。"""
        st = self._require_state()
        w = st.get("pending_wait")
        return float(w["seconds"]) if isinstance(w, dict) else 0.0

    def advance_wait(self, dt_seconds: float) -> None:
        """倒计时 @wait：dt_seconds 秒流逝，剩余时间减少；到 0 自动清除 pending_wait。

        demo 主循环每帧调一次，dt_seconds 来自 renderer 帧间隔。
        """
        st = self._require_state()
        w = st.get("pending_wait")
        if not isinstance(w, dict):
            return
        left = float(w.get("seconds", 0.0)) - float(dt_seconds)
        if left <= 0:
            st["pending_wait"] = None
        else:
            w["seconds"] = left

    def trace(self) -> list[dict]:
        """已执行事件的日志拷贝，每个事件带从 1 开始的自增 seq。"""
        return copy.deepcopy(self._events)

    def inject(self, instructions: list[dict], at="here") -> dict:
        """在当前帧当前位置（当前指令之前）插入指令，插入后从插入处继续执行。"""
        st = self._require_state()
        if at != "here":
            raise NotImplementedError('目前只支持 at="here"，其他位置留待后续版本')
        if not isinstance(instructions, list) or not all(isinstance(i, dict) for i in instructions):
            raise RuntimeError("inject 的指令必须是 list[dict]")
        try:
            # JSON 往返：深拷贝 + 校验可序列化（防止调用方持有引用、或塞进对象）
            copied = json.loads(json.dumps(instructions, ensure_ascii=False))
        except (TypeError, ValueError) as e:
            raise RuntimeError(f"inject 的指令必须是 JSON 可序列化的（{e}）")
        self._pop_exhausted()
        if not st["stack"]:
            raise RuntimeError("剧本已执行完，没有可注入的当前位置")
        frame = st["stack"][-1]
        lst = self._lists[frame[0]]
        lst[frame[1]:frame[1]] = copied
        # 重建索引：登记注入内容里的新标签 / 新 if body，并修正同列表后续标签的下标
        self._index_root(self._lists[0])
        return self.snapshot()

    def screenshot(self, path=None):
        raise NotImplementedError("截图由渲染层（renderer）提供，runtime 不支持")

    # ---- 存档 / 读档 ----

    def save(self, slot) -> str:
        """存档：生成锚点栈，把 GameState + 锚点写入存档位，返回文件路径。"""
        self._require_state()
        self._pop_exhausted()  # 先弹出已走完的帧，保证快照与锚点一致
        return save_api.save(self.snapshot(), slot, self._anchor_stack())

    def load_save(self, slot) -> dict:
        """读档：重新加载剧本 → 按锚点重建执行栈 → 覆盖其余状态，返回 snapshot。

        剧本已改动导致锚点失效时抛 RuntimeError（中文）。
        """
        data = save_api.load(slot)  # 不存在/损坏 → SaveError
        saved = data["state"]
        script = saved.get("script")
        if not isinstance(script, str) or not script:
            raise RuntimeError("存档失效：存档里缺少剧本路径")
        if "anchor_stack" not in data:
            raise RuntimeError("存档版本过旧，请重新存档")
        anchors = data["anchor_stack"]
        if not isinstance(anchors, list):
            raise RuntimeError("存档失效：锚点信息格式不正确")
        if saved.get("stack") and not anchors:
            raise RuntimeError("存档失效：缺少锚点信息")

        # 用存档里的剧本路径重新加载（重建指令列表/标签/if body 索引）
        if not Path(script).is_file():
            raise RuntimeError(f"存档失效：剧本文件不存在（{script}）")
        try:
            self.load(script)
        except FileNotFoundError:
            raise RuntimeError(f"存档失效：剧本文件不存在（{script}）")
        except GalSyntaxError as e:
            raise RuntimeError(f"存档失效：剧本已改动，无法解析（{e}）")

        self._restore_anchor_stack(anchors)
        # 其余状态直接采用存档值（重新 load 的初始值被覆盖）。
        # 除 script/stack 外全量覆盖：插件往 state 加的自定义字段也随之还原。
        for key, value in saved.items():
            if key not in ("script", "stack"):
                self._state[key] = copy.deepcopy(value)
        return self.snapshot()

    # ==================== 内部实现 ====================

    def _load_plugins(self) -> None:
        """扫描 {剧本目录}/plugins/*.py 并逐模块加载（模块顶层调 register_command 注册）。

        每次 load() 都重新扫描——换掉/删掉插件后重新 load 即生效。
        注册表存进本实例（self._commands），同进程多个 Runtime（编辑器预览）
        各自加载插件时不会互相清空。
        目录不存在 → 跳过；单个插件加载失败 → 中文警告到 stderr，不崩，继续加载其余。
        """
        global _COMMANDS
        registry: dict = {}
        previous = _COMMANDS
        _COMMANDS = registry  # 加载期间插件顶层 register_command 写进本次注册表
        try:
            plugins_dir = Path(self._state["script"]).resolve().parent / "plugins"
            if plugins_dir.is_dir():
                for path in sorted(plugins_dir.glob("*.py")):  # 文件名排序：加载顺序确定
                    try:
                        spec = importlib.util.spec_from_file_location(f"gal_plugin_{path.stem}", path)
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)
                    except Exception as e:
                        print(f"[插件警告] 加载 plugins/{path.name} 失败：{e}", file=sys.stderr)
        finally:
            _COMMANDS = previous
        self._commands = registry

    def _require_state(self) -> dict:
        if self._state is None:
            raise RuntimeError("尚未加载剧本，请先调用 load()")
        return self._state

    def _emit(self, event: dict) -> dict:
        """事件进 trace，附自增 seq（从 1 开始）。"""
        event["seq"] = len(self._events) + 1
        self._events.append(event)
        return event

    def _pop_exhausted(self) -> None:
        """弹出已走完的栈帧（下标越界即走完）。"""
        st = self._state
        while st["stack"] and st["stack"][-1][1] >= len(self._lists[st["stack"][-1][0]]):
            st["stack"].pop()

    def _peek(self) -> dict | None:
        """看当前待执行指令（不推进）；栈空返回 None。"""
        self._pop_exhausted()
        st = self._state
        if not st["stack"]:
            return None
        frame = st["stack"][-1]
        return self._lists[frame[0]][frame[1]]

    def _index_root(self, top: list[dict]) -> None:
        """全量重建列表 / 标签索引。顶层列表固定为 0 号。"""
        self._lists = {0: top}
        self._labels = {}
        self._next_id = 1
        self._walk(0, top)

    def _walk(self, list_id: int, instrs: list[dict]) -> None:
        for i, ins in enumerate(instrs):
            op = ins.get("op")
            if op == "label":
                self._labels[ins["name"]] = (list_id, i)
            elif op == "if":
                body = ins.get("body")
                if not isinstance(body, list):
                    raise RuntimeError(f'第 {ins.get("line", "?")} 行：if 指令缺少 body 列表')
                bid = self._next_id
                self._next_id += 1
                self._lists[bid] = body
                ins["_body_id"] = bid  # 运行时内部字段，不进 GameState
                self._walk(bid, body)
                # P26 T2：@elif/@else 链（elif 是嵌套 if，也是列表）
                else_body = ins.get("else_body")
                if isinstance(else_body, list):
                    eid = self._next_id
                    self._next_id += 1
                    self._lists[eid] = else_body
                    ins["_else_id"] = eid
                    self._walk(eid, else_body)

    def _label_at(self, target: str, line) -> tuple[int, int]:
        if target not in self._labels:
            raise RuntimeError(f'第 {line} 行：找不到标签 "{target}"')
        return self._labels[target]

    def _jump_stack(self, target: str, line) -> list[list[int]]:
        """跳到目标标签的完整栈：目标在 @if 体内时补上父帧，跑完 body 会回到 if 之后，
        而不是整部游戏直接结束。"""
        lid, idx = self._label_at(target, line)
        owners = self._if_body_owners()
        frames: list[list[int]] = []
        cur, seen = lid, set()
        while cur in owners and cur not in seen:
            seen.add(cur)
            pl, pi, _branch = owners[cur]
            frames.append([pl, pi + 1])   # 父 if 已执行完：body 结束后从 if 的下一条继续
            cur = pl
        frames.reverse()
        frames.append([lid, idx])
        return frames

    # ---- 存档锚点：把临时列表下标换成"label 名 + 偏移"，读档时重新定位 ----

    def _anchor_stack(self) -> list[dict]:
        """把 state["stack"] 的每一帧转成可跨运行还原的锚点。"""
        st = self._require_state()
        return [self._anchor_frame(lid, idx) for lid, idx in st["stack"]]

    def _anchor_frame(self, lid: int, idx: int) -> dict:
        """单帧 → 锚点。

        1) 列表内向上最近的 @label（下标 ≤ idx）→ label 锚 + 偏移
        2) 该列表是某个 if 的 body（body 里没有 label）→ 递归锚定父 if 指令
        3) 顶层且无 label → top 锚 + 偏移
        """
        lst = self._lists[lid]
        for j in range(min(idx, len(lst) - 1), -1, -1):
            if lst[j].get("op") == "label":
                return {"kind": "label", "name": lst[j]["name"], "offset": idx - j}
        owner = self._if_body_owners().get(lid)
        if owner is not None:
            pl, pi, branch = owner
            anchor = {"kind": "ifbody", "parent": self._anchor_frame(pl, pi), "offset": idx}
            if branch == "else":  # P26 T2：else/elif 体要标注分支，读档才能还原
                anchor["branch"] = "else"
            return anchor
        return {"kind": "top", "offset": idx}

    def _if_body_owners(self) -> dict[int, tuple[int, int, str]]:
        """反向索引：if/else 体列表ID -> (父 if 所在的列表ID, 下标, 分支 body/else)。"""
        owners: dict[int, tuple[int, int, str]] = {}
        for lid, instrs in self._lists.items():
            for i, ins in enumerate(instrs):
                if ins.get("op") == "if":
                    if "_body_id" in ins:
                        owners[ins["_body_id"]] = (lid, i, "body")
                    if "_else_id" in ins:
                        owners[ins["_else_id"]] = (lid, i, "else")
        return owners

    def _restore_anchor_stack(self, anchors: list[dict]) -> None:
        """把锚点栈还原为 state["stack"]；锚点失效抛中文 RuntimeError。"""
        st = self._require_state()
        owners = self._if_body_owners()

        def restore(anchor: dict) -> list[int]:
            if not isinstance(anchor, dict):
                raise RuntimeError("存档失效：锚点信息格式不正确")
            kind = anchor.get("kind")
            try:
                offset = int(anchor.get("offset", 0))
            except (TypeError, ValueError):
                raise RuntimeError("存档失效：锚点偏移不是数字")
            if kind == "top":
                top = self._lists[0]
                return [0, max(0, min(offset, len(top) - 1))]
            if kind == "label":
                name = anchor.get("name")
                if name not in self._labels:
                    raise RuntimeError(f"存档失效：剧本已改动（找不到锚点 {name}）")
                lid, li = self._labels[name]
                return [lid, max(0, min(li + offset, len(self._lists[lid]) - 1))]
            if kind == "ifbody":
                parent = anchor.get("parent")
                if not isinstance(parent, dict):
                    raise RuntimeError("存档失效：剧本已改动（if 分支锚点缺少父级）")
                pl, pi = restore(parent)
                ins = self._lists[pl][pi]
                branch = anchor.get("branch") or "body"
                bid = None
                if ins.get("op") == "if":
                    bid = ins.get("_else_id") if branch == "else" else ins.get("_body_id")
                if bid is None or bid not in owners:
                    raise RuntimeError("存档失效：剧本已改动（找不到 if 分支锚点）")
                return [bid, max(0, min(offset, len(self._lists[bid]) - 1))]
            raise RuntimeError(f"存档失效：未知锚点类型 {kind!r}")

        st["stack"] = [restore(a) for a in anchors]

    @staticmethod
    def _show(st: dict, ins: dict) -> None:
        char, expr_name = ins["char"], ins["expr"]
        anim = ins.get("anim") or "呼吸"
        for s in st["sprites"]:
            if s["char"] == char:
                s["expr"] = expr_name
                s["anim"] = anim
                for key in ("pos", "scale", "z", "x", "y"):  # 本次未写的布局参数回到缺省（不留上一次的）
                    if key in ins:
                        s[key] = ins[key]
                    else:
                        s.pop(key, None)
                if ins.get("layers"):  # 分层组合同理：本次没写就回整张立绘
                    s["layers"] = dict(ins["layers"])
                else:
                    s.pop("layers", None)
                return
        entry = {"char": char, "expr": expr_name, "anim": anim}
        for key in ("pos", "scale", "z", "x", "y"):
            if key in ins:
                entry[key] = ins[key]
        if ins.get("layers"):
            entry["layers"] = dict(ins["layers"])
        st["sprites"].append(entry)

    @staticmethod
    def _exec_set(st: dict, ins: dict):
        var, operator = ins["var"], ins["operator"]
        # P29 P0-2：表达式求值失败（如除零）抛 ExprError，这里翻译成 RuntimeError 中文，
        # 由 step() 的兜底统一捕获并跳过，不让玩家闪退。
        try:
            if "expr" in ins:
                value = expr_api.evaluate(ins["expr"], st["vars"])
            else:
                value = ins["value"]
        except expr_api.ExprError as e:
            raise RuntimeError(f'变量 "{var}" 的表达式有误：{e}') from None
        cur = st["vars"].get(var, 0)  # 未定义变量默认 0
        # P29 P0-1：字符串 += 数字、或数字 -= 字符串 → TypeError 会冒泡崩游戏。
        # 这里翻译成 RuntimeError 中文；同型运算（str+=str / num+=num / num-=num）正常放行。
        try:
            if operator == "+=":
                st["vars"][var] = cur + value
            elif operator == "-=":
                st["vars"][var] = cur - value
            elif operator == "=":
                st["vars"][var] = value
            else:
                raise RuntimeError(f'不支持的变量运算符 "{operator}"')
        except TypeError:
            cur_t = type(cur).__name__
            val_t = type(value).__name__
            raise RuntimeError(
                f'变量 "{var}" 类型不匹配：当前是 {cur_t}，'
                f'无法 {operator} {val_t}（字符串只能 += 字符串，数字之间才能 + / -）'
            ) from None
        return st["vars"][var]

    @staticmethod
    def _eval_cond(st: dict, cond: dict) -> bool:
        if "expr" in cond:  # 组合条件（and/or/not、括号、四则、比较）
            return bool(expr_api.evaluate(cond["expr"], st["vars"]))
        cur = st["vars"].get(cond["var"], 0)  # 未定义变量默认 0
        value, op = cond["value"], cond["op"]
        try:
            if op == ">=":
                return cur >= value
            if op == "<=":
                return cur <= value
            if op == "==":
                return cur == value
            if op == "!=":
                return cur != value
            if op == ">":
                return cur > value
            if op == "<":
                return cur < value
        except TypeError:
            raise TypeError(
                f'条件比较类型不匹配：变量 "{cond["var"]}" 当前为 {type(cur).__name__}，'
                f'无法与 {type(value).__name__} 进行 {op} 比较')
        raise RuntimeError(f'不支持的条件运算符 "{op}"')
