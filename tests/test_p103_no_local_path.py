"""P103：成品里不许有开发机的路径。

`ins` 里每条指令都带来源文件，编辑器靠它把报错指到具体那一行 —— 这是对的。
但这份列表会原样内联进成品 HTML，而成品是发给玩家玩的。

后果有两层：
  轻的，玩家看到一串 `D:\\娱乐工作区\\...` 不知道是什么；
  重的，等于把开发机的目录结构跟着每个游戏一起发出去。

这不是理论风险：v1.1.1 之前的包每一个都带着它，只是没人去翻那段 JSON。
"""
import os
import re
import tempfile

import pytest

pytestmark = [pytest.mark.unit]

from engine import webpack  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEMO = os.path.join(ROOT, "games", "newbie_demo")


def _build() -> str:
    fd, out = tempfile.mkstemp(suffix=".html")
    os.close(fd)
    try:
        webpack.build_single(DEMO, out, title="新手示例")
        with open(out, encoding="utf-8") as f:
            return f.read()
    finally:
        if os.path.exists(out):
            os.remove(out)


@pytest.fixture(scope="module")
def html() -> str:
    return _build()


def test_成品不含本机绝对路径(html):
    """盘符路径、家目录、工作区别名，一个都不许有。"""
    for bad in ("D:\\\\", "C:\\\\Users", "娱乐工作区", "\\\\玩具项目"):
        assert bad not in html, f"成品里出现了本机路径片段：{bad}"


def test_指令来源只留文件名(html):
    """file 字段必须是纯文件名，不能带目录。"""
    files = re.findall(r'"file":"([^"]*)"', html)
    assert files, "找不到 file 字段——打包链路变了，这条断言需要跟着改"
    for f in files:
        assert not f.startswith(("D:", "C:", "/")), f"file 还是绝对路径：{f}"
        assert "\\\\" not in f and "/" not in f, f"file 带了目录：{f}"
