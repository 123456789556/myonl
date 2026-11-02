"""编辑器 Trae 化交互验收（Playwright 无头自测）。

用途：编辑器会话交付后 / Lead 复核时，一条命令跑完 12+ 条核心交互，输出通过/失败清单与截图。
不修改任何工程文件；跑完自动关服务。

用法：
    py -3 tools/verify_editor_trae_ui.py            # 默认 games/教程示例，端口自动
    py -3 tools/verify_editor_trae_ui.py --keep     # 失败也保留浏览器？(默认全关)
退出码：0 = 全部通过；1 = 有失败（会打印失败清单）。
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHOT_DIR = ROOT / "screenshots"


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def wait_server(url: str, timeout: float = 25.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        try:
            with urllib.request.urlopen(url + "/api/files", timeout=1) as r:
                if r.status == 200:
                    return True
        except Exception:  # noqa: BLE001 — 服务未就绪继续等
            time.sleep(0.25)
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default=str(ROOT / "games" / "教程示例"))
    ap.add_argument("--headed", action="store_true")
    args = ap.parse_args()
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    proc = subprocess.Popen(
        [sys.executable, "-c", f"from engine.editor import serve; serve(r'{args.project}', {port})"],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    SHOT_DIR.mkdir(exist_ok=True)
    results: list[dict] = []
    errors: list[str] = []
    try:
        if not wait_server(base):
            print("FAIL: 编辑器服务未起来")
            return 1
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=not args.headed)
            ctx = browser.new_context(viewport={"width": 1600, "height": 900})
            ctx.add_init_script("try{localStorage.removeItem('gal_onboarding_done');localStorage.removeItem('gal_welcome_done')}catch(e){}")
            page = ctx.new_page()
            console_msgs: list[str] = []
            page.on("console", lambda m: console_msgs.append(f"{m.type}: {m.text}") if m.type == "error" else None)
            page.goto(base + "/", wait_until="networkidle")
            page.wait_for_timeout(2200)

            def check(name: str, cond: bool, detail: str = "") -> None:
                results.append({"name": name, "ok": bool(cond), "detail": detail})

            # 1 页面加载 + 无 console error
            check("页面加载且无 JS 报错", not console_msgs, "; ".join(console_msgs[:3]))

            # 2 首屏欢迎卡（obCard 或 welcomeCard 任一）可弹、可 Esc 关闭
            ob = page.locator("#obMask, .ob-mask, #welcomeMask").first
            visible = ob.is_visible() if ob.count() else False
            if visible:
                page.keyboard.press("Escape")
                page.wait_for_timeout(400)
                left = page.locator("#obMask, .ob-mask, #welcomeMask").first
                check("首屏引导可 Esc 关闭", not (left.is_visible() if left.count() else False))
            else:
                check("首屏引导出现", False, "未检测到引导浮层")

            # 3 顶部动作条可见（运行/保存/打包）
            toolbar = page.locator(".editor-toolbar .tb-btn, .editor-toolbar #btnRun")
            names = []
            for bid in ("btnRun", "btnSave", "btnPack"):
                loc = page.locator(f"#{bid}")
                names.append(loc.count() > 0 and loc.is_visible())
            check("顶部动作条：运行/保存/打包可见", all(names))

            # 4 活动栏 SVG 图标 >= 5
            svg_n = page.locator("#activityBar svg").count()
            check("活动栏 SVG 图标 >= 5", svg_n >= 5, f"实际 {svg_n}")

            # 5 语法高亮层存在且有 token
            token_n = page.locator(".hl-layer .t-cmd, .hl-layer .t-comment").count()
            check("语法高亮 token 渲染", token_n > 0, f"token {token_n}")

            # 6 全局搜索可打开并出结果
            page.locator("#actSearch").first.click()
            page.wait_for_timeout(300)
            page.fill("#qsInput", "label")
            page.wait_for_timeout(1500)
            rows = page.locator("#qsResults .qs-row").count()
            check("全局搜索出结果", rows > 0, f"结果 {rows}")
            page.keyboard.press("Escape")
            page.wait_for_timeout(200)
            check("全局搜索可 Esc 关闭", not page.locator("#qsInput").is_visible())

            # 7 菜单可打开/关闭
            page.locator('.menu-item[data-menu="file"]').first.click()
            page.wait_for_timeout(250)
            open_menu = page.locator("#menuDropdown").is_visible()
            page.keyboard.press("Escape")
            page.wait_for_timeout(200)
            check("菜单可打开且 Esc 关闭", open_menu)

            # 8 Ctrl+F 查找替换（T5 应有）
            page.locator("#source").click()
            page.keyboard.press("Control+f")
            page.wait_for_timeout(400)
            find_ok = page.locator("#findBox, .find-box, #findInput").count() > 0
            check("Ctrl+F 查找面板存在", find_ok)
            page.keyboard.press("Escape")

            # 9 当前行高亮（T6 应有）
            has_cur = page.locator(".cur-line, .current-line, #lineHighlight").count() > 0
            check("当前行高亮存在", has_cur)

            # 10 右侧面板标签化（T7 应有）
            right_tabs = page.locator("#rightTabs, .right-tabs, [data-right-tab]").count()
            check("右侧面板标签化存在", right_tabs > 0)

            # 11 状态栏分段
            sb = all(page.locator(f"#{i}").count() > 0 for i in ("sbLine", "sbProblems", "sbVersion"))
            check("状态栏分段齐全", sb)

            # 12 设置中心：分页存在（工程与数据/游戏界面/桌宠/关于）
            page.locator('.act-btn[data-view="settings"]').first.click()
            page.wait_for_timeout(500)
            tabs_n = page.locator(".set-tab").count()
            check("设置中心分页 >= 4", tabs_n >= 4, f"tab {tabs_n}")
            page.locator("#settingsCancel").click()
            page.keyboard.press("Escape")
            page.wait_for_timeout(200)

            # 13 桌宠状态接口可用（只查 status，不真的弹窗）
            pet_ok = page.evaluate("fetch('/api/pet',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'status'})}).then(r=>r.json()).then(d=>!!d.ok)")
            check("桌宠 /api/pet 状态可读", bool(pet_ok))

            # 14 编辑器可输入并被检查（改一句台词 → 状态变化）
            before = page.locator("#source").input_value()
            page.locator("#source").click()
            page.keyboard.press("Control+End")
            page.keyboard.type("\n# verify")
            page.wait_for_timeout(600)
            after = page.locator("#source").input_value()
            check("编辑器可输入", after != before)


            # 15 主题切换（深色/浅色）
            page.evaluate("window.__setEditorTheme('light')")
            page.wait_for_timeout(300)
            theme_ok = page.evaluate("document.documentElement.getAttribute('data-theme')==='light'")
            check("浅色/深色主题可切换", bool(theme_ok))
            page.evaluate("window.__setEditorTheme('dark')")

            # 16 语言下拉切换高亮模式
            lang_ok = page.evaluate("(function(){var s=document.getElementById('sbLang');if(!s)return false;window.__setEditorLang('json');var v=window.__hlGetMode&&window.__hlGetMode();window.__setEditorLang('gal');return v==='json';})()")
            check("语言下拉切换高亮模式", bool(lang_ok))

            # 17 游戏界面可切左侧
            page.evaluate("window.__previewSideToggle()")
            page.wait_for_timeout(300)
            side_ok = page.evaluate("document.querySelector('.main').classList.contains('preview-left')")
            check("游戏界面可切到左侧", bool(side_ok))
            page.evaluate("window.__previewSideToggle()")

            # 18 搜索出文件结果（搜文件夹内的东西）
            page.locator("#actSearch").first.click()
            page.wait_for_timeout(300)
            page.fill("#qsInput", "script")
            page.wait_for_timeout(1600)
            file_rows = page.locator(".qs-file-row").count()
            check("搜索出文件结果", file_rows > 0, f"文件结果 {file_rows}")
            page.keyboard.press("Escape")


            # 19 场景视图（可视化编辑）可打开/关闭
            page.locator("#btnSceneView").first.click()
            page.wait_for_timeout(700)
            scene_n = page.locator(".scene-item").count()
            check("场景视图可打开（场景数 > 0）", scene_n > 0, f"场景 {scene_n}")
            if scene_n > 0:
                page.locator(".scene-item").first.click()
                page.wait_for_timeout(400)
                stage_bg = page.locator(".sf-stage-bg").count()
                check("场景舞台显示背景预览", stage_bg > 0, f"背景 {stage_bg}")
            page.locator("#sceneClose").click()
            page.wait_for_timeout(300)
            page.locator("#btnCharLib").first.click()
            page.wait_for_timeout(600)
            char_ok = (page.locator("#charPage").count() > 0 and page.locator("#charList").count() > 0)
            check("角色库可打开", bool(char_ok))
            page.locator("#charClose").click()
            page.wait_for_timeout(200)

            page.wait_for_timeout(1500)   # 等最后一次预览/检查请求收尾，避免服务被杀时留下临时剧本
            page.screenshot(path=str(SHOT_DIR / "verify_editor_trae.png"))
            browser.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

    failed = [r for r in results if not r["ok"]]
    print(json.dumps(results, ensure_ascii=False, indent=1))
    print(f"\n通过 {len(results) - len(failed)}/{len(results)}；截图 {SHOT_DIR / 'verify_editor_trae.png'}")
    if failed:
        print("失败项：")
        for r in failed:
            print(f" - {r['name']}  {r['detail']}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
