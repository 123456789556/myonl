"""生成安卓壳需要的两样东西：应用图标（复用 PWA 那套）+ 固定签名。

为什么要固定签名：Android 覆盖安装要求同一个签名。签名一变，玩家就必须先卸载，
app 私有目录里的 localStorage 会被一起删掉 —— 正好撞在"升级不能毁数据"这条线上。
所以签名只生成一次，进仓库（这是公开测试签名，正式上架请换成自己的）。

跑一次就够，重复跑会覆盖（旧包就装不上了）。
"""

import datetime
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.pwa import _icon_png  # noqa: E402  同一套图标，手机桌面和网页主屏长得一样

ANDROID = ROOT / "android" / "app" / "src" / "main" / "res"
DENSITIES = (("mdpi", 48), ("hdpi", 72), ("xhdpi", 96), ("xxhdpi", 144), ("xxxhdpi", 192))
KEYSTORE = ROOT / "android" / "keystore" / "myonl-test.p12"
PASSWORD = "[REDACTED-BY-P104]"
ALIAS = "myonl"


def write_icons() -> None:
    for name, size in DENSITIES:
        out = ANDROID / f"mipmap-{name}" / "ic_launcher.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(_icon_png(size))
        print(f"icon {name} {size}px -> {out.relative_to(ROOT)}")


def write_keystore() -> None:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.serialization import pkcs12
    from cryptography.x509.oid import NameOID

    if KEYSTORE.exists():
        print(f"keystore 已存在，跳过（删掉它才能重生成）：{KEYSTORE.relative_to(ROOT)}")
        return

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.datetime.now(datetime.timezone.utc)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "MYONL"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "MYONL Engine"),
    ])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=365 * 30))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    blob = pkcs12.serialize_key_and_certificates(
        ALIAS.encode("utf-8"), key, cert, None,
        serialization.BestAvailableEncryption(PASSWORD.encode("utf-8"))
    )
    KEYSTORE.parent.mkdir(parents=True, exist_ok=True)
    KEYSTORE.write_bytes(blob)
    print(f"keystore -> {KEYSTORE.relative_to(ROOT)}（{len(blob)} B，别名 {ALIAS}）")


if __name__ == "__main__":
    write_icons()
    write_keystore()
