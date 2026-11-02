# -*- coding: utf-8 -*-
"""M2 发布流程验收：模拟陌生人从发行包走完「改一句 → 保存 → 运行 → 打包 → 成品启动」。

与 `verify_release_clean.ps1` 的分工：
- 那个脚本验证「双击 editor.exe 能开窗、冻结 exe 能跑 demo」；
- 本脚本验证发行版**真正的一键发布链路**：没有 Python/PyInstaller 时，
  编辑器也必须能把工程打成可玩的游戏（靠内置玩家模板复制，不需要编译）。

用法：
    py -3 tools/verify_release_flow.py                 # 用 dist/release 下最新的 zip
    py -3 tools/verify_release_flow.py --zip <zip> --keep

退出码：0 = 全流程通过；1 = 某一步失败；2 = 找不到 zip。
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from ctypes import wintypes
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parent.parent
APP_TITLE = "MYONL 编辑器"


def _log(step: str, message: str) -> None:
    print(f"{step} {message}", flush=True)


def _json(url: str, payload=None, timeout=10):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    req = urllib.request.Request(url, data=data, headers=headers,
                                 method="POST" if data else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def _window_titles(pids: set[int]) -> dict[int, str]:
    """返回 {pid: 可见窗口标题}（仅 Windows；用于确认真的开了窗口）。"""
    titles: dict[int, str] = {}
    try:
        user32 = ctypes.windll.user32
        EnumProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

        def _cb(hwnd, _lparam):
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value in pids and user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buf, length + 1)
                    titles[pid.value] = buf.value
            return True

        user32.EnumWindows(EnumProc(_cb), 0)
    except Exception:  # noqa: BLE001 — 非 Windows / 受限环境只跳过窗口断言
        pass
    return titles


def _wait_window(pids, timeout: float, title_hint: str = "") -> str:
    pid_set = {pids} if isinstance(pids, int) else set(pids)
    deadline = time.time() + timeout
    while time.time() < deadline:
        titles = _window_titles(pid_set)
        for title in titles.values():
            if not title_hint or title_hint in title:
                return title
        time.sleep(0.5)
    return ""


def _editor_port(pid: int, timeout: float = 40) -> int:
    """找到编辑器内置 HTTP 服务的端口（随机端口，只能从进程/探测反查）。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            for conn in psutil.Process(pid).net_connections(kind="tcp"):
                if conn.status == psutil.CONN_LISTEN and conn.laddr:
                    return int(conn.laddr.port)
        except (psutil.Error, OSError):
            pass
        # 兜底：扫全部 127.0.0.1 监听端口，用 /api/script 认领
        try:
            for conn in psutil.net_connections(kind="tcp"):
                if (conn.status == psutil.CONN_LISTEN and conn.laddr
                        and conn.laddr.ip in ("127.0.0.1", "0.0.0.0", "::1", "::")):
                    try:
                        probe = _json(f"http://127.0.0.1:{conn.laddr.port}/api/script", timeout=1)
                    except Exception:  # noqa: BLE001
                        continue
                    if "text" in probe:
                        return int(conn.laddr.port)
        except (psutil.Error, OSError):
            pass
        time.sleep(0.7)
    raise TimeoutError("编辑器 HTTP 服务未就绪")


def _wait_job(base: str, job_id: str, timeout: float = 180) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = _json(f"{base}/api/pack/status?id={job_id}", timeout=10)["job"]
        if status.get("status") != "running":
            return status
        time.sleep(1.0)
    raise TimeoutError("打包任务超时")


def _fresh_env(profile: Path) -> dict:
    env = dict(os.environ)
    env.pop("PYTHONHOME", None)
    env.pop("PYTHONPATH", None)
    env["APPDATA"] = str(profile / "AppData" / "Roaming")
    env["LOCALAPPDATA"] = str(profile / "AppData" / "Local")
    env["USERPROFILE"] = str(profile)
    env["TEMP"] = str(profile / "Temp")
    env["TMP"] = env["TEMP"]
    env["PATH"] = os.pathsep.join([os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32"),
                                   os.environ.get("SystemRoot", r"C:\Windows")])
    for key in ("APPDATA", "LOCALAPPDATA", "USERPROFILE", "TEMP"):
        Path(env[key]).mkdir(parents=True, exist_ok=True)
    return env


