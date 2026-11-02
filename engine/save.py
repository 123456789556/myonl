"""MYONL 存档模块。

职责：GameState ←→ JSON 存档文件。
- 10 个独立存档位（1~10）+ 1 个快存位（quick，固定覆盖）
- 存档文件：saves/slot_{slot}.json，saves/ 目录自动创建
- 真正的定位依据是 anchor_stack（锚点栈），state.stack 只作参考；
  锚点的生成与还原由 runtime 负责（只有 runtime 认识指令列表索引）
- 只用 Python 标准库；异常信息用中文
"""
from __future__ import annotations

import copy
import json
import sys
from datetime import datetime
from pathlib import Path

from engine import data as data_api  # P40：存档目录跟随 data_root()（随游戏/AppData/自定义）

SLOT_COUNT = 10            # 存档位 1~10
QUICK_SLOT = "quick"       # 快存位（固定覆盖）
SCHEMA_VERSION = 4         # 存档格式版本（v4：payload 加 thumbnail_path/chapter_name/last_text，存档卡片三要素）
# 存档目录：默认 relative "saves"（相对当前工作目录）；demo.run 启动时按资源根改为
# <assets_root>/saves，保证开发模式与打包后（exe 旁）行为一致，且不同游戏不互相污染。
# 模块级变量保留字符串形态，兼容外部工具直接赋值 save.SAVES_DIR。
SAVES_DIR = "saves"
PERSISTENT_FILE = "persistent.json"  # P26 T4：全局解锁记录（跨存档/跨周目，不随读档回退）

# 存档版本迁移表（Schema migration）：
#   MIGRATIONS[n] = 函数(存档 dict) -> dict，把 version=n 的存档升级为 version=n+1。
#   未来加字段/改结构时在此注册迁移函数；函数只允许补字段/改格式，禁止删数据。
MIGRATIONS: dict[int, object] = {}


def _migrate_v1_to_v2(data: dict) -> dict:
    """v1 → v2：补 P11 新增字段默认值（state.video=None、sprites[].anim="呼吸"）。只补不删。"""
    state = data.get("state")
    if isinstance(state, dict):
        state.setdefault("video", None)
        sprites = state.get("sprites")
        if isinstance(sprites, list):
            for sp in sprites:
                if isinstance(sp, dict):
                    sp.setdefault("anim", "呼吸")
    return data


MIGRATIONS[1] = _migrate_v1_to_v2


def _migrate_v2_to_v3(data: dict) -> dict:
    """v2 → v3：补 P13 新增字段默认值（state.gallery=[]，已解锁 CG 列表）。只补不删。"""
    state = data.get("state")
    if isinstance(state, dict):
        state.setdefault("gallery", [])
    return data


MIGRATIONS[2] = _migrate_v2_to_v3


def _migrate_v3_to_v4(data: dict) -> dict:
    """v3 → v4：补 ⑨ 存档卡片三要素默认值（thumbnail_path/chapter_name/last_text）。只补不删。"""
    data.setdefault("thumbnail_path", None)
    data.setdefault("chapter_name", None)
    data.setdefault("last_text", None)
    return data


MIGRATIONS[3] = _migrate_v3_to_v4


class SaveError(Exception):
    """存档错误。中文提示。"""


# ==================== 存档目录配置 ====================

def saves_dir() -> Path:
    """当前存档目录。

    demo.run 会 set_saves_dir 到资源根；未设置时按 P40 data_dir 策略：
    数据根 = data_root()（随游戏 / %APPDATA%/Moyul/<游戏名> / 自定义）。
    """
    if SAVES_DIR == "saves":
        return Path(data_api.data_root()) / "saves"
    return Path(SAVES_DIR)


def set_saves_dir(path) -> Path:
    """切换存档目录（demo.run 用 <assets_root>/saves）。返回新目录 Path。"""
    global SAVES_DIR
    SAVES_DIR = str(path)
    return Path(SAVES_DIR)


def reset_saves_dir() -> None:
    """恢复默认 "saves"（进程内多处调用 demo 时避免上一个游戏的目录泄漏）。"""
    global SAVES_DIR
    SAVES_DIR = "saves"


