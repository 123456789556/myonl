# -*- coding: utf-8 -*-
"""设备能力探测与画质档位（默认值体系的一部分）。

为什么需要：不同机器的内存/CPU/显卡/屏幕差异很大，同一套默认值在低配机上会卡、
在高配机上会显得小。这里给「低 / 中 / 高」三档一个统一口径，并给出**逐项依据**：

- detect_spec()：快速探测（<10ms，不依赖第三方库、不初始化 pygame）
- detect_gpu()：较慢的显卡探测（PowerShell/WMI，约 0.5–1.5s，仅详细报告时调用）
- classify()：兼容旧接口的三档判定（内存/核数/屏幕）
- score_spec() / tier_from_score()：详细评分（内存/CPU/显卡/屏幕/磁盘）
- evaluate()：汇总 + 建议值 + 逐条依据（给人看的「为什么这档」）
- suggest_settings()：该档位的建议默认值

用法：
    py -3 -m engine.capability            # 详细报告（含显卡，约 1s）
    py -3 -m engine.capability --fast     # 快速报告（跳过显卡）
    py -3 -m engine.capability --json     # 机器可读

注意：这是「建议值」，不会自动写进玩家的 settings.json——是否采纳由引擎/开发者决定，
避免同一份仓库在不同机器上默认值漂移（测试也不稳定）。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

TIERS = ("low", "mid", "high")

# 各档位的建议默认值（引擎/新建游戏可读取；玩家仍可在设置里覆盖）
TIER_DEFAULTS = {
    "low": {
        "window_size": [1280, 720],
        "skip_shake": True,          # 关闭镜头震动/粒子的重效果
        "video_height": 720,
        "image_cache_mb": 128,
        "pixel_scale": 6,
        "desc": "集成显卡/8GB 内存级：保 720p 流畅，重效果可关",
    },
    "mid": {
        "window_size": [1600, 900],
        "skip_shake": False,
        "video_height": 1080,
        "image_cache_mb": 256,
        "pixel_scale": 4,
        "desc": "主流轻薄本/台式：900p~1080p，效果全开",
    },
    "high": {
        "window_size": [1920, 1080],
        "skip_shake": False,
        "video_height": 1080,
        "image_cache_mb": 512,
        "pixel_scale": 4,
        "desc": "独显/2K 屏级：1080p 全开；后续 video_height 可上 1440/2160",
    },
}

# 详细建议（evaluate 输出用）：比 TIER_DEFAULTS 多粒子/纹理/文字特效等开关
_TIER_RECOMMEND = {
    "low": {
        "window_size": [1280, 720],
        "video_height": 720,
        "image_cache_mb": 128,
        "shake": False,
        "particles": False,
        "text_effects": False,
        "texture_quality": "低",
        "note": "优先保证流畅：关震动/粒子，视频 720p，缓存 128MB",
    },
    "mid": {
        "window_size": [1600, 900],
        "video_height": 1080,
        "image_cache_mb": 256,
        "shake": True,
        "particles": True,
        "text_effects": True,
        "texture_quality": "中",
        "note": "默认档：1080p 视频、效果全开、缓存 256MB",
    },
    "high": {
        "window_size": [1920, 1080],
        "video_height": 1080,
        "image_cache_mb": 512,
        "shake": True,
        "particles": True,
        "text_effects": True,
        "texture_quality": "高",
        "note": "宽裕档：1080p 起步，视频/缓存可继续上调（后续 1440/2160）",
    },
}


def classify(ram_gb: float | None, cpu_cores: int | None,
             screen_w: int | None, screen_h: int | None) -> str:
    """兼容旧接口的三档判定（内存/核数/屏幕，不含显卡）。"""
    parts = score_spec(ram_gb, cpu_cores, screen_w, screen_h)
    return tier_from_score(parts["total"], with_gpu=False)


def _num(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _ints(*values) -> tuple[int, ...]:
    out = []
    for value in values:
        try:
            out.append(int(value or 0))
        except (TypeError, ValueError):
            out.append(0)
    return tuple(out)


def score_spec(ram_gb=None, cpu_cores=None, screen_w=None, screen_h=None,
               gpu: int = 0, disk_free_gb=None) -> dict:
    """逐项打分（0–3 / 0–2 / 0–1），返回 {"ram":..,...,"total":..} 与依据。"""
    ram = _num(ram_gb)
    cores, sw, sh = _ints(cpu_cores, screen_w, screen_h)
    disk = _num(disk_free_gb) if disk_free_gb is not None else None

    ram_score = 3 if ram >= 32 else 2 if ram >= 16 else 1 if ram >= 8 else 0
    cpu_score = 3 if cores >= 16 else 2 if cores >= 8 else 1 if cores >= 4 else 0
    gpu_score_v = max(0, min(3, int(gpu or 0)))
    screen_score = 2 if (sw >= 2560 and sh >= 1440) else 1 if (sw >= 1920 and sh >= 1080) else 0
    disk_score = 1 if (disk is not None and disk >= 20) else 0

    evidence = [
        f"内存 {ram:g}GB → +{ram_score}",
        f"CPU {cores} 核 → +{cpu_score}",
        f"显卡评分 {gpu_score_v}/3 → +{gpu_score_v}",
        f"屏幕 {sw}x{sh} → +{screen_score}",
        (f"磁盘剩余 {disk:g}GB → +{disk_score}" if disk is not None else "磁盘剩余未知 → +0"),
    ]
    total = ram_score + cpu_score + gpu_score_v + screen_score + disk_score
    return {"ram": ram_score, "cpu": cpu_score, "gpu": gpu_score_v,
            "screen": screen_score, "disk": disk_score, "total": total,
            "evidence": evidence}


def tier_from_score(total: int, with_gpu: bool = True) -> str:
    """分数 → 档位。

    带显卡：high≥8 / mid≥4（显卡最高 3 分，低配核显拿 1 分也能进 mid）。
    不带显卡：high≥6 / mid≥3（少 3 分，阈值同步下调，避免快速探测把好机器误判成 low）。
    """
    if with_gpu:
        high_th, mid_th = 8, 4
    else:
        high_th, mid_th = 6, 3
    if total >= high_th:
        return "high"
    if total >= mid_th:
        return "mid"
    return "low"


def gpu_score(name: str | None, vram_gb: float | None) -> int:
    """显卡评分：优先看显存，其次看型号关键词（WMI 的 AdapterRAM 可能不准，仅作参考）。"""
    by_vram = 0
    vram = _num(vram_gb, -1)
    if vram >= 8:
        by_vram = 3
    elif vram >= 4:
        by_vram = 2
    elif vram >= 2:
        by_vram = 1

    text = str(name or "").lower()
    by_name = 0
    if any(k in text for k in ("rtx", "rx 6", "rx 7", "rx 9", "arc a7", "arc b")):
        by_name = 3
    elif any(k in text for k in ("gtx", "rx 5", "rx 6", "arc a5", "radeon pro")):
        by_name = 2
    elif any(k in text for k in ("intel", "iris", "uhd", "vega", "radeon graphics", "amd radeon")):
        by_name = 1
    elif not text:
        by_name = 0
    return max(by_vram, by_name)


def _windows_ram_gb() -> float | None:
    """Windows：GlobalMemoryStatusEx 取物理内存（GB）。"""
    try:
        import ctypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
            return None
        return round(stat.ullTotalPhys / (1024 ** 3), 1)
    except Exception:  # noqa: BLE001 — 探测失败不阻塞游戏，返回 None 由调用方兜底
        return None


def _windows_screen() -> tuple[int | None, int | None]:
    try:
        import ctypes

        user32 = ctypes.windll.user32
        return int(user32.GetSystemMetrics(0)), int(user32.GetSystemMetrics(1))
    except Exception:  # noqa: BLE001
        return None, None


def detect_gpu() -> dict:
    """探测显卡（Windows，PowerShell/WMI；约 0.5–1.5s）。失败返回空信息，不抛异常。"""
    if os.environ.get("MYONL_SKIP_GPU"):
        return {"name": None, "vram_gb": None, "error": "MYONL_SKIP_GPU"}
    if os.name != "nt":
        return {"name": None, "vram_gb": None, "error": "仅 Windows 探测显卡"}
    ps = ("Get-CimInstance Win32_VideoController | "
          "Select-Object Name,AdapterRAM | ConvertTo-Json -Compress")
    try:
        proc = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=8)
        raw = (proc.stdout or "").strip()
        if not raw:
            return {"name": None, "vram_gb": None, "error": (proc.stderr or "无输出")[:120]}
        data = json.loads(raw)
        items = data if isinstance(data, list) else [data]
        best = None
        for item in items:
            vram = item.get("AdapterRAM")
            gb = round(_num(vram, 0) / (1024 ** 3), 1) if vram else None
            cand = {"name": str(item.get("Name") or "") or None, "vram_gb": gb}
            if best is None or gpu_score(cand["name"], cand["vram_gb"]) > gpu_score(best["name"], best["vram_gb"]):
                best = cand
        return best or {"name": None, "vram_gb": None, "error": "没有显卡记录"}
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        return {"name": None, "vram_gb": None, "error": f"{type(exc).__name__}: {exc}"}


def detect_disk_free_gb(path: str | None = None) -> float | None:
    try:
        target = Path(path or os.getcwd())
        usage = shutil.disk_usage(str(target))
        return round(usage.free / (1024 ** 3), 1)
    except OSError:
        return None


def detect_spec() -> dict:
    """快速探测（不含显卡）：内存/CPU/屏幕/档位/建议值。"""
    ram = _windows_ram_gb()
    cores = os.cpu_count()
    screen_w, screen_h = _windows_screen()
    tier = classify(ram, cores, screen_w, screen_h)
    return {
        "os": sys.platform,
        "ram_gb": ram,
        "cpu_cores": cores,
        "screen_w": screen_w,
        "screen_h": screen_h,
        "tier": tier,
        "suggested": dict(TIER_DEFAULTS[tier]),
    }


def evaluate(include_gpu: bool = True) -> dict:
    """详细评估：硬件 + 逐项分数 + 档位 + 建议值 + 依据（给 CLI/编辑器展示）。"""
    ram = _windows_ram_gb()
    cores = os.cpu_count()
    screen_w, screen_h = _windows_screen()
    disk_free = detect_disk_free_gb()
    gpu_info = detect_gpu() if include_gpu else {"name": None, "vram_gb": None, "error": "跳过"}
    gpu_points = gpu_score(gpu_info.get("name"), gpu_info.get("vram_gb"))
    parts = score_spec(ram, cores, screen_w, screen_h, gpu=gpu_points, disk_free_gb=disk_free)
    tier = tier_from_score(parts["total"], with_gpu=include_gpu)
    return {
        "spec": {
            "os": sys.platform,
            "ram_gb": ram,
            "cpu_cores": cores,
            "screen_w": screen_w,
            "screen_h": screen_h,
            "gpu_name": gpu_info.get("name"),
            "vram_gb": gpu_info.get("vram_gb"),
            "gpu_error": gpu_info.get("error"),
            "disk_free_gb": disk_free,
        },
        "scores": parts,
        "tier": tier,
        "recommendations": dict(_TIER_RECOMMEND[tier]),
        "suggested_settings": dict(TIER_DEFAULTS[tier]),
    }


def suggest_settings(tier: str | None = None) -> dict:
    """返回该档位建议的默认设置；tier 为空时按本机快速探测。"""
    name = tier if tier in TIER_DEFAULTS else detect_spec()["tier"]
    return dict(TIER_DEFAULTS[name])


def _print_report(report: dict, fast: bool) -> None:
    spec, scores, rec = report["spec"], report["scores"], report["recommendations"]
    print("== 设备评估 ==")
    print(f"系统：{spec['os']}")
    print(f"内存：{spec['ram_gb']} GB｜CPU：{spec['cpu_cores']} 核｜"
          f"屏幕：{spec['screen_w']}x{spec['screen_h']}")
    if fast:
        print("显卡：跳过（--fast）")
    elif spec.get("gpu_name"):
        print(f"显卡：{spec['gpu_name']}（显存约 {spec.get('vram_gb')} GB，WMI 值仅供参考）")
    else:
        print(f"显卡：未识别（{spec.get('gpu_error') or '无'}）")
    print(f"磁盘剩余：{spec.get('disk_free_gb')} GB")
    print()
    print("== 评分 ==")
    for line in scores["evidence"]:
        print(f"  {line}")
    print(f"  总分：{scores['total']} → 档位：{report['tier']}")
    print()
    print("== 建议（首次默认值） ==")
    for key, val in rec.items():
        if key != "note":
            print(f"  {key}: {val}")
    print(f"  note: {rec['note']}")


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    # sys.stdout 类型是 TextIO（无 reconfigure 声明）；运行时才知是 TextIOWrapper/StringIO，
    # 故用 getattr 拿（Any），hasattr 语义不变且 pyright 不再误报
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8", errors="replace")
    if argv and argv[0] in ("-h", "--help"):
        print("用法：py -3 -m engine.capability [--fast] [--json]")
        return 0
    report = evaluate(include_gpu="--fast" not in argv)
    if "--json" in argv:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    _print_report(report, fast="--fast" in argv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
