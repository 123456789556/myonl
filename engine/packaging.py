"""P35 打包发布核心：打包档案、版本迭代、图标、运营号与打包历史。

设计目标：
- 与 PyInstaller 构建解耦：pack_project() 接受 build_func 注入，测试不真打包；
- 所有面向开发者的错误都是中文，并一次列出全部缺失项；
- 打包档案 pack_config.json 跟随游戏目录走，重新打包（版本 +1）时原项目内容不变；
- 打包历史写入 build/pack_history.json，编辑器/CLI 可列出"已打包项目"并继续迭版本。
"""
from __future__ import annotations

import copy
import importlib.util
import json
import os
import re
import shutil
import struct
import sys
from datetime import datetime
from pathlib import Path

PROFILE_NAME = "pack_config.json"
HISTORY_REL = Path("build") / "pack_history.json"
VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
_BAD_NAME_CHARS = set('\\/:*?"<>|')


class PackProfileError(Exception):
    """打包档案/版本/图标错误。中文提示，可直接展示给开发者。"""


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _history_path(root=None) -> Path:
    root = Path(root) if root else _repo_root()
    return root / HISTORY_REL


def _read_json(path: Path, default):
    """读 JSON：兼容 UTF-8 BOM；文件损坏/类型不符时返回默认值，不抛异常。"""
    try:
        raw = path.read_text(encoding="utf-8-sig")
        data = json.loads(raw)
        return data if isinstance(data, type(default)) else default
    except (OSError, ValueError, TypeError):
        return default


