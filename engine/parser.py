"""MYONL 剧本解析器：.gal 文本 ←→ 指令列表。

- 解析：parse_text / parse_file，输出 list[dict]（每条指令带源行号 line）
- 反向：dump_text（指令列表 → .gal 文本）、dumps/loads（JSON）
- 所有语法错误抛 GalSyntaxError，携带 1 起始行号与中文提示。

语法定义见 engine_spec.md 第 3 节。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import expr
from .errors import error_dict, suggest_hint

__all__ = ["GalSyntaxError", "parse_text", "parse_file", "dump_text", "dumps", "loads"]

_HEX6 = re.compile(r"#[0-9a-fA-F]{6}(?![0-9a-fA-F])")
_COLOR = re.compile(r"#[0-9a-fA-F]{6}")
_NAME = re.compile(r"\w+", re.UNICODE)
_SET = re.compile(r"^(\w+)\s*(\+=|-=|=)\s*(-?\d+(?:\.\d+)?)$")
_SET_EXPR = re.compile(r"^(\w+)\s*(\+=|-=|=)\s*(.+)$")
# P28 E5：@set 变量 = "字符串"（只支持 =，不支持引号内的转义）
_SET_STR = re.compile(r'^(\w+)\s*=\s*"([^"]*)"$')
_COND = re.compile(r"^(\w+?)\s*(==|!=|>=|<=|>|<)\s*(-?\d+(?:\.\d+)?)$")
_INLINE_COMMENT = re.compile(r"\s#")
_ANIM_ARG = re.compile(r"anim=(\w+)", re.UNICODE)
_FPS_ARG = re.compile(r"fps=(\d+)")
_INT_ARG = re.compile(r"-?\d+")
_ANIM_PARAMS = ("x", "y", "alpha", "scale")   # P30-C-c：@anim 可补间的立绘参数
_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")
_CAM_KINDS = {"pan", "zoom", "shake", "reset"}
_TRANS_KINDS = {"dissolve", "wipe", "slide"}
_DIRS = {"左", "右", "上", "下"}


class GalSyntaxError(Exception):
    """剧本语法错误。line 为 1 起始的行号（0 表示文件级错误），message 为中文原因。

    A1：除旧字段 message/line/source 外，另提供结构化视图 summary/detail/hint，
    to_dict() 同时输出新字段与旧字段（老调用方不受影响）。
    A3：hint 未显式传入时按消息（+ 出错行原文）自动猜一条建议。
    """

    def __init__(self, line: int, message: str, source: str = "<string>",
                 hint: str | None = None, text: str = ""):
        self.line = line
        self.message = message
        self.source = source
        self._hint = hint
        self._text = text
        super().__init__(f"{source} 第 {line} 行：{message}")

    @property
    def hint(self) -> str:
        """可操作建议；未显式给出时按消息与出错行原文惰性推断（猜不到为空串）。"""
        if self._hint is None:
            self._hint = suggest_hint(self.message, self._text)
        return self._hint

    @property
    def summary(self) -> str:
        """一句话人话描述：只说哪里不对，不带文件行号前缀。"""
        return self.message

    @property
    def detail(self) -> str:
        """详细上下文：文件 + 行号 + 原因，便于复制排查。"""
        return str(self.args[0])

    def to_dict(self) -> dict:
        """统一错误对象（新字段 + 旧字段 message/file/line 兼容）。"""
        d = error_dict(self.summary, detail=self.detail, hint=self.hint,
                       line=self.line, file=self.source)
        d.update({"message": self.message, "file": self.source, "line": self.line})
        return d


def _num(s: str):
    v = float(s)
    return int(v) if v.is_integer() else v


def _fmt_num(v) -> str:
    return str(int(v)) if isinstance(v, float) and v.is_integer() else str(v)


def _strip_comment(line: str) -> str:
    """去注释：整行 # 注释、行内「空白+#」注释；# 后接 6 位十六进制视为颜色。"""
    lstripped = line.lstrip()
    if lstripped.startswith("#") and not _HEX6.match(lstripped):
        return ""
    pos = 0
    while True:
        m = _INLINE_COMMENT.search(line, pos)
        if not m:
            return line.rstrip()
        hash_at = m.end() - 1
        if not _HEX6.match(line, hash_at):
            return line[: m.start()].rstrip()
        pos = m.end()


