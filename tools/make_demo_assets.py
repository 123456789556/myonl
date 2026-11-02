# -*- coding: utf-8 -*-
"""占位素材生成工具（P16）：为新建游戏补生成占位图。

薄封装 engine.newgame.make_placeholder_assets（CLI/编辑器新建向导共用同一实现）。

用法：
    py tools/make_demo_assets.py [游戏目录]     # 默认 games/newbie_demo
    py tools/make_demo_assets.py games/我的游戏 --overwrite   # 强制重生成（覆盖同名）

已存在的同名文件默认跳过（不覆盖用户素材）。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.newgame import make_placeholder_assets  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="为游戏目录生成占位素材（2 背景 + 2 立绘）")
    ap.add_argument("game_dir", nargs="?", default=str(ROOT / "games" / "newbie_demo"),
                    help="游戏目录（默认 games/newbie_demo）")
    ap.add_argument("--overwrite", action="store_true", help="同名文件也重新生成（会覆盖）")
    args = ap.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    root = Path(args.game_dir)
    if not root.is_dir():
        print(f"错误：游戏目录不存在：{root}（请先用 py -m engine.cli new 创建）",
              file=sys.stderr)
        return 1

    made = make_placeholder_assets(root, overwrite=args.overwrite)
    if made:
        for p in made:
            print(f"已生成：{p}")
        print(f"共生成 {len(made)} 个占位素材。")
    else:
        print("占位素材已存在，全部跳过（--overwrite 可强制重新生成）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
