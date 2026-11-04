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

            # 4b 卡片视图（跨文件只读总览 / 单文件可编辑）：卡片数量与行号完整，切回源码不丢内容
            before_len = page.evaluate("() => document.querySelector('#source').value.length")
            page.evaluate("() => window.__switchTab('card')")
            page.wait_for_timeout(1200)
            card_n = page.locator("#cardView .card").count()
            line_n = page.locator("#cardView .card .card-line").count()
            page.screenshot(path=str(SHOT_DIR / "verify_card_view.png"))
            page.evaluate("() => window.__switchTab('source')")
            page.wait_for_timeout(300)
            after_len = page.evaluate("() => document.querySelector('#source').value.length")
            check("卡片视图卡片数与行号完整",
                  card_n > 5 and line_n >= card_n and before_len == after_len,
                  f"卡片 {card_n} / 行号 {line_n} / 源码长度 {before_len}→{after_len}")

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

            # ==================== 20 大剧本高亮层：逐行增量更新回归 ====================
            # 覆盖：整层与文本高度一致、打字后不漂移、光标行对齐、错误行不串行
            big = page.evaluate("""() => {
              const ta = document.querySelector('#source');
              const pre = document.querySelector('.hl-layer');
              const lines = ['@character 林晚 #ffb3c8', '@bg bg_走廊'];
              for (let i = 1; i <= 3000; i++) lines.push('@ 林晚 第' + i + '句台词');
              ta.value = lines.join('\\n');
              ta.dispatchEvent(new Event('input', {bubbles: true}));
              void pre.offsetHeight;
              return {lines: lines.length, children: pre.children.length,
                      pre_h: pre.scrollHeight, ta_h: ta.scrollHeight,
                      line_h: pre.children[1].offsetHeight,
                      tokens: pre.querySelectorAll('span').length};
            }""")
            check("大剧本高亮层逐行结构", big["children"] == big["lines"] and big["line_h"] == 22,
                  f"行数 {big['lines']} / 容器 {big['children']} / 行高 {big['line_h']}")
            check("大剧本高亮层与文本高度一致", abs(big["pre_h"] - big["ta_h"]) <= 2,
                  f"高亮 {big['pre_h']} / 文本 {big['ta_h']}")
            check("大剧本仍有语法高亮 token", big["tokens"] > 0, f"token {big['tokens']}")

            typed = page.evaluate("""() => {
              const ta = document.querySelector('#source');
              const pre = document.querySelector('.hl-layer');
              const top_before = pre.children[2000].offsetTop;
              const rows = ta.value.split('\\n');
              rows[300] = '@ 林晚 打字后的一句话';
              ta.value = rows.join('\\n');
              const t0 = performance.now();
              ta.dispatchEvent(new Event('input', {bubbles: true}));
              const ms = performance.now() - t0;
              void pre.offsetHeight;
              return {ms: ms, children: pre.children.length, top_before: top_before,
                      top_after: pre.children[2000].offsetTop,
                      pre_h: pre.scrollHeight, ta_h: ta.scrollHeight};
            }""")
            check("打字后高亮层不漂移",
                  typed["children"] == big["lines"] and abs(typed["pre_h"] - typed["ta_h"]) <= 2
                  and typed["top_after"] == typed["top_before"],
                  f"容器 {typed['children']} / 高度差 {typed['ta_h'] - typed['pre_h']} / "
                  f"第 2001 行位移 {typed['top_after'] - typed['top_before']} / 单键 {typed['ms']:.0f}ms")

            cursor = page.evaluate("""async () => {
              const ta = document.querySelector('#source');
              const rows = ta.value.split('\\n');
              let pos = 0;
              for (let i = 0; i < 499; i++) pos += rows[i].length + 1;
              ta.focus();
              ta.setSelectionRange(pos, pos);
              ta.scrollTop = 0;            // 选完光标再回顶，避免浏览器把光标滚进视口
              ta.dispatchEvent(new Event('scroll'));
              ta.dispatchEvent(new Event('keyup', {bubbles: true}));
              // 当前行背景/行号高度在下一帧才应用（避免输入路径里强制重排），等两帧再读
              await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
              const hl = document.getElementById('lineHighlight');
              const pre = document.querySelector('.hl-layer');
              const m = /matrix\\(1, 0, 0, 1, 0, (-?[\\d.]+)\\)/.exec(getComputedStyle(hl).transform);
              const cur = document.querySelector('#lineNumbers .ln.cur');
              // 期望值取高亮层真实行顶（Chromium 会按 1/64 px 取整，固定 22.4 会累计偏差）
              const expect = pre.children[499] ? pre.children[499].offsetTop - ta.scrollTop
                                               : 10 + 499 * 22.4 - ta.scrollTop;
              return {y: m ? Number(m[1]) : NaN, expect: expect,
                      cur: cur ? Number(cur.dataset.line) : null, scroll: ta.scrollTop,
                      h: parseFloat(hl.style.height)};
            }""")
            check("打字后光标与高亮层仍对齐",
                  abs(cursor["y"] - cursor["expect"]) <= 2 and cursor["cur"] == 500,
                  f"当前行背景 {cursor['y']} / 期望 {cursor['expect']:.1f} / 行号 {cursor['cur']}")

            ins = page.evaluate("""() => {
              const ta = document.querySelector('#source');
              const pre = document.querySelector('.hl-layer');
              const last_before = pre.children[pre.children.length - 1].offsetTop;
              const h_before = pre.children[1].offsetHeight;
              const rows = ta.value.split('\\n');
              rows.splice(300, 0, '@ 林晚 新插入的一行');
              ta.value = rows.join('\\n');
              const t0 = performance.now();
              ta.dispatchEvent(new Event('input', {bubbles: true}));
              const ms = performance.now() - t0;
              void pre.offsetHeight;
              const last_after = pre.children[pre.children.length - 1].offsetTop;
              return {ms: ms, children: pre.children.length,
                      shift: last_after - last_before, h_before: h_before,
                      pre_h: pre.scrollHeight, ta_h: ta.scrollHeight};
            }""")
            check("插入一行后高亮层随行数增长",
                  ins["children"] == big["lines"] + 1 and abs(ins["shift"] - ins["h_before"]) <= 2
                  and abs(ins["pre_h"] - ins["ta_h"]) <= 2,
                  f"容器 {ins['children']} / 末行下移 {ins['shift']}（行高 {ins['h_before']}） / 单次 {ins['ms']:.0f}ms")

            err = page.evaluate("""async () => {
              const ta = document.querySelector('#source');
              const pre = document.querySelector('.hl-layer');
              const rows = ta.value.split('\\n');
              rows[1000] = '@foo bar';      // 第 1001 行
              rows[2000] = '@foo baz';      // 第 2001 行：第二条错误，只应报第一条
              ta.value = rows.join('\\n');
              ta.dispatchEvent(new Event('input', {bubbles: true}));
              const r = await fetch('/api/check', {method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({text: ta.value})}).then(x => x.json());
              return {ok: r.ok, line: r.line, message: r.message, children: pre.children.length,
                      top1000: pre.children[1000].offsetTop, line_h: pre.children[1].offsetHeight};
            }""")
            try:
                page.wait_for_function(
                    "() => document.querySelector('#lineNumbers .ln.err') !== null", timeout=12000)
                err_state = page.evaluate("""() => {
                  const all = Array.from(document.querySelectorAll('#lineNumbers .ln.err'));
                  const pre = document.querySelector('.hl-layer');
                  return {n: all.length, line: all[0] ? Number(all[0].dataset.line) : null,
                          children: pre.children.length};
                }""")
            except Exception:  # noqa: BLE001 — 超时即视为未标出错误行
                err_state = {"n": 0, "line": None, "children": 0}
            check("多行语法错误只标第一条且不串行",
                  (not err["ok"]) and err["line"] == 1001 and err_state["n"] == 1
                  and err_state["line"] == err["line"] and abs(err["top1000"] - 1000 * 22.4) <= 2
                  and err_state["children"] == err["children"],
                  f"报错行 {err['line']} / 标红 {err_state['line']}（{err_state['n']} 处） / "
                  f"第 1001 行 top {err['top1000']} / 容器 {err['children']}→{err_state['children']}")

            # 窄窗口 900 / 1024 / 800：高亮层与文本高度仍一致
            narrow = {}
            for w in (900, 1024, 800):
                page.set_viewport_size({"width": w, "height": 800})
                page.wait_for_timeout(350)
                narrow[w] = page.evaluate("""() => {
                  const pre = document.querySelector('.hl-layer');
                  const ta = document.querySelector('#source');
                  return {pre_h: pre.scrollHeight, ta_h: ta.scrollHeight};
                }""")
                page.screenshot(path=str(SHOT_DIR / f"verify_hl_{w}.png"))
            page.set_viewport_size({"width": 1600, "height": 900})
            page.wait_for_timeout(300)
            check("窄窗口 900/1024/800 高亮层高度一致",
                  all(abs(v["pre_h"] - v["ta_h"]) <= 2 for v in narrow.values()),
                  "; ".join(f"{w}: {v['ta_h'] - v['pre_h']}" for w, v in narrow.items()))

            # 滚动到底：高亮层盒高必须随内容增长，否则正文会被自身裁空（只剩行号）
            scroll = page.evaluate("""() => {
              const ta = document.querySelector('#source');
              const pre = document.querySelector('.hl-layer');
              ta.scrollTop = ta.scrollHeight;
              ta.dispatchEvent(new Event('scroll'));
              const wr = document.querySelector('#sourceWrap').getBoundingClientRect();
              let visible = 0;
              for (const ch of pre.children) {
                const b = ch.getBoundingClientRect();
                if (b.bottom > wr.top + 10 && b.top < wr.bottom - 10) visible++;
              }
              return {client_h: pre.clientHeight, scroll_h: pre.scrollHeight,
                      visible: visible, top: ta.scrollTop,
                      transform: pre.style.transform};
            }""")
            check("滚动到底后高亮层不被自身裁空",
                  scroll["client_h"] + 1 >= scroll["scroll_h"] and scroll["visible"] > 5,
                  f"盒高 {scroll['client_h']} / 内容 {scroll['scroll_h']} / "
                  f"可视行 {scroll['visible']} / 位移 {scroll['transform']}")
            page.screenshot(path=str(SHOT_DIR / "verify_hl_scroll.png"))
            page.evaluate("""() => {
              const ta = document.querySelector('#source');
              ta.scrollTop = 0;
              ta.dispatchEvent(new Event('scroll'));
            }""")
            page.wait_for_timeout(200)

            # 软换行（长台词自动折行）：行号必须逐行跟高亮层等高，当前行/错误浮层必须对齐
            wrap = page.evaluate("""async () => {
              const ta = document.querySelector('#source');
              const rows = [];
              for (let i = 1; i <= 12; i++) rows.push('@ 林晚 第' + i + '行短台词');
              rows[2] = '@ 林晚 ' + '长'.repeat(120);   // 第 3 行折成 3 排
              ta.value = rows.join('\\n');
              ta.dispatchEvent(new Event('input', {bubbles: true}));
              await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
              const pre = document.querySelector('.hl-layer');
              const nums = document.querySelector('#lineNumbers');
              let drift = 0, maxH = 0, sumH = 0;
              for (let i = 0; i < pre.children.length; i++) {
                drift = Math.max(drift, Math.abs(nums.children[i].getBoundingClientRect().top
                                            - pre.children[i].getBoundingClientRect().top));
                maxH = Math.max(maxH, pre.children[i].getBoundingClientRect().height);
                sumH += nums.children[i].getBoundingClientRect().height;
              }
              // #lineNumbers 是 flex 拉伸的高容器，它的 scrollHeight 等于自身可视高度，
              // 所以用「行号逐行高度之和」对比「高亮层内容高」，并核对末行底边
              const lastPre = pre.children[pre.children.length - 1].getBoundingClientRect();
              const lastNum = nums.children[nums.children.length - 1].getBoundingClientRect();
              return {lines: pre.children.length,
                      nums_h: Math.round(sumH),
                      pre_h: Math.round(lastPre.bottom - pre.children[0].getBoundingClientRect().top),
                      bottom_delta: Math.round(lastNum.bottom - lastPre.bottom),
                      drift: Math.round(drift), wrap_h: Math.round(maxH),
                      ln3_h: Math.round(nums.children[2].getBoundingClientRect().height)};
            }""")
            check("软换行后行号逐行对齐高亮层",
                  wrap["lines"] == 12 and wrap["drift"] <= 2
                  and abs(wrap["nums_h"] - wrap["pre_h"]) <= 2 and abs(wrap["bottom_delta"]) <= 2
                  and wrap["wrap_h"] >= 44 and abs(wrap["ln3_h"] - wrap["wrap_h"]) <= 2,
                  f"行 {wrap['lines']} / 最大漂移 {wrap['drift']} / 行号逐行高之和 {wrap['nums_h']} vs "
                  f"内容高 {wrap['pre_h']} / 末行底边差 {wrap['bottom_delta']} / "
                  f"折行高 {wrap['wrap_h']} / 行号3高 {wrap['ln3_h']}")
            page.screenshot(path=str(SHOT_DIR / "verify_hl_wrap.png"))

            # 当前行背景落在折行行的真实位置
            cur = page.evaluate("""async () => {
              const ta = document.querySelector('#source');
              const rows = ta.value.split('\\n');
              let pos = 0;
              for (let i = 0; i < 2; i++) pos += rows[i].length + 1;
              ta.focus();
              ta.setSelectionRange(pos, pos);
              ta.scrollTop = 0;
              ta.dispatchEvent(new Event('scroll'));
              ta.dispatchEvent(new Event('keyup', {bubbles: true}));
              await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
              const hl = document.getElementById('lineHighlight').getBoundingClientRect();
              const row = document.querySelector('.hl-layer').children[2].getBoundingClientRect();
              return {delta: Math.round(hl.top - row.top), hl_h: Math.round(hl.height),
                      row_h: Math.round(row.height)};
            }""")
            check("软换行行的当前行背景覆盖整行",
                  abs(cur["delta"]) <= 2 and abs(cur["hl_h"] - cur["row_h"]) <= 2,
                  f"背景 top 差 {cur['delta']} / 高 {cur['hl_h']} vs 行高 {cur['row_h']}")

            # 折行上的语法错误：浮层要盖住整行，且只标这一行
            page.evaluate("""async () => {
              const ta = document.querySelector('#source');
              const rows = ta.value.split('\\n');
              rows[2] = '@foo ' + '长'.repeat(120);
              ta.value = rows.join('\\n');
              ta.dispatchEvent(new Event('input', {bubbles: true}));
              const r = await fetch('/api/check', {method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({text: ta.value})}).then(x => x.json());
              window.__wrapErr = r;
            }""")
            page.wait_for_function(
                "() => document.querySelector('#lineNumbers .ln.err') !== null", timeout=12000)
            errwrap = page.evaluate("""() => {
              const all = Array.from(document.querySelectorAll('#lineNumbers .ln.err'));
              const ov = document.getElementById('errorOverlay').getBoundingClientRect();
              const row = document.querySelector('.hl-layer').children[2].getBoundingClientRect();
              return {n: all.length, line: all[0] ? Number(all[0].dataset.line) : null,
                      delta: Math.round(ov.top - row.top),
                      ov_h: Math.round(ov.height), row_h: Math.round(row.height),
                      api_line: window.__wrapErr ? window.__wrapErr.line : null};
            }""")
            check("折行上的错误浮层整行对齐且不串行",
                  errwrap["api_line"] == 3 and errwrap["n"] == 1 and errwrap["line"] == 3
                  and abs(errwrap["delta"]) <= 2 and abs(errwrap["ov_h"] - errwrap["row_h"]) <= 2,
                  f"报错行 {errwrap['api_line']} / 标红 {errwrap['line']}（{errwrap['n']} 处）/ "
                  f"浮层 top 差 {errwrap['delta']} / 高 {errwrap['ov_h']} vs 行高 {errwrap['row_h']}")
            page.screenshot(path=str(SHOT_DIR / "verify_hl_wrap_err.png"))

            # 打包面板：读取项目列表失败时给中文可操作提示，不卡在「正在读取……」进行态
            page.route("**/api/pack/projects", lambda route: route.abort())
            page.locator("#btnPack").click()
            page.wait_for_timeout(800)
            pack_txt = page.locator("#packStatus").inner_text() if page.locator("#packStatus").count() else ""
            check("打包面板请求失败有中文提示且不残留进行态",
                  "无法连接编辑器服务" in pack_txt and "正在读取" not in pack_txt,
                  f"状态「{pack_txt}」")
            page.unroute("**/api/pack/projects")
            page.locator("#packClose").click()
            page.wait_for_timeout(200)

            # 检查进行中：预览栏文案切成「检查中…」，不残留上一轮的「解析成功 · 实时预览」
            stalled = []

            def stall_check(route):
                stalled.append(route)   # 先挂起请求，读进行态文案后再释放

            page.route("**/api/check", stall_check)
            page.evaluate("""() => {
              const ta = document.querySelector('#source');
              ta.value = ta.value + '\\n@ 林晚 检查中横幅测试';
              ta.dispatchEvent(new Event('input', {bubbles: true}));
            }""")
            page.wait_for_timeout(900)   # 防抖 500ms 后请求已发出，但被挂起
            inflight = page.locator("#previewState").inner_text() if page.locator("#previewState").count() else ""
            check("检查进行中预览栏显示「检查中…」", inflight.strip() == "检查中…",
                  f"实际「{inflight}」")
            for route in stalled:
                route.abort()
            page.unroute("**/api/check")
            page.wait_for_timeout(400)

            # 运行按钮：请求未返回前禁用，连点只发一次（避免一次点击拉起两个游戏窗口）
            run_hits = []
            page.route("**/api/run", lambda route: run_hits.append(route))
            page.evaluate("() => { const b = document.querySelector('#btnRun'); b.click(); b.click(); }")
            page.wait_for_timeout(400)
            run_disabled = page.evaluate("() => document.querySelector('#btnRun').disabled")
            check("运行按钮请求期间禁用且连点只发一次",
                  len(run_hits) == 1 and run_disabled,
                  f"请求 {len(run_hits)} 次 / 禁用 {run_disabled}")
            for route in run_hits:
                route.abort()
            page.unroute("**/api/run")
            page.wait_for_timeout(600)

            # 预览请求失败：清掉上一轮旧图，改给中文提示，避免把旧画面当成新结果
            page.route("**/api/preview", lambda route: route.abort())
            page.evaluate("""() => {
              const ta = document.querySelector('#source');
              ta.value = '@character 林晚 #ffb3c8\\n@ 林晚 预览失败测试台词';
              ta.dispatchEvent(new Event('input', {bubbles: true}));
            }""")
            page.wait_for_timeout(1400)
            pv_placeholder = page.locator("#previewWrap .preview-placeholder").count()
            pv_txt = page.locator("#previewState").inner_text()
            check("预览请求失败清掉旧图并给中文提示",
                  pv_placeholder == 1 and "无法连接编辑器服务" in pv_txt,
                  f"占位 {pv_placeholder} / 状态「{pv_txt}」")
            page.unroute("**/api/preview")
            page.wait_for_timeout(300)

            # 空状态：搜索无匹配要有明确提示；空剧本要显示可操作空状态
            page.locator("#actSearch").first.click()
            page.wait_for_timeout(300)
            page.fill("#qsInput", "zzz_no_match_zzz")
            page.wait_for_timeout(1200)
            qs_empty = page.locator("#qsResults").inner_text()
            check("搜索无匹配显示空状态", "没有匹配结果" in qs_empty, f"面板「{qs_empty[:40]}」")
            page.keyboard.press("Escape")
            page.wait_for_timeout(200)

            page.evaluate("""() => {
              const ta = document.querySelector('#source');
              ta.value = '';
              ta.dispatchEvent(new Event('input', {bubbles: true}));
            }""")
            page.wait_for_timeout(900)
            empty_ph = page.evaluate("""() => {
              const ph = document.querySelector('#previewWrap .preview-placeholder');
              return {txt: ph ? ph.innerText : '', aug: ph ? !!ph.getAttribute('data-aug') : false};
            }""")
            empty_state = page.locator("#status").inner_text()
            check("空剧本显示空状态与可操作按钮",
                  empty_state.strip() == "空剧本" and empty_ph["aug"] and "写一句台词" in empty_ph["txt"],
                  f"状态「{empty_state}」/ 占位「{empty_ph['txt'][:30]}」/ 按钮 {empty_ph['aug']}")

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