class _Parser:
    def __init__(self, text: str, source: str, base_dir=None, include_stack=None):
        self.source = source
        self.cur_file = source          # 当前正在解析的行所属文件（报错定位用）
        # 多文件内联展开后的行：(行号, 缩进空格数, 去注释去首尾空白的内容, 源文件)
        self.lines: list[tuple[int, int, str, str]] = []
        self._base_dir = Path(base_dir) if base_dir is not None else Path.cwd()
        self._include_stack = set(include_stack or ())  # 递归链上的真实路径（循环检测）
        self._collect(text, source, self._base_dir)
        self.i = 0
        self.characters: set[str] = set()
        self.labels: dict[str, int] = {}

    def _collect(self, text: str, file: str, base_dir: Path) -> None:
        """收集文本行；遇到顶层 @include 就递归把目标文件内容内联展开到当前位置。"""
        for n, raw in enumerate(text.splitlines(), 1):
            content = _strip_comment(raw)
            if not content.strip():
                continue
            # 行首 Tab 统一按 4 空格展开：缩进层级仍只由空格数决定，
            # 这样从编辑器/记事本里用 Tab 缩进的剧本也能正常解析。
            lead = len(content) - len(content.lstrip("\t "))
            if "\t" in content[:lead]:
                content = content[:lead].replace("\t", "    ") + content[lead:]
            indent = len(content) - len(content.lstrip(" "))
            stripped = content.strip()
            parts = stripped.split(None, 1)
            if parts and parts[0] == "@include":
                if indent > 0:
                    raise GalSyntaxError(n, "@include 只能出现在顶层（不能写在 @if / @choice 块内）", file)
                arg = parts[1].strip() if len(parts) > 1 else ""
                if not arg:
                    raise GalSyntaxError(n, "@include 后面需要文件名，如：@include 章节/第一章.gal", file)
                # 路径基准 = 当前文件所在目录；resolve 用于循环检测与跨文件读取
                target = (Path(base_dir) / arg).resolve()
                if target in self._include_stack:
                    raise GalSyntaxError(n, f"@include 循环引用：{arg}", file)
                try:
                    child_text = target.read_text(encoding="utf-8-sig")
                except FileNotFoundError:
                    raise GalSyntaxError(n, f"@include 文件不存在：{arg}", file)
                except UnicodeDecodeError:
                    raise GalSyntaxError(n, f"@include 文件编码不是 UTF-8：{arg}", file)
                except OSError as e:
                    raise GalSyntaxError(n, f"@include 读取失败：{arg}（{e}）", file)
                self._include_stack.add(target)
                try:
                    self._collect(child_text, str(target), target.parent)
                finally:
                    self._include_stack.discard(target)
                continue
            self.lines.append((n, indent, stripped, file))

    def error(self, line: int, message: str, file=None) -> GalSyntaxError:
        text = ""
        for n, _indent, stripped, f in self.lines:
            if n == line and (file is None or f == file):
                text = stripped
                break
        return GalSyntaxError(line, message, file or self.cur_file or self.source,
                              text=text)

    # ---- 主流程 ----

    def parse(self) -> list[dict]:
        prog = self._block(0)
        self._check_targets(prog)
        return prog

    def _block(self, base_indent: int) -> list[dict]:
        out = []
        while self.i < len(self.lines):
            n, indent, _, file = self.lines[self.i]
            if indent < base_indent:
                break
            if indent > base_indent:
                raise self.error(n, "意外的缩进：该行不属于任何 @if 或 @choice 语句块")
            ins = self._one()
            ins["file"] = file  # 公共字段：该指令实际所在文件（跨文件报错/预检定位）
            if ins["op"] == "voice" and (not out or out[-1]["op"] != "say"):
                raise self.error(ins["line"],
                                 '@voice 必须紧跟在一条台词之后（前一行应是 "@ 角色 文本" 或 "@ 旁白"，中间不能有其他指令）')
            out.append(ins)
        return out

    def _indented_block(self, parent_line: int, parent_indent: int, who: str) -> list[dict]:
        if self.i >= len(self.lines) or self.lines[self.i][1] <= parent_indent:
            raise self.error(parent_line, f"{who} 后面需要一段缩进的语句块（至少一行，且比本行多缩进）")
        return self._block(self.lines[self.i][1])

    def _else_block(self, indent: int):
        """收集 @if 块后面同缩进的 @elif / @else 链（P26 T2）。

        返回 else 体指令列表（@elif 用嵌套 if 指令表示，语义与 if/else 链等价）；
        没有 @elif / @else 紧跟时返回 None（行为与旧剧本完全一致）。
        """
        if self.i >= len(self.lines):
            return None
        n, ind, content, file = self.lines[self.i]
        if ind != indent or not content.startswith("@"):
            return None
        head = content[1:].split(None, 1)[0]
        if head not in ("else:", "else", "elif", "elif:"):
            return None
        self.cur_file = file
        rest = content[1:][len(head):].strip()
        if head in ("else:", "else"):
            if rest not in ("", ":"):
                raise self.error(n, "@else 不需要条件（写法是单独一行 @else:）", file)
            self.i += 1
            return self._indented_block(n, indent, "@else")
        if not rest.endswith(":"):
            raise self.error(n, '@elif 的条件后面要以 ":" 结尾，并接一段缩进语句块', file)
        cond = self._parse_cond(rest[:-1].strip(), n)
        self.i += 1
        body = self._indented_block(n, indent, "@elif")
        nested = {"op": "if", "cond": cond, "body": body, "line": n}
        deeper = self._else_block(indent)  # @elif 后面还能继续 @elif / @else
        if deeper is not None:
            nested["else_body"] = deeper
        return [nested]

    # ---- 单条指令 ----

    def _one(self) -> dict:
        n, indent, content, file = self.lines[self.i]
        self.cur_file = file
        if not content.startswith("@"):
            raise self.error(n, '每条指令必须以 "@" 开头')
        rest = content[1:]
        body = rest.strip()
        if not body:  # 只有 "@"：下一行整行当旁白
            self.i += 1
            return self._say_next(n)
        if body.startswith("["):  # 括号台词：@[名字] 文本 / @[[整屏独白]]
            self.i += 1
            return self._say_bracket(n, body)
        if rest[0].isspace():  # 旁白：@ 文本（已登记角色也可 @ 名字 文本）
            self.i += 1
            return self._say(n, body)

        parts = rest.split(None, 1)
        head = parts[0]
        argstr = parts[1].strip() if len(parts) > 1 else ""
        self.i += 1

        if head == "character":
            # @character 名字 颜色 [kind=布局名]（P0-1：kind 绑定对话框布局，缺省 default）
            parts = argstr.split()
            if len(parts) not in (2, 3):
                raise self.error(n, "@character 需要 2 个参数（名字 颜色），可追加 kind=布局名，"
                                  f"实际给了 {len(parts)} 个")
            name, color = parts[0], parts[1]
            if not _COLOR.fullmatch(color):
                raise self.error(n, f'颜色 "{color}" 不合法：应为 6 位十六进制，如 #aaccff')
            kind = "default"
            if len(parts) == 3:
                if not parts[2].startswith("kind="):
                    raise self.error(n, f'@character 第三个参数应为 kind=布局名，实际为 "{parts[2]}"')
                kind = parts[2][len("kind="):]
                if not kind:
                    raise self.error(n, "@character kind= 后面不能为空")
            if name in self.characters:
                raise self.error(n, f'角色 "{name}" 重复定义')
            self.characters.add(name)
            return {"op": "character", "name": name, "color": color,
                    "kind": kind, "line": n}

        if head in ("bg", "music", "sfx"):
            usage = {"bg": "图片名", "music": "音乐名", "sfx": "音效名"}[head]
            key = {"bg": "image", "music": "track", "sfx": "sound"}[head]
            if head == "sfx":  # @sfx 严格 1 个参数
                (value,) = self._args(n, head, argstr, 1, usage)
                return {"op": head, key: value, "line": n}
            # @bg / @music 允许扩展参数（P26 T3 音乐淡入淡出；P33 @bg fadein）
            parts = argstr.split()
            if not parts:
                if head == "music":
                    raise self.error(n, "@music 需要 1 个参数（音乐名），可追加 fadein=秒 / fadeout=秒")
                raise self.error(n, "@bg 需要 1 个参数（图片名），可追加 fadein=秒")
            ins = {"op": head, key: parts[0], "line": n}
            allowed = ("fadein", "fadeout") if head == "music" else ("fadein",)
            tip = " / ".join(p + "=秒" for p in allowed)
            for part in parts[1:]:
                if "=" not in part:
                    raise self.error(n, f'@{head} 的扩展参数应为 {tip}，实际为 "{part}"')
                name, value = part.split("=", 1)
                if name not in allowed:
                    raise self.error(n, f'@{head} 不支持参数 "{name}="：可用 {tip}')
                try:
                    sec = float(value)
                except ValueError:
                    raise self.error(n, f"{name} 应为数字（秒），实际为 \"{value}\"")
                if sec < 0:
                    raise self.error(n, f"{name} 不能为负数，实际为 {value}")
                if sec > 0:  # fade=0 等同不写（无淡入淡出）
                    ins[name] = _num(value)
            return ins

        if head == "voice":
            (sound,) = self._args(n, head, argstr, 1, "配音文件名")
            # 字段名用 sound 不用 file：file 是全部指令的公共字段（源文件定位，见 _block）
            return {"op": "voice", "sound": sound, "line": n}

        if head == "video":
            parts = argstr.split()
            if len(parts) not in (1, 2):
                raise self.error(n, f"@video 需要 1 个参数（视频名），可追加 fps=帧率，实际给了 {len(parts)} 个")
            fps = 30
            if len(parts) == 2:
                m = _FPS_ARG.fullmatch(parts[1])
                if not m or int(m.group(1)) <= 0:
                    raise self.error(n, f'@video 的第二个参数应为 fps=正整数（如 fps=24），实际为 "{parts[1]}"')
                fps = int(m.group(1))
            return {"op": "video", "name": parts[0], "fps": fps, "line": n}

        if head == "show":
            parts = argstr.split()
            if len(parts) < 2 or len(parts) > 10:
                raise self.error(n, f"@show 需要 2 个参数（角色ID 表情），可追加 anim=动画名 / pos=左|中|右 / scale=0.5~2.0 / z=整数 / x=像素 / y=像素 / 部位:素材，实际给了 {len(parts)} 个")
            char, expr_name = parts[0], parts[1]
            anim, pos, scale, z, pos_x, pos_y = "呼吸", None, None, None, None, None
            layers = None
            for part in parts[2:]:
                if ":" in part:
                    # P30-C-d：分层立绘 部位:素材（默认素材写在 images/layers/角色ID/ 下）
                    layer_part, layer_name = part.split(":", 1)
                    self._check_name(n, layer_part, "部位名")
                    self._check_name(n, layer_name, f'部位 "{layer_part}" 的素材名')
                    layers = layers or {}
                    layers[layer_part] = layer_name
                    continue
                if "=" not in part:
                    raise self.error(
                        n,
                        f'@show 的参数应为 anim=动画名 / pos=左|中|右 / scale=0.5~2.0 / z=整数 / x=像素 / y=像素 / 部位:素材，实际为 "{part}"')
                key, value = part.split("=", 1)
                if key == "anim":
                    if not _ANIM_ARG.fullmatch(part):
                        raise self.error(n, f'@show 的参数应为 anim=动画名（如 anim=walk），实际为 "{part}"')
                    anim = value
                elif key == "pos":
                    if value not in ("左", "中", "右"):
                        raise self.error(n, f'pos 只能是 左/中/右，实际为 "{value}"')
                    pos = value
                elif key == "scale":
                    try:
                        num = float(value)
                    except ValueError:
                        raise self.error(n, f'scale 应为数字（范围 0.5~2.0），实际为 "{value}"')
                    if not (0.5 <= num <= 2.0):
                        raise self.error(n, f"scale 范围 0.5~2.0，实际为 {value}")
                    scale = _num(value)
                elif key == "z":
                    # P30-C-b：立绘层序（大者在上；缺省 0，缺省时绘制顺序与旧版完全一致）
                    if not _INT_ARG.fullmatch(value):
                        raise self.error(n, f'z 应为整数（如 z=1 / z=-1），实际为 "{value}"')
                    z = int(value)
                elif key in ("x", "y"):
                    # 场景视图（可视化）用：相对默认位置的像素偏移，负=左/上
                    if not _INT_ARG.fullmatch(value) or abs(int(value)) > 3000:
                        raise self.error(n, f'{key} 应为 -3000~3000 的整数像素偏移，实际为 "{value}"')
                    if key == "x":
                        pos_x = int(value)
                    else:
                        pos_y = int(value)
                else:
                    raise self.error(
                        n,
                        f'@show 不支持参数 "{key}="：可用 anim=动画名 / pos=左|中|右 / scale=0.5~2.0 / z=整数 / x=像素 / y=像素')
            ins = {"op": "show", "char": char, "expr": expr_name, "anim": anim, "line": n}
            if pos is not None:
                ins["pos"] = pos
            if scale is not None:
                ins["scale"] = scale
            if z is not None:
                ins["z"] = z
            if pos_x is not None:
                ins["x"] = pos_x
            if pos_y is not None:
                ins["y"] = pos_y
            if layers:
                ins["layers"] = layers
            return ins

        if head == "hide":
            (char,) = self._args(n, head, argstr, 1, "角色ID")
            return {"op": "hide", "char": char, "line": n}

        if head == "anim":
            # P30-C-c：给立绘参数挂补间（x / y / alpha / scale）
            parts = argstr.split()
            if len(parts) < 3 or len(parts) > 4:
                raise self.error(
                    n, "@anim 需要 3 个参数（角色ID 参数=起始~结束|目标 秒数），"
                       "可追加 ease=linear|ease_in|ease_out|ease_in_cubic|...（T7 共 22 种）")
            char = parts[0]
            if "=" not in parts[1]:
                raise self.error(n, f'@anim 的参数应为 参数=值（如 x=-100~0），实际为 "{parts[1]}"')
            param, raw = parts[1].split("=", 1)
            if param not in _ANIM_PARAMS:
                raise self.error(n, f'@anim 支持的参数：x / y / alpha / scale，实际为 "{param}"')
            from_value = None
            if "~" in raw:
                left, raw = raw.split("~", 1)
                from_value = self._anim_value(n, param, left)
            to_value = self._anim_value(n, param, raw)
            try:
                secs = float(parts[2])
            except ValueError:
                raise self.error(n, f'@anim 的秒数应为数字，实际为 "{parts[2]}"')
            if secs < 0:
                raise self.error(n, f"@anim 的秒数不能为负，实际为 {parts[2]}")
            ease = "linear"
            if len(parts) == 4:
                if not parts[3].startswith("ease="):
                    raise self.error(
                        n, f'ease 格式应为 ease=<曲线名>，实际为 "{parts[3]}"')
                ease = parts[3][5:]
                # T7：从 timeline.EASINGS 取合法曲线名集合，保持单一数据源
                from .timeline import EASINGS as _EASINGS
                if ease not in _EASINGS:
                    raise self.error(
                        n, f'ease 只能是 {" / ".join(sorted(_EASINGS))} 之一，实际为 "{ease}"')
            ins = {"op": "anim", "char": char, "param": param, "to": to_value,
                   "secs": _num(str(secs)), "ease": ease, "line": n}
            if from_value is not None:
                ins["from"] = from_value
            return ins

        if head == "fg":
            # P30-C-b：前景/特效层贴图（画在立绘之上、UI 遮罩之下）；名称为 无 时清除
            parts = argstr.split()
            if not parts or len(parts) > 4:
                raise self.error(n, "@fg 需要 1 个参数（前景素材名 / 无），可追加 x=像素 / y=像素 / alpha=0~1")
            name = parts[0]
            x = y = 0
            alpha = 1.0
            for part in parts[1:]:
                if "=" not in part:
                    raise self.error(
                        n, f'@fg 的扩展参数应为 x=像素 / y=像素 / alpha=0~1，实际为 "{part}"')
                key, value = part.split("=", 1)
                if key in ("x", "y"):
                    if not _INT_ARG.fullmatch(value):
                        raise self.error(n, f'{key} 应为整数（像素偏移），实际为 "{value}"')
                    if key == "x":
                        x = int(value)
                    else:
                        y = int(value)
                elif key == "alpha":
                    try:
                        num = float(value)
                    except ValueError:
                        raise self.error(n, f'alpha 应为数字（范围 0~1），实际为 "{value}"')
                    if not (0.0 <= num <= 1.0):
                        raise self.error(n, f"alpha 范围 0~1，实际为 {value}")
                    alpha = num
                else:
                    raise self.error(n, f'@fg 不支持参数 "{key}="：可用 x=像素 / y=像素 / alpha=0~1')
            if name not in ("无", "none"):
                self._check_name(n, name, "前景素材名")
            else:
                name = "无"
            return {"op": "fg", "name": name, "x": x, "y": y, "alpha": alpha, "line": n}

        if head == "cg":
            (name,) = self._args(n, head, argstr, 1, "CG 名称")
            return {"op": "cg", "name": name, "line": n}

        if head == "camera":
            parts = argstr.split()
            if len(parts) < 2:
                raise self.error(n, "@camera 需要 子命令(pan/zoom/shake/reset) + 参数")
            kind = parts[0]
            if kind not in _CAM_KINDS:
                raise self.error(n, f'@camera 子命令 "{kind}" 不支持（pan/zoom/shake/reset）')
            args = parts[1:]
            if kind == "pan":
                if len(args) != 2 or args[0] not in _DIRS:
                    raise self.error(n, '@camera pan 格式：@camera pan 方向(左/右/上/下) 秒数')
                try:
                    secs = _num(args[1])
                except ValueError:
                    raise self.error(n, f'@camera pan 的秒数应为数字，实际 "{args[1]}"')
                if secs <= 0:
                    raise self.error(n, "@camera pan 的秒数必须 > 0")
                return {"op": "camera", "kind": "pan", "args": [args[0], secs], "line": n}
            if kind == "zoom":
                if len(args) != 2:
                    raise self.error(n, '@camera zoom 格式：@camera zoom 起始缩放 结束缩放')
                vals = []
                for a in args:
                    try:
                        vals.append(_num(a))
                    except ValueError:
                        raise self.error(n, f'@camera zoom 的缩放比例应为数字，实际 "{a}"')
                return {"op": "camera", "kind": "zoom", "args": vals, "line": n}
            if kind == "shake":
                if len(args) != 2:
                    raise self.error(n, '@camera shake 格式：@camera shake 秒数 幅度')
                try:
                    secs = _num(args[0])
                    amp = _num(args[1])
                except ValueError:
                    raise self.error(n, '@camera shake 的秒数和幅度应为数字')
                if secs <= 0:
                    raise self.error(n, "@camera shake 的秒数必须 > 0")
                return {"op": "camera", "kind": "shake", "args": [secs, amp], "line": n}
            # reset
            if len(args) != 1:
                raise self.error(n, '@camera reset 格式：@camera reset 秒数')
            try:
                secs = _num(args[0])
            except ValueError:
                raise self.error(n, f'@camera reset 的秒数应为数字，实际 "{args[0]}"')
            if secs <= 0:
                raise self.error(n, "@camera reset 的秒数必须 > 0")
            return {"op": "camera", "kind": "reset", "args": [secs], "line": n}

        if head == "transition":
            parts = argstr.split()
            if not parts:
                raise self.error(n, "@transition 需要 子命令(dissolve/wipe/slide) + 参数")
            kind = parts[0]
            if kind not in _TRANS_KINDS:
                raise self.error(n, f'@transition 子命令 "{kind}" 不支持（dissolve/wipe/slide）')
            args = parts[1:]
            if kind == "dissolve":
                if len(args) != 1:
                    raise self.error(n, '@transition dissolve 格式：@transition dissolve 秒数')
                try:
                    secs = _num(args[0])
                except ValueError:
                    raise self.error(n, f'@transition dissolve 的秒数应为数字，实际 "{args[0]}"')
                if secs <= 0:
                    raise self.error(n, "@transition dissolve 的秒数必须 > 0")
                return {"op": "transition", "kind": "dissolve", "args": [secs], "line": n}
            if len(args) != 2 or args[0] not in _DIRS:
                raise self.error(n, f'@transition {kind} 格式：@transition {kind} 方向(左/右/上/下) 秒数')
            try:
                secs = _num(args[1])
            except ValueError:
                raise self.error(n, f'@transition {kind} 的秒数应为数字，实际 "{args[1]}"')
            if secs <= 0:
                raise self.error(n, f"@transition {kind} 的秒数必须 > 0")
            return {"op": "transition", "kind": kind, "args": [args[0], secs], "line": n}

        if head == "wait":
            # @wait 2.0 / @wait 500ms / @wait 1s / @wait 300（无单位默认秒）
            if not argstr:
                raise self.error(n, "@wait 需要等待时长（数字 + 可选单位 s/ms，如 @wait 1.5 / @wait 500ms）")
            raw = argstr.strip()
            unit = "s"
            if raw.endswith("ms"):
                unit, raw = "ms", raw[:-2].strip()
            elif raw.endswith("s"):
                unit, raw = "s", raw[:-1].strip()
            try:
                value = _num(raw)
            except ValueError:
                raise self.error(n, f'@wait 的时长应为数字，实际 "{raw}"')
            if value <= 0:
                raise self.error(n, "@wait 的时长必须 > 0")
            seconds = value / 1000.0 if unit == "ms" else value
            return {"op": "wait", "seconds": seconds, "line": n}

        if head == "chapter":
            # U12：@chapter 第一章 雨夜 [secs=1.2] —— 章节/幕间演出卡（黑场 + 标题）
            if not argstr:
                raise self.error(n, "@chapter 需要章节标题，如 @chapter 第一章 雨夜")
            title_parts = []
            secs = None
            for part in argstr.split():
                if "=" in part:
                    k, v = part.split("=", 1)
                    if k != "secs":
                        raise self.error(n, f"@chapter 不认识的参数 {k}=（只支持 secs=）")
                    try:
                        secs = _num(v)
                    except ValueError:
                        raise self.error(n, f'@chapter 的 secs= 应为数字，实际 "{v}"')
                    if secs <= 0:
                        raise self.error(n, "@chapter 的 secs= 必须 > 0")
                    continue
                title_parts.append(part)
            if not title_parts:
                raise self.error(n, "@chapter 需要章节标题")
            return {"op": "chapter", "title": " ".join(title_parts), "secs": secs, "line": n}

        if head == "label":
            (name,) = self._args(n, head, argstr, 1, "标签名")
            self._check_name(n, name, "标签名")
            if name in self.labels:
                raise self.error(n, f'标签 "{name}" 重复定义')
            self.labels[name] = n
            return {"op": "label", "name": name, "line": n}

        if head == "jump":
            (target,) = self._args(n, head, argstr, 1, "标签名")
            self._check_name(n, target, "标签名")
            return {"op": "jump", "target": target, "line": n}

        if head == "end":
            if argstr:
                raise self.error(n, "@end 不需要参数")
            return {"op": "end", "line": n}

        if head == "set":
            m = _SET.match(argstr)
            if m:
                return {"op": "set", "var": m.group(1), "operator": m.group(2),
                        "value": _num(m.group(3)), "line": n}
            m = _SET_STR.fullmatch(argstr)
            if m:  # P28 E5：字符串变量（台词里用 ${变量} 插值，旧写法 {变量} 兼容）
                return {"op": "set", "var": m.group(1), "operator": "=",
                        "value": m.group(2), "line": n}
            m = _SET_EXPR.fullmatch(argstr)
            if not m:
                raise self.error(
                    n, "变量语句格式应为：@set 变量 += 数值（也支持 -= 和 =），"
                       '或 @set 变量 = 表达式（如 @set 好感 = 好感 + (次数 * 2)），'
                       '或 @set 变量 = "字符串"')
            var, operator, rhs = m.group(1), m.group(2), m.group(3).strip()
            if operator != "=":
                raise self.error(
                    n, f"{operator} 只支持数值（如 @set 好感 += 1）；表达式请用 =（如 @set 好感 = 好感 + 1）")
            try:
                expr.validate(rhs)
            except expr.ExprError as e:
                raise self.error(
                    n, f"非法表达式：{e}（右值支持变量、数字、字符串字面量与 + 拼接、"
                       f"四则 + - * /、括号、比较、and/or/not）")
            return {"op": "set", "var": var, "operator": "=", "expr": rhs, "line": n}

        if head == "if":
            if not argstr.endswith(":"):
                raise self.error(n, '@if 的条件后面要以 ":" 结尾，并接一段缩进语句块')
            cond_text = argstr[:-1].strip()
            cond = self._parse_cond(cond_text, n)
            body = self._indented_block(n, indent, "@if")
            ins = {"op": "if", "cond": cond, "body": body, "line": n}
            else_body = self._else_block(indent)  # P26 T2：@elif / @else 链
            if else_body is not None:
                ins["else_body"] = else_body
            return ins

        if head.split(":")[0] in ("else", "elif"):
            raise self.error(
                n, f'@{head.split(":")[0]} 前面必须紧接一个同缩进的 @if 或 @elif 块'
                   f'（@elif/@else 与对应的 @if 顶格缩进一致）')

        if head == "choice:" or (head == "choice" and argstr == ":"):
            return self._choice(n, indent)

        if head == "choice":
            raise self.error(n, '@choice 后面需要冒号，写法是单独一行 "@choice:"，后接缩进的选项列表')

        if head.startswith("plug:"):
            name = head[5:]
            if not name:
                raise self.error(n, '"@plug:" 后面缺少插件指令名，写法如：@plug:shake 1.0')
            self._check_name(n, name, "插件指令名")
            return {"op": "plug", "plugin": name, "args": argstr.split(), "line": n}

        raise self.error(
            n,
            f'未知指令 "@{head}"。支持的指令：@character @bg @music @sfx @voice @video @show @hide @anim @fg '
            f'@cg @camera @transition @wait "@[角色] 文本"（角色）/ "@ 文本"（旁白） @choice: @jump @label @if @set @end '
            f'（角色台词用方括号，例：@[林晚] 你好。）；插件指令请用 "@plug:" 前缀，如 @plug:shake 1.0',
        )

    # ---- 复合指令 ----

    def _say_next(self, line: int) -> dict:
        """`@` 单独一行：下一行整行当旁白（下一行不能再是 @ 指令）。"""
        if self.i >= len(self.lines):
            raise self.error(line, "@ 后面缺少台词：下一行要写要显示的文本")
        n, _indent, content, file = self.lines[self.i]
        if content.startswith("@"):
            raise self.error(line, "@ 后面缺少台词：下一行不能是另一条 @ 指令")
        self.cur_file = file
        self.i += 1
        return {"op": "say", "char": None, "text": content, "line": n}

    def _say_bracket(self, line: int, body: str) -> dict:
        """括号台词（不需要登记角色、也不会误判旁白里的冒号）：

        @[林晚] 你好。            普通对话框台词（括号不显示）
        @[林晚]                   下一行整行是台词
        @[[林晚]] 那年夏天……       整屏独白（NVL）
        @[[我忽然想起那年夏天。]]   整屏旁白
        """
        nvl = body.startswith("[[")
        start = 2 if nvl else 1
        if nvl:
            close = body.find("]]", start)
            if close < 0:
                raise self.error(line, '括号没有闭合：写 "@[[名字]] 台词"（整屏独白）')
            inner = body[start:close].strip()
            if "[" in inner or "]" in inner:
                raise self.error(line, "整屏独白的 [[...]] 里不能再出现 [ 或 ]")
        else:
            # 单括号允许嵌套：[林晚[老师]] 台词 —— 名字本身带方括号时也能用
            depth, close = 0, -1
            for k in range(start, len(body)):
                ch = body[k]
                if ch == "[":
                    depth += 1
                elif ch == "]":
                    if depth == 0:
                        close = k
                        break
                    depth -= 1
            if close < 0:
                raise self.error(line, '括号没有闭合：写 "@[名字] 台词"')
            inner = body[start:close].strip()
        if not inner:
            raise self.error(line, "括号里缺少角色名或整屏文字")
        if not nvl and len(inner) > 20:
            raise self.error(line, f"角色名太长（最多 20 个字符）：{inner}")
        tail = body[close + (2 if nvl else 1):].strip()
        if tail[:1] in (":", "："):   # 顺手打了冒号也认，冒号不显示
            tail = tail[1:].strip()
        if nvl and not tail:          # @[[整段文字]] → 整屏旁白
            return {"op": "say", "char": None, "text": inner,
                    "layout": "nvl", "line": line}
        if not tail:                  # @[名字] → 下一行整行是台词
            if self.i >= len(self.lines):
                raise self.error(line, f'角色 "{inner}" 的对话缺少文本')
            n, _indent, content, file = self.lines[self.i]
            if content.startswith("@"):
                raise self.error(line, f'角色 "{inner}" 的对话缺少文本')
            self.cur_file = file
            self.i += 1
            return {"op": "say", "char": inner, "text": content, "line": n}
        ins = {"op": "say", "char": inner, "text": tail, "line": line}
        if nvl:
            ins["layout"] = "nvl"
        return ins

    def _say(self, line: int, rest: str) -> dict:
        parts = rest.split(None, 1)
        if parts and parts[0] in self.characters:
            if len(parts) == 1 or not parts[1].strip():
                raise self.error(line, f'角色 "{parts[0]}" 的对话缺少文本')
            return {"op": "say", "char": parts[0], "text": parts[1].strip(), "line": line}
        # 旁白前缀：`@ 旁白 文本` 与文档/报错提示的写法一致，去掉「旁白」再按旁白渲染，
        # 否则画面上会多出一行字「旁白 xxx」。未注册角色时才走这里（注册了按角色台词处理）。
        if parts and parts[0] == "旁白" and len(parts) > 1 and parts[1].strip():
            return {"op": "say", "char": None, "text": parts[1].strip(), "line": line}
        return {"op": "say", "char": None, "text": rest, "line": line}

    def _choice(self, line: int, indent: int) -> dict:
        options = []
        opt_indent = None  # 第一行选项的缩进；整组必须一致（顶格或统一缩进均可）
        while self.i < len(self.lines):
            ln, ind, content, file = self.lines[self.i]
            if not content.startswith(">"):
                break
            if opt_indent is None:
                opt_indent = ind
            elif ind != opt_indent:
                raise self.error(
                    ln, "选项行缩进不一致：同一组选项应对齐（要么全顶格，要么缩进相同）", file)
            self.cur_file = file
            options.append(self._option(ln, content[1:].strip()))
            self.i += 1
        if not options:
            raise self.error(line, '"@choice:" 后面需要选项列表（每行以 > 开头）')
        return {"op": "choice", "options": options, "line": line}

    def _option(self, line: int, body: str) -> dict:
        if "->" not in body:
            raise self.error(line, '选项缺少 "-> 标签"，格式：> 文本: 条件 -> 标签（条件可省略）')
        left, target = body.rsplit("->", 1)
        target = target.strip()
        if not target:
            raise self.error(line, '选项缺少跳转标签（"->" 后面为空）')
        if not _NAME.fullmatch(target):
            raise self.error(line, f'标签名 "{target}" 不合法：只能含中英文、数字和下划线')
        left = left.strip()
        cond = None
        text = left
        if ":" in left:
            t, c = left.rsplit(":", 1)
            cond = self._parse_cond(
                c.strip(), line, "；选项文本中不能含英文冒号，请改用中文“：”")
            text = t.strip()
        if not text:
            raise self.error(line, "选项文本不能为空")
        opt = {"text": text, "target": target}
        if cond:
            opt["cond"] = cond
        return opt

    def _parse_cond(self, text: str, line: int, hint: str = "") -> dict:
        """条件解析：单条件（变量 运算符 数值，六种运算符）或安全表达式。

        单条件保持旧字段 {var, op, value}；表达式条件返回 {expr: 原文}。
        """
        m = _COND.fullmatch(text)
        if m:
            return {"var": m.group(1), "op": m.group(2), "value": _num(m.group(3))}
        try:
            expr.validate(text)
        except expr.ExprError as e:
            raise self.error(
                line,
                f'条件 "{text}" 不合法：{e}。单条件格式为 变量 运算符 数值'
                f"（运算符 == != > < >= <=），也可写组合表达式"
                f"（and/or/not、括号、四则、字符串比较）{hint}")
        return {"expr": text}

    # ---- 工具 ----

    def _args(self, line: int, cmd: str, argstr: str, count: int, usage: str) -> list[str]:
        args = argstr.split()
        if len(args) != count:
            raise self.error(line, f"@{cmd} 需要 {count} 个参数（{usage}），实际给了 {len(args)} 个")
        return args

    def _anim_value(self, line: int, param: str, text: str):
        """@anim 的数值校验：x/y 不限、alpha 0~1、scale 0.5~2.0。"""
        if not _NUMBER.fullmatch(text):
            raise self.error(line, f'@anim 的数值应为数字，实际为 "{text}"')
        value = _num(text)
        if param == "alpha" and not (0.0 <= value <= 1.0):
            raise self.error(line, f"alpha 范围 0~1，实际为 {text}")
        if param == "scale" and not (0.5 <= value <= 2.0):
            raise self.error(line, f"scale 范围 0.5~2.0，实际为 {text}")
        return value

    def _check_name(self, line: int, name: str, what: str) -> None:
        if not _NAME.fullmatch(name):
            raise self.error(line, f'{what} "{name}" 不合法：只能含中英文、数字和下划线')

    def _check_targets(self, prog: list[dict]) -> None:
        def walk(instrs):
            for ins in instrs:
                if ins["op"] == "jump":
                    yield ins["target"], ins["line"], ins.get("file")
                elif ins["op"] == "choice":
                    for o in ins["options"]:
                        yield o["target"], ins["line"], ins.get("file")
                elif ins["op"] == "if":
                    yield from walk(ins["body"])
                    yield from walk(ins.get("else_body") or [])  # P26 T2：@elif/@else 体也要查跳转

        for target, line, file in walk(prog):
            if target not in self.labels:
                raise self.error(line, f'跳转目标 "{target}" 不存在：没有名为 "{target}" 的 @label', file)


