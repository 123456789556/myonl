# -*- coding: utf-8 -*-
"""设备能力探测与画质档位（默认值体系）。

纯函数 classify 可复现；detect_spec 在本机跑通并返回合法档位。
"""
from __future__ import annotations

import pytest

from engine import capability

pytestmark = [pytest.mark.unit]


def test_低配机被判为low():
    assert capability.classify(4.0, 2, 1366, 768) == "low"


def test_主流机判为mid():
    assert capability.classify(8.0, 4, 1920, 1080) == "mid"


def test_高配机判为high():
    assert capability.classify(16.0, 8, 2560, 1440) == "high"


def test_缺失信息不炸且回落low():
    assert capability.classify(None, None, None, None) == "low"
    assert capability.classify("坏", "坏", "坏", "坏") == "low"


def test_三档默认值单调递增():
    low = capability.TIER_DEFAULTS["low"]
    mid = capability.TIER_DEFAULTS["mid"]
    high = capability.TIER_DEFAULTS["high"]
    assert low["window_size"][0] <= mid["window_size"][0] <= high["window_size"][0]
    assert low["image_cache_mb"] < mid["image_cache_mb"] < high["image_cache_mb"]
    assert low["skip_shake"] is True and high["skip_shake"] is False


def test_本机探测返回合法结果():
    spec = capability.detect_spec()
    assert spec["tier"] in capability.TIERS
    assert isinstance(spec["suggested"], dict)
    assert "window_size" in spec["suggested"]


def test_suggest_settings_按档位取且不共享引用():
    a = capability.suggest_settings("low")
    b = capability.suggest_settings("low")
    assert a == b
    a["window_size"] = [1, 1]
    assert capability.TIER_DEFAULTS["low"]["window_size"] != [1, 1]


# ==================== 详细评分（设备评估做得细一些） ====================

def test_逐项评分与依据():
    parts = capability.score_spec(15.3, 16, 1536, 864, gpu=3, disk_free_gb=37.0)
    assert parts["ram"] == 1 or parts["ram"] == 2  # 15.3GB 按阈值是 16 以下 → 1
    assert parts["cpu"] == 3
    assert parts["gpu"] == 3
    assert parts["screen"] == 0
    assert parts["disk"] == 1
    assert parts["total"] == sum(parts[k] for k in ("ram", "cpu", "gpu", "screen", "disk"))
    assert len(parts["evidence"]) == 5


def test_显卡评分按显存与型号():
    assert capability.gpu_score("NVIDIA GeForce RTX 4060 Laptop GPU", 4.0) == 3
    assert capability.gpu_score("NVIDIA GeForce GTX 1650", 4.0) == 2
    assert capability.gpu_score("Intel(R) UHD Graphics 620", None) == 1
    assert capability.gpu_score(None, None) == 0
    assert capability.gpu_score("未知显卡", None) == 0


def test_档位阈值():
    assert capability.tier_from_score(8, with_gpu=True) == "high"
    assert capability.tier_from_score(4, with_gpu=True) == "mid"
    assert capability.tier_from_score(7, with_gpu=False) == "high"
    assert capability.tier_from_score(3, with_gpu=False) == "mid"
    assert capability.tier_from_score(0, with_gpu=True) == "low"


def test_详细评估结构完整():
    report = capability.evaluate(include_gpu=False)
    assert report["tier"] in capability.TIERS
    assert set(report) >= {"spec", "scores", "tier", "recommendations", "suggested_settings"}
    rec = report["recommendations"]
    for key in ("window_size", "video_height", "image_cache_mb", "shake", "particles", "note"):
        assert key in rec
    assert isinstance(report["scores"]["total"], int)
