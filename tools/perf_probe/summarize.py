# -*- coding: utf-8 -*-
"""汇总三份实测 JSON，打印表格供报告引用。只读结果，不写产物。"""
import json
import statistics
from pathlib import Path

R = Path(__file__).resolve().parent / "results"


def med(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 2) if xs else None


def first_paint():
    d = json.loads((R / "first_paint.json").read_text(encoding="utf-8"))
    print("=== 首屏 TTI ms（中位 / min / max / 各次）===")
    for r in d["results"]:
        t = r["tti_ms"]
        print(f"{r['profile']:14} {r['viewport']:18} {r['pack']:8} "
              f"med={t['median']:7} min={t['min']:7} max={t['max']:7} runs={t['runs']}")


def assets():
    d = json.loads((R / "assets_load.json").read_text(encoding="utf-8"))
    print("\n=== 素材递增：帧时间 median/p95/over50、heap used MB、活跃素材 ===")
    for r in d["results"]:
        frames = [f or {} for f in r["frames"]]
        heap = [h or {} for h in r["heap"]]
        assets = r["assets"]
        fmed = med([f.get("median") for f in frames])
        fp95 = med([f.get("p95") for f in frames])
        fmax = med([f.get("max") for f in frames])
        over = med([f.get("over50") for f in frames])
        hmed = med([h.get("usedMb") for h in heap])
        amed = med([a.get("mb") if a else None for a in assets])
        names = med([a.get("names") if a else None for a in assets])
        print(f"{r['profile']:14} n={r['count']:3} med={fmed:7} p95={fp95:7} "
              f"max={fmax:7} over50={over:5} heapUsed={hmed}MB assetsMb={amed} names={names}")


def movie():
    d = json.loads((R / "movie_release.json").read_text(encoding="utf-8"))
    print("\n=== 视频释放：release 后 movie.count / readyState / paused / srcCleared / heap ===")
    for s in d["summary"]:
        print(s["profile"])
        for i, rel in enumerate(s["release1_movie"]):
            print(f"  run{i+1}: release1={rel} srcCleared1={s['srcCleared1_runs'][i]} "
                  f"srcCleared2={s['srcCleared2_runs'][i]} heap={s['heap'][i]}")


def rotation():
    d = json.loads((R / "rotation_t0.json").read_text(encoding="utf-8"))
    print("\n=== 转屏 t0：帧号 before/land/back + 环差 ===")
    for r in d["results"]:
        print(r["profile"], "length=", r["length"], "deltas=", r["deltas"])


if __name__ == "__main__":
    first_paint()
    assets()
    movie()
    rotation()
