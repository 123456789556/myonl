"""打包日志的控制台编码守护（2026-11-10，release-smoke 实测回归）。

起因：GitHub windows-latest runner 是英文区域，控制台编码 cp1252，
`packaging.py` 第一句 `print("开始打包：…")` 抛 UnicodeEncodeError，
把整个打包流程打断——产物还没开始写，看起来像"打包功能坏了"。
"""
import io
import sys

import pytest

from engine import packaging

pytestmark = [pytest.mark.unit]


def _cp1252_stream() -> io.TextIOWrapper:
    """模拟英文区域 Windows 的控制台：能收 ASCII，收不了中文。"""
    return io.TextIOWrapper(io.BytesIO(), encoding="cp1252")


def test_cp1252_console_crashes_without_guard(monkeypatch):
    """守护测试的前提：不加保护时确实会崩，否则这条守护没有意义。"""
    monkeypatch.setattr(sys, "stdout", _cp1252_stream())
    with pytest.raises(UnicodeEncodeError):
        print("开始打包：教程示例", flush=True)


def test_ensure_tolerant_console_survives_cp1252(monkeypatch):
    """加了保护之后，中文日志不再中断流程（stdout / stderr 都要覆盖）。"""
    out, err = _cp1252_stream(), _cp1252_stream()
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "stderr", err)
    packaging.ensure_tolerant_console()
    print("开始打包：教程示例", flush=True)
    print("打包完成", file=sys.stderr, flush=True)


def test_utf8_console_keeps_chinese(monkeypatch):
    """中文控制台上行为不变：中文原样输出，不许被替换掉。"""
    buf = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buf)
    packaging.ensure_tolerant_console()          # StringIO 没有 reconfigure，应被跳过
    print("开始打包：教程示例")
    assert "开始打包：教程示例" in buf.getvalue()


def test_none_stdout_is_ignored(monkeypatch):
    """PyInstaller 窗口化的 editor.exe 里 stdout 可能是 None，不许因此抛异常。"""
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    packaging.ensure_tolerant_console()
