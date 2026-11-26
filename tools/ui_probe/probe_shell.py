# -*- coding: utf-8 -*-
"""P258：把「手点界面」变成「机器每次点」——手机壳 / 桌面壳的最小必过探针。

为什么入库：v1.2.55~v1.2.57 三轮里的界面硬伤（浮层压卡片 27px、遮罩铺满整屏、
点「导出这个作品」连带弹出整页导出）都是靠人在 Playwright 里手动点出来的，
那些脚本躺在工作区外的 `_tools` 目录里（不在 git、不进 CI）。结果是：pytest 1529 个绿灯
只证明「文本断言没回退」，不证明用户看到的界面是对的。

这份探针只做「看过就再也不会错」的那几件事，逐条断言，任何一条不符 exit 1。

跑法（本地与 CI 同一条命令）：
    python tools/build_editor_single.py
    python -m http.server 8877 --directory dist/web        # 另开一个终端
    python tools/ui_probe/probe_shell.py --base http://127.0.0.1:8877

覆盖：
    手机 390×844  10 条   浮层不压卡片/不出屏/六项齐/四路收起/导出不串整页/删除先关菜单
    手机 844×390   2 条   横屏落点
    桌面 1440×900  4 条   三栏起来/文件菜单条目/导出出 toast/零 JS 异常
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

from playwright.sync_api import sync_playwright

MOBILE_W, MOBILE_H = 390, 844
LAND_W, LAND_H = 844, 390
DESK_W, DESK_H = 1440, 900

PAGE = "/editor-single.html"


class Report:
    def __init__(self) -> None:
        self.rows: list[tuple[str, bool, str]] = []

    def add(self, name: str, ok: bool, detail: str = "") -> bool:
        self.rows.append((name, ok, detail))
        print(("  OK   " if ok else "  BAD  ") + name + ("  | " + detail if detail else ""), flush=True)
        return ok

    def check(self, name: str, fn, shots: Path | None = None, page=None) -> bool:
        try:
            return fn()
        except Exception as exc:  # 单条失败不中断整轮
            print("  BAD  " + name + "  | " + type(exc).__name__ + ": " + str(exc)[:200], flush=True)
            if shots is not None and page is not None:
                try:
                    page.screenshot(path=str(shots / (name + "-FAIL.png")))
                except Exception:
                    pass
            self.rows.append((name, False, type(exc).__name__ + ": " + str(exc)[:200]))
            return False

    @property
    def bad(self) -> int:
        return sum(1 for _n, ok, _d in self.rows if not ok)


def rect(pg, sel: str):
    return pg.eval_on_selector(
        sel, "el=>{const r=el.getBoundingClientRect();return [Math.round(r.left),Math.round(r.top),Math.round(r.width),Math.round(r.height)]}"
    )


def visible(pg, sel: str) -> bool:
    return pg.eval_on_selector(
        sel,
        "el=>{const r=el.getBoundingClientRect();const s=getComputedStyle(el);"
        "return r.width>0&&r.height>0&&s.visibility!=='hidden'&&s.display!=='none'&&s.opacity!=='0'}",
    )


def count(pg, sel: str) -> int:
    return len(pg.query_selector_all(sel))


def pop_open(pg, timeout: int = 1200) -> bool:
    try:
        pg.wait_for_selector(".m-more-pop", state="visible", timeout=timeout)
        return True
    except Exception:
        return False


def pop_gone(pg, timeout: int = 1200) -> bool:
    try:
        pg.wait_for_selector(".m-more-pop", state="detached", timeout=timeout)
        return True
    except Exception:
        return False


def open_pop(pg) -> bool:
    pg.locator(".m-home-card .m-card-more").first.click()
    return pop_open(pg)


def overlap(a, b) -> int:
    """两块矩形在屏幕上的相交面积（0 = 不压）。"""
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ox = min(ax + aw, bx + bw) - max(ax, bx)
    oy = min(ay + ah, by + bh) - max(ay, by)
    return max(0, ox) * max(0, oy)


def probe_mobile(pg, rep: Report, shots: Path, base: str) -> None:
    pg.set_viewport_size({"width": MOBILE_W, "height": MOBILE_H})
    pg.goto(base + PAGE, wait_until="domcontentloaded", timeout=60000)
    pg.wait_for_selector(".m-home-card", state="visible", timeout=20000)
    pg.wait_for_timeout(400)
    pg.screenshot(path=str(shots / "m01-home.png"))

    def c_bars() -> bool:
        nav = count(pg, "[data-nav]")
        heads = count(pg, ".m-home-find")
        # P260：底栏第三格从「垃圾箱」改名「回收箱」—— 名字得跟这页真实行为对上。
        txt = pg.eval_on_selector_all("[data-nav]", "els=>els.map(e=>e.textContent.trim())")
        lab = "回收箱" in txt
        return rep.add("手机 底栏 4 格 / 页头 3 钮 / 第三格叫回收箱", nav == 4 and heads == 3 and lab,
                       "nav=%d heads=%d labels=%s" % (nav, heads, txt))

    def c_no_splash() -> bool:
        vis = pg.evaluate(
            "()=>{const t=[...document.querySelectorAll('body *')].filter(e=>{"
            "const s=getComputedStyle(e),r=e.getBoundingClientRect();"
            "return r.height>0&&s.display!=='none'&&s.visibility!=='hidden'&&s.opacity!=='0'"
            "&&/MY ?加载中|加载中/.test(e.textContent||'')&&e.children.length===0;});"
            "return t.length}"
        )
        return rep.add("手机 冷启动后没有「加载中」徽标盖着", vis == 0, "残留 %d 个" % vis)

    def c_pop_open() -> bool:
        ok = open_pop(pg)
        pg.wait_for_timeout(200)
        pg.screenshot(path=str(shots / "m02-pop.png"))
        return rep.add("「⋯」点开出现浮层", ok)

    def c_rows() -> bool:
        n = count(pg, ".m-more-pop [id^=mMore]")
        ids = pg.eval_on_selector_all(".m-more-pop [id^=mMore]", "els=>els.map(e=>e.id)")
        return rep.add("浮层六项齐", n == 6, "rows=%d ids=%s" % (n, ",".join(ids)))

    def c_no_overlap() -> bool:
        pop = rect(pg, ".m-more-pop")
        card = rect(pg, ".m-home-card")
        a = overlap(pop, card)
        return rep.add("浮层不压被点的卡片", a == 0, "pop=%s card=%s 相交=%d px²" % (pop, card, a))

    def c_inside() -> bool:
        pop = rect(pg, ".m-more-pop")
        l, t, w, h = pop
        ok = l >= 6 and t >= 0 and l + w <= MOBILE_W - 6 and t + h <= MOBILE_H
        return rep.add("浮层不出屏也不贴边（左右各留 ≥6px）", ok, "pop=%s 屏=%dx%d" % (pop, MOBILE_W, MOBILE_H))

    def c_opaque() -> bool:
        # P261 改底色后，这条口径从「等于 #fff / #262626」改成「不透明 + 不糊成一块」：
        # 浮层要么和页面底色差着，要么有 1px 描边；半透明两条都不算。
        bg = pg.eval_on_selector(".m-more-pop", "el=>getComputedStyle(el).backgroundColor")
        info = pg.eval_on_selector(
            ".m-more-pop",
            "el=>{const c=getComputedStyle(el);return {bg:c.backgroundColor,bw:c.borderTopWidth,bs:c.borderTopStyle,"
            "page:getComputedStyle(document.body).backgroundColor};}")
        theme = pg.evaluate("()=>document.documentElement.dataset.theme||'light'")
        opaque = "rgba" not in bg or ", 1)" in bg or bg.startswith("rgb(")
        differs = bg != info["page"]
        has_border = info["bs"] not in ("none", "hidden") and info["bw"] not in ("0px", "")
        return rep.add("浮层是实底（不透明，且与底色不同或有描边）", opaque and (differs or has_border),
                       "theme=%s bg=%s page=%s border=%s" % (theme, bg, info["page"], info["bw"]))

    def c_radius() -> bool:
        # P261：全站改成硬边（A/B/C 三条一起落：纸感 + 终端感 + 结构性去味）。
        # 只认两种圆角：≤6px，或者真圆 50%；其他（12/14/16/999 胶囊）一律算没改到位。
        data = pg.evaluate(
            "()=>{const out=[];const sel=['.m-home-card','.m-card-thumb','.m-home-find',"
            "'.m-home-findbox input','.m-more-pop','.m-more-row2','.m-link'];"
            "for(const s of sel){for(const el of document.querySelectorAll(s)){"
            "if(!(el.offsetWidth||el.offsetHeight))continue;"
            "const c=getComputedStyle(el);"
            "out.push([s, c.borderTopLeftRadius, c.borderBottomRightRadius]);}}return out;}")
        bad = []
        for sel_name, tl, br in data:
            for v in (tl, br):
                if v in ("50%", "0px", ""):
                    continue
                try:
                    px = float(v.replace("px", ""))
                except ValueError:
                    bad.append("%s=%s" % (sel_name, v)); continue
                if px > 6:
                    bad.append("%s=%s" % (sel_name, v))
        return rep.add("圆角统一：≤6px 或真圆 50%（胶囊/大圆角清零）", not bad,
                       "样本 %d 个；越界 %s" % (len(data), bad if bad else "无"))

    def c_outside() -> bool:
        pg.mouse.click(30, MOBILE_H - 120)
        return rep.add("点别处收起", pop_gone(pg))

    def c_toggle() -> bool:
        open_pop(pg)
        pg.wait_for_timeout(150)
        pg.locator(".m-home-card .m-card-more").first.click()
        return rep.add("再点同一颗钮收起（不是只开不管）", pop_gone(pg))

    def c_export_one() -> bool:
        open_pop(pg)
        pg.locator("#mMoreExp").click()
        ok_toast = False
        try:
            pg.wait_for_selector("text=已导出", timeout=6000)
            ok_toast = True
        except Exception:
            pass
        page_exp = pg.evaluate(
            "()=>{const e=document.querySelector('.m-exp-page,#m-exp-page');"
            "if(!e)return 0;const r=e.getBoundingClientRect();return (r.width>8&&r.height>8)?1:0}"
        )
        pg.screenshot(path=str(shots / "m03-export.png"))
        return rep.add(
            "导出单个作品：有 toast、不串整页导出",
            ok_toast and page_exp == 0,
            "toast=%s 整页导出=%d" % (ok_toast, page_exp),
        )

    def c_delete() -> bool:
        pg.wait_for_timeout(400)
        open_pop(pg)
        pg.locator("#mMoreDel").click()
        try:
            pg.wait_for_selector("text=删除「", timeout=6000)
            has_title = True
        except Exception:
            has_title = False
        menu_left = count(pg, ".m-more-pop")
        pg.screenshot(path=str(shots / "m04-del.png"))
        # 取消退出，别真删（后续条目还要用这张卡）
        try:
            pg.locator("text=取消").last.click(timeout=4000)
        except Exception:
            pass
        pg.wait_for_timeout(200)
        return rep.add(
            "删除：确认层带作品名、菜单已先收起",
            has_title and menu_left == 0,
            "标题=%s 菜单残留=%d" % (has_title, menu_left),
        )

    def c_hist() -> bool:
        pg.wait_for_timeout(300)
        open_pop(pg)
        pg.locator("#mMoreHist").click()
        try:
            pg.wait_for_selector(".snap-panel", state="visible", timeout=6000)
        except Exception:
            return rep.add("版本历史：面板出现", False)
        bg = pg.eval_on_selector(".snap-panel", "el=>getComputedStyle(el).backgroundColor")
        opaque = bg.startswith("rgb(") or ", 1)" in bg
        pg.screenshot(path=str(shots / "m05-hist.png"))
        try:
            pg.keyboard.press("Escape")
            pg.mouse.click(20, 60)
        except Exception:
            pass
        pg.wait_for_timeout(300)
        # 这条只验「面板是不透的实底」，关不关得掉不属于这条；
        # 若它没被 ESC 收掉，直接摘掉，别让它挡住后面那条点卡片。
        pg.evaluate("()=>{const p=document.querySelector('.snap-panel');if(p)p.remove();}")
        return rep.add("版本历史：面板是实底（首页内容不透上来）", opaque, "bg=%s" % bg)

    def c_enter_direct() -> bool:
        # P281：作品工作台封面屏已撤。点卡直接落逐句编辑：底栏五格出来、
        # 旧 `.m-work` 层不许残留；再点 ‹ 回首页，底栏随之收起。
        card = rect(pg, ".m-home-card")
        pg.mouse.click(card[0] + 24, card[1] + 24)
        try:
            pg.wait_for_selector(".m-tabbar", state="visible", timeout=8000)
        except Exception:
            return rep.add("点卡直进逐句编辑（无工作台封面屏）", False, "点完底栏 tab 没出来")
        pg.wait_for_timeout(400)
        pg.screenshot(path=str(shots / "m06-editor.png"))
        tabs = pg.eval_on_selector_all(
            ".m-tab", "els=>els.map(e=>e.dataset.tab+':'+e.textContent.trim())")
        want = ["script:剧本", "assets:素材", "look:外观", "preview:预览", "export:导出"]
        workbench = count(pg, ".m-work")
        ok = tabs == want and workbench == 0
        if not ok:
            return rep.add("点卡直进逐句编辑（无工作台封面屏）", False,
                           "tabs=%s work=%d" % (tabs, workbench))
        back = rect(pg, "#mHomeBack")
        if back[2] < 20 or back[3] < 20:
            return rep.add("点卡直进逐句编辑（无工作台封面屏）", False,
                           "返回键太小 rect=%s" % (back,))
        pg.mouse.click(back[0] + back[2] / 2, back[1] + back[3] / 2)
        pg.wait_for_timeout(800)
        gone = pg.evaluate("()=>{const t=document.querySelector('.m-tabbar');"
                           "if(!t)return true;const r=t.getBoundingClientRect();return r.width===0}")
        home = pg.evaluate("()=>{const h=document.querySelector('.m-home');"
                           "if(!h)return 0;const r=h.getBoundingClientRect();return r.width}")
        return rep.add("点卡直进逐句编辑（无工作台封面屏），‹ 可回首页",
                       ok and gone and home > 0,
                       "tabs=%s 工作台残留=%d 底栏撤=%s 首页宽=%s" % (tabs, workbench, gone, home))

    rep.check("底栏与页头", c_bars, shots, pg)
    rep.check("冷启动无遮挡", c_no_splash, shots, pg)
    rep.check("浮层出现", c_pop_open, shots, pg)
    rep.check("浮层六项", c_rows, shots, pg)
    rep.check("浮层不压卡", c_no_overlap, shots, pg)
    rep.check("浮层不出屏", c_inside, shots, pg)
    rep.check("浮层实底", c_opaque, shots, pg)
    rep.check("圆角统一", c_radius, shots, pg)
    rep.check("点别处收起", c_outside, shots, pg)
    rep.check("同钮收起", c_toggle, shots, pg)
    rep.check("导出不串整页", c_export_one, shots, pg)
    rep.check("删除确认", c_delete, shots, pg)
    rep.check("历史面板实底", c_hist, shots, pg)
    rep.check("点卡直进编辑并回首页", c_enter_direct, shots, pg)


def probe_landscape(pg, rep: Report, shots: Path, base: str) -> None:
    pg.set_viewport_size({"width": LAND_W, "height": LAND_H})
    pg.goto(base + PAGE, wait_until="domcontentloaded", timeout=60000)
    pg.wait_for_selector(".m-home-card", state="visible", timeout=20000)
    pg.wait_for_timeout(400)

    def c_open() -> bool:
        return rep.add("横屏 浮层能开", open_pop(pg))

    def c_geo() -> bool:
        pop = rect(pg, ".m-more-pop")
        card = rect(pg, ".m-home-card")
        l, t, w, h = pop
        inside = l >= 6 and t >= 0 and l + w <= LAND_W - 6 and t + h <= LAND_H
        a = overlap(pop, card)
        pg.screenshot(path=str(shots / "m10-land.png"))
        return rep.add("横屏 不压卡、不出屏", inside and a == 0, "pop=%s 相交=%d" % (pop, a))

    rep.check("横屏 开浮层", c_open, shots, pg)
    rep.check("横屏 落点", c_geo, shots, pg)


def probe_desktop(pg, rep: Report, shots: Path, base: str) -> None:
    errors: list[str] = []
    badres: list[str] = []
    pg.on("pageerror", lambda e: errors.append("pageerror: " + str(e)))
    # 单文件离线形态下 /api/* 一律 404（没有后端），这是预期的，不算界面异常；
    # 真正要抓的是脚本本身报错（pageerror）与非 api 资源的加载失败。
    pg.on(
        "response",
        lambda r: badres.append("%d %s" % (r.status, r.url))
        if r.status >= 400 and "/api/" not in r.url
        else None,
    )
    pg.on(
        "console",
        lambda m: errors.append("console: " + m.text)
        if m.type == "error"
        and "Failed to load resource" not in m.text
        and "fetching the script" not in m.text  # Service Worker 注册失败（dist 里没有 sw.js），与界面无关
        else None,
    )

    pg.set_viewport_size({"width": DESK_W, "height": DESK_H})
    pg.goto(base + PAGE, wait_until="domcontentloaded", timeout=60000)
    pg.wait_for_timeout(1500)
    pg.screenshot(path=str(shots / "d01-boot.png"))

    def c_shell() -> bool:
        body = pg.evaluate("()=>document.body.className")
        status = pg.evaluate("()=>{const e=document.querySelector('#sbVersion');return e?e.textContent.trim():''}")
        return rep.add("桌面 编辑器起来、状态栏带版本号", "MYONL v" in status, "body=%r #sbVersion=%r" % (body[:40], status[:40]))

    def c_filemenu() -> bool:
        try:
            pg.locator("div.menu-item", has_text="文件").first.click(timeout=5000)
        except Exception:
            return rep.add("桌面 文件菜单能开", False, "没找到顶栏「文件」")
        try:
            pg.wait_for_selector(".menu-dropdown.open", state="visible", timeout=5000)
        except Exception:
            return rep.add("桌面 文件菜单能开", False, "菜单没展开")
        n = len(pg.query_selector_all(".menu-dropdown.open > *"))
        items = pg.eval_on_selector_all(".menu-dropdown.open > *", "els=>els.map(e=>e.textContent.trim())")
        pg.screenshot(path=str(shots / "d02-filemenu.png"))
        return rep.add("桌面 文件菜单条目 ≥9", n >= 9, "条目=%d %s" % (n, " | ".join(items)[:160]))

    def c_export_toast() -> bool:
        try:
            pg.locator(".menu-dropdown.open > *", has_text="导出一个 HTML").first.click(timeout=5000)
        except Exception:
            return rep.add("桌面 导出入口点了有反馈", False, "没找到导出条目")
        # toast 只活 2.2 秒，必须在它消失前抓，不能先 sleep 再看
        msg = ""
        try:
            pg.wait_for_function(
                "()=>{const e=document.querySelector('.m-tst');return !!e&&(e.textContent||'').trim().length>1}",
                timeout=8000,
            )
            msg = pg.evaluate("()=>{const e=document.querySelector('.m-tst');return e?e.textContent.trim():''}")
        except Exception:
            msg = ""
        pg.screenshot(path=str(shots / "d03-export.png"))
        # 单文件版没有后端，导出必然失败——允许失败，但不许静默（P258 之前这里真的什么都没有）
        return rep.add("桌面 导出入口点了有反馈（失败也行，静默不行）", bool(msg), "提示=%r" % msg[:120])

    def c_find() -> bool:
        # P262：这层以前整套写死深色 + 投影 + 23px 胶囊，两套皮都不跟。现在要求它跟主题：
        # 不透明、有描边、零投影、圆角 ≤6，并且正文字色对底色 ≥4.5:1。
        try:
            pg.keyboard.press("Control+f")
            pg.wait_for_function(
                "()=>{const e=document.querySelector('#mlRoot');return !!e&&!e.classList.contains('hidden')}",
                timeout=4000,
            )
        except Exception:
            return rep.add("桌面 搜索浮层跟主题", False, "Ctrl+F 没打开浮层")
        try:
            pg.fill("#mlFind", "label", timeout=3000)
        except Exception:
            pass
        pg.wait_for_timeout(300)
        got = pg.evaluate(
            "()=>{const r=document.querySelector('#mlRoot');const c=getComputedStyle(r);"
            "const s=document.querySelector('.ml-in');const cs=s?getComputedStyle(s):null;"
            "const pg_=getComputedStyle(document.body);"
            "const L=(h)=>{const m=h.match(/\\d+/g);if(!m)return null;const v=m.slice(0,3).map(Number).map(x=>{x/=255;"
            "return x<=0.03928?x/12.92:Math.pow((x+0.055)/1.055,2.4)});return 0.2126*v[0]+0.7152*v[1]+0.0722*v[2]};"
            "const fg=L(c.color),bg=L(c.backgroundColor);"
            "const ratio=fg&&bg?(Math.max(fg,bg)+0.05)/(Math.min(fg,bg)+0.05):0;"
            "return {bg:c.backgroundColor,page:pg_.backgroundColor,bw:parseFloat(c.borderTopWidth),"
            "sh:c.boxShadow,rad:parseFloat(c.borderTopLeftRadius),txt:c.color,ratio:Number(ratio.toFixed(2)),"
            "inRad:cs?parseFloat(cs.borderTopLeftRadius):-1};}"
        )
        pg.screenshot(path=str(shots / "d04-find.png"))
        ok = (
            got["bg"] not in ("rgba(0, 0, 0, 0)", "transparent")
            and (got["bg"] != got["page"] or got["bw"] >= 1)
            and got["sh"] in ("none", "")
            and 0 <= got["rad"] <= 6
            and 0 <= got["inRad"] <= 6
            and got["ratio"] >= 4.5
        )
        return rep.add(
            "桌面 搜索浮层跟主题（实底·细边·零投影·4px·字底≥4.5）",
            ok,
            "bg=%s page=%s border=%s shadow=%s r=%s 输入框r=%s 字/底=%.2f" % (
                got["bg"], got["page"], got["bw"], got["sh"], got["rad"], got["inRad"], got["ratio"]),
        )

    def c_no_errors() -> bool:
        allbad = errors + badres
        return rep.add("桌面 零 JS 异常、零资源 404", len(allbad) == 0, " | ".join(allbad)[:300])

    rep.check("桌面 三栏", c_shell, shots, pg)
    rep.check("桌面 文件菜单", c_filemenu, shots, pg)
    rep.check("桌面 导出", c_export_toast, shots, pg)
    rep.check("桌面 搜索浮层", c_find, shots, pg)
    rep.check("桌面 无异常", c_no_errors, shots, pg)


def probe_editor(pg, rep: Report, shots: Path, base: str) -> None:
    """P259 手机残留：触控底线与两处量出来的版面硬伤。

    这三类此前没人守，靠人看截图：
      ① 顶栏几颗只有 34 高、场景页头 38 高、变量入口 30 高、删句 ✕ 38 高 —— 全在 44 以下；
      ② 场景页从 top=50+safe 开始，却还被 .center-page 的 padding-top:40 再让一次安全区，
         头顶一条 40px 白带（实测 cp-head.top - page.top = 41）；
      ③ 回收箱「彻底删除」被全局 button:hover 染成浅色主题的 deep-blue 底 + 红字。
    """
    pg.set_viewport_size({"width": MOBILE_W, "height": MOBILE_H})
    pg.goto(base + PAGE, wait_until="domcontentloaded", timeout=60000)
    pg.wait_for_selector(".m-home-card", state="visible", timeout=20000)
    pg.wait_for_timeout(400)
    card = rect(pg, ".m-home-card")
    pg.mouse.click(card[0] + 24, card[1] + 24)
    # P281：点卡直接落逐句编辑，中间不再夹作品工作台一层（封面屏 / 写·玩两钮已撤）
    pg.wait_for_selector(".m-tabbar", state="visible", timeout=8000)
    pg.wait_for_timeout(1200)

    def c_topbar() -> bool:
        # P260：查找那颗收进「下面那颗放大镜浮球」，顶栏剩三颗；作品名顶到原来查找的位置。
        hs = [("mHomeBack", rect(pg, "#mHomeBack")[3]),
              ("mTopPreview", rect(pg, "#mTopPreview")[3]),
              ("menu", rect(pg, ".menubar .menu-item")[3])]
        bad = [n for n, h in hs if h < 44]
        find_vis = pg.is_visible("#mTopFind") if count(pg, "#mTopFind") else False
        back, title = rect(pg, "#mHomeBack"), rect(pg, ".menubar .m-title2")
        gap = title[0] - (back[0] + back[2])
        return rep.add("顶栏三颗高 ≥44 / 查找已收 / 作品名顶上来",
                       (not bad) and (not find_vis) and gap <= 16,
                       "实测 %s find=%s 间距=%d" % (hs, find_vis, gap))

    def c_scene_gap() -> bool:
        page = rect(pg, "#scenePage")
        head = rect(pg, "#scenePage .cp-head")
        gap = head[1] - page[1]
        return rep.add("场景页头顶不留安全带空带（≤8px）", gap <= 8, "page.top=%d head.top=%d 空带=%d" % (page[1], head[1], gap))

    def c_scene_btns() -> bool:
        # P277：条上只留「‹ 作品」与「⋯」；保存搬进 ⋯（弹层里每项也是 44 高）。
        # 这里量条上仍在的两颗，外加确认保存已不在条上（不该再占一格）。
        more = rect(pg, ".menubar .scn-more")[3] if count(pg, ".menubar .scn-more") else None
        hs = [("sceneClose", rect(pg, "#sceneClose")[3]),
              ("sceneClose.w", rect(pg, "#sceneClose")[2])]
        if more is not None:                     # 手机外壳才有「⋯」；桌面形态量不到，不判它
            hs.append(("scnMore", more))
        bad = [n for n, v in hs if v < 44]
        save_on_bar = rect(pg, "#sceneSave")[3] > 0 if more is not None else False
        return rep.add("场景页头：返回/⋯ 高与宽 ≥44（保存已收进 ⋯）", (not bad) and not save_on_bar,
                       "实测 %s saveOnBar=%s" % (hs, save_on_bar))

    def c_var_entry() -> bool:
        h = rect(pg, ".m-var-entry-b")[3] if count(pg, ".m-var-entry-b") else 0
        return rep.add("变量与条件入口「加一条」高 ≥44", h >= 44, "高=%d" % h)

    def c_bin_purge() -> bool:
        pg.locator("#mHomeBack").click(timeout=6000)
        pg.wait_for_timeout(900)
        if count(pg, "#scenePage.open"):
            pg.keyboard.press("Escape")
            pg.wait_for_timeout(400)
        pg.click('[data-nav="bin"]', timeout=6000)
        pg.wait_for_timeout(700)
        pg.locator("#mBinPurge").hover(timeout=4000)
        pg.wait_for_timeout(250)
        bg = pg.eval_on_selector("#mBinPurge", "el=>getComputedStyle(el).backgroundColor")
        # P261：不再写死浅色那两个蓝，直接从主题变量取「主色 / 带字主色」再比 —— 换肤也不会放过它
        accents = pg.evaluate(
            "()=>{const s=getComputedStyle(document.documentElement);"
            "const hex=h=>{const v=h.trim().replace('#','');"
            "return 'rgb(' + parseInt(v.slice(0,2),16) + ', ' + parseInt(v.slice(2,4),16) + ', ' + parseInt(v.slice(4,6),16) + ')';};"
            "return [hex(s.getPropertyValue('--blue')||'#000'), hex(s.getPropertyValue('--blue-ink')||'#000')];}")
        bad = any(bg.startswith(a) for a in accents)
        pg.screenshot(path=str(shots / "m07-bin.png"))
        return rep.add("回收箱「彻底删除」底不是主色块（悬停后也一样）", not bad, "bg=%s 主色=%s" % (bg, accents))

    rep.check("顶栏 44", c_topbar, shots, pg)
    rep.check("场景页空带", c_scene_gap, shots, pg)
    rep.check("场景页头按钮", c_scene_btns, shots, pg)
    rep.check("变量入口高度", c_var_entry, shots, pg)
    rep.check("回收箱危险键底色", c_bin_purge, shots, pg)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8877", help="dist/web 的 http 根地址")
    ap.add_argument("--out", default="dist/_probe", help="截图与报告目录")
    ap.add_argument("--skip-desktop", action="store_true")
    ap.add_argument("--skip-landscape", action="store_true")
    args = ap.parse_args()

    shots = Path(args.out).resolve()
    shots.mkdir(parents=True, exist_ok=True)
    rep = Report()

    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--disable-dev-shm-usage"])
        mobile = browser.new_context(
            viewport={"width": MOBILE_W, "height": MOBILE_H},
            device_scale_factor=2,
            is_mobile=True,
            has_touch=True,
        )
        pg = mobile.new_page()
        probe_mobile(pg, rep, shots, args.base)
        probe_editor(pg, rep, shots, args.base)
        if not args.skip_landscape:
            probe_landscape(pg, rep, shots, args.base)
        mobile.close()

        if not args.skip_desktop:
            desk = browser.new_context(viewport={"width": DESK_W, "height": DESK_H})
            dp = desk.new_page()
            probe_desktop(dp, rep, shots, args.base)
            desk.close()
        browser.close()

    passed = len(rep.rows) - rep.bad
    print("")
    print("探针结果：%d/%d 通过，%d 条不符" % (passed, len(rep.rows), rep.bad))
    print("截图：%s" % shots)
    (shots / "report.json").write_text(
        json.dumps({"passed": passed, "total": len(rep.rows), "bad": rep.bad,
                    "rows": [{"name": n, "ok": ok, "detail": d} for n, ok, d in rep.rows]},
                   ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    return 0 if rep.bad == 0 else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(2)
