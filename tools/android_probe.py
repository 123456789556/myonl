"""真机验收小工具：一次装好 adb 之后，后面每条验证都用它。

用法（在仓库根目录）：
  py -3 tools\android_probe.py info
  py -3 tools\android_probe.py browsers
  py -3 tools\android_probe.py open "file:///sdcard/Download/myonl-demo.html"
  py -3 tools\android_probe.py open "http://localhost:8765/single/教程示例.html" --pkg com.vivo.browser
  py -3 tools\android_probe.py tap 540 1600
  py -3 tools\android_probe.py rot port|land|auto
  py -3 tools\android_probe.py shot android-1
  py -3 tools\android_probe.py logcat 20

为什么要 TEMP 覆盖：这台机器上 adb daemon 在默认 %TEMP% 下写 adb.log 会被拒
（Permission denied），daemon 直接起不来。所以每个子进程都把 TEMP 指到
D:\\娱乐工作区\\_tools\\tmp。
"""

from __future__ import annotations

import os
import subprocess
import sys
import time

ADB = r"D:\娱乐工作区\_tools\platform-tools\adb.exe"
TMP = r"D:\娱乐工作区\_tools\tmp"
SHOTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "screenshots")

ENV = dict(os.environ, TEMP=TMP, TMP=TMP)


def adb(*args: str, timeout: int = 60) -> str:
    os.makedirs(TMP, exist_ok=True)
    r = subprocess.run([ADB, *args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=ENV, timeout=timeout)
    out = (r.stdout or "").strip()
    err = (r.stderr or "").strip()
    if r.returncode != 0:
        raise SystemExit(f"adb {' '.join(args)} 失败：{err or out}")
    return out


def need_device() -> str:
    # 这台机器上 adb daemon 会随调用结束被回收，所以每次先拉一次服务再枚举
    try:
        subprocess.run([ADB, "start-server"], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=ENV, timeout=30)
    except Exception:
        pass
    for _ in range(3):
        lines = [l for l in adb("devices", "-l").splitlines()[1:] if l.strip()]
        if lines and "offline" not in lines[0]:
            return lines[0].split()[0]
        if lines and "offline" in lines[0]:
            time.sleep(2)
            continue
        time.sleep(2)
    lines = [l for l in adb("devices", "-l").splitlines()[1:] if l.strip()]
    if not lines:
        raise SystemExit("没有设备：手机没连 / 没开 USB 调试")
    raise SystemExit("设备 offline：手机亮屏解锁，点掉「允许 USB 调试」弹窗")


def cmd_info() -> None:
    need_device()
    props = adb("shell", "getprop ro.product.manufacturer; getprop ro.product.model; "
                         "getprop ro.build.version.release; wm size; wm density")
    print(props)
    pkg = adb("shell", "dumpsys webviewupdate | grep -m1 -i 'current webview package'")
    print(pkg.strip())


def cmd_browsers() -> None:
    need_device()
    out = adb("shell", "pm list packages | grep -Ei 'browser|chrome|quark|ucmobile|opera|firefox|edge|vivo'")
    print(out)


def cmd_open(url: str, pkg: str | None) -> None:
    need_device()
    if pkg:
        # 直接指定包：避免系统弹「打开方式」让人点
        adb("shell", f"am start -a android.intent.action.VIEW -d '{url}' -t text/html -n {pkg}")
    else:
        adb("shell", f"am start -a android.intent.action.VIEW -d '{url}' -t text/html")
    print("已发出打开请求：" + url)


def cmd_tap(x: int, y: int) -> None:
    need_device()
    adb("shell", f"input tap {x} {y}")
    print(f"点了 {x},{y}")


def cmd_rot(which: str) -> None:
    need_device()
    if which == "auto":
        adb("shell", "settings put system accelerometer_rotation 1")
    else:
        deg = {"port": 0, "land": 1, "land2": 3}[which]
        adb("shell", "settings put system accelerometer_rotation 0")
        adb("shell", f"settings put system user_rotation {deg}")
    print("旋转已切到 " + which)


def cmd_shot(name: str) -> None:
    need_device()
    remote = "/sdcard/_probe.png"
    adb("shell", f"screencap -p {remote}")
    # adb pull 的目标路径不能带中文（会给 No such file or directory），先落到 ASCII 临时目录再搬
    staging = os.path.join(TMP, "_probe.png")
    adb("pull", remote, staging)
    adb("shell", f"rm -f {remote}")
    os.makedirs(SHOTS, exist_ok=True)
    local = os.path.join(SHOTS, name + ".png")
    with open(staging, "rb") as src, open(local, "wb") as dst:
        dst.write(src.read())
    print("截图：" + local)


def cmd_logcat(tail: int) -> None:
    need_device()
    adb("logcat", "-d", "-t", str(tail))
    print(adb("shell", f"logcat -d -t {tail} | grep -Ei 'chromium|webview|myonl|Uncaught' | tail -40"))


def cmd_reverse(port: int) -> None:
    need_device()
    adb("reverse", f"tcp:{port}", f"tcp:{port}")
    print(f"手机现在可以用 http://localhost:{port}/ 访问电脑上的服务")


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 1
    sub, rest = argv[0], argv[1:]
    pkg = None
    if "--pkg" in rest:
        i = rest.index("--pkg")
        pkg = rest[i + 1]
        rest = rest[:i] + rest[i + 2:]
    {"info": cmd_info,
     "browsers": cmd_browsers,
     "open": lambda: cmd_open(rest[0], pkg),
     "tap": lambda: cmd_tap(int(rest[0]), int(rest[1])),
     "rot": lambda: cmd_rot(rest[0]),
     "shot": lambda: cmd_shot(rest[0]),
     "logcat": lambda: cmd_logcat(int(rest[0]) if rest else 60),
     "reverse": lambda: cmd_reverse(int(rest[0]) if rest else 8765),
     }[sub]()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
