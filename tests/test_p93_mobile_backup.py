"""P93 守护：手机端存档能带走、能带回。

手机端存档在 localStorage，而 localStorage **按 origin 隔离**。把导出的 HTML 换个文件名、
换个目录、或者从浏览器打开改成用文件管理器打开，就是另一个 origin —— 旧存档看不见。
浏览器不给跨 origin 读写的方法，所以唯一的解法是给玩家一个搬运口：
导出成文件、到新位置再导进来。这里钉住几件事：

1. 导出码带固定前缀，且是全量（本机所有 myonl: 键，不止当前作品）；
2. 导入只认 myonl: 前缀的键，别的东西一个不碰；
3. 存档页脚必须有「导出 / 导入」两个键，且 act() 里真有这两个分支；
4. 面板高度算的格子数与 drawSlots 实际画的一致（不一致就是让步长对不上，底下空一条）。
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PLAYER = ROOT / "web" / "myonl-player.js"

pytestmark = [pytest.mark.unit]


@pytest.fixture(scope="module")
def src():
    return PLAYER.read_text(encoding="utf-8")


def test_export_code_has_prefix(src):
    """导出码必须能被玩家一眼认出，并在导入时按前缀剥掉。"""
    assert '"MYONL1:" + b64encode' in src
    assert 'code.indexOf("MYONL1:")' in src


def test_export_is_whole_store(src):
    """导出扫全库的 myonl: 键 —— 换设备时别的作品也要一起搬走。"""
    block = src[src.index("function storeExportCode"):src.index("function storeImportCode")]
    assert 'k.indexOf("myonl:") !== 0' in block
    assert "localStorage.length" in block


def test_import_touches_only_own_keys(src):
    """导入只写自己的键：存档码里被人塞了别的字段也不能落进 localStorage。"""
    block = src[src.index("function storeImportCode"):src.index("function storeExportFile")]
    assert 'if (k.indexOf("myonl:") !== 0) return;' in block


def test_save_footer_has_export_import(src):
    """存档页脚两个键要在，act() 也要真有分支 —— 只画按钮不接动作是假功能。"""
    assert 'uiButton("exp"' in src
    assert 'uiButton("imp"' in src
    assert 'if (id === "exp")' in src
    assert 'if (id === "imp")' in src


def test_import_takes_a_file(src):
    """手机上下载目录里选文件，比让人手打一长串码现实。"""
    assert "function storeImportFile" in src
    assert 'inp.type = "file"' in src
    assert "FileReader" in src


def test_slot_panel_height_matches_rows(src):
    """menuPanel 预留的高度必须和 drawSlots 画的格子高度一致，否则面板底下空一条。"""
    panel = re.search(r"const ch = Math\.round\(L\.fs \* \(land \? (\d+\.\d) : (\d+\.\d)\)\);"
                      r"\s*\n\s*bodyH", src)
    assert panel, "menuPanel 里的 ch 算式没找到"
    slots = re.findall(r"const ch = Math\.round\(L\.fs \* \(land \? (\d+\.\d) : (\d+\.\d)\)\);", src)
    assert len(slots) >= 2, "drawSlots 里的 ch 算式没找到"
    assert slots[0] == slots[-1], f"面板 {slots[0]} 与格子 {slots[-1]} 高度不一致"
