# -*- coding: utf-8 -*-
"""MYONL 台词富文本：类 Word 的局部样式标记（P46）。

剧本台词里可写内联标记，渲染层按样式分段绘制：

    {b}粗体{/b}  {i}斜体{/i}
    {color=#ff6666}红字{/color}  {color=red}颜色名也行{/color}
    {size=40}大字{/size}
    {{ 与 }} 输出字面花括号；标记可嵌套；未闭合的标记在句尾自动闭合；
    不识别的 {标签} 按原文显示（不吞字）。

设计约束：
- 折行仍按正文字号对「去标记后的纯文本」计算（与 _wrap_text 完全一致），
  样式只影响绘制，不影响分页/行数——保证老剧本版式零变化；
- 打字机按可视字符计数（标记不占字符）；
- 本模块不 import pygame：字体/颜色解析在渲染层（FontBook 注入）。
"""
from __future__ import annotations

import re

# 样式元组：(bold, italic, color, size)；color 为原始字符串（渲染层解析），size 为 int 或 None
BASE_STYLE = (False, False, None, None)

_TAG = re.compile(r"\{(/?)(b|i|color|size)(=[^}]*)?\}")
_SIZE_RE = re.compile(r"^=\s*(\d{1,3})\s*$")
_ESC_L = "\x00"  # {{ 转义占位符（解析前替换，输出前还原为 {）
_ESC_R = "\x01"  # }} 转义占位符（还原为 }）


def _esc(text: str) -> str:
    return text.replace("{{", _ESC_L).replace("}}", _ESC_R)


def _unesc(text: str) -> str:
    return text.replace(_ESC_L, "{").replace(_ESC_R, "}")


def parse(text: str) -> list:
    """把带标记的台词解析成 [(片段文本, 样式)] 列表。

    - 嵌套用每属性栈恢复（如 {b}粗{color=red}粗红{/color}粗{/b}）；
    - 未闭合标记在文本末尾自动闭合；非法取值（如 size=abc）的标签按原文显示；
    - 返回片段顺序与原文一致，空片段不产生。
    """
    text = _esc(str(text))
    segs: list = []
    bold, italic, color, size = BASE_STYLE
    stacks: dict = {"b": [], "i": [], "color": [], "size": []}
    pos = 0
    for m in _TAG.finditer(text):
        if m.start() > pos:
            segs.append((_unesc(text[pos:m.start()]),
                         (bold, italic, color, size)))
        closing, name, arg = m.group(1), m.group(2), m.group(3)
        literal = False
        if not closing:
            if name == "size":
                sm = _SIZE_RE.match(arg or "")
                if not sm or not (8 <= int(sm.group(1)) <= 128):
                    literal = True  # 非法字号 → 整个标签按原文显示
                else:
                    stacks["size"].append(size)
                    size = int(sm.group(1))
            elif name == "color":
                if not arg or not arg[1:].strip():
                    literal = True
                else:
                    stacks["color"].append(color)
                    color = arg[1:].strip()
            else:
                stacks[name].append(bold if name == "b" else italic)
                if name == "b":
                    bold = True
                else:
                    italic = True
        else:
            if arg:  # {/b=x} 不合法 → 按原文显示
                literal = True
            elif stacks[name]:
                prev = stacks[name].pop()
                if name == "b":
                    bold = prev
                elif name == "i":
                    italic = prev
                elif name == "color":
                    color = prev
                else:
                    size = prev
            else:
                literal = True  # 没有对应的开标签 → 闭标签也按原文显示（对称容错）
        if literal:
            segs.append((_unesc(m.group(0)),
                         (bold, italic, color, size)))
        pos = m.end()
    if pos < len(text):
        segs.append((_unesc(text[pos:]), (bold, italic, color, size)))
    return [(t, s) for t, s in segs if t]


def strip(text: str) -> str:
    """去掉全部标记，返回可视纯文本（打字机计数/回看/选项显示用）。"""
    return "".join(seg for seg, _ in parse(text))


def visible_prefix(text: str, n: int) -> str:
    """截取「恰好 n 个可视字符」的原文前缀（标签完整保留、不计数）。

    结果可能含未闭合标签——parse 会自动闭合，渲染安全；不在标签中间截断。
    转义（{{ }}）先替换为占位符再计数，与 parse/strip 口径一致；
    返回值直接喂给 parse/strip（占位符对二者透明）。
    """
    if n <= 0:
        return ""
    work = _esc(str(text))
    out: list = []
    seen = 0
    pos = 0
    for m in _TAG.finditer(work):
        chunk = work[pos:m.start()]
        take = n - seen
        if len(chunk) >= take:
            out.append(chunk[:take])
            return "".join(out)
        out.append(chunk)
        seen += len(chunk)
        out.append(m.group(0))  # 标签完整带上，不占可视字数
        pos = m.end()
    out.append(work[pos:pos + max(0, n - seen)])
    return "".join(out)


def split_rich_lines(segments: list, plain_lines: list) -> list:
    """按纯文本折行结果把样式片段切成逐行样式行。

    plain_lines 来自 _wrap_text(strip(原文))；本函数只做片段→行的偏移映射，
    不改变折行结果（老剧本版式零变化）。行间换行符不属任何一行。
    """
    # 摊平成逐字符 (char, style)，跳过换行符（_wrap_text 的断行依据）
    chars = [(ch, style) for seg, style in segments for ch in seg if ch != "\n"]
    idx = 0
    rich_lines = []
    for line in plain_lines:
        cur: list = []
        for ch in line:
            if idx < len(chars):
                style = chars[idx][1]
            else:
                style = BASE_STYLE  # 兜底：理论上不会发生
            if cur and cur[-1][1] == style:
                cur[-1][0] += ch
            else:
                cur.append([ch, style])
            idx += 1
        rich_lines.append([(t, s) for t, s in cur])
    return rich_lines


def line_width(rich_line: list, font_of) -> int:
    """样式行像素宽：各片段用各自字体量宽后求和。"""
    return sum(font_of(style).size(seg)[0] for seg, style in rich_line if seg)


class FontBook:
    """按 (字号, 粗体, 斜体) 缓存的字体簿（pygame 合成粗/斜，无需额外字体文件）。"""

    def __init__(self, path, base_size: int):
        self.path = path
        self.base_size = int(base_size)
        self._cache: dict = {}

    def get(self, style=BASE_STYLE):
        bold, italic, _color, size = style
        key = (int(size) if size else self.base_size, bool(bold), bool(italic))
        font = self._cache.get(key)
        if font is None:
            import pygame

            font = pygame.font.Font(self.path, key[0])
            font.set_bold(key[1])
            font.set_italic(key[2])
            self._cache[key] = font
        return font
