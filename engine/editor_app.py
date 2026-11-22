"""MYONL 编辑器桌面窗口入口。

用 pywebview 加载编辑器页面：Windows 下走系统 Edge WebView2（Win10/11 自带），
不依赖用户安装浏览器。HTTP 服务仍由 engine.editor 提供，绑定 127.0.0.1 随机端口，
窗口关闭即停服务。

命令行模式不受影响：py -m engine.editor --project ... --port ... 照常可用。

启动：
    py -m engine.editor_app [--project 工程目录] [--script 剧本.gal]
打包：
    build_editor.bat → dist/editor/editor.exe
"""
from __future__ import annotations

import argparse
import os
import sys
import threading
from http.server import ThreadingHTTPServer

from engine.editor import EditorApp, _default_project, _list_gal_files


_WEBVIEW2_CLIENT = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"


def _webview2_installed() -> bool:
    """检测 Windows 的 Edge WebView2 Runtime（pywebview 的 Windows 后端依赖它）。

    先查注册表（HKLM/HKCU、32/64 位视图），再查安装目录；检测本身失败时返回 True，
    避免因为读注册表被拦截而误判「不可用」。
    """
    if sys.platform != "win32":
        return True
    try:
        import winreg

        paths = (
            (winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{_WEBVIEW2_CLIENT}"),
            (winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{_WEBVIEW2_CLIENT}"),
            (winreg.HKEY_CURRENT_USER, rf"Software\Microsoft\EdgeUpdate\Clients\{_WEBVIEW2_CLIENT}"),
        )
        for hive, path in paths:
            try:
                with winreg.OpenKey(hive, path) as key:
                    version, _ = winreg.QueryValueEx(key, "pv")
                    if version and str(version) != "0.0.0.0":
                        return True
            except OSError:
                continue
    except Exception:  # noqa: BLE001 — 检测失败不阻止启动
        return True
    for env in ("ProgramFiles(x86)", "ProgramFiles"):
        base = os.environ.get(env)
        if base and os.path.isdir(os.path.join(base, "Microsoft", "EdgeWebView", "Application")):
            return True
    return False


def _show_startup_error(message: str) -> None:
    """无控制台的发行版也要让用户看见错误：Windows 下弹窗 + stderr 双保险。"""
    print(message, file=sys.stderr)
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, message, "MYONL 编辑器", 0x10)
    except Exception:  # noqa: BLE001 — 弹窗失败不影响退出
        pass


def _has_gal(root: str) -> bool:
    try:
        return bool(_list_gal_files(root))
    except OSError:
        return False


def _has_gal_direct(root: str) -> bool:
    """工程根目录下直接有 .gal 才算「能双击打开的工程」。

    不能用递归版判断：发行包里 dist/ 根目录递归也能扫到 games/<示例>/script.gal，
    会把「上级目录」误判成工程，双击后编辑器里一个文件都没有。
    """
    try:
        return any(p.is_file() and p.name.lower().endswith(".gal") for p in os.scandir(root))
    except OSError:
        return False


def _resolve_project(project: str | None) -> str:
    """双击 exe 时挑一个可用工程：参数 > 配置记录 > 当前/上级目录的 games/示例故事。"""
    if project not in (None, ""):
        return os.path.realpath(project)
    cwd = os.path.realpath(os.getcwd())
    picked = _default_project(cwd)
    if _has_gal_direct(picked):
        return picked
    # M1：双击 exe 的兜底工程——发行包目录里通常带 games/<示例>，按优先级找一个能打开的
    preferred = ("教程示例", "标准示例", "新游戏", "新游戏模板")
    base = cwd
    for _ in range(3):  # dist/editor → dist → 仓库根
        games_dir = os.path.join(base, "games")
        if os.path.isdir(games_dir):
            for name in preferred:
                demo = os.path.join(games_dir, name)
                if os.path.isdir(demo) and _has_gal_direct(demo):
                    return os.path.realpath(demo)
            # 未知目录名：扫 games/ 下任一直接含 .gal 的工程（排序保证确定性）
            for name in sorted(os.listdir(games_dir)):
                demo = os.path.join(games_dir, name)
                if os.path.isdir(demo) and _has_gal_direct(demo):
                    return os.path.realpath(demo)
        parent = os.path.dirname(base)
        if parent == base:
            break
        base = parent
    return picked


def start_server(project_root: str, script_path: str | None = None):
    """在 127.0.0.1 随机空闲端口起编辑器服务，返回 (server, url)。"""
    app = EditorApp(project_root, script_path)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), app.make_handler())
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{port}"


