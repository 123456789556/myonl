"""P108：编辑器里的两处「廉价感」—— 静态打开报红字、状态栏版本号停在 rc19。

这两个都不影响功能，但都是从玩家视角一眼看到的错：
1. 双击 index.html 打开时 /api/assets 回一段 404 HTML，旧代码把它当「素材清单读取失败」红字挂着。
2. index.html 把版本写死成 rc19，发到 rc23 了它还写 rc19 —— 报 bug 时两边说的不是同一版。
"""
from pathlib import Path
import re
import pytest

pytestmark = [pytest.mark.unit]

ROOT = Path(__file__).resolve().parents[1]


def _read(*parts):
    return ROOT.joinpath(*parts).read_text(encoding="utf-8")


def test_静态打开不再报素材清单失败():
    src = _read("editor", "editor_main.js")
    i = src.index("async function refreshAssets()")
    seg = src[i:i + 1600]
    assert 'headers.get("content-type")' in seg, "先看返回的是不是 JSON，别对 404 的 HTML 直接 json()"
    assert "assetsReady = false" in seg
    assert 'setAssetHint("素材清单读取失败：" + e' not in seg, "没有后端不是错误，不能挂红字"


def test_版本号只有一个来源():
    # 真源已收口到 engine/_version.py（P214）。这里只守「别在别处再写死一个」。
    ver = _read("engine", "_version.py")
    m = re.search(r'^VERSION\s*=\s*"([0-9]+\.[0-9]+\.[0-9]+)"', ver, re.M)
    assert m, "_version.py 里的 VERSION 必须是 x.y.z 三段，不带 rc/beta 后缀"
    init = _read("engine", "__init__.py")
    assert "from ._version import VERSION as __version__" in init, \
        "__version__ 必须从 _version.py 转挂，不许再写死一个数字"
    assert not re.search(r'__version__\s*=\s*"[0-9]', init), "__init__.py 里还有写死的版本号"
    html = _read("editor", "index.html")
    assert not re.search(r"v1\.0\.0-rc\d+", html), "index.html 不许再写死版本号"
    ed = _read("engine", "editor.py")
    assert "/api/version" in ed, "后端要提供版本端点"
    assert "def _app_version(" in ed
    shell = _read("editor", "editor_shell.js")
    assert 'fetch("/api/version"' in shell
    assert "MYONL · 本地" in shell, "没有后端时要老实说本地，不能瞎报一个 rcNN"


def test_发行包版本不再自己写一个():
    """tools/build_release_zip.py 以前写死 v1.0.0-rc19，与 tag 无关。"""
    src = _read("tools", "build_release_zip.py")
    assert "from engine._version import VERSION" in src
    assert not re.search(r'DEFAULT_VERSION\s*=\s*"v1\.0\.0', src), "又写死了一个版本号"


def test_版本号不落后于已发布的包():
    """版本号必须真的往前走，别又漂回 1.0.0。"""
    ver = _read("engine", "_version.py")
    m = re.search(r'^VERSION\s*=\s*"([0-9]+)\.([0-9]+)\.([0-9]+)"', ver, re.M)
    assert m, "找不到 VERSION"
    ma, mi, pa = (int(x) for x in m.groups())
    assert (ma, mi, pa) >= (1, 1, 0), "版本号停在 1.0.x 说明又忘了跟着发版走"
