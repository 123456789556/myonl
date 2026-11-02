"""把 brand/mooki_v2.svg 按图层/表情拆分为透明 PNG，供桌宠视差合成。

输出到 brand/mooki_layers/：
  glow / body / cheeks / star / dust  五个基础层
  expr_normal / expr_happy / expr_surprise / expr_angry  四个表情层（眼+嘴）

用法:
    py tools/export_mooki_layers.py
"""
from __future__ import annotations

import os
import re
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SVG_PATH = os.path.join(ROOT, "brand", "mooki_v2.svg")
OUT_DIR = os.path.join(ROOT, "brand", "mooki_layers")
SIZE = 400  # SVG viewBox 是 400x400


def _read_svg() -> str:
    with open(SVG_PATH, "r", encoding="utf-8") as f:
        return f.read()


def _isolate(svg: str, keep_ids: list[str]) -> str:
    """返回只保留 keep_ids 中图层/表情组的 SVG（其余组设 display:none）。

    保留规则：keep 里的组 + 它的全部子组（如 layer-body 内的 body-core）+ 它的全部祖先组
    （如 layer-face 保留时，其父级也要显示）。只按 id 逐个隐藏会把被保留组的嵌套子组
    一起藏掉，导出图就空了（P39 修复）。<defs> 不受影响（渐变定义始终保留）。
    """
    pattern = re.compile(r'<g\s+id="([^"]+)"[^>]*>|</g>')
    roots: list = []
    stack: list = []
    for m in pattern.finditer(svg):
        if m.group(1):
            node = {"id": m.group(1), "start": m.start(), "end": m.end(),
                    "parent": stack[-1] if stack else None, "children": []}
            (stack[-1]["children"] if stack else roots).append(node)
            stack.append(node)
        elif stack:
            stack.pop()

    keep = set()

    def mark_subtree(node):
        keep.add(node["id"])
        for c in node["children"]:
            mark_subtree(c)

    def walk(node):
        if node["id"] in keep_ids:
            mark_subtree(node)
            p = node["parent"]
            while p is not None:        # 祖先链一并保留（否则子组永远画不出来）
                keep.add(p["id"])
                p = p["parent"]
        for c in node["children"]:
            walk(c)

    for r in roots:
        walk(r)

    parts, pos = [], 0
    for m in pattern.finditer(svg):
        if not m.group(1):
            continue
        parts.append(svg[pos:m.start()])
        full = m.group(0)
        if m.group(1) not in keep:
            full = full[:-1] + ' display="none">'
        else:
            full = full.replace(' display="none"', '')   # 被保留组须显式显示
        parts.append(full)
        pos = m.end()
    parts.append(svg[pos:])
    return "".join(parts)


def export_one(svg: str, name: str, keep: list[str]) -> None:
    isolated = _isolate(svg, keep)
    tmp = os.path.join(OUT_DIR, f"_{name}.svg")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(isolated)
    surf = pygame.image.load_sized_svg(tmp, (SIZE, SIZE))
    out = os.path.join(OUT_DIR, f"mooki_{name}.png")
    pygame.image.save(surf, out)
    os.unlink(tmp)
    print(f"OK mooki_{name}.png")


def main() -> int:
    pygame.init()
    os.makedirs(OUT_DIR, exist_ok=True)
    svg = _read_svg()

    # 基础层（始终显示）
    export_one(svg, "glow", ["layer-glow"])
    export_one(svg, "body", ["layer-body"])
    export_one(svg, "cheeks", ["cheeks"])              # 腮红（从 layer-face 抽出）
    export_one(svg, "star", ["layer-star"])
    export_one(svg, "dust", ["layer-dust"])

    # 正常表情的可动部件（分层视差）
    export_one(svg, "eyes", ["layer-eyes"])            # 眼白 ±6
    export_one(svg, "pupils", ["layer-pupils"])        # 瞳孔 ±8
    export_one(svg, "mouth_normal", ["expr-mouth-normal"])  # 嘴 ±4

    # 非默认表情（扁平整张，替换眼+瞳孔+嘴）
    export_one(svg, "expr_happy", ["expr-happy"])
    export_one(svg, "expr_surprise", ["expr-surprise"])
    export_one(svg, "expr_angry", ["expr-angry"])

    print(f"全部导出到 {OUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
