# -*- coding: utf-8 -*-
"""P136 技术债 6：demo.py 存档补写必须走已有原子写路径，不许裸 write_text。

复核结论：该裸 write_text 在 P130 已修为 save_api._atomic_write_text；本测试锁死这条，
防止以后回退成「写到一半断电留下半截档」。settings 落盘走 data.save_settings
（临时文件 + os.replace），不在本文件重复造原子写。
"""
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "engine" / "demo.py"


def test_demo_save_enrich_uses_atomic_write():
    src = DEMO.read_text(encoding="utf-8")
    assert "save_api._atomic_write_text(save_path" in src, "补写卡片字段没走原子写"
    # 已有的裸 write_text 落盘句式不能再出现（读文件的 open(...,encoding=...) 不算）
    bad = 'save_path.write_text(_json.dumps(data'
    assert bad not in src, "又退回裸 write_text 了 —— 断电会留下半截档"


def test_demo_imports_save_api():
    src = DEMO.read_text(encoding="utf-8")
    assert "from . import save as save_api" in src
