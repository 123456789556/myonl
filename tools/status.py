# -*- coding: utf-8 -*-
"""STATUS.md 自动数字区生成器（M0 收口）。

只负责「可机器验证的数字」：测试收集数、覆盖率、pyright 错误数、git 状态。
人负责的「在做/下一门槛/阻塞」写在 auto 块外面，脚本不碰。

用法：
    py -3 tools/status.py            # 打印
    py -3 tools/status.py --write    # 写回 docs/STATUS.md 的 auto 块

设计取舍：不跑全量 pytest（90 秒），只 collect；通过的用例数由「最近验证」表维护。
覆盖率读 .coverage（若存在），所以它反映的是「上一次带 --cov 的运行」。
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATUS_FILE = ROOT / "docs" / "STATUS.md"
BASELINE_FILE = ROOT / "tools" / "pyright-baseline.json"
BEGIN = "<!-- auto:begin -->"
END = "<!-- auto:end -->"


def _run(cmd: list[str], timeout: int = 120, env_extra: dict | None = None) -> tuple[int, str]:
    env = dict(os.environ)
    env.update(env_extra or {})
    try:
        proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout, env=env)
        return proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, f"{type(exc).__name__}: {exc}"


def _home_env() -> dict:
    """Windows 下 pyright-python 需要 HOME/USERPROFILE（用来放 .cache）。

    有些调用链（CI/工具子进程）会剥掉这两个变量；此时回落到 Python 的 home 或临时目录，
    保证 status.py 在「干净环境」里也能算数。
    """
    home = os.environ.get("USERPROFILE") or os.environ.get("HOME") or ""
    if not home:
        try:
            home = str(Path.home())
        except RuntimeError:
            home = ""
    if not home or home == "~":
        import tempfile

        home = tempfile.gettempdir()
    return {"HOME": home, "USERPROFILE": home}


def _run_sep(cmd: list[str], timeout: int = 120, env_extra: dict | None = None) -> tuple[int, str, str]:
    """跑命令并分别返回 stdout / stderr（pyright 的 JSON 在 stdout，告警在 stderr）。"""
    env = dict(os.environ)
    env.update(env_extra or {})
    try:
        proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout, env=env)
        return proc.returncode, proc.stdout or "", proc.stderr or ""
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, "", f"{type(exc).__name__}: {exc}"


def count_tests() -> str:
    code, out = _run([sys.executable, "-m", "pytest", "--collect-only", "-q"])
    m = re.search(r"(\d+) tests? collected", out)
    if m:
        return m.group(1)
    return "?"


def pyright_errors() -> tuple[str, str]:
    cmd = [sys.executable, "-m", "pyright", "engine", "--pythonpath", sys.executable, "--outputjson"]
    code, out, _err = _run_sep(cmd, timeout=180, env_extra=_home_env())
    try:
        data = json.loads(out[out.find("{"):])
        now = int((data.get("summary") or {}).get("errorCount", 0))
    except (ValueError, TypeError):
        return "?", "?"
    baseline = "?"
    try:
        raw = BASELINE_FILE.read_text(encoding="utf-8-sig")
        baseline = str(json.loads(raw).get("_total", "?"))
    except (OSError, ValueError):
        pass
    return str(now), baseline


def coverage_pct() -> str:
    """读门禁摘要（`tools/check_coverage.ps1` 写）；没有摘要才回退 .coverage。

    背景：任意一次带 --cov 的局部运行都会留下 .coverage，直接读它会让 STATUS 与门禁
    口径不一致（曾出现 66.56% vs 门禁 82.63%）。摘要文件带 HEAD 与时间，可判断是否过期。
    """
    summary_file = ROOT / ".coverage-summary.json"
    if summary_file.is_file():
        try:
            data = json.loads(summary_file.read_text(encoding="utf-8-sig"))
            pct = data.get("coverage")
            if not isinstance(pct, (int, float)):
                return "?"
            _, head_now = _run(["git", "rev-parse", "--short", "HEAD"], timeout=30)
            head_now = head_now.strip()
            head_then = str(data.get("head") or "").strip()
            note = "门禁实测"
            if head_then and head_now and head_then != head_now:
                note = f"门禁实测，但为旧提交 {head_then}，需重跑"
            return f"{float(pct):.2f}%（{note}）"
        except (OSError, ValueError, TypeError):
            return "?"
    cov_file = ROOT / ".coverage"
    if not cov_file.is_file():
        return "?"
    try:
        import io

        import coverage  # pytest-cov 已装则可用
        cov = coverage.Coverage(data_file=str(cov_file))
        cov.load()
        return f"{cov.report(file=io.StringIO()):.2f}%（非门禁实测，勿当真）"
    except Exception:  # noqa: BLE001 — 覆盖率只是展示，失败不影响门禁
        return "?"


def git_info() -> dict:
    info: dict = {}
    _, out = _run(["git", "rev-list", "--count", "HEAD"], timeout=30)
    info["commits"] = out.strip() or "?"
    _, out = _run(["git", "log", "-1", "--format=%h %s"], timeout=30)
    info["head"] = (out.strip() or "?")[:80]
    _, out = _run(["git", "status", "--porcelain"], timeout=30)
    info["dirty"] = "有未提交改动" if out.strip() else "干净"
    _, out = _run(["git", "tag", "--sort=-creatordate"], timeout=30)
    tags = [t for t in out.splitlines() if t.strip()]
    info["tag"] = tags[0] if tags else "（无 tag）"
    return info


def render_block() -> str:
    tests = count_tests()
    errors, baseline = pyright_errors()
    cov = coverage_pct()
    g = git_info()
    lines = [
        BEGIN,
        "<!-- 自动数字区：由 tools/status.py 写入，勿手改 -->",
        f"- 测试收集：{tests} 项（通过数见下方「最近验证」）",
        f"- 覆盖率：{cov}",
        f"- pyright：{errors} 个错误 / 基线 {baseline}"
        + ("（超出基线，需修）" if errors.isdigit() and baseline.isdigit() and int(errors) > int(baseline) else "（未超基线）"),
        f"- git：{g['commits']} 个提交 · 最新 tag {g['tag']} · HEAD {g['head']} · 工作区{g['dirty']}",
        END,
    ]
    return "\n".join(lines)


def write_status() -> bool:
    if not STATUS_FILE.is_file():
        print(f"错误：找不到 {STATUS_FILE}")
        return False
    text = STATUS_FILE.read_text(encoding="utf-8")
    start = text.find(BEGIN)
    end = text.find(END)
    if start < 0 or end < 0 or end < start:
        print("错误：STATUS.md 缺少 auto:begin / auto:end 标记")
        return False
    block = render_block()
    new_text = text[:start] + block + text[end + len(END):]
    STATUS_FILE.write_text(new_text, encoding="utf-8")
    print(f"已更新 {STATUS_FILE.relative_to(ROOT)}")
    return True


def main(argv: list[str]) -> int:
    if "--write" in argv:
        return 0 if write_status() else 1
    print(render_block())
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
