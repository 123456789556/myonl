"""MYONL 命令行工具。

用法：
    python -m engine.cli --check script.gal     检查语法（错误带行号，退出码见 engine_spec.md 第 6 节）
    python -m engine.cli --tojson script.gal    输出指令 JSON（-o out.json 写文件）
    python -m engine.cli --fromjson out.json    由指令 JSON 还原 .gal 文本
    python -m engine.cli new 游戏名             新建游戏骨架（games/游戏名/，--dir 可换位置）
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .newgame import ALIGNS, TEMPLATES, THEMES, create_game
from .parser import GalSyntaxError, dump_text, dumps, loads, parse_file


def _force_utf8() -> None:
    """CLI 输出统一 UTF-8（stdout 与 stderr 都要重配）。

    Windows 中文版默认 cp936：输出被重定向到管道时，调用方（含测试）
    按 UTF-8 解码会 UnicodeDecodeError，stdout 里是成功信息、stderr 里是
    报错信息，只要漏配一个流就会让调用方拿到 None。
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


def _main_new(argv) -> int:
    """new 子命令：新建游戏骨架（与编辑器「＋ 新建游戏」共用 create_game）。"""
    ap = argparse.ArgumentParser(prog="engine.cli new", description="新建游戏：生成可运行的项目骨架")
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
    _force_utf8()
    try:
        root = create_game(args.name, args.dir, template=args.template,
                           theme=args.theme, align=args.align)
    except ValueError as e:
        print(f"错误：{e}", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"错误：生成游戏失败（{e}）", file=sys.stderr)
        return 2
    print(f"已创建游戏：{root}（模板：{args.template}）")
    print(f"  剧本：{root / 'script.gal'}")
    print(f"  用编辑器打开：py -m engine.editor --project {root}")
    return 0


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv and argv[0] == "new":
        return _main_new(argv[1:])
    ap = argparse.ArgumentParser(prog="engine.cli", description="MYONL 剧本工具")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true", help="检查 .gal 语法")
    g.add_argument("--tojson", action="store_true", help=".gal → 指令 JSON")
    g.add_argument("--fromjson", action="store_true", help="指令 JSON → .gal 文本")
    ap.add_argument("script", help=".gal 剧本路径（--fromjson 时为 .json 路径）")
    ap.add_argument("-o", "--output", help="输出到文件（默认打印到 stdout）")
    args = ap.parse_args(argv)

    _force_utf8()

    if args.fromjson:
        try:
            text = Path(args.script).read_text(encoding="utf-8")
        except (FileNotFoundError, UnicodeDecodeError) as e:
            print(f"错误：无法读取 {args.script}（{e}）", file=sys.stderr)
            return 2
        try:
            instrs = loads(text)
        except ValueError as e:
            print(f"错误：JSON 不合法（{e}）", file=sys.stderr)
            return 1
        out = dump_text(instrs)
    else:
        try:
            instrs = parse_file(args.script)
        except GalSyntaxError as e:
            print(f"语法错误：{e}", file=sys.stderr)
            return 1
        if args.check:
            print(f"语法检查通过：{args.script}（{len(instrs)} 条顶层指令）")
            return 0
        out = dumps(instrs) + "\n"

    if args.output:
        Path(args.output).write_text(out, encoding="utf-8")
        print(f"已写入 {args.output}")
    else:
        sys.stdout.write(out if out.endswith("\n") else out + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