class _EditorBridge:
    """前端未保存状态 → Python 侧标记。

    关闭确认不能现读 JS：pywebview 的 closing 事件在窗口 UI 线程里同步执行，
    此时同步求值 JS 会卡住窗口消息循环。所以由前端在脏标记变化时主动通知，
    关窗时只看这个布尔量。
    """

    def __init__(self) -> None:
        self.dirty = False

    def set_dirty(self, dirty: bool = False) -> bool:
        self.dirty = bool(dirty)
        return True


CLOSE_CONFIRM_TEXT = "当前有未保存的修改，关闭将丢弃这些修改。确定关闭吗？"


def make_closing_handler(window, bridge: _EditorBridge):
    """构造关闭确认回调：无未保存 → 直接关；否则弹原生确认框。

    回调返回 False 时 pywebview 会取消关闭（见 webview.event.Event.set）。
    对话框不可用或调用失败时不阻塞关闭，避免用户卡在关不掉的窗口上。
    """

    def _on_closing() -> bool:
        if not bridge.dirty:
            return True
        dialog = getattr(window, "create_confirmation_dialog", None)
        if dialog is None:
            return True
        try:
            return bool(dialog("MYONL 编辑器", CLOSE_CONFIRM_TEXT))
        except Exception:  # noqa: BLE001 — 确认框失败不应导致无法关闭
            return True

    return _on_closing


def _route_pythonnet_runtime() -> str:
    """让 pythonnet 从 ASCII 路径初始化（中文目录装 exe 时唯一能开窗的办法）。

    真因：pywebview 的 Windows 后端要 pythonnet，它把 `Python.Runtime.dll` 的路径
    交给 .NET Framework 加载；clr_loader 传的是 UTF-8 字节，.NET 按系统 ANSI 代码页
    解释，路径里有中文就变成一个不存在的路径 —— 于是 `Failed to resolve
    Python.Runtime.Loader.Initialize from ...\\娱乐工作区\\...`，窗口根本出不来。
    实测：同一个 exe，放 `C:\\myonl_test_ascii\\` 能开，放 `D:\\娱乐工作区\\...` 报上面这条。

    做法：把 runtime 目录（3 个 dll，约 630KB）复制到 LOCALAPPDATA 下的纯英文路径，
    用复制品完成 `Python.Runtime.Loader.Initialize`，再把 pythonnet 标记成已加载，
    后面的 `import clr` 直接复用，不再走它自己那条中文路径。

    返回一句人类可读的说明，供启动日志用；路径本来就全是英文时直接跳过。
    """
    if sys.platform != "win32":
        return "skip:not-win32"
    try:
        import pythonnet
    except Exception:  # noqa: BLE001 — 没装 pythonnet 交给上层报错
        return "skip:no-pythonnet"
    dll = os.path.join(os.path.dirname(pythonnet.__file__), "runtime", "Python.Runtime.dll")
    if not os.path.isdir(os.path.dirname(dll)) or _is_ascii(os.path.abspath(dll)):
        return "skip:ascii-path"
    if getattr(pythonnet, "_LOADED", False):
        return "skip:already-loaded"
    try:
        import clr_loader
        import shutil
        import tempfile

        # 候选目录挨个试：杀软会拦「刚下载的 exe 往 AppData 写文件」（WinError 5），
        # 所以不能只认 LOCALAPPDATA 一处；这里挑第一个真能建、能复制的纯英文目录。
        cands = []
        for base in (os.environ.get("LOCALAPPDATA"), tempfile.gettempdir(), "C:\\", "D:\\"):
            if base:
                cands.append(os.path.join(base, "myonl_pyrt"))
        dst_dir, last_err = "", "no-candidate"
        for c in cands:
            if not _is_ascii(c):
                continue
            try:
                os.makedirs(c, exist_ok=True)
                for name in os.listdir(os.path.dirname(dll)):
                    src = os.path.join(os.path.dirname(dll), name)
                    tgt = os.path.join(c, name)
                    # 已经拷过、大小一样就跳过：杀软会拦「重复覆盖已存在文件」
                    if os.path.isfile(src) and not (
                            os.path.exists(tgt) and os.path.getsize(tgt) == os.path.getsize(src)):
                        shutil.copy2(src, tgt)
                if os.path.isfile(os.path.join(c, "Python.Runtime.dll")):
                    dst_dir = c
                    break
            except OSError as e:
                last_err = f"{c}: {e}"
                if os.path.isfile(os.path.join(c, "Python.Runtime.dll")):
                    dst_dir = c
                    break
        if not dst_dir:
            return f"fail:{last_err}"
        dst = os.path.join(dst_dir, "Python.Runtime.dll")
        if not _is_ascii(dst):
            return f"fail:no-ascii-home {dst}"
        rt = clr_loader.get_netfx()
        asm = rt.get_assembly(dst)
        if asm.get_function("Python.Runtime.Loader.Initialize")(b"") != 0:
            return "fail:initialize-nonzero"
        pythonnet.set_runtime(rt)
        pythonnet._LOADER_ASSEMBLY = asm  # noqa: SLF001 — 官方没有其它登记方式
        pythonnet._LOADED = True  # noqa: SLF001
        # 少了这一步，退出解释器时 .NET 会在 finalize 里抛 E0434352（窗口关掉后弹个莫名错误）。
        # 正常路径下 pythonnet.load() 自己会注册，我们绕过了它，所以补上。
        import atexit

        atexit.register(pythonnet.unload)
        return f"ok:routed-to-{dst_dir}"
    except Exception as e:  # noqa: BLE001 — 路由失败就按原样试，别挡住启动
        return f"fail:{e}"


