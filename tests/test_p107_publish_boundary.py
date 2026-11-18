"""P107：本地待定区不许再长出一份引擎代码。

这件事已经发生过一次：`myonl-publish` 里存着引擎仓某个时点的整份快照
（engine/editor/web/tests/tools/games/locale/brand/.github），比对了五个
关键文件，hash 全不一样 —— 也就是说它是旧版，改的东西根本没同步回来。
拿着它当参考，照着改，改出来的是半个月前的样子。

268 MB，614 个跟踪文件，一半是重复。

规矩写进测试里，比写进 README 里管用：谁往那儿放代码，门禁就红。

在别人机器上跑时这个目录不存在 —— skip，不是 fail。
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
PUBLISH = REPO.parent / "myonl-publish"

# 这几个目录只该存在于引擎仓。
# 同名出现在 publish 里，就意味着有人又抄了一份过去。
CODE_DIRS = ("engine", "editor", "web", "tests", "tools", "games",
             "locale", "brand", ".github", "android", "docs")

# 这几个文件是引擎仓的构建入口，出现即说明整包被搬过去了。
CODE_FILES = ("pack.py", "editor.spec", "requirements.txt",
              "requirements-dev.txt", "pytest.ini", "conftest.py",
              "build.bat", "build_editor.bat", "pyrightconfig.json")


pytestmark = [
    pytest.mark.unit,
    pytest.mark.skipif(
        not PUBLISH.is_dir(),
        reason="没有 myonl-publish 目录（这是仓库之外的东西，别人机器上本来就没有）",
    ),
]


def test_待定区不存在引擎代码目录():
    found = [d for d in CODE_DIRS if (PUBLISH / d).is_dir()]
    assert not found, (
        f"myonl-publish 里出现了引擎代码目录：{found}\n"
        f"代码只留 {REPO.name} 一份。抄过去的那份永远会和这里不一致。"
    )


def test_待定区不存在构建入口文件():
    found = [f for f in CODE_FILES if (PUBLISH / f).is_file()]
    assert not found, (
        f"myonl-publish 里出现了构建入口：{found}\n"
        f"这个目录只放内部文档、研修日志和作品，不放能跑的东西。"
    )


def test_待定区必须有一个说明自己的README():
    readme = PUBLISH / "README.md"
    assert readme.is_file(), "myonl-publish 缺 README，别人打开不知道这里是什么"
    text = readme.read_text(encoding="utf-8", errors="ignore")
    assert "不是" in text and "源码" in text, (
        "README 必须明说这里不是源码仓库 —— 否则迟早有人把它当第二个工程用"
    )


def test_待定区没有remote():
    """没有 remote 是刻意的：里面的东西有版权疑问，不该上网。

    `.git/config` 里只要出现 [remote，就说明有人配了推送地址。
    """
    cfg = PUBLISH / ".git" / "config"
    if not cfg.is_file():
        pytest.skip("不是 git 仓库，跳过")
    text = cfg.read_text(encoding="utf-8", errors="ignore")
    assert "[remote" not in text, (
        "myonl-publish 被配上了 remote。\n"
        "这里面有第三方作品和素材，推上去就是再分发 —— 把 remote 删掉。"
    )


def test_待定区不囤可重建产物():
    """dist / screenshots 这类东西一囤就是几百 MB，且永远没人看。"""
    bloat = ("dist", "screenshots", "saves", "build", ".pytest_cache")
    found = [d for d in bloat if (PUBLISH / d).is_dir()]
    assert not found, (
        f"myonl-publish 又在囤可重建产物：{found}\n"
        f"需要时重新生成，不要进版本库。"
    )
