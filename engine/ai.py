"""AI 助手配置（P74：预留接口，默认关闭）。

定位很明确：**这是给作者的帮手，不是给引擎跑逻辑的**。所以它存在用户目录
（`~/.myonl/ai.json`），不进任何工程目录、不进导出包、不进 git —— 一份 key
不该因为导出一次网页包就跟着发出去。

当前实现只做「配置 + 脱敏读取 + 连通性自检」三件事：真正调用什么模型、发什么
prompt，是后面接上具体能力时再决定的。留成这样是有意的 —— 先把 key 存哪、
怎么不外泄这两件事定死，比先接一个厂商的 SDK 重要。
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".myonl")
CONFIG_PATH = os.path.join(CONFIG_DIR, "ai.json")

_DEFAULTS = {
    "enabled": False,
    "base_url": "https://api.openai.com/v1",   # OpenAI 兼容即可（含国内各家兼容端点）
    "model": "",
    "key": "",
    "max_tokens": 2048,
    "timeout": 30,
}
_SECRET_FIELDS = ("key",)


def _read() -> dict:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    out = dict(_DEFAULTS)
    if isinstance(data, dict):
        for k in _DEFAULTS:
            if k in data:
                out[k] = data[k]
    return out


def _write(data: dict) -> str:
    os.makedirs(CONFIG_DIR, exist_ok=True)
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, CONFIG_PATH)
    try:                       # 尽力收紧权限（Windows 上可能不支持 chmod，忽略失败）
        os.chmod(CONFIG_PATH, 0o600)
    except OSError:
        pass
    return CONFIG_PATH


def mask_key(key: str) -> str:
    """脱敏：只露头尾，够作者确认「配的是哪一把」，不足以泄露。"""
    key = (key or "").strip()
    if not key:
        return ""
    if len(key) <= 8:
        return "*" * len(key)
    return key[:4] + "*" * (len(key) - 8) + key[-4:]


def payload() -> dict:
    """给编辑器的读接口：**绝不返回明文 key**。"""
    cfg = _read()
    return {
        "ok": True,
        "enabled": bool(cfg["enabled"]),
        "base_url": cfg["base_url"],
        "model": cfg["model"],
        "max_tokens": cfg["max_tokens"],
        "timeout": cfg["timeout"],
        "key_mask": mask_key(cfg["key"]),
        "has_key": bool((cfg["key"] or "").strip()),
        "path": CONFIG_PATH,
        "note": ("key 只存在这台电脑的用户目录下，不写进工程、不进导出包、不进 git。"
                 "接的是 OpenAI 兼容接口（/chat/completions）。"),
    }


def save(patch: dict) -> dict:
    """写配置。key 传空串 = 保持原样；传 `clear_key: true` 才真清掉。"""
    if not isinstance(patch, dict):
        return {"ok": False, "message": "参数应为对象"}
    cfg = _read()
    if "enabled" in patch:
        cfg["enabled"] = bool(patch["enabled"])
    if "base_url" in patch:
        url = str(patch["base_url"] or "").strip()
        if url and not url.startswith(("http://", "https://")):
            return {"ok": False, "message": "base_url 必须以 http:// 或 https:// 开头"}
        cfg["base_url"] = url or _DEFAULTS["base_url"]
    if "model" in patch:
        cfg["model"] = str(patch["model"] or "").strip()
    for k in ("max_tokens", "timeout"):
        if k in patch:
            try:
                v = int(patch[k])
            except (TypeError, ValueError):
                continue
            cfg[k] = max(64, min(8192, v)) if k == "max_tokens" else max(5, min(120, v))
    if patch.get("clear_key"):
        cfg["key"] = ""
    elif str(patch.get("key") or "").strip():
        cfg["key"] = str(patch["key"]).strip()
    try:
        path = _write(cfg)
    except OSError as e:
        return {"ok": False, "message": f"写配置失败：{e}"}
    out = payload()
    out["path"] = path
    return out


def ping() -> dict:
    """连通性自检：拿 models 列表探一下，不消耗 token。"""
    cfg = _read()
    key = (cfg["key"] or "").strip()
    if not key:
        return {"ok": False, "message": "还没填 key"}
    url = cfg["base_url"].rstrip("/") + "/models"
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + key})
    try:
        with urllib.request.urlopen(req, timeout=min(20, int(cfg["timeout"]))) as r:
            body = r.read(2048).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return {"ok": False, "message": f"接口返回 {e.code}：{e.reason}（key 或 base_url 不对？）"}
    except (urllib.error.URLError, OSError, ValueError) as e:
        return {"ok": False, "message": f"连不上：{e}"}
    except Exception as e:   # noqa: BLE001
        return {"ok": False, "message": f"连接失败：{e}"}
    models = []
    try:
        data = json.loads(body)
        models = [m.get("id", "") for m in (data.get("data") or [])][:8]
    except ValueError:
        pass
    return {"ok": True, "models": models,
            "message": "连通" + (f"，可用模型示例：{'、'.join(models)}" if models else "")}
