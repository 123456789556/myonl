"""项目路径安全校验与多文件工程辅助（多文件解析/标签大纲/include/时间线）。

从 `engine.editor` 拆出的独立模块，保持原有函数名与行为不变；
`engine.editor` 仍按原名重新导出，历史引用无需改动。
"""

from __future__ import annotations

import os
import re
import tempfile
import time

from .parser import GalSyntaxError, parse_file

# 素材名白名单：中文/字母/数字/下划线（章节名复用同一条规则）
_ASSET_NAME = re.compile(r"^[0-9A-Za-z_一-鿿]+$")


def _safe_within(root: str, target: str) -> str:
    """把 target 解析到 root 下的绝对路径；若越界则抛 ValueError。"""
    root_real = os.path.realpath(root)
    candidate = os.path.realpath(os.path.join(root_real, target)) if not os.path.isabs(target) \
        else os.path.realpath(target)
    if candidate != root_real and not candidate.startswith(root_real + os.sep):
        raise ValueError(f"路径越界：{target}")
    return candidate


# ==================== P17 多文件工程（只追加，核心零改动） ====================
_INCLUDE_LINE = re.compile(r"^@include\s+(\S+)")
_TAIL_COMMENT = re.compile(r"\s+#.*$")


_TMP_GAL_RE = re.compile(r"^tmp[a-z0-9_]{8}\.gal$")


def _remove_quiet(path: str, retries: int = 5) -> None:
    """删除临时剧本；Windows 上偶发被其它线程/进程短暂占用，短重试避免残留 tmp*.gal。"""
    for i in range(retries):
        try:
            os.remove(path)
            return
        except FileNotFoundError:
            return
        except OSError:
            if i == retries - 1:
                return
            time.sleep(0.02)


def _cleanup_stale_tmp(root: str, min_age: float = 0.5) -> int:
    """清掉上次异常退出残留的临时剧本（只认 mkstemp 命名 tmpXXXXXXXX.gal）。返回删除数。"""
    now = time.time()
    removed = 0
    try:
        names = os.listdir(root)
    except OSError:
        return 0
    for name in names:
        if not _TMP_GAL_RE.match(name):
            continue
        path = os.path.join(root, name)
        try:
            if now - os.path.getmtime(path) >= min_age:
                os.remove(path)
                removed += 1
        except OSError:
            continue
    return removed


def _is_tmp_gal(name: str) -> bool:
    """判断是否是编辑器预览用的临时剧本（mkstemp 命名：tmp + 8 位随机 + .gal）。"""
    return bool(_TMP_GAL_RE.match(name))


def _list_gal_files(root: str) -> list:
    """递归列出项目下全部 .gal：相对路径（/ 分隔），排序返回。"""
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d != "__pycache__"]
        for fn in filenames:
            if fn.lower().endswith(".gal") and not _is_tmp_gal(fn):
                rel = os.path.relpath(os.path.join(dirpath, fn), root)
                out.append(rel.replace(os.sep, "/"))
    return sorted(out)


def _walk_instrs(instrs):
    """按文档顺序铺平指令流（@if 嵌套体 + @elif/@else 体就地展开；@choice 选项无嵌套指令）。"""
    for i in instrs or []:
        yield i
        if i.get("op") == "if":
            yield from _walk_instrs(i.get("body"))
            yield from _walk_instrs(i.get("else_body"))


def _to_rel(root: str, path, fallback: str) -> str:
    """绝对路径转项目相对路径（/ 分隔）；转换失败返回 fallback。"""
    try:
        return os.path.relpath(path, root).replace(os.sep, "/")
    except (TypeError, ValueError):
        return fallback


def _rel_gal(root: str, rel: str) -> str:
    """校验相对路径指向项目内 .gal 并返回绝对路径；越界/非 .gal 抛 ValueError。"""
    rel = (rel or "").strip().replace("\\", "/").lstrip("/")
    if not rel or not rel.lower().endswith(".gal"):
        raise ValueError("只支持项目内的 .gal 文件")
    return _safe_within(root, rel)