# ---- 公开 API ----

def parse_text(text: str, source: str = "<string>") -> list[dict]:
    """把 .gal 文本解析为指令列表。语法错误抛 GalSyntaxError（带行号）。

    @include 的路径基准为当前工作目录；文件剧本请用 parse_file（基准为剧本所在目录）。
    """
    return _Parser(text, source).parse()


def parse_file(path) -> list[dict]:
    """读取 .gal 文件（UTF-8；兼容记事本另存的 BOM）并解析；@include 相对当前文件所在目录展开。"""
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        raise GalSyntaxError(0, f"文件不存在：{p}", source=str(p))
    except UnicodeDecodeError:
        raise GalSyntaxError(0, "文件编码不是 UTF-8，请把剧本另存为 UTF-8", source=str(p))
    return _Parser(text, str(p), base_dir=p.parent, include_stack={p.resolve()}).parse()


def dump_text(instructions: list[dict]) -> str:
    """指令列表 → .gal 文本（与 parse_text 互逆）。"""
    out: list[str] = []
    _dump(instructions, out, 0)
    return "\n".join(out) + "\n"


def _dump(instrs: list[dict], out: list[str], level: int) -> None:
    pad = "    " * level
    for ins in instrs:
        op = ins["op"]
        if op == "character":
            s = f'{pad}@character {ins["name"]} {ins["color"]}'
            if ins.get("kind") not in (None, "", "default"):
                s += f' kind={ins["kind"]}'
            out.append(s)
        elif op in ("bg", "music", "sfx"):
            key = {"bg": "image", "music": "track", "sfx": "sound"}[op]
            s = f"{pad}@{op} {ins[key]}"
            if op == "music":  # P26 T3：淡入淡出参数（0 / 缺省不输出）
                if ins.get("fadein"):
                    s += f' fadein={_fmt_num(ins["fadein"])}'
                if ins.get("fadeout"):
                    s += f' fadeout={_fmt_num(ins["fadeout"])}'
            elif op == "bg" and ins.get("fadein"):  # P33：@bg 淡入
                s += f' fadein={_fmt_num(ins["fadein"])}'
            out.append(s)
        elif op == "voice":
            out.append(f'{pad}@voice {ins["sound"]}')
        elif op == "video":
            s = f'{pad}@video {ins["name"]}'
            if ins.get("fps") not in (None, 30):
                s += f' fps={ins["fps"]}'
            out.append(s)
        elif op == "show":
            s = f'{pad}@show {ins["char"]} {ins["expr"]}'
            if ins.get("anim") not in (None, "呼吸"):
                s += f' anim={ins["anim"]}'
            if ins.get("pos"):
                s += f' pos={ins["pos"]}'
            if ins.get("scale") not in (None, 1, 1.0):
                s += f' scale={_fmt_num(ins["scale"])}'
            if ins.get("z"):
                s += f' z={ins["z"]}'
            if ins.get("x") is not None:
                s += f' x={ins["x"]}'
            if ins.get("y") is not None:
                s += f' y={ins["y"]}'
            for layer_part, layer_name in (ins.get("layers") or {}).items():
                s += f" {layer_part}:{layer_name}"
            out.append(s)
        elif op == "anim":
            s = f'{pad}@anim {ins["char"]} {ins["param"]}='
            if "from" in ins:
                s += f'{_fmt_num(ins["from"])}~'
            s += f'{_fmt_num(ins["to"])} {_fmt_num(ins["secs"])}'
            if ins.get("ease") and ins["ease"] != "linear":
                s += f' ease={ins["ease"]}'
            out.append(s)
        elif op == "fg":
            s = f'{pad}@fg {ins["name"]}'
            if ins.get("x"):
                s += f' x={ins["x"]}'
            if ins.get("y"):
                s += f' y={ins["y"]}'
            if ins.get("alpha") not in (None, 1, 1.0):
                s += f' alpha={_fmt_num(ins["alpha"])}'
            out.append(s)
        elif op == "hide":
            out.append(f'{pad}@hide {ins["char"]}')
        elif op == "cg":
            out.append(f'{pad}@cg {ins["name"]}')
        elif op == "camera":
            args = " ".join(str(a) for a in ins["args"])
            out.append(f'{pad}@camera {ins["kind"]} {args}')
        elif op == "transition":
            args = " ".join(str(a) for a in ins["args"])
            out.append(f'{pad}@transition {ins["kind"]} {args}')
        elif op == "chapter":
            s = f'{pad}@chapter {ins["title"]}'
            if ins.get("secs"):
                s += f' secs={_fmt_num(ins["secs"])}'
            out.append(s)
        elif op == "say":
            if ins.get("layout") == "nvl":  # 整屏独白：dump 回 [[...]] 写法
                out.append(f'{pad}@[[{ins["char"]}]] {ins["text"]}' if ins.get("char")
                           else f'{pad}@[[{ins["text"]}]]')
            elif ins.get("char"):
                # 一律用括号写法：不依赖 @character 登记，卡片/场景视图往返不会把角色台词降级成旁白
                out.append(f'{pad}@[{ins["char"]}] {ins["text"]}')
            else:
                out.append(f'{pad}@ {ins["text"]}')
        elif op == "wait":
            out.append(f'{pad}@wait {_fmt_num(ins["seconds"])}')
        elif op == "set":
            if "expr" in ins:
                out.append(f'{pad}@set {ins["var"]} {ins["operator"]} {ins["expr"]}')
            elif isinstance(ins["value"], str):  # P28 E5：字符串变量 dump 回带引号
                out.append(f'{pad}@set {ins["var"]} {ins["operator"]} "{ins["value"]}"')
            else:
                out.append(f'{pad}@set {ins["var"]} {ins["operator"]} {_fmt_num(ins["value"])}')
        elif op == "label":
            out.append(f'{pad}@label {ins["name"]}')
        elif op == "jump":
            out.append(f'{pad}@jump {ins["target"]}')
        elif op == "end":
            out.append(f"{pad}@end")
        elif op == "if":
            c = ins["cond"]
            if "expr" in c:
                out.append(f'{pad}@if {c["expr"]}:')
            else:
                out.append(f'{pad}@if {c["var"]} {c["op"]} {_fmt_num(c["value"])}:')
            _dump(ins["body"], out, level + 1)
            if ins.get("else_body"):  # P26 T2：@else 体（@elif 会 dump 成 @else: + 内嵌 @if）
                out.append(f"{pad}@else:")
                _dump(ins["else_body"], out, level + 1)
        elif op == "choice":
            out.append(f"{pad}@choice:")
            for o in ins["options"]:
                s = f'{pad}    > {o["text"]}'
                if o.get("cond"):
                    c = o["cond"]
                    s += (f': {c["expr"]}' if "expr" in c
                          else f': {c["var"]} {c["op"]} {_fmt_num(c["value"])}')
                out.append(f'{s} -> {o["target"]}')
        elif op == "plug":
            args = ins.get("args") or []
            suffix = " " + " ".join(str(a) for a in args) if args else ""
            out.append(f'{pad}@plug:{ins["plugin"]}{suffix}')
        else:
            raise ValueError(f'未知指令类型 "{op}"，无法还原为 .gal 文本')


def dumps(instructions: list[dict], **kw) -> str:
    """指令列表 → JSON 字符串。"""
    kw.setdefault("ensure_ascii", False)
    kw.setdefault("indent", 2)
    return json.dumps(instructions, **kw)


def loads(s: str) -> list[dict]:
    """JSON 字符串 → 指令列表。"""
    data = json.loads(s)
    if not isinstance(data, list):
        raise ValueError("指令 JSON 的顶层必须是数组")
    return data
