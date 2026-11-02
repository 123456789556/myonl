/* ===================================================================
   场景视图（可视化编辑，2026-11-01）：
   对标 LetsGal Studio 的「场景管理 + 属性检查器」——不写代码也能改：
   左侧场景列表（按 @label 分幕），右侧属性面板改 背景/音乐/角色/台词/选项/跳转；
   保存时只改这些对应行，其它指令（@if/@wait/注释…）原样保留，写回同一个 .gal 文件。
   =================================================================== */
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var E = window.__editor || {};
  var pane = document.querySelector(".left-pane"), tabs = $("editorTabs");
  if (!pane || !tabs) return;

  var page = document.createElement("div");
  page.className = "center-page scene-page";
  page.id = "scenePage";
  page.innerHTML = '<div class="cp-head">' +
    '<span class="cp-title">场景编辑</span>' +
    '<span class="cp-hint">不写代码也能改画面：左选场景，右边改背景/角色/台词</span>' +
    '<span class="cp-spacer"></span>' +
    '<select class="cp-btn" id="sceneFilter" title="筛选场景类型"><option value="all">全部</option><option value="talk">有台词</option><option value="pic">纯画面</option><option value="video">视频</option></select>' +
    '<button type="button" class="cp-btn" id="sceneAdd" title="在本文件末尾新建一幕">＋ 新场景</button>' +
    '<button type="button" class="cp-btn" id="sceneCopy" title="复制当前场景（新 label）">复制</button>' +
    '<button type="button" class="cp-btn" id="sceneDel" title="删除当前场景（有跳转引用会先提示）">删除</button>' +
    '<button type="button" class="cp-btn" id="sceneRefresh" title="重新读取剧本">刷新</button>' +
    '<button type="button" class="cp-btn" id="sceneSave" title="把改动写回 .gal 文件（只改对应行）">保存修改</button>' +
    '<button type="button" class="cp-btn" id="sceneClose" title="关闭（Esc）">✕ 关闭</button>' +
    "</div>" +
    '<div class="scene-body"><div class="scene-list" id="sceneList"></div><div class="scene-form" id="sceneForm"></div></div>';
  pane.appendChild(page);

  var listEl = $("sceneList"), formEl = $("sceneForm");
  // 搜索框放在两栏上方的工具条里：直接插进 .scene-body 会多一个 flex 子项，把
  // 左侧列表和右侧表单挤成一条缝（并溢出到预览面板上，导致控件点不到）。
  var toolsBar = document.createElement("div");
  toolsBar.className = "scene-tools";
  try { page.insertBefore(toolsBar, page.querySelector(".scene-body")); } catch (e) {}
  var sceneSearch = document.createElement("input");
  sceneSearch.className = "set-search";
  sceneSearch.id = "sceneSearch";
  sceneSearch.placeholder = "搜索场景名…";
  // 筛选下拉也放进工具条，给顶部按钮腾地方（窗口窄时不换行遮挡）
  try {
    var filterEl = $("sceneFilter");
    if (filterEl) toolsBar.appendChild(filterEl);
  } catch (e) {}
  try { toolsBar.appendChild(sceneSearch); } catch (e) {}
  var ROW_H = 54;                 // 场景行固定高度（见 editor.css .scene-page .scene-item）
  var rowCache = null, rowCacheKey = "", paintPending = 0;
  var realPreviewUrl = "";
  var scenes = [];
  var curIdx = -1;
  var model = null;

  function fit() {
    // 小窗口下别把场景页顶到可视区外（739×650 实测会整页落到屏幕下方）
    var top = tabs.offsetTop + tabs.offsetHeight;
    page.style.top = Math.max(0, Math.min(top, window.innerHeight - 220)) + "px";
  }
  function toast(msg) { try { if (E.toast) E.toast(msg); } catch (e) {} }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]; }); }
  // 统一取正文：Windows 记事本保存的文件可能带 BOM，先剥掉再匹配 @label
  function getText() { return String(E.getText ? E.getText() : "").replace(/^\uFEFF/, ""); }

  function parseScenes(text) {
    var lines = String(text || "").replace(/^\uFEFF/, "").split("\n");
    var marks = [];
    for (var i = 0; i < lines.length; i++) {
      var m = lines[i].match(/^@label\s+(\S+)/);
      if (m) marks.push({ name: m[1], start: i });
    }
    var out = [];
    // 第一个 @label 之前的内容（@character/@bg/@set 等）也当成一个「开场设置」场景，避免看不到
    if (marks.length && marks[0].start > 0) {
      var headHas = lines.slice(0, marks[0].start).some(function (x) { return x.trim() && !/^\s*#/.test(x); });
      if (headHas) out.push({ name: "开场设置", start: 0, end: marks[0].start, head: true });
    }
    for (var k = 0; k < marks.length; k++) {
      out.push({ name: marks[k].name, start: marks[k].start, end: k + 1 < marks.length ? marks[k + 1].start : lines.length });
    }
    return out;
  }

  // 台词行解析：@[[...]] 整屏 / @[...] 普通（名字可再套 []）/ @ 角色 文本（旧写法）。
  // 独立成函数便于测试直接执行；必须与 engine/parser.py 的 _say_bracket 保持一致：
  // 先认双括号，再按「方括号深度」找单括号的闭合位置，不能用惰性正则（会把嵌套名截断）。
  function stripLeadColon(s) {
    s = String(s == null ? "" : s).trim();
    return /^[:：]/.test(s) ? s.slice(1).trim() : s;
  }
  function parseSayLine(t) {
    if (t.indexOf("@[[") === 0) {
      var c2 = t.indexOf("]]", 3);
      if (c2 > 3) {
        var who2 = t.slice(3, c2).trim();
        if (who2) return { who: who2, text: stripLeadColon(t.slice(c2 + 2)), style: "bracket2" };
      }
      return null;
    }
    if (t.indexOf("@[") === 0) {
      var depth = 0, close = -1;
      for (var k = 2; k < t.length; k++) {
        var ch = t.charAt(k);
        if (ch === "[") depth += 1;
        else if (ch === "]") {
          if (depth === 0) { close = k; break; }
          depth -= 1;
        }
      }
      if (close > 2) {
        var who = t.slice(2, close).trim();
        if (who) return { who: who, text: stripLeadColon(t.slice(close + 1)), style: "bracket" };
      }
      return null;
    }
    var m = t.match(/^@\s+(\S+)(?:\s+(.*))?$/);
    if (m) return { who: m[1], text: (m[2] || "").trim(), style: "plain" };
    return null;
  }

  function parseScene(lines, sc) {
    var seg = lines.slice(sc.start, sc.end);
    var m = { name: sc.name, lines: seg, start: sc.start, end: sc.end, bg: null, music: null, fg: null, chars: [], says: [], options: [], jump: null };
    var choiceLine = -1;
    for (var i = 0; i < seg.length; i++) {
      var t = seg[i];
      // 背景/音乐保留名字后面的演出参数（fadein/fadeout），保存时不丢
      var b = t.match(/^@bg\s+(\S+)(.*)$/);
      if (b) m.bg = { i: i, name: b[1], extra: (b[2] || "").trim() };
      var mu = t.match(/^@music\s+(\S+)(.*)$/);
      if (mu) m.music = { i: i, name: mu[1], extra: (mu[2] || "").trim() };
      var vd = t.match(/^@video\s+(\S+)(.*)$/); if (vd) m.video = { i: i, name: vd[1], extra: (vd[2] || "").trim() };
      var sh = t.match(/^@show\s+(.+)$/);
      if (sh) {
        var toks = sh[1].trim().split(/\s+/);
        var ch = { i: i, name: toks.shift(), expr: "", pos: null, x: null, y: null, anim: null, rawParams: [] };
        if (toks.length && !/[=:]/.test(toks[0])) ch.expr = toks.shift();
        ch.rawParams = toks.slice();   // anim=、部位:素材 等原样保留，保存时回写
        toks.forEach(function (part) {
          var p = part.split("="), k = p[0], v = p[1];
          if (k === "pos" && (v === "左" || v === "中" || v === "右")) ch.pos = v;
          if (k === "x" && /^-?\d+$/.test(v)) ch.x = parseInt(v, 10);
          if (k === "y" && /^-?\d+$/.test(v)) ch.y = parseInt(v, 10);
          if (k === "scale" && /^\d*(\.\d+)?$/.test(v)) ch.scale = parseFloat(v);
          if (k === "z" && /^-?\d+$/.test(v)) ch.z = parseInt(v, 10);
          if (k === "anim") ch.anim = v;
        });
        m.chars.push(ch);
      }
      var fgm = t.match(/^@fg\s+(\S+)/); if (fgm) m.fg = { i: i, name: fgm[1] };
      var jp = t.match(/^@jump\s+(\S+)/); if (jp) m.jump = { i: i, target: jp[1] };
      if (/^@choice\s*:/.test(t.trim())) choiceLine = i;
      // 台词三种写法：@[[角色]] 整屏 / @[角色] 普通 / @ 角色 文本（旧写法）
      var said = parseSayLine(t);
      if (said) m.says.push({ i: i, who: said.who, text: said.text, style: said.style });
    }
    if (choiceLine >= 0) {
      for (var j = choiceLine + 1; j < seg.length; j++) {
        var op = seg[j].match(/^\s*>\s*(.+?)\s*->\s*(\S+)\s*$/);
        if (!op) break;
        m.options.push({ i: j, text: op[1], target: op[2] });
      }
    }
    return m;
  }

  function allCharacters() {
    var txt = getText();
    var names = {}, re = /^@character\s+(\S+)/gm, mm;
    while ((mm = re.exec(txt))) names[mm[1]] = 1;
    return Object.keys(names);
  }
  function assetList(kind) {
    try { var a = E.getAssets ? E.getAssets() : null; return (a && a[kind]) || []; } catch (e) { return []; }
  }
  function optsHtml(list, selected, emptyLabel) {
    var html = '<option value="">' + esc(emptyLabel || "（无）") + "</option>";
    var seen = {};
    if (selected && list.indexOf(selected) < 0) {
      html += '<option value="' + esc(selected) + '" selected>' + esc(selected) + "（当前）</option>";
      seen[selected] = 1;
    }
    list.forEach(function (x) { if (!seen[x]) html += '<option value="' + esc(x) + '"' + (x === selected ? " selected" : "") + ">" + esc(x) + "</option>"; });
    return html;
  }

  function refresh() {
    var text = getText();
    scenes = parseScenes(text);
    renderList();
    if (scenes.length) {
      if (curIdx < 0 || curIdx >= scenes.length) curIdx = 0;
      selectScene(curIdx);
    } else {
      listEl.innerHTML = '<div class="scene-empty">还没有 @label，先给场景起个名字吧</div>';
      formEl.innerHTML = '<div class="scene-empty">这个文件还没有场景</div>';
    }
  }

  var sceneFilter = "all";
  var CH_H = 30;                  // 章节分组头行高（见 editor.css .scene-chapter）
  // V3：章节分组折叠状态（标题 → 1），按工程记忆
  var collapsedChapters = {};
  try { collapsedChapters = JSON.parse(localStorage.getItem("gal_scene_chapters") || "{}") || {}; } catch (e) { collapsedChapters = {}; }
  function saveCollapsed() {
    try { localStorage.setItem("gal_scene_chapters", JSON.stringify(collapsedChapters)); } catch (e) {}
  }
  // 场景列表虚拟滚动：只渲染视口内的行（几百场景也不卡）。
  // 行模型按「正文 + 筛选 + 搜索 + 折叠」缓存，选中场景时不再重扫全文。
  function chapterOf(sc, chapters) {
    var name = "";
    for (var k = 0; k < chapters.length; k++) {
      if (chapters[k].line < sc.start) name = chapters[k].title; else break;
    }
    return name;
  }

  function buildRows() {
    var text = getText();
    var lines = text.split("\n");
    var q = (sceneSearch.value || "").trim().toLowerCase();
    var chapters = [];
    for (var li = 0; li < lines.length; li++) {
      var mc = lines[li].match(/^@chapter\s+(.+)$/);
      if (mc) chapters.push({ line: li, title: mc[1].replace(/\s+secs=\S+$/, "").trim() });
    }
    var rows = [], group = null, groupCount = 0;
    function flushGroup() {
      if (group !== null && groupCount === 0) {
        // 搜索/筛选后空章节不显示（避免一排空标题）
        rows = rows.filter(function (r) { return r.type !== "chapter" || r.title !== group; });
      }
    }
    scenes.forEach(function (sc, i) {
      var seg = lines.slice(sc.start + 1, sc.end).join("\n");
      var isVideo = /^@video\s+\S/m.test(seg);
      var hasShow = /^@show\s+\S/m.test(seg);
      var hasSay = /^(?:@\s+\S|@\[)/m.test(seg);
      var kind = isVideo ? "video" : (hasSay ? "talk" : (hasShow ? "pic" : "talk"));
      if (sceneFilter !== "all" && sceneFilter !== kind) return;
      if (q && sc.name.toLowerCase().indexOf(q) < 0) return;
      var ch = chapterOf(sc, chapters);
      if (ch !== group) {
        flushGroup();
        group = ch;
        groupCount = 0;
        if (chapters.length) rows.push({ type: "chapter", title: ch, h: CH_H, count: 0 });
      }
      groupCount += 1;
      if (chapters.length) {
        // 组头计数：折叠时组头就是最后一行，展开时需回溯到组头
        for (var bi = rows.length - 1; bi >= 0; bi--) {
          if (rows[bi].type === "chapter") { rows[bi].count += 1; break; }
        }
      }
      if (chapters.length && collapsedChapters[ch || "(未分章)"]) return;   // 折叠：只留组头
      rows.push({
        type: "scene",
        i: i,
        h: ROW_H,
        name: sc.name,
        bg: (seg.match(/^@bg\s+(\S+)/m) || [])[1] || "—",
        kind: isVideo ? "视频" : (hasSay ? "有台词" : (hasShow ? "纯画面" : "空")),
        badge: isVideo ? '<span class="sc-badge video">视频</span>'
          : (!hasSay && hasShow ? '<span class="sc-badge">纯画面</span>' : ""),
      });
    });
    flushGroup();
    return rows;
  }

  function rowsKey() {
    var sig = Object.keys(collapsedChapters).filter(function (k) { return collapsedChapters[k]; }).sort().join(",");
    return getText() + "\u0000" + sceneFilter + "\u0000" +
      (sceneSearch.value || "") + "\u0000" + sig;
  }

  function ensureRows() {
    var key = rowsKey();
    if (!rowCache || rowCacheKey !== key) { rowCache = buildRows(); rowCacheKey = key; }
    return rowCache;
  }

  function rowOffsets(rows) {
    var off = [], y = 0;
    for (var k = 0; k < rows.length; k++) { off.push(y); y += rows[k].h; }
    return { off: off, total: y };
  }

  function paint() {
    paintPending = 0;
    var rows = rowCache || [];
    var holder = listEl.querySelector(".scene-rows");
    if (!holder) return;
    var geo = rowOffsets(rows);
    var top = listEl.scrollTop, viewH = listEl.clientHeight || 400;
    var first = 0;
    while (first < rows.length && geo.off[first] + rows[first].h < top) first++;
    first = Math.max(0, first - 2);
    var last = first, bottom = top + viewH;
    while (last < rows.length && geo.off[last] < bottom) last++;
    last = Math.min(rows.length, last + 2);
    var html = "";
    for (var k = first; k < last; k++) {
      var r = rows[k], y = geo.off[k];
      if (r.type === "chapter") {
        var ckey = r.title || "(未分章)";
        var folded = !!collapsedChapters[ckey];
        html += '<div class="scene-chapter" data-ch="' + esc(ckey) + '" style="top:' + y + 'px" title="点击折叠/展开本章">' +
          '<span class="sc-chev">' + (folded ? "▸" : "▾") + "</span>" +
          '<span class="sc-ch-name">' + esc(ckey) + "</span>" +
          '<span class="sc-ch-count">' + r.count + "</span></div>";
        continue;
      }
      html += '<div class="scene-item' + (r.i === curIdx ? " active" : "") + '" data-i="' + r.i +
        '" style="top:' + y + 'px" title="' + esc(r.name) + '">' +
        '<div class="sc-name">' + esc(r.name) + r.badge + "</div>" +
        '<div class="sc-meta">' + esc(r.bg) + " · " + r.kind + "</div></div>";
    }
    holder.innerHTML = html;
  }

  function schedulePaint() {
    if (paintPending) return;
    paintPending = (window.requestAnimationFrame || function (f) { return setTimeout(f, 16); })(paint);
  }

  function renderList() {
    var rows = ensureRows();
    listEl.innerHTML = rows.length
      ? '<div class="scene-rows" style="height:' + rowOffsets(rows).total + 'px"></div>'
      : '<div class="scene-empty">还没有场景</div>';
    paint();
  }

  function selectScene(i) {
    curIdx = i;
    var text = getText();
    var lines = text.split("\n");
    model = parseScene(lines, scenes[i]);
    renderList();
    renderForm();
  }

  function charactersSafe() { try { return allCharacters(); } catch (e) { return []; } }

  // ---------- 图层顺序面板：背景 < 立绘(z) < 前景 < UI，拖拽立绘行改 z ----------
  function layerOrder() {
    return model.chars.map(function (c, i) { return { c: c, i: i }; })
      .filter(function (x) { return !x.c.del; })
      .sort(function (a, b) { return (b.c.z || 0) - (a.c.z || 0); });   // 高 z 在上
  }

  function layerPanelHtml() {
    var rows = [];
    rows.push('<div class="sf-layer fixed ui"><span class="sf-layer-tag">最上</span>' +
      '<span class="sf-layer-name">UI 界面层（对话框 / 菜单，固定）</span></div>');
    if (model.fg) {
      rows.push('<div class="sf-layer fixed fg"><span class="sf-layer-tag">前景</span>' +
        '<span class="sf-layer-name">' + esc(model.fg.name) + '（@fg，固定盖在立绘上）</span></div>');
    }
    layerOrder().forEach(function (x) {
      rows.push('<div class="sf-layer draggable" data-i="' + x.i + '" title="拖动调整前后顺序">' +
        '<span class="sf-layer-handle">≡</span>' +
        '<span class="sf-layer-name">' + esc(x.c.name || "（未选角色）") +
        (x.c.expr ? " · " + esc(x.c.expr) : "") + "</span>" +
        '<span class="sf-layer-z">z=' + (x.c.z == null ? 0 : x.c.z) + "</span>" +
        '<button type="button" class="icon-btn sf-layer-up" data-i="' + x.i + '" title="上移一层（更靠前）">↑</button>' +
        '<button type="button" class="icon-btn sf-layer-down" data-i="' + x.i + '" title="下移一层（更靠后）">↓</button></div>');
    });
    rows.push('<div class="sf-layer fixed bg"><span class="sf-layer-tag">最下</span>' +
      '<span class="sf-layer-name">背景' + (model.bg ? " · " + esc(model.bg.name) : "") + "</span></div>");
    return '<div class="sf-sec">图层顺序 <span class="sf-hint">拖动立绘行改 z，越上越靠前</span></div>' +
      '<div class="sf-layers" id="sfLayers">' + rows.join("") + "</div>";
  }

  function reorderLayers(fromI, toI) {
    var list = layerOrder();
    var from = -1, to = -1;
    for (var k = 0; k < list.length; k++) {
      if (list[k].i === fromI) from = k;
      if (list[k].i === toI) to = k;
    }
    if (from < 0 || to < 0 || from === to) return;
    var moved = list.splice(from, 1)[0];
    list.splice(to, 0, moved);
    var n = list.length;
    list.forEach(function (x, idx) { x.c.z = n - 1 - idx; });   // 顶部 z 最大
    renderForm();   // 重建表单：z 输入框、图层表、舞台一起刷新
  }

  function moveLayer(i, dir) {
    var list = layerOrder();
    var pos = -1;
    for (var k = 0; k < list.length; k++) if (list[k].i === i) pos = k;
    if (pos < 0) return;
    var target = pos + (dir > 0 ? -1 : 1);   // dir>0 = 在列表里向上（更靠前）
    if (target < 0 || target >= list.length) return;
    reorderLayers(i, list[target].i);
  }

  function wireLayers() {
    var box = $("sfLayers");
    if (!box) return;
    Array.prototype.forEach.call(box.querySelectorAll(".sf-layer-up"), function (btn) {
      btn.addEventListener("click", function () { moveLayer(parseInt(btn.getAttribute("data-i"), 10), 1); });
    });
    Array.prototype.forEach.call(box.querySelectorAll(".sf-layer-down"), function (btn) {
      btn.addEventListener("click", function () { moveLayer(parseInt(btn.getAttribute("data-i"), 10), -1); });
    });
    // 指针拖拽（WebView2 / 无头浏览器都稳，不依赖 HTML5 DnD）
    // 事件绑在容器上：指针移出行外也能继续收到 move，松手时用 elementFromPoint 找目标行。
    var dragEl = null, dragI = -1, startY = 0, dragging = false;
    function clearMarks() {
      Array.prototype.forEach.call(box.querySelectorAll(".sf-layer"), function (r) {
        r.classList.remove("drag-over", "dragging");
      });
    }
    box.addEventListener("pointerdown", function (ev) {
      if (ev.target.closest && ev.target.closest("button")) return;   // 点 ↑↓ 不拖
      var el = ev.target.closest ? ev.target.closest(".sf-layer.draggable") : null;
      if (!el) return;
      ev.preventDefault();
      dragEl = el;
      dragI = parseInt(el.getAttribute("data-i"), 10);
      startY = ev.clientY;
      dragging = false;
      try { box.setPointerCapture(ev.pointerId); } catch (e) {}
    });
    box.addEventListener("pointermove", function (ev) {
      if (!dragEl) return;
      if (!dragging && Math.abs(ev.clientY - startY) < 4) return;
      dragging = true;
      dragEl.classList.add("dragging");
      var under = document.elementFromPoint(ev.clientX, ev.clientY);
      var row = under && under.closest ? under.closest(".sf-layer.draggable") : null;
      Array.prototype.forEach.call(box.querySelectorAll(".sf-layer"), function (r) {
        if (r !== row) r.classList.remove("drag-over");
      });
      if (row && row !== dragEl) row.classList.add("drag-over");
    });
    box.addEventListener("pointerup", function (ev) {
      if (dragEl && dragging) {
        var under = document.elementFromPoint(ev.clientX, ev.clientY);
        var row = under && under.closest ? under.closest(".sf-layer.draggable") : null;
        var targetI = row ? parseInt(row.getAttribute("data-i"), 10) : NaN;
        if (!isNaN(targetI) && targetI !== dragI) reorderLayers(dragI, targetI);
      }
      dragEl = null;
      dragI = -1;
      dragging = false;
      clearMarks();
    });
    box.addEventListener("pointercancel", function () {
      dragEl = null;
      dragI = -1;
      dragging = false;
      clearMarks();
    });
  }

  function renderForm() {
    if (!model) return;
    var chars = allCharacters();
    var lib = window.__characterLib && window.__characterLib.characters ? window.__characterLib.characters : [];
    var libIds = lib.map(function (c) { return c.id; });
    var pool = libIds.concat(chars.filter(function (x) { return libIds.indexOf(x) < 0; }));
    var exprs = {};
    lib.forEach(function (c) { Object.keys(c.avatars || {}).forEach(function (k) { exprs[k] = 1; }); });
    var images = assetList("images"), audios = assetList("audio");
    var h = [];
    h.push('<div class="sf-scene"><span class="sf-label">场景</span><b>' + esc(model.name) + "</b></div>");
    h.push('<div class="sf-row"><span class="sf-label">背景</span><select id="sfBg">' + optsHtml(images, model.bg ? model.bg.name : "", "（保持不变）") + "</select></div>");
    h.push('<div class="sf-row"><span class="sf-label">音乐</span><select id="sfMusic">' + optsHtml(audios, model.music ? model.music.name : "", "（保持不变）") + "</select></div>");
    var videos = assetList("videos");
    h.push('<div class="sf-row"><span class="sf-label">视频</span><select id="sfVideo" title="@video 全屏视频：只有视频、没有台词的过场就靠它">' + optsHtml(videos, model.video ? model.video.name : "", "（无视频）") + "</select></div>");
    h.push('<datalist id="sfExprList">' + Object.keys(exprs).map(function (k) { return '<option value="' + esc(k) + '">'; }).join("") + "</datalist>");
    h.push('<div class="sf-stage-wrap"><div class="sf-stage" id="sfStage"></div><div class="sf-stage-hint">拖动角色调整位置 · 双击复位 · 也可用下面的位置下拉</div></div>');
    h.push(layerPanelHtml());
    h.push('<div class="sf-sec">角色 <button type="button" class="icon-btn" id="sfAddChar">＋ 加角色</button></div>');
    h.push('<div id="sfChars">');
    model.chars.forEach(function (c, i) {
      if (c.del) return;
      h.push('<div class="sf-cast" data-i="' + i + '"><select class="sf-char">' + optsHtml(pool, c.name, "角色…") + '</select>' +
        '<input class="sf-expr" list="sfExprList" placeholder="表情" value="' + esc(c.expr) + '">' +
        '<input class="sf-scale" type="number" min="0.5" max="2" step="0.05" placeholder="缩放" title="scale 0.5~2" value="' + (c.scale != null ? c.scale : "") + '">' +
        '<input class="sf-z" type="number" step="1" placeholder="层级" title="z 图层顺序，大者在上" value="' + (c.z != null ? c.z : "") + '">' +
        '<select class="sf-pos" title="位置（左/中/右）；拖动预览后为自定义"><option value="">默认</option>' +
        '<option value="左"' + (c.pos === "左" ? " selected" : "") + '>左</option>' +
        '<option value="中"' + (c.pos === "中" ? " selected" : "") + '>中</option>' +
        '<option value="右"' + (c.pos === "右" ? " selected" : "") + '>右</option></select>' +
        '<button type="button" class="icon-btn sf-edit-char" data-i="' + i + '" title="编辑这个角色（会打开角色库）">✎</button>' +
        '<button type="button" class="icon-btn sf-del" data-kind="char" data-i="' + i + '">✕</button></div>');
    });
    h.push("</div>");
    h.push('<div class="sf-sec">台词 <button type="button" class="icon-btn" id="sfAddSay">＋ 加台词</button></div>');
    h.push('<div id="sfSays">');
    model.says.forEach(function (s, i) {
      if (s.del) return;
      h.push('<div class="sf-say" data-i="' + i + '"><select class="sf-who">' + optsHtml(pool, s.who, "角色…") + "</select>" +
        '<textarea class="sf-text" rows="2" placeholder="台词内容">' + esc(s.text) + "</textarea>" +
        '<button type="button" class="icon-btn sf-del" data-kind="say" data-i="' + i + '">✕</button></div>');
    });
    h.push("</div>");
    h.push('<div class="sf-sec">选项（@choice） <button type="button" class="icon-btn" id="sfAddOpt">＋ 加选项</button></div>');
    h.push('<div id="sfOpts">');
    model.options.forEach(function (o, i) {
      if (o.del) return;
      h.push('<div class="sf-opt" data-i="' + i + '"><input class="sf-opt-text" placeholder="选项文字" value="' + esc(o.text) + '">' +
        '<input class="sf-opt-target" placeholder="跳转到 label" value="' + esc(o.target) + '">' +
        '<button type="button" class="icon-btn sf-del" data-kind="opt" data-i="' + i + '">✕</button></div>');
    });
    h.push("</div>");
    h.push('<div class="sf-row"><span class="sf-label">结束跳转</span><input id="sfJump" placeholder="@jump 目标（留空=不跳）" value="' + esc(model.jump ? model.jump.target : "") + '"></div>');
    h.push('<div class="sf-actions"><button type="button" class="icon-btn" id="sfSaveBtn">保存这个场景</button></div>');
    formEl.innerHTML = h.join("");
    wire();
    renderStage();
  }

  // ---------- 舞台预览：背景 + 可拖动角色 ----------
  var dragState = null;
  function chipPercent(c) {
    var left, bottom = 6;
    if (c.x !== null && c.y !== null) {
      left = 50 + (c.x / 1280) * 100;
      bottom = 6 - (c.y / 720) * 100;
    } else if (c.pos === "左") { left = 22; }
    else if (c.pos === "右") { left = 78; }
    else { left = 50; }
    return { left: left, bottom: bottom };
  }
  function placeChip(chip, c) {
    var p = chipPercent(c);
    chip.style.left = p.left + "%";
    chip.style.bottom = p.bottom + "%";
  }
  function renderStage() {
    var stage = $("sfStage");
    if (!stage || !model) return;
    var bgName = $("sfBg") && $("sfBg").value ? $("sfBg").value : (model.bg ? model.bg.name : "");
    var inherited = false;
    if (!bgName) {
      var allLines = getText().split("\n");
      for (var li = model.start - 1; li >= 0; li--) {
        var mm = allLines[li].match(/^@bg\s+(\S+)/);
        if (mm) { bgName = mm[1]; inherited = true; break; }
      }
    }
    var url = "";
    try { if (bgName && E.assetURL) url = E.assetURL("images", bgName); } catch (e) {}
    stage.innerHTML = url
      ? '<img class="sf-stage-bg" src="' + esc(url) + '" alt="">' +
        (inherited ? '<div class="sf-stage-inherit">沿用上一场景背景：' + esc(bgName) + "</div>" : "")
      : '<div class="sf-stage-empty">选背景后这里显示画面预览</div>';
    var realBtn = document.createElement("button");
    realBtn.type = "button"; realBtn.className = "sf-real-btn";
    realBtn.textContent = realPreviewUrl ? "✓ 真实渲染（点此还原）" : "🖼 真实渲染预览";
    realBtn.title = "用引擎真实渲染这一帧当底图（不是 HTML 模拟）";
    realBtn.addEventListener("click", function () {
      if (realPreviewUrl) { realPreviewUrl = ""; var o = document.getElementById("sfRealShot"); if (o) o.remove(); renderStage(); return; }
      var path = "";
      try { path = E.getCurPath ? (E.getCurPath() || "") : ""; } catch (e) {}
      realBtn.textContent = "渲染中…"; realBtn.disabled = true;
      fetch("/api/preview", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: getText(), path: path, frames: 10 }) })
        .then(function (r) { if (!r.ok) throw new Error("预览失败 " + r.status); return r.blob(); })
        .then(function (b) {
          realPreviewUrl = URL.createObjectURL(b);
          var old = document.getElementById("sfRealShot"); if (old) old.remove();
          var shot = document.createElement("img");
          shot.id = "sfRealShot"; shot.className = "sf-real-shot";
          shot.src = realPreviewUrl; shot.alt = "引擎真实渲染预览";
          var st = document.getElementById("sfStage");
          if (st) st.appendChild(shot);
          realBtn.textContent = "✓ 真实渲染（点此还原）"; realBtn.disabled = false;
        })
        .catch(function (e) { realBtn.textContent = "真实渲染失败"; realBtn.disabled = false; toast("真实预览失败：" + e, true); });
    });
    stage.appendChild(realBtn);
    var videoName = $("sfVideo") && $("sfVideo").value ? $("sfVideo").value : (model.video ? model.video.name : "");
    if (videoName) {
      var vwrap = document.createElement("div");
      vwrap.className = "sf-stage-video";
      var vbtn = document.createElement("button");
      vbtn.type = "button";
      vbtn.className = "sf-video-play";
      vbtn.textContent = "▶ 播放视频：" + videoName;
      vbtn.title = "这是视频场景（可以没有台词）；点一下才加载播放，避免打开就卡";
      vbtn.addEventListener("click", function () {
        var vurl = "";
        try { if (E.assetURL) vurl = E.assetURL("videos", videoName); } catch (e) {}
        vwrap.innerHTML = '<video class="sf-stage-video-el" src="' + esc(vurl) + '" controls muted loop playsinline></video>';
        var vel = vwrap.querySelector("video");
        if (vel) { var pr = vel.play(); if (pr && pr.catch) pr.catch(function () {}); }
      });
      vwrap.appendChild(vbtn);
      stage.appendChild(vwrap);
    }
    model.chars.forEach(function (c, i) {
      if (c.del || !c.name) return;
      var chip = document.createElement("div");
      chip.className = "sf-sprite";
      chip.setAttribute("data-i", i);
      chip.style.zIndex = String(10 + (c.z || 0));   // 舞台上的前后关系跟 z 一致
      chip.title = "拖动定位；双击复位";
      chip.innerHTML = '<b>' + esc(c.name) + '</b>' + (c.expr ? '<span>' + esc(c.expr) + '</span>' : "");
      placeChip(chip, c);
      chip.addEventListener("pointerdown", function (ev) {
        ev.preventDefault();
        var rect = stage.getBoundingClientRect();
        dragState = { idx: i, startX: ev.clientX, startY: ev.clientY, rect: rect, chip: chip,
                      baseX: c.x !== null ? c.x : (c.pos === "左" ? -320 : c.pos === "右" ? 320 : 0),
                      baseY: c.y !== null ? c.y : 0 };
        chip.classList.add("dragging");
      });
      chip.addEventListener("dblclick", function () {
        c.x = null; c.y = null; c.pos = "中";
        var sel = formEl.querySelector('.sf-cast[data-i="' + i + '"] .sf-pos');
        if (sel) sel.value = "中";
        placeChip(chip, c);
      });
      stage.appendChild(chip);
    });
  }
  document.addEventListener("pointermove", function (ev) {
    if (!dragState) return;
    var st = dragState;
    var dx = (ev.clientX - st.startX) / st.rect.width * 1280;
    var dy = (ev.clientY - st.startY) / st.rect.height * 720;
    var c = model.chars[st.idx];
    c.x = Math.round(st.baseX + dx);
    c.y = Math.round(st.baseY + dy);
    c.pos = null;
    placeChip(st.chip, c);
  });
  document.addEventListener("pointerup", function () {
    if (!dragState) return;
    dragState.chip.classList.remove("dragging");
    dragState = null;
    var sel = formEl.querySelectorAll(".sf-pos");
    for (var i = 0; i < sel.length; i++) sel[i].value = "";
  });

  function wire() {
    var del = formEl.querySelectorAll(".sf-del");
    for (var i = 0; i < del.length; i++) {
      del[i].addEventListener("click", function () {
        var kind = this.getAttribute("data-kind"), idx = parseInt(this.getAttribute("data-i"), 10);
        if (kind === "char") model.chars[idx].del = true;
        if (kind === "say") model.says[idx].del = true;
        if (kind === "opt") model.options[idx].del = true;
        renderForm();
      });
    }
    $("sfAddChar").addEventListener("click", function () { model.chars.push({ added: true, name: charactersSafe()[0] || "", expr: "" }); renderForm(); });
    $("sfAddSay").addEventListener("click", function () { model.says.push({ added: true, who: charactersSafe()[0] || "", text: "" }); renderForm(); });
    $("sfAddOpt").addEventListener("click", function () { model.options.push({ added: true, text: "", target: "" }); renderForm(); });
    var edits = formEl.querySelectorAll(".sf-edit-char");
    for (var m = 0; m < edits.length; m++) {
      edits[m].addEventListener("click", function () {
        var idx = parseInt(this.getAttribute("data-i"), 10);
        var row = formEl.querySelector('.sf-cast[data-i="' + idx + '"] .sf-char');
        var name = row ? row.value : "";
        if (window.__openCharacterManager) window.__openCharacterManager(name);
      });
    }
    var posSel = formEl.querySelectorAll(".sf-pos");
    for (var k = 0; k < posSel.length; k++) {
      posSel[k].addEventListener("change", function () {
        var row = this.closest(".sf-cast");
        var idx = row ? parseInt(row.getAttribute("data-i"), 10) : -1;
        if (idx < 0) return;
        var c = model.chars[idx];
        if (this.value) { c.pos = this.value; c.x = null; c.y = null; }
        else c.pos = null;
        renderStage();
      });
    }
    var bgSel = $("sfBg");
    if (bgSel) bgSel.addEventListener("change", renderStage);
    var vSel = $("sfVideo");
    if (vSel) vSel.addEventListener("change", renderStage);
    wireLayers();   // 图层顺序面板的拖拽
    $("sfSaveBtn").addEventListener("click", saveCurrent);
  }

  function collect() {
    if (!model) return;
    model.newBg = $("sfBg").value;
    model.newMusic = $("sfMusic").value;
    model.newVideo = $("sfVideo") ? $("sfVideo").value : "";
    var castEls = formEl.querySelectorAll(".sf-cast");
    var chars = [];
    for (var i = 0; i < castEls.length; i++) {
      var sel = castEls[i].querySelector(".sf-char"), ex = castEls[i].querySelector(".sf-expr");
      if (!sel || !sel.value) continue;
      var idx = parseInt(castEls[i].getAttribute("data-i"), 10);
      var base = model.chars[idx] || {};
      var szI = castEls[i].querySelector(".sf-scale"), zI = castEls[i].querySelector(".sf-z");
      var szV = szI && szI.value.trim() !== "" ? parseFloat(szI.value) : null;
      if (szV != null && (szV < 0.5 || szV > 2)) szV = null;
      chars.push({ i: (base && base.i != null) ? base.i : null,
                   name: sel.value, expr: (ex && ex.value.trim()) || "",
                   rawParams: (base && base.rawParams) || [],
                   pos: base.pos || null,
                   x: (base.x === undefined ? null : base.x),
                   y: (base.y === undefined ? null : base.y),
                   scale: szV,
                   z: zI && zI.value.trim() !== "" ? parseInt(zI.value, 10) : null });
    }
    model.newChars = chars;
    var sayEls = formEl.querySelectorAll(".sf-say");
    var says = [];
    for (var j = 0; j < sayEls.length; j++) {
      var who = sayEls[j].querySelector(".sf-who"), txt = sayEls[j].querySelector(".sf-text");
      if (!who || !who.value) continue;
      var si = parseInt(sayEls[j].getAttribute("data-i"), 10);
      var baseSay = (!isNaN(si) && model.says[si]) ? model.says[si] : null;
      // 新加的台词默认用方括号写法（不用先登记角色）；原有台词保留原写法
      says.push({ i: (baseSay && baseSay.i != null) ? baseSay.i : null,
                  who: who.value, text: (txt && txt.value) || "",
                  style: (baseSay && baseSay.style) || "bracket" });
    }
    model.newSays = says;
    var optEls = formEl.querySelectorAll(".sf-opt");
    var opts = [];
    for (var k = 0; k < optEls.length; k++) {
      var t = optEls[k].querySelector(".sf-opt-text"), g = optEls[k].querySelector(".sf-opt-target");
      if (!t || !t.value.trim()) continue;
      opts.push({ text: t.value.trim(), target: (g && g.value.trim()) || "" });
    }
    model.newOptions = opts;
    model.newJump = $("sfJump") ? $("sfJump").value.trim() : "";
  }

  function saveCurrent() {
    var text = getText();
    if (!text) { toast("没有打开的剧本"); return; }
    collect();
    var lines = text.split("\n");
    var sc = scenes[curIdx];
    var seg = lines.slice(sc.start, sc.end);
    var insertAfter = {};
    function markAdd(i, arr) { (insertAfter[i] = insertAfter[i] || []).push.apply(insertAfter[i], arr); }

    var bgLine = -1, muLine = -1;
    for (var i = 0; i < seg.length; i++) {
      if (/^@bg\s+/.test(seg[i])) bgLine = i;
      if (/^@music\s+/.test(seg[i])) muLine = i;
    }
    if (model.newBg) {
      // 名字没改就保留原来的 fadein 等演出参数
      var bgKeep = model.bg && model.bg.name === model.newBg && model.bg.extra ? " " + model.bg.extra : "";
      if (bgLine >= 0) seg[bgLine] = "@bg " + model.newBg + bgKeep;
      else markAdd(0, ["@bg " + model.newBg]);
    }
    if (model.newMusic) {
      var muKeep = model.music && model.music.name === model.newMusic && model.music.extra ? " " + model.music.extra : "";
      if (muLine >= 0) seg[muLine] = "@music " + model.newMusic + muKeep;
      else markAdd(0, ["@music " + model.newMusic]);
    }

    // 视频场景（@video 全屏视频，可以没有台词）
    var videoLine = -1;
    for (var vi = 0; vi < seg.length; vi++) if (seg[vi] !== null && /^@video\s+/.test(seg[vi])) videoLine = vi;
    if (model.newVideo) {
      var vline = "@video " + model.newVideo;
      if (model.video && model.video.extra && model.video.name === model.newVideo) vline += " " + model.video.extra;
      if (videoLine >= 0) seg[videoLine] = vline;
      else markAdd(Math.max(bgLine, muLine, 0), [vline]);
    } else if (videoLine >= 0) seg[videoLine] = null;

    // 立绘：原有行原位改写（保持顺序与 @if 间穿插），未识别参数（anim=、部位:素材）原样保留
    var showIdx = [], showAt = {};
    for (var s = 0; s < seg.length; s++) if (/^@show\s+/.test(seg[s])) { showIdx.push(s); showAt[s] = 1; }
    showIdx.forEach(function (idx) { seg[idx] = null; });
    var castAnchor = Math.max(bgLine, muLine, 0);
    var managed = { pos: 1, x: 1, y: 1, scale: 1, z: 1 };
    function showLine(c) {
      var line = "@show " + c.name + (c.expr ? " " + c.expr : "");
      (c.rawParams || []).forEach(function (tok) {
        if (!managed[tok.split("=")[0]]) line += " " + tok;
      });
      if (c.x !== null && c.y !== null) line += " x=" + c.x + " y=" + c.y;
      else if (c.pos) line += " pos=" + c.pos;
      if (c.scale != null) line += " scale=" + c.scale;
      if (c.z != null) line += " z=" + c.z;
      return line;
    }
    model.newChars.forEach(function (c) {
      var line = showLine(c);
      if (c.i != null && showAt[c.i]) seg[c.i] = line;
      else markAdd(castAnchor, [line]);
    });

    // 台词：原有行原位改写（不再整体搬到末尾），新增的插在最后一句之后
    var sayIdx = [], sayAt = {};
    for (var q = 0; q < seg.length; q++) {
      if (/^@\s+\S/.test(seg[q]) || /^@\[/.test(seg[q])) { sayIdx.push(q); sayAt[q] = 1; }
    }
    sayIdx.forEach(function (idx) { seg[idx] = null; });
    var sayAnchor = sayIdx.length ? sayIdx[sayIdx.length - 1] : castAnchor;
    model.newSays.forEach(function (x) {
      var line = x.style === "bracket2" ? "@[[" + x.who + "]]"
        : x.style === "plain" ? "@ " + x.who
          : "@[" + x.who + "]";
      if (x.text) line += " " + x.text;
      if (x.i != null && sayAt[x.i]) seg[x.i] = line;
      else markAdd(sayAnchor, [line]);
    });

    var firstEnd = -1;
    for (var e0 = 0; e0 < seg.length; e0++) {
      if (seg[e0] !== null && /^@end\b/.test(seg[e0])) { firstEnd = e0; break; }
    }
    var choiceAt = -1;
    for (var c2 = 0; c2 < seg.length; c2++) {
      if (seg[c2] === null) continue;
      if (/^@choice\s*:/.test(seg[c2].trim())) { choiceAt = c2; break; }
    }
    if (choiceAt >= 0) {
      var endOpt = choiceAt + 1;
      while (endOpt < seg.length && /^\s*>/.test(seg[endOpt])) endOpt++;
      for (var d = choiceAt + 1; d < endOpt; d++) seg[d] = null;
      var opts = model.newOptions.map(function (o) { return "  > " + o.text + " -> " + (o.target || "start"); });
      if (!opts.length) seg[choiceAt] = null;
      else { seg[choiceAt] = "@choice:"; markAdd(choiceAt, opts); }
    } else if (model.newOptions.length) {
      // 没有原 @choice 时插在 @end 之前（插到最后一行之后会让选项永远到不了）
      var optAnchor = firstEnd >= 0 ? firstEnd - 1 : seg.length - 1;
      markAdd(optAnchor, ["@choice:"].concat(model.newOptions.map(function (o) { return "  > " + o.text + " -> " + (o.target || "start"); })));
    }

    var jumpLine = -1, endLine = -1;
    for (var j = 0; j < seg.length; j++) {
      if (seg[j] === null) continue;
      if (/^@jump\s+/.test(seg[j])) jumpLine = j;
      if (/^@end\b/.test(seg[j])) endLine = j;
    }
    if (model.newJump) {
      if (jumpLine >= 0) seg[jumpLine] = "@jump " + model.newJump;
      else markAdd(endLine >= 0 ? endLine - 1 : seg.length - 1, ["@jump " + model.newJump]);
    } else if (jumpLine >= 0) seg[jumpLine] = null;

    var outSeg = [];
    for (var z = 0; z < seg.length; z++) {
      if (seg[z] !== null) outSeg.push(seg[z]);
      if (insertAfter[z]) outSeg.push.apply(outSeg, insertAfter[z]);
    }
    if (insertAfter[-1]) outSeg = insertAfter[-1].concat(outSeg);
    var newText = lines.slice(0, sc.start).concat(outSeg, lines.slice(sc.end)).join("\n");
    if (E.setText) E.setText(newText);
    try { var b = $("btnSave"); if (b) b.click(); } catch (e) {}
    toast("场景「" + scenes[curIdx].name + "」已应用到编辑器，正在保存…");
    refresh();
  }

  function open() {
    page.classList.add("open"); fit();
    if (!window.__characterLib) {
      fetch("/api/characters", { cache: "no-store" }).then(function (r) { return r.json(); })
        .then(function (d) { window.__characterLib = (d && d.data) || { characters: [] }; refresh(); })
        .catch(function () { refresh(); });
    } else refresh();
    schedulePaint();   // 布局稳定后再按真实视口高度补一次
  }
  function close() { page.classList.remove("open"); }
  window.__openSceneEditor = open;
  $("sceneClose").addEventListener("click", close);
  function applyText(newText, msg) {
    if (E.setText) E.setText(newText);
    try { var b = $("btnSave"); if (b) b.click(); } catch (e) {}
    toast(msg);
    refresh();
  }
  function insertScene(newName, mode) {
    var text = getText();
    if (!text) { toast("没有打开的剧本"); return; }
    if (!/^\S+$/.test(newName)) { toast("场景名不能有空格", true); return; }
    var lines = text.split("\n");
    var sc = scenes[curIdx];
    var newLabel = "@label " + newName;
    var block, at;
    if (mode === "copy" && sc) {
      // 复制整幕时丢掉 @character（全局注册，复制会重复定义）
      block = lines.slice(sc.start, sc.end).filter(function (l) { return !/^@character\s+/.test(l); });
      block[0] = newLabel;
      block.push("");
      at = sc.end;
    } else {
      block = ["", newLabel, "@end", ""];
      at = lines.length;
    }
    var out = lines.slice(0, at).concat(block, lines.slice(at)).join("\n");
    applyText(out, mode === "copy" ? ("已复制为「" + newName + "」") : ("已新建场景「" + newName + "」"));
    var idx = parseScenes(out).findIndex(function (x) { return x.name === newName; });
    if (idx >= 0) selectScene(idx);
  }
  function addScene() {
    var name = prompt("新场景名（label，不能有空格）：", "新场景" + (scenes.length + 1));
    if (name) insertScene(name.trim(), "add");
  }
  function copyScene() {
    if (curIdx < 0) return;
    if (scenes[curIdx].head) { toast("「开场设置」是文件头（角色注册等），不能整段复制", true); return; }
    var name = prompt("复制「" + scenes[curIdx].name + "」为（新 label）：", scenes[curIdx].name + "_副本");
    if (name) insertScene(name.trim(), "copy");
  }
  function delScene() {
    if (curIdx < 0) return;
    var sc = scenes[curIdx];
    var text = getText();
    var refs = [];
    text.split("\n").forEach(function (l, i) {
      var mj = l.match(/^@jump\s+(\S+)/);
      var mo = l.match(/^\s*>\s*.+?->\s*(\S+)\s*$/);
      if ((mj && mj[1] === sc.name) || (mo && mo[1] === sc.name)) refs.push(i + 1);
    });
    if (refs.length && !confirm("有 " + refs.length + " 处 @jump/选项指向「" + sc.name + "」（第 " + refs.join("、") + " 行），删除后这些跳转会失效。仍然删除？")) return;
    var lines = text.split("\n");
    var out = lines.slice(0, sc.start).concat(lines.slice(sc.end)).join("\n");
    applyText(out, "已删除场景「" + sc.name + "」");
    curIdx = Math.max(0, Math.min(curIdx, parseScenes(out).length - 1));
    refresh();
  }
  // ==================== 右键菜单：复制/粘贴一幕、查看属性、剪贴板 ====================
  // 用户要求：右键别再被忽视——场景列表与源码区都有菜单，复制文字/整幕、看属性都走这里。
  var ctxEl = null;
  var sceneClip = null;
  try { sceneClip = JSON.parse(localStorage.getItem("gal_scene_clip") || "null"); } catch (e) { sceneClip = null; }

  function closeCtx() {
    if (ctxEl && ctxEl.parentNode) ctxEl.parentNode.removeChild(ctxEl);
    ctxEl = null;
  }

  function showCtx(x, y, items) {
    closeCtx();
    var el = document.createElement("div");
    ctxEl = el;   // 必须记下来，否则 closeCtx/点击/Esc 都删不掉旧菜单（会叠成一摞）
    el.className = "scene-ctx";
    items.forEach(function (it) {
      if (it.sep) {
        var sp = document.createElement("div");
        sp.className = "scene-ctx-sep";
        el.appendChild(sp);
        return;
      }
      var b = document.createElement("button");
      b.type = "button";
      b.textContent = it.label;
      if (it.danger) b.className = "danger";
      b.disabled = !!it.disabled;
      b.addEventListener("click", function (ev) {
        ev.stopPropagation();
        closeCtx();
        try { it.run(); } catch (err) { toast("操作失败：" + err, true); }
      });
      el.appendChild(b);
    });
    document.body.appendChild(el);
    var r = el.getBoundingClientRect();
    el.style.left = Math.max(6, Math.min(x, window.innerWidth - r.width - 8)) + "px";
    el.style.top = Math.max(6, Math.min(y, window.innerHeight - r.height - 8)) + "px";
  }

  document.addEventListener("click", closeCtx);
  document.addEventListener("keydown", function (ev) { if (ev.key === "Escape") closeCtx(); });
  window.addEventListener("resize", closeCtx);

  function uniqueLabel(base) {
    var used = scenes.map(function (s) { return s.name; });
    var name = base, n = 2;
    while (used.indexOf(name) >= 0) { name = base + n; n += 1; }
    return name;
  }

  function copySceneAt(i) {
    var text = getText();
    var sc = scenes[i];
    if (!sc) return;
    if (sc.head) {
      // 「开场设置」是第一个 @label 之前的文件头（@character/@bg/@set…），
      // 复制成新幕会把 @character 重复定义，直接拒绝并说明。
      toast("「开场设置」是文件头（角色注册等），不能整段复制；请复制具体的一幕", true);
      return;
    }
    var block = text.split("\n").slice(sc.start, sc.end);
    sceneClip = { name: sc.name, lines: block };
    try { localStorage.setItem("gal_scene_clip", JSON.stringify(sceneClip)); } catch (e) {}
    toast("已复制场景「" + sc.name + "」，右键可粘贴");
  }

  function pasteSceneAfter(i) {
    if (!sceneClip || !sceneClip.lines || !sceneClip.lines.length) { toast("剪贴板里没有场景", true); return; }
    var text = getText();
    var lines = text.split("\n");
    var at = (i >= 0 && scenes[i]) ? scenes[i].end : lines.length;
    var newName = uniqueLabel((sceneClip.name || "场景") + "_副本");
    // 角色注册（@character）是全局的：复制进来的那份会触发「重复定义」，
    // 原文件里已经有了，粘贴时直接丢掉这几行。
    var block = sceneClip.lines.filter(function (l) { return !/^@character\s+/.test(l); });
    var labelAt = -1;
    for (var k = 0; k < block.length; k++) {
      if (/^@label\s+\S+/.test(block[k])) { labelAt = k; break; }
    }
    if (labelAt >= 0) block[labelAt] = "@label " + newName;
    else block.unshift("@label " + newName);
    if (block[block.length - 1].trim() !== "") block.push("");
    var out = lines.slice(0, at).concat(block, lines.slice(at)).join("\n");
    applyText(out, "已粘贴为「" + newName + "」");
    var idx = parseScenes(out).findIndex(function (x) { return x.name === newName; });
    if (idx >= 0) selectScene(idx);
  }

  listEl.addEventListener("contextmenu", function (ev) {
    ev.preventDefault();
    ev.stopPropagation();
    var item = ev.target.closest ? ev.target.closest(".scene-item") : null;
    var i = item ? parseInt(item.getAttribute("data-i"), 10) : -1;
    if (isNaN(i)) i = -1;
    if (i >= 0) selectScene(i);
    var canCopy = i >= 0 && scenes[i] && !scenes[i].head;   // 文件头（开场设置）不能整段复制
    showCtx(ev.clientX, ev.clientY, [
      { label: "查看这一幕的属性", disabled: i < 0, run: function () {
        if (i < 0) return;
        selectScene(i);
        formEl.scrollTop = 0;
        toast("右侧就是这一幕的属性");
      } },
      { sep: true },
      { label: "复制这一幕", disabled: !canCopy, run: function () { copySceneAt(i); } },
      { label: "粘贴到这一幕下面", disabled: !sceneClip, run: function () { pasteSceneAfter(i); } },
      { sep: true },
      { label: "删除这一幕", disabled: i < 0, danger: true, run: delScene },
      { label: "新建场景（文件末尾）", run: addScene }
    ]);
  });

  // 源码区右键：复制/剪切/粘贴/全选 + 复制所在幕 / 查看所在幕属性
  var srcEl = $("source");
  function sceneAtCursor() {
    if (!srcEl) return -1;
    var line = srcEl.value.slice(0, srcEl.selectionStart).split("\n").length - 1;
    var now = parseScenes(srcEl.value);
    for (var k = 0; k < now.length; k++) {
      if (line >= now[k].start && line < now[k].end) return k;
    }
    return -1;
  }
  function fireInput() {
    try { srcEl.dispatchEvent(new Event("input", { bubbles: true })); } catch (e) {}
  }
  function copySelection() {
    var txt = srcEl.value.slice(srcEl.selectionStart, srcEl.selectionEnd);
    if (!txt) return;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(txt).then(function () { toast("已复制"); })
        .catch(function () { toast("复制失败，请按 Ctrl+C", true); });
    } else {
      try { document.execCommand("copy"); toast("已复制"); } catch (e) { toast("复制失败，请按 Ctrl+C", true); }
    }
  }
  function pasteIntoSource() {
    if (!navigator.clipboard || !navigator.clipboard.readText) { toast("请按 Ctrl+V 粘贴（浏览器限制）", true); return; }
    navigator.clipboard.readText().then(function (txt) {
      if (!txt) return;
      srcEl.setRangeText(txt, srcEl.selectionStart, srcEl.selectionEnd, "end");
      fireInput();
      toast("已粘贴");
    }).catch(function () { toast("请按 Ctrl+V 粘贴（浏览器限制）", true); });
  }
  if (srcEl) {
    srcEl.addEventListener("contextmenu", function (ev) {
      ev.preventDefault();
      ev.stopPropagation();
      var hasSel = srcEl.selectionStart !== srcEl.selectionEnd;
      var idx = sceneAtCursor();
      showCtx(ev.clientX, ev.clientY, [
        { label: "复制", disabled: !hasSel, run: copySelection },
        { label: "剪切", disabled: !hasSel, run: function () {
          copySelection();
          srcEl.setRangeText("", srcEl.selectionStart, srcEl.selectionEnd, "end");
          fireInput();
        } },
        { label: "粘贴", run: pasteIntoSource },
        { label: "全选", run: function () { srcEl.focus(); srcEl.select(); } },
        { sep: true },
        { label: "复制所在幕", disabled: idx < 0, run: function () {
          refresh();
          copySceneAt(idx);
        } },
        { label: "查看所在幕属性", disabled: idx < 0, run: function () {
          if (window.__openSceneEditor) window.__openSceneEditor();
          refresh();
          selectScene(idx);
        } }
      ]);
    });
  }

  $("sceneAdd").addEventListener("click", addScene);
  $("sceneCopy").addEventListener("click", copyScene);
  $("sceneDel").addEventListener("click", delScene);
  $("sceneFilter").addEventListener("change", function () { sceneFilter = this.value; renderList(); });
  sceneSearch.addEventListener("input", function () { renderList(); });
  listEl.addEventListener("scroll", function () { closeCtx(); schedulePaint(); });
  $("sceneRefresh").addEventListener("click", function () { refresh(); toast("已重新读取剧本"); });
  $("sceneSave").addEventListener("click", saveCurrent);
  listEl.addEventListener("click", function (ev) {
    var chEl = ev.target.closest ? ev.target.closest(".scene-chapter") : null;
    if (chEl) {
      var ck = chEl.getAttribute("data-ch") || "(未分章)";
      if (collapsedChapters[ck]) delete collapsedChapters[ck]; else collapsedChapters[ck] = 1;
      saveCollapsed();
      renderList();
      return;
    }
    var it = ev.target.closest ? ev.target.closest(".scene-item") : null;
    if (!it) return;
    selectScene(parseInt(it.getAttribute("data-i"), 10));
  });
  document.addEventListener("keydown", function (ev) {
    if (ev.key === "Escape" && page.classList.contains("open")) { close(); ev.preventDefault(); ev.stopPropagation(); }
  }, true);
  window.addEventListener("resize", function () { if (page.classList.contains("open")) { fit(); schedulePaint(); } });

  try {
    var bar = document.querySelector(".editor-toolbar");
    if (bar) {
      var b = document.createElement("button");
      b.type = "button"; b.className = "tb-btn"; b.id = "btnSceneView";
      b.title = "场景编辑：不写代码，可视化改背景/角色/台词";
      b.innerHTML = '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3.5" y="4.5" width="17" height="15" rx="2"/><path d="M3.5 9.5h17M8 4.5v15"/></svg><span class="tb-txt">场景</span>';
      b.addEventListener("click", open);
      bar.insertBefore(b, bar.firstChild);
    }
  } catch (e) {}
})();
