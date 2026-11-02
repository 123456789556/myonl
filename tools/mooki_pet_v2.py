# -*- coding: utf-8 -*-
"""兼容入口：桌宠已移入引擎（engine/pet.py）。源码模式仍可用 py tools/mooki_pet_v2.py。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.pet import cli_main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(cli_main())