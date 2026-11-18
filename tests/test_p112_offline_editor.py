"""P112：手机离线编游戏这条线不许退化。

三件事必须一直成立：
1. `--lan` 不许回来（用户明确否决，传输走数据线）。
2. file:// 下不发探测请求（控制台不该刷 CORS 红字）。
3. 手机上「导出」是浮在最上层的一层，并且有真能用的按钮。
"""
from pathlib import Path
import re

import pytest

ROOT = Path(__file__).resolve().parent.parent
pytestmark = [pytest.mark.unit]


def _read(p):
    return (ROOT / p).read_text(encoding="utf-8")


def test_no_lan_editor():
    src = _read("engine/editor.py")
    assert "--lan" not in src
    assert "_lan_gate" not in src
    assert "0.0.0.0" not in src, "编辑器只能绑 127.0.0.1：那套接口能改剧本、能删文件"


def test_offline_probe_skips_file_protocol():
    src = _read("editor/gal_offline.js")
    assert "androidplatform" in src, "APK 里的 WebView 也要直接判离线"
    # 探针必须在「协议/域名判定」之后，file:// 不走到 XHR
    m = re.search(r"function _probe[\s\S]*?offline = true", src) or None
    bar = src.index("else {\n    try {\n      var probe")
    assert "location.protocol" in src[:bar]


def test_export_layer_sits_above_scene_page():
    css = _read("editor/editor.css")
    assert ".center-page.open.mode-export" in css
    assert "z-index: 440" in css


def test_offline_export_bar_has_real_actions():
    src = _read("editor/gal_offline.js")
    assert "__myonlExportGal" in src
    assert "__myonlExportLib" in src
    assert "off-export" in src