def _atomic_write_json(path: Path, data) -> None:
    """原子写：先写临时文件再 os.replace，避免异常退出留下半截 JSON。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def profile_path(project_dir) -> Path:
    return Path(project_dir).resolve() / PROFILE_NAME


def load_profile(project_dir) -> dict:
    """读取打包档案；文件不存在返回空对象（兼容旧项目直接打包）。"""
    path = profile_path(project_dir)
    data = _read_json(path, {})
    return copy.deepcopy(data)


def save_profile(project_dir, profile: dict) -> Path:
    path = profile_path(project_dir)
    _atomic_write_json(path, profile)
    return path


def validate_version(version) -> str:
    text = str(version or "").strip()
    if not VERSION_RE.fullmatch(text):
        raise PackProfileError(f"版本号格式不正确：{text or '(空)'}；请使用 1.0.0 这样的三段数字")
    return text


def bump_version(version, part: str = "patch") -> str:
    """语义化版本递增：patch 1.0.0→1.0.1，minor→1.1.0，major→2.0.0。"""
    match = VERSION_RE.fullmatch(str(version or "").strip())
    if not match:
        raise PackProfileError(f"无法递增版本：{version!r} 不是 1.0.0 格式")
    major, minor, patch = (int(x) for x in match.groups())
    part = str(part or "patch").lower()
    if part == "patch":
        patch += 1
    elif part == "minor":
        minor += 1
        patch = 0
    elif part == "major":
        major += 1
        minor = patch = 0
    else:
        raise PackProfileError(f"未知版本递增方式：{part}（可选 patch / minor / major）")
    return f"{major}.{minor}.{patch}"


def _validate_publisher(publisher, errors: list[str]) -> None:
    if not isinstance(publisher, dict):
        errors.append("缺少运营号配置：请填写 publisher.name 与 publisher.account_id")
        return
    name = str(publisher.get("name") or "").strip()
    account = str(publisher.get("account_id") or "").strip()
    if not name:
        errors.append("运营号名称为空：请在 pack_config.json 的 publisher.name 填写")
    if not account:
        errors.append("运营号 ID 为空：请在 pack_config.json 的 publisher.account_id 填写")


def validate_profile(profile: dict, project_dir=None, check_icon: bool = True) -> list[str]:
    """校验打包必填项，返回中文错误列表（空列表 = 可打包）。"""
    errors: list[str] = []
    if not isinstance(profile, dict):
        return ["打包档案格式错误：应为 JSON 对象"]

    name = str(profile.get("game_name") or "").strip()
    if not name:
        errors.append("游戏名为空：请填写 pack_config.json 的 game_name")
    elif len(name) > 60:
        errors.append(f"游戏名过长：最多 60 个字符，当前 {len(name)} 个")
    elif any(ch in _BAD_NAME_CHARS for ch in name):
        errors.append('游戏名不能包含这些字符：\\ / : * ? " < > |')

    version = str(profile.get("version") or "").strip()
    if not version:
        errors.append("版本号为空：请填写 pack_config.json 的 version（如 1.0.0）")
    elif not VERSION_RE.fullmatch(version):
        errors.append(f"版本号格式不正确：{version}；请使用 1.0.0 这样的三段数字")

    _validate_publisher(profile.get("publisher"), errors)

    icon = str(profile.get("icon") or "").strip()
    if not icon:
        errors.append("游戏图标为空：请填写 pack_config.json 的 icon（PNG 或 ICO）")
    elif check_icon and project_dir is not None:
        icon_path = Path(project_dir) / icon
        if not icon_path.is_file():
            errors.append(f"游戏图标不存在：{icon}（应放在游戏目录内）")
        elif icon_path.suffix.lower() not in (".png", ".ico"):
            errors.append(f"游戏图标格式不支持：{icon}；仅支持 .png 或 .ico")
    return errors


def _rel_key(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def load_history(root=None, history_path=None) -> dict:
    path = Path(history_path) if history_path else _history_path(root)
    data = _read_json(path, {"schema": 1, "projects": {}})
    if not isinstance(data.get("projects"), dict):
        data["projects"] = {}
    data.setdefault("schema", 1)
    return data


def project_history(project_dir, root=None, history_path=None) -> dict:
    root = Path(root) if root else _repo_root()
    key = _rel_key(Path(project_dir), root)
    history = load_history(root, history_path)
    entry = history["projects"].get(key) or {}
    return copy.deepcopy(entry)


def latest_build(project_dir, root=None, history_path=None) -> dict | None:
    builds = project_history(project_dir, root, history_path).get("builds") or []
    return builds[-1] if builds else None


def next_version(project_dir, bump: str = "patch", root=None, history_path=None) -> str:
    """在下一次迭代打包前预览版本号（不写文件）。"""
    profile = load_profile(project_dir)
    latest = latest_build(project_dir, root, history_path)
    base = (latest or {}).get("version") or profile.get("version") or "1.0.0"
    return bump_version(base, bump)


def _png_size(png_bytes: bytes) -> tuple[int, int]:
    """从 PNG IHDR 读取宽高；不是合法 PNG 时抛中文错误。"""
    if len(png_bytes) < 24 or png_bytes[:8] != b"\x89PNG\r\n\x1a\n":
        raise PackProfileError("图标不是有效的 PNG 文件")
    if png_bytes[12:16] != b"IHDR":
        raise PackProfileError("PNG 图标缺少 IHDR 信息，文件可能已损坏")
    width, height = struct.unpack(">II", png_bytes[16:24])
    if width <= 0 or height <= 0:
        raise PackProfileError("PNG 图标尺寸非法")
    return width, height


def png_to_ico(png_path, ico_path) -> Path:
    """把 PNG 包装成单图 ICO（Windows 支持 PNG 压缩图标，无需第三方库）。

    PyInstaller 的 --icon 只接受 .ico；模板默认给 PNG，这里自动转换，
    开发者不必再去找在线转换工具。
    """
    png_path, ico_path = Path(png_path), Path(ico_path)
    data = png_path.read_bytes()
    width, height = _png_size(data)
    if max(width, height) > 256:
        raise PackProfileError(
            f"图标尺寸过大：{width}×{height}；请使用 256×256 或更小的正方形 PNG")
    # ICO 目录项：宽高 0 表示 256；PNG 数据从偏移 22 开始
    ico = struct.pack("<HHH", 0, 1, 1) + struct.pack(
        "<BBBBHHII",
        0 if width >= 256 else width,
        0 if height >= 256 else height,
        0, 0, 1, 32, len(data), 22,
    ) + data
    ico_path.parent.mkdir(parents=True, exist_ok=True)
    ico_path.write_bytes(ico)
    return ico_path


def resolve_icon(project_dir, icon_spec, work_dir) -> Path:
    """定位并规范化图标：ICO 直接返回，PNG 转成 work_dir/icon.ico。"""
    project_dir = Path(project_dir)
    spec = str(icon_spec or "").strip()
    if not spec:
        raise PackProfileError("游戏图标为空")
    icon_path = project_dir / spec
    if not icon_path.is_file():
        raise PackProfileError(f"游戏图标不存在：{icon_path}")
    suffix = icon_path.suffix.lower()
    if suffix == ".ico":
        return icon_path
    if suffix == ".png":
        return png_to_ico(icon_path, Path(work_dir) / "icon.ico")
    raise PackProfileError(f"游戏图标格式不支持：{icon_path.name}；仅支持 .png 或 .ico")


def write_game_info(out_dir, profile: dict, build_number: int, built_at=None) -> Path:
    """在产物根目录写 game_info.json：版本、运营号、构建号随包可查。"""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    publisher = profile.get("publisher") if isinstance(profile.get("publisher"), dict) else {}
    info = {
        "game_name": str(profile.get("game_name") or ""),
        "version": str(profile.get("version") or ""),
        "build_number": int(build_number or 0),
        "built_at": built_at or _now_iso(),
        "publisher": {
            "name": str(publisher.get("name") or ""),
            "account_id": str(publisher.get("account_id") or ""),
            "channel": str(publisher.get("channel") or ""),
            "contact": str(publisher.get("contact") or ""),
        },
        "description": str(profile.get("description") or ""),
        "release_notes": str(profile.get("release_notes") or ""),
        "engine": "MYONL",
    }
    _atomic_write_json(out_dir / "game_info.json", info)
    return out_dir / "game_info.json"


# ---- 内置玩家模板：编辑器发行版（无 Python/PyInstaller）靠复制它来打包 ----
PLAYER_EXE = "MYONLPlayer.exe"
_TEMPLATE_REL = Path("engine") / "templates" / "player"
# 与 pack.py 的 _EXCLUDE_NAMES 对齐：开发/版本控制/内部档案不进玩家产物
_PACK_EXCLUDE_NAMES = {
    ".git", "__pycache__", ".pytest_cache", "build", "dist", "tests", "engine",
    "editor", "screenshots", ".screenshots", "pack.py", "conftest.py",
    ".gitignore", "requirements.txt", "requirements-dev.txt", "src", "saves",
    "pack_config.json", "game_info.json", "icon.ico",
}


def player_template_dir(root=None) -> Path | None:
    """找到可用的玩家模板目录（MYONLPlayer.exe + _internal）；没有返回 None。

    查找顺序：冻结包内置目录（sys._MEIPASS）→ 打包根目录 → 源码树。
    """
    candidates = []
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", None)
        if base:
            candidates.append(Path(base) / _TEMPLATE_REL)
    if root:
        candidates.append(Path(root) / _TEMPLATE_REL)
    candidates.append(Path(__file__).resolve().parent / "templates" / "player")
    for path in candidates:
        if (path / PLAYER_EXE).is_file() and (path / "_internal").is_dir():
            return path
    return None


def _copytree_into(src: Path, dst: Path) -> None:
    """把 src 目录内容合并进 dst（Python 3.7 没有 dirs_exist_ok，手动递归）。"""
    if sys.version_info >= (3, 8):
        shutil.copytree(src, dst, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        return
    dst.mkdir(parents=True, exist_ok=True)
    for entry in src.iterdir():
        if entry.name == "__pycache__" or entry.name.endswith(".pyc"):
            continue
        target = dst / entry.name
        if entry.is_dir():
            _copytree_into(entry, target)
        else:
            shutil.copy2(entry, target)


def _copy_game_tree(project: Path, out_dir: Path) -> None:
    """把游戏目录的剧本/资源原样复制进产物（与 pack.py 的排除清单一致）。"""
    for item in sorted(project.iterdir()):
        if item.name in _PACK_EXCLUDE_NAMES or item.name.startswith("."):
            continue
        target = out_dir / item.name
        if item.is_dir():
            _copytree_into(item, target)
        else:
            shutil.copy2(item, target)


def _template_builder(template: Path, root: Path):
    """返回 build_func：复制玩家模板 + 游戏资源，全程不需要 PyInstaller。"""
    def build(project_dir, *, name, icon=None, version="", publisher=None,
              description="", release_notes=""):
        out_dir = Path(root) / "dist" / name
        if out_dir.exists():
            shutil.rmtree(out_dir)  # 只清本游戏的产物目录，避免旧版本残留
        out_dir.mkdir(parents=True)
        shutil.copy2(template / PLAYER_EXE, out_dir / f"{name}.exe")
        shutil.copytree(template / "_internal", out_dir / "_internal")
        _copy_game_tree(Path(project_dir).resolve(), out_dir)
        return str(out_dir)

    return build


def _default_builder(root: Path):
    if getattr(sys, "frozen", False):
        # 编辑器发行版没有 Python/PyInstaller：只能复制预构建的玩家模板。
        # 若缺模板，必须给出明确中文提示，不能落到 pack.py 后报“PyInstaller 退出码 2”。
        template = player_template_dir(root)
        if template is None:
            raise PackProfileError(
                "当前发行包缺少玩家模板（engine/templates/player），无法打包游戏；"
                "请重新下载完整发行包，或使用源码版 pack.py")
        return _template_builder(template, Path(root))
    mod = sys.modules.get("pack")
    if mod is not None and callable(getattr(mod, "pack", None)):
        return mod.pack
    candidate = root / "pack.py"
    if not candidate.is_file():
        raise PackProfileError("当前环境缺少打包器 pack.py，无法执行 PyInstaller 构建")
    spec = importlib.util.spec_from_file_location("moyul_pack_builder", candidate)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module.pack


def _build_number(project_dir, root=None, history_path=None) -> int:
    builds = project_history(project_dir, root, history_path).get("builds") or []
    return len(builds) + 1


def pack_project(project_dir, *, version=None, bump=None, name=None, icon=None,
                 publisher=None, description=None, release_notes=None,
                 build_func=None, root=None, history_path=None, register=True,
                 verbose=True) -> dict:
    """完整打包流程：合并档案 → 校验 → 版本迭代 → 构建 → 写元数据 → 记历史。

    返回 dict（可直接 JSON 给编辑器）；失败抛 PackProfileError（中文）。
    """
    root = Path(root) if root else _repo_root()
    project = Path(project_dir).resolve()
    if not project.is_dir():
        raise PackProfileError(f"游戏目录不存在：{project}")
    if not (project / "script.gal").is_file():
        raise PackProfileError(f"游戏目录里缺少 script.gal：{project}")

    profile = load_profile(project)
    if name is not None:
        profile["game_name"] = str(name).strip()
    if icon is not None:
        profile["icon"] = str(icon).strip()
    if description is not None:
        profile["description"] = str(description)
    if release_notes is not None:
        profile["release_notes"] = str(release_notes)
    if publisher is not None:
        base_pub = profile.get("publisher") if isinstance(profile.get("publisher"), dict) else {}
        merged = copy.deepcopy(base_pub)
        for key in ("name", "account_id", "channel", "contact"):
            if publisher.get(key) is not None:
                merged[key] = str(publisher.get(key))
        profile["publisher"] = merged

    if version is not None and bump:
        raise PackProfileError("不能同时指定固定版本号与版本递增方式")
    if bump:
        latest = latest_build(project, root, history_path)
        base = (latest or {}).get("version") or profile.get("version") or "1.0.0"
        profile["version"] = bump_version(base, bump)
    elif version is not None:
        profile["version"] = validate_version(version)
    else:
        profile["version"] = str(profile.get("version") or "1.0.0")

    errors = validate_profile(profile, project, check_icon=True)
    if errors:
        raise PackProfileError("打包配置不完整：\n- " + "\n- ".join(errors))

    game_name = str(profile["game_name"]).strip()
    icon_ico = resolve_icon(project, profile.get("icon"), root / "build" / game_name)
    builder = build_func or _default_builder(root)
    build_number = _build_number(project, root, history_path)
    built_at = _now_iso()

    if verbose:
        print(f"开始打包：{game_name} v{profile['version']}（第 {build_number} 次构建）", flush=True)
    try:
        out_dir = Path(builder(
            str(project), name=game_name, icon=str(icon_ico),
            version=profile["version"], publisher=profile.get("publisher"),
            description=profile.get("description"), release_notes=profile.get("release_notes"),
        ))
    except (PackProfileError, OSError):
        raise
    except Exception as exc:
        raise PackProfileError(f"打包失败：{exc}") from exc
    if not out_dir.is_dir():
        raise PackProfileError(f"打包器未返回有效产物目录：{out_dir}")

    # 只有构建成功才落盘版本与历史：失败重试不会消耗版本号
    save_profile(project, profile)
    info_path = write_game_info(out_dir, profile, build_number, built_at)
    size_bytes = sum(p.stat().st_size for p in out_dir.rglob("*") if p.is_file())

    result = {
        "ok": True,
        "project": _rel_key(project, root),
        "game_name": game_name,
        "version": profile["version"],
        "build_number": build_number,
        "built_at": built_at,
        "output_dir": _rel_key(out_dir, root),
        "exe": str(out_dir / f"{game_name}.exe"),
        "size_bytes": size_bytes,
        "icon": str(icon_ico),
        "info_path": str(info_path),
        "publisher": copy.deepcopy(profile.get("publisher") or {}),
    }
    if register:
        record_build(project, result, root=root, history_path=history_path)
        result["history"] = str(Path(history_path) if history_path else _history_path(root))
    if verbose:
        print(f"打包完成：{out_dir}")
        print(f"  版本：v{profile['version']}（构建 #{build_number}）")
        print(f"  产物体积：{size_bytes / 1024 / 1024:.2f} MB")
    return result


def record_build(project_dir, result: dict, root=None, history_path=None) -> dict:
    """把一次成功构建写入历史；同一项目保留全部版本记录。"""
    root = Path(root) if root else _repo_root()
    key = _rel_key(Path(project_dir), root)
    path = Path(history_path) if history_path else _history_path(root)
    history = _read_json(path, {"schema": 1, "projects": {}})
    if not isinstance(history.get("projects"), dict):
        history["projects"] = {}
    entry = history["projects"].setdefault(key, {
        "project": key,
        "game_name": result.get("game_name"),
        "publisher": result.get("publisher") or {},
        "builds": [],
    })
    entry["game_name"] = result.get("game_name") or entry.get("game_name")
    entry["publisher"] = result.get("publisher") or entry.get("publisher") or {}
    builds = entry.setdefault("builds", [])
    builds.append({
        "version": result.get("version"),
        "build_number": result.get("build_number"),
        "built_at": result.get("built_at") or _now_iso(),
        "output_dir": result.get("output_dir"),
        "exe": result.get("exe"),
        "size_bytes": result.get("size_bytes"),
        "icon": result.get("icon"),
    })
    _atomic_write_json(path, history)
    return entry


def list_projects(projects_dir=None, root=None, history_path=None) -> list[dict]:
    """列出可选择打包的游戏项目：含打包档案/历史版本，按已打包优先排序。"""
    root = Path(root) if root else _repo_root()
    projects_dir = Path(projects_dir) if projects_dir else root / "games"
    history = load_history(root, history_path)
    rows = []
    if projects_dir.is_dir():
        for child in sorted(projects_dir.iterdir(), key=lambda p: p.name):
            if not child.is_dir() or not (child / "script.gal").is_file():
                continue
            key = _rel_key(child, root)
            profile = load_profile(child)
            entry = copy.deepcopy(history["projects"].get(key) or {})
            builds = entry.get("builds") or []
            latest = builds[-1] if builds else None
            rows.append({
                "project": key,
                "folder": child.name,
                "game_name": profile.get("game_name") or child.name,
                "version": (latest or {}).get("version") or profile.get("version") or "1.0.0",
                "profile_version": profile.get("version") or "",
                "icon": profile.get("icon") or "",
                "publisher": copy.deepcopy(profile.get("publisher") or {}),
                "packaged": bool(builds),
                "build_count": len(builds),
                "latest": copy.deepcopy(latest) if latest else None,
                "has_profile": bool(profile),
            })
    rows.sort(key=lambda r: (not r["packaged"], 0 if r["folder"].startswith("月光") else 1, r["folder"]))
    return rows
