"""A1：结构化错误对象（解析/运行错误统一形状）。

统一字段：
- summary：一句话人话描述（问题面板「简单」视图 / 状态栏用）
- detail：带文件与行号的原始上下文（「详细」视图 / 日志用）
- hint：可操作建议（「你是不是想写…」，A3 填充；无建议时为空串）
- line：1 起始行号，0 表示文件级错误
- file：相对路径或 ``<string>``

旧字段（message / line / file）由 :meth:`GalSyntaxError.to_dict` 一并保留，
老调用方与老测试无需改动。
"""
from __future__ import annotations

from typing import Any


def error_dict(summary: str, *, detail: str = "", hint: str = "",
               line: int = 0, file: str = "<string>") -> dict[str, Any]:
    """构造统一错误对象；detail 缺省时回落为 summary。"""
    return {
        "summary": summary,
        "detail": detail or summary,
        "hint": hint,
        "line": int(line or 0),
        "file": file or "<string>",
    }


# A3：常见错误猜测表（消息关键词 → 「你是不是想写…」建议）
# 顺序优先：越具体的规则放前面，避免被宽规则抢先命中。
_HINT_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("未知指令",), '指令名可能拼错了。全部指令以 @ 开头，可用「帮助 → 教程」查完整列表；'
                    '写台词请用 "@[角色] 文本"（方括号标角色）或 "@ 文本"（旁白）'),
    (("@character", "颜色"), '颜色要写 6 位十六进制，例如 #aaccff'),
    (("颜色", "十六进制"), '颜色要写 6 位十六进制，例如 #aaccff'),
    (("@voice", "紧跟在一条台词之后"), '把 @voice 移到台词（@ 角色 文本）的下一行，中间不要插入其他指令'),
    (("@include", "文件编码"), '把被引用的剧本另存为 UTF-8（记事本「另存为」里可选）'),
    (("@include", "文件不存在"), '检查文件名与目录层级是否写对，路径相对当前剧本所在目录'),
    (("意外的缩进",), '这一行多缩进了：块外的指令请顶格写，块内才缩进'),
    (("后面需要一段缩进的语句块",), '下一行缩进写块内容，例如 @if 条件 后换行缩进写台词'),
    (('要以 ":" 结尾',), '@if / @elif / @else 的条件行要以冒号结尾：@if 变量 > 数值:',),
    (("@choice", "冒号"), '@choice 要单独一行写成 "@choice:"（带冒号），下面每行选项以 > 开头'),
    (("选项缺少",), '选项格式是 "> 文本 -> 标签"，条件可写在文本后："> 文本: 变量 > 数值 -> 标签"'),
    (("@choice", "->"), '选项格式是 "> 文本 -> 标签"，条件可写在文本后："> 文本: 变量 > 数值 -> 标签"'),
    (("不合法：只能含中英文、数字和下划线",), '名字只能含中文、英文、数字和下划线，去掉空格与标点'),
    (("应为数字",), '这里要写数字（如 0.5、1、24），不要带单位或引号'),
    (("应为整数",), '这里要写整数（如 1、2），不要写小数'),
    (("不支持参数",), '检查参数名拼写，可用参数见提示中列出的列表'),
    (("必须 > 0",), '时长/幅度要大于 0，例如 0.5'),
    (("需要", "个参数"), '按括号里给出的用法补齐参数，参数之间用空格分隔'),
    (("必须是数字",), '这里要写数字，不要写文字或引号'),
)

_MISSING_AT_HINT = '每条指令必须以 @ 开头；台词写成 "@[角色] 文本"（角色）或 "@ 文本"（旁白）'


def suggest_hint(message: str, text: str = "") -> str:
    """按错误消息猜一条可操作建议；猜不到时返回空串（调用方按无建议处理）。

    text 为该行原文，用于「你是不是想写 @…」这类针对原文的提示。
    """
    m = message or ""
    for keywords, hint in _HINT_RULES:
        if all(k in m for k in keywords):
            return hint
    if "每条指令必须以" in m or "后面缺少指令内容" in m:
        raw = (text or "").strip()
        if raw and not raw.startswith("@"):
            head = raw.split()[0]
            if head and not head.startswith(("#", ">")) and len(head) <= 20:
                return f'你是不是想写 "@{head}"？' + _MISSING_AT_HINT
        return _MISSING_AT_HINT
    return ""
