# -*- coding: utf-8 -*-
"""P114：JS 内核（parser.js + pack.js）—— 手机端出成品的最后一块。

这些断言不是为了凑数，是给三个真踩过的坑上锁：
1. 解析器与 Python 版产出不一致（手机打出来的和电脑打出来的不一样）；
2. pack.js 里写字面脚本标签，宿主内联时被 HTML 解析器切成两段，
   MYONLPack 直接 undefined（编辑器的「做成成品」按钮点了没反应）；
3. 编辑器单文件没把内核内联进去，装到手机上才发现按钮是空的。
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.slow]

ROOT = Path(__file__).resolve().parent.parent


def test_parser_js_exists():
    p = ROOT / "engine" / "parser.js"
    assert p.is_file(), "engine/parser.js 缺失：手机端就编不出成品"
    src = p.read_text(encoding="utf-8")
    assert "MYONLParser" in src
    # 中文标识符靠这个字符类撑：Python 的 \w 含 CJK，JS 的 \w 不含
    assert "u4e00" in src, "中文名字/标签的正则区间被删了，@set 信任 = 0 会解析失败"


def test_pack_js_exists():
    p = ROOT / "engine" / "pack.js"
    assert p.is_file(), "engine/pack.js 缺失：手机端就拼不出成品 HTML"
    assert "MYONLPack" in p.read_text(encoding="utf-8")


def test_pack_js_has_no_literal_script_tag():
    """字面标签会提前闭合宿主脚本（真事故，见文件头注释）。"""
    src = (ROOT / "engine" / "pack.js").read_text(encoding="utf-8")
    assert "<script" not in src, "pack.js 里出现字面开头标签，内联进编辑器时会被切断"
    assert "</script" not in src, "pack.js 里出现字面收尾标签，内联进编辑器时会提前闭合"


def test_editor_index_loads_kernel():
    html = (ROOT / "editor" / "index.html").read_text(encoding="utf-8")
    assert "/parser.js" in html
    assert "/pack.js" in html
    # 599 行的硬上限还在（tests/test_code_health.py 也会查，这里顺手防一手）
    assert len(html.splitlines()) < 600


def test_editor_backend_serves_kernel():
    src = (ROOT / "engine" / "editor.py").read_text(encoding="utf-8")
    assert '"/parser.js"' in src
    assert '"/pack.js"' in src
    # 内核文件在 engine/，_serve_editor_file 必须能回落到那里
    assert "os.path.dirname(os.path.abspath(__file__))" in src


def test_pack_diff_matches_python():
    """5 个真实工程，JS 与 Python 逐字段比对。没装 node 就跳过。"""
    if not shutil.which("node"):
        import pytest
        pytest.skip("这台机器没有 node，跳过对拍")
    r = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "pack_diff.py")],
        capture_output=True, text=True, encoding="utf-8", cwd=str(ROOT),
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    assert r.returncode == 0, "JS 与 Python 解析结果不一致：\n" + r.stdout[-1500:]
    assert "0 个不一致" in r.stdout
