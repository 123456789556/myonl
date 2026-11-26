/* P202 手机版面护栏（脚本层）
   干四件事：
   1. 给 html 打 m-shell / m-wide，横屏顶栏从「一排文字」压成「图标 + 更多」
   2. 顶栏作品名可点 → 改名（先建后名的后半截：不用在新建时被迫起名）
   3. 页面切换前清浮层，别留异物压在上一页上
   4. 对外给一个检查口 window.__myonlOverflowAudit()：把出界/折行的控件列出来
   全部只碰手机壳（pointer: coarse），桌面端一行不改。 */
(function () {
  "use strict";
  var DE = document.documentElement;
  var LIB = "myonl:off:lib:v1";
  var DRAFT = "myonl:off:draft:v1";
  var ORPHAN = "myonl:off:draft:v1:orphan";

  function shell() {
    // 真机是 pointer:coarse；窄窗口（平板分屏 / 网页预览）也当手机壳，否则一窄就露桌面顶栏
    try { if (window.matchMedia("(pointer: coarse)").matches) return true; } catch (e) {}
    return window.innerWidth <= 900 || /Android|iPhone|iPad/i.test(navigator.userAgent || "");
  }
  function wide() { return window.innerWidth > window.innerHeight && window.innerHeight <= 560; }

  function iconify(el, on, txt, icon, label) {
    if (!el) return;
    if (on) {
      if (el.getAttribute("data-p202") !== "1") {
        el.setAttribute("data-p202", "1");
        el.setAttribute("data-p202-txt", el.textContent);
      }
      el.textContent = icon;
      el.setAttribute("aria-label", label);
    } else if (el.getAttribute("data-p202") === "1") {
      el.textContent = el.getAttribute("data-p202-txt") || txt;
      el.removeAttribute("aria-label");
    }
  }

  /* ---- P264/P268 横屏分栏：左栏和预览两处都能拖宽、预览可收起、编辑与预览换位 ----
     用户原话：「左边区域收一些可以拖动宽度」「场景和预览界面的宽也可以调整」。
     拖动只改 --m-rail / --m-prev，没有元素写死 width；双击把手复位，方向键 ±8（Shift ±32）。 */
  var RAIL = "myonl:off:railW:v1", STAGE = "myonl:off:stageOff:v1", PREV = "myonl:off:prevW:v1";
  function railPx() {
    var v = 0; try { v = parseInt(localStorage.getItem(RAIL) || "", 10) || 0; } catch (e) {}
    return v > 0 ? v : 232;
  }
  function stageOff() { try { return localStorage.getItem(STAGE) === "1"; } catch (e) { return false; } }
  // 左栏最多 320，整块正文至少留 290（预览列另有下限 170）：宽度不够时先压缩左栏，不允许把正文挤成一条缝
  function railMax() { return Math.max(150, Math.min(320, window.innerWidth - 460)); }
  function prevPx() {
    var v = 0; try { v = parseInt(localStorage.getItem(PREV) || "", 10) || 0; } catch (e) {}
    return v > 0 ? v : Math.round(window.innerWidth * .34);
  }
  // 预览能宽到哪：正文至少 320，且预览框高度不许顶出栏高（高宽比吃 --sf-pad）
  function padPct() {
    var v = 0; try { v = parseFloat(getComputedStyle(DE).getPropertyValue("--sf-pad")) || 0; } catch (e) {}
    return v > 10 && v < 140 ? v : 36;
  }
  function prevMax() {
    var rail = parseInt(DE.style.getPropertyValue("--m-rail"), 10) || railPx();
    var byBody = window.innerWidth - rail - 290;   // 290 = 正文列下限 + 两侧内边距，实测 844 下正文还剩 253px
    var byHigh = Math.round((window.innerHeight - 150) * 100 / padPct());
    return Math.max(170, Math.min(460, byBody, byHigh));
  }
  function applyPane() {
    if (!shell()) {
      chromeSync(false); DE.classList.remove("m-stage-off", "m-graph-on");
      DE.style.removeProperty("--m-rail"); DE.style.removeProperty("--m-prev"); gSig = ""; return;
    }
    DE.style.setProperty("--m-rail", Math.min(Math.max(railPx(), 150), railMax()) + "px");
    DE.style.setProperty("--m-prev", Math.min(Math.max(prevPx(), 170), prevMax()) + "px");
    DE.classList.toggle("m-stage-off", stageOff());
    // 分栏只在横屏且 >=700 宽成立（同 @media (orientation:landscape) and (min-width:700px)）；竖屏不许多出手柄和按钮
    var split = window.innerWidth >= 700 && window.innerWidth > window.innerHeight;
    var g = document.getElementById("mRailGrip"), b = document.getElementById("mStageBtn"), pg = document.getElementById("mPrevGrip");
    if (g) g.style.display = split ? "" : "none";
    if (pg) pg.style.display = split && !stageOff() ? "" : "none";
    if (b) {
      b.style.display = split ? "" : "none";
      b.textContent = stageOff() ? "\u9884\u89C8" : "\u00D7";
      b.setAttribute("aria-label", stageOff() ? "展开画面预览" : "收起画面预览");
    }
    graphSync(); chromeSync(split);
  }
  function toggleStage() {
    try { localStorage.setItem(STAGE, stageOff() ? "0" : "1"); } catch (e) {}
    applyPane();
  }
  // 两条把手同一套行为：拖、双击复位、方向键微调；命中区 22px，里头一颗 4x44 的可见短条
  function bindGrip(g, page, kind) {
    var rail = kind === "rail", prop = rail ? "--m-rail" : "--m-prev", key = rail ? RAIL : PREV;
    g.setAttribute("role", "separator"); g.setAttribute("aria-orientation", "vertical");
    g.setAttribute("tabindex", "0");
    g.setAttribute("aria-label", rail ? "左栏宽度，拖动调整、双击复位" : "预览宽度，拖动调整、双击复位");
    function cur() { return parseInt(DE.style.getPropertyValue(prop), 10) || 0; }
    function lim(w) { return rail ? Math.min(Math.max(w, 150), railMax()) : Math.min(Math.max(w, 170), prevMax()); }
    function set(w) { DE.style.setProperty(prop, lim(w) + "px"); }
    function save() {
      try { localStorage.setItem(key, String(cur())); } catch (err) {}
      if (rail) {
        // 左栏变宽会让预览顶出正文下限：按新的 rail 重新夹一次
        var pw = parseInt(DE.style.getPropertyValue("--m-prev"), 10) || prevPx();
        DE.style.setProperty("--m-prev", Math.min(Math.max(pw, 170), prevMax()) + "px");
        gSig = ""; renderGraph();
      }
    }
    var x0 = 0, base = 0;
    function move(ev) { set(base + (ev.clientX - x0)); }
    function up() {
      page.classList.remove("m-dragging"); g.classList.remove("on");
      g.removeEventListener("pointermove", move); g.removeEventListener("pointerup", up); g.removeEventListener("pointercancel", up);
      save();
    }
    g.addEventListener("pointerdown", function (e) {
      e.preventDefault(); e.stopPropagation();
      try { g.setPointerCapture(e.pointerId); } catch (err) {}
      page.classList.add("m-dragging"); g.classList.add("on");
      x0 = e.clientX; base = cur();
      g.addEventListener("pointermove", move); g.addEventListener("pointerup", up); g.addEventListener("pointercancel", up);
    });
    g.addEventListener("dblclick", function (e) {
      e.preventDefault(); e.stopPropagation();
      try { localStorage.removeItem(key); } catch (err) {}
      applyPane(); if (rail) { gSig = ""; renderGraph(); }
    });
    g.addEventListener("keydown", function (e) {
      var d = e.key === "ArrowLeft" ? -1 : e.key === "ArrowRight" ? 1 : 0;
      if (!d) return;
      e.preventDefault(); set(cur() + d * (e.shiftKey ? 32 : 8)); save();
    });
  }
  function ensurePane() {
    var p = document.getElementById("scenePage");
    if (!p) return;
    if (!document.getElementById("mRailGrip")) {
      var g = document.createElement("div");
      g.id = "mRailGrip"; g.className = "m-rail-grip";
      p.appendChild(g); bindGrip(g, p, "rail");
    }
    if (!document.getElementById("mPrevGrip")) {
      var pg = document.createElement("div");
      pg.id = "mPrevGrip"; pg.className = "m-prev-grip";
      p.appendChild(pg); bindGrip(pg, p, "prev");
    }
    var sw = p.querySelector(".sf-stage-wrap");
    if (sw && !document.getElementById("mStageBtn")) {
      var btn = document.createElement("button");
      btn.type = "button"; btn.id = "mStageBtn"; btn.className = "m-stage-btn";
      btn.addEventListener("click", function (e) { e.preventDefault(); e.stopPropagation(); toggleStage(); });
      sw.appendChild(btn);
    }
    applyPane();
  }

  function apply() {
    if (!shell()) return;
    DE.classList.add("m-shell"); if (window.visualViewport) DE.style.setProperty("--m-vvh", Math.round(window.visualViewport.height) + "px");
    watchScenePage(); applyPane(); ensurePane();
    var w = wide();
    DE.classList.toggle("m-wide", w);
    iconify(document.querySelector('.menubar .menu-item[data-menu="file"]'), w, "菜单", "☰", "菜单");
    iconify(document.getElementById("mTopPreview"), w, "预览", "▶", "预览");
  }

  /* ---- 改名：lib 与草稿一起改，漏一处就等于把内容丢掉 ---- */
  function readLib() {
    try { return JSON.parse(localStorage.getItem(LIB) || "{}"); } catch (e) { return null; }
  }
  function currentName() {
    var lib = readLib();
    return (lib && lib.current) || "";
  }
  // 草稿是单键、按 name 区分作品：改名不同步，下次打开会被判成「别人的草稿」而丢弃
  function renameDrafts(oldName, newName) {
    [DRAFT, ORPHAN].forEach(function (k) {
      try {
        var d = JSON.parse(localStorage.getItem(k) || "null");
        if (d && d.name === oldName) { d.name = newName; localStorage.setItem(k, JSON.stringify(d)); }
      } catch (e) {}
    });
  }
  function renameProject(oldName, newName) {
    // P203：离线内核把作品库缓存在 memLib 里，直接改 localStorage 会被下一次 writeLib
    // 用旧对象整体覆盖回去（名字看着改了，刷新又变回来）。有 __myonlLib 就只走它。
    var api = window.__myonlLib;
    var lib = api ? api.read() : readLib();
    if (!lib || !lib.projects) return "这本机上还没有作品库";
    if (lib.projects.some(function (p) { return p.name === newName; })) return "已经有同名作品了";
    var hit = null;
    lib.projects.forEach(function (p) { if (p.name === oldName) hit = p; });
    if (!hit) return "找不到「" + oldName + "」";
    hit.name = newName;
    hit.mtime = Math.round(Date.now() / 1000);
    if (lib.current === oldName) lib.current = newName;
    if (api) api.write(lib);
    else try { localStorage.setItem(LIB, JSON.stringify(lib)); } catch (e) { return "写不进去，存储可能满了"; }
    renameDrafts(oldName, newName);
    try { if (sessionStorage.getItem("myonl:projName") === oldName) sessionStorage.setItem("myonl:projName", newName); } catch (e) {}
    var t = document.querySelector(".m-title2");
    if (t && t.textContent === oldName) { t.textContent = newName; t.title = newName; }
    var fp = document.getElementById("filePath");
    if (fp && fp.textContent.trim() === oldName) fp.textContent = newName;
    return "";
  }
  // 作品卡的「⋯ → 改名」在 editor_trash.js，它没有自己去改库的权限，只能调这一个
  window.MYONLRenameProject = renameProject;

  function openRename() {
    if (!shell() || document.getElementById("p202Mask")) return;
    var oldName = currentName();
    if (!oldName) return;
    var mask = document.createElement("div");
    mask.id = "p202Mask";
    mask.className = "p202-mask";
    mask.innerHTML =
      '<div class="p202-box" role="dialog" aria-label="改个名字">' +
        '<h4>改个名字</h4>' +
        '<input class="p202-in" id="p202In" maxlength="24" autocomplete="off" spellcheck="false">' +
        '<div class="p202-row">' +
          '<button type="button" class="p202-cancel" id="p202Cancel">取消</button>' +
          '<button type="button" class="p202-ok" id="p202Ok">改名</button>' +
        '</div>' +
      '</div>';
    document.body.appendChild(mask);
    var inp = mask.querySelector("#p202In");
    inp.value = oldName;
    inp.focus();
    inp.select();
    function done() { mask.remove(); }
    mask.addEventListener("click", function (e) { if (e.target === mask) done(); });
    mask.querySelector("#p202Cancel").addEventListener("click", done);
    function submit() {
      var v = String(inp.value || "").trim();
      if (!v || v === oldName) { done(); return; }
      var err = renameProject(oldName, v);
      if (err) { inp.value = v; inp.setAttribute("placeholder", err); inp.value = ""; return; }
      done();
    }
    mask.querySelector("#p202Ok").addEventListener("click", submit);
    inp.addEventListener("keydown", function (e) { if (e.key === "Enter") submit(); });
  }

  /* ---- P265 横屏左栏：剧本流程图（蓝图式节点图，只读）----
     用户原话「可串联可并联可视化更高也就是类似虚幻蓝图」「游戏可是预览图串联起来的节点分布图」。
     节点 = 一幕（上半截是这一幕的背景缩略图），线 = @jump / 选项 / 没写跳转时顺序流到下一幕；
     分支横向并排、汇合画回同一个节点、跳回前面幕的线是虚线，跳到不存在的幕是红虚线小块。
     点节点 = 进那一幕；拖动平移、双指缩放、空白处点两下回全局。数据每次从正文现读，不另存一份。 */
  var VIEW = "myonl:off:sceneView:v1", ORI = "myonl:off:graphOri:v1", MW = 88, MH = 64;
  var NW = 104, NH = 62, GW = 88, GH = 24, GX = 18, GY = 42;   // GY：竖排层间距，42 是给线上的字留的
  var gT = { x: 0, y: 0, z: 1 }, gSig = "", gCount = -1, gD = null, gSvg = null, gAct = -1;
  var gPtr = {}, gDist = 0, gPinch = 0, gDown = null, gMini = { s: 1, ox: 0, oy: 0 }, gTap = null;
  function escG(s) { return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function cut(s, n) { s = String(s); return s.length > n ? s.slice(0, n - 1) + "\u2026" : s; }
  function own(o, k) { return Object.prototype.hasOwnProperty.call(o, k); }
  function graphOn() { try { return localStorage.getItem(VIEW) !== "list"; } catch (e) { return true; } }
  function graphSplit() { return shell() && window.innerWidth >= 700 && window.innerWidth > window.innerHeight; }
  // 蓝图可以竖着走也可以横着走（用户：「蓝图可以竖着可以横着」）：默认竖排 = 层往下、同层往右；横排 = 层往右、同层往下
  function graphHori() { try { return localStorage.getItem(ORI) === "h"; } catch (e) { return false; } }

  function graphData() {
    var E = window.__editor || {}, src = "";
    try { src = String(E.getText ? E.getText() : "").replace(/^\uFEFF/, ""); } catch (e) {}
    var lines = src.split("\n"), ns = [], by = {}, cur = null, i, t, m;
    for (i = 0; i < lines.length; i++) {
      t = lines[i];
      m = t.match(/^@label\s+(\S+)/);
      if (m) { cur = { name: m[1], bg: "", out: [], choice: false, ch: false, end: false }; by[m[1]] = ns.length; ns.push(cur); continue; }
      if (!cur) {   // 第一个 @label 之前的内容，列表里也算一幕（「开场设置」；一条 @label 都没有时叫「剧本」）—— 编号必须和列表对上
        if (!t.trim() || /^\s*#/.test(t)) continue;
        cur = { name: "开场设置", bg: "", out: [], choice: false, ch: false, head: true, end: false }; ns.push(cur);
      }
      m = t.match(/^@bg\s+(\S+)/); if (m && !cur.bg) cur.bg = m[1];
      m = t.match(/^\s*@jump\s+(\S+)/); if (m) cur.out.push({ to: m[1], k: "jump", txt: "\u8DF3" });
      m = t.match(/^\s*>\s*(.+?)\s*->\s*(\S+)\s*$/);
      if (m && cur.ch) cur.out.push({ to: m[2], k: "choice", txt: m[1] });
      else if (t.trim()) cur.ch = false;              // 选项块到第一条非「>」行为止
      if (/^\s*@end\b/.test(t)) cur.end = true;       // 写了 @end：这一幕到此为止
      if (/^@choice\s*:/.test(t)) { cur.ch = true; cur.choice = true; }
    }
    if (ns.length === 1 && ns[0].head) ns[0].name = "\u5267\u672c";
    var edges = [], ghosts = [], gi = {}, last = "";
    function target(name) {
      if (own(by, name)) return by[name];
      if (!own(gi, name)) { gi[name] = ns.length + ghosts.length; ghosts.push({ name: name, ghost: true, out: [] }); }
      return gi[name];
    }
    ns.forEach(function (n, a) {
      if (n.bg) last = n.bg; else n.inh = last;       // 没写 @bg 的幕沿用上一幕的背景（与预览区同一套算法）
      var seen = {};
      n.out.forEach(function (o) {
        var b = target(o.to);
        if (b === a || seen[b]) return;
        seen[b] = 1; edges.push({ from: a, to: b, k: o.k, back: b < a, txt: o.txt || "" });
      });
      // 写了 @end 的幕到此为止，不许再顺序流到下一幕 —— 否则示范案例会画成「坦白 → 岔开」一条线，分叉被压没
      if (!n.end && !edges.some(function (e) { return e.from === a; }) && a < ns.length - 1) edges.push({ from: a, to: a + 1, k: "flow", back: false, txt: "" });
    });
    // 分层：只按「往后走」的线排（跳回前面的虚线不参与），同一层按上游的平均位置排，减少交叉
    var all = ns.concat(ghosts), rank = [], col = [], cnt = [], maxR = 0, cw = 0, r;
    all.forEach(function (n, a) {
      var k = 0;
      edges.forEach(function (e) { if (e.to === a && !e.back) k = Math.max(k, rank[e.from] + 1); });
      rank[a] = k; maxR = Math.max(maxR, k);
    });
    function bary(a) {
      var s = 0, c = 0;
      edges.forEach(function (e) { if (e.to === a && !e.back) { s += col[e.from]; c++; } });
      return c ? s / c : -1;
    }
    for (r = 0; r <= maxR; r++) {
      var ids = [];
      all.forEach(function (n, a) { if (rank[a] === r) ids.push(a); });
      if (r) ids.sort(function (a, b) { return bary(a) - bary(b) || a - b; });
      cnt[r] = ids.length; cw = Math.max(cw, ids.length);
      ids.forEach(function (a, c) { col[a] = c; });
    }
    var H = graphHori(), LA = H ? 56 : GY, pitch = H ? NH : NW, step = H ? NW : NH;   // LA：层间距（横排留大些给线上的字）；pitch：同层步长的边长，step：层方向上的边长
    var w = H ? maxR * (NW + LA) + NW : cw * (NW + GX) - GX, hsh = 0;
    for (i = 0; i < src.length; i++) hsh = (hsh * 31 + src.charCodeAt(i)) | 0;
    all.forEach(function (n, a) {
      var gw = n.ghost ? GW : NW, gh = n.ghost ? GH : NH, major = rank[a] * (step + LA);
      var minor = (cw * (pitch + GX) - GX - (cnt[rank[a]] * (pitch + GX) - GX)) / 2 + col[a] * (pitch + GX);
      n.x = H ? major : minor + (NW - gw) / 2; n.y = H ? minor + (NH - gh) / 2 : major;
    });
    return { all: all, edges: edges, w: w, h: H ? cw * (NH + GX) - GX : maxR * (NH + GY) + NH, hori: H,
             sig: ns.length + "|" + edges.length + "|" + hsh + "|" + (H ? "h" : "v") };
  }

  function applyT() {
    if (!gSvg || !gD) return;
    var box = document.getElementById("mGraph"), W = box.clientWidth, H = box.clientHeight;
    gT.x = Math.min(Math.max(gT.x, 44 - gD.w * gT.z), W - 44);   // 怎么拖都至少留 44px 图在栏里
    gT.y = Math.min(Math.max(gT.y, 44 - gD.h * gT.z), H - 44);
    gSvg.setAttribute("transform", "translate(" + gT.x + "," + gT.y + ") scale(" + gT.z + ")");
    var mv = document.getElementById("mMiniV"), mm = mv && mv.parentNode;
    // 图整个都在栏里时不显示小总览；放大或拖走了才出来，框告诉你现在看的是哪一块
    if (mm) mm.style.display = (gD.w * gT.z > W + 1 || gD.h * gT.z > H + 1) ? "" : "none";
    if (mv) {
      mv.setAttribute("x", gMini.ox - gT.x / gT.z * gMini.s); mv.setAttribute("y", gMini.oy - gT.y / gT.z * gMini.s);
      mv.setAttribute("width", W / gT.z * gMini.s); mv.setAttribute("height", H / gT.z * gMini.s);
    }
  }
  // 在小总览上点 / 拖：点的那个位置挪到栏中央
  function miniNav(e) {
    var m = document.getElementById("mMini"), box = document.getElementById("mGraph");
    if (!m || !box || !gD) return;
    var r = m.getBoundingClientRect(), s = gMini.s;
    gT.x = box.clientWidth / 2 - (e.clientX - r.left - gMini.ox) / s * gT.z;
    gT.y = box.clientHeight / 2 - (e.clientY - r.top - gMini.oy) / s * gT.z; applyT();
  }
  function graphFit() {
    if (!gD) return;
    var box = document.getElementById("mGraph"), W = box.clientWidth - 12, H = box.clientHeight - 12;
    gT.z = Math.max(0.6, Math.min(1, W / gD.w, H / gD.h));       // 不小于 0.6：再小字就看不清了，宁可拖着看
    // 竖排：第一排节点贴顶，跟右边正文的「场景」两个字同一水平线（用户：「场景和 start 平行」）；横排：第一列贴左
    gT.x = gD.hori ? 12 : Math.max(6, (W - gD.w * gT.z) / 2);
    gT.y = gD.hori ? Math.max(6, (H - gD.h * gT.z) / 2) : 12;
    applyT();
  }
  function zoomAt(px, py, f) {
    var z = Math.min(3, Math.max(0.4, gT.z * f)); if (z === gT.z) return;
    gT.x = px - (px - gT.x) * (z / gT.z); gT.y = py - (py - gT.y) * (z / gT.z); gT.z = z; applyT();
  }

  function renderGraph() {
    var box = document.getElementById("mGraph");
    if (!box || !graphSplit() || !graphOn()) return;
    var aEl = document.querySelector("#sceneList .scene-item.active");
    if (aEl) gAct = parseInt(aEl.getAttribute("data-i"), 10);   // 自动落到第一幕时没人点列表，只能从列表自己读
    var d = graphData();
    if (d.sig + "|" + gAct === gSig) return;
    gSig = d.sig + "|" + gAct; gD = d;
    var W = box.clientWidth, H = box.clientHeight; if (!W || !H) return;
    var E = window.__editor || {}, act = gAct, h = [];
    var H = d.hori;   // 「层方向」= 竖排的 y / 横排的 x；「横方向」= 另一个。下面的函数都按这两个轴说话
    function al(n) { return H ? n.x : n.y; }                                   // 层方向起点
    function ac(n) { return H ? n.y : n.x; }                                   // 横方向起点
    function ll(n) { return n.ghost ? (H ? GW : GH) : (H ? NW : NH); }          // 层方向长度
    function lc(n) { return n.ghost ? (H ? GH : GW) : (H ? NH : NW); }          // 横方向长度
    function pt(a, b) { return H ? a + " " + b : b + " " + a; }
    var mk = 'viewBox="0 0 6 6" refX="5" refY="3" markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0L6 3L0 6z"/></marker>';
    h.push('<svg><defs><marker id="mga" ' + mk + '<marker id="mgb" ' + mk +
      '<clipPath id="mgc"><rect x="4" y="4" width="96" height="40" rx="2"/></clipPath></defs><g id="mGraphView">');
    d.edges.forEach(function (e) {
      var a = d.all[e.from], b = d.all[e.to], p, l1, l2, an = "middle";
      // 线上的字：选项写选项原文，@jump 写「跳」，顺序流不写字
      if (e.back) {   // 跳回前面：从源头外侧绕出去，落回目标外侧
        var s1 = al(a) + ll(a) / 2, s2 = ac(a) + lc(a), e1 = al(b) + ll(b) / 2, e2 = ac(b) + lc(b), bu = 36;
        p = "M" + pt(s1, s2) + "C" + pt(s1, s2 + bu) + " " + pt(e1, e2 + bu) + " " + pt(e1, e2);
        l1 = (s1 + e1) / 2; l2 = (s2 + e2) / 2 + bu * 0.86;
      } else {
        var f1 = al(a) + ll(a), f2 = ac(a) + lc(a) / 2, t1 = al(b), t2 = ac(b) + lc(b) / 2, mm = (f1 + t1) / 2;
        p = "M" + pt(f1, f2) + "C" + pt(mm, f2) + " " + pt(mm, t2) + " " + pt(t1, t2);
        // 正对着的两个节点：字写在线的下 / 右侧（写在线上会盖住箭头）；分叉的线写在线的中点
        if (Math.abs(f2 - t2) < 2) { l1 = H ? mm : f2 + 5; l2 = H ? f2 + 14 : mm + 4; if (!H) an = "start"; }
        else { l1 = mm; l2 = (f2 + t2) / 2 + 4; }
      }
      var lx = H ? l1 : l2, ly = H ? l2 : l1;
      h.push('<path class="m-ge ' + e.k + (e.back ? " back" : "") + '" d="' + p + '" marker-end="url(#' + (e.k === "choice" ? "mgb" : "mga") + ')"/>' +
        (e.txt && !e.back ? '<text class="m-gel ' + e.k + '" x="' + lx + '" y="' + ly + '" text-anchor="' + an + '">' + escG(cut(e.txt, 6)) + "</text>" : "") +
        (e.back ? '<text class="m-gel back" x="' + lx + '" y="' + ly + '" text-anchor="middle">' + escG(cut(e.txt || "", 4)) + "</text>" : ""));
    });
    if (!d.all.length) h.push('<text class="m-g-empty" x="10" y="24">还没有场景</text>');
    d.all.forEach(function (n, a) {
      if (n.ghost) {
        h.push('<g class="m-gn ghost" transform="translate(' + n.x + "," + n.y + ')"><rect width="' + GW + '" height="' + GH + '" rx="4"/><text x="' + (GW / 2) + '" y="16" text-anchor="middle">' + escG("\u2192 " + cut(n.name, 6)) + "</text></g>");
        return;
      }
      var url = "", bg = n.bg || n.inh;
      try { if (bg && E.assetURL) url = E.assetURL("images", bg) || ""; } catch (e) {}
      h.push('<g class="m-gn' + (a === act ? " on" : "") + (n.choice ? " fork" : "") + '" data-i="' + a + '" transform="translate(' + n.x + "," + n.y + ')">' +
        '<rect class="m-gn-box" width="' + NW + '" height="' + NH + '" rx="4"/><rect class="m-gn-thumb" x="4" y="4" width="96" height="40"/>' +
        (url ? '<image x="4" y="4" width="96" height="40" preserveAspectRatio="xMidYMid slice" clip-path="url(#mgc)" xlink:href="' + escG(url) + '" href="' + escG(url) + '"/>'
             : '<path class="m-gn-none" d="M4 4L100 44M100 4L4 44"/>') +
        '<text x="52" y="57" text-anchor="middle">' + escG(cut(n.name, 7)) + "</text>" +
        (n.choice ? '<circle class="m-gn-fork" cx="13" cy="13" r="8"/><path class="m-gn-forkp" d="M13 8v4M9 18l4-6M17 18l-4-6"/>' : "") + "</g>");
    });
    h.push("</g></svg>");
    // 小总览（用户：「再来一个小的总览去寻找」）：整张图缩成一块，只画节点块 + 一个取景框；点上头就把视图挪过去
    gMini.s = Math.max(0.04, Math.min((MW - 8) / d.w, (MH - 8) / d.h, 1)); gMini.ox = (MW - d.w * gMini.s) / 2; gMini.oy = (MH - d.h * gMini.s) / 2;
    h.push('<svg id="mMini" viewBox="0 0 ' + MW + " " + MH + '" aria-label="总览">');
    d.edges.forEach(function (e) {   // 先画线：小总览里也要看得出谁连着谁（点线图）
      var a = d.all[e.from], b = d.all[e.to], x1 = gMini.ox + (a.x + NW / 2) * gMini.s, y1 = gMini.oy + (a.y + NH / 2) * gMini.s;
      var x2 = gMini.ox + (b.x + (b.ghost ? GW : NW) / 2) * gMini.s, y2 = gMini.oy + (b.y + (b.ghost ? GH : NH) / 2) * gMini.s;
      h.push('<line class="mm-e' + (e.back ? " back" : "") + '" x1="' + x1.toFixed(1) + '" y1="' + y1.toFixed(1) + '" x2="' + x2.toFixed(1) + '" y2="' + y2.toFixed(1) + '"/>');
    });
    d.all.forEach(function (n, a) {
      h.push('<rect class="mm-n' + (a === act ? " on" : "") + (n.ghost ? " ghost" : "") + '" x="' + (gMini.ox + n.x * gMini.s).toFixed(1) +
        '" y="' + (gMini.oy + n.y * gMini.s).toFixed(1) + '" width="' + ((n.ghost ? GW : NW) * gMini.s).toFixed(1) + '" height="' + ((n.ghost ? GH : NH) * gMini.s).toFixed(1) + '"/>');
    });
    h.push('<rect id="mMiniV"/></svg>');
    box.innerHTML = h.join(""); gSvg = box.querySelector("#mGraphView");
    if (gCount !== d.all.length) graphFit(); else applyT();   // 幕数变了才重新看全局，改台词不抢视角
    gCount = d.all.length;
  }

  // 点节点 = 等同点列表里那一行（走列表自己的点击链路：选中 + 进详情，不另写一份）
  function openScene(i) {
    var h = document.querySelector("#sceneList .scene-rows");
    if (!h || !(i >= 0)) return;
    var d = document.createElement("div");
    d.className = "scene-item"; d.setAttribute("data-i", String(i));
    h.appendChild(d); d.click(); d.remove();
  }

  function bindGraph(box) {
    box.addEventListener("pointerdown", function (e) {
      if (e.button > 0) return;
      var onMini = !!(e.target.closest && e.target.closest("#mMini"));
      gPtr[e.pointerId] = onMini ? [-1e6, -1e6] : [e.clientX, e.clientY];
      try { box.setPointerCapture(e.pointerId); } catch (err) {}
      if (Object.keys(gPtr).length === 1) { gDist = 0; gDown = e.target.closest ? e.target.closest(".m-gn[data-i]") : null; }
      else { gPinch = 0; gDown = null; gDist = 99; }
      e.preventDefault();
    });
    box.addEventListener("pointermove", function (e) {
      var p = gPtr[e.pointerId]; if (!p) return;
      if (p[0] < -1e5) { miniNav(e); return; }   // 这根手指在小总览上
      var dx = e.clientX - p[0], dy = e.clientY - p[1], ks = Object.keys(gPtr), r = box.getBoundingClientRect();
      gPtr[e.pointerId] = [e.clientX, e.clientY];
      if (ks.length >= 2) {
        var a = gPtr[ks[0]], b = gPtr[ks[ks.length - 1]], d2 = Math.max(8, Math.hypot(a[0] - b[0], a[1] - b[1]));
        if (gPinch) zoomAt((a[0] + b[0]) / 2 - r.left, (a[1] + b[1]) / 2 - r.top, d2 / gPinch);
        gPinch = d2;
      } else { gDist += Math.abs(dx) + Math.abs(dy); gT.x += dx; gT.y += dy; applyT(); }
    });
    ["pointerup", "pointercancel"].forEach(function (ev) {
      box.addEventListener(ev, function (e) {
        delete gPtr[e.pointerId]; gPinch = 0;
        if (Object.keys(gPtr).length) return;
        if (gDist < 8) {
          if (gDown) openScene(parseInt(gDown.getAttribute("data-i"), 10));
          else {
            // P275：空白处点两下 = 回全局。顶栏那三颗「− ＋ 全局」撤掉了：
            // 手势本来就有（双指缩放、拖动平移），再摆一排按钮只把顶栏挤满。
            // 判据：300ms 内、30px 内的第二下；节点上的两下算两次进幕，不算回全局。
            var t2 = Date.now(), pv = gTap;
            if (pv && t2 - pv.t < 300 && Math.abs(e.clientX - pv.x) < 30 && Math.abs(e.clientY - pv.y) < 30) {
              graphFit(); gTap = null;
            } else gTap = { t: t2, x: e.clientX, y: e.clientY };
          }
        }
        gDown = null;
      });
    });
    box.addEventListener("wheel", function (e) {   // 电脑上预览手机壳时用：Ctrl+滚轮缩放，滚轮平移
      e.preventDefault();
      var r = box.getBoundingClientRect();
      if (e.ctrlKey) zoomAt(e.clientX - r.left, e.clientY - r.top, e.deltaY < 0 ? 1.1 : 0.9);
      else { gT.x -= e.deltaX; gT.y -= e.deltaY; applyT(); }
    }, { passive: false });
  }

  // 场景页头的「流程 | 列表」「竖排 | 横排」与缩放三颗，只建一次
  function graphBar(p, on) {
    var head = p.querySelector(".cp-head"), add = document.getElementById("sceneAdd");
    if (!head || !add) return;
    var bar = document.getElementById("mGraphBar");
    if (!bar) {
      bar = document.createElement("div"); bar.id = "mGraphBar";
      bar.innerHTML = '<div class="m-gmodes"><button type="button" data-m="graph">流程</button><button type="button" data-m="list">列表</button></div>' +
        '<div class="m-gori"><button type="button" data-o="v" aria-label="换方向"></button></div>';
      bar.addEventListener("click", function (e) {
        var b = e.target.closest ? e.target.closest("button") : null; if (!b) return;
        var m = b.getAttribute("data-m");
        if (m) { try { localStorage.setItem(VIEW, m); } catch (err) {} graphSync(); return; }
        var o = b.getAttribute("data-o");
        if (o) {
          try { localStorage.setItem(ORI, o); } catch (err) {}
          gSig = ""; gCount = -1; renderGraph();
          // P277：这枚现在收在 ⋯ 里，点完不刷标签的话，人只看到菜单关了、图翻了，
          // 不知道当前是竖还是横。刷完再走，标签始终写着"现在是什么方向"。
          graphBar(document.getElementById("scenePage"), graphOn());
          return;   // 换方向 = 重新看全局
        }
      });
      head.insertBefore(bar, add);
    }
    Array.prototype.forEach.call(bar.querySelectorAll("[data-m]"), function (b) { b.classList.toggle("on", (b.getAttribute("data-m") === "graph") === on); });
    // P276：竖排/横排合成一枚「当前方向 ⇄」，点一下就翻。两枚并排占 92px，
    // 又都得读一遍才知道哪个是当前状态；一枚写着自己现在的状态，点一下就是另一个。
    var ob = bar.querySelector("[data-o]");
    if (ob) {
      var hh = graphHori();
      ob.setAttribute("data-o", hh ? "v" : "h");
      ob.textContent = hh ? "横排 ⇄" : "竖排 ⇄";
    }
  }

  function graphSync() {
    var p = document.getElementById("scenePage");
    if (!p || !graphSplit()) { DE.classList.remove("m-graph-on"); gSig = ""; return; }
    var body = p.querySelector(".scene-body"); if (!body) return;
    var on = graphOn();
    DE.classList.toggle("m-graph-on", on);
    graphBar(p, on);
    var box = document.getElementById("mGraph");
    if (!box) {
      box = document.createElement("div"); box.id = "mGraph"; body.appendChild(box); bindGraph(box);
      var list = document.getElementById("sceneList");
      if (window.MutationObserver && list) new MutationObserver(function () { renderGraph(); }).observe(list, { childList: true, subtree: true, characterData: true });
    }
    renderGraph();
  }

  /* ---- P265b 横屏：场景页那一行并进顶栏 ----
     用户原话「把行往上移动一些…场景编辑再退两次回到作品界面」。
     横屏 390 高里顶栏 50 + 场景页头 50 + 逐句/源码 44，正文 145 才开始。做法：场景页头整行取消，
     「流程｜列表 −＋□」「＋新场景」「保存本场景」「⋯」原节点搬进顶栏（竖屏 / 退出场景页时搬回原位），
     回作品只按顶栏「‹ 作品」一次。只挪 DOM 位置，不新建任何入口。 */
  function chromeSync(split) {
    var p = document.getElementById("scenePage"), mb = document.querySelector(".menubar");
    var more = document.querySelector("#scenePage .cp-head .scn-more, .menubar > .scn-more");
    var on = !!(split && p && mb && more && p.classList.contains("open"));
    if (on === DE.classList.contains("m-chrome-on")) return;
    DE.classList.toggle("m-chrome-on", on);
    var els = ["mGraphBar", "sceneAdd", "sceneSave"].map(function (id) { return document.getElementById(id); });
    els[3] = more;
    if (on) {
      var pivot = document.getElementById("mTopPreview") || mb.firstChild;
      els.forEach(function (el) {
        if (!el) return;
        el._mHome = [el.parentNode, el.nextSibling];
        mb.insertBefore(el, pivot);
      });
    } else {
      for (var i = els.length - 1; i >= 0; i--) {   // 倒着放回去：每样东西的「原后一个」这时都已归位
        var el = els[i]; if (!el || !el._mHome) continue;
        var h = el._mHome;
        if (h[0]) { if (h[1] && h[1].parentNode === h[0]) h[0].insertBefore(el, h[1]); else h[0].appendChild(el); }
        el._mHome = null;
      }
    }
  }

  // 场景页自己会「打开 / 进详情」（P217 自动落到第一幕，不经列表点击）：盯它的 class，变了就把把手、收起钮、流程图补齐
  function watchScenePage() {
    var p = document.getElementById("scenePage");
    if (!p || !window.MutationObserver || p.dataset.mWatch === "1") return;
    p.dataset.mWatch = "1";
    new MutationObserver(function () { setTimeout(function () { ensurePane(); graphSync(); }, 0); }).observe(p, { attributes: true, attributeFilter: ["class"] });
  }

  /* ---- 页面切换不许留异物 ---- */
  function cleanOverlays() {
    ["mlRoot", "mTryPlay", "p202Mask"].forEach(function (id) {
      var el = document.getElementById(id);
      if (!el) return;
      el.classList.add("hidden");
      el.style.display = "none";
    });
    Array.prototype.forEach.call(document.querySelectorAll(".m-sheet, .modal-mask, .insert-menu"), function (el) {
      if (el.parentNode) el.parentNode.removeChild(el);
    });
  }
  window.__myonlCleanOverlays = cleanOverlays;

  /* ---- 检查口：出界 / 折行，一个都不许有 ---- */
  window.__myonlOverflowAudit = function () {
    var vw = window.innerWidth, vh = window.innerHeight, bad = [];
    var sel = "button, .menu-item, .m-top-preview, .m-title2, .m-tabbar .m-tab, .m-home-card, .m-card-name";
    function inScroller(el) {
      for (var p = el.parentNode; p && p.nodeType === 1; p = p.parentNode) {
        var cs = getComputedStyle(p);
        if (/(auto|scroll)/.test(cs.overflowY) || /(auto|scroll)/.test(cs.overflowX)) return true;
      }
      return false;
    }
    Array.prototype.forEach.call(document.querySelectorAll(sel), function (el) {
      var r = el.getBoundingClientRect();
      if (!r.width || !r.height) return;
      var cs = getComputedStyle(el);
      if (cs.visibility === "hidden" || cs.display === "none") return;
      // 省略号截断是设计内行为，不是折行
      if (cs.textOverflow === "ellipsis" && cs.whiteSpace === "nowrap") return;
      // 完全在屏幕外（左侧收纳条 / 视口下方待滚动内容）不算遮挡
      if (r.right <= 0 || r.top >= vh || r.bottom <= 0) return;
      if (r.right > vw + 1 || r.bottom > vh + 1 || (r.left < -1 && r.right > 0)) {
        if (inScroller(el)) return;
        bad.push({ el: el.id || el.className, why: "出界", box: [Math.round(r.left), Math.round(r.top), Math.round(r.right), Math.round(r.bottom)] });
      } else if (el.scrollWidth > el.clientWidth + 1 && cs.whiteSpace !== "nowrap") {
        bad.push({ el: el.id || el.className, why: "折行", w: [el.scrollWidth, el.clientWidth] });
      }
    });
    return bad;
  };

  // 返回首页 / 退出编辑器时先清一遍，别把浮层带到上一页
  document.addEventListener("click", function (e) {
    var t = e.target && e.target.closest ? e.target.closest("#mHomeBack, .m-work-back, .mb-back") : null;
    if (t) cleanOverlays();
  }, true);

  // 场景页是后建的：点进某一幕才把拖动手柄与「收起预览」按钮挂上去（P264）
  document.addEventListener("click", function (e) {
    var t = e.target && e.target.closest ? e.target.closest("#sceneList .scene-item") : null;
    if (t) { gAct = parseInt(t.getAttribute("data-i"), 10) || 0; setTimeout(ensurePane, 0); }
  }, true);

  // 作品名可点改名
  document.addEventListener("click", function (e) {
    var t = e.target && e.target.closest ? e.target.closest(".m-title2") : null;
    if (t) openRename();
  }, false);

  window.addEventListener("resize", apply); try { if (window.visualViewport) window.visualViewport.addEventListener("resize", apply); } catch (e) {}
  window.addEventListener("orientationchange", function () { setTimeout(apply, 260); });
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", apply);
  else apply();
  setTimeout(apply, 400);
  setTimeout(apply, 1200);
})();