def slot_path(slot) -> Path:
    """存档文件路径（会校验槽位合法性）；demo 补写存档卡片时用。"""
    return _slot_path(_normalize_slot(slot))


# ==================== 对外接口 ====================

def save(state: dict, slot, anchor_stack=None, *,
         thumbnail_path=None, chapter_name=None, last_text=None) -> str:
    """把 GameState + 可选锚点栈写入存档位，返回存档文件路径。

    ⑨ 存档卡片三要素：
      - thumbnail_path：当前画面缩略图（280×160）文件路径（通常由 demo 截屏后传入）
      - chapter_name：当前章节/label 名（如 "序章"）
      - last_text：最后一句台词（history[-1].text，30 字截断）
    三个字段都是可选的（None 也合法）—— runtime.save() 不传也不影响存档基本功能。
    """
    slot_key = _normalize_slot(slot)
    if not isinstance(state, dict):
        raise SaveError("存档失败：GameState 必须是 dict")
    if anchor_stack is not None and not isinstance(anchor_stack, list):
        raise SaveError("存档失败：anchor_stack 必须是列表")

    payload = {
        "engine": "moyul",
        "version": SCHEMA_VERSION,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "label": _nearest_label(anchor_stack),
        "thumbnail_path": thumbnail_path,   # ⑨ 存档卡片：缩略图路径
        "chapter_name": chapter_name,       # ⑨ 存档卡片：章节/label 名
        "last_text": last_text,             # ⑨ 存档卡片：末句（30 字截断）
        "state": copy.deepcopy(state),
        "anchor_stack": copy.deepcopy(anchor_stack) if anchor_stack else [],
    }
    try:
        text = json.dumps(payload, ensure_ascii=False, indent=2)
    except (TypeError, ValueError) as e:
        raise SaveError(f"存档失败：GameState 无法序列化为 JSON（{e}）")

    path = _slot_path(slot_key)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    except OSError as e:
        raise SaveError(f"存档失败：无法写入 {path}（{e}）")
    return str(path)


def load(slot) -> dict:
    """读取存档，返回存档 dict（含 "state" 字段）；不存在或损坏抛 SaveError。"""
    slot_key = _normalize_slot(slot)
    path = _slot_path(slot_key)
    if not path.is_file():
        raise SaveError(f"存档位 {slot_key} 没有存档")
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except OSError as e:
        raise SaveError(f"读取存档失败：{path}（{e}）")
    except ValueError as e:
        raise SaveError(f"存档文件损坏：{path}（{e}）")
    if not isinstance(data, dict) or not isinstance(data.get("state"), dict):
        raise SaveError(f"存档文件损坏：{path}（缺少 state 字段）")
    if data.get("engine") not in ("moyul", "galengine"):  # galengine=旧引擎存档，兼容读取
        raise SaveError(f"存档文件损坏：{path}（不是 Moyul 存档）")
    data = _migrate(data)
    return data


def _migrate(data: dict) -> dict:
    """存档版本迁移：旧版本逐级升级到当前格式；未来版本拦截报错。

    - version > SCHEMA_VERSION → 存档来自更新引擎，抛 SaveError
    - version < SCHEMA_VERSION → 逐级调用 MIGRATIONS[n]，直到当前版本
    - 缺失 version 按 0 处理（迁移链起点）
    """
    version = data.get("version")
    if not isinstance(version, int):
        version = 0
    if version > SCHEMA_VERSION:
        raise SaveError("存档来自更新的引擎版本，请先升级引擎")
    while version < SCHEMA_VERSION:
        fn = MIGRATIONS.get(version)
        if fn is None:
            raise SaveError(f"存档版本 {version} 过旧，没有可用的迁移路径（当前格式版本 {SCHEMA_VERSION}）")
        migrated = fn(dict(data))
        if not isinstance(migrated, dict):
            raise SaveError(f"存档迁移失败：MIGRATIONS[{version}] 必须返回 dict")
        data = migrated
        data["version"] = version + 1
        version += 1
    return data


