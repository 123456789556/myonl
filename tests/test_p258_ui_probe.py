# -*- coding: utf-8 -*-
"""P258：界面探针必须真的接在 CI 上，而不是又躺在某个人本地的目录里。

这几条守的是「接线」，不是探针的具体断言内容（那是 probe_shell.py 自己的事）：
  - 探针脚本在仓库里，且不认识任何本机绝对路径（不然 CI 上直接找不到）；
  - workflow 真的会构建单文件、装 Chromium、跑它、并且以它的 exit code 为准；
  - 探针条数不许偷偷减少（减了就说明有人在删麻烦）。
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "tools" / "ui_probe" / "probe_shell.py"
WF = ROOT / ".github" / "workflows" / "ui-probe.yml"
REQ = ROOT / "requirements-ui.txt"
MIN_CHECKS = 19


def test_probe_script_in_repo() -> None:
    assert PROBE.is_file(), "探针脚本不在仓库里 —— 那就还是「手点」"
    text = PROBE.read_text(encoding="utf-8")
    assert "尺寸底板/" not in text, "探针里还留着本机目录的路径，CI 上跑不了"
    assert "D:\\" not in text and "D:/" not in text, "探针里写死了本机盘符"


def test_probe_has_enough_checks() -> None:
    text = PROBE.read_text(encoding="utf-8")
    n = text.count("rep.check(")
    assert n >= MIN_CHECKS, "探针只剩 %d 条（应 ≥%d）—— 少了就说明有人在删难做的断言" % (n, MIN_CHECKS)


def test_probe_exit_code_semantics() -> None:
    text = PROBE.read_text(encoding="utf-8")
    assert "return 0 if rep.bad == 0 else 1" in text, "探针必须以「有不符就 exit 1」收尾，否则 CI 永远绿"


def test_workflow_wired() -> None:
    assert WF.is_file(), "没有 .github/workflows/ui-probe.yml，探针等于没跑"
    text = WF.read_text(encoding="utf-8")
    for need, why in [
        ("tools/build_editor_single.py", "要先构建 dist 里的单文件"),
        ("playwright install chromium", "要装浏览器"),
        ("tools/ui_probe/probe_shell.py", "要真的调用探针"),
        ("exit $code", "要以探针的退出码为准，不能吞掉"),
        ("editor/**", "编辑器一改就要跑"),
        ("upload-artifact", "失败时要能看到截图"),
    ]:
        assert need in text, "workflow 缺了「%s」：%s" % (need, why)


def test_probe_requirements() -> None:
    assert REQ.is_file(), "缺 requirements-ui.txt"
    assert "playwright" in REQ.read_text(encoding="utf-8").lower()


def test_main_pytest_matrix_not_polluted() -> None:
    """Chromium 不许塞进主门禁矩阵（7 个 Python 版本都要装浏览器，纯拖时间）。"""
    main = (ROOT / "requirements-dev.txt").read_text(encoding="utf-8").lower()
    assert "playwright" not in main, "playwright 应该只在 requirements-ui.txt 里"
