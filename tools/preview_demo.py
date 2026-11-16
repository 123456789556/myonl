"""把示例工程重新导出成播放器预览用的单文件（放仓库根 dist/single，/single-file/ 读的就是这里）。"""
import os
import sys

sys.path.insert(0, os.getcwd())

from engine.webpack import build_single  # noqa: E402

out = os.path.join("dist", "single", "教程示例.html")
os.makedirs(os.path.dirname(out), exist_ok=True)
r = build_single(os.path.join("games", "教程示例"), out)
print("bytes", (r or {}).get("bytes"), "->", out)
