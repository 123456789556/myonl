"""手机 ↔ 电脑的连接入口（P74）。

这个引擎的"协同"其实已经是现成的：编辑器和游戏都是**跑在电脑上的一个 HTTP 服务**，
手机只是浏览器客户端 —— 手机打开同一个地址，就是在编辑电脑上那份工程，
保存、预览、导出全都落在电脑磁盘上。缺的只是「手机怎么找到这个地址」。

所以这里只做三件事：

1. `local_ips()`：本机局域网 IPv4（手机和电脑连同一个 WiFi 时用得上的那个）。
2. `qr_data_url(text)`：把地址画成二维码（segno 纯 Python，PNG → base64 data URI），
   手机上扫码比手输 `192.168.x.x:8790` 靠谱得多。
3. `adb_state()` / `adb_push()`：插上 USB 线时把**成品**（单文件 HTML）推到
   `/sdcard/Download/MYONL/`，手机用任何浏览器点开就能玩。
   没装 adb 或没开「USB 调试」时如实返回原因，不假装成功。
"""
from __future__ import annotations

import base64
import io
import os
import socket
import subprocess

# adb 默认找位置：环境变量 → 仓库同级 _tools/platform-tools → PATH
_ADB_HINTS = (
    os.environ.get("MYONL_ADB", ""),
    r"D:\娱乐工作区\_tools\platform-tools\adb.exe",
)
_PHONE_DIR = "/sdcard/Download/MYONL"


def local_ips() -> list:
    """本机可被手机访问的 IPv4 列表（排除 127.0.0.1）。

    用 UDP connect 试探默认出口地址：不发包，但能拿到「本机会走哪张网卡」，
    比解析 `ipconfig` 文本稳。
    """
    found = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            found.append(s.getsockname()[0])
        finally:
            s.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip not in found:
                found.append(ip)
    except OSError:
        pass
    return [ip for ip in found if ip and not ip.startswith("127.")]


def qr_data_url(text: str) -> str:
    """文本 → `data:image/png;base64,...` 的二维码。没装 segno 就返回空串（前端不显示图）。"""
    if not text:
        return ""
    try:
        import segno
    except ImportError:
        return ""
    try:
        qr = segno.make(text, error="m")
        buf = io.BytesIO()
        # 深色底上的码：深底白码扫不动，所以用「浅底深码」，外面留 2 模块静区
        qr.save(buf, kind="png", scale=6, border=2, dark="#101420", light="#e8ecf6")
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:   # noqa: BLE001 — 二维码画不出来不该拦着编辑器用
        return ""


def link_payload(port: int, project_name: str = "") -> dict:
    """给编辑器前端用的连接信息。"""
    ips = local_ips()
    urls = [f"http://{ip}:{port}/" for ip in ips]
    url = urls[0] if urls else ""
    return {
        "ok": True,
        "port": port,
        "ips": ips,
        "urls": urls,
        "url": url,
        "qr": qr_data_url(url),
        "project": project_name,
        "hint": ("手机和电脑连同一个 WiFi，扫这个码就能在手机上打开编辑器，"
                 "改的是电脑上这份工程。" if url else
                 "没探测到局域网地址：检查电脑是否连着 WiFi / 有线网。"),
    }


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
