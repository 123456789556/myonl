"""安全表达式求值器：标准库 ast 白名单子集，绝不执行任意 Python。

支持：变量、十进制整数/小数、字符串字面量（"双引号"/'单引号'）、字符串 + 拼接、
四则 + - * /、括号、比较 == != > < >= <=、逻辑 and/or/not。
禁止：属性访问、下标、函数调用、f-string、True/False 字面量、lambda、赋值、__ 开头的名字等。
类型纪律：字符串之间只放行 + 拼接与比较；字符串与数字混合运算/比大小抛 ExprError（中文）。
非法表达式抛 ExprError（中文）；未定义变量按旧语义取 0。
"""
from __future__ import annotations

import ast
import operator

__all__ = ["ExprError", "validate", "evaluate"]

_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}
_CMP_OPS = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Gt: operator.gt,
    ast.Lt: operator.lt,
    ast.GtE: operator.ge,
    ast.LtE: operator.le,
}
_UNARY_OPS = {ast.USub: operator.neg, ast.UAdd: operator.pos, ast.Not: operator.not_}

# 常见非法语法 → 中文原因（其余节点统一报"不支持 xxx 语法"）
_BANNED = {
    ast.Attribute: "属性访问（如 变量.属性）",
    ast.Subscript: "下标访问（如 变量[0]）",
    ast.Call: "函数调用",
    ast.Lambda: "lambda",
    ast.IfExp: "条件表达式（a if b else c）",
    ast.Dict: "字典",
    ast.List: "列表",
    ast.Tuple: "元组",
    ast.Set: "集合",
    ast.JoinedStr: "字符串",
    ast.FormattedValue: "字符串",
    ast.NamedExpr: "赋值表达式",
    ast.Starred: "星号展开",
}


class ExprError(Exception):
    """表达式不合法（中文原因）。"""


def _parse(text: str) -> ast.AST:
    if not isinstance(text, str) or not text.strip():
        raise ExprError("表达式为空")
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError:
        raise ExprError(f'表达式 "{text}" 语法有误')
    return tree.body


def validate(text: str) -> None:
    """校验表达式（只看语法白名单，不求值）。非法抛 ExprError。"""
    _check(_parse(text))


def evaluate(text: str, variables=None):
    """按变量表求值；未定义变量按 0。非法表达式抛 ExprError。"""
    node = _parse(text)
    _check(node)
    return _eval(node, variables or {})


def _check(node: ast.AST) -> None:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float, str)):
            raise ExprError("只支持数字、字符串字面量和变量（不支持 True/False）")
        return
    if isinstance(node, ast.Name):
        if node.id.startswith("__"):
            raise ExprError(f'变量名 "{node.id}" 不合法（不允许 __ 开头）')
        return
    if isinstance(node, ast.BinOp):
        if type(node.op) not in _BIN_OPS:
            raise ExprError("只支持四则运算 + - * /（不支持取模、幂、整除等）")
        _check(node.left)
        _check(node.right)
        return
    if isinstance(node, ast.UnaryOp):
        if type(node.op) not in _UNARY_OPS:
            raise ExprError("不支持该一元运算（只支持负号、正号、not）")
        _check(node.operand)
        return
    if isinstance(node, ast.BoolOp):
        if not isinstance(node.op, (ast.And, ast.Or)):
            raise ExprError("不支持该逻辑运算（只支持 and / or）")
        for value in node.values:
            _check(value)
        return
    if isinstance(node, ast.Compare):
        for op in node.ops:
            if type(op) not in _CMP_OPS:
                raise ExprError("不支持该比较运算（只支持 == != > < >= <=）")
        _check(node.left)
        for value in node.comparators:
            _check(value)
        return
    reason = _BANNED.get(type(node))
    if reason:
        raise ExprError(f"不允许{reason}")
    raise ExprError(f"不支持 {type(node).__name__} 语法")


def _eval(node: ast.AST, variables: dict):
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        return variables.get(node.id, 0)
    if isinstance(node, ast.BinOp):
        left = _eval(node.left, variables)
        right = _eval(node.right, variables)
        if isinstance(left, str) or isinstance(right, str):
            # 字符串只放行 str+str 拼接；str*int、str-str、str+num 等统一中文报错
            if isinstance(node.op, ast.Add) and isinstance(left, str) and isinstance(right, str):
                return left + right
            raise ExprError("字符串只支持 + 拼接，且两边都必须是字符串（不能与数字混合运算）")
        if isinstance(node.op, ast.Div) and right == 0:
            raise ExprError("除数不能为 0")
        return _BIN_OPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp):
        value = _eval(node.operand, variables)
        try:
            return _UNARY_OPS[type(node.op)](value)
        except TypeError:
            raise ExprError("正负号只能用于数字（字符串前只能用 not）") from None
    if isinstance(node, ast.BoolOp):
        values = [bool(_eval(v, variables)) for v in node.values]
        return all(values) if isinstance(node.op, ast.And) else any(values)
    if isinstance(node, ast.Compare):
        left = _eval(node.left, variables)
        for op, comparator in zip(node.ops, node.comparators):
            right = _eval(comparator, variables)
            try:
                if not _CMP_OPS[type(op)](left, right):
                    return False
            except TypeError:
                raise ExprError("字符串和数字不能比大小（== / != 可以混用）") from None
            left = right
        return True
    raise ExprError(f"不支持 {type(node).__name__} 语法")
