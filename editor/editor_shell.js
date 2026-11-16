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

  // P61：菜单里也能导出单文件——不用先翻到「UI 设计」弹窗底部
  function say(msg) {
    if (typeof window.toast === "function") window.toast(msg);
    else if (window.__toast) window.__toast(msg);
  }

  function exportSingleHtml() {
    fetch("/api/export-single", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    })
      .then((r) => r.json())
      .then((d) => {
        if (!d.ok) { say(d.message || "导出失败"); return; }
        var a = document.createElement("a");
        a.href = new URL(d.url, window.location.href).href;
        a.target = "_blank";
        a.rel = "noopener";
        a.click();
        say("已导出单文件（" + d.kb + " KB）——手机浏览器直接打开就能玩");
        if (d.missing && d.missing.length) {
          say("注意：有 " + d.missing.length + " 个素材找不到（" + d.missing.slice(0, 3).join("、")
            + "），游戏里会是空白");
        }
      })
      .catch((e) => say("导出失败：" + e));
  }

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
      { label: "导出一个 HTML（手机能直接打开）", action: exportSingleHtml },
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

  // ===== P59：窄屏（手机）布局 —— 侧栏和预览变抽屉，编辑区铺满 =====
  // 三栏在 390px 宽下每栏只剩 100px，根本没法写剧本。窄屏只留「编辑区 + 底部悬浮按钮」，
  // 侧栏、右侧预览各自变成从边缘滑出的抽屉，点外面 / Esc 关掉。
  var mobileMQ = window.matchMedia("(max-width: 860px)");
  var maskEl = null;
  var dockEl = null;

  function closeDrawers() {
    mainEl.classList.remove("mobile-tree-open", "mobile-preview-open", "mobile-asset-open");
    if (maskEl) maskEl.classList.remove("on");
  }

  function syncMask() {
    if (!maskEl) return;
    var open = mainEl.classList.contains("mobile-tree-open") ||
               mainEl.classList.contains("mobile-preview-open") ||
               mainEl.classList.contains("mobile-asset-open");
    maskEl.classList.toggle("on", open);
  }

  function toggleDrawer(cls) {
    var willOpen = !mainEl.classList.contains(cls);
    closeDrawers();
    if (willOpen) mainEl.classList.add(cls);
    syncMask();
  }

  function buildMobileUI() {
    if (dockEl) return;
    maskEl = document.createElement("div");
    maskEl.className = "mobile-mask";
    maskEl.addEventListener("click", closeDrawers);
    document.body.appendChild(maskEl);

    dockEl = document.createElement("div");
    dockEl.className = "mobile-dock";
    dockEl.innerHTML =
      '<button type="button" class="m-dock-btn" id="mDockTree" title="工程文件 / 章节大纲">📁</button>' +
      '<button type="button" class="m-dock-btn" id="mDockAssets" title="素材库">🗂</button>' +
      '<button type="button" class="m-dock-btn" id="mDockPreview" title="实时预览">👁</button>' +
      '<button type="button" class="m-dock-btn m-dock-run" id="mDockRun" title="运行">▶</button>';
    document.body.appendChild(dockEl);

    $("mDockTree").addEventListener("click", function () { toggleDrawer("mobile-tree-open"); });
    $("mDockAssets").addEventListener("click", function () { toggleDrawer("mobile-asset-open"); });
    $("mDockPreview").addEventListener("click", function () { toggleDrawer("mobile-preview-open"); });
    $("mDockRun").addEventListener("click", function () {
      var run = $("btnRun");
      if (run) run.click();
    });

    // P65：手机端底部 tab。真机上「右上 4 个浮圆按钮 + 三行顶栏」把正文挤成半屏，
    // 改成一条纯文字 tab：剧本 / 素材 / 外观 / 预览 / 导出（不放 emoji，图标风格不统一反而乱）。
    var tabbar = document.createElement("div");
    tabbar.className = "m-tabbar";
    tabbar.innerHTML =
      '<button type="button" class="m-tab active" data-tab="script">剧本</button>' +
      '<button type="button" class="m-tab" data-tab="assets">素材</button>' +
      '<button type="button" class="m-tab" data-tab="look">外观</button>' +
      '<button type="button" class="m-tab" data-tab="preview">预览</button>' +
      '<button type="button" class="m-tab" data-tab="export">导出</button>';
    document.body.appendChild(tabbar);

    function setTab(which) {
      tabbar.querySelectorAll(".m-tab").forEach(function (b) {
        b.classList.toggle("active", b.dataset.tab === which);
      });
    }

    tabbar.addEventListener("click", function (e) {
      var btn = e.target.closest ? e.target.closest(".m-tab") : null;
      if (!btn) return;
      var which = btn.dataset.tab;
      setTab(which);
      if (which === "script") { closeDrawers(); return; }
      if (which === "assets") { toggleDrawer("mobile-asset-open"); return; }
      if (which === "preview") { toggleDrawer("mobile-preview-open"); return; }
      if (which === "look") {
        closeDrawers();
        var ui = $("btnUIDesign");
        if (ui) ui.click();
        return;
      }
      if (which === "export") {
        closeDrawers();
        var ui2 = $("btnUIDesign");
        if (ui2) ui2.click();       // 导出在「界面设计」弹窗里，手机端一步到位
        return;
      }
    });

    // 顶栏「⋯」：展开/收起工具条（默认收起，正文优先）
    var mainEl2 = document.querySelector(".main") || document.body;
    var more = document.createElement("button");
    more.className = "icon-btn";
    more.id = "mToolsToggle";
    more.type = "button";
    more.title = "展开工具条";
    more.innerHTML = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" '
      + 'stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">'
      + '<circle cx="5" cy="12" r="1.4"/><circle cx="12" cy="12" r="1.4"/>'
      + '<circle cx="19" cy="12" r="1.4"/></svg>';
    var fsBtn = document.createElement("button");
    fsBtn.className = "icon-btn";
    fsBtn.id = "mFullscreen";
    fsBtn.type = "button";
    fsBtn.title = "全屏（隐藏浏览器工具栏）";
    fsBtn.innerHTML = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" '
      + 'stroke="currentColor" stroke-width="1.9" stroke-linecap="round" aria-hidden="true">'
      + '<path d="M4 9V5h4M16 5h4v4M20 15v4h-4M8 19H4v-4"/></svg>';
    var mbActs = document.querySelector(".menubar .mb-acts");
    var anchor = mbActs || document.querySelector(".menubar");
    if (anchor) {
      // 手机端左上角「‹ 作品」：回工作台（否则进了编辑器就出不去）
      var back = document.createElement("button");
      back.className = "icon-btn";
      back.id = "mHomeBack";
      back.type = "button";
      back.title = "返回作品列表";
      back.innerHTML = '<svg viewBox="0 0 24 24" width="17" height="17" fill="none" '
        + 'stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">'
        + '<path d="M14.5 5.5L8 12l6.5 6.5"/></svg>';
      back.addEventListener("click", function () {
        if (window.__myonlShowHome) window.__myonlShowHome();
      });
      anchor.parentNode.insertBefore(back, anchor.parentNode.firstChild);
      anchor.parentNode.insertBefore(fsBtn, anchor);
      anchor.parentNode.insertBefore(more, anchor);
      more.addEventListener("click", function () {
        var open = mainEl2.classList.toggle("m-tools-open");
        more.classList.toggle("active", open);
        more.title = open ? "收起工具条" : "展开工具条";
        if (open) closeDrawers();
      });
      fsBtn.addEventListener("click", function () {
        // 手机上「竖屏必须全屏」：进全屏后浏览器工具栏消失，视口高度才是整块屏幕。
        var el = document.documentElement;
        var req = el.requestFullscreen || el.webkitRequestFullscreen || el.msRequestFullscreen;
        if (!req) return;
        var p = req.call(el);
        if (p && p.then) p.catch(function () {});
      });
    }

    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") closeDrawers();
    });

    // 搜索框在手机上收成一个图标，点一下才展开（不然 390 宽塞不下菜单 + 搜索 + 入口）
    var sWrap = $("mbSearchWrap");
    if (sWrap) {
      sWrap.addEventListener("click", function () {
        if (!mobileMQ.matches || sWrap.classList.contains("open")) return;
        sWrap.classList.add("open");
        var inp = $("mbSearchInput");
        if (inp) { setTimeout(function () { inp.focus(); }, 0); }
      });
      document.addEventListener("click", function (e) {
        if (!sWrap.classList.contains("open")) return;
        if (sWrap.contains(e.target)) return;
        sWrap.classList.remove("open");
      });
    }
  }

  // P65 诊断口：手机上的定位偏差必须靠数据判，不靠猜。
  // 加 ?diag=1 才显示（普通用户看不到，验收脚本和真机排查用）。
  (function setupDiag() {
    if (location.search.indexOf("diag=1") < 0) return;
    var d = document.createElement("div");
    d.style.cssText = "position:fixed;left:0;top:0;z-index:9999;background:#000c;"
      + "color:#7f7;font:11px/1.5 monospace;padding:6px;white-space:pre;pointer-events:none";
    document.body.appendChild(d);
    setInterval(function () {
      var t = document.querySelector(".m-tabbar");
      var r = t ? t.getBoundingClientRect() : null;
      var cs = t ? getComputedStyle(t) : null;
      d.textContent = [
        "inner " + window.innerWidth + "x" + window.innerHeight,
        "vv " + (window.visualViewport
          ? Math.round(window.visualViewport.width) + "x" + Math.round(window.visualViewport.height)
            + " s" + window.visualViewport.scale.toFixed(2) : "-"),
        "dpr " + (window.devicePixelRatio || 1),
        "body " + document.body.scrollHeight + " doc " + document.documentElement.scrollHeight,
        "tab " + (r ? "top" + Math.round(r.top) + " h" + Math.round(r.height)
          + " gap" + Math.round(window.innerHeight - r.bottom) : "-"),
        "css " + (cs ? cs.height + " / bottom " + cs.bottom : "-"),
      ].join("\n");
    }, 400);
  })();

  function syncMobileLayout() {
    if (mobileMQ.matches) {
      buildMobileUI();
      buildKeybar();
    } else {
      closeDrawers();
      if (keybarEl) keybarEl.classList.remove("show");
      document.body.classList.remove("m-kb-open");
    }
  }
  // ---- 手机键盘快捷条：@ 系列指令 + 缩进 + 撤销。手机上打 "@choice:" 太慢。----
  var keybarEl = null;
  var KB_KEYS = [
    ["at", "@", "@", null],
    ["choice", "@choice:", "@choice:\n    ", null],
    ["if", "@if", "@if ", null],
    ["set", "@set", "@set ", null],
    ["label", "@label", "@label ", null],
    ["show", "@show", "@show ", null],
    ["arrow", "→", "-> ", null],
    ["indent", "缩进", null, "indent"],
    ["newline", "换行", "\n", null],
    ["undo", "撤销", null, "undo"]
  ];

  function insertAtCursor(text) {
    var e = $("source");
    if (!e) return;
    e.focus();
    var s = e.selectionStart;
    if (typeof s !== "number") s = e.value.length;
    var t = e.selectionEnd;
    if (typeof t !== "number") t = s;
    e.setRangeText(text, s, t, "end");
    e.dispatchEvent(new Event("input", { bubbles: true }));
    e.dispatchEvent(new Event("keyup", { bubbles: true }));
  }

  function indentCurrentLine() {
    var e = $("source");
    if (!e) return;
    e.focus();
    var s = e.selectionStart || 0;
    var lineStart = e.value.lastIndexOf("\n", s - 1) + 1;
    e.setRangeText("    ", lineStart, lineStart, "end");
    e.selectionStart = e.selectionEnd = s + 4;
    e.dispatchEvent(new Event("input", { bubbles: true }));
  }

  // 键盘弹起时（尤其 iOS 不缩 viewport）把快捷条顶到键盘上方，dock / 状态栏让位
  function syncKeyboardOffset() {
    var vv = window.visualViewport;
    var gap = 0;
    if (vv) gap = Math.max(0, window.innerHeight - (vv.height + vv.offsetTop));
    var kbOpen = gap > 80;
    if (keybarEl) keybarEl.style.bottom = (kbOpen ? Math.round(gap) : 30) + "px";
    document.body.classList.toggle("m-kb-open", kbOpen);
  }

  function buildKeybar() {
    if (keybarEl) return;
    keybarEl = document.createElement("div");
    keybarEl.className = "m-keybar";
    KB_KEYS.forEach(function (k) {
      var b = document.createElement("button");
      b.type = "button";
      b.id = "m-kb-" + k[0];
      b.className = "m-kb" + (k[2] ? "" : " act");
      b.textContent = k[1];
      // pointerdown + preventDefault：点快捷键时输入框不能失焦，否则插入位置丢失
      b.addEventListener("pointerdown", function (ev) { ev.preventDefault(); });
      b.addEventListener("click", function () {
        if (k[3] === "indent") indentCurrentLine();
        else if (k[3] === "undo") { try { document.execCommand("undo"); } catch (err) {} }
        else insertAtCursor(k[2]);
        syncKeyboardOffset();
      });
      keybarEl.appendChild(b);
    });
    document.body.appendChild(keybarEl);

    var src = $("source");
    if (src) {
      src.addEventListener("focus", function () {
        if (!mobileMQ.matches) return;
        keybarEl.classList.add("show");
        document.body.classList.add("m-typing");
        syncKeyboardOffset();
      });
      src.addEventListener("blur", function () {
        // 点快捷条本身不该收起来（pointerdown 已 preventDefault，正常不会失焦）
        setTimeout(function () {
          if (document.activeElement === src || keybarEl.contains(document.activeElement)) return;
          keybarEl.classList.remove("show");
          document.body.classList.remove("m-typing", "m-kb-open");
          if (keybarEl) keybarEl.style.bottom = "30px";
        }, 60);
      });
    }
    if (window.visualViewport) {
      window.visualViewport.addEventListener("resize", syncKeyboardOffset);
      window.visualViewport.addEventListener("scroll", syncKeyboardOffset);
    }
  }

  // 所有函数/变量都就位后再初始化一次（var 提升会让早调用拿到 undefined）
  if (mobileMQ.addEventListener) mobileMQ.addEventListener("change", syncMobileLayout);
  else if (mobileMQ.addListener) mobileMQ.addListener(syncMobileLayout);
  syncMobileLayout();
})();
