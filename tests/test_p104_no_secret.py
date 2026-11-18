"""P104：签名私钥与密码不许进仓库。

公开仓库里放 p12 + 明文密码，等于把「伪造安装包」的材料整套送出去：
任何人拿到私钥，就能签一个包名和签名都相同的 APK，Android 会认它是同一个人做的，
覆盖安装到已经装了正版的手机上 —— 作品存档、素材，全跟着走。

这条门禁只守一件事：**要密码只能从外面来**。
"""
import re
import subprocess

import pytest

pytestmark = [pytest.mark.unit]

from pathlib import Path  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
GRADLE = ROOT / "android" / "app" / "build.gradle"
GITIGNORE = ROOT / ".gitignore"
CI = ROOT / ".github" / "workflows" / "android-apk.yml"


def test_gradle不许有明文兜底密码():
    """storePassword / keyPassword 只允许从环境变量读。"""
    src = GRADLE.read_text(encoding="utf-8")
    for line in src.splitlines():
        s = line.strip()
        if s.startswith("//"):
            continue
        m = re.match(r"(storePassword|keyPassword)\s+(.+)", s)
        if not m:
            continue
        val = m.group(2).strip()
        # 两种都合法：当场从 env 读，或者引用一个从 env 读来的变量。
        # 不合法的是带引号的字面量 —— 那才是把密码写进仓库。
        ok = "getenv" in val or re.fullmatch(r"[A-Za-z_]\w*", val)
        assert ok, (
            f"{m.group(1)} 写的是字面量 —— 私钥密码不该进公开仓库：{s}")


def test_gitignore挡住签名文件():
    """p12 / jks / keystore 必须在忽略名单里，否则下次一 add 就又进去了。"""
    src = GITIGNORE.read_text(encoding="utf-8")
    for pat in ("*.p12", "*.jks", ".keystore"):
        assert pat in src, f".gitignore 缺规则 {pat}"


def test_私钥不在git索引里():
    """工作区里可以留着私钥用来出包，但绝不能是被追踪的文件。"""
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.splitlines()
    leaked = [p for p in tracked if p.lower().endswith((".p12", ".jks", ".keystore"))]
    assert not leaked, f"这些私钥还在被 git 追踪：{leaked}"


def test_CI有还原私钥的步骤():
    """私钥不进仓库了，CI 就得更早一步把 secret 写成文件，否则它签不了名。"""
    src = CI.read_text(encoding="utf-8")
    assert "MYONL_KEYSTORE_B64" in src, "CI 没有从 secret 还原 p12 的步骤"
    assert "MYONL_STORE_PASS" in src, "CI 没把签名密码传给 gradle"


def test_CI拦得住未签名的包():
    """签名失败时要这里就红，不能把装不上的包发出去。"""
    src = CI.read_text(encoding="utf-8")
    assert "apksigner" in src, "CI 没有校验签名，未签名包会被发出去"