def list_slots() -> list[dict]:
    """扫描 saves/ 返回存档摘要列表：快存最前，数字位按 1~10 排序。"""
    root = saves_dir()
    if not root.is_dir():
        return []
    entries: list[dict] = []
    for path in root.glob("slot_*.json"):
        slot_key = path.stem[len("slot_"):]
        # 只认 quick 与 1~10，其他文件（临时文件/旧格式残留）忽略
        if slot_key != QUICK_SLOT and not (slot_key.isdigit() and 1 <= int(slot_key) <= SLOT_COUNT):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            continue  # 损坏的存档不进列表，但不影响其他存档
        if not isinstance(data, dict) or not isinstance(data.get("state"), dict):
            continue
        entries.append({
            "slot": slot_key,
            "saved_at": data.get("saved_at"),
            "label": data.get("label"),
            "file": str(path),
            # ⑨ 存档卡片三要素
            "thumbnail_path": data.get("thumbnail_path"),
            "chapter_name": data.get("chapter_name"),
            "last_text": data.get("last_text"),
        })
    entries.sort(key=lambda e: (0 if e["slot"] == QUICK_SLOT else 1,
                                int(e["slot"]) if e["slot"].isdigit() else 0))
    return entries


def delete_slot(slot) -> None:
    """删除指定存档；不存在抛 SaveError。"""
    slot_key = _normalize_slot(slot)
    path = _slot_path(slot_key)
    if not path.is_file():
        raise SaveError(f"存档位 {slot_key} 没有存档，无法删除")
    try:
        path.unlink()
    except OSError as e:
        raise SaveError(f"删除存档失败：{path}（{e}）")


# ==================== 全局解锁记录（P26 T4）====================

def load_persistent() -> dict:
    """读 saves/persistent.json（跨周目记录）；不存在/损坏返回空记录，不崩。"""
    path = _persistent_path()
    if not path.is_file():
        return {"gallery": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {"gallery": []}
    if not isinstance(data, dict):
        return {"gallery": []}
    gallery = data.get("gallery")
    data["gallery"] = [str(n) for n in gallery] if isinstance(gallery, list) else []
    return data


def unlock_cg(name) -> None:
    """@cg 时把 CG 名写入全局解锁记录（跨档/跨周目保留）；写失败只警告不崩。"""
    name = str(name or "").strip()
    if not name:
        return
    data = load_persistent()
    if name in data["gallery"]:
        return
    data["gallery"].append(name)
    path = _persistent_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as e:
        print(f"[解锁警告] 全局解锁记录写入失败：{e}", file=sys.stderr)


def gallery_union(current=None) -> list[str]:
    """画廊显示用：全局已解锁 ∪ 当前存档已解锁（全局在前，档内独有的补在后面）。"""
    merged = list(load_persistent()["gallery"])
    for name in current or []:
        if name not in merged:
            merged.append(name)
    return merged


# ==================== 内部实现 ====================

def _persistent_path() -> Path:
    return saves_dir() / PERSISTENT_FILE


def _normalize_slot(slot) -> str:
    """把存档位统一成字符串：1~10 的 int（或数字字符串）→ "1"~"10"，"quick" 原样。"""
    if isinstance(slot, bool):
        raise SaveError(f"存档位不合法：{slot!r}（可用 1~{SLOT_COUNT} 或 \"quick\"）")
    if slot == QUICK_SLOT:
        return QUICK_SLOT
    if isinstance(slot, int) and 1 <= slot <= SLOT_COUNT:
        return str(slot)
    if isinstance(slot, str) and slot.isdigit() and 1 <= int(slot) <= SLOT_COUNT:
        return str(int(slot))
    raise SaveError(f"存档位不合法：{slot!r}（可用 1~{SLOT_COUNT} 或 \"quick\"）")


def _slot_path(slot_key: str) -> Path:
    return saves_dir() / f"slot_{slot_key}.json"


def _nearest_label(anchor_stack) -> str | None:
    """从当前帧锚点向上找最近的 label 名（给存档列表显示用）。

    if body 帧没有 label，递归看父 if 指令的锚点；顶层无 label 则为 None。
    """
    if not anchor_stack:
        return None
    anchor = anchor_stack[-1]
    while isinstance(anchor, dict):
        kind = anchor.get("kind")
        if kind == "label":
            return anchor.get("name")
        if kind == "ifbody":
            anchor = anchor.get("parent")
            continue
        return None
    return None
