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

  /* ---- P264 横屏分栏：左栏可拖宽、预览可收起、编辑与预览换位 ----
     用户原话「横屏编辑和预览区换一下位置，预览区可关闭，左边区域收一些可以拖动宽度，自适应做好」。
     拖动只改 --m-rail，没有任何元素写死 width；收起只给 html 挂 m-stage-off，版式全交给 CSS。 */
  var RAIL = "myonl:off:railW:v1", STAGE = "myonl:off:stageOff:v1";
  function railPx() {
    var v = 0; try { v = parseInt(localStorage.getItem(RAIL) || "", 10) || 0; } catch (e) {}
    return v > 0 ? v : 232;
  }
  function stageOff() { try { return localStorage.getItem(STAGE) === "1"; } catch (e) { return false; } }
  // 左栏最多 320，整块编辑区至少留 380：宽度不够时先压缩左栏，不允许把编辑区挤成一条缝
  function railMax() { return Math.max(150, Math.min(320, window.innerWidth - 380)); }
  function applyPane() {
    if (!shell()) { chromeSync(false); DE.classList.remove("m-stage-off", "m-graph-on"); DE.style.removeProperty("--m-rail"); gSig = ""; return; }
    DE.style.setProperty("--m-rail", Math.min(Math.max(railPx(), 150), railMax()) + "px");
    DE.classList.toggle("m-stage-off", stageOff());
    // 分栏只在横屏且 ≥700 宽成立（同 @media (orientation:landscape) and (min-width:700px)）；竖屏不许多出手柄和按钮
    var split = window.innerWidth >= 700 && window.innerWidth > window.innerHeight;
    var g = document.getElementById("mRailGrip"), b = document.getElementById("mStageBtn");
    if (g) g.style.display = split ? "" : "none";
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
  function ensurePane() {
    var p = document.getElementById("scenePage");
    if (!p) return;
    if (!document.getElementById("mRailGrip")) {
      var g = document.createElement("div");
      g.id = "mRailGrip"; g.className = "m-rail-grip"; g.setAttribute("role", "separator");
      p.appendChild(g);
      g.addEventListener("pointerdown", function (e) {
        e.preventDefault(); e.stopPropagation();
        try { g.setPointerCapture(e.pointerId); } catch (err) {}
        p.classList.add("m-dragging");
        function move(ev) {
          var w = Math.min(Math.max(Math.round(ev.clientX - p.getBoundingClientRect().left), 150), railMax());
          DE.style.setProperty("--m-rail", w + "px");
        }
        function up() {
          p.classList.remove("m-dragging");
          g.removeEventListener("pointermove", move); g.removeEventListener("pointerup", up);
          try { localStorage.setItem(RAIL, String(parseInt(DE.style.getPropertyValue("--m-rail"), 10) || 232)); } catch (err) {}
          gSig = ""; renderGraph();   // 栏宽变了，流程图按新宽度重新看全局
        }
        g.addEventListener("pointermove", move); g.addEventListener("pointerup", up);
      });
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
     点节点 = 进那一幕；拖动平移、双指缩放、「□」看全局。数据每次从正文现读，不另存一份。 */
  var VIEW = "myonl:off:sceneView:v1", NW = 104, NH = 62, GW = 88, GH = 24, GX = 18, GY = 34;
  var gT = { x: 0, y: 0, z: 1 }, gSig = "", gCount = -1, gD = null, gSvg = null, gAct = -1;
  var gPtr = {}, gDist = 0, gPinch = 0, gDown = null;
  function escG(s) { return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function cut(s, n) { s = String(s); return s.length > n ? s.slice(0, n - 1) + "\u2026" : s; }
  function own(o, k) { return Object.prototype.hasOwnProperty.call(o, k); }
  function graphOn() { try { return localStorage.getItem(VIEW) !== "list"; } catch (e) { return true; } }
  function graphSplit() { return shell() && window.innerWidth >= 700 && window.innerWidth > window.innerHeight; }

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
    var w = cw * (NW + GX) - GX, hsh = 0;
    for (i = 0; i < src.length; i++) hsh = (hsh * 31 + src.charCodeAt(i)) | 0;
    all.forEach(function (n, a) { n.x = (w - (cnt[rank[a]] * (NW + GX) - GX)) / 2 + col[a] * (NW + GX); n.y = rank[a] * (NH + GY); });
    return { all: all, edges: edges, w: w, h: (maxR + 1) * NH + maxR * GY, sig: ns.length + "|" + edges.length + "|" + hsh };
  }

  function applyT() {
    if (!gSvg || !gD) return;
    var box = document.getElementById("mGraph"), W = box.clientWidth, H = box.clientHeight;
    gT.x = Math.min(Math.max(gT.x, 44 - gD.w * gT.z), W - 44);   // 怎么拖都至少留 44px 图在栏里
    gT.y = Math.min(Math.max(gT.y, 44 - gD.h * gT.z), H - 44);
    gSvg.setAttribute("transform", "translate(" + gT.x + "," + gT.y + ") scale(" + gT.z + ")");
  }
  function graphFit() {
    if (!gD) return;
    var box = document.getElementById("mGraph"), W = box.clientWidth - 12, H = box.clientHeight - 12;
    gT.z = Math.max(0.6, Math.min(1, W / gD.w, H / gD.h));       // 不小于 0.6：再小字就看不清了，宁可拖着看
    gT.x = Math.max(6, (W - gD.w * gT.z) / 2); gT.y = Math.max(6, (H - gD.h * gT.z) / 2);
    applyT();
  }
  function zoomAt(px, py, f) {
    var z = Math.min(2, Math.max(0.5, gT.z * f)); if (z === gT.z) return;
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
    var mk = 'viewBox="0 0 6 6" refX="5" refY="3" markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0L6 3L0 6z"/></marker>';
    h.push('<svg><defs><marker id="mga" ' + mk + '<marker id="mgb" ' + mk +
      '<clipPath id="mgc"><rect x="4" y="4" width="96" height="40" rx="2"/></clipPath></defs><g id="mGraphView">');
    d.edges.forEach(function (e) {
      var a = d.all[e.from], b = d.all[e.to], bw = b.ghost ? GW : NW, bh = b.ghost ? GH : NH, p;
      var lx, ly, an = "middle";   // 线上的字：选项写选项原文，@jump 写「跳」，顺序流不写字
      if (e.back) {   // 跳回前面：从源头右腰绕出去，落回目标右腰
        var sx = a.x + NW, sy = a.y + NH / 2, ex = b.x + bw, ey = b.y + bh / 2;
        p = "M" + sx + " " + sy + "C" + (sx + 36) + " " + sy + " " + (ex + 36) + " " + ey + " " + ex + " " + ey;
        lx = (sx + ex) / 2 + 20; ly = (sy + ey) / 2 + 4;
      } else {
        var x1 = a.x + NW / 2, y1 = a.y + NH, x2 = b.x + bw / 2, y2 = b.y, my = (y1 + y2) / 2;
        p = "M" + x1 + " " + y1 + "C" + x1 + " " + my + " " + x2 + " " + my + " " + x2 + " " + y2;
        // 上下正对着的两个节点，字写在箭头右边（写在线上会盖住箭头）；分叉的线写在线的中点
        if (Math.abs(x1 - x2) < 2) { lx = x1 + 5; an = "start"; } else lx = (x1 + x2) / 2;
        ly = my + 4;
      }
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
      gPtr[e.pointerId] = [e.clientX, e.clientY];
      try { box.setPointerCapture(e.pointerId); } catch (err) {}
      if (Object.keys(gPtr).length === 1) { gDist = 0; gDown = e.target.closest ? e.target.closest(".m-gn[data-i]") : null; }
      else { gPinch = 0; gDown = null; gDist = 99; }
      e.preventDefault();
    });
    box.addEventListener("pointermove", function (e) {
      var p = gPtr[e.pointerId]; if (!p) return;
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
        if (gDist < 8 && gDown) openScene(parseInt(gDown.getAttribute("data-i"), 10));
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

  // 场景页头的「流程 | 列表」与缩放三颗，只建一次
  function graphBar(p, on) {
    var head = p.querySelector(".cp-head"), add = document.getElementById("sceneAdd");
    if (!head || !add) return;
    var bar = document.getElementById("mGraphBar");
    if (!bar) {
      bar = document.createElement("div"); bar.id = "mGraphBar";
      bar.innerHTML = '<div class="m-gmodes"><button type="button" data-m="graph">流程</button><button type="button" data-m="list">列表</button></div>' +
        '<div class="m-gzoom"><button type="button" data-z="-" aria-label="缩小">−</button><button type="button" data-z="+" aria-label="放大">＋</button><button type="button" data-z="fit" aria-label="看全局">□</button></div>';
      bar.addEventListener("click", function (e) {
        var b = e.target.closest ? e.target.closest("button") : null; if (!b) return;
        var m = b.getAttribute("data-m");
        if (m) { try { localStorage.setItem(VIEW, m); } catch (err) {} graphSync(); return; }
        var box = document.getElementById("mGraph"); if (!box) return;
        if (b.getAttribute("data-z") === "fit") graphFit();
        else zoomAt(box.clientWidth / 2, box.clientHeight / 2, b.getAttribute("data-z") === "+" ? 1.25 : 0.8);
      });
      head.insertBefore(bar, add);
    }
    Array.prototype.forEach.call(bar.querySelectorAll("[data-m]"), function (b) { b.classList.toggle("on", (b.getAttribute("data-m") === "graph") === on); });
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
