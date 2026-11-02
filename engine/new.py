"""P0-2 Launcher CLI：新建 MYONL 游戏项目骨架。

用法：
    python -m engine.new 游戏名                  # default 教学骨架
    python -m engine.new 游戏名 --template moonlight  # 复刻《月光漫步》全量资源
    python -m engine.new 游戏名 --dir projects   # 指定生成位置（默认 games/）

与 engine.cli new 子命令共用 newgame.create_game；本模块是独立入口，
方便 Ren'Py 风格的「python -m engine.new mygame」一行起项目。
"""
from __future__ import annotations

import argparse
import sys

from .newgame import ALIGNS, TEMPLATES, THEMES, create_game


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    ap = argparse.ArgumentParser(
        prog="engine.new",
        description="新建 MYONL 游戏项目骨架",
    )
    ap.add_argument("name", help="游戏名（中文/字母/数字/下划线，≤20 字符）")
    ap.add_argument("--dir", default="games", help="生成位置（默认 games/）")
    ap.add_argument(
        "--template",
        default="default",
        choices=TEMPLATES,
        help="项目模板：default=教学骨架，moonlight=复刻《月光漫步》全量资源",
    )
    # P46：UI 主题与正文对齐（写入 config.json，建后也可手改）
    ap.add_argument("--theme", default="black", choices=THEMES,
                    help="UI 主题：仅 black=标准版（一套标准 UI，改 config.json 自定义）")
    ap.add_argument("--align", default="left", choices=ALIGNS,
                    help="正文对齐：left=左对齐顶格（默认），center=居中，right=右对齐")
    args = ap.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    try:
        root = create_game(args.name, args.dir, template=args.template,
                           theme=args.theme, align=args.align)
    except ValueError as e:
        print(f"错误：{e}", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"错误：生成游戏失败（{e}）", file=sys.stderr)
        return 2

    print(f"已创建游戏：{root}")
    print(f"  模板：{args.template}")
    print(f"  剧本：{root / 'script.gal'}")
    print(f"  编辑器打开：py -m engine.editor --project {root}")
    if args.template == "default":
        print(f"  占位素材：{root / 'images'}（4 张纯色块，替换同名文件即可）")
    else:
        print(f"  月光漫步资源已就位，直接运行：py -m engine.demo {root / 'script.gal'} --assets {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
