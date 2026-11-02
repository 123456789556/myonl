"""CLI 冒烟测试：--check / --tojson / --fromjson 三命令可用，退出码符合 engine_spec.md。"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration]

ROOT = Path(__file__).resolve().parent.parent

VALID = "@character 林晚 #aaccff\n@bg classroom\n@label a\n@jump a\n@end\n"
INVALID = "@bg classroom\n@foo bar\n"


def run_cli(*args):
    # 子进程显式按 UTF-8 解码：engine/cli.py 会把自身 stdout 重配为 UTF-8，
    # 而 Windows 中文版 subprocess 的默认 errors 解码是 GBK（cp936），
    # 不指定 encoding 时 reader 线程会 UnicodeDecodeError，r.stdout 变成 None。
    return subprocess.run(
        [sys.executable, "-m", "engine.cli", *args],
        capture_output=True, text=True, encoding="utf-8", cwd=ROOT,
    )


def test_check_ok(tmp_path):
    f = tmp_path / "ok.gal"
    f.write_text(VALID, encoding="utf-8")
    r = run_cli("--check", str(f))
    assert r.returncode == 0
    assert "语法检查通过" in r.stdout


def test_check_bad(tmp_path):
    f = tmp_path / "bad.gal"
    f.write_text(INVALID, encoding="utf-8")
    r = run_cli("--check", str(f))
    assert r.returncode == 1
    assert "第 2 行" in r.stderr


def test_tojson_and_fromjson(tmp_path):
    gal = tmp_path / "ok.gal"
    gal.write_text(VALID, encoding="utf-8")
    js = tmp_path / "out.json"

    r = run_cli("--tojson", str(gal), "-o", str(js))
    assert r.returncode == 0
    instrs = json.loads(js.read_text(encoding="utf-8"))
    assert instrs[1] == {"op": "bg", "image": "classroom", "line": 2, "file": str(gal)}

    back = tmp_path / "back.gal"
    r = run_cli("--fromjson", str(js), "-o", str(back))
    assert r.returncode == 0
    assert "@bg classroom" in back.read_text(encoding="utf-8")
