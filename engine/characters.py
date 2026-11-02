"""项目级角色库（characters.json，2026-11-01）。

定位：角色 = 一等资产（颜色/对话框布局/立绘表情映射），剧本里的 @character 仍然兼容；
引擎启动时把角色库作为初始角色表，剧本里的 @character 可覆盖同名条目。
"""
from __future__ import annotations

import json
import os
import re

FILE_NAME = "characters.json"
SCHEMA = 1
_COLOR = re.compile(r'^#[0-9a-fA-F]{6}$')


def empty() -> dict:
    return {"schema": SCHEMA, "characters": []}


def _norm_entry(raw: dict) -> dict | None:
    if not isinstance(raw, dict):
        return None
    cid = str(raw.get("id") or raw.get("name") or "").strip()
    if not cid:
        return None
    color = str(raw.get("color") or "#ffffff")
    if not _COLOR.match(color):
        color = "#ffffff"
    kind = str(raw.get("kind") or "default").strip() or "default"
    avatars: dict[str, str] = {}
    raw_av = raw.get("avatars")
    if isinstance(raw_av, dict):
        for k, v in raw_av.items():
            ks, vs = str(k).strip(), str(v).strip()
            if ks and vs:
                avatars[ks] = vs
    # V4：语音前缀（配音文件名约定，如 林晚_）与分层立绘（部位 → 素材名）
    layers: dict[str, str] = {}
    raw_layers = raw.get("layers")
    if isinstance(raw_layers, dict):
        for k, v in raw_layers.items():
            ks, vs = str(k).strip(), str(v).strip()
            if ks and vs:
                layers[ks] = vs
    return {
        "id": cid,
        "name": str(raw.get("name") or cid).strip() or cid,
        "color": color,
        "kind": kind,
        "avatars": avatars,
        "layers": layers,
        "voice": str(raw.get("voice") or "").strip()[:60],
        "notes": str(raw.get("notes") or "")[:500],
    }


def normalize(data) -> dict:
    """把任意输入规整成 {"schema":1,"characters":[...]}（去重、校验颜色/ID）。"""
    if isinstance(data, list):
        data = {"characters": data}
    if not isinstance(data, dict):
        return empty()
    out, seen = [], set()
    for raw in data.get("characters") or []:
        entry = _norm_entry(raw)
        if entry is None or entry["id"] in seen:
            continue
        seen.add(entry["id"])
        out.append(entry)
    return {"schema": SCHEMA, "characters": out}


def path(project_root: str) -> str:
    return os.path.join(project_root, FILE_NAME)


def load(project_root: str) -> dict:
    """读角色库；缺失/损坏返回空库（编辑器里由用户重建）。"""
    try:
        with open(path(project_root), encoding="utf-8") as f:
            return normalize(json.load(f))
    except (OSError, ValueError):
        return empty()


def save(project_root: str, data) -> str:
    normalized = normalize(data)
    target = path(project_root)
    tmp = target + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(normalized, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, target)
    return target


def load_for_script(script_path: str) -> dict[str, dict]:
    """按剧本路径向上找 characters.json（最多 4 层），返回 {id: {color, kind}}。"""
    base = os.path.dirname(os.path.realpath(script_path))
    for _ in range(4):
        target = os.path.join(base, FILE_NAME)
        if os.path.isfile(target):
            data = load(base)
            return {c["id"]: {"color": c["color"], "kind": c["kind"]} for c in data["characters"]}
        parent = os.path.dirname(base)
        if parent == base:
            break
        base = parent
    return {}


_RENAME_OPS = ("show", "hide", "anim")


def usage_in_project(project_root: str, ids=None) -> dict[str, dict]:
    """V4：统计每个角色在工程 .gal 里的引用（跨 @include 文件）。

    计数规则：`@character/@show/@hide/@anim 角色` 与台词行 `@ 角色 文本`；
    台词行只认已注册角色（旁白 `@ 文本` 不计）。
    返回 {角色ID: {"lines": 行数, "files": 文件数}}。
    """
    known = set(str(i) for i in (ids or []))
    op_pat = re.compile(r"^@(?:character|show|hide|anim)\s+(\S+)")
    say_pat = re.compile(r"^@\s+(\S+)")
    out: dict[str, dict] = {}
    for root, dirs, names in os.walk(project_root):
        dirs[:] = [d for d in dirs
                   if d not in ("__pycache__", "build", "dist", "saves", ".git", "src")]
        for name in sorted(names):
            if not name.endswith(".gal"):
                continue
            hit: set[str] = set()
            try:
                with open(os.path.join(root, name), encoding="utf-8") as f:
                    for line in f:
                        t = line.strip()
                        m = op_pat.match(t)
                        if m is None:
                            m = say_pat.match(t)
                            if m is None or m.group(1) not in known:
                                continue
                        cid = m.group(1)
                        entry = out.setdefault(cid, {"lines": 0, "files": 0})
                        entry["lines"] += 1
                        hit.add(cid)
            except OSError:
                continue
            for cid in hit:
                out[cid]["files"] += 1
    return out


def rename_in_project(project_root: str, old: str, new: str) -> dict:
    """把角色 old 改名为 new：先改 characters.json，再同步工程内 .gal 引用。

    改的行：`@character old …`、`@show old …`、`@hide old`、`@anim old …`、台词行 `@ old …`。
    返回 {files, lines}；不碰素材/存档/临时文件。
    """
    old, new = old.strip(), new.strip()
    if not old or not new or old == new:
        raise ValueError("角色名不能为空，且新旧不能相同")
    if not re.fullmatch(r"[^\s@]+", new):
        raise ValueError("新角色名不能包含空白字符")
    data = load(project_root)
    changed = 0
    for c in data["characters"]:
        if c["id"] == old:
            c["id"] = new
            if c["name"] == old:
                c["name"] = new
            changed += 1
    if changed == 0:
        raise ValueError(f"角色库里没有 \"{old}\"")
    save(project_root, data)
    files = 0
    lines = 0
    pat = re.compile(r"^(@)(\s*)(" + re.escape(old) + r")(?=\s|$)")
    pat_show = re.compile(r"^(@(?:show|hide|anim)\s+)(" + re.escape(old) + r")(?=\s|$)")
    pat_char = re.compile(r"^(@character\s+)(" + re.escape(old) + r")(?=\s|$)")
    for root, dirs, names in os.walk(project_root):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", "build", "dist", "saves", ".git")]
        for name in names:
            if not name.endswith(".gal"):
                continue
            path = os.path.join(root, name)
            try:
                with open(path, encoding="utf-8") as f:
                    src = f.read()
            except (OSError, UnicodeDecodeError):
                continue
            out, hit = [], 0
            for line in src.splitlines(keepends=True):
                body = line.rstrip("\r\n")
                eol = line[len(body):]
                if body.startswith("@character "):
                    nb = pat_char.sub(r"\g<1>" + new, body, count=1)
                elif body.startswith(("@show ", "@hide ", "@anim ")):
                    nb = pat_show.sub(r"\g<1>" + new, body, count=1)
                elif body.startswith("@ "):
                    nb = pat.sub(r"\g<1>\g<2>" + new, body, count=1)
                else:
                    nb = body
                if nb != body:
                    hit += 1
                out.append(nb + eol)
            if hit:
                try:
                    with open(path, "w", encoding="utf-8") as f:
                        f.write("".join(out))
                except OSError:
                    continue
                files += 1
                lines += hit
    return {"files": files, "lines": lines, "character": new}
