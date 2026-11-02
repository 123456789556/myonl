(() => {
  const $ = (id) => document.getElementById(id);
  const source = $("source");
  const lineNumbers = $("lineNumbers");
  const sourceWrap = $("sourceWrap");
  const statusEl = $("status");
  const filePathEl = $("filePath");
  const previewWrap = $("previewWrap");
  const previewBar = $("previewBar");
  const jsonView = $("jsonView");
  const cardView = $("cardView");
  const errorOverlay = $("errorOverlay");
  const autocomplete = $("autocomplete");
  const btnRun = $("btnRun");

  let debounceTimer = null;
  let lastError = null;

  // ---- P17 协同钩子：内容/光标变化广播（editor_pro.js 订阅）----
  const _changeFns = [];
  const _cursorFns = [];
  function _emitChange() { _changeFns.forEach(f => { try { f(); } catch (e) {} }); }
  function _emitCursor() {
    const line = source.value.slice(0, source.selectionStart).split("\n").length;
    _cursorFns.forEach(f => { try { f(line); } catch (e) {} });
  }

  // ---- E-2：撤销/重做历史栈（覆盖原生打字 + 卡片/拖拽/补全等程序化修改）----
  const _hist = { stack: [], idx: -1, typingTimer: null, max: 500 };
  function _histSnap() {
    return { v: source.value, s: source.selectionStart, e: source.selectionEnd };
  }
  function _histPush() {
    const cur = _histSnap();
    const top = _hist.stack[_hist.idx];
    if (top && top.v === cur.v && top.s === cur.s && top.e === cur.e) return;
    _hist.stack = _hist.stack.slice(0, _hist.idx + 1);
    _hist.stack.push(cur);
    if (_hist.stack.length > _hist.max) { _hist.stack.shift(); } else { _hist.idx++; }
  }
  function _histApply(snap) {
    source.value = snap.v;
    source.selectionStart = snap.s;
    source.selectionEnd = snap.e;
    source.dispatchEvent(new Event("input"));   // 派发 input：让 editor_pro.js 同步缓冲/脏标记
    _emitChange();
  }
  function undo() {
    clearTimeout(_hist.typingTimer);
    const top = _hist.stack[_hist.idx];
    if (!top || source.value !== top.v) _histPush();   // 打字中途先把当前压栈
    if (_hist.idx <= 0) return;
    _hist.idx--;
    _histApply(_hist.stack[_hist.idx]);
  }
  function redo() {
    clearTimeout(_hist.typingTimer);
    if (_hist.idx >= _hist.stack.length - 1) return;
    _hist.idx++;
    _histApply(_hist.stack[_hist.idx]);
  }
  // 程序化修改专用：压"修改前"→设值→压"修改后"，调用方自行 updateLineNumbers/scheduleCheck
  function setSourceValue(v, selStart, selEnd) {
    clearTimeout(_hist.typingTimer);
    _histPush();
    source.value = v;
    if (selStart != null) source.selectionStart = selStart;
    if (selEnd != null) source.selectionEnd = selEnd;
    _histPush();
  }
  // 文件加载/切换：不进撤销栈，直接重置历史
  function resetHistory() {
    _hist.stack = [_histSnap()];
    _hist.idx = 0;
    clearTimeout(_hist.typingTimer);
  }
  // 打字停顿 400ms 后压一次快照（一段连续输入 = 一个撤销步）
  source.addEventListener("input", () => {
    clearTimeout(_hist.typingTimer);
    _hist.typingTimer = setTimeout(_histPush, 400);
  });
  resetHistory();

  // ---- M1.5：Trae/VSCode 式面包屑（工程 › 文件 › 当前 @label） ----
  const breadcrumbEl = $("breadcrumb");
  function _bcProjectName() {
    try {
      const rootPath = (editorCfg && editorCfg.project_root) || "";
      const parts = String(rootPath).replace(/[\\/]+$/, "").split(/[\\/]/).filter(Boolean);
      return parts.length ? parts[parts.length - 1] : "工程";
    } catch (e) {
      return "工程";
    }
  }
  function updateBreadcrumb() {
    if (!breadcrumbEl) return;
    const items = [{ t: _bcProjectName(), cls: "dim" }];
    let rel = "";
    try {
      rel = (window.__proCurPath && window.__proCurPath()) || (filePathEl && filePathEl.textContent) || "";
    } catch (e) {}
    rel = String(rel || "").trim();
    items.push({ t: rel || "script.gal", cls: "cur" });
    const upTo = source.value.slice(0, source.selectionStart);
    const labels = upTo.match(/@label\s+([^\s#]+)/g);
    if (labels && labels.length) {
      items.push({ t: labels[labels.length - 1].replace(/@label\s+/, ""), cls: "label" });
    }
    breadcrumbEl.innerHTML = items.map((it, i) =>
      '<span class="bc-item ' + it.cls + '">' + escapeText(it.t) + "</span>" +
      (i < items.length - 1 ? '<span class="bc-sep">›</span>' : "")
    ).join("");
  }

  // ---- 行号 ----
  function updateLineNumbers() {
    const arr = source.value.split("\n");
    let html = "";
    for (let i = 1; i <= arr.length; i++) {
      let cls = (lastError && lastError.line === i) ? 'ln err' : 'ln';
      if (/^@include\s+\S+/.test(arr[i - 1].trim())) cls += ' inc';  // @include 行号可点跳
      html += `<div class="${cls}" data-line="${i}">${i}</div>`;
    }
    lineNumbers.innerHTML = html;
    markCurrentLine(cursorLineIndex());
    updateBreadcrumb();
  }
  source.addEventListener("input", updateLineNumbers);
  source.addEventListener("scroll", () => {
    lineNumbers.scrollTop = source.scrollTop;
  });

  // ---- tab 切换 ----
  function switchTab(name) {
    document.querySelectorAll(".tab").forEach(t => {
      t.classList.toggle("active", t.dataset.tab === name);
    });
    const isSource = name === "source";
    sourceWrap.style.display = isSource ? "" : "none";
    source.style.display = isSource ? "" : "none";
    lineNumbers.style.display = isSource ? "" : "none";
    jsonView.classList.toggle("active", name === "json");
    cardView.classList.toggle("active", name === "card");
    if (name === "card") {
      enterCardView();
    }
  }
  document.querySelectorAll(".tab").forEach(tab => {
    tab.addEventListener("click", () => switchTab(tab.dataset.tab));
  });

  // ---- 状态 ----
  function setStatus(ok, msg) {
    statusEl.textContent = msg;
    statusEl.className = "status " + (ok ? "ok" : "err");
  }
  // P43：后续流程（LetsGal 式）——从剧本解析 @label 与选项跳转目标
  function updateFlowNext(text) {
    const labels = [];
    const reLabel = /@label\s+([^\s#]+)/g;
    let m;
    while ((m = reLabel.exec(text)) !== null) labels.push(m[1]);
    const targets = [];
    const reChoice = /-\s*>\s*([^\s#]+)/g;
    while ((m = reChoice.exec(text)) !== null && targets.length < 8) targets.push(m[1]);
    const box = $("flowNextTargets");
    if (!box) return;
    const items = [...labels.map(l => ({t: l, kind: "label"})), ...targets.map(t => ({t, kind: "goto"}))];
    box.innerHTML = items.length
      ? items.map(i => `<span class="tgt">${i.kind === "label" ? "⚑ " : "→ "}${i.t}</span>`).join("")
      : "本章无跳转目标";
  }
  let _pulseTimer = null;
  function setPreviewBar(ok, msg) {
    const st = $("previewState");
    if (st) st.textContent = msg;
    previewBar.className = "preview-bar" + (ok ? "" : " err");
    // M1.5：保存/预览成功的轻微正反馈（0.6s 脉冲；不弹窗、可被 CSS 关闭）
    if (ok && /已保存|已更新|解析成功/.test(String(msg || ""))) {
      previewBar.classList.remove("pulse");
      void previewBar.offsetWidth;   // 重启动画
      previewBar.classList.add("pulse");
      clearTimeout(_pulseTimer);
      _pulseTimer = setTimeout(() => previewBar.classList.remove("pulse"), 700);
    }
  }

  // ---- 高亮错误行 ----
  function highlightError(line) {
    if (!line) {
      errorOverlay.style.display = "none";
      return;
    }
    const lineHeight = 1.6 * 14; // line-height * font-size
    const top = source.offsetTop + (line - 1) * lineHeight - source.scrollTop;
    errorOverlay.style.display = "block";
    errorOverlay.style.left = lineNumbers.offsetWidth + "px";
    errorOverlay.style.width = (source.offsetWidth - lineNumbers.offsetWidth) + "px";
    errorOverlay.style.top = top + "px";
    errorOverlay.style.height = lineHeight + "px";
    // 滚动到错误行
    source.focus();
    source.scrollTop = (line - 1) * lineHeight;
  }
  source.addEventListener("scroll", () => { if (lastError) highlightError(lastError.line); });
  window.addEventListener("resize", () => { if (lastError) highlightError(lastError.line); });

  // ---- D1：底部 Dock 面板体系（问题 / 输出 / 运行日志）----
  const problemsPanel = $("problemsPanel");
  const problemsList = $("problemsList");
  const dockBadge = $("dockProblemBadge");
  const dockOutput = $("dockOutput");
  const dockRun = $("dockRun");
  const actProblemBadge = $("actProblemBadge");   // D2：活动栏「问题数」红徽标
  const actDirtyDot = $("actDirtyDot");           // D2：活动栏「未保存」黄点
  const actImportSpin = $("actImportSpin");       // D2：素材导入中转圈
  const DOCK_H_KEY = "moyul_dock_h";
  const DOCK_MAX_LINES = 500;
  let dockPane = "problems";     // 当前激活 tab
  let dockOpen = false;          // 面板显隐
  let lastProblemCount = 0;      // 问题数 0→N 跳变才自动弹出（手动关后不反复弹）

  function escapeText(t) {
    return String(t).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  function jumpToLine(line) {
    const lines = source.value.split("\n");
    const n = Math.max(1, Math.min(Number(line) || 1, lines.length));
    let pos = 0;
    for (let i = 0; i < n - 1; i++) pos += lines[i].length + 1;
    source.focus();
    source.setSelectionRange(pos, pos + (lines[n - 1] || "").length);
    source.scrollTop = Math.max(0, (n - 4) * 22);
    highlightError(n);
  }

  function dockActivate(pane) {
    dockPane = pane;
    document.querySelectorAll("#dockTabs .dock-tab").forEach(function (t) {
      t.classList.toggle("active", t.dataset.pane === pane);
    });
    problemsPanel.querySelectorAll(".dock-pane").forEach(function (p) {
      p.classList.toggle("hidden", p.dataset.pane !== pane);
    });
    $("dockView").classList.toggle("hidden", pane !== "problems");   // A2：视图切换只在问题页出现
    const cur = problemsPanel.querySelector('.dock-pane[data-pane="' + pane + '"]');
    if (cur) cur.scrollTop = cur.scrollHeight;
  }

  function dockShow(open, pane) {
    dockOpen = !!open;
    problemsPanel.classList.toggle("hidden", !dockOpen);
    if (dockOpen && pane) dockActivate(pane);
  }
  window.__dockToggle = function () { dockShow(!dockOpen); };

  // 轻量日志 API：输出 / 运行日志共用（时间戳 + 文本行，500 行上限滚动）
  function dockLog(channel, msg) {
    const el = channel === "run" ? dockRun : dockOutput;
    if (!el) return;
    const d = new Date();
    const pad = function (v) { return ("0" + v).slice(-2); };
    const line = document.createElement("div");
    line.className = "dock-line";
    line.innerHTML = '<span class="dock-ts">' + pad(d.getHours()) + ":" + pad(d.getMinutes()) + ":" + pad(d.getSeconds()) +
      '</span><span class="dock-msg">' + escapeText(msg) + "</span>";
    el.appendChild(line);
    while (el.children.length > DOCK_MAX_LINES) el.removeChild(el.firstChild);
    if (dockOpen && dockPane === (channel === "run" ? "run" : "output")) el.scrollTop = el.scrollHeight;
  }
  window.dockLog = dockLog;

  // ---- A2：问题面板「简单 / 详细」两视图（详细含指令原文与建议，可复制）----
  let problemItems = [];
  let problemView = "simple";
  try {
    const savedView = localStorage.getItem("moyul_problem_view");
    if (savedView === "detail") problemView = "detail";
  } catch (e) {}

  function sourceLineText(lineNo) {
    const lines = source.value.split("\n");
    const n = Number(lineNo) || 0;
    return n > 0 && n <= lines.length ? lines[n - 1] : "";
  }

  function problemText(it) {
    let out = (it.detail || it.message || "语法错误");
    const raw = sourceLineText(it.line);
    if (raw) out += "\n指令原文：" + raw;
    if (it.hint) out += "\n建议：" + it.hint;
    return out;
  }

  function copyProblem(it) {
    const done = function () { toast("已复制问题详情"); };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(problemText(it)).then(done, function () { toast("复制失败，请手动选中", true); });
      return;
    }
    try {
      const ta = document.createElement("textarea");
      ta.value = problemText(it);
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      ta.remove();
      done();
    } catch (e) { toast("复制失败，请手动选中", true); }
  }

  function renderProblemRows() {
    problemsList.innerHTML = "";
    problemItems.forEach(function (it) {
      const row = document.createElement("div");
      row.className = "problem-row" + (problemView === "detail" ? " detail" : "");
      const summary = escapeText(it.summary || it.message || "语法错误");
      if (problemView === "simple") {
        row.innerHTML = '<span class="problem-line">第 ' + (Number(it.line) || "?") + ' 行</span>' +
          '<span class="problem-msg">' + summary + "</span>";
        row.addEventListener("click", function () { jumpToLine(it.line); });
      } else {
        const raw = escapeText(sourceLineText(it.line));
        row.innerHTML =
          '<div class="pd-head"><span class="problem-line">第 ' + (Number(it.line) || "?") + ' 行</span>' +
          '<span class="problem-msg">' + summary + "</span>" +
          '<button type="button" class="icon-btn pd-copy" title="Copy · 复制问题详情">复制</button></div>' +
          (raw ? '<div class="pd-raw">指令原文：' + raw + "</div>" : "") +
          (it.hint ? '<div class="pd-hint">建议：' + escapeText(it.hint) + "</div>" : "");
        // 详细视图：点行号区跳转，点「复制」只复制
        row.querySelector(".pd-copy").addEventListener("click", function (ev) {
          ev.stopPropagation();
          copyProblem(it);
        });
        row.querySelector(".pd-head").addEventListener("click", function () { jumpToLine(it.line); });
      }
      problemsList.appendChild(row);
    });
  }

  function setProblemView(view) {
    problemView = view === "detail" ? "detail" : "simple";
    document.querySelectorAll("#dockView .dock-seg").forEach(function (b) {
      b.classList.toggle("active", b.dataset.view === problemView);
    });
    try { localStorage.setItem("moyul_problem_view", problemView); } catch (e) {}
    renderProblemRows();
  }

  $("dockView").addEventListener("click", function (ev) {
    const seg = ev.target.closest(".dock-seg");
    if (seg) setProblemView(seg.dataset.view);
  });
  setProblemView(problemView);   // 恢复上次视图偏好（记忆 localStorage）

  // ---- D2：活动栏徽标（问题数 / 未保存 / 素材导入中）----
  // editor_pro.js 在脏状态变化时回调（该脚本先于本文件定义，调用时已可用）
  window.__actSetDirty = function (dirty) {
    if (actDirtyDot) actDirtyDot.classList.toggle("hidden", !dirty);
  };
  function setActImporting(on) {
    if (actImportSpin) actImportSpin.classList.toggle("hidden", !on);
  }

  function renderProblems(items) {
    const n = items && items.length ? items.length : 0;
    const sbp = $("sbProblems");
    if (sbp) { sbp.textContent = "⚠ " + n; sbp.className = n ? "sb-item warn" : "sb-item"; }
    dockBadge.textContent = n;
    dockBadge.classList.toggle("hidden", !n);
    actProblemBadge.textContent = n;
    actProblemBadge.classList.toggle("hidden", !n);
    problemItems = (items || []).slice();
    renderProblemRows();
    // 问题数 0→N 跳变时自动弹出并切到问题 tab；手动关闭期间不反复弹
    if (n > 0 && lastProblemCount === 0) dockShow(true, "problems");
    lastProblemCount = n;
  }

  // dock tab 切换 / 清空 / 关闭
  $("dockTabs").addEventListener("click", function (ev) {
    const tab = ev.target.closest(".dock-tab");
    if (tab) dockActivate(tab.dataset.pane);
  });
  $("dockClear").addEventListener("click", function () {
    const cur = problemsPanel.querySelector('.dock-pane[data-pane="' + dockPane + '"]');
    if (cur) cur.innerHTML = "";
  });
  $("dockClose").addEventListener("click", function () { dockShow(false); });

  // 顶部拖拽把手：120px ~ 60vh，记忆 localStorage
  function applyDockHeight(h) {
    problemsPanel.style.height = Math.max(120, Math.min(h, window.innerHeight * 0.6)) + "px";
  }
  try {
    const savedH = parseInt(localStorage.getItem(DOCK_H_KEY), 10);
    if (savedH) applyDockHeight(savedH);
  } catch (e) {}
  let dockDrag = null;
  $("dockResize").addEventListener("mousedown", function (ev) {
    dockDrag = { y: ev.clientY, h: problemsPanel.getBoundingClientRect().height };
    ev.preventDefault();
  });
  window.addEventListener("mousemove", function (ev) {
    if (dockDrag) applyDockHeight(dockDrag.h + (dockDrag.y - ev.clientY));
  });
  window.addEventListener("mouseup", function () {
    if (!dockDrag) return;
    dockDrag = null;
    try { localStorage.setItem(DOCK_H_KEY, String(parseInt(problemsPanel.style.height, 10) || 0)); } catch (e) {}
  });

  // inspector / timeline 分区折叠（VSCode 式，记忆不落盘）
  const inspectorEl = $("inspector");
  $("inspectorToggle").addEventListener("click", function () {
    const collapsed = inspectorEl.classList.toggle("collapsed");
    $("inspectorToggle").textContent = collapsed ? "+" : "−";
  });
  const timelineEl = $("timeline");
  timelineEl.addEventListener("click", function (ev) {
    if (ev.target && ev.target.classList && ev.target.classList.contains("tl-title")) {
      timelineEl.classList.toggle("collapsed");
    }
  });

  // 多标签切换/打开文件时同步面包屑
  if (window.MutationObserver && $("editorTabs")) {
    new MutationObserver(updateBreadcrumb).observe($("editorTabs"), {
      childList: true, subtree: true, attributes: true,
    });
  }

  const sbProblemsEl = $("sbProblems");
  if (sbProblemsEl) {
    sbProblemsEl.addEventListener("click", function () {
      if (!problemsList.children.length) return;
      dockShow(true, "problems");
    });
  }

  // ---- 语法检查 + 预览（防抖 500ms）----
  function scheduleCheck() {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => { checkAndPreview(); }, 500);
  }

  async function checkAndPreview() {
    const text = source.value;
    const curPath = (window.__proCurPath && window.__proCurPath()) || undefined;
    if (!text.trim()) {
      setStatus(true, "空剧本");
      previewWrap.innerHTML = '<div class="preview-placeholder">输入剧本后自动预览</div>';
      setPreviewBar(true, "就绪");
      updateFlowNext("");   // 空剧本也要清掉上一文件的后续流程残留
      updateMissingBar();   // 同步清掉上一文件的缺素材条
      lastError = null;
      highlightError(null);
      renderProblems([]);
      updateLineNumbers();
      _emitChange();
      return;
    }
    // 语法检查
    let checkResp;
    try {
      checkResp = await fetch("/api/check", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({text, path: curPath}),
      }).then(r => r.json());
    } catch (e) {
      setStatus(false, "检查请求失败");
      return;
    }
    if (!checkResp.ok) {
      lastError = {line: checkResp.line, file: checkResp.file, message: checkResp.message};
      setStatus(false, `语法错误 · 第 ${checkResp.line} 行`);
      setPreviewBar(false, `解析失败：${checkResp.file} 第 ${checkResp.line} 行：${checkResp.message}`);
      highlightError(checkResp.line);
      renderProblems([{
        line: checkResp.line,
        summary: checkResp.summary || checkResp.message,
        detail: checkResp.detail || "",
        hint: checkResp.hint || "",
        message: checkResp.message || "语法错误",
      }]);
      updateLineNumbers();
      return;
    }
    lastError = null;
    setStatus(true, `语法检查通过 · ${checkResp.count} 条指令`);
    highlightError(null);
    renderProblems([]);
    updateLineNumbers();
    updateFlowNext(text);
    _emitChange();
    updateMissingBar();  // 缺素材红字随剧本实时更新
    // 更新 JSON 视图
    try {
      const jsonResp = await fetch("/api/check", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({text, path: curPath}),
      }).then(r => r.json());
      if (jsonResp.ok) jsonView.textContent = JSON.stringify(jsonResp.instructions || jsonResp, null, 2);
    } catch (e) {}
    // 预览（T4：editor_pro.js 把请求改写成「锚定 @label start / 光标台词」的小剧本）
    try {
      const blob = await fetch("/api/preview", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({text, frames: 30, path: curPath}),
      }).then(async r => {
        if (r.status === 422) {
          const err = await r.json();
          setPreviewBar(false, `解析失败：${err.file} 第 ${err.line} 行：${err.message}`);
          return null;
        }
        return r.blob();
      });
      if (blob) {
        const url = URL.createObjectURL(blob);
        previewWrap.innerHTML = `<img src="${url}" alt="预览">`;
        setPreviewBar(true, "解析成功 · 实时预览");
        pushPreviewHistory(url, curPath);
      }
    } catch (e) {
      setPreviewBar(false, "预览请求失败：" + e);
    }
  }

  source.addEventListener("input", () => {
    updateLineNumbers();
    hideAutocomplete();
    scheduleCheck();
  });
  source.addEventListener("click", _emitCursor);
  source.addEventListener("keyup", _emitCursor);

  // ===== P20 属性检查器：点源码行 → 表单改参数 → 源码/预览实时同步 =====
  let inspIdx = -1;
  let inspStamp = "";
  let inspSuppress = false;

  function cursorLineIndex() {
    const before = source.value.slice(0, source.selectionStart);
    return before.split("\n").length - 1;
  }
  function markCurrentLine(idx) {
    lineNumbers.querySelectorAll(".ln.cur").forEach(e => e.classList.remove("cur"));
    const el = lineNumbers.querySelector('.ln[data-line="' + (idx + 1) + '"]');
    if (el && !el.classList.contains("err")) el.classList.add("cur");
  }
  function lineIndent(s) { return (s.match(/^\s*/) || [""])[0]; }

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  function field(value, ph) {
    const i = document.createElement("input");
    i.value = value || "";
    if (ph) i.placeholder = ph;
    return i;
  }
  function selectField(options, value) {
    const s = document.createElement("select");
    let found = false;
    options.forEach(([v, label]) => {
      const o = document.createElement("option");
      o.value = v; o.textContent = label;
      if (v === value) { o.selected = true; found = true; }
      s.appendChild(o);
    });
    if (value && !found) {
      const o = document.createElement("option");
      o.value = value; o.textContent = value; o.selected = true;
      s.appendChild(o);
    }
    return s;
  }
  function row(label, control) {
    const r = el("div", "insp-row");
    r.appendChild(el("label", "", label));
    r.appendChild(control);
    return r;
  }
  // ---- M1.5：素材晾衣绳（Asset Clothesline）----
  // 交互灵感：Tendedero（MIT）。只借「悬停滑出 + 悬挂卡片 + 点击即用」的想法，未复制其代码/名称/图标。
  // 能力：最近素材 / 置顶常用 / 点击或拖拽插入指令 / 预览历史。
  const clEl = $("clothesline");
  const clItemsEl = $("clItems");
  const clTrigger = $("clTrigger");
  const CL_PIN_KEY = "myonl_cl_pins";
  const CL_PREVIEW_MAX = 6;
  let clHideTimer = null;
  let clTab = "assets";
  let clPreviewHistory = [];
  let clPins = [];
  try {
    const raw = localStorage.getItem(CL_PIN_KEY);
    clPins = raw ? JSON.parse(raw) : [];
    if (!Array.isArray(clPins)) clPins = [];
  } catch (e) { clPins = []; }
  function _clKey(cat, name) { return cat + ":" + name; }
  function _clSavePins() {
    try { localStorage.setItem(CL_PIN_KEY, JSON.stringify(clPins)); } catch (e) {}
  }
  function _clAssetCards() {
    const all = [];
    (assets.images || []).forEach((n) => all.push({ cat: "images", name: n, ins: "@bg " + n }));
    (assets.audio || []).forEach((n) => all.push({ cat: "audio", name: n, ins: "@music " + n }));
    (assets.anims || []).forEach((n) => all.push({ cat: "anims", name: n, ins: "@anim " + n }));
    const pinned = [];
    const rest = [];
    all.forEach((c) => {
      c.key = _clKey(c.cat, c.name);
      c.pinned = clPins.indexOf(c.key) >= 0;
      (c.pinned ? pinned : rest).push(c);
    });
    // 置顶的在前，其余最多凑 6 个；置顶已失效的从存储里清掉
    const validPins = clPins.filter((k) => all.some((c) => c.key === k));
    if (validPins.length !== clPins.length) { clPins = validPins; _clSavePins(); }
    return pinned.concat(rest).slice(0, 8);
  }
  function _clRenderAssets() {
    const cards = _clAssetCards();
    if (!cards.length) {
      clItemsEl.innerHTML = '<div class="cl-empty">还没有素材——把图片/音频拖进编辑器试试</div>';
      return;
    }
    cards.forEach((c) => {
      const card = document.createElement("div");
      card.className = "cl-card cat-" + c.cat + (c.pinned ? " pinned" : "");
      card.title = c.ins + "（点击插入 / 拖到左侧代码区）";
      card.draggable = true;
      const pin = document.createElement("button");
      pin.className = "cl-pin";
      pin.textContent = c.pinned ? "★" : "☆";
      pin.title = c.pinned ? "取消置顶" : "置顶：常用素材钉在绳子最左";
      pin.addEventListener("click", (ev) => {
        ev.stopPropagation();
        if (c.pinned) clPins = clPins.filter((k) => k !== c.key);
        else clPins.push(c.key);
        _clSavePins();
        refreshClothesline();
      });
      const thumb = document.createElement(c.cat === "audio" ? "div" : "img");
      if (c.cat === "audio") {
        thumb.className = "cl-audio";
        thumb.textContent = "♪";
      } else {
        thumb.src = assetURL(c.cat, c.name);
        thumb.alt = c.name;
        thumb.loading = "lazy";
      }
      const nm = document.createElement("div");
      nm.className = "cl-nm";
      nm.textContent = c.name;
      card.appendChild(pin);
      card.appendChild(thumb);
      card.appendChild(nm);
      card.addEventListener("click", () => {
        insertDirective(c.ins);
        hideClothesline();
      });
      card.addEventListener("dragstart", (ev) => {
        try {
          ev.dataTransfer.setData("text/plain", c.ins + "\n");
          ev.dataTransfer.effectAllowed = "copy";
        } catch (e) {}
        card.classList.add("dragging");
      });
      card.addEventListener("dragend", () => card.classList.remove("dragging"));
      clItemsEl.appendChild(card);
    });
  }
  function _clRenderPreviews() {
    if (!clPreviewHistory.length) {
      clItemsEl.innerHTML = '<div class="cl-empty">还没有预览记录——改一句台词，右侧预览成功后会挂在这里</div>';
      return;
    }
    clPreviewHistory.forEach((hst) => {
      const card = document.createElement("div");
      card.className = "cl-card preview";
      card.title = hst.file + " · " + hst.time + "（点击回到这次预览）";
      const img = document.createElement("img");
      img.src = hst.url;
      img.alt = "预览 " + hst.time;
      const nm = document.createElement("div");
      nm.className = "cl-nm";
      nm.textContent = hst.time;
      card.appendChild(img);
      card.appendChild(nm);
      card.addEventListener("click", () => {
        previewWrap.innerHTML = '<img src="' + hst.url + '" alt="历史预览">';
        setPreviewBar(true, "历史预览 · " + hst.file + " · " + hst.time);
        hideClothesline();
      });
      clItemsEl.appendChild(card);
    });
  }
  function refreshClothesline() {
    if (!clItemsEl) return;
    clItemsEl.innerHTML = "";
    if (clTab === "previews") _clRenderPreviews();
    else _clRenderAssets();
  }
  function pushPreviewHistory(url, file) {
    if (!url) return;
    const d = new Date();
    const pad = (n) => (n < 10 ? "0" + n : "" + n);
    const time = pad(d.getHours()) + ":" + pad(d.getMinutes()) + ":" + pad(d.getSeconds());
    clPreviewHistory.unshift({ url: url, file: file || "script.gal", time: time });
    while (clPreviewHistory.length > CL_PREVIEW_MAX) {
      const old = clPreviewHistory.pop();
      try { URL.revokeObjectURL(old.url); } catch (e) {}
    }
    if (clEl && clEl.classList.contains("open") && clTab === "previews") refreshClothesline();
  }
  function showClothesline() {
    clearTimeout(clHideTimer);
    clEl.classList.add("open");
    refreshClothesline();
  }
  function hideClothesline() {
    clEl.classList.remove("open");
  }
  function scheduleHideClothesline() {
    clearTimeout(clHideTimer);
    clHideTimer = setTimeout(hideClothesline, 260);
  }
  if (clTrigger) {
    clTrigger.addEventListener("mouseenter", showClothesline);
    clTrigger.addEventListener("click", () => { clEl.classList.contains("open") ? hideClothesline() : showClothesline(); });
    clTrigger.addEventListener("mouseleave", scheduleHideClothesline);
  }
  if (clEl) {
    clEl.addEventListener("mouseenter", () => clearTimeout(clHideTimer));
    clEl.addEventListener("mouseleave", scheduleHideClothesline);
  }
  document.querySelectorAll(".cl-tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      clTab = tab.dataset.cltab || "assets";
      document.querySelectorAll(".cl-tab").forEach((t) => t.classList.toggle("active", t === tab));
      refreshClothesline();
    });
  });
  // 拖拽到左侧代码区 → 在光标处插入指令
  const leftPaneDrop = document.querySelector(".left-pane");
  function _dropDirective(ev) {
    let text = "";
    try { text = (ev.dataTransfer && ev.dataTransfer.getData("text/plain")) || ""; } catch (e) { text = ""; }
    if (!text) return false;
    ev.preventDefault();
    insertDirective(text.replace(/\s+$/, ""));
    return true;
  }
  if (leftPaneDrop) {
    leftPaneDrop.addEventListener("dragover", (ev) => {
      ev.preventDefault();
      try { ev.dataTransfer.dropEffect = "copy"; } catch (e) {}
      leftPaneDrop.classList.add("drop-ready");
    });
    leftPaneDrop.addEventListener("dragleave", (ev) => {
      if (!leftPaneDrop.contains(ev.relatedTarget)) leftPaneDrop.classList.remove("drop-ready");
    });
    leftPaneDrop.addEventListener("drop", (ev) => {
      leftPaneDrop.classList.remove("drop-ready");
      _dropDirective(ev);
    });
  }
  // ---- A1 检查器候选联想：input + datalist，候选取自素材库缓存（assets）----
  let _dlSeq = 0;
  function charIdList() {
    // 立绘命名约定「角色_表情」，角色 ID 即下划线前缀去重；bg_/cg_ 是背景与 CG，排除
    return [...new Set((assets.images || [])
      .filter(n => n.includes("_") && !/^(bg|cg)_/.test(n))
      .map(n => n.split("_")[0]))];
  }
  function candidateField(body, value, ph, getList) {
    const i = field(value, ph);
    const dl = document.createElement("datalist");
    dl.id = "insp-dl-" + (++_dlSeq);
    i.setAttribute("list", dl.id);
    const refill = () => {
      dl.innerHTML = "";
      (getList() || []).forEach(v => {
        const o = document.createElement("option");
        o.value = v;
        dl.appendChild(o);
      });
    };
    refill();
    // 素材库刷新或联动字段（如角色名）改动后，焦点进来时重取候选
    i.addEventListener("focus", refill);
    body.appendChild(dl);   // 随检查器重绘一起销毁，不泄漏
    return i;
  }
  function appendTag(body, text) {
    body.appendChild(el("div", "insp-tag", text));
  }
  function bindLive(control, apply) {
    let timer = null;
    control.addEventListener("input", () => {
      clearTimeout(timer);
      timer = setTimeout(() => apply(true), 180);
    });
    control.addEventListener("change", () => { clearTimeout(timer); apply(false); });
  }
  function writeLines(lines, keepIdx, quiet, focusSel) {
    setSourceValue(lines.join("\n"));
    // A2：程序化改写也要派发 input，让 editor_pro.js 同步缓冲并刷新脏标记
    source.dispatchEvent(new Event("input", { bubbles: true }));
    updateLineNumbers();
    hideAutocomplete();
    scheduleCheck();
    const line = lines[keepIdx] || "";
    inspIdx = keepIdx;
    inspStamp = keepIdx + "|" + line;
    if (!quiet) {
      const offset = lines.slice(0, keepIdx).reduce((n, l) => n + l.length + 1, 0) + line.length;
      source.focus();
      source.setSelectionRange(offset, offset);
      renderInspector(keepIdx, line);
      if (focusSel) {
        const target = $("inspectorBody").querySelector(focusSel);
        if (target) target.focus();
      }
    }
  }
  function updateInspectorFromCursor() {
    const idx = cursorLineIndex();
    const line = source.value.split("\n")[idx] || "";
    const stamp = idx + "|" + line;
    if (stamp === inspStamp) return;
    inspIdx = idx; inspStamp = stamp;
    markCurrentLine(idx);
    renderInspector(idx, line);
  }

  function renderInspector(idx, line) {
    const body = $("inspectorBody");
    $("inspectorLine").textContent = "第 " + (idx + 1) + " 行";
    body.innerHTML = "";
    const t = (line || "").trim();
    const pad = lineIndent(line || "");
    if (!t) {
      body.innerHTML = '<div class="insp-empty">空行。点击有指令的行来编辑参数。</div>';
      return;
    }
    let m;

    // 对话行：@ 角色 文本
    if ((m = t.match(/^@\s+(\S+)\s+(.*)$/))) {
      appendTag(body, "对话");
      const who = field(m[1], "角色名");
      const said = field(m[2], "台词");
      body.appendChild(row("角色", who));
      body.appendChild(row("台词", said));
      const apply = (quiet) => {
        const lines = source.value.split("\n");
        if (idx < 0 || idx >= lines.length) return;
        lines[idx] = lineIndent(lines[idx]) + "@ " + who.value.trim() + " " + said.value.trim();
        writeLines(lines, idx, quiet);
      };
      bindLive(who, apply);
      bindLive(said, apply);
      return;
    }

    // @bg 图片 + 过渡
    if ((m = t.match(/^@bg\s+(\S+)/))) {
      appendTag(body, "@bg");
      const name = candidateField(body, m[1], "图片名", () => assets.images || []);
      body.appendChild(row("图片名", name));
      const next = source.value.split("\n")[idx + 1] || "";
      let transVal = "";
      const tm = next.trim().match(/^@transition\s+(\S+)(?:\s+(\S+))?\s+(\S+)\s*$/);
      if (tm) transVal = tm[1] === "dissolve" ? ("dissolve " + tm[3]) : (tm[1] + " " + tm[2] + " " + tm[3]);
      const trans = selectField([
        ["", "无过渡（硬切）"],
        ["dissolve 0.5", "溶解 0.5 秒"],
        ["dissolve 1.0", "溶解 1.0 秒"],
        ["wipe 左 0.5", "擦除 左 0.5 秒"],
        ["slide 右 0.5", "滑动 右 0.5 秒"],
      ], transVal);
      body.appendChild(row("过渡", trans));
      const apply = (quiet) => {
        const lines = source.value.split("\n");
        if (idx < 0 || idx >= lines.length) return;
        const p = lineIndent(lines[idx]);
        lines[idx] = p + "@bg " + name.value.trim();
        const has = lines[idx + 1] !== undefined && /^\s*@transition\s+/.test(lines[idx + 1]);
        if (trans.value) {
          const tl = p + "@transition " + trans.value;
          if (has) lines[idx + 1] = tl; else lines.splice(idx + 1, 0, tl);
        } else if (has) {
          lines.splice(idx + 1, 1);
        }
        writeLines(lines, idx, quiet);
      };
      bindLive(name, apply);
      trans.addEventListener("change", () => apply(false));
      return;
    }

    // @choice: 选项列表
    if (/^@choice\s*:/.test(t)) {
      appendTag(body, "@choice");
      const all = source.value.split("\n");
      const labels = (source.value.match(/^@label\s+(\S+)/gm) || []).map(s => s.trim().split(/\s+/)[1]);
      const defTarget = labels[0] || "标签名";
      let end = idx + 1;
      while (end < all.length && all[end].trim().startsWith(">")) end++;
      const parsed = [];
      for (let i = idx + 1; i < end; i++) {
        const om = all[i].trim().slice(1).trim().match(/^(.*?)(?::\s*(.*?))?\s*->\s*(\S+)$/);
        parsed.push(om
          ? {text: om[1].trim(), cond: (om[2] || "").trim(), target: om[3].trim()}
          : {text: all[i].trim().slice(1).trim(), cond: "", target: defTarget});
      }
      const inputs = [];
      const applyChoice = (quiet) => {
        const lines = source.value.split("\n");
        if (idx < 0 || idx >= lines.length) return;
        const p = lineIndent(lines[idx]);
        lines[idx] = p + "@choice:";
        const opts = inputs.map(r => {
          const cond = r.cond.value.trim();
          return p + "    > " + (r.text.value.trim() || "选项")
            + (cond ? ": " + cond : "") + " -> " + (r.target.value.trim() || defTarget);
        });
        let stop = idx + 1;
        while (stop < lines.length && lines[stop].trim().startsWith(">")) stop++;
        lines.splice(idx + 1, stop - (idx + 1), ...opts);
        writeLines(lines, idx, quiet);
      };
      parsed.forEach(o => {
        const holder = el("div", "insp-opt");
        const ti = field(o.text, "选项文本");
        const ci = field(o.cond, "条件（可空）");
        const gi = field(o.target, "跳转标签");
        const del = el("button", "insp-del", "×");
        del.type = "button"; del.title = "删除该选项";
        const obj = {text: ti, cond: ci, target: gi};
        [ti, ci, gi].forEach(i => bindLive(i, applyChoice));
        del.addEventListener("click", () => {
          const at = inputs.indexOf(obj);
          if (at >= 0) inputs.splice(at, 1);
          holder.remove();
          applyChoice(false);
        });
        holder.append(ti, ci, gi, del);
        body.appendChild(holder);
        inputs.push(obj);
      });
      const add = el("button", "insp-add", "＋ 添加选项");
      add.type = "button";
      add.addEventListener("click", () => {
        const lines = source.value.split("\n");
        let stop = idx + 1;
        while (stop < lines.length && lines[stop].trim().startsWith(">")) stop++;
        lines.splice(stop, 0, pad + "    > 新选项 -> " + defTarget);
        writeLines(lines, idx, false);
      });
      const wrap = el("div", "insp-actions");
      wrap.appendChild(add);
      body.appendChild(wrap);
      return;
    }

    // @show 角色 表情 [anim=] [pos=] [scale=]
    if ((m = t.match(/^@show\s+(\S+)\s+(\S+)(.*)$/))) {
      appendTag(body, "@show");
      const args = {};
      (m[3] || "").replace(/(\w+)=(\S+)/g, (_, k, v) => { args[k] = v; });
      const who = candidateField(body, m[1], "角色ID", charIdList);
      // 表情候选联动角色 ID：立绘命名「角色_表情」，只列该角色的表情后缀
      const exp = candidateField(body, m[2], "表情名", () => {
        const w = who.value.trim();
        if (!w) return [];
        const pre = w + "_";
        return (assets.images || []).filter(n => n.startsWith(pre)).map(n => n.slice(pre.length));
      });
      const anim = candidateField(body, args.anim || "", "呼吸", () => assets.anims || []);
      const pos = selectField([["", "不指定"], ["左", "左"], ["中", "中"], ["右", "右"]], args.pos || "");
      const scale = field(args.scale || "", "0.5~2.0");
      body.appendChild(row("角色", who));
      body.appendChild(row("表情", exp));
      body.appendChild(row("动画", anim));
      body.appendChild(row("位置", pos));
      body.appendChild(row("缩放", scale));
      const apply = (quiet) => {
        const lines = source.value.split("\n");
        if (idx < 0 || idx >= lines.length) return;
        let s = lineIndent(lines[idx]) + "@show " + who.value.trim() + " " + exp.value.trim();
        if (anim.value.trim()) s += " anim=" + anim.value.trim();
        if (pos.value) s += " pos=" + pos.value;
        if (scale.value.trim()) s += " scale=" + scale.value.trim();
        lines[idx] = s;
        writeLines(lines, idx, quiet);
      };
      [who, exp, anim, scale].forEach(i => bindLive(i, apply));
      pos.addEventListener("change", () => apply(false));
      return;
    }

    // @set 变量 运算符 值
    if ((m = t.match(/^@set\s+(\S+)\s*([+\-]?=)\s*(.+)$/))) {
      appendTag(body, "@set");
      const v = field(m[1], "变量名");
      const op = selectField([["=", "="], ["+=", "+="], ["-=", "-="]], m[2]);
      const rhs = field(m[3], "数值或表达式");
      body.appendChild(row("变量", v));
      body.appendChild(row("运算", op));
      body.appendChild(row("值", rhs));
      const apply = (quiet) => {
        const lines = source.value.split("\n");
        if (idx < 0 || idx >= lines.length) return;
        lines[idx] = lineIndent(lines[idx]) + "@set " + v.value.trim() + " " + op.value + " " + rhs.value.trim();
        writeLines(lines, idx, quiet);
      };
      [v, rhs].forEach(i => bindLive(i, apply));
      op.addEventListener("change", () => apply(false));
      return;
    }

    // @if 条件:
    if (t.startsWith("@if ")) {
      appendTag(body, "@if");
      const cond = field(t.replace(/^@if\s+/, "").replace(/:\s*$/, ""), "变量 > 3 或表达式");
      body.appendChild(row("条件", cond));
      const apply = (quiet) => {
        const lines = source.value.split("\n");
        if (idx < 0 || idx >= lines.length) return;
        lines[idx] = lineIndent(lines[idx]) + "@if " + cond.value.trim().replace(/:\s*$/, "") + ":";
        writeLines(lines, idx, quiet);
      };
      bindLive(cond, apply);
      return;
    }

    // @character 名 颜色 / 单参数指令 / @video
    if ((m = t.match(/^@character\s+(\S+)(?:\s+(#\S+))?/))) {
      appendTag(body, "@character");
      const nm = field(m[1], "角色名");
      const color = field(m[2] || "#ffffff", "#rrggbb");
      body.appendChild(row("角色", nm));
      body.appendChild(row("颜色", color));
      const apply = (quiet) => {
        const lines = source.value.split("\n");
        if (idx < 0 || idx >= lines.length) return;
        lines[idx] = lineIndent(lines[idx]) + "@character " + nm.value.trim() + " " + color.value.trim();
        writeLines(lines, idx, quiet);
      };
      [nm, color].forEach(i => bindLive(i, apply));
      return;
    }
    if ((m = t.match(/^@video\s+(\S+)(?:\s+fps=(\d+))?/))) {
      appendTag(body, "@video");
      const nm = candidateField(body, m[1], "视频名", () => assets.videos || []);
      const fps = field(m[2] || "", "fps（可空）");
      body.appendChild(row("视频", nm));
      body.appendChild(row("帧率", fps));
      const apply = (quiet) => {
        const lines = source.value.split("\n");
        if (idx < 0 || idx >= lines.length) return;
        lines[idx] = lineIndent(lines[idx]) + "@video " + nm.value.trim()
          + (fps.value.trim() ? " fps=" + fps.value.trim() : "");
        writeLines(lines, idx, quiet);
      };
      [nm, fps].forEach(i => bindLive(i, apply));
      return;
    }
    if ((m = t.match(/^@(music|sfx|voice|cg|label|jump|hide)\s+(\S+)/))) {
      const kind = m[1];
      appendTag(body, "@" + kind);
      // A1：素材类指令按素材库联想；label/jump 是剧本内符号，不给素材候选
      const cat = kind === "cg" ? "images"
        : (kind === "music" || kind === "sfx" || kind === "voice") ? "audio" : null;
      const nm = cat
        ? candidateField(body, m[2], "素材名", () => assets[cat] || [])
        : field(m[2], kind === "jump" || kind === "label" ? "名称" : "素材名");
      body.appendChild(row("名称", nm));
      const apply = (quiet) => {
        const lines = source.value.split("\n");
        if (idx < 0 || idx >= lines.length) return;
        lines[idx] = lineIndent(lines[idx]) + "@" + kind + " " + nm.value.trim();
        writeLines(lines, idx, quiet);
      };
      bindLive(nm, apply);
      return;
    }
    if ((m = t.match(/^@transition\s+(\S+)(?:\s+(\S+))?\s+(\S+)\s*$/))) {
      appendTag(body, "@transition");
      const kind = selectField([["dissolve", "溶解"], ["wipe", "擦除"], ["slide", "滑动"]], m[1]);
      const dir = selectField([["", "（无方向）"], ["左", "左"], ["右", "右"], ["上", "上"], ["下", "下"]],
                              m[1] === "dissolve" ? "" : (m[2] || ""));
      const secs = field(m[1] === "dissolve" ? m[3] : m[3], "秒数");
      body.appendChild(row("类型", kind));
      body.appendChild(row("方向", dir));
      body.appendChild(row("秒数", secs));
      const apply = (quiet) => {
        const lines = source.value.split("\n");
        if (idx < 0 || idx >= lines.length) return;
        const parts = ["@transition", kind.value];
        if (kind.value !== "dissolve" && dir.value) parts.push(dir.value);
        parts.push(secs.value.trim());
        lines[idx] = lineIndent(lines[idx]) + parts.join(" ");
        writeLines(lines, idx, quiet);
      };
      kind.addEventListener("change", () => apply(false));
      dir.addEventListener("change", () => apply(false));
      bindLive(secs, apply);
      return;
    }

    // 普通叙述行
    if (!t.startsWith("@")) {
      appendTag(body, "叙述");
      const txt = field(t, "旁白文本");
      body.appendChild(row("文本", txt));
      const apply = (quiet) => {
        const lines = source.value.split("\n");
        if (idx < 0 || idx >= lines.length) return;
        lines[idx] = lineIndent(lines[idx]) + txt.value.trim();
        writeLines(lines, idx, quiet);
      };
      bindLive(txt, apply);
      return;
    }

    // 其余指令（@camera / @plug / @end 等）：直接编辑整行
    appendTag(body, (t.split(/\s+/)[0] || "指令"));
    const rawInput = field(t, "整行文本");
    body.appendChild(row("整行", rawInput));
    const apply = (quiet) => {
      const lines = source.value.split("\n");
      if (idx < 0 || idx >= lines.length) return;
      lines[idx] = lineIndent(lines[idx]) + rawInput.value.trim();
      writeLines(lines, idx, quiet);
    };
    bindLive(rawInput, apply);
  }

  source.addEventListener("click", updateInspectorFromCursor);
  source.addEventListener("keyup", updateInspectorFromCursor);

  // ---- 自动补全 ----
  let acItems = [];
  let acSelected = 0;
  function showAutocomplete(items) {
    if (!items.length) { hideAutocomplete(); return; }
    acItems = items;
    acSelected = 0;
    autocomplete.innerHTML = items.map((it, i) =>
      `<div class="item ${i === 0 ? 'selected' : ''}" data-i="${i}">${it}</div>`
    ).join("");
    autocomplete.style.display = "block";
    positionAutocomplete();
  }
  function positionAutocomplete() {
    // 简单定位：在 textarea 光标附近（用行高估算）
    const rect = source.getBoundingClientRect();
    const lineHeight = 1.6 * 14;
    const lines = source.value.substring(0, source.selectionStart).split("\n");
    const top = rect.top + lines.length * lineHeight - source.scrollTop + 4;
    autocomplete.style.top = top + "px";
    autocomplete.style.left = rect.left + 4 + "px";
  }
  function hideAutocomplete() {
    autocomplete.style.display = "none";
    acItems = [];
  }
  function selectAc(i) {
    acSelected = Math.max(0, Math.min(i, acItems.length - 1));
    autocomplete.querySelectorAll(".item").forEach((el, idx) => {
      el.classList.toggle("selected", idx === acSelected);
    });
  }
  function applyAc() {
    if (!acItems.length) return;
    const val = acItems[acSelected];
    // 替换当前 token
    const start = source.selectionStart;
    const before = source.value.substring(0, start);
    const tokenMatch = before.match(/\S+$/);
    const tokenStart = tokenMatch ? before.length - tokenMatch[0].length : start;
    const endPos = tokenStart + val.length;
    setSourceValue(source.value.substring(0, tokenStart) + val + source.value.substring(start), endPos, endPos);
    hideAutocomplete();
    scheduleCheck();
  }

  async function triggerComplete() {
    const text = source.value;
    const lines = text.split("\n");
    const curLineIdx = text.substring(0, source.selectionStart).split("\n").length - 1;
    const line = lines[curLineIdx] || "";
    try {
      const resp = await fetch("/api/complete", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({line, text}),
      }).then(r => r.json());
      showAutocomplete(resp.items || []);
    } catch (e) {}
  }

  source.addEventListener("keydown", (e) => {
    if (autocomplete.style.display === "block" && acItems.length) {
      if (e.key === "ArrowDown") { e.preventDefault(); selectAc(acSelected + 1); return; }
      if (e.key === "ArrowUp") { e.preventDefault(); selectAc(acSelected - 1); return; }
      if (e.key === "Tab" || e.key === "Enter") { e.preventDefault(); applyAc(); return; }
      if (e.key === "Escape") { e.preventDefault(); hideAutocomplete(); return; }
    }
    // 输入 @ 后弹补全
    if (e.key === "@") {
      setTimeout(triggerComplete, 10);
    }
    // 指令名后敲空格：列出该指令的素材名（@bg / @show / @voice …）
    if (e.key === " ") {
      const before = source.value.substring(0, source.selectionStart) + " ";
      const curLine = before.split("\n").pop();
      if (/^@[A-Za-z]+\s+$/.test(curLine)) setTimeout(triggerComplete, 10);
    }
  });
  source.addEventListener("click", () => hideAutocomplete());

  autocomplete.addEventListener("mousedown", (e) => {
    const item = e.target.closest(".item");
    if (item) {
      e.preventDefault();
      acSelected = parseInt(item.dataset.i);
      applyAc();
    }
  });

  // ==================== 卡片视图 ====================
  // 数据流：卡片表单 → 指令 dict 列表（cardModel）→ /api/render → .gal 文本 → 源码区 → 预览
  // 前端绝不自己拼 .gal 文本，序列化只在后端 parser.dump_text 一份
  let cardModel = [];
  let expandedPath = null;   // 当前展开卡片的路径串（如 "[0,1]"），重渲染后保持展开
  let cardErrorMsg = "";

  const BADGE = {
    say: ["对话", "say"], bg: ["背景", "bg"], music: ["音乐", "music"], sfx: ["音效", "sfx"],
    show: ["立绘", "show"], hide: ["隐藏", "hide"], character: ["角色", "character"],
    label: ["标签", "label"], jump: ["跳转", "jump"], set: ["变量", "set"],
    if: ["条件", "if"], choice: ["选项", "choice"], end: ["结束", "end"],
  };
  const ADD_TYPES = [
    ["say", "对话"], ["bg", "背景"], ["music", "音乐"], ["sfx", "音效"],
    ["show", "立绘"], ["hide", "隐藏"], ["character", "角色"], ["label", "标签"],
    ["jump", "跳转"], ["set", "变量"], ["if", "条件"], ["choice", "选项"], ["end", "结束"],
  ];

  function postJSON(url, body) {
    return fetch(url, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body),
    }).then(r => r.json());
  }

  // 深拷贝一份指令列表（保留 line 用于卡片上显示行号；line/file 由后端 /api/render 剔除）
  function cloneInstrs(list) {
    return JSON.parse(JSON.stringify(list || []));
  }

  function collectCharacters() {
    const out = [];
    (function walk(list) {
      for (const i of list) {
        if (i.op === "character" && i.name && !out.includes(i.name)) out.push(i.name);
        if (Array.isArray(i.body)) walk(i.body);
      }
    })(cardModel);
    return out;
  }
  function collectLabels() {
    const out = [];
    (function walk(list) {
      for (const i of list) {
        if (i.op === "label" && i.name && !out.includes(i.name)) out.push(i.name);
        if (Array.isArray(i.body)) walk(i.body);
      }
    })(cardModel);
    return out;
  }

  function summaryOf(ins) {
    switch (ins.op) {
      case "say": return (ins.char ? ins.char + "：" : "旁白：") + (ins.text || "");
      case "bg": return "背景 → " + (ins.image || "");
      case "music": return "音乐 → " + (ins.track || "");
      case "sfx": return "音效 → " + (ins.sound || "");
      case "show": return "立绘 " + (ins.char || "") + " / " + (ins.expr || "");
      case "hide": return "隐藏 " + (ins.char || "");
      case "character": return (ins.name || "") + " " + (ins.color || "");
      case "label": return "标签 " + (ins.name || "");
      case "jump": return "跳到 → " + (ins.target || "");
      case "set": return (ins.var || "") + " " + (ins.operator || "") + " " + ins.value;
      case "if": {
        const c = ins.cond || {};
        return "若 " + (c.var || "") + " " + (c.op || "") + " " + c.value + " 则执行 " + (ins.body || []).length + " 条";
      }
      case "choice": return (ins.options || []).length + " 个选项";
      case "end": return "剧本结束";
      default: return ins.op || "未知";
    }
  }

  // ---------- 渲染 ----------
  function renderCards() {
    cardView.innerHTML = "";
    if (cardErrorMsg) {
      const bar = document.createElement("div");
      bar.className = "card-error-bar";
      bar.textContent = cardErrorMsg;
      cardView.appendChild(bar);
    }
    if (!cardModel.length) {
      const empty = document.createElement("div");
      empty.className = "card-empty";
      empty.textContent = "还没有指令，点下面的「＋ 添加指令」开始写剧本。";
      cardView.appendChild(empty);
    }
    cardView.appendChild(buildList(cardModel, [], 0));
    // 顶层添加按钮
    cardView.appendChild(makeAddButton(cardModel, [], "＋ 添加指令"));
  }

  function buildList(list, parentPath, depth) {
    const wrap = document.createElement("div");
    list.forEach((ins, idx) => {
      const path = parentPath.concat([idx]);
      wrap.appendChild(buildCard(ins, list, idx, path, depth));
    });
    return wrap;
  }

  function buildCard(ins, list, index, path, depth) {
    const pathKey = JSON.stringify(path);
    const card = document.createElement("div");
    card.className = "card";
    card.dataset.path = pathKey;

    const [label, cls] = BADGE[ins.op] || ["未知", "end"];

    // ---- 头部 ----
    const head = document.createElement("div");
    head.className = "card-head";

    const badge = document.createElement("span");
    badge.className = "badge badge-" + cls;
    badge.textContent = label;
    head.appendChild(badge);

    const sum = document.createElement("span");
    sum.className = "card-summary";
    sum.textContent = summaryOf(ins);
    head.appendChild(sum);

    if (ins.line) {
      const ln = document.createElement("span");
      ln.className = "card-line";
      ln.textContent = "第 " + ins.line + " 行";
      head.appendChild(ln);
    }

    const btns = document.createElement("span");
    btns.className = "card-btns";
    btns.appendChild(iconBtn("↑", "上移", (e) => { e.stopPropagation(); moveIn(list, index, -1, card, path); }));
    btns.appendChild(iconBtn("↓", "下移", (e) => { e.stopPropagation(); moveIn(list, index, 1, card, path); }));
    btns.appendChild(iconBtn("✕", "删除", (e) => { e.stopPropagation(); list.splice(index, 1); expandedPath = null; applyModel(null); }));
    head.appendChild(btns);

    head.addEventListener("click", () => {
      expandedPath = (expandedPath === pathKey) ? null : pathKey;
      renderCards();
    });
    card.appendChild(head);

    // ---- 展开的表单 ----
    if (expandedPath === pathKey) {
      card.appendChild(buildForm(ins, list, index, path, card));
    }

    // ---- 嵌套：@if 的 body 子卡片（始终缩进显示，结构一眼可读）----
    if (ins.op === "if") {
      const kids = document.createElement("div");
      kids.className = "card-children";
      if (ins.body && ins.body.length) {
        kids.appendChild(buildList(ins.body, path.concat(["body"]), depth + 1));
      } else {
        const note = document.createElement("div");
        note.className = "card-note";
        note.textContent = "条件内暂无指令";
        kids.appendChild(note);
      }
      kids.appendChild(makeAddButton(ins.body || (ins.body = []), path.concat(["body"]), "＋ 在条件内添加指令"));
      card.appendChild(kids);
    }
    return card;
  }

  function iconBtn(text, title, handler) {
    const b = document.createElement("button");
    b.className = "icon-btn";
    b.type = "button";
    b.textContent = text;
    b.title = title;
    b.addEventListener("click", handler);
    return b;
  }

  function makeAddButton(list, parentPath, text) {
    const holder = document.createElement("div");
    const btn = document.createElement("button");
    btn.className = "card-add";
    btn.type = "button";
    btn.textContent = text;
    btn.title = "Add · 添加新指令卡片";
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      showAddPicker(holder, list, parentPath);
    });
    holder.appendChild(btn);
    return holder;
  }

  function showAddPicker(holder, list, parentPath) {
    holder.innerHTML = "";
    const row = document.createElement("div");
    row.className = "option-row";
    row.style.marginTop = "8px";
    const sel = document.createElement("select");
    sel.className = "opt-text";
    ADD_TYPES.forEach(([v, label]) => {
      const o = document.createElement("option");
      o.value = v; o.textContent = label;
      sel.appendChild(o);
    });
    const ok = document.createElement("button");
    ok.className = "icon-btn";
    ok.textContent = "添加";
    ok.title = "Confirm Add · 确认添加";
    ok.addEventListener("click", (e) => {
      e.stopPropagation();
      list.push(defaultInstr(sel.value));
      expandedPath = JSON.stringify(parentPath.concat([list.length - 1]));
      applyModel(null);
    });
    const cancel = document.createElement("button");
    cancel.className = "icon-btn";
    cancel.textContent = "取消";
    cancel.title = "Cancel · 取消添加";
    cancel.addEventListener("click", (e) => {
      e.stopPropagation();
      renderCards();
    });
    row.appendChild(sel); row.appendChild(ok); row.appendChild(cancel);
    holder.appendChild(row);
  }

  function defaultInstr(op) {
    const labels = collectLabels();
    const tgt = labels[0] || "start";
    switch (op) {
      case "say": return {op: "say", char: null, text: "新对话"};
      case "bg": return {op: "bg", image: "classroom"};
      case "music": return {op: "music", track: "bgm_main"};
      case "sfx": return {op: "sfx", sound: "click"};
      case "show": return {op: "show", char: collectCharacters()[0] || "林晚", expr: "normal"};
      case "hide": return {op: "hide", char: collectCharacters()[0] || "林晚"};
      case "character": return {op: "character", name: "新角色", color: "#aaccff"};
      case "label": return {op: "label", name: "new_label"};
      case "jump": return {op: "jump", target: tgt};
      case "set": return {op: "set", var: "好感", operator: "+=", value: 1};
      case "if": return {op: "if", cond: {var: "好感", op: ">=", value: 1}, body: []};
      case "choice": return {op: "choice", options: [{text: "选项一", target: tgt}]};
      case "end": return {op: "end"};
      default: return {op: "end"};
    }
  }

  // ---------- 表单 ----------
  function fieldRow(labelText, el) {
    const d = document.createElement("div");
    d.className = "field";
    const l = document.createElement("label");
    l.textContent = labelText;
    d.appendChild(l); d.appendChild(el);
    return d;
  }
  function mkInput(field, value, type) {
    const el = document.createElement("input");
    if (type === "color") { el.type = "color"; } else if (type === "number") { el.type = "number"; el.step = "any"; }
    else { el.type = "text"; }
    el.dataset.f = field;
    el.value = value === undefined || value === null ? "" : value;
    return el;
  }
  function mkTextarea(field, value) {
    const el = document.createElement("textarea");
    el.dataset.f = field;
    el.value = value === undefined || value === null ? "" : value;
    return el;
  }
  function mkSelect(field, value, options) {
    const el = document.createElement("select");
    el.dataset.f = field;
    options.forEach(([v, label]) => {
      const o = document.createElement("option");
      o.value = v; o.textContent = label;
      el.appendChild(o);
    });
    el.value = value;
    return el;
  }

  function buildForm(ins, list, index, path, card) {
    const form = document.createElement("div");
    form.className = "card-form";
    form.addEventListener("click", (e) => e.stopPropagation());

    const chars = collectCharacters();
    const labels = collectLabels();

    switch (ins.op) {
      case "character":
        form.appendChild(fieldRow("名字", mkInput("name", ins.name)));
        form.appendChild(fieldRow("颜色", mkInput("color", ins.color || "#aaccff", "color")));
        break;
      case "bg":
        form.appendChild(fieldRow("图片名", mkInput("image", ins.image)));
        break;
      case "music":
        form.appendChild(fieldRow("音乐名", mkInput("track", ins.track)));
        break;
      case "sfx":
        form.appendChild(fieldRow("音效名", mkInput("sound", ins.sound)));
        break;
      case "show":
        form.appendChild(fieldRow("角色ID", mkInput("char", ins.char)));
        form.appendChild(fieldRow("表情", mkInput("expr", ins.expr)));
        break;
      case "hide":
        form.appendChild(fieldRow("角色ID", mkInput("char", ins.char)));
        break;
      case "say": {
        const opts = [["__none__", "旁白"]].concat(chars.map(c => [c, c]));
        form.appendChild(fieldRow("角色", mkSelect("char", ins.char || "__none__", opts)));
        form.appendChild(fieldRow("文本", mkTextarea("text", ins.text)));
        break;
      }
      case "label":
        form.appendChild(fieldRow("标签名", mkInput("name", ins.name)));
        break;
      case "jump": {
        if (!labels.length) {
          const note = document.createElement("div");
          note.className = "card-note";
          note.textContent = "剧本里还没有 @label，请先在别处添加一个「标签」卡片，再来选跳转目标。";
          form.appendChild(note);
          form.appendChild(fieldRow("目标标签", mkInput("target", ins.target)));
        } else {
          const opts = labels.map(l => [l, l]);
          if (ins.target && !labels.includes(ins.target)) opts.unshift([ins.target, ins.target + "（不存在）"]);
          form.appendChild(fieldRow("目标标签", mkSelect("target", ins.target, opts)));
        }
        break;
      }
      case "set":
        form.appendChild(fieldRow("变量名", mkInput("var", ins.var)));
        form.appendChild(fieldRow("运算符", mkSelect("operator", ins.operator,
          [["+=", "+="], ["-=", "-="], ["=", "="]])));
        form.appendChild(fieldRow("数值", mkInput("value", ins.value, "number")));
        break;
      case "if": {
        const c = ins.cond || {var: "好感", op: ">=", value: 1};
        form.appendChild(fieldRow("变量", mkInput("condVar", c.var)));
        form.appendChild(fieldRow("运算符", mkSelect("condOp", c.op, [[">=", ">="], ["==", "=="]])));
        form.appendChild(fieldRow("数值", mkInput("condValue", c.value, "number")));
        const note = document.createElement("div");
        note.className = "card-note";
        note.textContent = "条件成立时执行下方缩进的子卡片。";
        form.appendChild(note);
        break;
      }
      case "choice": {
        const box = document.createElement("div");
        box.dataset.f = "optionsBox";
        // 从当前输入框读回选项（增删前先同步，避免丢失未保存的输入）
        const readRows = () => {
          const out = [];
          box.querySelectorAll(".option-row").forEach(row => {
            const t = row.querySelector('[data-k="text"]');
            const c = row.querySelector('[data-k="cond"]');
            const tg = row.querySelector('[data-k="target"]');
            if (!t) return;
            const o = {text: t.value.trim(), target: tg.value};
            const cs = (c.value || "").trim();
            if (cs) {
              const m = cs.match(/^(\S+)\s*(>=|==)\s*(-?\d+(?:\.\d+)?)$/);
              if (m) o.cond = {var: m[1], op: m[2], value: Number(m[3])};
            }
            out.push(o);
          });
          return out;
        };
        form.readOptions = readRows;
        const renderOpts = () => {
          box.innerHTML = "";
          (ins.options || []).forEach((o, oi) => {
            const row = document.createElement("div");
            row.className = "option-row";
            const t = document.createElement("input");
            t.className = "opt-text"; t.value = o.text || ""; t.placeholder = "选项文本";
            t.dataset.o = oi; t.dataset.k = "text";
            const cond = document.createElement("input");
            cond.className = "opt-cond";
            cond.value = o.cond ? `${o.cond.var} ${o.cond.op} ${o.cond.value}` : "";
            cond.placeholder = "条件（可选）：好感 >= 2";
            cond.dataset.o = oi; cond.dataset.k = "cond";
            const tg = document.createElement("select");
            tg.className = "opt-target";
            tg.dataset.o = oi; tg.dataset.k = "target";
            const tgOpts = labels.length ? labels.map(l => [l, l]) : [["", "（无标签）"]];
            if (o.target && !labels.includes(o.target)) tgOpts.unshift([o.target, o.target + "（不存在）"]);
            tgOpts.forEach(([v, label]) => {
              const op = document.createElement("option");
              op.value = v; op.textContent = label;
              tg.appendChild(op);
            });
            tg.value = o.target || "";
            const del = iconBtn("✕", "删除选项", (e) => {
              e.stopPropagation();
              ins.options = readRows();
              ins.options.splice(oi, 1);
              renderOpts();
            });
            row.appendChild(t); row.appendChild(cond); row.appendChild(tg); row.appendChild(del);
            box.appendChild(row);
          });
          const add = document.createElement("button");
          add.className = "card-add";
          add.style.marginTop = "8px";
          add.textContent = "＋ 添加选项";
          add.title = "Add Option · 添加新的分支选项";
          add.addEventListener("click", (e) => {
            e.stopPropagation();
            ins.options = readRows();
            ins.options.push({text: "新选项", target: labels[0] || "start"});
            renderOpts();
          });
          box.appendChild(add);
        };
        renderOpts();
        form.appendChild(box);
        break;
      }
      case "end": {
        const note = document.createElement("div");
        note.className = "card-note";
        note.textContent = "@end 表示剧本到此结束，不需要参数。";
        form.appendChild(note);
        break;
      }
      default:
        break;
    }

    // 保存按钮
    const actions = document.createElement("div");
    actions.className = "field-actions";
    const save = document.createElement("button");
    save.textContent = "保存修改";
    save.title = "Save Changes · 保存当前卡片修改";
    save.addEventListener("click", async (e) => {
      e.stopPropagation();
      const g = (f) => form.querySelector(`[data-f="${f}"]`);
      const num = (v) => {
        const n = Number(v);
        return Number.isFinite(n) ? n : 0;
      };
      switch (ins.op) {
        case "character": ins.name = g("name").value.trim(); ins.color = g("color").value; break;
        case "bg": ins.image = g("image").value.trim(); break;
        case "music": ins.track = g("track").value.trim(); break;
        case "sfx": ins.sound = g("sound").value.trim(); break;
        case "show": ins.char = g("char").value.trim(); ins.expr = g("expr").value.trim(); break;
        case "hide": ins.char = g("char").value.trim(); break;
        case "say": {
          const v = g("char").value;
          ins.char = v === "__none__" ? null : v;
          ins.text = g("text").value.trim();
          if (!ins.char) delete ins.char;
          break;
        }
        case "label": ins.name = g("name").value.trim(); break;
        case "jump": ins.target = g("target").value.trim(); break;
        case "set":
          ins.var = g("var").value.trim();
          ins.operator = g("operator").value;
          ins.value = num(g("value").value);
          break;
        case "if": {
          const c = ins.cond || (ins.cond = {});
          c.var = g("condVar").value.trim();
          c.op = g("condOp").value;
          c.value = num(g("condValue").value);
          break;
        }
        case "choice": {
          if (form.readOptions) ins.options = form.readOptions();
          break;
        }
        default: break;
      }
      await applyModel(card);
    });
    actions.appendChild(save);

    const close = document.createElement("button");
    close.className = "icon-btn";
    close.textContent = "收起";
    close.title = "Collapse · 收起卡片详情";
    close.addEventListener("click", (e) => {
      e.stopPropagation();
      expandedPath = null;
      renderCards();
    });
    actions.appendChild(close);
    form.appendChild(actions);
    return form;
  }

  function moveIn(list, index, delta, card, path) {
    const j = index + delta;
    if (j < 0 || j >= list.length) return;
    const tmp = list[index];
    list[index] = list[j];
    list[j] = tmp;
    // 保持展开状态跟着卡片一起移动
    if (expandedPath === JSON.stringify(path)) {
      const moved = path.slice();
      moved[moved.length - 1] = j;
      expandedPath = JSON.stringify(moved);
    }
    applyModel(null);
  }

  // ---------- 应用改动：卡片模型 → 文本 → 源码 → 预览 ----------
  async function applyModel(badCard) {
    cardErrorMsg = "";
    let resp;
    try {
      resp = await postJSON("/api/render", {instructions: cardModel});
    } catch (e) {
      cardErrorMsg = "生成剧本请求失败：" + e;
      renderCards();
      return;
    }
    if (!resp.ok) {
      cardErrorMsg = resp.message || "生成剧本失败";
      if (badCard) badCard.classList.add("bad");
      renderCards();
      if (badCard) {
        const again = cardView.querySelector(`.card[data-path='${badCard.dataset.path}']`);
        if (again) again.classList.add("bad");
      }
      return;
    }
    // 后端生成的文本写回源码区（前端不拼文本）
    setSourceValue(resp.text);
    updateLineNumbers();
    // 重新解析刷新行号，保持展开的卡片
    const chk = await postJSON("/api/check", {text: resp.text});
    if (chk.ok) {
      cardModel = cloneInstrs(chk.instructions);
    }
    renderCards();
    scheduleCheck();  // 预览联动（沿用源码视图的防抖）
  }

  async function enterCardView() {
    cardErrorMsg = "";
    expandedPath = null;
    const text = source.value;
    const hasInclude = /^\s*@include\b/m.test(text);
    let resp;
    try {
      resp = await postJSON("/api/check", {text, path: (window.__proCurPath && window.__proCurPath()) || undefined});
    } catch (e) {
      cardView.innerHTML = '<div class="card-error-bar">检查请求失败：' + e + '</div>';
      return;
    }
    if (!resp.ok) {
      // 语法错误：切回源码视图并高亮错误行
      switchTab("source");
      lastError = {line: resp.line, file: resp.file, message: resp.message};
      setStatus(false, `语法错误 · 第 ${resp.line} 行`);
      setPreviewBar(false, `解析失败：${resp.file} 第 ${resp.line} 行：${resp.message}`);
      highlightError(resp.line);
      updateLineNumbers();
      return;
    }
    if (hasInclude) {
      // 多文件剧本：卡片视图切换为跨文件只读总览（editor_pro.js 渲染）
      if (window.__proCards) {
        window.__proCards(resp.instructions || []);
      } else {
        cardView.innerHTML = '<div class="card-disabled">检测到 <b>@include</b>：多文件剧本请用「源码」视图编辑。</div>';
      }
      return;
    }
    cardModel = cloneInstrs(resp.instructions);
    renderCards();
  }

  // ==================== P12 素材库 ====================
  // 素材清单只列文件名（后端 stat），缩略图按需加载；拖素材到代码区生成指令行
  const assetPane = $("assetPane");
  const assetBody = $("assetBody");
  const assetHint = $("assetHint");
  const assetFile = $("assetFile");
  const assetTabs = $("assetTabs");
  const assetSearch = $("assetSearch");
  const assetSearchClear = $("assetSearchClear");
  const assetProgress = $("assetProgress");
  const assetProgressFill = $("assetProgressFill");
  const assetProgressText = $("assetProgressText");
  const missingBar = $("missingBar");

  const CAT_LABEL = { images: "图片", characters: "角色", audio: "音频", fonts: "字体", videos: "视频", anims: "动画" };
  let assets = { images: [], characters: [], audio: [], fonts: [], videos: [], anims: [] };
  let assetCat = "images";
  let assetQuery = "";              // E-3：素材搜索关键词（当前分类内过滤）
  let assetsReady = false;
  let playingAudio = null;
  let insertMenuEl = null;
  let insertMenuOnClose = null;
  let editorCfg = { project_root: "", data_root: "", auto_insert: true };
  let pendingInserts = [];
  let lastImportPoint = { x: window.innerWidth / 2, y: 120 };

  // ---- P20：轻提示（toast，中文，右下角，2.8 秒自动消失）----
  function toast(msg, isErr) {
    if (window.dockLog) window.dockLog("output", msg);   // D1：同步进底部 Dock「输出」页
    const wrap = $("toastWrap");
    if (!wrap) return;
    const el = document.createElement("div");
    el.className = "toast" + (isErr ? " err" : "");
    el.textContent = msg;
    wrap.appendChild(el);
    setTimeout(() => {
      el.style.opacity = "0";
      el.style.transition = "opacity .25s";
      setTimeout(() => el.remove(), 260);
    }, 2800);
  }

  function assetURL(cat, name) {
    return "/api/asset/" + cat + "/" + encodeURIComponent(name);
  }

  function setAssetHint(msg, err) {
    assetHint.textContent = msg;
    assetHint.style.color = err ? "#f38ba8" : "#585b70";
  }

  // ---- E-3：素材搜索（当前分类内过滤，Esc / ✕ 清空）----
  function setAssetQuery(v) {
    assetQuery = (v || "").trim();
    assetSearch.value = assetQuery;
    assetSearchClear.classList.toggle("hidden", !assetQuery);
    renderAssets();
  }
  assetSearch.addEventListener("input", () => setAssetQuery(assetSearch.value));
  assetSearch.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape") { ev.preventDefault(); setAssetQuery(""); }
  });
  assetSearchClear.addEventListener("click", () => { setAssetQuery(""); assetSearch.focus(); });

  // ---- E-3：批量导入进度（≥2 个文件时显示，结束后停留 0.9s 再收起）----
  let importProgressTimer = null;
  function setImportProgress(done, total, failed) {
    if (!assetProgress || total < 2) return;
    if (importProgressTimer) { clearTimeout(importProgressTimer); importProgressTimer = null; }
    assetProgress.classList.remove("hidden");
    const pct = total ? Math.min(100, Math.round(done * 100 / total)) : 0;
    assetProgressFill.style.width = pct + "%";
    assetProgressText.textContent = "导入中 " + done + "/" + total + "（" + pct + "%）"
      + (failed ? " · 失败 " + failed : "");
  }
  function finishImportProgress() {
    if (!assetProgress || assetProgress.classList.contains("hidden")) return;
    importProgressTimer = setTimeout(() => {
      assetProgress.classList.add("hidden");
      assetProgressFill.style.width = "0%";
    }, 900);
  }

  async function refreshAssets() {
    try {
      const resp = await fetch("/api/assets", {cache: "no-store"}).then(r => r.json());
      if (resp && resp.ok) {
        assets = resp.assets || assets;
    refreshClothesline();
        assetsReady = true;
      } else {
        setAssetHint((resp && resp.message) || "素材清单读取失败", true);
      }
    } catch (e) {
      setAssetHint("素材清单读取失败：" + e, true);
    }
    if (assetCat === "characters") window.__characterLib = null;  // V1：刷新按钮同时重读角色库
    renderAssets();
    updateMissingBar();
    if (window.__proAfterAssets) window.__proAfterAssets();
  }

  function renderAssets() {
    if (assetCat === "characters") { renderCharacterAssets(); return; }
    assetBody.innerHTML = "";
    const all = assets[assetCat] || [];
    const q = assetQuery.trim().toLowerCase();   // E-3：当前分类内按文件名过滤
    const list = q ? all.filter(n => String(n).toLowerCase().includes(q)) : all;
    if (!list.length) {
      const empty = document.createElement("div");
      empty.className = "asset-empty";
      empty.textContent = q
        ? CAT_LABEL[assetCat] + "：没有匹配「" + assetQuery + "」的素材"
        : CAT_LABEL[assetCat] + "：暂无素材，把文件拖到这里导入";
      assetBody.appendChild(empty);
      return;
    }
    list.forEach(name => {
      const card = document.createElement("div");
      card.className = "asset-card";
      card.draggable = true;
      card.title = name + "（拖到代码区生成指令）";
      card.addEventListener("dragstart", (e) => {
        e.dataTransfer.effectAllowed = "copy";
        e.dataTransfer.setData("text/plain", JSON.stringify({ category: assetCat, name }));
        setAssetHint("把「" + name + "」拖到左侧代码区即可生成指令");
      });

      if (assetCat === "audio") {
        const ph = document.createElement("div");
        ph.className = "ph";
        ph.textContent = "♪";
        card.appendChild(ph);
        const play = document.createElement("div");
        play.className = "play";
        play.textContent = "▶ 试听";
        play.addEventListener("click", (e) => {
          e.stopPropagation();
          toggleAudio(name, play);
        });
        card.appendChild(play);
      } else if (assetCat === "fonts") {
        const ph = document.createElement("div");
        ph.className = "ph";
        ph.textContent = "Aa";
        card.appendChild(ph);
      } else {
        const img = document.createElement("img");
        img.loading = "lazy";  // 按需加载，20GB 项目也不卡
        img.alt = name;
        img.src = assetURL(assetCat, name);
        card.appendChild(img);
      }

      const nm = document.createElement("div");
      nm.className = "nm";
      nm.textContent = name;
      card.appendChild(nm);
      assetBody.appendChild(card);
    });
  }

  // ---- V1：素材库「角色」分类（与图片/音频并列）----
  function characterLib() {
    const lib = window.__characterLib;
    return (lib && Array.isArray(lib.characters)) ? lib.characters : [];
  }

  function characterAvatar(c) {
    const av = (c && c.avatars) || {};
    const keys = Object.keys(av);
    if (!keys.length) return "";
    const preferred = av["默认"] ? "默认" : (av["normal"] ? "normal" : keys[0]);
    return av[preferred] || "";
  }

  function ensureCharacters() {
    if (window.__characterLib) return Promise.resolve();
    return fetch("/api/characters", { cache: "no-store" })
      .then(r => r.json())
      .then(d => {
        window.__characterLib = (d && d.data) || { schema: 1, characters: [] };
        if (assetCat === "characters") renderAssets();
      })
      .catch(() => {});
  }

  function renderCharacterAssets() {
    assetBody.innerHTML = "";
    ensureCharacters();
    const q = assetQuery.trim().toLowerCase();
    const list = characterLib().filter(c =>
      !q || String(c.id + " " + (c.name || "")).toLowerCase().includes(q));
    if (!list.length) {
      const empty = document.createElement("div");
      empty.className = "asset-empty";
      empty.textContent = q
        ? "角色：没有匹配「" + assetQuery + "」的角色"
        : "角色：暂无角色，先在角色库里建一个";
      assetBody.appendChild(empty);
      if (!q) {
        const add = document.createElement("button");
        add.type = "button";
        add.className = "icon-btn";
        add.id = "assetCharAdd";
        add.textContent = "＋ 新建角色";
        add.addEventListener("click", () => {
          if (window.__openCharacterManager) window.__openCharacterManager();
        });
        assetBody.appendChild(add);
      }
      return;
    }
    list.forEach(c => {
      const expr = Object.keys(c.avatars || {})[0] || "默认";
      const card = document.createElement("div");
      card.className = "asset-card";
      card.draggable = true;
      card.title = (c.name || c.id) + "（拖到代码区生成 @show；单击编辑角色）";
      card.addEventListener("dragstart", (e) => {
        e.dataTransfer.effectAllowed = "copy";
        e.dataTransfer.setData("text/plain",
          JSON.stringify({ category: "characters", name: c.id + " " + expr }));
        setAssetHint("把「" + (c.name || c.id) + "」拖到左侧代码区即可生成登场指令");
      });
      card.addEventListener("click", () => {
        if (window.__openCharacterManager) window.__openCharacterManager(c.id);
      });
      const av = characterAvatar(c);
      if (av) {
        const img = document.createElement("img");
        img.loading = "lazy";
        img.alt = c.id;
        img.src = assetURL("images", av);
        card.appendChild(img);
      } else {
        const ph = document.createElement("div");
        ph.className = "ph";
        ph.textContent = String((c.name || c.id) || "?").slice(0, 2);
        card.appendChild(ph);
      }
      const nm = document.createElement("div");
      nm.className = "nm";
      nm.textContent = c.name || c.id;
      card.appendChild(nm);
      assetBody.appendChild(card);
    });
  }

  function toggleAudio(name, el) {
    if (playingAudio && playingAudio.dataset.name === name) {
      playingAudio.pause();
      playingAudio = null;
      el.textContent = "▶ 试听";
      return;
    }
    if (playingAudio) {
      playingAudio.pause();
      playingAudio = null;
      assetBody.querySelectorAll(".play").forEach(p => { p.textContent = "▶ 试听"; });
    }
    const audio = new Audio(assetURL("audio", name));
    audio.dataset.name = name;
    audio.onended = () => {
      el.textContent = "▶ 试听";
      if (playingAudio === audio) playingAudio = null;
    };
    audio.play().catch(() => setAssetHint("试听失败：浏览器无法播放该音频", true));
    el.textContent = "■ 停止";
    playingAudio = audio;
  }

  // ---- 拖拖导入 ----
  function fileToBase64(file) {
    return new Promise((resolve, reject) => {
      const r = new FileReader();
      r.onload = () => resolve(String(r.result).split(",", 2)[1] || "");
      r.onerror = () => reject(r.error);
      r.readAsDataURL(file);
    });
  }

  // D2：导入期间在活动栏「素材库」按钮上转圈（批量多文件也只在结束时停一次）
  async function importFiles(fileList, dropPoint) {
    const files = Array.from(fileList || []);
    if (!files.length) return;
    setActImporting(true);
    try {
      await importFilesInner(files, dropPoint);
    } finally {
      setActImporting(false);
      finishImportProgress();
    }
  }

  async function importFilesInner(files, dropPoint) {
    const at = dropPoint || lastImportPoint;
    const msgs = [];
    const imported = [];
    let okCount = 0, errCount = 0;
    const total = files.length;
    let processed = 0;
    const step = () => setImportProgress(++processed, total, errCount);   // E-3：逐个更新进度
    for (const f of files) {
      const ext = (f.name.split(".").pop() || "").toLowerCase();
      let category = null;
      if (["png", "jpg", "jpeg", "webp"].includes(ext)) category = "images";
      else if (["wav", "ogg", "mp3"].includes(ext)) category = "audio";
      else if (["ttf", "otf"].includes(ext)) category = "fonts";
      if (!category) {
        msgs.push("「" + f.name + "」类型不支持（只收图片/音频/字体）");
        errCount++;
        step();
        continue;
      }
      // 同名冲突三选：覆盖 / 改名 / 取消
      let overwrite = false;
      const stem = f.name.replace(/\.[^.]+$/, "");
      if ((assets[category] || []).includes(stem)) {
        const choice = await askAssetConflict(f.name);
        if (choice === "cancel") {
          msgs.push("「" + f.name + "」已取消");
          step();
          continue;
        }
        overwrite = choice === "overwrite";
      }
      let b64;
      try {
        b64 = await fileToBase64(f);
      } catch (e) {
        msgs.push("「" + f.name + "」读取失败");
        errCount++;
        step();
        continue;
      }
      try {
        const resp = await postJSON("/api/import", {
          category, filename: f.name, data_b64: b64, overwrite,
        });
        if (resp.ok) {
          const note = resp.overwritten ? "（已覆盖同名文件）"
            : (resp.renamed_from ? "（重名，改存为 " + resp.name + "）" : "");
          msgs.push("已导入 " + resp.path + note);
          imported.push({ category, name: resp.name, path: resp.path });
          assetCat = category;
          okCount++;
        } else {
          msgs.push("「" + f.name + "」导入失败：" + (resp.message || "未知错误"));
          errCount++;
        }
      } catch (e) {
        msgs.push("「" + f.name + "」导入请求失败");
        errCount++;
      }
      step();
    }
    // B2：批量导入只发一条汇总 toast，不再每个文件一条
    if (errCount === 0 && total === 1) {
      toast(msgs[0]);  // 单文件成功：显示具体路径
    } else if (errCount === 0) {
      toast("已导入 " + okCount + " 个素材");
    } else if (okCount === 0) {
      toast("导入失败 " + errCount + " 个，请检查素材栏详细提示", true);
    } else {
      toast("已导入 " + okCount + " 个，失败 " + errCount + " 个");
    }
    setAssetHint(msgs.join("；"), msgs.some(m => m.includes("失败") || m.includes("不支持")));
    assetTabs.querySelectorAll(".asset-tab").forEach(t => {
      t.classList.toggle("active", t.dataset.cat === assetCat);
    });
    await refreshAssets();
    queueInserts(imported, at);
  }

  // ---- P20：同名冲突弹窗（覆盖 / 改名 / 取消），返回 Promise<'overwrite'|'rename'|'cancel'> ----
  function askAssetConflict(filename) {
    const modal = $("conflictModal");
    $("conflictDesc").textContent =
      "素材库已有「" + filename + "」。覆盖会替换原文件，改名会自动保存为「名字_1」。";
    modal.style.display = "flex";
    return new Promise((resolve) => {
      const done = (choice) => {
        modal.style.display = "none";
        $("conflictOverwrite").onclick = null;
        $("conflictRename").onclick = null;
        $("conflictCancel").onclick = null;
        resolve(choice);
      };
      $("conflictOverwrite").onclick = () => done("overwrite");
      $("conflictRename").onclick = () => done("rename");
      $("conflictCancel").onclick = () => done("cancel");
    });
  }

  // ---- P20：导入后自动生成指令（图片弹 @bg / @show / @cg 菜单）----
  function queueInserts(items, at) {
    if (!items.length) return;
    if (!editorCfg.auto_insert) {
      if (items.length > 1) toast("已导入 " + items.length + " 个素材（自动生成指令已关闭）");
      return;
    }
    pendingInserts = pendingInserts.concat(items.map(it => ({ ...it, at })));
    processInsertQueue();
  }

  function processInsertQueue() {
    if (insertMenuEl) return;  // 已有菜单打开：等它关闭后继续
    const item = pendingInserts.shift();
    if (!item) return;
    const options = directiveOptions(item.category, item.name);
    if (!options.length) {
      toast("字体已导入：" + item.path + "（在主题里使用）");
      processInsertQueue();
      return;
    }
    options.push({ label: "跳过（不生成指令）", skip: true });
    showInsertMenu(item.at.x, item.at.y, options, (opt) => {
      if (!opt.skip) insertDirective(opt.text);
      processInsertQueue();
    });
  }

  // ---- P20 设置面板：工程目录 / 数据目录 / 自动生成指令 ----
  async function loadConfig() {
    try {
      const cfg = await fetch("/api/config", {cache: "no-store"}).then(r => r.json());
      if (cfg && cfg.ok) editorCfg = cfg;
    } catch (e) { /* 配置读取失败不阻断编辑器 */ }
  }

  function openSettings() {
    $("settingsErr").textContent = "";
    $("setProject").value = editorCfg.project_root || "";
    $("setData").value = editorCfg.custom_data_root ? (editorCfg.data_root || "") : "";
    $("setAutoInsert").checked = editorCfg.auto_insert !== false;
    // 启动动画开关走 localStorage（纯前端，不随工程）
    try { $("setSplash").checked = localStorage.getItem("moyul_splash") !== "off"; } catch (e) { $("setSplash").checked = true; }
    $("setProjectPath").textContent = "当前：" + (editorCfg.project_root || "");
    $("setDataPath").textContent = editorCfg.custom_data_root
      ? "当前：绝对路径 " + editorCfg.data_root + "（移动工程后需重设）"
      : "当前：随工程（" + (editorCfg.project_root || "") + "/images 等）";
    $("settingsModal").style.display = "flex";
  }

  function closeSettings() { $("settingsModal").style.display = "none"; }

  async function saveSettings() {
    const project = $("setProject").value.trim();
    if (!project) { $("settingsErr").textContent = "工程目录不能为空"; return; }
    const projectChanged = project !== (editorCfg.project_root || "");
    if (projectChanged && !confirm("切换工程会重新加载编辑器，未保存的修改将丢失。继续？")) return;
    try {
      const body = {project_root: project};
      if (!projectChanged) {
        // 切换工程时不覆盖新工程自己的配置（数据目录/自动插指令跟随新工程）
        body.data_root = $("setData").value.trim();
        body.auto_insert = $("setAutoInsert").checked;
      }
      const resp = await postJSON("/api/config", body);
      if (!resp.ok) { $("settingsErr").textContent = resp.message || "保存失败"; return; }
      // 启动动画开关：纯前端 localStorage
      try {
        localStorage.setItem("moyul_splash", $("setSplash").checked ? "on" : "off");
      } catch (e) {}
      closeSettings();
      if (projectChanged) {
        toast("已切换工程：" + resp.project_root + "，正在重新加载…");
        setTimeout(() => location.reload(), 400);
        return;
      }
      editorCfg = resp;
      toast("设置已保存（.editor_config.json）");
      await refreshAssets();
    } catch (e) {
      $("settingsErr").textContent = "保存请求失败：" + e;
    }
  }

  $("btnSettings").addEventListener("click", openSettings);
  $("settingsCancel").addEventListener("click", closeSettings);
  $("settingsOk").addEventListener("click", saveSettings);
  $("setProjectReset").addEventListener("click", () => {
    $("setProject").value = editorCfg.project_root || "";
  });
  $("setDataReset").addEventListener("click", () => {
    $("setData").value = "";
    $("setDataPath").textContent = "留空 = 随工程（移动工程不失效）";
  });


  ["dragenter", "dragover"].forEach(type => {
    assetPane.addEventListener(type, (e) => {
      e.preventDefault();
      assetPane.classList.add("dragover");
    });
  });
  assetPane.addEventListener("dragleave", (e) => {
    if (!assetPane.contains(e.relatedTarget)) assetPane.classList.remove("dragover");
  });
  assetPane.addEventListener("drop", (e) => {
    e.preventDefault();
    assetPane.classList.remove("dragover");
    if (e.dataTransfer.files && e.dataTransfer.files.length) {
      lastImportPoint = { x: e.clientX, y: e.clientY };
      importFiles(e.dataTransfer.files, lastImportPoint);
    }
  });
  $("assetImportBtn").addEventListener("click", () => {
    const r = $("assetImportBtn").getBoundingClientRect();
    lastImportPoint = { x: r.left, y: r.bottom + 6 };
    assetFile.click();
  });
  assetFile.addEventListener("change", () => {
    importFiles(assetFile.files, lastImportPoint);
    assetFile.value = "";
  });
  $("assetRefresh").addEventListener("click", refreshAssets);
  $("assetCollapse").addEventListener("click", () => setAssetOpen(false));

  // ---- P20 三栏布局：可拖分隔条 + 宽度记忆 + 素材抽屉 ----
  const LAYOUT_KEY = "gal_editor_layout";
  const splitTree = $("splitTree");
  const splitEdit = $("splitEdit");
  const filePane = $("filePane");
  const mainEl = document.querySelector(".main");

  function loadLayout() {
    let o = {};
    try { o = JSON.parse(localStorage.getItem(LAYOUT_KEY) || "{}"); } catch (e) {}
    if (o.tree) document.documentElement.style.setProperty("--tree-w", o.tree + "px");
    if (o.right) document.documentElement.style.setProperty("--right-w", o.right + "px");
    // P42：默认展开三列（文件树），折叠只由用户手动触发，不再恢复上次折叠状态
  }
  function saveLayout(patch) {
    try {
      const o = JSON.parse(localStorage.getItem(LAYOUT_KEY) || "{}");
      Object.assign(o, patch);
      localStorage.setItem(LAYOUT_KEY, JSON.stringify(o));
    } catch (e) {}
  }
  function setTreeCollapsed(on) {
    filePane.classList.toggle("collapsed", on);
    $("fpCollapse").textContent = on ? "⟩" : "⟨";
    $("fpCollapse").title = on ? "展开文件栏" : "折叠文件栏";
    saveLayout({treeCollapsed: on});
  }

  // ---- D3：侧栏分区分组折叠（工程文件 / 章节大纲，chevron + 状态记忆）----
  const SIDE_GROUP_KEY = "moyul_side_groups";
  const sideGroups = {};
  try { Object.assign(sideGroups, JSON.parse(localStorage.getItem(SIDE_GROUP_KEY) || "{}")); } catch (e) {}

  function applySideGroup(name, collapsed) {
    sideGroups[name] = !!collapsed;
    const body = name === "tree" ? $("fpTree") : $("fpOutline");
    const chev = name === "tree" ? $("fpTreeChev") : $("fpOutlineChev");
    if (body) body.classList.toggle("hidden", !!collapsed);
    if (chev) chev.textContent = collapsed ? "▸" : "▾";
    try { localStorage.setItem(SIDE_GROUP_KEY, JSON.stringify(sideGroups)); } catch (e) {}
  }

  function wireSideGroup(headId, name) {
    const head = $(headId);
    if (!head) return;
    head.addEventListener("click", (ev) => {
      if (ev.target.closest("button")) return;   // 头部按钮（＋章节 / 折叠栏 / 刷新）不触发分组折叠
      applySideGroup(name, !sideGroups[name]);
    });
    applySideGroup(name, !!sideGroups[name]);    // 启动时恢复上次折叠状态
  }
  wireSideGroup("fpTreeHead", "tree");
  wireSideGroup("fpOutlineHead", "outline");
  function setAssetOpen(open) {
    assetPane.classList.toggle("open", open);
    $("btnAssets").classList.toggle("active", open);
    if (open) refreshAssets();
  }

  function dragSplit(splitEl, getStart, apply) {
    splitEl.addEventListener("pointerdown", (e) => {
      e.preventDefault();
      splitEl.classList.add("dragging");
      document.body.classList.add("col-resizing");
      const startX = e.clientX;
      const start = getStart();
      let last = null;
      const move = (ev) => { last = apply(start, ev.clientX - startX); };
      const up = () => {
        splitEl.classList.remove("dragging");
        document.body.classList.remove("col-resizing");
        window.removeEventListener("pointermove", move);
        window.removeEventListener("pointerup", up);
        if (last) saveLayout(last);
      };
      window.addEventListener("pointermove", move);
      window.addEventListener("pointerup", up);
    });
  }

  // 章节树 | 编辑区
  dragSplit(splitTree,
    () => filePane.getBoundingClientRect().width,
    (start, dx) => {
      if (filePane.classList.contains("collapsed")) setTreeCollapsed(false);
      const w = Math.max(140, Math.min(460, start + dx));
      document.documentElement.style.setProperty("--tree-w", w + "px");
      return {tree: Math.round(w)};
    });

  // 编辑区 | 预览+检查器
  dragSplit(splitEdit,
    () => $("splitEdit").nextElementSibling.getBoundingClientRect().width,
    (start, dx) => {
      const maxW = Math.max(320, mainEl.clientWidth - 380);
      const w = Math.max(300, Math.min(maxW, start - dx));
      document.documentElement.style.setProperty("--right-w", w + "px");
      return {right: Math.round(w)};
    });

  // 双击分隔条恢复默认宽度
  splitTree.addEventListener("dblclick", () => {
    document.documentElement.style.setProperty("--tree-w", "220px");
    setTreeCollapsed(false);
    saveLayout({tree: 220});
  });
  splitEdit.addEventListener("dblclick", () => {
    document.documentElement.style.setProperty("--right-w", "520px");
    saveLayout({right: 520});
  });

  $("fpCollapse").addEventListener("click", () => setTreeCollapsed(!filePane.classList.contains("collapsed")));
  // P43：预览工具栏（Reload / Go to cursor / Float window）
  $("pvReload").addEventListener("click", () => { scheduleCheck(); setPreviewBar(true, "已重载"); });
  $("pvGoto").addEventListener("click", () => { source.focus(); const l = source.value.slice(0, source.selectionStart).split("\n").length; setPreviewBar(true, `光标在第 ${l} 行`); });
  $("pvFloat").addEventListener("click", () => { window.open(location.href, "_blank"); });
  $("btnAssets").addEventListener("click", () => setAssetOpen(!assetPane.classList.contains("open")));
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && assetPane.classList.contains("open")) setAssetOpen(false);
  });
  assetTabs.addEventListener("click", (e) => {
    const tab = e.target.closest(".asset-tab");
    if (!tab) return;
    assetCat = tab.dataset.cat;
    assetTabs.querySelectorAll(".asset-tab").forEach(t => {
      t.classList.toggle("active", t === tab);
    });
    renderAssets();
  });

  // ---- 拖剪式补全：素材 → 指令行 ----
  function directiveOptions(category, name) {
    if (category === "characters") {
      // V1：素材库「角色」拖拽——名字里带表情（"角色id 表情"）
      const parts = String(name).trim().split(/\s+/);
      const cid = parts[0] || "角色ID";
      const expr = parts.slice(1).join(" ") || "默认";
      return [
        { label: "@show " + cid + " " + expr + "（登场立绘）", text: "@show " + cid + " " + expr },
        { label: "@character " + cid + " #ffffff（注册角色）", text: "@character " + cid + " #ffffff" },
        { label: "@ " + cid + " （写一句台词）", text: "@ " + cid + " " },
      ];
    }
    if (category === "images") {
      const opts = [
        { label: "@bg " + name + "（作背景）", text: "@bg " + name },
        { label: "@cg " + name + "（作 CG / 回忆画面）", text: "@cg " + name },
      ];
      const cut = name.indexOf("_");
      if (cut > 0) {
        opts.push({
          label: "@show " + name.slice(0, cut) + " " + name.slice(cut + 1) + "（作立绘）",
          text: "@show " + name.slice(0, cut) + " " + name.slice(cut + 1),
        });
      } else {
        opts.push({ label: "@show 角色ID 表情（作立绘，需补参数）", text: "@show 角色ID 表情" });
      }
      return opts;
    }
    if (category === "anims") {
      const parts = name.split("_");
      if (parts.length >= 3) {
        const anim = parts[parts.length - 1];
        const expr = parts[parts.length - 2];
        const char = parts.slice(0, parts.length - 2).join("_");
        return [{ label: "@show " + char + " " + expr + " anim=" + anim, text: "@show " + char + " " + expr + " anim=" + anim }];
      }
      return [{ label: "@show 角色ID 表情 anim=" + name, text: "@show 角色ID 表情 anim=" + name }];
    }
    if (category === "videos") {
      return [{ label: "@video " + name + "（帧序列视频背景）", text: "@video " + name }];
    }
    if (category === "audio") {
      return [
        { label: "@music " + name + "（背景音乐）", text: "@music " + name },
        { label: "@sfx " + name + "（音效）", text: "@sfx " + name },
        { label: "@voice " + name + "（配音，须紧跟台词）", text: "@voice " + name },
      ];
    }
    return [];  // 字体不生成指令
  }

  function closeInsertMenu() {
    if (insertMenuEl) {
      insertMenuEl.remove();
      insertMenuEl = null;
      const onClose = insertMenuOnClose;
      insertMenuOnClose = null;
      if (onClose) onClose();
    }
  }

  function showInsertMenu(x, y, options, onPick, onClose) {
    closeInsertMenu();
    const menu = document.createElement("div");
    menu.className = "insert-menu";
    menu.style.left = Math.max(8, Math.min(x, window.innerWidth - 260)) + "px";
    menu.style.top = y + "px";
    options.forEach(opt => {
      const b = document.createElement("button");
      b.type = "button";
      b.textContent = opt.label;
      b.addEventListener("click", () => {
        insertMenuOnClose = null;  // 主动选择：不再触发“关闭后继续队列”
        closeInsertMenu();
        onPick(opt);
      });
      menu.appendChild(b);
    });
    document.body.appendChild(menu);
    insertMenuEl = menu;
    insertMenuOnClose = onClose || null;
    setTimeout(() => {
      document.addEventListener("mousedown", onDocDown, { once: true });
    }, 0);
    function onDocDown(e) {
      if (insertMenuEl && !insertMenuEl.contains(e.target)) closeInsertMenu();
    }
  }

  function insertDirective(text) {
    const val = source.value;
    const pos = source.selectionStart;
    const lineStart = val.lastIndexOf("\n", pos - 1) + 1;
    const atLineStart = val.slice(lineStart, pos).trim() === "";
    const payload = (atLineStart ? "" : "\n") + text + "\n";
    const caret = pos + payload.length;
    setSourceValue(val.slice(0, pos) + payload + val.slice(pos), caret, caret);
    updateLineNumbers();
    scheduleCheck();
    setPreviewBar(true, "已生成指令：" + text);
  }

  function handleAssetDrop(e, dataTransfer) {
    const raw = dataTransfer.getData("text/plain");
    if (!raw) return false;
    let payload;
    try { payload = JSON.parse(raw); } catch (err) { return false; }
    if (!payload || !payload.category || !payload.name) return false;
    const options = directiveOptions(payload.category, payload.name);
    if (!options.length) {
      setPreviewBar(false, "字体素材不生成指令：请在游戏设置里使用字体");
      return true;
    }
    showInsertMenu(e.clientX, e.clientY, options, (opt) => insertDirective(opt.text));
    return true;
  }

  source.addEventListener("dragover", (e) => {
    if (e.dataTransfer.types.includes("text/plain")) {
      e.preventDefault();
      e.dataTransfer.dropEffect = "copy";
    }
  });
  source.addEventListener("drop", (e) => {
    if (handleAssetDrop(e, e.dataTransfer)) e.preventDefault();
  });
  // 落在代码区外：不静默，明确提示
  document.addEventListener("drop", (e) => {
    if (e.defaultPrevented) return;
    if (assetPane.contains(e.target)) return;
    if (e.dataTransfer.getData("text/plain")) {
      setPreviewBar(false, "拖拽落点无效：请把素材拖到左侧代码区");
    }
  });

  // ---- 缺素材可视化（本地按素材清单比对，含行号）----
  function scanMissing() {
    if (!assetsReady) return [];
    const lines = source.value.split("\n");
    const has = (cat, n) => (assets[cat] || []).includes(n);
    const out = [];
    lines.forEach((raw, i) => {
      const line = raw.trim();
      let m;
      if ((m = line.match(/^@bg\s+(\S+)/))) {
        if (!has("images", m[1])) out.push({ line: i + 1, what: "@bg", msg: "images/" + m[1] + ".png" });
      } else if ((m = line.match(/^@video\s+(\S+)/))) {
        if (!has("videos", m[1])) out.push({ line: i + 1, what: "@video", msg: "images/videos/" + m[1] + "_001.png" });
      } else if ((m = line.match(/^@(music|sfx|voice)\s+(\S+)/))) {
        if (!has("audio", m[2])) out.push({ line: i + 1, what: "@" + m[1], msg: "audio/" + m[2] + ".ogg" });
      } else if ((m = line.match(/^@show\s+(\S+)\s+(\S+)/))) {
        const key = m[1] + "_" + m[2];
        const animOk = (assets.anims || []).some(n => n.startsWith(key + "_"));
        if (!has("images", key) && !animOk) {
          out.push({ line: i + 1, what: "@show", msg: "images/" + key + ".png" });
        }
      }
    });
    return out;
  }

  function jumpToLine(line) {
    const lines = source.value.split("\n");
    let pos = 0;
    for (let i = 0; i < line - 1 && i < lines.length; i++) pos += lines[i].length + 1;
    if (sourceWrap.style.display === "none") switchTab("source");
    source.focus();
    source.selectionStart = source.selectionEnd = pos;
    source.scrollTop = Math.max(0, (line - 3) * (1.6 * 14));
    updateLineNumbers();
  }

  function updateMissingBar() {
    const missing = scanMissing();
    if (!missing.length) {
      missingBar.style.display = "none";
      missingBar.innerHTML = "";
      return;
    }
    missingBar.style.display = "block";
    const shown = missing.slice(0, 8).map(m =>
      `<span class="ml" data-line="${m.line}">第 ${m.line} 行 ${m.what} 缺 ${m.msg}</span>`
    ).join("　·　");
    missingBar.innerHTML = `<b>缺素材 ${missing.length} 处</b>　` + shown +
      (missing.length > 8 ? `　…等共 ${missing.length} 处` : "");
    missingBar.querySelectorAll(".ml").forEach(el => {
      el.addEventListener("click", () => jumpToLine(parseInt(el.dataset.line, 10)));
    });
  }

  // ---- 新建游戏弹窗（与 CLI `py -m engine.cli new` 共用后端生成函数）----
  const newGameModal = $("newGameModal");
  const newGameName = $("newGameName");
  const newGameDir = $("newGameDir");
  const newGameErr = $("newGameErr");

  function openNewGame() {
    newGameErr.textContent = "";
    newGameName.value = "";
    newGameDir.value = "";
    newGameModal.style.display = "flex";
    setTimeout(() => newGameName.focus(), 30);
  }
  function closeNewGame() { newGameModal.style.display = "none"; }

  async function browseNewGameDir() {
    newGameErr.textContent = "";
    try {
      const resp = await fetch("/api/browse", {method: "POST"}).then(r => r.json());
      if (resp.ok && resp.path) {
        newGameDir.value = resp.path;
      } else if (!resp.ok) {
        newGameErr.textContent = resp.message || "目录选择不可用，可手动输入路径";
      }
    } catch (e) {
      newGameErr.textContent = "请求失败：" + e;
    }
  }

  async function submitNewGame() {
    const name = newGameName.value.trim();
    if (!name) { newGameErr.textContent = "游戏名不能为空"; return; }
    const base_dir = newGameDir.value.trim();
    // P46：主题/对齐选项随创建请求下发（后端 newgame.create_game 校验）
    const theme = $("newGameTheme").value;
    const align = $("newGameAlign").value;
    const payload = {name, theme, align};
    if (base_dir) payload.base_dir = base_dir;
    try {
      const resp = await fetch("/api/new", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload),
      }).then(r => r.json());
      if (resp.ok) {
        closeNewGame();
        await loadScript();
        await refreshAssets();
        statusEl.textContent = resp.message || "已创建";
        statusEl.className = "status ok";
      } else {
        newGameErr.textContent = resp.message || "创建失败";
      }
    } catch (e) {
      newGameErr.textContent = "请求失败：" + e;
    }
  }

  $("btnNew").addEventListener("click", openNewGame);
  $("newGameCancel").addEventListener("click", closeNewGame);
  $("newGameOk").addEventListener("click", submitNewGame);

  // ---- P46 富文本工具栏：选中文字包标记（引擎 richtext 渲染，语法见开发者指南）----
  function richWrap(open, close) {
    const ta = $("source");
    const s = ta.selectionStart, e = ta.selectionEnd;
    if (s === e) { statusEl.textContent = "先在剧本里选中一段文字"; statusEl.className = "status warn"; return; }
    ta.setRangeText(open + ta.value.slice(s, e) + close, s, e, "select");
    ta.dispatchEvent(new Event("input", {bubbles: true}));
    ta.focus();
  }
  document.querySelectorAll("#richToolbar [data-rich]").forEach(btn => {
    btn.addEventListener("click", () => richWrap(`{${btn.dataset.rich}}`, `{/${btn.dataset.rich}}`));
  });
  $("richColor").addEventListener("change", ev => {
    if (ev.target.value) richWrap(`{color=${ev.target.value}}`, "{/color}");
    ev.target.value = "";
  });
  $("richSize").addEventListener("change", ev => {
    if (ev.target.value) richWrap(`{size=${ev.target.value}}`, "{/size}");
    ev.target.value = "";
  });
  $("newGameBrowse").addEventListener("click", browseNewGameDir);
  newGameName.addEventListener("keydown", (e) => {
    if (e.key === "Enter") submitNewGame();
    if (e.key === "Escape") closeNewGame();
  });
  newGameModal.addEventListener("click", (e) => { if (e.target === newGameModal) closeNewGame(); });

  // ---- P35 打包发布：项目选择 / 必填档案 / 版本迭代 / 后台构建进度 ----
  const packModal = $("packModal");
  const packProject = $("packProject");
  const packMeta = $("packMeta");
  const packErrors = $("packErrors");
  const packStatusEl = $("packStatus");
  let packProjects = [];
  let packProfile = null;
  let packFolder = "";
  let packPollTimer = null;

  function packEsc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g,
      c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
  }
  function packSetStatus(text, cls) {
    packStatusEl.textContent = text;
    packStatusEl.className = "pack-status" + (cls ? " " + cls : "");
  }
  function packShowErrors(errors, fallback) {
    const list = Array.isArray(errors) ? errors : [];
    if (list.length) {
      packErrors.innerHTML = "请先完善以下必填项：<br>" + list.map(packEsc).join("<br>");
    } else {
      packErrors.textContent = fallback || "";
    }
  }
  function packCollectProfile() {
    const base = packProfile && typeof packProfile === "object" ? {...packProfile} : {};
    base.game_name = $("packName").value.trim();
    base.version = $("packVersion").value.trim();
    base.icon = $("packIcon").value.trim();
    base.release_notes = $("packNotes").value.trim();
    base.publisher = {
      name: $("packPublisher").value.trim(),
      account_id: $("packAccount").value.trim(),
      channel: $("packChannel").value.trim(),
      contact: $("packContact").value.trim(),
    };
    return base;
  }
  function packFillProfile(profile) {
    packProfile = profile || {};
    const pub = packProfile.publisher || {};
    $("packName").value = packProfile.game_name || packFolder || "";
    $("packVersion").value = packProfile.version || "1.0.0";
    $("packIcon").value = packProfile.icon || "icon.png";
    $("packPublisher").value = pub.name || "";
    $("packAccount").value = pub.account_id || "";
    $("packChannel").value = pub.channel || "";
    $("packContact").value = pub.contact || "";
    $("packNotes").value = packProfile.release_notes || "";
  }
  function packRenderMeta() {
    const row = packProjects.find(p => p.folder === packFolder);
    if (!row) { packMeta.innerHTML = ""; return; }
    const latest = row.latest || {};
    if (row.packaged) {
      packMeta.innerHTML =
        `<span class="pack-chip">已打包 v${packEsc(row.version)} · 构建 #${row.build_count}</span>` +
        `<span>上次产物：${packEsc(latest.output_dir || "")}</span>` +
        `<span>${packEsc(latest.built_at || "")}</span>`;
    } else {
      packMeta.innerHTML = `<span class="pack-chip warn">尚未打包</span>` +
        `<span>填写游戏名 / 图标 / 运营号后即可生成首个版本</span>`;
    }
  }
  async function packLoadProfile(folder) {
    packFolder = folder;
    packProfile = null;
    packErrors.textContent = "";
    if (!folder) {
      packSetStatus("没有可打包项目：请先在 games/ 下新建游戏。", "fail");
      return;
    }
    const resp = await fetch("/api/pack/profile?project=" + encodeURIComponent(folder))
      .then(r => r.json());
    if (!resp.ok) {
      packSetStatus(resp.message || "读取打包配置失败", "fail");
      return;
    }
    packFillProfile(resp.profile);
    packShowErrors(resp.errors);
    packRenderMeta();
    $("packBump").value = "";
    packSetStatus("已加载打包配置。修改后可直接打包，或先保存配置。");
  }
  async function packLoadProjects() {
    const resp = await fetch("/api/pack/projects").then(r => r.json());
    if (!resp.ok) {
      packSetStatus(resp.message || "读取项目列表失败", "fail");
      return;
    }
    packProjects = resp.projects || [];
    packProject.innerHTML = packProjects.length
      ? packProjects.map(p => `<option value="${packEsc(p.folder)}">${packEsc(p.game_name)}` +
          `${p.packaged ? " · v" + packEsc(p.version) + " · #" + p.build_count : " · 未打包"}</option>`).join("")
      : `<option value="">（暂无项目）</option>`;
    const current = packProjects.find(p => p.folder === resp.current);
    packFolder = current ? current.folder : (packProjects[0] ? packProjects[0].folder : "");
    if (packFolder) packProject.value = packFolder;
    await packLoadProfile(packFolder);
  }
  async function packPreviewVersion() {
    const bump = $("packBump").value;
    if (!packFolder) return;
    if (!bump) {
      $("packVersion").value = (packProfile && packProfile.version) || "1.0.0";
      return;
    }
    const resp = await fetch("/api/pack/version?project=" + encodeURIComponent(packFolder) +
      "&bump=" + encodeURIComponent(bump)).then(r => r.json());
    if (resp.ok) $("packVersion").value = resp.version;
  }
  async function packSaveProfile(silent) {
    if (!packFolder) return false;
    const resp = await fetch("/api/pack/profile", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({project: packFolder, profile: packCollectProfile()}),
    }).then(r => r.json());
    if (!resp.ok) {
      packShowErrors([], resp.message || "保存失败");
      return false;
    }
    packProfile = packCollectProfile();
    packShowErrors(resp.errors);
    if (!silent) packSetStatus(resp.message || "配置已保存", resp.errors && resp.errors.length ? "fail" : "ok");
    return true;
  }
  async function packPollJob(jobId) {
    clearInterval(packPollTimer);
    const tick = async () => {
      const resp = await fetch("/api/pack/status?id=" + encodeURIComponent(jobId))
        .then(r => r.json());
      if (!resp.ok) {
        packSetStatus(resp.message || "查询打包状态失败", "fail");
        clearInterval(packPollTimer);
        return;
      }
      const job = resp.job;
      if (job.status === "running") {
        packSetStatus(job.message || "正在打包……", "running");
        return;
      }
      clearInterval(packPollTimer);
      if (job.status === "ok") {
        const r = job.result || {};
        const mb = ((r.size_bytes || 0) / 1024 / 1024).toFixed(2);
        await packLoadProjects();
        packSetStatus(
          `打包完成：${r.game_name} v${r.version}（构建 #${r.build_number}）\n` +
          `产物：${r.output_dir}\n体积：${mb} MB\n运营号：${(r.publisher || {}).name || ""} / ${(r.publisher || {}).account_id || ""}`,
          "ok");
      } else {
        packSetStatus(job.message || "打包失败", "fail");
      }
    };
    tick();
    packPollTimer = setInterval(tick, 1500);
  }
  async function packStart() {
    if (!packFolder) {
      packSetStatus("请选择游戏项目", "fail");
      return;
    }
    $("packStart").disabled = true;
    packSetStatus("正在提交打包任务……", "running");
    const bump = $("packBump").value;
    const body = {
      project: packFolder,
      profile: packCollectProfile(),
      bump: bump || null,
      version: bump ? null : $("packVersion").value.trim(),
    };
    const resp = await fetch("/api/pack/build", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body),
    }).then(r => r.json()).finally(() => { $("packStart").disabled = false; });
    if (!resp.ok) {
      packShowErrors(resp.errors, resp.message || "打包失败");
      packSetStatus(resp.message || "打包失败", "fail");
      return;
    }
    packShowErrors([]);
    packPollJob(resp.job_id);
  }
  async function openPack() {
    packModal.style.display = "flex";
    packSetStatus("正在读取项目列表……", "running");
    try {
      await packLoadProjects();
    } catch (e) {
      packSetStatus("读取项目列表失败：" + e, "fail");
    }
  }
  function closePack() {
    packModal.style.display = "none";
    clearInterval(packPollTimer);
  }
  $("btnPack").addEventListener("click", openPack);
  $("packClose").addEventListener("click", closePack);
  $("packRefresh").addEventListener("click", async () => {
    packSetStatus("正在刷新项目列表……", "running");
    await packLoadProjects();
  });
  $("packProject").addEventListener("change", () => packLoadProfile($("packProject").value));
  $("packBump").addEventListener("change", packPreviewVersion);
  $("packSave").addEventListener("click", () => packSaveProfile(false));
  $("packStart").addEventListener("click", packStart);
  packModal.addEventListener("click", (e) => { if (e.target === packModal) closePack(); });

  // ---- 新手引导（三步浮层，纯前端，不进存档）----
  const OB_KEY = "gal_onboarding_done";
  const obMask = $("obMask"), obRing = $("obRing"), obCard = $("obCard");
  const obTitle = $("obTitle"), obDesc = $("obDesc"), obStepTag = $("obStepTag");
  const obPrev = $("obPrev"), obNext = $("obNext"), obSkip = $("obSkip");
  let obStep = 0;

  const OB_STEPS = [
    { title: "这是你的创作台",
      desc: "左边是工程文件与章节，中间写剧本，右边实时预览。新建游戏在顶部「文件 → 新建游戏」，场景/角色/素材/设置也在顶部右侧。",
      target: "fpTreeHead" },
    { title: "写第一行",
      desc: "在中间输入剧本。已为你插入一行示例对话「@ 主角 你好。」，改改文字，右侧会实时预览。",
      target: "source", insert: "@ 主角 你好。" },
    { title: "看效果 / 出包",
      desc: "右侧就是游戏画面的实时预览；点顶部「视图 → 运行游戏」或按 Ctrl+R 打开游戏窗口试玩，0 基础也能先看到画面。",
      target: "previewWrap" },
  ];

  function obMarkDone() {
    try { localStorage.setItem(OB_KEY, "1"); localStorage.setItem("gal_welcome_done", "1"); } catch (e) {}
  }
  // T3：首次启动弹一次欢迎卡（沿用本引导 obCard）；「帮助 → 新手引导」可随时重开。

  function obRender() {
    const s = OB_STEPS[obStep];
    obCard.dataset.step = String(obStep + 1);
    obStepTag.textContent = `第 ${obStep + 1} / ${OB_STEPS.length} 步`;
    obTitle.textContent = s.title;
    obDesc.textContent = s.desc;
    obPrev.style.visibility = obStep === 0 ? "hidden" : "visible";
    obNext.textContent = obStep === OB_STEPS.length - 1 ? "完成" : "下一步";
    if (s.insert && !source.value.includes(s.insert)) {
      const ins = (source.value && !source.value.endsWith("\n") ? "\n" : "") + s.insert + "\n";
      setSourceValue(source.value + ins, source.value.length + ins.length, source.value.length + ins.length);
      updateLineNumbers();
      scheduleCheck();
    }
    const el = $(s.target);
    if (el) {
      const r = el.getBoundingClientRect();
      const pad = 6;
      obRing.style.display = "block";
      obRing.style.left = (r.left - pad) + "px";
      obRing.style.top = (r.top - pad) + "px";
      obRing.style.width = (r.width + pad * 2) + "px";
      obRing.style.height = (r.height + pad * 2) + "px";
      if (s.target === "source") {
        source.focus();
        source.selectionStart = source.selectionEnd = source.value.length;
      }
    } else {
      obRing.style.display = "none";
    }
  }

  function obStart() {
    obStep = 0;
    obMask.style.display = "block";
    obCard.style.display = "block";
    obRender();
  }
  function obClose(markDone) {
    obMask.style.display = "none";
    obCard.style.display = "none";
    obRing.style.display = "none";
    if (markDone) obMarkDone();
  }

  obSkip.addEventListener("click", () => obClose(true));
  obPrev.addEventListener("click", () => { if (obStep > 0) { obStep--; obRender(); } });
  obNext.addEventListener("click", () => {
    if (obStep < OB_STEPS.length - 1) { obStep++; obRender(); } else { obClose(true); }
  });
  window.addEventListener("resize", () => { if (obCard.style.display !== "none") obRender(); });
  $("btnGuide").addEventListener("click", () => {
    try { localStorage.removeItem(OB_KEY); } catch (e) {}
    obStart();
  });

  // ---- 运行 demo ----
  btnRun.addEventListener("click", async () => {
    const text = source.value;
    dockLog("run", "请求运行游戏…");
    try {
      const resp = await fetch("/api/run", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({text, path: (window.__proCurPath && window.__proCurPath()) || undefined}),
      }).then(r => r.json());
      if (resp.ok) {
        dockLog("run", "游戏已启动（独立窗口，游戏输出不进此日志）");
        btnRun.classList.add("started");   // 图标/文字取舍：不覆盖 SVG 图标+文字，只加短暂高亮
        setTimeout(() => { btnRun.classList.remove("started"); }, 2000);
      } else {
        dockLog("run", "运行失败：" + (resp.message || "未知错误"));
        dockShow(true, "run");
        alert("运行失败：" + (resp.message || "未知错误"));
      }
    } catch (e) {
      dockLog("run", "运行请求失败：" + e);
      dockShow(true, "run");
      alert("运行请求失败：" + e);
    }
  });

  // ---- 加载默认剧本 ----
  async function loadScript() {
    try {
      const resp = await fetch("/api/script", {cache: "no-store"}).then(r => r.json());
      if (resp.text) {
        source.value = resp.text;
        resetHistory();
        filePathEl.textContent = (window.__proLabel && window.__proLabel()) ||
          (resp.path ? resp.path.split(/[\\/]/).pop() : "script.gal");
      }
      updateLineNumbers();
      scheduleCheck();
      updateInspectorFromCursor();
    } catch (e) {
      updateLineNumbers();
    }
  }

  // ---- P17 多文件工程桥：editor_pro.js 通过此对象与编辑器主逻辑协作 ----
  window.__editor = {
    getText: () => source.value,
    setText(t) { source.value = t; resetHistory(); updateLineNumbers(); scheduleCheck(); inspStamp = ""; updateInspectorFromCursor(); },
    gotoLine: jumpToLine,
    getCursorLine: () => source.value.slice(0, source.selectionStart).split("\n").length,
    setFileLabel: (p) => { filePathEl.textContent = p; },
    refresh: scheduleCheck,
    refreshAssets,
    getAssets: () => assets,
    assetURL,
    setPreviewMsg: setPreviewBar,
    toast: toast,          // P44-M1：标签上限等瞬时提示走右下角 toast（不会被异步检查覆盖）
    sourceEl: source,
    lineNumbersEl: lineNumbers,
    cardViewEl: cardView,
    switchToSource: () => switchTab("source"),
    // T5：查找替换的程序化改写（走主脚本撤销栈，undo 可还原）
    setSourceValue(v, a, b) {
      setSourceValue(v, a, b);
      source.dispatchEvent(new Event("input"));   // 同步脏标记/检查，替换后可 Ctrl+Z
    },
    onboardingClose: obClose,
    onCursor: (f) => _cursorFns.push(f),
    onChange: (f) => _changeFns.push(f),
    emitChange: _emitChange,
  };

  // 初始化
  loadLayout();
  (async () => {
    await loadConfig();
    await loadScript();
    refreshAssets();
    try { if (!localStorage.getItem(OB_KEY) && !localStorage.getItem("gal_welcome_done")) obStart(); } catch (e) {}
  })();
  // E-2：壳层 IIFE（菜单/命令面板）需要的撤销/重做接口
  window.undo = undo;
  window.redo = redo;
})();

