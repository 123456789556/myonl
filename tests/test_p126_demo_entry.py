"""P190：首页的「试玩示例」换成「新手教程」。

原来那个入口探到 game.html 就露出来，点开是一份和当前作品无关的 demo。
新手点进去看到的是别人的游戏，既不知道自己能做同样的事，也不知道要去哪改。
现在改成建一份真的短作品（能打开、能改、能导出），教程本身就是可编辑的剧本。
"""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOME = (ROOT / "editor" / "mobile" / "editor_home.js").read_text(encoding="utf-8")
TRASH = (ROOT / "editor" / "mobile" / "editor_trash.js").read_text(encoding="utf-8")
OFF = (ROOT / "editor" / "gal_offline.js").read_text(encoding="utf-8")
CI = (ROOT / ".github" / "workflows" / "android-apk.yml").read_text(encoding="utf-8")

pytestmark = [pytest.mark.unit]


def _code(src: str) -> str:
    """去掉整行注释 —— 注释里写着"原来这里是「试玩示例」"，别让校验撞上自己。"""
    return "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("//"))


def test_demo_entry_is_gone():
    """「试玩示例」整条删掉：按钮、内嵌层、退出试玩的 postMessage 都不该留在首页。"""
    code = _code(HOME)
    assert 'id="mHomeDemo"' not in HOME
    assert "试玩示例" not in code
    assert "function openDemo" not in code
    assert "myonl-exit-demo" not in code


def test_home_has_tutorial_entry():
    # P205：教程不再单独出；P206：用户又说「教程不要单独开一列」→ 素材页只剩三 tab，
    # 教程降级成素材列表下面的一行折叠速查。首页什么都不挂。
    assert 'id="mHomeTut"' not in HOME
    assert 'id="mHomeTutLink"' not in HOME
    assert '["tut", "教程"]' not in TRASH
    assert 'id="mLibTut"' in TRASH


def test_tutorial_creates_a_real_project():
    """不是播 demo，是打开一份真作品；库里没有才 POST /api/new 兜底建。

    P217 改口径：教程不再自带第二份正文（原 TUT_TEXT），示范案例的正文只有
    gal_offline.js 的 starterText() 一处。两份正文迟早说法不一致。
    """
    assert 'fetch("/api/new"' in HOME
    assert "TUT_TEXT" not in HOME, "教程不该再维护第二份示例正文"
    # 建完直接进编辑器
    assert 'openProject(TUT_NAME)' in HOME


def test_教程与示范案例是同一个作品():
    """P217：默认库只给一份「示范案例」，教程入口指向它，不许凭空多出第二个作品。"""
    assert 'var TUT_NAME = "示范案例"' in HOME
    assert 'current: "示范案例"' in OFF
    assert 'name: "示范案例"' in OFF
    assert "我的第一个游戏" not in _code(OFF), "默认作品名已改，旧名不许留在代码里"
    assert '新手教程"' not in _code(HOME)


def test_tutorial_is_not_recreated():
    """已经建过就别再建 —— 用户可能自己改过它，覆盖等于删他的东西。"""
    assert "p.name === TUT_NAME" in HOME


def test_tutorial_text_is_valid_script():
    """示范案例正文必须自己就是合法剧本：@label / @choice: 后面紧跟 > 选项 -> 标签。

    P217：正文真源搬到 gal_offline.js 的 starterText()，这里跟着改指向。
    """
    assert "@label start" in OFF
    assert "@choice:" in OFF
    assert "> 跟她说实话 -> 坦白" in OFF
    # 角色台词用 @[名] 写法，不依赖角色库里先建人；
    # 旁白也写 @[旁白]：编辑器的逐句卡会把「@ 无空格中文整句」当成角色名（见 P190 备注）
    assert "@[小满]" in OFF
    assert "@[旁白]" in OFF


def test_new_api_accepts_seed_text():
    """离线内核的 /api/new 要能收 text，否则教程只能建成空模板。"""
    assert 'typeof b.text === "string"' in OFF
    assert "starterText()" in OFF


def test_apk_entry_page_is_editor():
    """装上打开的是编辑器（做游戏），不是播放器 —— 这是「手机为主」的定位。"""
    assert "cp dist/web/editor-single.html android/app/src/main/assets/index.html" in CI
