"""P126：APK 里的内置示例一直没入口。

CI 每次构建都往 assets/ 塞一个 game.html（build_single 生成的单文件示例，约 547 KB），
注释写着「装上就能直接玩一关」。但编辑器首页从来没这个按钮 ——
下载 APK 的人打开只看到一个空书架，那 547 KB 纯粹白占体积。
现在首页探一下 game.html 在不在，在就显示「试玩示例」。
"""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOME = (ROOT / "editor" / "editor_home.js").read_text(encoding="utf-8")
CI = (ROOT / ".github" / "workflows" / "android-apk.yml").read_text(encoding="utf-8")

pytestmark = [pytest.mark.unit]


def test_apk_still_ships_the_demo():
    """示例还得打进 APK，否则这条入口是空的。"""
    assert "build_single('games/newbie_demo'" in CI
    assert "android/app/src/main/assets/game.html" in CI


def test_home_has_demo_entry():
    assert 'id="mHomeDemo"' in HOME
    assert "试玩示例" in HOME
    # 默认隐藏：浏览器里没有 game.html，不该出现一个点了报错的按钮
    assert 'id="mHomeDemo" style="display:none"' in HOME


def test_demo_entry_is_probed_before_showing():
    """先 GET 探文件（不用 HEAD —— 部分 WebView 对 HEAD 不返回），成功才露出来。"""
    assert 'fetch("./game.html", {cache: "no-store"})' in HOME
    assert 'db.dataset.ok === "1"' in HOME
    assert 'location.href = "./game.html"' in HOME


def test_apk_entry_page_is_editor():
    """装上打开的是编辑器（做游戏），不是播放器 —— 这是「手机为主」的定位。"""
    assert "cp dist/web/editor-single.html android/app/src/main/assets/index.html" in CI
