"""P214：exe 与 APK 的版本必须同源、同号。

背景（实证）：同一份代码曾同时自称三个版本 ——
  `engine/__init__.py` `__version__ = "1.0.0rc24"`（桌面状态栏 `MYONL v1.0.0rc24`）
  `tools/build_release_zip.py` `DEFAULT_VERSION = "v1.0.0-rc19"`（exe 发行 zip 名）
  git tag `v1.2.32`（APK 的 versionName / versionCode，CI 从 tag 推）
三处互不校验。用户两端的版本号对不上，报 bug 时说的不是同一版。

现在真源只有 `engine/_version.py` 的 `VERSION`，其余全部推导或校验。
本文件守「推导链没断」，CI 另外守「tag 与 VERSION 一致」。
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

ROOT = Path(__file__).resolve().parents[1]
EXE_WF = ROOT / ".github" / "workflows" / "windows-exe.yml"


def _read(*parts: str) -> str:
    return ROOT.joinpath(*parts).read_text(encoding="utf-8")


def _version() -> str:
    m = re.search(r'^VERSION\s*=\s*"([^"]+)"', _read("engine", "_version.py"), re.M)
    assert m, "engine/_version.py 里没有 VERSION"
    return m.group(1)


def test_版本是干净的三段语义号():
    """不许带 rc / beta / dev 后缀：Android versionName 与 exe 包名直接拿它，
    带后缀会让两台设备显示的版本对不上。"""
    ver = _version()
    assert re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", ver), f"VERSION 不是 x.y.z：{ver}"


def test_engine_版本号从真源转挂():
    init = _read("engine", "__init__.py")
    assert "from ._version import VERSION as __version__" in init


def test_发行包版本从真源推导():
    src = _read("tools", "build_release_zip.py")
    assert "from engine._version import VERSION" in src
    assert 'DEFAULT_VERSION = "v" + _VER' in src, "DEFAULT_VERSION 必须由 VERSION 拼出来，不许写死"


def test_apk_versionName来自tag():
    """APK 侧靠 tag，所以 tag 必须与 VERSION 一致 —— 由 CI 守，这里守推导没被改坏。"""
    wf = _read(".github", "workflows", "android-apk.yml")
    assert "MYONL_VERSION_NAME=$VER" in wf
    assert "MAJ * 10000 + MIN * 100 + PAT" in wf


def test_有打exe的CI():
    """P214 前 .github/workflows 里没有任何一条打 exe，desktop 只能本机手搓。"""
    assert EXE_WF.is_file(), "缺 .github/workflows/windows-exe.yml"
    src = EXE_WF.read_text(encoding="utf-8")
    assert "editor.spec" in src, "exe 必须用仓库里的 editor.spec，不要另起一套打包参数"
    assert "build_player_template" in src, "发行版缺玩家模板，编辑器里「打包游戏」会坏"
    assert "runs-on: windows-latest" in src
    assert "v*" in src, "tag 推送要自动出 exe"


def test_exe的CI会拦截版本不一致的tag():
    assert EXE_WF.is_file()
    src = EXE_WF.read_text(encoding="utf-8")
    assert "engine._version" in src, "CI 要读真源比对 tag"
    assert "github.ref_name" in src


def test_两端产物命名同号():
    """同一版号下，APK 与 exe 压缩包都带这个号，人能对着找。"""
    ver = _version()
    apk_wf = _read(".github", "workflows", "android-apk.yml")
    assert 'MYONL-${GITHUB_REF_NAME:-manual}.apk' in apk_wf
    exe_src = EXE_WF.read_text(encoding="utf-8")
    assert "MYONL-${{ github.ref_name }}-editor-win.zip" in exe_src
    assert ver  # 只用来提示：改了 VERSION 别忘了 tag 同名