def _check_gal_text(text: str, dir_: str) -> None:
    """在 dir_ 写临时文件做语法检查（@include 以该目录为基准）；有错抛 GalSyntaxError。"""
    fd, tmp = tempfile.mkstemp(suffix=".gal", dir=dir_)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        parse_file(tmp)
    finally:
        _remove_quiet(tmp)


def _parse_at_root(text: str, root: str):
    """把文本写到项目根临时文件再 parse_file（@include 以项目根为基准）。

    返回 (指令列表, 顶层文件真实路径)：include 展开的其它文件指令 file 字段≠顶层路径。
    """
    fd, tmp = _mkstemp_or_explain(root)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        return parse_file(tmp), os.path.realpath(tmp)
    finally:
        _remove_quiet(tmp)


def _mkstemp_or_explain(dir_: str):
    """在 dir_ 建临时 .gal；目录不可写时抛中文 ValueError（供各 API 统一返回 400）。"""
    try:
        return tempfile.mkstemp(suffix=".gal", dir=dir_)
    except OSError as e:
        raise ValueError(
            f"工程目录不可写，无法做语法检查（{dir_}）：请检查目录权限后重试"
        ) from e


def _rel_edit_dir(root: str, rel: str) -> str:
    """正在编辑的 rel 文件所在目录（_rel_gal 校验：.gal + 在项目内）。"""
    return os.path.dirname(_rel_gal(root, rel))


def _parse_rel(text: str, root: str, rel: str) -> list[dict]:
    """把 text 当作 root 下的 rel 文件解析（@include 以该文件所在目录为基准）。

    主文本的语法错误与指令 file 字段都定位到 rel（而非临时文件）；
    @include 展开的其他文件指令保留真实绝对路径。
    """
    dir_ = _rel_edit_dir(root, rel)
    fd, tmp = _mkstemp_or_explain(dir_)
    tmp_real = os.path.realpath(tmp)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        try:
            instrs = parse_file(tmp)
        except GalSyntaxError as e:
            if os.path.realpath(e.source) == tmp_real:
                e.source = rel
                e.args = (f"{rel} 第 {e.line} 行：{e.message}",)
            raise
        for i in _walk_instrs(instrs):
            if i.get("file") and os.path.realpath(i["file"]) == tmp_real:
                i["file"] = rel
        return instrs
    finally:
        _remove_quiet(tmp)


def _new_chapter(root: str, name: str) -> str:
    """新建章节文件（项目根下 name.gal）：白名单 + 不覆盖 + 教学骨架。返回相对路径。"""
    name = (name or "").strip()
    if name.lower().endswith(".gal"):
        name = name[:-4]
    if not name:
        raise ValueError("章节名不能为空")
    if not _ASSET_NAME.fullmatch(name):
        raise ValueError("章节名只支持中文/字母/数字/下划线，不能含空格或符号")
    rel = f"{name}.gal"
    target = os.path.realpath(os.path.join(root, rel))
    try:
        with open(target, "x", encoding="utf-8") as f:
            f.write(f"# 章节：{name}\n@label {name}\n@ 这里是新的一幕，开始写吧。\n")
    except FileExistsError:
        raise ValueError(f"章节「{name}」已存在，换个名字吧（不会覆盖已有文件）")
    return rel


def _collect_project_labels(root: str) -> dict:
    """跨文件收集 @label（文件+行号）与 @jump 目标；解析失败的文件进 errors 不中断。"""
    labels, jumps, errors = [], [], []
    seen = set()
    for rel in _list_gal_files(root):
        try:
            instrs = parse_file(os.path.join(root, rel.replace("/", os.sep)))
        except (GalSyntaxError, OSError, UnicodeDecodeError) as e:
            errors.append({"file": rel, "message": str(e)})
            continue
        for i in _walk_instrs(instrs):
            op = i.get("op")
            if op not in ("label", "jump"):
                continue
            f = _to_rel(root, i.get("file"), rel) if i.get("file") else rel
            key = (op, f, i.get("line"), i.get("name") or i.get("target"))
            if key in seen:  # include 展开造成的重复只收一次
                continue
            seen.add(key)
            if op == "label":
                labels.append({"file": f, "line": i.get("line"), "name": i.get("name")})
            else:
                jumps.append({"file": f, "line": i.get("line"), "target": i.get("target")})
    return {"labels": labels, "jumps": jumps, "errors": errors}


