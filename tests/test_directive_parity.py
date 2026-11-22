"""指令跨端一致性门禁：同一条 @ 指令，电脑端（Python）和手机端（JS）必须给同一结论。

为什么要这条：@ 指令是我们自造的。哪一端不认识，用户就会在那一端直接撞「未知指令」——
手机上打不开电脑端做的剧本，或者反过来。人肉记名单漏过，所以用机器对拍守着。

实现走 tools/check_directive_parity.py（同一份样例表），这里只做裁决：
- 两端都 OK 且 op 序列一致 → 过
- 两端都报错（说明这条样例本来就写错）→ 不算差异
- 一端 OK 一端报错 → 只允许在 KNOWN_ONE_SIDED 里（产品上明确只在一端可写）
- 其余一律红

没装 node 就跳过：这条检查的价值在开发机与本地门禁，CI 的 tests 流水线不一定带 node。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "check_directive_parity.py"

# 产品上明确「只有电脑端能写」的：手机端会给出中文提示，不是崩溃。
# 加新条目要同时改 docs 里的能力边界说明。
KNOWN_ONE_SIDED = {"anim", "plug"}


def _run():
    if not shutil.which("node"):
        pytest.skip("没装 node，跳过多端对拍")
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    p = subprocess.run([sys.executable, str(TOOL)], capture_output=True, text=True,
                       encoding="utf-8", cwd=str(ROOT), timeout=180, env=env)
    return p


def test_指令两端对拍没有真差异():
    p = _run()
    out = (p.stdout or "") + (p.stderr or "")
    assert "真差异 0 条" in out, f"出现真差异：\n{out[-1500:]}"
    assert p.returncode == 0, f"对拍退出码非 0：\n{out[-1500:]}"


def test_仅一端可用的指令在已知名单里():
    p = _run()
    out = (p.stdout or "") + (p.stderr or "")
    found = set()
    for line in out.splitlines():
        if line.startswith("[仅一端]"):
            found.add(line.split()[1].strip())
    assert found <= KNOWN_ONE_SIDED, (
        f"多出只有一端能用的指令：{sorted(found - KNOWN_ONE_SIDED)}"
        f"（要补另一端的实现，或写进 KNOWN_ONE_SIDED 并在文档里说明边界）"
    )
