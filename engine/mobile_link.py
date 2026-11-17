"""插线把成品推到手机（P88 起只留这条路）。

手机上「连编辑器」这件事砍掉了：扫码和局域网地址探测在真机上一次都没跑通过
（adb 反复 offline、投屏抢通道），留着就是一张兑现不了的承诺。现在只有一条路：

`adb_state()` / `adb_push()` —— 插上 USB 线时把**成品**（单文件 HTML）推到
`/sdcard/Download/MYONL/`，手机用任何浏览器点开就能玩。没装 adb 或没开
「USB 调试」时如实返回原因，不假装成功。

工程和素材本身的搬运交给系统文件管理（手机插线当 U 盘用），不在这里做。
"""
from __future__ import annotations

import os
import subprocess

# adb 默认找位置：环境变量 → 仓库同级 _tools/platform-tools → PATH
_ADB_HINTS = (
    os.environ.get("MYONL_ADB", ""),
    r"D:\娱乐工作区\_tools\platform-tools\adb.exe",
)
_PHONE_DIR = "/sdcard/Download/MYONL"


def _adb_path() -> str:
    for hint in _ADB_HINTS:
        if hint and os.path.isfile(hint):
            return hint
    return ""


def adb_state() -> dict:
    """adb 与设备状态。没有 adb / 没有设备都把原因说清楚。"""
    adb = _adb_path()
    if not adb:
        return {"ok": False, "adb": "", "devices": [],
                "message": "没找到 adb（把 platform-tools 放到 _tools/platform-tools，"
                           "或设环境变量 MYONL_ADB）"}
    try:
        env = dict(os.environ)
        # adb 默认往 %TEMP% 写日志，某些机器上会被拒；指到仓库同级 tmp 更稳
        env.setdefault("TEMP", os.path.join(os.path.dirname(adb), "tmp"))
        out = subprocess.run([adb, "devices"], capture_output=True, text=True,
                             timeout=12, env=env).stdout
    except (OSError, subprocess.SubprocessError) as e:
        return {"ok": False, "adb": adb, "devices": [], "message": f"adb 跑不起来：{e}"}
    devices = []
    for line in out.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            devices.append(parts[0])
    return {
        "ok": bool(devices),
        "adb": adb,
        "devices": devices,
        "message": ("已连接 " + "、".join(devices) if devices else
                    "没检测到手机：数据线插好后，手机上打开「开发者选项 → USB 调试」并允许授权"),
    }


def adb_push(local_path: str, remote_dir: str = _PHONE_DIR) -> dict:
    """把一个成品文件推到手机的 Download/MYONL/ 下。"""
    state = adb_state()
    if not state["ok"]:
        return {"ok": False, "message": state["message"]}
    if not os.path.isfile(local_path):
        return {"ok": False, "message": f"文件不存在：{local_path}"}
    adb = state["adb"]
    env = dict(os.environ)
    env.setdefault("TEMP", os.path.join(os.path.dirname(adb), "tmp"))
    name = os.path.basename(local_path)
    remote = remote_dir.rstrip("/") + "/" + name
    try:
        mk = subprocess.run([adb, "shell", "mkdir", "-p", remote_dir],
                            capture_output=True, text=True, timeout=20, env=env)
        if mk.returncode != 0:
            return {"ok": False, "message": f"建目录失败：{(mk.stderr or '').strip()}"}
        push = subprocess.run([adb, "push", local_path, remote],
                              capture_output=True, text=True, timeout=120, env=env)
    except (OSError, subprocess.SubprocessError) as e:
        return {"ok": False, "message": f"adb push 失败：{e}"}
    if push.returncode != 0:
        return {"ok": False, "message": f"推送失败：{(push.stderr or '').strip()}"}
    return {"ok": True, "remote": remote, "bytes": os.path.getsize(local_path),
            "message": f"已推到手机 {remote}（用手机浏览器打开就能玩）"}
