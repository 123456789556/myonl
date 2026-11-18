"""P101：播放器的存档导出必须真的落地。

背景：编辑器的导出早就改成走安卓保存桥了，但**播放器里还留着一份旧写法**
（`URL.createObjectURL` + `<a download>`）—— 它和编辑器那份是同一个洞的两个出口：
WebView 对 blob 下载什么都不做，可代码 `return true`，界面照喊「已导出到下载目录」。

玩家受害最重：存档导出是他们换设备时唯一的保命手段。提示成功、手机里啥也没有，
比直接报错更伤人。

这批契约守四件事：
1. 有保存桥就必须走桥（不是"有就用一下、没有就算了"）；
2. 桥坏了要能回落到浏览器下载，不能直接失败；
3. 返回值必须能区分「桥 / 下载 / 没成功」，界面才有话可说；
4. 不能再出现「已导出到下载目录」这种说死地方的话。
"""
import re

import pytest

pytestmark = [pytest.mark.unit]

from pathlib import Path  # noqa: E402

PLAYER = Path(__file__).resolve().parent.parent / "web" / "myonl-player.js"


def _src():
    return PLAYER.read_text(encoding="utf-8")


def test_导出走保存桥():
    """`__MYONLSave` 必须出现在导出函数里，而且要在 createObjectURL 之前。"""
    src = _src()
    assert "__MYONLSave" in src, "播放器没接保存桥——手机上导出会假成功"
    at = src.index("function storeExportFile")
    seg = src[at:at + 1200]
    assert "__MYONLSave" in seg, "保存桥不在 storeExportFile 里"
    bridge_at = seg.index("__MYONLSave")
    url_at = seg.index("createObjectURL") if "createObjectURL" in seg else 10 ** 9
    assert bridge_at < url_at, "桥必须先在前面拦，不能先走 createObjectURL"


def test_返回三种状态():
    """界面要说准话，函数就得区分三条路，不能一个 true 打发。"""
    seg = _src()
    at = seg.index("function storeExportFile")
    body = seg[at:at + 1400]
    for token in ('"bridge"', '"download"', "return false"):
        assert token in body, f"缺 {token} 分支"


def test_桥坏了能回落():
    """桥抛异常时不能直接失败，得退到浏览器下载。"""
    src = _src()
    at = src.index("function storeExportFile")
    body = src[at:at + 1400]
    assert "catch" in body, "没有兜底，桥一坏就彻底导不出"
    after_catch = body[body.index("catch"):]
    assert "createObjectURL" in after_catch, "兜底里得真的走下载"


def test_不再说导出到下载目录():
    """手机上根本没有「下载目录」这回事，这句话本身就是在骗人。"""
    src = _src()
    assert "已导出到下载目录" not in src, "旧文案还在——手机用户会去下载目录里找不存在的东西"


def test_导入用文件选择器():
    """导入不能让人手打一长串码；必须是系统文件选择器。"""
    src = _src()
    at = src.index("function storeImportFile")
    body = src[at:at + 500]
    assert re.search(r'type\s*=\s*"file"', body), "导入没走文件选择器"
