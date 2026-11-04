/* ===================================================================
   壳层（P38）：菜单栏下拉 / 活动栏视图切换 / 内嵌教程 / 命令面板 / 状态栏行号。
   从 editor_main.js 拆出（T16 域拆分）；只依赖全局 DOM 与 window.__editor* 桥。
   =================================================================== */
// ---- P38 壳层：菜单栏下拉 + 活动栏视图切换 ----
(function () {
  // 修复：$ 原本只定义在上一个 IIFE 里，壳层（菜单/活动栏）拿不到 →
  // 菜单展开与活动栏切换会在加载时静默报错。这里补一份作用域内的 $。
  const $ = (id) => document.getElementById(id);
  const mainEl = document.querySelector(".main");
  const dropdown = $("menuDropdown");

  // ---- M1.5：内嵌教程（帮助 → 教程 / 说明书；F1）----
  const helpPanel = $("helpPanel");
  const helpListEl = $("helpList");
  const helpContentEl = $("helpContent");
  let helpLoaded = false;

  function escHtml(t) {
    return String(t).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }
  function mdInline(t) {
    return escHtml(t)
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer">$1</a>');
  }
  function mdToHtml(md) {
    const lines = String(md).replace(/\r\n/g, "\n").split("\n");
    const out = [];
    let i = 0, list = null, code = null, table = null;
    const closeList = () => { if (list) { out.push(list === "ol" ? "</ol>" : "</ul>"); list = null; } };
    const closeTable = () => { if (table) { out.push("</tbody></table>"); table = null; } };
    const flush = () => { closeList(); closeTable(); };
    while (i < lines.length) {
      const line = lines[i];
      const fence = line.match(/^\s*```/);
      if (fence) {
        if (code === null) { flush(); code = []; }
        else { out.push("<pre><code>" + escHtml(code.join("\n")) + "</code></pre>"); code = null; }
        i++; continue;
      }
      if (code !== null) { code.push(line); i++; continue; }
      if (!line.trim()) { flush(); i++; continue; }
      const h = line.match(/^(#{1,4})\s+(.*)$/);
      if (h) { flush(); const n = h[1].length; out.push("<h" + n + ">" + mdInline(h[2]) + "</h" + n + ">"); i++; continue; }
      if (/^\s*([-*_])\1{2,}\s*$/.test(line)) { flush(); out.push("<hr>"); i++; continue; }
      if (/^\s*\|/.test(line) && i + 1 < lines.length && /^\s*\|?[\s:-]+\|/.test(lines[i + 1])) {
        flush();
        const cells = (row) => row.replace(/^\s*\|/, "").replace(/\|\s*$/, "").split("|").map(c => mdInline(c.trim()));
        out.push("<table><thead><tr>" + cells(line).map(c => "<th>" + c + "</th>").join("") + "</tr></thead><tbody>");
        table = true; i += 2; continue;
      }
      if (table && /^\s*\|/.test(line)) {
        const cells = line.replace(/^\s*\|/, "").replace(/\|\s*$/, "").split("|").map(c => mdInline(c.trim()));
        out.push("<tr>" + cells.map(c => "<td>" + c + "</td>").join("") + "</tr>"); i++; continue;
      }
      if (/^\s*>\s?/.test(line)) { flush(); out.push("<blockquote>" + mdInline(line.replace(/^\s*>\s?/, "")) + "</blockquote>"); i++; continue; }
      const ul = line.match(/^\s*[-*]\s+(.*)$/);
      const ol = line.match(/^\s*\d+[.)]\s+(.*)$/);
      if (ul || ol) {
        closeTable();
        const kind = ul ? "ul" : "ol";
        if (list !== kind) { closeList(); out.push(kind === "ol" ? "<ol>" : "<ul>"); list = kind; }
        out.push("<li>" + mdInline((ul || ol)[1]) + "</li>"); i++; continue;
      }
      flush();
      out.push("<p>" + mdInline(line) + "</p>");
      i++;
    }
    flush();
    return out.join("");
  }

  function toggleHelp(force) {
    const show = force === undefined ? helpPanel.classList.contains("hidden") : force;
    helpPanel.classList.toggle("hidden", !show);
    if (show && !helpLoaded) loadHelpIndex();
  }

  async function loadHelpIndex() {
    helpLoaded = true;
    try {
      const r = await fetch("/api/help");
      const data = await r.json();
      const docs = data.docs || [];
      if (!docs.length) {
        helpListEl.innerHTML = '<div class="help-empty">没有找到教程文件（发行包是否漏带 docs/？）</div>';
        return;
      }
      helpListEl.innerHTML = "";
      docs.forEach((doc) => {
        const item = document.createElement("div");
        item.className = "help-item";
        item.textContent = doc.title;
        item.dataset.id = doc.id;
        item.addEventListener("click", () => loadHelpDoc(doc.id, item));
        helpListEl.appendChild(item);
      });
      loadHelpDoc(docs[0].id, helpListEl.firstChild);
    } catch (e) {
      helpListEl.innerHTML = '<div class="help-empty">教程加载失败：' + escHtml(String(e)) + "</div>";
    }
  }

  async function loadHelpDoc(id, item) {
    helpListEl.querySelectorAll(".help-item").forEach(el => el.classList.remove("active"));
    if (item) item.classList.add("active");
    helpContentEl.innerHTML = '<div class="help-empty">加载中…</div>';
    try {
      const r = await fetch("/api/help/doc?id=" + encodeURIComponent(id));
      const data = await r.json();
      if (!data.ok) throw new Error(data.message || "读取失败");
      helpContentEl.innerHTML = mdToHtml(data.text || "");
      helpContentEl.scrollTop = 0;
    } catch (e) {
      helpContentEl.innerHTML = '<div class="help-empty">' + escHtml(String(e)) + "</div>";
    }
  }

  $("actHelp").addEventListener("click", () => toggleHelp());
  $("helpClose").addEventListener("click", () => toggleHelp(false));
  window.addEventListener("keydown", (ev) => {
    const mod = ev.ctrlKey || ev.metaKey;
    if (ev.key === "F1") { ev.preventDefault(); toggleHelp(); }
    if (ev.key === "Escape" && !helpPanel.classList.contains("hidden")) toggleHelp(false);
    // 菜单 / 提示里写出的快捷键必须真能触发；否则用户按键无反应
    const clickBtn = (id) => { const el = $(id); if (el && !el.disabled) el.click(); };
    if (ev.key === "F5") {
      ev.preventDefault(); clickBtn("btnRun");
    } else if (!ev.shiftKey && mod && (ev.key === "r" || ev.key === "R")) {
      ev.preventDefault(); clickBtn("btnRun");
    } else if (mod && !ev.shiftKey && (ev.key === "p" || ev.key === "P")) {
      ev.preventDefault(); clickBtn("btnPack");
    } else if (mod && (ev.key === "n" || ev.key === "N")) {
      ev.preventDefault(); clickBtn("btnNew");
    } else if (mod && ev.key === ",") {
      ev.preventDefault(); clickBtn("btnSettings");
    }
    // E-2：撤销/重做 + 命令面板
    if (mod && (ev.key === "z" || ev.key === "Z")) {
      ev.preventDefault();
      if (ev.shiftKey) redo(); else undo();
    } else if (mod && (ev.key === "y" || ev.key === "Y")) {
      ev.preventDefault(); redo();
    } else if (mod && ev.shiftKey && (ev.key === "p" || ev.key === "P")) {
      ev.preventDefault(); openCommandPalette();
    } else if (mod && (ev.key === "j" || ev.key === "J")) {
      ev.preventDefault(); if (window.__dockToggle) window.__dockToggle();
    } else if (ev.key === "Escape") {
      closeCommandPalette();
    }
  });

  // 菜单定义（label, shortcut, action）
  const MENUS = {
    file: [
      { label: "新建游戏", shortcut: "Ctrl+N", action: () => $("btnNew").click() },
      { label: "保存", shortcut: "Ctrl+S", action: () => $("btnSave").click() },
      { label: "新建章节", action: () => $("btnNewChapter").click() },
      { label: "打包发布", shortcut: "Ctrl+P", action: () => $("btnPack").click() },
    ],
    edit: [
      { label: "撤销", shortcut: "Ctrl+Z", action: undo },
      { label: "重做", shortcut: "Ctrl+Y", action: redo },
    ],
    view: [
      { label: "源码视图", action: () => switchTab("source") },
      { label: "JSON 视图", minLevel: 3, action: () => switchTab("json") },
      { label: "卡片视图", minLevel: 3, action: () => switchTab("card") },
      { label: "素材库", action: () => $("btnAssets").click() },
      { label: "底部面板", shortcut: "Ctrl+J", action: () => window.__dockToggle && window.__dockToggle() },
      { label: "游戏界面位置（左 / 右）", action: () => window.__previewSideToggle && window.__previewSideToggle() },
      { label: "切换主题（深色 / 浅色）", action: () => window.__themeToggle && window.__themeToggle() },
      { label: "场景编辑（可视化）", action: () => window.__openSceneEditor && window.__openSceneEditor() },
      { label: "角色库（角色与立绘）", action: () => window.__openCharacterManager && window.__openCharacterManager() },
      { label: "UI 设计区", minLevel: 3, action: () => $("btnUIDesign").click() },
      { label: "桌宠（实验）", minLevel: 3, action: () => window.__petToggle && window.__petToggle() },
      { label: "设置中心", shortcut: "Ctrl+,", action: () => $("btnSettings").click() },
      // E9：档位切换（命令面板 / 视图菜单都能改）
      { label: "档位：Level 1 新手", action: () => window.__editorLevel && window.__editorLevel.set(1) },
      { label: "档位：Level 2 默认", action: () => window.__editorLevel && window.__editorLevel.set(2) },
      { label: "档位：Level 3 专业", action: () => window.__editorLevel && window.__editorLevel.set(3) },
    ],
    run: [
      { label: "运行游戏", shortcut: "F5", action: () => $("btnRun").click() },
    ],
    help: [
      { label: "教程 / 说明书", shortcut: "F1", action: () => toggleHelp() },
      { label: "新手引导", action: () => $("btnGuide").click() },
      { label: "关于 MYONL", action: () => alert("MYONL 引擎 · 视觉小说创作工具\n极简字母月 · Mooki 发光小团子") },
    ],
  };

  function switchTab(name) {
    // P1：视图菜单与页签共用主编辑器入口；卡片视图必须走 enterCardView，不能只切 display
    if (window.__switchTab) {
      window.__switchTab(name);
      return;
    }
    // 兜底：主编辑器未就绪时只切显示，避免菜单点击报错
    document.querySelectorAll(".tab").forEach(t =>
      t.classList.toggle("active", t.dataset.tab === name));
    ["source", "json", "card"].forEach(v => {
      const el = document.getElementById(v + (v === "source" ? "Wrap" : "View"));
      if (el) el.style.display = (v === name) ? (v === "source" ? "flex" : "block") : "none";
    });
  }

  // ---- E9：按档位裁剪菜单项（Level 1 新手看不到专业入口；Level 3 全开） ----
  function _levelNow() {
    return (window.__editorLevel && window.__editorLevel.get()) || 2;
  }
  function _menuVisible(item) {
    return !item.minLevel || _levelNow() >= item.minLevel;
  }

  function openMenu(btn, key) {
    document.querySelectorAll(".menu-item").forEach(m => m.classList.remove("active"));
    btn.classList.add("active");
    const items = (MENUS[key] || []).filter(_menuVisible);
    dropdown.innerHTML = items.map(it =>
      `<div class="menu-dd-item" data-action="${it.label}"><span>${it.label}</span>` +
      (it.shortcut ? `<span class="shortcut">${it.shortcut}</span>` : "") + `</div>`
    ).join("");
    const rect = btn.getBoundingClientRect();
    dropdown.style.left = rect.left + "px";
    dropdown.classList.add("open");
    dropdown.querySelectorAll(".menu-dd-item").forEach((el, i) => {
      el.addEventListener("click", () => { items[i].action(); closeMenu(); });
    });
  }
  function closeMenu() {
    document.querySelectorAll(".menu-item").forEach(m => m.classList.remove("active"));
    dropdown.classList.remove("open");
  }

  // ---- E-2：命令面板 ----
  const cmdMask = $("cmdPaletteMask");
  const cmdInput = $("cmdInput");
  const cmdList = $("cmdList");
  let _cmdItems = [];   // {label, shortcut, action}
  let _cmdSel = 0;
  function _flattenCmds() {
    const flat = [];
    Object.values(MENUS).forEach(arr => arr.filter(_menuVisible).forEach(it => flat.push(it)));
    return flat;
  }
  function _fuzzyMatch(text, q) {
    if (!q) return true;
    const tl = text.toLowerCase(), ql = q.toLowerCase();
    let ti = 0;
    for (let qi = 0; qi < ql.length; qi++) {
      ti = tl.indexOf(ql[qi], ti);
      if (ti < 0) return false;
      ti++;
    }
    return true;
  }
  function _renderCmdList(q) {
    const items = _cmdItems.filter(it => _fuzzyMatch(it.label, q));
    if (!items.length) {
      cmdList.innerHTML = '<div class="cmd-empty">无匹配命令</div>';
      _cmdSel = 0;
      return;
    }
    if (_cmdSel >= items.length) _cmdSel = items.length - 1;
    cmdList.innerHTML = items.map((it, i) =>
      `<div class="cmd-item${i === _cmdSel ? " sel" : ""}" data-i="${i}">` +
      `<span class="cmd-label">${it.label}</span>` +
      (it.shortcut ? `<span class="cmd-sc">${it.shortcut}</span>` : "") +
      `</div>`
    ).join("");
    cmdList.querySelectorAll(".cmd-item").forEach(el => {
      el.addEventListener("click", () => {
        const idx = parseInt(el.dataset.i, 10);
        closeCommandPalette();
        items[idx].action();
      });
    });
  }
  function openCommandPalette() {
    _cmdItems = _flattenCmds();
    _cmdSel = 0;
    cmdInput.value = "";
    cmdMask.classList.remove("hidden");
    setTimeout(() => cmdInput.focus(), 0);
    _renderCmdList("");
  }
  function closeCommandPalette() {
    cmdMask.classList.add("hidden");
  }
  cmdInput.addEventListener("input", () => { _cmdSel = 0; _renderCmdList(cmdInput.value); });
  cmdInput.addEventListener("keydown", (e) => {
    const items = _cmdItems.filter(it => _fuzzyMatch(it.label, cmdInput.value));
    if (e.key === "ArrowDown") { e.preventDefault(); _cmdSel = Math.min(_cmdSel + 1, items.length - 1); _renderCmdList(cmdInput.value); }
    else if (e.key === "ArrowUp") { e.preventDefault(); _cmdSel = Math.max(_cmdSel - 1, 0); _renderCmdList(cmdInput.value); }
    else if (e.key === "Enter") {
      e.preventDefault();
      if (items[_cmdSel]) { const act = items[_cmdSel].action; closeCommandPalette(); act(); }
    }
  });
  cmdMask.addEventListener("click", (e) => { if (e.target === cmdMask) closeCommandPalette(); });

  // ---- E4：入门任务进度（自动勾选、可折叠、不弹窗）----
  (function tasks() {
    const headEl = $("fpTaskHead"), listEl = $("fpTask"), countEl = $("fpTaskCount");
    if (!headEl || !listEl) return;
    const KEY = "gal_tasks_done", COLLAPSE = "gal_tasks_collapsed";
    let done = {};
    try { done = JSON.parse(localStorage.getItem(KEY) || "{}") || {}; } catch (e) { done = {}; }
    const ITEMS = [
      { id: "run", label: "运行一次（▶ 运行）" },
      { id: "bg", label: "换过背景（@bg）" },
      { id: "choice", label: "加过选项（@choice）" },
      { id: "asset", label: "导入/用过素材" },
      { id: "pack", label: "打包一次" },
    ];
    function render() {
      const n = ITEMS.filter(it => done[it.id]).length;
      if (countEl) countEl.textContent = n + "/" + ITEMS.length;
      listEl.innerHTML = ITEMS.map(it =>
        '<div class="fp-task-item' + (done[it.id] ? " done" : "") + '">' +
        '<span class="fp-task-mark">' + (done[it.id] ? "✓" : "○") + "</span>" +
        "<span>" + it.label + "</span></div>").join("");
    }
    function mark(id) {
      if (done[id]) return;
      done[id] = 1;
      try { localStorage.setItem(KEY, JSON.stringify(done)); } catch (e) {}
      render();
    }
    window.__taskDone = mark;   // 其他模块成功后也可调用
    try {
      if (localStorage.getItem(COLLAPSE) === "1") {
        listEl.classList.add("hidden");
        $("fpTaskChev").textContent = "▸";
      }
    } catch (e) {}
    headEl.addEventListener("click", () => {
      const hidden = listEl.classList.toggle("hidden");
      $("fpTaskChev").textContent = hidden ? "▸" : "▾";
      try { localStorage.setItem(COLLAPSE, hidden ? "1" : "0"); } catch (e) {}
    });
    // 文本类任务：内容里出现对应指令即勾选（不打断写作）
    function scan() {
      let text = "";
      try { text = (window.__editor && window.__editor.getText()) || ""; } catch (e) { return; }
      if (/^\s*@bg\s+\S/m.test(text)) mark("bg");
      if (/^\s*@choice\s*:/m.test(text)) mark("choice");
      if (/^\s*@(?:music|sfx|voice|cg|video)\s+\S/m.test(text)) mark("asset");
    }
    try { if (window.__editor && window.__editor.onChange) window.__editor.onChange(scan); } catch (e) {}
    setTimeout(scan, 800);
    const runBtn = $("btnRun");
    if (runBtn) runBtn.addEventListener("click", () => mark("run"));
    const packBtn = $("btnPack");
    if (packBtn) packBtn.addEventListener("click", () => mark("pack"));
    render();
  })();

  document.querySelectorAll(".menu-item").forEach(btn => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      if (btn.classList.contains("active")) { closeMenu(); return; }
      openMenu(btn, btn.dataset.menu);
    });
  });
  document.addEventListener("click", closeMenu);

  // 活动栏视图切换
  function setView(view) {
    document.querySelectorAll(".act-btn").forEach(b =>
      b.classList.toggle("active", b.dataset.view === view));
    if (view === "files") {
      mainEl.classList.remove("hide-files", "show-assets");
    } else if (view === "assets") {
      mainEl.classList.add("hide-files", "show-assets");
    } else if (view === "settings") {
      $("btnSettings").click();
      // 设置按钮切回 files 视图
      document.querySelector('.act-btn[data-view="files"]').click();
    }
  }
  document.querySelectorAll(".act-btn").forEach(b =>
    b.addEventListener("click", () => setView(b.dataset.view)));

  // 状态栏行号同步
  const src = $("source");
  function updateSbLine() {
    const lines = src.value.slice(0, src.selectionStart).split("\n").length;
    $("sbLine").textContent = "第 " + lines + " 行";
  }
  src.addEventListener("input", updateSbLine);
  src.addEventListener("click", updateSbLine);
  src.addEventListener("keyup", updateSbLine);
})();
