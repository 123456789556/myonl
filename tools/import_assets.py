# -*- coding: utf-8 -*-
"""批量导入照片 / 短视频为引擎素材（大量素材导入）。

给「一次几十上百张照片 + 若干短视频」的项目用：源目录扫一遍，
自动转尺寸、压体积、去重、改安全文件名、写清单和可直接粘贴的 .gal 片段。

处理规则：
- 照片 → 背景（默认 cover 裁切到画布尺寸存 JPG；也可 --format png / --kind sprite 存透明 PNG）
- 短视频 → 帧序列 images/videos/<名>_001.png 起（引擎 @video 的格式），默认 30fps、最多 10 秒
- 去重：按 SHA1 内容哈希，重复的文件跳过并记录
- 冲突：目标同名时 rename(默认) / skip / overwrite

产物：
- 工程 images/ 下素材
- import_report.json：每个文件的源/目标/哈希/状态
- asset_manifest.json：素材清单（名字/类型/文件/字节/哈希），给打包与版本管理用
- import_snippets.gal：可直接粘贴的 @bg / @video 引用

用法：
    py -3 tools/import_assets.py D:\素材\照片 --project games/我的游戏
    py -3 tools/import_assets.py D:\素材\短视频 --project games/我的游戏 --no-images
    py -3 tools/import_assets.py D:\素材 --project games/我的游戏 --kind sprite --format png
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import re
import sys
from pathlib import Path

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
_ILLEGAL = re.compile(r'[\\/:*?"<>|\s]+')


def _sha1(path: Path) -> str:
    h = hashlib.sha1()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _safe_name(stem: str) -> str:
    name = _ILLEGAL.sub("_", str(stem)).strip("._")
    return name or "asset"


def _canvas_of(project: Path) -> tuple[int, int]:
    try:
        from engine import config as cfgapi  # 仅用于读画布尺寸

        return tuple(cfgapi.load(str(project)).canvas_size())
    except Exception:  # noqa: BLE001 — 读不到配置就用默认画布，不阻塞导入
        return (1280, 720)


def _cover(img, size: tuple[int, int]):
    """等比放大到覆盖目标尺寸，再居中裁切（照片当背景用，不留黑边）。"""
    from PIL import Image

    tw, th = size
    sw, sh = img.size
    scale = max(tw / sw, th / sh)
    nw, nh = max(tw, int(round(sw * scale))), max(th, int(round(sh * scale)))
    img = img.resize((nw, nh), Image.LANCZOS)
    left, top = (nw - tw) // 2, (nh - th) // 2
    return img.crop((left, top, left + tw, top + th))


def _fit_height(img, height: int):
    """立绘：按高度等比缩放，保留透明通道（不铺满画布，引擎会自行缩放）。"""
    from PIL import Image

    w, h = img.size
    scale = height / h if h else 1.0
    return img.resize((max(1, int(round(w * scale))), height), Image.LANCZOS)


def _contain(img, size: tuple[int, int]):
    """等比缩进目标尺寸并居中（保留完整画面，四周补黑）。"""
    from PIL import Image

    tw, th = size
    out = Image.new("RGB", (tw, th), (0, 0, 0))
    fit = img.copy()
    fit.thumbnail((tw, th), Image.LANCZOS)
    out.paste(fit, ((tw - fit.width) // 2, (th - fit.height) // 2))
    return out


def _blur_pad(img, size: tuple[int, int], radius: int = 40, darken: float = 0.55):
    """竖屏素材（抖音 9:16 等）默认处理：背景用同图放大模糊压暗，前景完整等比居中。

    直接 cover 会把竖屏裁掉大半；letterbox 黑边又丑。模糊填充是短视频平台的通用做法：
    内容不丢、16:9 画面不空。
    """
    from PIL import Image, ImageEnhance, ImageFilter

    bg = _cover(img, size).filter(ImageFilter.GaussianBlur(radius))
    bg = ImageEnhance.Brightness(bg).enhance(darken)
    fg = img.copy()
    fg.thumbnail(size, Image.LANCZOS)
    bg.paste(fg, ((size[0] - fg.width) // 2, (size[1] - fg.height) // 2))
    return bg


def _pick_fit(img, requested: str) -> str:
    """auto：横屏照片/视频 cover 裁切；竖屏/方形（抖音短视屏）走模糊填充。"""
    if requested != "auto":
        return requested
    w, h = img.size
    ratio = (w / h) if h else 1.0
    return "cover" if ratio >= 1.25 else "blur"


def _apply_fit(img, size: tuple[int, int], fit: str):
    if fit == "contain":
        return _contain(img, size)
    if fit == "blur":
        return _blur_pad(img, size)
    return _cover(img, size)


def _unique_dest(dest: Path, on_conflict: str, taken: set) -> Path | None:
    if dest.name in taken:
        if on_conflict == "skip":
            return None
        if on_conflict == "overwrite":
            return dest
    elif not dest.exists():
        taken.add(dest.name)
        return dest
    elif on_conflict == "skip":
        return None
    elif on_conflict == "overwrite":
        taken.add(dest.name)
        return dest
    stem, suffix = dest.stem, dest.suffix
    for i in range(2, 1000):
        cand = dest.with_name(f"{stem}_{i}{suffix}")
        if cand.name not in taken and not cand.exists():
            taken.add(cand.name)
            return cand
    return None


def _process_image(src: Path, project: Path, canvas, kind: str, fmt: str,
                   prefix: str, on_conflict: str, taken: set, report: list, manifest: dict,
                   dry_run: bool, fit_requested: str = "auto", quality: int = 88) -> None:
    from PIL import Image, ImageOps

    entry = {"source": str(src), "type": "image", "kind": kind, "status": "ok"}
    try:
        with Image.open(src) as raw:
            img = ImageOps.exif_transpose(raw)
            if kind == "sprite":
                img = _fit_height(img.convert("RGBA"), canvas[1])
                suffix = ".png"
            else:
                rgb = img.convert("RGB")
                img = _apply_fit(rgb, canvas, _pick_fit(img, fit_requested))
                suffix = ".png" if fmt == "png" else ".jpg"
            name = _safe_name(src.stem)
            dest = project / "images" / f"{prefix}{name}{suffix}"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest = _unique_dest(dest, on_conflict, taken)
            if dest is None:
                entry.update(status="skipped", reason="目标已存在（on_conflict=skip）")
                report.append(entry)
                return
            if not dry_run:
                if suffix == ".jpg":
                    img.save(dest, "JPEG", quality=max(1, min(95, int(quality))), optimize=True)
                else:
                    img.save(dest, "PNG", optimize=True)
            entry["target"] = str(dest.relative_to(project)).replace("\\", "/")
            if not dry_run:
                entry["bytes"] = dest.stat().st_size
                entry["sha1"] = _sha1(dest)
                manifest["assets"].append({
                    "name": dest.stem, "type": kind, "file": entry["target"],
                    "bytes": entry["bytes"], "sha1": entry["sha1"], "source": str(src),
                })
    except Exception as exc:  # noqa: BLE001 — 单张坏图不打断整批导入
        entry.update(status="error", reason=f"{type(exc).__name__}: {exc}")
    report.append(entry)


def _extract_video(src: Path, project: Path, canvas, fps: int, max_seconds: float,
                   on_conflict: str, taken: set, report: list, manifest: dict,
                   dry_run: bool, fit_requested: str = "auto") -> None:
    entry = {"source": str(src), "type": "video", "status": "ok"}
    try:
        import av  # 视频解码（工具链依赖，见 requirements-dev.txt）
        from PIL import Image
    except ImportError as exc:
        entry.update(status="error", reason=f"缺少视频依赖：{exc}（pip install av）")
        report.append(entry)
        return
    try:
        name = _safe_name(src.stem)
        out_dir = project / "images" / "videos"
        first = out_dir / f"{name}_001.png"
        if first.exists() or f"{name}_001.png" in taken:
            if on_conflict == "skip":
                entry.update(status="skipped", reason="帧序列已存在")
                report.append(entry)
                return
        if not dry_run:
            out_dir.mkdir(parents=True, exist_ok=True)
        container = av.open(str(src))
        try:
            stream = container.streams.video[0]
            base = float(stream.time_base) if stream.time_base else 0.0
            limit = float(max_seconds)
            step = 1.0 / max(1, int(fps))
            next_t = 0.0
            frames = 0
            t_first = None
            t_last = 0.0
            for frame in container.decode(stream):
                t = float(frame.pts * base) if frame.pts is not None else frames / float(fps)
                if t > limit:
                    break
                if t + 1e-6 < next_t:
                    continue
                img = frame.to_image().convert("RGB")
                img = _apply_fit(img, canvas, _pick_fit(img, fit_requested))
                if not dry_run:
                    img.save(out_dir / f"{name}_{frames + 1:03d}.png", "PNG", optimize=True)
                if t_first is None:
                    t_first = t
                t_last = t
                frames += 1
                next_t = t + step  # 跟随源帧时间推进，避免「源比目标稀疏时」网格漂移
                if frames >= int(limit * fps) + 1:
                    break
        finally:
            container.close()
        duration = max(1e-6, (t_last - (t_first or 0.0)))
        # 输出 fps 用「实际保存帧数 / 时长」反算：源视频比目标 fps 稀疏时（如 12fps 素材），
        # 保存帧率就是源帧率，若按目标 30fps 写进 @video 会播成 0.4 倍速。
        fps_out = max(1, int(round(frames / duration))) if frames > 1 else int(fps)
        entry.update(target=f"images/videos/{name}_001.png 起 {frames} 帧",
                     frames=frames, fps_in=int(round((frames - 1) / duration)) if frames > 1 else int(fps),
                     fps=fps_out, duration=round(frames / fps_out, 2))
        if not dry_run:
            manifest["assets"].append({"name": name, "type": "video", "file": f"images/videos/{name}_001.png",
                                       "frames": frames, "fps": fps_out, "source": str(src)})
    except Exception as exc:  # noqa: BLE001
        entry.update(status="error", reason=f"{type(exc).__name__}: {exc}")
    report.append(entry)


def import_folder(source: Path, project: Path, *, kind: str = "bg", prefix: str = "bg_",
                  fmt: str = "jpg", fps: int = 30, max_seconds: float = 10.0,
                  on_conflict: str = "rename", include_images: bool = True,
                  include_videos: bool = True, dry_run: bool = False,
                  fit: str = "auto", quality: int = 88) -> dict:
    """扫描 source 目录并导入到 project。返回报告 dict（同时落盘 report/manifest/snippets）。"""
    source = Path(source).resolve()
    project = Path(project).resolve()
    if not source.is_dir():
        raise FileNotFoundError(f"源目录不存在：{source}")
    if not project.is_dir():
        raise FileNotFoundError(f"工程目录不存在：{project}")
    canvas = _canvas_of(project)
    report: list = []
    manifest = {"version": 1, "project": str(project),
                "imported_at": _dt.datetime.now().isoformat(timespec="seconds"),
                "canvas": list(canvas), "assets": []}
    taken: set = set()
    seen: dict = {}
    files = sorted(p for p in source.rglob("*") if p.is_file())
    for src in files:
        suffix = src.suffix.lower()
        is_image, is_video = suffix in IMAGE_EXTS, suffix in VIDEO_EXTS
        if not ((is_image and include_images) or (is_video and include_videos)):
            continue
        try:
            digest = _sha1(src)
        except OSError as exc:
            report.append({"source": str(src), "status": "error", "reason": f"读取失败：{exc}"})
            continue
        if digest in seen:
            report.append({"source": str(src), "type": "image" if is_image else "video",
                           "status": "skipped", "reason": f"重复内容（同 {seen[digest]}）"})
            continue
        seen[digest] = src.name
        if is_image:
            _process_image(src, project, canvas, kind, fmt, prefix, on_conflict,
                           taken, report, manifest, dry_run, fit, quality)
        else:
            _extract_video(src, project, canvas, fps, max_seconds, on_conflict,
                           taken, report, manifest, dry_run, fit)
    # 落盘：报告 / 清单 / 片段
    ok = [e for e in report if e.get("status") == "ok"]
    if not dry_run:
        (project / "import_report.json").write_text(
            json.dumps({"canvas": list(canvas), "source": str(source),
                        "summary": {"ok": len(ok), "total": len(report)},
                        "items": report}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
        (project / "asset_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        lines = ["# 素材导入生成：可直接复制到 script.gal", ""]
        for a in manifest["assets"]:
            if a["type"] == "video":
                lines.append(f"@video {a['name']} fps={a.get('fps', 30)}")
            else:
                lines.append(f"@bg {a['name']}")
        (project / "import_snippets.gal").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"summary": {"ok": len(ok), "total": len(report)}, "items": report,
            "canvas": list(canvas), "manifest": manifest}


def main(argv: list[str]) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="批量导入照片/短视频为 MYONL 素材")
    ap.add_argument("source", help="素材源目录（递归扫描）")
    ap.add_argument("--project", required=True, help="游戏工程目录（含 config.json）")
    ap.add_argument("--kind", choices=("bg", "sprite"), default="bg",
                    help="照片用途：bg=背景（cover 裁切，默认）/ sprite=立绘（透明 PNG）")
    ap.add_argument("--prefix", default="bg_", help="素材名前缀（默认 bg_；立绘可写角色名_）")
    ap.add_argument("--format", choices=("jpg", "png"), default="jpg", help="照片输出格式")
    ap.add_argument("--fit", choices=("auto", "cover", "contain", "blur"), default="auto",
                    help="画面适配：auto=横屏裁切/竖屏模糊填充（默认）；cover 裁切；contain 黑边；blur 模糊填充")
    ap.add_argument("--quality", type=int, default=88,
                    help="JPG 质量 1~95（默认 88；78=更小体积、92=更高画质；PNG 不受影响）")
    ap.add_argument("--fps", type=int, default=30, help="短视频转帧帧率（默认 30）")
    ap.add_argument("--max-seconds", type=float, default=10.0, help="每个短视频最多取多少秒")
    ap.add_argument("--on-conflict", choices=("rename", "skip", "overwrite"), default="rename")
    ap.add_argument("--no-images", action="store_true", help="不导入照片")
    ap.add_argument("--no-videos", action="store_true", help="不导入短视频")
    ap.add_argument("--dry-run", action="store_true", help="只扫描不落盘")
    args = ap.parse_args(argv)
    try:
        result = import_folder(
            Path(args.source), Path(args.project), kind=args.kind, prefix=args.prefix,
            fmt=args.format, fps=args.fps, max_seconds=args.max_seconds,
            on_conflict=args.on_conflict, include_images=not args.no_images,
            include_videos=not args.no_videos, dry_run=args.dry_run, fit=args.fit,
            quality=args.quality)
    except (OSError, ValueError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    summary = result["summary"]
    print(f"导入完成：成功 {summary['ok']} / 共 {summary['total']} 个文件（画布 {result['canvas'][0]}x{result['canvas'][1]}）")
    for item in result["items"]:
        state = item.get("status")
        if state != "ok":
            print(f"  [{state}] {Path(item['source']).name}：{item.get('reason', '')}")
    if not args.dry_run:
        print("已生成：import_report.json / asset_manifest.json / import_snippets.gal")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
