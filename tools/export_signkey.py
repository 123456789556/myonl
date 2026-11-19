"""把 p12 里的签名材料导成前端能用的 json（私钥 + 证书 + 公钥）。

前端的 v2 签名走 WebCrypto：私钥要 PKCS#8 DER，证书和公钥要原样 DER。
跑一次就够，产物 editor/signkey.json 随仓库走（公开测试证书，不保密）。
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path

from cryptography.hazmat.primitives.serialization import (
    Encoding, NoEncryption, PrivateFormat, PublicFormat, pkcs12,
)

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "android" / "keystore" / "myonl-test.p12"
OUT = ROOT / "editor" / "signkey.json"


def main() -> None:
    if not SRC.exists():
        raise SystemExit(
            f"找不到证书：{SRC}\n"
            "  自己生成一张（包名不变、但签名不同，老用户升级会冲突）：\n"
            "    keytool -genkeypair -keystore android/keystore/myonl-test.p12 \\\n"
            "      -storetype PKCS12 -alias myonl -keyalg RSA -keysize 2048 \\\n"
            "      -validity 10000 -dname \"O=MYONL Engine, CN=MYONL\""
        )
    password = os.environ.get("MYONL_STORE_PASS", "").strip() or "myonl-apk-2026"
    data = SRC.read_bytes()
    try:
        key, cert, _ = pkcs12.load_key_and_certificates(data, password.encode())
    except ValueError as e:
        raise SystemExit(f"证书打不开（密码不对？）：{e}") from e
    if key is None or cert is None:
        raise SystemExit("这个 p12 里没有私钥或证书")

    pkcs8 = key.private_bytes(Encoding.DER, PrivateFormat.PKCS8, NoEncryption())
    cert_der = cert.public_bytes(Encoding.DER)
    spki = cert.public_key().public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)

    payload = {
        "privateKey": base64.b64encode(pkcs8).decode(),
        "cert": base64.b64encode(cert_der).decode(),
        "publicKey": base64.b64encode(spki).decode(),
        "subject": cert.subject.rfc4514_string(),
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print(f"私钥 PKCS#8 : {len(pkcs8):,} B")
    print(f"证书 DER    : {len(cert_der):,} B")
    print(f"公钥 SPKI   : {len(spki):,} B")
    print(f"写出        : {OUT}")


if __name__ == "__main__":
    main()