def _is_ascii(path: str) -> bool:
    """路径能否纯 ASCII 表示；不能就说明里面有中文/全角字符。"""
    try:
        path.encode("ascii")
        return True
    except UnicodeEncodeError:
        return False


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    ap = argparse.ArgumentParser(prog="engine.editor_app", description="MYONL 编辑器桌面窗口")
    ap.add_argument("--project", default=None, help="项目根目录（默认：当前目录/配置记录）")
    ap.add_argument("--script", default=None, help="默认打开的剧本路径（必须在项目目录内）")
    args = ap.parse_args(argv)

    _route_note = _route_pythonnet_runtime()
    if _route_note.startswith("fail"):
        print(f"[pyrt] {_route_note}", file=sys.stderr)

    try:
        import webview
    except ImportError:
        _show_startup_error("错误：未安装 pywebview，无法打开内置窗口。\n"
                            "请执行 py -m pip install pywebview 安装，或改用命令行模式：\n"
                            "  py -m engine.editor --project 工程目录 --port 8000")
        return 1
    except Exception as e:  # noqa: BLE001 — pythonnet 初始化失败也算「窗口没开成」
        _show_startup_error(f"编辑器窗口启动失败：{e}\n\n"
                            f"[安装路径] {sys.executable}\n"
                            "[pyrt] " + _route_note + "\n\n"
                            "如果路径里有中文，请把整包挪到纯英文目录再试（如 D:\\MYONL）；\n"
                            "或者把上面 [pyrt] 一行发给我们。")
        return 3

    if not _webview2_installed():
        _show_startup_error(
            "缺少 Microsoft Edge WebView2 Runtime，编辑器窗口无法打开。\n\n"
            "请安装（免费，Win10/11 多数已自带）：\n"
            "https://developer.microsoft.com/microsoft-edge/webview2/\n\n"
            "安装后重新双击 editor.exe 即可。")
        return 3

    project = _resolve_project(args.project)
    try:
        srv, url = start_server(project, args.script)
    except ValueError as e:
        print(f"错误：{e}", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"错误：无法启动本地编辑器服务（{e}）", file=sys.stderr)
        return 1

    try:
        bridge = _EditorBridge()
        win = webview.create_window("MYONL 编辑器", url, width=1280, height=800,
                                    min_size=(900, 600), background_color="#1e1e2e",
                                    js_api=bridge)
        if win is not None:
            win.events.closing += make_closing_handler(win, bridge)
        webview.start()
    except Exception as e:  # noqa: BLE001 — 发行版无控制台，必须弹窗说明
        _show_startup_error(f"编辑器窗口启动失败：{e}\n\n"
                            f"[安装路径] {sys.executable}\n"
                            f"[pyrt] {_route_note}\n\n"
                            "WebView2 装好了还报这句时，多半是安装路径里有中文 —— 整包挪到\n"
                            "纯英文目录（如 D:\\MYONL）再双击；已经挪了还不行，把这几行发回来。")
        return 3
    finally:
        srv.shutdown()
        srv.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