def run_flow(zip_path: Path, keep: bool = False) -> int:
    work = Path(tempfile.mkdtemp(prefix="myonl_flow_"))
    editor = None
    try:
        _log("[1/6]", f"解压 {zip_path.name} → {work}")
        with __import__("zipfile").ZipFile(zip_path) as zf:
            zf.extractall(work)
        base = next(p for p in work.iterdir() if p.is_dir())
        exe = base / "editor" / "editor.exe"
        project = base / "games" / "教程示例"
        if not exe.is_file() or not project.is_dir():
            raise RuntimeError("发行包里缺少 editor.exe 或 games/教程示例")

        env = _fresh_env(work / "_profile")
        _log("[2/6]", "启动发行版编辑器（无 Python 环境 + 空 AppData）")
        editor = subprocess.Popen([str(exe), "--project", str(project)],
                                  cwd=str(base), env=env,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        port = _editor_port(editor.pid)
        api = f"http://127.0.0.1:{port}"
        title = _wait_window(editor.pid, 25, APP_TITLE)
        if not title:
            raise RuntimeError("编辑器窗口没有打开")
        _log("      ", f"编辑器窗口已打开 [{title}] · API {api}")

        _log("[3/6]", "读取剧本并改一句（模拟用户编辑）")
        original = _json(f"{api}/api/script")["text"]
        marker = "\n@ 流程验证：这一句由发行版编辑器写入。\n@end"
        if "@end" in original:
            edited = original.rsplit("@end", 1)[0].rstrip() + marker
        else:
            edited = original + marker
        _json(f"{api}/api/script", {"text": edited})
        saved = _json(f"{api}/api/script")
        if "流程验证" not in saved["text"]:
            raise RuntimeError("保存后读回的内容里没有修改行")

        _log("[4/6]", "语法检查 + 点「运行」打开预览窗口")
        checked = _json(f"{api}/api/check", {"text": edited})
        if not checked.get("ok"):
            raise RuntimeError(f"语法检查失败：{checked.get('message')}")
        _json(f"{api}/api/run", {"text": edited})
        child_title = ""
        deadline = time.time() + 20
        while time.time() < deadline and not child_title:
            try:
                kids = psutil.Process(editor.pid).children(recursive=True)
            except psutil.Error:
                kids = []
            child_title = _wait_window({k.pid for k in kids}, 1, "教程示例")
        if not child_title:
            raise RuntimeError("点「运行」后没有出现游戏窗口")
        _log("      ", f"游戏预览窗口已打开 [{child_title}]")
        try:
            for kid in psutil.Process(editor.pid).children(recursive=True):
                kid.kill()
        except psutil.Error:
            pass

        _log("[5/6]", "点「打包发布」——发行版必须靠内置玩家模板完成")
        started = time.time()
        resp = _json(f"{api}/api/pack/build",
                     {"project": "教程示例", "version": "1.0.0"}, timeout=30)
        if not resp.get("ok"):
            raise RuntimeError(f"打包请求失败：{resp.get('message')}")
        job = _wait_job(api, resp["job_id"])
        if job.get("status") != "ok":
            raise RuntimeError(f"打包失败：{job.get('message')}")
        result = job["result"]
        built_exe = Path(result["exe"])
        if not built_exe.is_file():
            raise RuntimeError(f"打包产物不存在：{built_exe}")
        _log("      ", f"打包完成：{result['output_dir']}（{result['size_bytes']/1024/1024:.1f} MB，"
                       f"{time.time()-started:.1f}s）")

        _log("[6/6]", "启动打包产物（同一套无 Python 环境）")
        demo = subprocess.Popen([str(built_exe)], cwd=str(built_exe.parent), env=env)
        demo_title = _wait_window(demo.pid, 30, "教程示例")
        if not demo_title:
            raise RuntimeError("打包产物没有打开游戏窗口")
        _log("      ", f"成品窗口已打开 [{demo_title}]")
        demo.kill()

        _log("PASS", "发行包从编辑到成品全流程通过（未使用 Python / PyInstaller）")
        return 0
    except Exception as exc:  # noqa: BLE001 — 验收脚本要给出明确失败原因
        _log("FAIL", f"{type(exc).__name__}: {exc}")
        return 1
    finally:
        if editor is not None and editor.poll() is None:
            try:
                for kid in psutil.Process(editor.pid).children(recursive=True):
                    kid.kill()
            except psutil.Error:
                pass
            editor.kill()
        if keep:
            print(f"保留现场：{work}")
        else:
            shutil.rmtree(work, ignore_errors=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="验证发行包「改→存→跑→打包→成品」全流程")
    ap.add_argument("--zip", default="", help="发行包 zip（缺省取 dist/release 下最新）")
    ap.add_argument("--keep", action="store_true", help="保留解压现场便于排查")
    args = ap.parse_args(argv)
    if args.zip:
        zip_path = Path(args.zip).resolve()
    else:
        candidates = sorted((ROOT / "dist" / "release").glob("MYONL*.zip"),
                            key=lambda p: p.stat().st_mtime, reverse=True)
        if not candidates:
            print("错误：dist/release 下没有发行包，先跑 tools/build_release_zip.py")
            return 2
        zip_path = candidates[0]
    if not zip_path.is_file():
        print(f"错误：找不到发行包 {zip_path}")
        return 2
    return run_flow(zip_path, keep=args.keep)


if __name__ == "__main__":
    raise SystemExit(main())
