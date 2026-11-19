# -*- coding: utf-8 -*-
"""P136 技术债 1：单文件体积告警必须贯通到作者眼前，JS 与 Python 同口径。

守护点：
1. webpack.py 与 pack.js 阈值同为 40MB / 80MB，并各自给出 soft/hard 等级；
2. editor.py 接口把告警文案 + 等级原样透传；
3. 两条前端路径（UI 设计中心页、菜单壳层）都显示告警，硬线是强提示；
4. 离线打包（gal_offline.js）用打包器返回的体积/告警，不再自己拿字符串长度瞎算。

本机无浏览器，前端只做源码断言；打包逻辑用 node 直接跑（没装 node 就跳过 JS 侧）。
"""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

ROOT = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# ---------- 1：两边阈值口径一致 ----------

def test_python_thresholds_match_js():
    py = _read("engine/webpack.py")
    js = _read("engine/pack.js")
    assert "FILE_SOFT_WARN = 40 * 1024 * 1024" in py
    assert "FILE_HARD_WARN = 80 * 1024 * 1024" in py
    assert "var FILE_SOFT_WARN = 40 * 1024 * 1024" in js
    assert "var FILE_HARD_WARN = 80 * 1024 * 1024" in js


def test_python_emits_warning_level():
    py = _read("engine/webpack.py")
    assert 'file_warning_level = "hard"' in py
    assert 'file_warning_level = "soft"' in py
    assert '"file_warning_level": file_warning_level' in py


def test_js_emits_warning_level():
    js = _read("engine/pack.js")
    assert 'fileWarningLevel = "hard"' in js
    assert 'fileWarningLevel = "soft"' in js
    assert "fileWarningLevel: rep.fileWarningLevel" in js


# ---------- 2：后端接口透传 ----------

def test_editor_api_passes_warning_level():
    src = _read("engine/editor.py")
    assert '"file_warning": stat.get("file_warning", "")' in src
    assert '"file_warning_level": stat.get("file_warning_level", "")' in src


# ---------- 3：前端两条路径都看得见告警 ----------

def test_uidesign_shows_hard_warning_as_strong():
    ui = _read("editor/editor_uidesign.js")
    assert "resp.file_warning" in ui
    assert 'resp.file_warning_level === "hard"' in ui
    # 硬线走红底强提示块，不能只跟软线一样一行红字
    assert "rgba(255,77,77" in ui


def test_shell_menu_shows_warning_that_were_dropped():
    shell = _read("editor/editor_shell.js")
    assert "d.file_warning" in shell, "菜单导出路径把体积告警丢了"
    assert "d.file_warning_level" in shell


def test_offline_export_uses_packer_report():
    off = _read("editor/gal_offline.js")
    assert "r.fileMb" in off, "离线打包没拿打包器算的体积"
    assert "r.fileWarningLevel" in off
    assert "r.fileWarning" in off
    # 旧的字符串长度瞎算不能再留
    assert "moviesPack[k].src.length" not in off


# ---------- 4：node 实跑 pack.js 三档判定 ----------

@pytest.mark.skipif(not shutil.which("node"), reason="本机没有 node，跳过 JS 逻辑实跑")
def test_pack_js_levels_real_run():
    js = _read("engine/pack.js")
    parser = _read("engine/parser.js")
    probe = r"""
      var sandbox = {};
      var window = sandbox;
      eval(%PARSER%);
      eval(%PACK%);
      function dataUri(bytes) {
        var b64 = '';
        for (var i = 0; i < bytes; i++) b64 += 'A';
        return 'data:image/png;base64,' + b64;
      }
      function build(n) {
        return window.MYONLPack.buildPack({
          title: 't', scriptText: '', assets: { a: dataUri(n) }, audio: {},
          videos: {}, movies: {}, config: {}, orientation: 'any'
        });
      }
      var soft = build(Math.ceil(41 * 1024 * 1024 * 4 / 3));
      var hard = build(Math.ceil(81 * 1024 * 1024 * 4 / 3));
      var calm = build(1024);
      console.log(JSON.stringify({
        soft: soft.fileWarningLevel, hard: hard.fileWarningLevel, calm: calm.fileWarningLevel,
        softMb: soft.fileMb, hardMb: hard.fileMb
      }));
    """
    probe = probe.replace("%PARSER%", repr(parser)).replace("%PACK%", repr(js))
    r = subprocess.run(["node", "-e", probe], capture_output=True, text=True,
                       encoding="utf-8", cwd=str(ROOT))
    assert r.returncode == 0, r.stderr
    import json
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out["soft"] == "soft", out
    assert out["hard"] == "hard", out
    assert out["calm"] == "", out