def _resolve_include(root: str, rel: str, line: int) -> dict:
    """解析某文件第 line 行的 @include 目标（相对当前文件所在目录，与 parser 同规则）。"""
    try:
        abs_path = _rel_gal(root, rel)
    except ValueError as e:
        return {"ok": False, "message": str(e)}
    try:
        with open(abs_path, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError as e:
        return {"ok": False, "message": f"读取文件失败：{e}"}
    if not (1 <= line <= len(lines)):
        return {"ok": False, "message": f"行号越界：{line}（共 {len(lines)} 行）"}
    content = _TAIL_COMMENT.sub("", lines[line - 1]).strip()
    m = _INCLUDE_LINE.match(content)
    if not m:
        return {"ok": False, "message": f"第 {line} 行不是 @include 指令"}
    arg = m.group(1)
    child = os.path.realpath(os.path.join(os.path.dirname(abs_path), arg))
    root_real = os.path.realpath(root)
    if child != root_real and not child.startswith(root_real + os.sep):
        return {"ok": False, "message": f"@include 目标越出项目目录：{arg}"}
    return {"ok": True, "target": _to_rel(root, child, arg),
            "exists": os.path.isfile(child)}


def extract_timeline(instrs, top_file: str = "<string>") -> list:
    """场景时间线节点：背景/立绘/音频三条泳道 + 选项节点，带行号。

    只取当前文件（file == top_file）；@include 展开的其它文件指令不计入
    （它们的行号属于别的文件，点击跳转会错位）。
    """
    nodes = []
    for i in _walk_instrs(instrs):
        if i.get("file") not in (None, top_file):
            continue
        op = i.get("op")
        ln = i.get("line")
        if op == "bg":
            nodes.append({"line": ln, "lane": "bg", "kind": "bg", "name": i.get("image"),
                          "label": i.get("image")})
        elif op == "video":
            nodes.append({"line": ln, "lane": "bg", "kind": "video", "name": i.get("name"),
                          "label": i.get("name")})
        elif op == "cg":
            nodes.append({"line": ln, "lane": "bg", "kind": "cg", "name": i.get("name"),
                          "label": "CG " + str(i.get("name"))})
        elif op == "show":
            char, expr = i.get("char"), i.get("expr")
            nodes.append({"line": ln, "lane": "sprite", "kind": "show",
                          "name": f"{char}_{expr}", "label": f"{char} {expr}"})
        elif op == "hide":
            nodes.append({"line": ln, "lane": "sprite", "kind": "hide",
                          "label": i.get("char")})
        elif op == "music":
            nodes.append({"line": ln, "lane": "audio", "kind": "music", "name": i.get("track"),
                          "label": i.get("track")})
        elif op == "sfx":
            nodes.append({"line": ln, "lane": "audio", "kind": "sfx", "name": i.get("sound"),
                          "label": i.get("sound")})
        elif op == "voice":
            nodes.append({"line": ln, "lane": "audio", "kind": "voice", "name": i.get("sound"),
                          "label": i.get("sound")})
        elif op == "choice":
            texts = [o.get("text", "") for o in (i.get("options") or [])]
            nodes.append({"line": ln, "lane": "choice", "kind": "choice",
                          "label": " / ".join(texts), "options": texts})
    return nodes


def scene_state_at(instrs, line: int, top_file: str = "<string>") -> dict:
    """某行处的场景状态：最后 bg / 当前 music / 可见立绘（文档顺序扫到 line 为止）。

    只算当前文件、忽略分支控制流（面板的近似展示，不模拟运行时）。
    """
    bg = music = None
    sprites = {}
    for i in _walk_instrs(instrs):
        if i.get("file") not in (None, top_file):
            continue
        if (i.get("line") or 0) > line:
            continue
        op = i.get("op")
        if op == "bg":
            bg = i.get("image")
        elif op == "music":
            music = i.get("track")
        elif op == "show":
            sprites[i.get("char")] = i.get("expr")
        elif op == "hide":
            sprites.pop(i.get("char"), None)
    return {"bg": bg, "music": music,
            "sprites": [{"char": c, "expr": e} for c, e in sprites.items()]}
