/* MYONL 编辑器 P17：多文件工程前台（文件树/缓冲切换/保存/新建章节/
   跨文件大纲/include 跳转/场景时间线/当前场景素材面板/卡片跨文件总览）。
   通过 window.__editor 桥与 index.html 主逻辑协作，主逻辑零侵入。 */
(function () {
  "use strict";
  const E = window.__editor;
  if (!E) return;

  const $ = id => document.getElementById(id);
  const fpTree = $("fpTree"), fpOutline = $("fpOutline");
  const btnSave = $("btnSave"), scenePanel = $("scenePanel"), timelineEl = $("timeline");

  // ---- 状态 ----
  let curPath = "";                 // 当前打开的相对路径（"章节/第一章.gal"）
  let files = [];                   // 工程全部 .gal（相对路径）
  const buffers = {};               // rel → 编辑中内容（未保存也保留）
  const savedText = {};             // rel → 磁盘内容（脏判定基准）
  let suppressBuffer = false;       // openFile 写源码区时不同步缓冲（防回写脏数据）
  const openTabs = [];              // P44-A1：已打开的标签（相对路径，按打开顺序）

  // 同步给主编辑器：检查/预览/运行请求都带上当前文件（@include 基准）
  window.__proCurPath = () => curPath;
  window.__proLabel = () => curPath;
  window.__proOpenFile = openFile;   // UI 搜索面板等壳层模块跳转用（openFile 是函数声明，已提升）

  // ---- P44-A1 标签栏（VSCode/Trae 式多标签）----
  const MAX_TABS = 12;              // 同时打开的标签上限（契约 T-UI-01 §3）
  const tabsEl = $("editorTabs");
  function renderTabs() {
    if (!tabsEl) return;
    tabsEl.innerHTML = "";
    if (!openTabs.length) {         // 空态占位（不显示可关闭标签）
      const empty = document.createElement("div");
      empty.className = "editor-tab tab-empty";
      empty.textContent = "无打开的文件";
      tabsEl.appendChild(empty);
    }
    const dupes = {};               // 同名文件（如多处 script.gal）→ 标签带一级目录区分
    openTabs.forEach(r => { const b = r.split("/").pop(); dupes[b] = (dupes[b] || 0) + 1; });
    openTabs.forEach(rel => {
      const tab = document.createElement("div");
      tab.className = "editor-tab" + (rel === curPath ? " active" : "") + (dirtyOf(rel) ? " dirty" : "");
      tab.title = rel;
      const nm = document.createElement("span");
      nm.className = "tab-name";
      nm.textContent = dupes[rel.split("/").pop()] > 1
        ? rel.split("/").slice(-2).join("/")     // 重名时显示「目录/文件名」
        : rel.split("/").pop();
      const dot = document.createElement("span");
      dot.className = "tab-dirty";
      const x = document.createElement("span");
      x.className = "tab-close";
      x.textContent = "✕";
      x.title = "关闭 " + rel;
      x.addEventListener("click", (e) => {
        e.stopPropagation();
        closeTab(rel);
      });
      tab.appendChild(nm); tab.appendChild(dot); tab.appendChild(x);
      tab.addEventListener("click", () => openFile(rel));
      tabsEl.appendChild(tab);
    });
    const plus = document.createElement("div");
    plus.className = "editor-tab tab-plus";
    plus.textContent = "＋";
    plus.title = "新建章节";
    plus.addEventListener("click", () => $("btnNewChapter") && $("btnNewChapter").click());
    tabsEl.appendChild(plus);
  }
  async function closeTab(rel) {
    const idx = openTabs.indexOf(rel);
    if (idx < 0) return;
    if (dirtyOf(rel) && !confirm("「" + rel + "」有未保存的修改，关闭将丢弃（内存中也不保留）。确定关闭吗？")) return;
    const wasActive = rel === curPath;
    openTabs.splice(idx, 1);
    delete buffers[rel];
    delete savedText[rel];
    if (wasActive) {
      const next = openTabs[Math.min(idx, openTabs.length - 1)];
      curPath = "";
      if (next) openFile(next);          // 切到相邻标签（openFile 内部会重画标签栏）
      else enterEmptyState();            // 最后一个标签关闭 → 空态（不关闭到 0）
    }
    renderTabs();
    renderTreeDirty();
    updateSaveBtn();
  }

  /** 空态：没有打开的标签（__proCurPath 返回空串，检查/预览自动不带 path） */
  function enterEmptyState() {
    curPath = "";
    suppressBuffer = true;
    E.setText("");
    suppressBuffer = false;
    E.setFileLabel("");
    renderTree();
    updateSaveBtn();
    refreshOutline();
    refreshTimeline();
    refreshScene(1);
    E.setPreviewMsg(true, "没有打开的文件——点 ＋ 新建章节，或在左侧选一个 .gal");
  }

  // ---- HTTP ----
  function api(url, body) {
    return fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    }).then(r => r.json());
  }
  function apiGet(url) { return fetch(url, { cache: "no-store" }).then(r => r.json()); }

  // ---- 脏标记 ----
  function dirtyOf(rel) { return rel in buffers && buffers[rel] !== savedText[rel]; }
  function updateSaveBtn() {
    const anyDirty = files.some(dirtyOf);
    // 图标/文字取舍：保存按钮是纯图标 + 脏点，文字由 __proToolbarSync 统一管，这里不再改 textContent（会吃掉 SVG）
    // A2：标题栏 ● 提示任一文件未保存
    document.title = (anyDirty ? "● " : "") + "MYONL 编辑器";
    // D2：活动栏「工程文件」按钮上的未保存黄点
    if (window.__actSetDirty) window.__actSetDirty(anyDirty);
    // T1/T8：顶部动作条三态 + 状态栏保存分段
    if (window.__proToolbarSync) window.__proToolbarSync();
    if (window.__statusSaveSync) window.__statusSaveSync();
    // 桌面窗口（pywebview）关闭确认：把「任一未保存」同步给 Python 侧。
    // 浏览器模式没有 window.pywebview，仍由上面的 beforeunload 兜底。
    try {
      if (window.pywebview && window.pywebview.api && window.pywebview.api.set_dirty) {
        const p = window.pywebview.api.set_dirty(anyDirty);
        if (p && typeof p.catch === "function") p.catch(() => {});
      }
    } catch (e) { /* 未就绪/非桌面模式：忽略 */ }
  }
  window.__proDirty = () => !!(curPath && dirtyOf(curPath));
  window.__proAnyDirty = () => files.some(dirtyOf);

  // ==================== 文件树 ====================
  const collapsedDirs = new Set();

  function buildTree(list) {
    const root = { dirs: {}, files: [] };
    for (const f of list) {
      const parts = f.split("/");
      let node = root;
      for (let i = 0; i < parts.length - 1; i++) {
        node = node.dirs[parts[i]] || (node.dirs[parts[i]] = { dirs: {}, files: [] });
      }
      node.files.push(f);
    }
    return root;
  }

  function renderNode(node, prefix, depth) {
    Object.keys(node.dirs).sort().forEach(d => {
      const rel = prefix ? prefix + "/" + d : d;
      const div = document.createElement("div");
      div.className = "fp-dir";
      div.style.paddingLeft = (6 + depth * 12) + "px";
      div.textContent = (collapsedDirs.has(rel) ? "▸ " : "▾ ") + d;
      div.title = rel;
      div.addEventListener("click", () => {
        if (collapsedDirs.has(rel)) collapsedDirs.delete(rel); else collapsedDirs.add(rel);
        renderTree();
      });
      fpTree.appendChild(div);
      if (!collapsedDirs.has(rel)) renderNode(node.dirs[d], rel, depth + 1);
    });
    node.files.slice().sort().forEach(f => {
      const div = document.createElement("div");
      div.className = "fp-item" + (f === curPath ? " cur" : "") + (dirtyOf(f) ? " dirty" : "");
      div.style.paddingLeft = (6 + depth * 12) + "px";
      div.title = f;
      div.innerHTML = '<span class="fp-dirty"></span><span class="fp-nm"></span>';
      div.querySelector(".fp-nm").textContent = f.split("/").pop();
      div.addEventListener("click", () => openFile(f));
      fpTree.appendChild(div);
    });
  }

  function renderTree() {
    fpTree.innerHTML = "";
    renderNode(buildTree(files), "", 0);
  }

  function renderTreeDirty() {
    fpTree.querySelectorAll(".fp-item").forEach(el => {
      el.classList.toggle("dirty", dirtyOf(el.title));
      el.classList.toggle("cur", el.title === curPath);
    });
  }

  // ==================== 打开 / 保存 ====================
  async function openFile(rel, gotoLine) {
    // 契约 §3：标签上限 12 个，超出提示先关标签（已打开的文件直接切换，不占新位）
    if (curPath !== rel && openTabs.indexOf(rel) < 0 && openTabs.length >= MAX_TABS) {
      const tip = "最多同时打开 " + MAX_TABS + " 个标签，请先关闭标签";
      if (E.toast) E.toast(tip, true);      // toast 2.8s，不会被异步检查覆盖
      E.setPreviewMsg(false, tip);
      return;
    }
    if (curPath && curPath !== rel) {
      buffers[curPath] = E.getText();  // 留住未保存修改（不写盘，切回可继续编辑）
      // A2：未保存切换前中文确认（取消则留在当前文件）
      if (dirtyOf(curPath) && !confirm(
          "「" + curPath + "」有未保存的修改。\n" +
          "切换后修改仍保留在内存里（文件树带 ● 标记），切回可继续编辑；\n" +
          "如需落盘请先 Ctrl+S 保存。确定切换吗？")) {
        return;
      }
    }
    let text;
    if (rel in buffers) {
      text = buffers[rel];
    } else {
      let resp;
      try { resp = await apiGet("/api/file/read?path=" + encodeURIComponent(rel)); }
      catch (e) { E.setPreviewMsg(false, "读取失败：" + e); return; }
      if (!resp.ok) { E.setPreviewMsg(false, resp.message || "读取失败"); return; }
      text = resp.text;
      savedText[rel] = text;
    }
    curPath = rel;
    suppressBuffer = true;
    E.setText(text);
    suppressBuffer = false;
    E.setFileLabel(rel);
    if (openTabs.indexOf(rel) < 0) openTabs.push(rel);
    renderTabs();
    renderTree();
    updateSaveBtn();
    refreshOutline();
    // 主动刷新可视化面板：checkAndPreview 失败路径不广播，防残留上一文件的节点
    refreshTimeline();
    refreshScene(gotoLine || 1);
    if (gotoLine) setTimeout(() => E.gotoLine(gotoLine), 30);
  }

  async function saveCurrent() {
    if (!curPath) return;
    buffers[curPath] = E.getText();  // 当前展示内容为准（含卡片视图改回的文本）
    const text = buffers[curPath];
    let resp;
    try { resp = await api("/api/file/save", { path: curPath, content: text }); }
    catch (e) { E.setPreviewMsg(false, "保存请求失败：" + e); return; }
    if (resp.ok) {
      savedText[curPath] = text;
      E.setPreviewMsg(true, resp.message || ("已保存 " + curPath));
      refreshOutline();
    } else {
      E.setPreviewMsg(false, (resp.message || "保存失败") + (resp.line ? `（第 ${resp.line} 行）` : ""));
      if (resp.line) { E.switchToSource(); E.gotoLine(resp.line); }
    }
    renderTabs();
    renderTreeDirty();
    updateSaveBtn();
  }

  btnSave.addEventListener("click", saveCurrent);
  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
      e.preventDefault();
      saveCurrent();
    }
  });
  window.addEventListener("beforeunload", (e) => {
    if (curPath) buffers[curPath] = E.getText();
    if (files.some(dirtyOf)) { e.preventDefault(); e.returnValue = ""; }
  });

  // 源码区输入 → 同步当前文件缓冲 + 脏标记
  E.sourceEl.addEventListener("input", () => {
    if (suppressBuffer || !curPath) return;
    buffers[curPath] = E.sourceEl.value;
    renderTabs();
    renderTreeDirty();
    updateSaveBtn();
  });

  // ==================== 新建章节弹窗 ====================
  const ncModal = $("newChapterModal"), ncName = $("newChapterName"), ncErr = $("newChapterErr");
  function openNC() { ncErr.textContent = ""; ncName.value = ""; ncModal.style.display = "flex"; setTimeout(() => ncName.focus(), 30); }
  function closeNC() { ncModal.style.display = "none"; }
  async function submitNC() {
    const name = ncName.value.trim();
    if (!name) { ncErr.textContent = "章节名不能为空"; return; }
    let resp;
    try { resp = await api("/api/file/new", { name }); }
    catch (e) { ncErr.textContent = "请求失败：" + e; return; }
    if (!resp.ok) { ncErr.textContent = resp.message || "创建失败"; return; }
    closeNC();
    try {
      const list = await apiGet("/api/files");
      if (list.ok) files = list.files || [];
    } catch (e) {}
    renderTree();
    openFile(resp.path);
  }
  $("btnNewChapter").addEventListener("click", openNC);
  $("newChapterCancel").addEventListener("click", closeNC);
  $("newChapterOk").addEventListener("click", submitNC);
  ncName.addEventListener("keydown", (e) => {
    if (e.key === "Enter") submitNC();
    if (e.key === "Escape") closeNC();
  });
  ncModal.addEventListener("click", (e) => { if (e.target === ncModal) closeNC(); });

  // ==================== 章节大纲（跨文件 @label / @jump） ====================
  async function refreshOutline() {
    let resp;
    try { resp = await apiGet("/api/labels"); } catch (e) { return; }
    if (!resp.ok) return;
    fpOutline.innerHTML = "";
    const labelFile = {};
    (resp.labels || []).forEach(l => { labelFile[l.name] = l.file; });
    const byFile = {};
    (resp.labels || []).forEach(l => { (byFile[l.file] = byFile[l.file] || []).push(l); });
    Object.keys(byFile).sort().forEach(f => {
      const fh = document.createElement("div");
      fh.className = "ol-file";
      fh.textContent = "📄 " + f;
      fpOutline.appendChild(fh);
      byFile[f].sort((a, b) => a.line - b.line).forEach(l => {
        const d = document.createElement("div");
        d.className = "ol-label";
        d.textContent = `⚑ ${l.name} · ${l.line}行`;
        d.title = `${f} 第 ${l.line} 行`;
        d.addEventListener("click", () => openFile(l.file, l.line));
        fpOutline.appendChild(d);
      });
    });
    (resp.jumps || []).slice()
      .sort((a, b) => (a.file === b.file ? a.line - b.line : (a.file < b.file ? -1 : 1)))
      .forEach(j => {
        const d = document.createElement("div");
        d.className = "ol-jump";
        const to = labelFile[j.target];
        d.textContent = `→ ${j.target} `;
        const span = document.createElement("span");
        span.className = "to";
        span.textContent = to ? (to === j.file ? "本文件" : to) : "（未定义）";
        d.appendChild(span);
        d.title = `${j.file} 第 ${j.line} 行`;
        d.addEventListener("click", () => openFile(j.file, j.line));
        fpOutline.appendChild(d);
      });
    if ((resp.errors || []).length) {
      const d = document.createElement("div");
      d.className = "ol-err";
      d.textContent = `⚠ ${resp.errors.length} 个文件解析失败`;
      fpOutline.appendChild(d);
    }
  }
  $("outlineRefresh").addEventListener("click", refreshOutline);

  // ==================== @include 行号跳转 ====================
  E.lineNumbersEl.addEventListener("click", (e) => {
    const t = e.target.closest(".ln.inc");
    if (!t || !curPath) return;
    const line = parseInt(t.dataset.line, 10);
    apiGet(`/api/include-target?path=${encodeURIComponent(curPath)}&line=${line}`)
      .then(resp => {
        if (resp.ok && resp.exists) openFile(resp.target);
        else if (resp.ok) E.setPreviewMsg(false, "目标文件不存在：" + resp.target);
        else E.setPreviewMsg(false, resp.message || "该行不是 @include");
      })
      .catch(() => E.setPreviewMsg(false, "include 跳转请求失败"));
  });

  // ==================== 场景时间线 ====================
  const TL_LANES = [["bg", "背景"], ["sprite", "立绘"], ["audio", "音频"], ["choice", "选项"]];
  let lastNodes = [];
  let tlSeq = 0;  // 竞态防护：只渲染最后一次请求的响应

  async function refreshTimeline() {
    const seq = ++tlSeq;
    const text = E.getText();
    if (!text.trim() || !curPath) { lastNodes = []; timelineEl.style.display = "none"; return; }
    let resp;
    try { resp = await api("/api/timeline", { text, path: curPath }); }
    catch (e) { return; }
    if (seq !== tlSeq) return;
    if (!resp.ok || !resp.nodes || !resp.nodes.length) {
      lastNodes = [];
      timelineEl.style.display = "none";
      return;
    }
    lastNodes = resp.nodes;
    renderTimeline();
  }

  function tlNode(n, has) {
    const el = document.createElement("div");
    el.className = "tl-node";
    el.title = `第 ${n.line} 行 ${n.label}`;
    let miss = false;
    let imgCat = null;
    if ((n.kind === "bg" || n.kind === "show" || n.kind === "cg") && n.name && has("images", n.name)) imgCat = "images";
    else if (n.kind === "video" && n.name && has("videos", n.name)) imgCat = "videos";
    if (imgCat) {
      const img = document.createElement("img");
      img.src = E.assetURL(imgCat, n.name);
      img.alt = n.label;
      el.appendChild(img);
    } else {
      const box = document.createElement("div");
      box.className = "box";
      if (n.kind === "choice") box.textContent = "？";
      else if (n.lane === "audio") {
        box.textContent = "♪";
        miss = !!(n.name && !has("audio", n.name));
      } else if (n.name) { box.textContent = "▦"; miss = true; }
      else box.textContent = "·";
      el.appendChild(box);
    }
    const nm = document.createElement("div");
    nm.className = "nm" + (miss ? " miss" : "");
    nm.textContent = n.label + (miss ? "（缺）" : "");
    el.appendChild(nm);
    el.addEventListener("click", () => { E.switchToSource(); E.gotoLine(n.line); });
    return el;
  }

  function renderTimeline() {
    const assets = E.getAssets() || {};
    const has = (cat, name) => (assets[cat] || []).includes(name);
    timelineEl.innerHTML = "";
    const title = document.createElement("div");
    title.className = "tl-title";
    title.textContent = "场景时间线";
    timelineEl.appendChild(title);
    let anyLane = false;
    for (const [lane, label] of TL_LANES) {
      const nodes = lastNodes.filter(n => n.lane === lane);
      if (!nodes.length) continue;
      anyLane = true;
      const laneEl = document.createElement("div");
      laneEl.className = "tl-lane";
      const nm = document.createElement("div");
      nm.className = "tl-lane-name";
      nm.textContent = label;
      laneEl.appendChild(nm);
      const track = document.createElement("div");
      track.className = "tl-track";
      nodes.forEach((n, i) => {
        if (i) {
          const link = document.createElement("div");
          link.className = "tl-link";
          track.appendChild(link);
        }
        track.appendChild(tlNode(n, has));
      });
      laneEl.appendChild(track);
      timelineEl.appendChild(laneEl);
    }
    timelineEl.style.display = anyLane ? "block" : "none";
  }

  E.onChange(refreshTimeline);

  // ==================== 当前场景素材面板（随行变化） ====================
  let lastScene = null;
  let sceneTimer = 0;

  E.onCursor(line => {
    clearTimeout(sceneTimer);
    sceneTimer = setTimeout(() => refreshScene(line), 300);
  });

  async function refreshScene(line) {
    const text = E.getText();
    if (!text.trim() || !curPath) { lastScene = null; scenePanel.style.display = "none"; return; }
    let resp;
    try { resp = await api("/api/scene", { text, line, path: curPath }); }
    catch (e) { return; }
    if (!resp.ok) { scenePanel.style.display = "none"; return; }
    lastScene = resp;
    renderScene(resp);
  }

  function renderScene(s) {
    const assets = E.getAssets() || {};
    const has = (cat, name) => (assets[cat] || []).includes(name);
    scenePanel.innerHTML = "";
    const chips = [];
    if (s.bg) chips.push({ kind: "背景", name: s.bg, cat: "images" });
    (s.sprites || []).forEach(sp =>
      chips.push({ kind: "立绘", name: sp.char + "_" + sp.expr, label: `${sp.char} ${sp.expr}`, cat: "images" }));
    if (s.music) chips.push({ kind: "音乐", name: s.music, cat: "audio" });
    if (!chips.length) {
      const d = document.createElement("div");
      d.className = "scene-empty";
      d.textContent = "此行无场景素材，可拖入图片自动插入 @bg";
      scenePanel.appendChild(d);
    } else {
      chips.forEach(c => {
        const el = document.createElement("div");
        el.className = "scene-chip";
        const miss = !has(c.cat, c.name);
        if (!miss && c.cat === "images") {
          const img = document.createElement("img");
          img.src = E.assetURL("images", c.name);
          img.alt = c.name;
          el.appendChild(img);
        } else {
          const box = document.createElement("div");
          box.className = "box";
          box.textContent = c.cat === "audio" ? "♪" : "▦";
          el.appendChild(box);
        }
        const txt = document.createElement("div");
        const kd = document.createElement("div");
        kd.className = "kind";
        kd.textContent = c.kind;
        const nm = document.createElement("div");
        nm.className = "nm" + (miss ? " miss" : "");
        nm.textContent = (c.label || c.name) + (miss ? "（缺素材）" : "");
        txt.appendChild(kd);
        txt.appendChild(nm);
        el.appendChild(txt);
        scenePanel.appendChild(el);
      });
    }
    scenePanel.style.display = "flex";
  }

  // 素材导入/删除后：时间线与场景面板的缺素材标记联动刷新
  window.__proAfterAssets = () => {
    if (lastNodes.length) renderTimeline();
    if (lastScene) renderScene(lastScene);
  };

  // ==================== 卡片视图：跨文件只读总览 ====================
  const OP_LABEL = {
    say: "对话", bg: "背景", music: "音乐", sfx: "音效", voice: "配音", video: "视频",
    show: "立绘", hide: "隐藏", character: "角色", label: "标签", jump: "跳转",
    set: "变量", if: "条件", choice: "选项", end: "结束", cg: "CG",
    camera: "镜头", transition: "转场", plug: "插件",
  };

  function relOf(file) {
    if (!file) return curPath || "";
    const norm = String(file).replace(/\\/g, "/");
    for (const f of files) {
      if (norm === f || norm.endsWith("/" + f)) return f;
    }
    return norm.split("/").pop();
  }

  function walkInstrs(list, out) {
    for (const ins of list || []) {
      out.push(ins);
      if (ins.op === "if" && ins.body) walkInstrs(ins.body, out);
    }
  }

  function summarize(ins) {
    switch (ins.op) {
      case "say": return (ins.char ? ins.char + "：" : "") + (ins.text || "");
      case "bg": return "背景 " + (ins.image || "");
      case "music": return "音乐 " + (ins.track || "");
      case "sfx": return "音效 " + (ins.sound || "");
      case "voice": return "配音 " + (ins.sound || "");
      case "video": return "视频 " + (ins.name || "");
      case "show": return `立绘 ${ins.char} ${ins.expr}`;
      case "hide": return "隐藏 " + (ins.char || "");
      case "label": return "标签 " + (ins.name || "");
      case "jump": return "跳转 " + (ins.target || "");
      case "set": return `变量 ${ins.var} ${ins.operator || "="} ${ins.value}`;
      case "if": {
        const c = ins.cond || {};
        return `条件 ${c.var || ""} ${c.op || ""} ${c.value === undefined ? "" : c.value}`;
      }
      case "choice": return "选项 " + (ins.options || []).map(o => o.text).join(" / ");
      case "end": return "结束";
      default: return ins.op;
    }
  }

  window.__proCards = function (instrs) {
    const cv = E.cardViewEl;
    cv.innerHTML = "";
    const tip = document.createElement("div");
    tip.className = "card-ro-tip";
    tip.textContent = "多文件剧本为只读总览：点击卡片跳到对应文件与行；编辑请用「源码」视图。";
    cv.appendChild(tip);
    const flat = [];
    walkInstrs(instrs, flat);
    let lastFile = null;
    flat.forEach(ins => {
      const f = relOf(ins.file);
      if (f !== lastFile) {
        lastFile = f;
        const h = document.createElement("div");
        h.className = "card-file-head";
        h.textContent = "📄 " + f + (f === curPath ? "" : "（经 @include 展开）");
        h.addEventListener("click", () => openFile(f));
        cv.appendChild(h);
      }
      const card = document.createElement("div");
      card.className = "card";
      const head = document.createElement("div");
      head.className = "card-head";
      const badge = document.createElement("span");
      badge.className = "badge badge-" + ins.op;
      badge.textContent = OP_LABEL[ins.op] || ins.op;
      const sum = document.createElement("span");
      sum.className = "card-summary";
      sum.textContent = summarize(ins);
      const ln = document.createElement("span");
      ln.className = "card-line";
      ln.textContent = "L" + (ins.line || "?");
      head.appendChild(badge);
      head.appendChild(sum);
      head.appendChild(ln);
      card.appendChild(head);
      card.addEventListener("click", () => openFile(f, ins.line));
      cv.appendChild(card);
    });
  };

  // ==================== 初始化：文件树 + 当前文件对齐 ====================
  (async function init() {
    try {
      const resp = await apiGet("/api/files");
      if (!resp.ok) return;
      files = resp.files || [];
      curPath = resp.current || files[0] || "";
      if (curPath) {
        const rd = await apiGet("/api/file/read?path=" + encodeURIComponent(curPath));
        if (rd.ok) {
          savedText[curPath] = rd.text;
          if (!E.getText()) {  // 主编辑器还没加载到内容时才写入（避免覆盖 loadScript）
            suppressBuffer = true;
            E.setText(rd.text);
            suppressBuffer = false;
          }
          E.setFileLabel(curPath);
          if (openTabs.indexOf(curPath) < 0) openTabs.push(curPath);
        }
      }
      renderTabs();
      renderTree();
      updateSaveBtn();
      refreshOutline();
    } catch (e) { /* 服务未就绪时静默降级：主编辑器旧行为不受影响 */ }
  })();
})();


/* ===================================================================
   UI 质感批 1（2026-11-01，对标 Trae/VSCode）：
   1) 活动栏 SVG 图标（替换 emoji）
   2) .gal 语法高亮（指令/标签/角色/台词/选项箭头/富文本标记/数字/注释）
   3) 代码区滚动同步（textarea 透明文字 + 底层彩色层）
   失败静默降级（不高亮 = 旧行为）。
   =================================================================== */
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };

  // ---------- 1. 活动栏 SVG 图标 ----------
  var ICONS = {
    files: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M7 3.5h6.5L18 8v12.5H7z"/><path d="M13.5 3.5V8H18"/><path d="M9.5 12.5h6M9.5 16h4"/></svg>',
    assets: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><rect x="3.5" y="5" width="17" height="14" rx="2"/><circle cx="8.5" cy="9.5" r="1.4"/><path d="M4.5 17l4.6-4.6 3.2 3.2 2.8-2.8 4.4 4.2"/></svg>',
    settings: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M12 2.8v2.6M12 18.6v2.6M2.8 12h2.6M18.6 12h2.6M5.5 5.5l1.9 1.9M16.6 16.6l1.9 1.9M18.5 5.5l-1.9 1.9M7.4 16.6l-1.9 1.9"/></svg>',
    help: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M9.6 9.3a2.5 2.5 0 1 1 3.3 2.3c-.7.3-.9.8-.9 1.5v.4"/><circle cx="12" cy="16.8" r="0.9" fill="currentColor" stroke="none"/></svg>'
  };

  function mountIcon(el, svg) {
    if (!el) return;
    for (var i = 0; i < el.childNodes.length; i++) {
      var n = el.childNodes[i];
      if (n.nodeType === 3 && n.textContent.trim()) { n.parentNode.removeChild(n); break; }
    }
    el.insertAdjacentHTML("afterbegin", svg);
    el.classList.add("has-svg-icon");
  }

  function applyIcons() {
    mountIcon(document.querySelector('.act-btn[data-view="files"]'), ICONS.files);
    mountIcon(document.querySelector('.act-btn[data-view="assets"]'), ICONS.assets);
    mountIcon(document.querySelector('.act-btn[data-view="settings"]'), ICONS.settings);
    mountIcon($("actHelp"), ICONS.help);
  }

  // ---------- 2. .gal 语法高亮 ----------
  var ESC = { "&": "&amp;", "<": "&lt;", ">": "&gt;" };
  function esc(s) { return String(s).replace(/[&<>]/g, function (c) { return ESC[c]; }); }

  var LABEL_CMDS = { label: 1, jump: 1, goto: 1, include: 1 };
  var TOKEN_RE = /(->\s*\S+)|(\{[^}\n]*\})|("[^"\n]*")|(\b\d+(?:\.\d+)?\b)/g;

  function paintRest(rest, out) {
    var idx = 0, m;
    TOKEN_RE.lastIndex = 0;
    while ((m = TOKEN_RE.exec(rest))) {
      out.push(esc(rest.slice(idx, m.index)));
      var s = m[0];
      if (s.charAt(0) === "-") {
        var p = s.match(/^(->)(\s*)(\S*)$/);
        if (p) out.push('<span class="t-arrow">-&gt;</span>' + esc(p[2]) + (p[3] ? '<span class="t-label">' + esc(p[3]) + "</span>" : ""));
        else out.push(esc(s));
      } else if (s.charAt(0) === "{") {
        out.push('<span class="t-mark">' + esc(s) + "</span>");
      } else if (s.charAt(0) === '"') {
        out.push('<span class="t-str">' + esc(s) + "</span>");
      } else {
        out.push('<span class="t-num">' + esc(s) + "</span>");
      }
      idx = m.index + s.length;
    }
    out.push(esc(rest.slice(idx)));
  }

  function hlLine(line) {
    if (/^\s*#/.test(line)) return '<span class="t-comment">' + esc(line) + "</span>";
    var out = [];
    var indent = line.match(/^\s*/)[0];
    var rest = line.slice(indent.length);
    out.push(esc(indent));

    var mc = rest.match(/^@([A-Za-z_]+)(\s*)([^\n]*)$/);
    if (mc) {
      out.push('<span class="t-cmd">@' + esc(mc[1]) + "</span>" + esc(mc[2]));
      var after = mc[3];
      if (LABEL_CMDS[mc[1]]) {
        var mt = after.match(/^(\s*)(\S+)([\s\S]*)$/);
        if (mt) {
          out.push(esc(mt[1]) + '<span class="t-label">' + esc(mt[2]) + "</span>");
          paintRest(mt[3], out);
          return out.join("");
        }
      } else if (mc[1] === "character") {
        var mch = after.match(/^(\s*)(\S+)([\s\S]*)$/);
        if (mch) {
          out.push(esc(mch[1]) + '<span class="t-char">' + esc(mch[2]) + "</span>");
          paintRest(mch[3], out);
          return out.join("");
        }
      }
      out.push(esc(after));
      return out.join("");
    }

    var ms = rest.match(/^@(\s+)(\S+)([\s\S]*)$/);
    if (ms) {
      out.push('<span class="t-cmd">@</span>' + esc(ms[1]) + '<span class="t-char">' + esc(ms[2]) + "</span>");
      paintRest(ms[3], out);
      return out.join("");
    }

    paintRest(rest, out);
    return out.join("");
  }

  var JSON_RE = /("(?:[^"\\]|\\.)*")(\s*:)?|(\b-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?\b)|(\btrue\b|\bfalse\b|\bnull\b)/g;
  function jsonHl(text) {
    var out = [], idx = 0, m;
    JSON_RE.lastIndex = 0;
    while ((m = JSON_RE.exec(text))) {
      out.push(esc(text.slice(idx, m.index)));
      if (m[1]) {
        if (m[2]) out.push('<span class="t-cmd">' + esc(m[1]) + "</span>" + esc(m[2]));
        else out.push('<span class="t-str">' + esc(m[1]) + "</span>");
      } else if (m[3]) {
        out.push('<span class="t-num">' + esc(m[3]) + "</span>");
      } else {
        out.push('<span class="t-mark">' + esc(m[4]) + "</span>");
      }
      idx = m.index + m[0].length;
    }
    out.push(esc(text.slice(idx)));
    return out.join("");
  }

  var ta = $("source"), wrap = $("sourceWrap");
  if (ta && wrap) {
    var pre = document.createElement("pre");
    pre.className = "hl-layer";
    pre.setAttribute("aria-hidden", "true");
    wrap.insertBefore(pre, ta);
    var last = null;
    var hlMode = "gal";
    // 逐行缓存上一次的原文：敲键时只重算变动行，避免整篇高亮重建（大剧本 90ms+）
    var prevLines = null;
    var LINE_H = 22.4;                       // textarea 14px × line-height 1.6（本闭包内的高亮层回退值）
    function hlDiv(line) {
      return '<div class="hl-line">' + hlLine(line) + "</div>";
    }
    function hlDivNode(line) {
      var div = document.createElement("div");
      div.className = "hl-line";
      div.innerHTML = hlLine(line);
      return div;
    }
    function notifyLines(from, count, reset) {
      try {
        window.dispatchEvent(new CustomEvent("myonl:hl-lines",
          { detail: { from: from, count: count, reset: !!reset } }));
      } catch (e) {}
    }
    // 软换行后每行高度不等：行号层 / 当前行 / 错误行 / 跳转统一按这里的真实位置算
    function hlMetrics(i) {
      var el = (hlMode === "gal") ? pre.children[i] : null;
      if (!el) return { top: 10 + Math.max(0, i) * LINE_H, h: LINE_H };
      return { top: el.offsetTop, h: el.getBoundingClientRect().height };
    }
    window.__hlLineMetrics = hlMetrics;
    window.__hlLineReady = function () { return hlMode === "gal" ? pre.children.length : -1; };
    window.__hlScrollTopForLine = function (lineNo, keepAbove) {
      var i = Math.max(0, (Number(lineNo) || 1) - 1);
      return Math.max(0, hlMetrics(i).top - 10 - (keepAbove || 0) * LINE_H);
    };
    function fullRender(lines) {
      var buf = [];
      for (var i = 0; i < lines.length; i++) buf.push(hlDiv(lines[i]));
      pre.innerHTML = buf.join("");
      prevLines = lines;
      notifyLines(0, lines.length);
    }
    function patchLine(i, line) {
      var el = pre.children[i];
      if (el) el.innerHTML = hlLine(line);
    }
    // 语言选择（状态栏 / 设置）：只影响编辑器显示，不影响剧本保存格式
    window.__hlSetMode = function (mode) {
      hlMode = (mode === "plain" || mode === "json") ? mode : "gal";
      last = null;
      render();
    };
    window.__hlGetMode = function () { return hlMode; };

    function syncScroll() {
      // 文本域出现竖向滚动条时 clientWidth 不含滚动条宽度（WebView2 经典滚动条为 10px），
      // 而高亮层铺到 right:0 会比文本域内容区宽出这一截，软换行断点随之不同：
      // 长行多/少折一行 → 行号、当前行、错误浮层越往下偏越多（表现为「末尾多 22px」）。
      var w = ta.clientWidth;
      if (w > 0 && pre.style.width !== w + "px") pre.style.width = w + "px";
      pre.style.transform = "translate(" + (-ta.scrollLeft) + "px," + (-ta.scrollTop) + "px)";
    }
    function render() {
      var text = ta.value;
      if (text === last) return;
      last = text;
      if (hlMode === "plain") { pre.textContent = text || " "; prevLines = null; notifyLines(0, 0, true); syncScroll(); return; }
      if (hlMode === "json") { pre.innerHTML = jsonHl(text) || " "; prevLines = null; notifyLines(0, 0, true); syncScroll(); return; }
      var lines = text.split("\n");
      var prev = prevLines;
      if (!prev || pre.children.length !== prev.length) { fullRender(lines); syncScroll(); return; }
      // 只动变化的中间段：公共前缀 + 公共后缀之外的行
      var n = lines.length, m = prev.length, p = 0, s = 0, i;
      while (p < n && p < m && lines[p] === prev[p]) p++;
      while (s < n - p && s < m - p && lines[n - 1 - s] === prev[m - 1 - s]) s++;
      var newMid = n - p - s, oldMid = m - p - s;
      // 变动面太大（整段粘贴/换文件）时整篇重建更划算
      if (newMid + oldMid > 40 && (newMid + oldMid) * 4 >= n) { fullRender(lines); syncScroll(); return; }
      if (newMid <= oldMid) {
        for (i = 0; i < newMid; i++) patchLine(p + i, lines[p + i]);
        for (i = 0; i < oldMid - newMid; i++) {
          var drop = pre.children[p + newMid];
          if (drop) pre.removeChild(drop);
        }
      } else {
        for (i = 0; i < oldMid; i++) patchLine(p + i, lines[p + i]);
        var frag = document.createDocumentFragment();
        for (i = oldMid; i < newMid; i++) frag.appendChild(hlDivNode(lines[p + i]));
        pre.insertBefore(frag, pre.children[p + oldMid] || null);
      }
      prevLines = lines;
      // 只通知变动行的新高度，行号层据此同步（软换行行高会变）
      notifyLines(p, Math.max(newMid, oldMid));
      syncScroll();
    }
    ta.addEventListener("input", render);
    ta.addEventListener("scroll", syncScroll, { passive: true });
    window.addEventListener("resize", syncScroll);
    (function watch() {
      if (ta.value !== last) render();
      window.requestAnimationFrame(watch);
    })();
    render();
    document.documentElement.classList.add("hl-on");
  }

  try { applyIcons(); } catch (e) { /* 旧 emoji 保留 */ }
})();


/* ===================================================================
   UI 质感批 1b：编辑器工具条（把 运行/保存/打包 搬到首屏可见处）
   直接复用主脚本已绑定的隐藏按钮（不复制 id、不改 HTML 行数）。
   =================================================================== */
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var pane = document.querySelector(".left-pane");
  var tabs = $("editorTabs");
  if (!pane) return;
  var bar = document.createElement("div");
  bar.className = "editor-toolbar";
  bar.innerHTML = '<span class="tb-spacer"></span>';
  // 图标取舍：主操作（运行/打包）图标+文字（新人要能找到）；保存是通用图标 → 纯图标+快捷键提示
  var TB_ICONS = {
    run: '<svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor" aria-hidden="true"><path d="M8 5.5v13l11-6.5z"/></svg>',
    save: '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 4.5h11l3 3V19.5H5z"/><path d="M8 4.5v5h7v-5"/><path d="M8 19.5v-6h8v6"/></svg>',
    pack: '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3.5 7.5L12 3l8.5 4.5v9L12 21l-8.5-4.5z"/><path d="M3.5 7.5L12 12l8.5-4.5M12 12v9"/></svg>',
    ui: '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3a9 9 0 1 0 0 18h1.5a2 2 0 0 0 0-4H13a2 2 0 0 1 0-4h4a4 4 0 0 0 0-8z"/><circle cx="7.5" cy="10.5" r="1"/><circle cx="10.5" cy="7" r="1"/><circle cx="15" cy="7.5" r="1"/></svg>'
  };
  var order = [
    ["btnRun", TB_ICONS.run, "运行", true],
    ["btnSave", TB_ICONS.save, "", false],
    ["btnPack", TB_ICONS.pack, "打包发布", false],
    // UI 设计区原来只有「设置中心 → 游戏界面」一处入口，工具条给显式入口
    ["btnUIDesign", TB_ICONS.ui, "UI 设计", false]
  ];
  var moved = [];
  for (var i = 0; i < order.length; i++) {
    var el = $(order[i][0]);
    if (!el) continue;
    el.classList.remove("hidden");
    el.classList.add("tb-btn");
    if (!order[i][2]) el.classList.add("tb-icon");
    if (order[i][3]) el.classList.add("primary");
    el.innerHTML = order[i][1]
      + (order[i][2] ? '<span class="tb-txt">' + order[i][2] + "</span>" : "")
      + (order[i][0] === "btnSave" ? '<span class="tb-dot" aria-hidden="true"></span>' : "");
    bar.appendChild(el);
    moved.push(el);
  }
  if (!moved.length) return;
  if (tabs && tabs.parentNode === pane) pane.insertBefore(bar, tabs);
  else pane.insertBefore(bar, pane.firstChild);
})();


/* ===================================================================
   UI 质感批 2：全局搜索（Ctrl+Shift+F，Trae/VSCode 式）
   跨 .gal 文件搜内容 → 点结果跳到对应文件 + 行；活动栏加放大镜入口。
   =================================================================== */
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var filesCache = null;
  var timer = null;
  var activeIdx = 0;

  var mask = document.createElement("div");
  mask.className = "qs-mask";
  mask.innerHTML = '<div class="qs-panel" role="dialog" aria-label="全局搜索">' +
    '<div class="qs-head">' +
    '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="10.5" cy="10.5" r="6.5"/><path d="M15.5 15.5L20 20"/></svg>' +
    '<input class="qs-input" id="qsInput" placeholder="搜索文件 / 内容（Ctrl+Shift+F）" autocomplete="off" spellcheck="false">' +
    '<span class="qs-hint">Enter 打开 · Esc 关闭</span>' +
    '</div><div class="qs-results" id="qsResults"></div></div>';
  document.body.appendChild(mask);
  var input = $("qsInput"), results = $("qsResults");

  function esc(s) { return String(s).replace(/[&<>]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]; }); }

  function ensureFiles() {
    if (filesCache) return Promise.resolve(filesCache);
    return fetch("/api/files").then(function (r) { return r.json(); }).then(function (d) {
      filesCache = (d && d.files) || [];
      return filesCache;
    });
  }

  function readFile(path) {
    return fetch("/api/file/read?path=" + encodeURIComponent(path))
      .then(function (r) { return r.json(); })
      .then(function (d) { return (d && d.text) || ""; })
      .catch(function () { return ""; });
  }

  function render(query, rows, fileRows) {
    var html = "";
    if (!query) {
      html = '<div class="qs-empty">输入关键词：先按文件名找文件，再搜剧本内容（工程内全部 .gal）</div>';
    } else if (!rows.length && !(fileRows && fileRows.length)) {
      html = '<div class="qs-empty">没有匹配结果</div>';
    } else {
      // 先列文件名命中（搜文件夹内的东西），再列内容命中
      if (fileRows && fileRows.length) {
        html += '<div class="qs-file"><span>文件</span><span class="qs-count">' + fileRows.length + ' 个</span></div>';
        fileRows.forEach(function (f) {
          var label = esc(f).split(esc(query)).join("<mark>" + esc(query) + "</mark>");
          html += '<div class="qs-row qs-file-row" data-path="' + esc(f) + '" data-line="0">' +
            '<span class="qs-ln">📄</span><span class="qs-txt">' + label + '</span></div>';
        });
      }
      var contentHtml = "", lastFile = null, total = 0;
      rows.forEach(function (r) {
        total += 1;
        if (r.path !== lastFile) {
          lastFile = r.path;
          var n = rows.filter(function (x) { return x.path === r.path; }).length;
          contentHtml += '<div class="qs-file"><span>' + esc(r.path) + '</span><span class="qs-count">' + n + ' 处</span></div>';
        }
        var line = esc(r.text).split(esc(query)).join("<mark>" + esc(query) + "</mark>");
        contentHtml += '<div class="qs-row" data-path="' + esc(r.path) + '" data-line="' + r.line + '">' +
          '<span class="qs-ln">' + (r.line + 1) + '</span><span class="qs-txt">' + line + '</span></div>';
      });
      html += '<div class="qs-file"><span>内容</span><span class="qs-count">' + total + ' 处</span></div>' + contentHtml;
    }
    results.innerHTML = html;
    activeIdx = 0;
  }

  function search(query) {
    if (!query) { render("", []); return; }
    results.innerHTML = '<div class="qs-empty">搜索中…</div>';
    ensureFiles().then(function (files) {
      var out = [];
      var chain = Promise.resolve();
      files.forEach(function (f) {
        chain = chain.then(function () {
          if (out.length >= 60) return null;
          return readFile(f).then(function (text) {
            if (!text) return;
            var lines = text.split("\n");
            for (var i = 0; i < lines.length && out.length < 60; i++) {
              if (lines[i].toLowerCase().indexOf(query.toLowerCase()) >= 0) {
                out.push({ path: f, line: i, text: lines[i].trim().slice(0, 200) });
              }
            }
          });
        });
      });
      var q = query.toLowerCase();
      var fileRows = files.filter(function (f) { return f.toLowerCase().indexOf(q) >= 0; }).slice(0, 8);
      return chain.then(function () { render(query, out, fileRows); });
    }).catch(function () {
      // 读取文件列表失败：别把「搜索中…」永远留在面板里
      results.innerHTML = '<div class="qs-empty">搜索失败：无法连接编辑器服务，请稍后重试</div>';
    });
  }

  function openPanel() {
    mask.classList.add("open");
    input.focus();
    input.select();
    if (!input.value) render("", []);
  }
  function closePanel() { mask.classList.remove("open"); }

  input.addEventListener("input", function () {
    clearTimeout(timer);
    var q = input.value.trim();
    timer = setTimeout(function () { search(q); }, 180);
  });
  input.addEventListener("keydown", function (ev) {
    if (ev.key === "Escape") { closePanel(); ev.preventDefault(); return; }
    if (ev.key === "Enter") {
      var first = results.querySelector(".qs-row");
      if (first) first.click();
      ev.preventDefault();
    }
  });
  results.addEventListener("click", function (ev) {
    var row = ev.target.closest ? ev.target.closest(".qs-row") : null;
    if (!row) return;
    closePanel();
    var open = window.__proOpenFile;
    if (open) open(row.getAttribute("data-path"), parseInt(row.getAttribute("data-line"), 10) + 1);
  });
  mask.addEventListener("mousedown", function (ev) { if (ev.target === mask) closePanel(); });
  document.addEventListener("keydown", function (ev) {
    var k = ev.key.toLowerCase();
    if (ev.ctrlKey && ev.shiftKey && k === "f") { ev.preventDefault(); openPanel(); }
    else if (ev.key === "Escape" && mask.classList.contains("open")) closePanel();
  });

  // 活动栏放大镜入口（插在「素材库」之后，避免改 HTML 行数）
  try {
    var bar = $("activityBar");
    var filesBtn = document.querySelector('.act-btn[data-view="files"]');
    if (bar && filesBtn) {
      var btn = document.createElement("div");
      btn.className = "act-btn";
      btn.id = "actSearch";
      btn.title = "Search · 全局搜索（Ctrl+Shift+F）";
      btn.innerHTML = '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><circle cx="10.5" cy="10.5" r="6.5"/><path d="M15.5 15.5L20 20"/></svg>';
      btn.addEventListener("click", openPanel);
      filesBtn.parentNode.insertBefore(btn, filesBtn.nextSibling);
    }
  } catch (e) { /* 旧布局保留 */ }
})();


/* ===================================================================
   Trae 化批 3（2026-11-01）
   T1 动作条三态 · T3 欢迎卡出口 · T4 预览锚定 @label start
   T5 Ctrl+F 查找替换 · T6 当前行高亮 · T7 右栏标签化 · T8 状态栏保存分段
   全部为增量模块：只经 window.__editor 桥协作，不改主脚本逻辑、不动引擎。
   =================================================================== */
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var E = window.__editor || {};
  var ta = E.sourceEl || $("source");
  var LINE_H = 22.4;                       // textarea 14px × line-height 1.6
  if (!ta) return;

  // ==================== T1 / T8：动作条三态 + 状态栏保存分段 ====================
  window.__proToolbarSync = function () {
    var has = !!(window.__proCurPath && window.__proCurPath());
    var dirty = !!(window.__proDirty && window.__proDirty());
    var run = $("btnRun"), save = $("btnSave"), pack = $("btnPack");
    if (run) {
      run.disabled = !has;
      run.title = has ? "Run Game · 运行游戏预览（Ctrl+R / F5）"
                      : "没有打开的文件——先在左侧选一个 .gal";
    }
    if (save) {
      save.classList.toggle("clean", !dirty);
      save.classList.toggle("dirty", dirty);
      save.disabled = !has;
      save.title = dirty ? "保存（Ctrl+S）· 有未保存修改" : "保存（Ctrl+S）";
    }
    if (pack) pack.title = "Pack · 打包发布（Ctrl+P）· 产物在 packs/";
  };
  window.__statusSaveSync = function () {
    var sb = $("sbSave");
    if (!sb) return;
    var dirty = !!(window.__proDirty && window.__proDirty());
    sb.textContent = dirty ? "● 未保存" : "✓ 已保存";
    sb.classList.toggle("dirty", dirty);
    sb.title = dirty ? "有未保存修改（Ctrl+S 保存）" : "所有修改已保存";
  };

  // T8：状态栏补「保存状态」段（VSCode 式最左）；活动栏图标可键盘聚焦
  (function () {
    var bar = $("statusbar"), ready = $("sbReady");
    if (bar && !$("sbSave")) {
      var sb = document.createElement("span");
      sb.className = "sb-item";
      sb.id = "sbSave";
      sb.textContent = "✓ 已保存";
      bar.insertBefore(sb, ready || bar.firstChild);
      var sep = document.createElement("span");
      sep.className = "sb-sep";
      bar.insertBefore(sep, sb.nextSibling);
    }
    var acts = document.querySelectorAll("#activityBar .act-btn");
    for (var i = 0; i < acts.length; i++) {
      acts[i].tabIndex = 0;
      acts[i].setAttribute("role", "button");
      acts[i].addEventListener("keydown", function (ev) {
        if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); this.click(); }
      });
    }
  })();

  // ==================== T1：打包中锁定（观察打包状态条，不改主脚本） ====================
  (function () {
    var pack = $("btnPack"), status = $("packStatus");
    if (!pack || !status) return;
    var PACK_ICON = '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3.5 7.5L12 3l8.5 4.5v9L12 21l-8.5-4.5z"/><path d="M3.5 7.5L12 12l8.5-4.5M12 12v9"/></svg>';
    var base = "打包发布";
    function sync() {
      var running = String(status.className || "").indexOf("running") >= 0;
      pack.disabled = running;
      pack.innerHTML = PACK_ICON + '<span class="tb-txt">' + (running ? "打包中…" : base) + "</span>";
      pack.title = running ? "正在打包，请稍候…" : "打包发布（Ctrl+P）· 产物在 packs/";
    }
    if (window.MutationObserver) {
      new MutationObserver(sync).observe(status, {
        attributes: true, attributeFilter: ["class"], childList: true, subtree: true,
      });
    }
    sync();
  })();

  // ==================== T3：欢迎卡（obCard）显式出口 + Esc ====================
  (function () {
    var card = $("obCard");
    if (!card || !card.querySelector) return;
    var actions = card.querySelector(".ob-actions");
    // T3：欢迎卡只弹一次（Esc/跳过/开始都算「看过」；「帮助→新手引导」可随时重开）
    function markWelcomeDone() {
      try { localStorage.setItem("gal_welcome_done", "1"); } catch (e) {}
    }
    function closeCard() { markWelcomeDone(); if (E.onboardingClose) E.onboardingClose(true); }
    function focusLine(n) {
      var lines = String(ta.value || "").split("\n");
      var pos = 0;
      for (var i = 0; i < n - 1 && i < lines.length; i++) pos += lines[i].length + 1;
      if (E.switchToSource) E.switchToSource();
      ta.focus();
      ta.setSelectionRange(pos, pos);
      ta.scrollTop = window.__hlScrollTopForLine
        ? window.__hlScrollTopForLine(n, 2) : Math.max(0, (n - 3) * LINE_H);
    }
    function openTutorial() {
      closeCard();
      if (E.switchToSource) E.switchToSource();
      fetch("/api/config", { cache: "no-store" }).then(function (r) { return r.json(); }).then(function (cfg) {
        var root = String((cfg && cfg.project_root) || "");
        var base = root.replace(/[\\/]+$/, "").split(/[\\/]/).pop();
        if (base === "教程示例") {
          var lines = String(ta.value || "").split("\n");
          for (var i = 0; i < lines.length; i++) {
            if (/^\s*@\s+\S/.test(lines[i])) { setTimeout(function () { focusLine(i + 1); }, 30); return; }
          }
          setTimeout(function () { ta.focus(); }, 30);
          return null;
        }
        var parent = root.replace(/[\\/][^\\/]+$/, "");
        if (!parent || parent === root) throw new Error("找不到配套的 教程示例 目录");
        return fetch("/api/config", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ project_root: parent + "/教程示例" }),
        }).then(function (r) { return r.json(); }).then(function (resp) {
          if (!resp.ok) throw new Error(resp.message || "切换工程失败");
          if (E.toast) E.toast("已切换到教程工程，正在重载…");
          setTimeout(function () { location.reload(); }, 350);
        });
      }).catch(function (err) {
        if (E.toast) E.toast("打开教程工程失败：" + ((err && err.message) || err), true);
      });
    }
    function mkBtn(label, title, fn) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = "icon-btn";
      b.textContent = label;
      b.title = title;
      b.addEventListener("click", fn);
      return b;
    }
    if (actions) {
      var tut = mkBtn("打开教程工程", "从教程示例的第一句台词开始改", openTutorial);
      var write = mkBtn("开始写剧本", "关闭欢迎卡，光标落到源码区", function () {
        closeCard();
        if (E.switchToSource) E.switchToSource();
        setTimeout(function () { ta.focus(); }, 30);
      });
      actions.insertBefore(tut, actions.firstChild);
      actions.insertBefore(write, tut.nextSibling);
    }
    document.addEventListener("keydown", function (ev) {
      if (ev.key === "Escape" && card.style.display !== "none") closeCard();
    }, true);
  })();

  // ==================== T4：预览锚定（默认 @label start，跟随光标台词） ====================
  var origFetch = window.fetch;
  var userMoved = false;

  function isSayLine(line) { return /^@\s+\S/.test(String(line == null ? "" : line).trim()); }
  function startLabelIndex(lines) {
    for (var i = 0; i < lines.length; i++) {
      var t = String(lines[i] || "").trim().replace(/\s*#.*$/, "");
      if (/^@label\s+start$/i.test(t)) return i;
    }
    return -1;
  }
  function cursorLine1() {
    return ta.value.slice(0, ta.selectionStart).split("\n").length;
  }
  function targetSayLine(lines, begin1) {
    var i;
    for (i = begin1 - 1; i < lines.length; i++) if (isSayLine(lines[i])) return i + 1;
    for (i = begin1 - 2; i >= 0; i--) if (isSayLine(lines[i])) return i + 1;
    for (i = 0; i < lines.length; i++) if (isSayLine(lines[i])) return i + 1;
    return 0;
  }
  function buildAnchoredText(lines, scene, target) {
    var out = [], i, t;
    for (i = 0; i < target - 1; i++) {
      t = String(lines[i] || "").trim();
      if (/^@character\s+/.test(t) || /^@set\s+/.test(t)) out.push(t);
    }
    if (scene) {
      if (scene.bg) out.push("@bg " + scene.bg);
      if (scene.music) out.push("@music " + scene.music);
      (scene.sprites || []).forEach(function (s) {
        out.push("@show " + s.char + (s.expr ? " " + s.expr : ""));
      });
    }
    out.push(String(lines[target - 1] || "").trim());
    out.push("@wait 2.0");     // 让背景转场 / 立绘入场完成
    out.push("@end");
    return out.join("\n") + "\n";
  }
  var anchorChip = null;
  function markAnchor(line) {
    window.__previewAnchorLine = line;
    var wrap = document.querySelector(".preview-wrap");
    if (!wrap) return;
    if (!anchorChip) {
      anchorChip = document.createElement("div");
      anchorChip.className = "preview-anchor";
      anchorChip.id = "previewAnchorChip";
      wrap.appendChild(anchorChip);
    }
    anchorChip.textContent = "⌖ 预览 · 第 " + line + " 行";
    anchorChip.classList.add("on");
  }
  function clearAnchor() {
    if (anchorChip) { anchorChip.classList.remove("on"); anchorChip.textContent = ""; }
    window.__previewAnchorLine = 0;
  }
  function placeStart(focus) {
    if (!String(ta.value || "").trim()) return;
    var lines = ta.value.split("\n");
    var idx = startLabelIndex(lines);
    var lineNo = idx >= 0 ? idx : 0;
    var pos = 0;
    for (var i = 0; i < lineNo; i++) pos += lines[i].length + 1;
    var caret = pos + (lines[lineNo] || "").length;
    ta.setSelectionRange(caret, caret);
    ta.scrollTop = window.__hlScrollTopForLine
      ? window.__hlScrollTopForLine(lineNo + 1, 1) : Math.max(0, (lineNo - 2) * LINE_H);
    if (focus) ta.focus();
    ta.dispatchEvent(new Event("click"));
  }
  try {
    ta.addEventListener("mousedown", function () { userMoved = true; });
    ta.addEventListener("keydown", function () { userMoved = true; });
    ta.addEventListener("input", function () { userMoved = true; });
  } catch (e) {}

  // 切换文件后重新锚定到该文件的 @label start（首次加载用定时兜底）
  var origSetLabel = E.setFileLabel;
  if (origSetLabel) {
    E.setFileLabel = function (p) {
      origSetLabel(p);
      userMoved = false;
      setTimeout(function () { if (!userMoved) placeStart(false); }, 0);
    };
  }
  [150, 450, 950].forEach(function (ms) {
    setTimeout(function () { if (!userMoved) placeStart(false); }, ms);
  });

  // 预览请求改写：/api/scene 取目标行场景 → 合成「角色声明 + 场景 + 当前台词」小剧本
  window.fetch = function (url, opts) {
    try {
      if (typeof url === "string" && /^\/api\/preview(?:[?#]|$)/.test(url) &&
          opts && typeof opts.body === "string") {
        var payload = JSON.parse(opts.body);
        var text = payload.text || "";
        if (String(text).trim()) {
          var lines = text.split("\n");
          var startIdx = startLabelIndex(lines);
          var begin1 = userMoved ? cursorLine1() : (startIdx >= 0 ? startIdx + 1 : 1);
          var target = targetSayLine(lines, begin1);
          if (target) {
            var path = payload.path || (window.__proCurPath && window.__proCurPath()) || undefined;
            return origFetch.call(window, "/api/scene", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ text: text, line: target, path: path }),
            }).then(function (r) { return r.json(); }).then(function (scene) {
              if (!scene || !scene.ok) return origFetch.call(window, url, opts);
              var np = {}, k;
              for (k in payload) np[k] = payload[k];
              np.text = buildAnchoredText(lines, scene, target);
              var no = {};
              for (k in opts) no[k] = opts[k];
              no.body = JSON.stringify(np);
              return origFetch.call(window, url, no);
            }).then(function (resp) {
              if (resp && resp.ok) markAnchor(target);
              return resp;
            }).catch(function () {
              return origFetch.call(window, url, opts);
            });
          }
        }
      }
    } catch (e) { /* 回退旧预览 */ }
    return origFetch.apply(window, arguments);
  };

  // 解析失败时收起锚点徽标
  try {
    var st = $("previewState");
    if (st && window.MutationObserver) {
      new MutationObserver(function () {
        if (/解析失败|失败/.test(String(st.textContent || ""))) clearAnchor();
      }).observe(st, { childList: true, characterData: true, subtree: true });
    }
  } catch (e) {}

  // ==================== T6：当前行整行淡背景（错误行红优先由 error-overlay 覆盖） ====================
  (function () {
    var wrap = $("sourceWrap"), nums = $("lineNumbers");
    if (!wrap || !nums) return;
    var hl = document.createElement("div");
    hl.className = "cur-line";
    hl.id = "lineHighlight";
    hl.setAttribute("aria-hidden", "true");
    var hll = wrap.querySelector(".hl-layer");
    if (hll) wrap.insertBefore(hl, hll); else wrap.insertBefore(hl, ta);
    var last = -1, paintRaf = 0;
    // 位置/高度读取放到下一帧做：输入同步里不强制重排（否则大剧本每键多出一次全量 layout）
    function paint() {
      paintRaf = 0;
      var idx = (E.getCursorLine ? E.getCursorLine() : 1) - 1;
      // 软换行行高不等，当前行背景要按高亮层的真实位置/高度走
      var met = (window.__hlLineMetrics && window.__hlLineReady && window.__hlLineReady() === nums.children.length)
        ? window.__hlLineMetrics(idx) : { top: 10 + idx * LINE_H, h: LINE_H };
      hl.style.transform = "translateY(" + (met.top - ta.scrollTop) + "px)";
      hl.style.height = met.h + "px";
    }
    function sync() {
      var idx = (E.getCursorLine ? E.getCursorLine() : 1) - 1;
      if (idx !== last) {
        last = idx;
        if (E.lineNumbersEl) {
          var old = E.lineNumbersEl.querySelector(".ln.cur");
          if (old) old.classList.remove("cur");
          var now = E.lineNumbersEl.querySelector('.ln[data-line="' + (idx + 1) + '"]');
          if (now && !now.classList.contains("err")) now.classList.add("cur");
        }
      }
      if (!paintRaf) paintRaf = requestAnimationFrame(paint);
    }
    ta.addEventListener("scroll", sync, { passive: true });
    ta.addEventListener("click", sync);
    ta.addEventListener("keyup", sync);
    ta.addEventListener("input", sync);
    if (E.onCursor) E.onCursor(function () { sync(); });
    window.addEventListener("resize", sync);
    sync();
  })();

  // ==================== T5：Ctrl+F 查找替换（浮层，不改 textarea 结构） ====================
  var find = { open: false, idx: 0, matches: [], text: "" };
  var findBox = null, findInput = null, findCount = null, findLayer = null;
  var findCase = null, findRe = null, findReplaceInput = null;

  function escHtml(s) {
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }
  function buildFind() {
    if (findBox) return;
    var wrap = $("sourceWrap");
    if (!wrap) return;
    findBox = document.createElement("div");
    findBox.className = "find-box";
    findBox.id = "findBox";
    findBox.innerHTML =
      '<div class="find-row">' +
        '<input id="findInput" class="find-input" type="text" placeholder="查找…" autocomplete="off" spellcheck="false">' +
        '<span class="find-count" id="findCount">0/0</span>' +
        '<label class="find-opt" title="区分大小写"><input id="findCase" type="checkbox">Aa</label>' +
        '<label class="find-opt" title="正则表达式"><input id="findRegex" type="checkbox">.*</label>' +
        '<button type="button" class="find-btn" id="findPrev" title="上一个（Shift+Enter）">↑</button>' +
        '<button type="button" class="find-btn" id="findNext" title="下一个（Enter）">↓</button>' +
        '<button type="button" class="find-btn" id="findClose" title="关闭（Esc）">✕</button>' +
      '</div>' +
      '<div class="find-row">' +
        '<input id="findReplaceInput" class="find-input" type="text" placeholder="替换为…" autocomplete="off" spellcheck="false">' +
        '<button type="button" class="find-btn wide" id="findReplace" title="替换当前匹配">替换</button>' +
        '<button type="button" class="find-btn wide" id="findReplaceAll" title="替换全部匹配">全部替换</button>' +
      '</div>';
    wrap.appendChild(findBox);
    findInput = $("findInput");
    findCount = $("findCount");
    findCase = $("findCase");
    findRe = $("findRegex");
    findReplaceInput = $("findReplaceInput");

    findLayer = document.createElement("pre");
    findLayer.className = "hl-layer find-layer";
    findLayer.setAttribute("aria-hidden", "true");
    wrap.insertBefore(findLayer, ta);

    findInput.addEventListener("input", function () { refreshFind(0); });
    findCase.addEventListener("change", function () { refreshFind(0); });
    findRe.addEventListener("change", function () { refreshFind(0); });
    $("findPrev").addEventListener("click", function () { stepFind(-1); });
    $("findNext").addEventListener("click", function () { stepFind(1); });
    $("findClose").addEventListener("click", closeFind);
    $("findReplace").addEventListener("click", replaceOne);
    $("findReplaceAll").addEventListener("click", replaceAll);
    findReplaceInput.addEventListener("keydown", function (ev) {
      if (ev.key === "Enter") { ev.preventDefault(); replaceOne(); }
    });
    ta.addEventListener("scroll", syncFindScroll, { passive: true });
    window.addEventListener("resize", syncFindScroll);
  }
  function syncFindScroll() {
    if (findLayer) findLayer.style.transform = "translate(" + (-ta.scrollLeft) + "px," + (-ta.scrollTop) + "px)";
  }
  function computeMatches(text) {
    var q = findInput.value;
    if (!q) return [];
    var flags = "g" + (findCase.checked ? "" : "i");
    var re;
    try {
      re = findRe.checked ? new RegExp(q, flags) : new RegExp(q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), flags);
    } catch (e) { return null; }            // 正则写错：显示 0/0，不抛
    var out = [], m;
    if (!re.global) re = new RegExp(re.source, flags);
    while ((m = re.exec(text))) {
      out.push([m.index, m.index + m[0].length]);
      if (!m[0].length) re.lastIndex++;
      if (out.length > 5000) break;
    }
    return out;
  }
  function renderFind() {
    if (!findLayer) return;
    if (!find.open || !find.matches.length) { findLayer.innerHTML = ""; return; }
    var text = find.text, pos = 0, buf = [];
    find.matches.forEach(function (m, i) {
      buf.push(escHtml(text.slice(pos, m[0])));
      buf.push('<mark class="find-hit' + (i === find.idx ? " cur" : "") + '">' + escHtml(text.slice(m[0], m[1])) + "</mark>");
      pos = m[1];
    });
    buf.push(escHtml(text.slice(pos)));
    findLayer.innerHTML = buf.join("") || " ";
    syncFindScroll();
    if (findCount) findCount.textContent = find.matches.length ? (find.idx + 1) + "/" + find.matches.length : "0/0";
  }
  function ensureVisible(pos) {
    var line = ta.value.slice(0, pos).split("\n").length - 1;
    // 软换行行高不等：取高亮层的真实行顶坐标，而不是 line * 固定行高
    var met = (window.__hlScrollTopForLine && window.__hlLineReady
      && window.__hlLineReady() === (ta.value.split("\n")).length)
      ? { top: window.__hlScrollTopForLine(line + 1, 0) } : { top: line * LINE_H };
    var top = met.top, h = ta.clientHeight;
    if (top < ta.scrollTop + 10) ta.scrollTop = Math.max(0, top - 24);
    else if (top > ta.scrollTop + h - 48) ta.scrollTop = Math.max(0, top - h + 64);
  }
  function selectMatch(i) {
    if (!find.matches.length) { if (findCount) findCount.textContent = "0/0"; renderFind(); return; }
    find.idx = (i % find.matches.length + find.matches.length) % find.matches.length;
    var m = find.matches[find.idx];
    ta.focus();
    ta.setSelectionRange(m[0], m[1]);
    ensureVisible(m[0]);
    renderFind();
  }
  function refreshFind(sel) {
    if (!find) return;
    find.text = ta.value;
    var ms = computeMatches(find.text);
    find.matches = ms || [];
    if (sel === "caret" && find.matches.length) {
      var c = ta.selectionStart, pick = 0;
      for (var i = 0; i < find.matches.length; i++) { if (find.matches[i][0] >= c) { pick = i; break; } }
      selectMatch(pick);
    } else if (find.matches.length) {
      selectMatch(0);
    } else {
      if (findCount) findCount.textContent = "0/0";
      renderFind();
    }
  }
  function stepFind(dir) {
    if (!find.matches.length) return;
    var i = find.idx + dir;
    if (i < 0) i = find.matches.length - 1;
    if (i >= find.matches.length) i = 0;
    selectMatch(i);
  }
  function applyEdit(text, caret) {
    if (E.setSourceValue) E.setSourceValue(text, caret, caret);
    else {
      ta.value = text;
      ta.setSelectionRange(caret, caret);
    }
    ta.dispatchEvent(new Event("input"));     // 同步缓冲 / 脏标记 / 行号
    ta.focus();
  }
  function replaceOne() {
    if (!find.matches.length) return;
    if (ta.value !== find.text) refreshFind(0);
    var m = find.matches[find.idx];
    if (!m) return;
    var val = findReplaceInput.value;
    var next = ta.value.slice(0, m[0]) + val + ta.value.slice(m[1]);
    var caret = m[0] + val.length;
    applyEdit(next, caret);
    refreshFind("caret");
  }
  function replaceAll() {
    if (!find.matches.length) return;
    if (ta.value !== find.text) refreshFind(0);
    var text = ta.value, out = "", pos = 0;
    find.matches.forEach(function (m) { out += text.slice(pos, m[0]) + findReplaceInput.value; pos = m[1]; });
    out += text.slice(pos);
    applyEdit(out, ta.selectionStart);
    refreshFind(0);
  }
  function openFind() {
    buildFind();
    if (!findBox) return;
    find.open = true;
    findBox.classList.add("open");
    findInput.focus();
    findInput.select();
    if (findInput.value) refreshFind(0);
    else { find.matches = []; if (findCount) findCount.textContent = "0/0"; renderFind(); }
  }
  function closeFind() {
    if (!find.open) return;
    find.open = false;
    if (findBox) findBox.classList.remove("open");
    find.matches = [];
    renderFind();
    ta.focus();
  }
  document.addEventListener("keydown", function (ev) {
    var key = String(ev.key || "").toLowerCase();
    if ((ev.ctrlKey || ev.metaKey) && key === "f") {
      ev.preventDefault();
      openFind();
      return;
    }
    if (!find.open) return;
    if (ev.key === "Escape") {
      ev.preventDefault();
      ev.stopPropagation();
      closeFind();
      return;
    }
    if (ev.key === "Enter" && ev.target === findInput) {
      ev.preventDefault();
      stepFind(ev.shiftKey ? -1 : 1);
    }
  }, true);

  // ==================== T7：右侧面板标签化（预览 / 检查器 / 时间线） ====================
  (function () {
    var pane = document.querySelector(".right-pane");
    if (!pane) return;
    var tabs = document.createElement("div");
    tabs.className = "right-tabs";
    tabs.id = "rightTabs";
    tabs.setAttribute("role", "tablist");
    var names = [["preview", "预览"], ["inspector", "检查器"], ["timeline", "时间线"]];
    names.forEach(function (n) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = "right-tab";
      b.dataset.rightTab = n[0];
      b.setAttribute("role", "tab");
      b.textContent = n[1];
      b.title = n[1] + " · 右侧栏显示对应区块";
      b.addEventListener("click", function () { apply(n[0]); });
      tabs.appendChild(b);
    });
    pane.insertBefore(tabs, pane.firstChild);
    var saved = "preview";
    try { saved = localStorage.getItem("gal_right_tab") || "preview"; } catch (e) {}
    if (!/^(preview|inspector|timeline)$/.test(saved)) saved = "preview";
    function apply(name) {
      pane.dataset.rtab = name;
      tabs.querySelectorAll(".right-tab").forEach(function (b) {
        var on = b.dataset.rightTab === name;
        b.classList.toggle("active", on);
        b.setAttribute("aria-selected", on ? "true" : "false");
      });
      try { localStorage.setItem("gal_right_tab", name); } catch (e) {}
    }
    apply(saved);
  })();

  // 首次同步（DOM 已就绪）
  window.__proToolbarSync();
  window.__statusSaveSync();
})();


/* ===================================================================
   UI 文案归一（2026-11-01，图标/文字取舍）：
   - 图标只做图标（通用语义：保存/刷新/折叠/新建），配 tooltip；
   - 文字只做文字（面板标题、菜单、弹窗按钮），去掉中英双写；
   - 只有「新人必须找到」的主操作保留 图标+文字（运行 / 打包发布）。
   参考：VSCode UX（Activity Bar 用图标+清晰名称；工具栏图标取库、次要操作收进 overflow）；
   Godot/Unity 工具栏 = 纯图标 + tooltip，菜单/检查器 = 纯文字。不抄 AI 面板。
   =================================================================== */
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };

  // 1) 通用「＋」按钮：图标-only（新建章节 / 导入素材），文字信息交给 tooltip + aria-label
  var PLUS = '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg>';
  function toIconOnly(btn) {
    if (!btn) return;
    var label = btn.title || btn.textContent.trim();
    btn.innerHTML = PLUS;
    btn.title = label;
    btn.setAttribute("aria-label", label);
    btn.classList.add("icon-only");
  }
  toIconOnly($("btnNewChapter"));
  toIconOnly($("assetImportBtn"));

  // 2) title 去中英双写： "Explorer · 工程文件" → "工程文件"
  var titled = document.querySelectorAll("[title]");
  for (var i = 0; i < titled.length; i++) {
    var raw = titled[i].getAttribute("title") || "";
    var fixed = raw.replace(/^[A-Za-z][A-Za-z0-9 ./&-]{1,40}?\s*·\s*/u, "");
    if (fixed !== raw) titled[i].setAttribute("title", fixed);
  }

  // 3) 面板标题去英文后缀（属性检查器 · Inspector → 属性检查器）
  var heads = document.querySelectorAll(".inspector-head > span:first-child, .dp-head > span:first-child");
  for (var j = 0; j < heads.length; j++) {
    heads[j].textContent = heads[j].textContent.replace(/\s*·\s*[A-Za-z][A-Za-z ]*$/, "");
  }
})();


/* ===================================================================
   界面衔接批（2026-11-01）：桌宠开关 + 设置中心分页
   - 桌宠：编辑器内「打开/关闭 Mooki」走 /api/pet（源码模式可用，发行包明确提示）
   - 设置中心：把散落的「工程/数据/启动动画」与「UI 设计区 / 桌宠 / 关于」收进一个
     分页面板（Trae 式左侧分类 + 内容），而不是三个互不相通的弹窗。
   =================================================================== */
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var E = window.__editor || {};

  function toast(msg, isErr) {
    try {
      if (E.toast) { E.toast(msg, !!isErr); return; }
    } catch (e) {}
    console.log("[editor]", msg);
  }

  function petFetch(action) {
    return fetch("/api/pet", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: action }),
    }).then(function (r) { return r.json(); });
  }

  // ---------- 桌宠：菜单 / 设置中心共用入口 ----------
  window.__petToggle = function () {
    petFetch("status").then(function (st) {
      return petFetch(st && st.running ? "stop" : "start");
    }).then(function (resp) {
      toast(resp.message || (resp.running ? "桌宠已打开" : "桌宠已关闭"), resp.ok === false);
      syncPetStatus(resp.running);
    }).catch(function (e) { toast("桌宠操作失败：" + e, true); });
  };

  function syncPetStatus(running) {
    var span = $("setPetStatus"), btn = $("setPetToggle");
    if (!span || !btn) return;
    span.textContent = running ? "运行中" : "已关闭";
    span.classList.toggle("on", !!running);
    btn.textContent = running ? "关闭桌宠" : "打开桌宠";
  }

  function refreshPetStatus() {
    petFetch("status").then(function (resp) {
      syncPetStatus(!!(resp && resp.running));
    }).catch(function () { syncPetStatus(false); });
  }

  // ---------- 设置中心：分页 ----------
  (function buildSettingsCenter() {
    var mask = $("settingsModal");
    if (!mask) return;
    var modal = mask.querySelector(".modal");
    if (!modal) return;
    var title = modal.querySelector(".modal-title");
    var actions = modal.querySelector(".modal-actions");
    var err = $("settingsErr");
    if (!title || !actions) return;

    var pane1 = document.createElement("div");
    pane1.className = "set-pane";
    [].slice.call(modal.children).forEach(function (el) {
      if (el === title || el === actions || el === err) return;
      pane1.appendChild(el);
    });

    var pane2 = document.createElement("div");
    pane2.className = "set-pane";
    pane2.style.display = "none";
    pane2.innerHTML =
      '<h3 class="set-h">游戏界面</h3>' +
      '<p class="set-p">圆角 / 位置 / 大小 / 像素化 / 正文字号 / 行距，都在「UI 设计区」里实时预览并写回 config.json。</p>' +
      '<button type="button" class="icon-btn" id="setOpenUiDesign">打开 UI 设计区</button>' +
      '<p class="set-hint">玩家侧设置（显示模式、音量、字号三档）在游戏里按 Esc → 设置。</p>';

    var pane3 = document.createElement("div");
    pane3.className = "set-pane";
    pane3.style.display = "none";
    pane3.innerHTML =
      '<h3 class="set-h">桌宠 Mooki（实验功能）</h3>' +
      '<p class="set-p">会跟着鼠标、能拖动的小桌宠。默认关闭，随编辑器一起分发；打开后可拖动 / 双击弹爱心 / 右键菜单，Esc 关闭。</p>' +
      '<div class="set-row"><span class="set-status" id="setPetStatus">状态未知</span>' +
      '<button type="button" class="icon-btn" id="setPetToggle">打开桌宠</button></div>' +
      '<p class="set-hint">打开后可拖动 / 双击弹爱心 / 右键菜单，Esc 关闭。</p>';

    var pane4 = document.createElement("div");
    pane4.className = "set-pane";
    pane4.style.display = "none";
    pane4.innerHTML =
      '<h3 class="set-h">关于 MYONL</h3>' +
      '<p class="set-p">MYONL 引擎 · 视觉小说创作工具。示例工程与教程都在游戏的 <b>games/</b> 下，可随意改。</p>' +
      '<p class="set-hint">快捷键：Ctrl+S 保存 · Ctrl+F 查找替换 · Ctrl+Shift+F 全局搜索 · Ctrl+, 设置中心 · F1 教程</p>';

    var PANES = [["工程与数据", pane1], ["游戏界面", pane2], ["桌宠", pane3], ["关于", pane4]];
    var body = document.createElement("div");
    body.className = "set-body";
    var tabBar = document.createElement("div");
    tabBar.className = "set-tabs";
    var content = document.createElement("div");
    content.className = "set-content";

    function select(name, idx) {
      [].forEach.call(tabBar.children, function (b, i) {
        b.classList.toggle("active", i === idx);
      });
      PANES.forEach(function (p, i) { p[1].style.display = i === idx ? "block" : "none"; });
      if (name === "桌宠") refreshPetStatus();
    }

    PANES.forEach(function (p, i) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = "set-tab" + (i === 0 ? " active" : "");
      b.textContent = p[0];
      b.addEventListener("click", function () { select(p[0], i); });
      tabBar.appendChild(b);
      content.appendChild(p[1]);
    });

    body.appendChild(tabBar);
    body.appendChild(content);
    modal.insertBefore(body, title.nextSibling);
    modal.classList.add("settings-center");
    title.textContent = "设置中心";

    if ($("setOpenUiDesign")) {
      $("setOpenUiDesign").addEventListener("click", function () {
        var cancel = $("settingsCancel");
        if (cancel) cancel.click();
        var ui = $("btnUIDesign");
        if (ui) ui.click();
      });
    }
    if ($("setPetToggle")) {
      $("setPetToggle").addEventListener("click", function () { window.__petToggle(); });
    }
    // 打开设置时刷新桌宠状态
    new MutationObserver(function () {
      if (mask.style.display && mask.style.display !== "none") refreshPetStatus();
    }).observe(mask, { attributes: true, attributeFilter: ["style"] });
  })();
})();

/* ===================================================================
   交互一致性批：Esc 关闭所有弹窗（设置中心 / UI 设计 / 打包 / 新建 / 冲突）
   统一兜底：任何可见的 .modal-mask 在 Esc 时走它自己的「取消/关闭」按钮。
   =================================================================== */
(function () {
  "use strict";
  var CLOSERS = ["settingsCancel", "uidClose", "packClose", "newGameCancel", "newChapterCancel", "conflictCancel"];
  document.addEventListener("keydown", function (ev) {
    if (ev.key !== "Escape") return;
    var masks = document.querySelectorAll(".modal-mask");
    for (var i = 0; i < masks.length; i++) {
      var m = masks[i];
      if (!m.style || m.style.display === "none" || getComputedStyle(m).display === "none") continue;
      for (var c = 0; c < CLOSERS.length; c++) {
        var btn = document.getElementById(CLOSERS[c]);
        if (btn && m.contains(btn)) { btn.click(); ev.preventDefault(); return; }
      }
    }
  });
})();

/* 顶部标题栏：产品名 + 全局搜索框（Enter 打开全局搜索结果） */
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var input = $("mbSearchInput");
  if (!input) return;
  function openResults(q) {
    var act = $("actSearch");
    if (act) act.click();
    setTimeout(function () {
      var qs = $("qsInput");
      if (qs && q) { qs.value = q; qs.dispatchEvent(new Event("input")); }
      if (qs) qs.focus();
    }, 30);
  }
  input.addEventListener("keydown", function (ev) {
    if (ev.key === "Enter") { ev.preventDefault(); openResults(input.value.trim()); }
    if (ev.key === "Escape") { input.value = ""; input.blur(); }
  });
})();

/* 衔接批 2：右栏空状态引导 + 设置中心搜索 */
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };

  // 1) 预览空状态：给「导入素材 / 运行游戏」两个真实动作，而不是一句死文案
  (function () {
    var wrap = $("previewWrap");
    if (!wrap) return;
    function augment() {
      var ph = wrap.querySelector(".preview-placeholder");
      if (!ph || ph.getAttribute("data-aug")) return;
      ph.setAttribute("data-aug", "1");
      ph.innerHTML = '<div class="empty-title">还没有可看的画面</div>' +
        '<div class="empty-sub">先写一句台词，或点下面按钮试试。</div>' +
        '<div class="empty-actions">' +
        '<button type="button" class="icon-btn" data-empty="import">导入素材</button>' +
        '<button type="button" class="icon-btn" data-empty="run">运行游戏</button>' +
        "</div>";
    }
    wrap.addEventListener("click", function (ev) {
      var b = ev.target.closest ? ev.target.closest("[data-empty]") : null;
      if (!b) return;
      var act = b.getAttribute("data-empty");
      if (act === "import") { var a = $("assetImportBtn"); if (a) a.click(); }
      if (act === "run") { var r = $("btnRun"); if (r) r.click(); }
    });
    new MutationObserver(augment).observe(wrap, { childList: true, subtree: true });
    augment();
  })();

  // 2) 设置中心：顶部搜索框，过滤当前页的设置项
  var settingsModal = $("settingsModal");
  if (!settingsModal) return;
  var content = settingsModal.querySelector(".set-content");
  if (!content) return;
  var search = document.createElement("input");
  search.className = "set-search";
  search.type = "search";
  search.placeholder = "搜索设置…（按当前分类过滤）";
  content.insertBefore(search, content.firstChild);
  search.addEventListener("input", function () {
    var q = search.value.trim().toLowerCase();
    var pane = null;
    content.querySelectorAll(":scope > .set-pane").forEach(function (p) {
      if (p.style.display !== "none") pane = p;
    });
    if (!pane) return;
    pane.querySelectorAll(":scope > *").forEach(function (el) {
      if (!q) { el.style.display = ""; return; }
      el.style.display = (el.textContent || "").toLowerCase().indexOf(q) >= 0 ? "" : "none";
    });
  });
})();

/* ===================================================================
   中心页面模式：设置中心 / UI 设计区 直接在中间编辑区打开（不是弹窗遮罩）
   - 像编辑器里的一个页面：顶部有标题 + 「并排」「关闭」，可随时关掉再打开；
   - 「并排」= 页面放到编辑区右侧，左边继续看剧本，调整时对照；
   - 实现：拦截原弹窗的显示，把 .modal 移进中心页面，关闭时再放回掩罩（主脚本逻辑零改动）。
   =================================================================== */
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var pane = document.querySelector(".left-pane");
  var tabs = $("editorTabs");
  if (!pane || !tabs) return;
  var page = document.createElement("div");
  page.className = "center-page";
  page.innerHTML = '<div class="cp-head">' +
    '<span class="cp-title" id="cpTitle">设置中心</span>' +
    '<span class="cp-hint">调整后点保存即可，随时可关掉</span>' +
    '<span class="cp-spacer"></span>' +
    '<button type="button" class="cp-btn" id="cpSplit" title="并排：页面放右侧，左边继续写剧本">并排</button>' +
    '<button type="button" class="cp-btn" id="cpClose" title="关闭页面（Esc）">✕ 关闭</button>' +
    "</div>" +
    '<div class="cp-body" id="cpBody"></div>';
  pane.appendChild(page);
  var host = $("cpBody"), titleEl = $("cpTitle");
  var HOSTS = {};   // maskId → {mask, placeholder}
  var current = null;

  function fit() {
    var top = 0;
    var child = tabs;
    while (child && child !== pane) { top += child.offsetTop; child = child.offsetParent; }
    page.style.top = (tabs.offsetTop + tabs.offsetHeight) + "px";
  }

  function remember(maskId) {
    if (HOSTS[maskId]) return HOSTS[maskId];
    var mask = $(maskId);
    if (!mask) return null;
    var ph = document.createElement("span");
    ph.className = "cp-ph";
    mask.appendChild(ph);
    HOSTS[maskId] = { mask: mask, ph: ph };
    return HOSTS[maskId];
  }

  function openPage(maskId, title) {
    var h = remember(maskId);
    if (!h) return;
    var modal = h.mask.querySelector(".modal");
    if (!modal) return;
    if (modal.parentNode !== host) host.appendChild(modal);
    titleEl.textContent = title;
    page.classList.add("open");
    host.scrollTop = 0;
    fit();
    current = { maskId: maskId, modal: modal };
    h.mask.style.display = "none";
  }

  function closePage() {
    if (!current) return;
    var h = HOSTS[current.maskId];
    if (h && h.ph && h.ph.parentNode) h.ph.parentNode.replaceChild(current.modal, h.ph);
    if (h) h.mask.style.display = "none";
    page.classList.remove("open");
    page.classList.remove("split");
    var splitBtn = $("cpSplit");
    if (splitBtn) splitBtn.classList.remove("on");
    current = null;
  }

  function intercept(maskId, title) {
    var h = remember(maskId);
    if (!h || !window.MutationObserver) return;
    new MutationObserver(function () {
      if (h.mask.style.display && h.mask.style.display !== "none") openPage(maskId, title);
    }).observe(h.mask, { attributes: true, attributeFilter: ["style"] });
  }
  intercept("settingsModal", "设置中心");
  intercept("uiDesignModal", "UI 设计区");

  $("cpSplit").addEventListener("click", function () {
    page.classList.toggle("split");
    this.classList.toggle("on", page.classList.contains("split"));
    fit();
  });
  $("cpClose").addEventListener("click", closePage);

  // 取消/保存/关闭类按钮点完自动收页面（主脚本先处理，收尾我们做）
  var CLOSERS = ["settingsCancel", "settingsOk", "uidClose", "uidSave", "packClose"];
  host.addEventListener("click", function (ev) {
    var btn = ev.target.closest ? ev.target.closest("button") : null;
    if (!btn) return;
    if (CLOSERS.indexOf(btn.id) >= 0) setTimeout(closePage, 0);
  }, true);

  document.addEventListener("keydown", function (ev) {
    if (ev.key !== "Escape" || !page.classList.contains("open")) return;
    var closer = current ? current.modal.querySelector("#settingsCancel, #uidClose") : null;
    if (closer) closer.click(); else closePage();
    ev.preventDefault();
    ev.stopPropagation();
  }, true);

  window.addEventListener("resize", function () { if (page.classList.contains("open")) fit(); });
  window.__centerPageOpen = function (which) {
    if (which === "ui") { var b = $("btnUIDesign"); if (b) b.click(); }
    else { var s = $("btnSettings"); if (s) s.click(); }
  };
})();

/* ===================================================================
   主题 / 语言 / 游戏界面位置（2026-11-01 用户要求）：
   - 深色 / 浅色两套编辑器主题（状态栏/菜单/设置中心「外观」页均可换，记忆到 localStorage）；
   - 状态栏语言下拉：剧本文本(.gal) / 纯文本 / JSON —— 只换显示，不影响保存格式；
   - 游戏界面（右侧预览）可在左/右之间切换（预览条 ⇌ 按钮、视图菜单）。
   =================================================================== */
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  function toast(msg) { try { if (window.__editor && window.__editor.toast) window.__editor.toast(msg); } catch (e) {} }

  // ---------- 1. 编辑器主题（深色 / 浅色） ----------
  var THEME_KEY = "gal_editor_theme";
  function currentTheme() { return document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark"; }
  function applyTheme(t) {
    t = t === "light" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", t);
    try { localStorage.setItem(THEME_KEY, t); } catch (e) {}
    var picks = document.querySelectorAll("[data-theme-pick]");
    for (var i = 0; i < picks.length; i++) picks[i].classList.toggle("on", picks[i].getAttribute("data-theme-pick") === t);
  }
  var savedTheme = null;
  try { savedTheme = localStorage.getItem(THEME_KEY); } catch (e) {}
  applyTheme(savedTheme === "light" ? "light" : "dark");
  window.__setEditorTheme = applyTheme;
  window.__themeToggle = function () { applyTheme(currentTheme() === "light" ? "dark" : "light"); toast(currentTheme() === "light" ? "已切换到浅色界面" : "已切换到深色界面"); };

  // ---------- 2. 语言（只影响高亮显示） ----------
  var LANG_KEY = "gal_editor_lang";
  var langSel = $("sbLang");
  function applyLang(v) {
    v = (v === "plain" || v === "json") ? v : "gal";
    if (window.__hlSetMode) window.__hlSetMode(v);
    if (langSel) langSel.value = v;
    try { localStorage.setItem(LANG_KEY, v); } catch (e) {}
  }
  if (langSel) {
    var savedLang = null;
    try { savedLang = localStorage.getItem(LANG_KEY); } catch (e) {}
    applyLang(savedLang || "gal");
    langSel.addEventListener("change", function () { applyLang(langSel.value); });
  }
  window.__setEditorLang = applyLang;

  // ---------- 3. 游戏界面（右栏）位置：右 / 左 ----------
  var SIDE_KEY = "gal_preview_side";
  function applySide(side) {
    var main = document.querySelector(".main");
    if (!main) return;
    main.classList.toggle("preview-left", side === "left");
    try { localStorage.setItem(SIDE_KEY, side); } catch (e) {}
    var b = $("pvSide");
    if (b) b.title = side === "left" ? "游戏界面在左侧（点击换回右侧）" : "游戏界面在右侧（点击换到左侧）";
  }
  var savedSide = null;
  try { savedSide = localStorage.getItem(SIDE_KEY); } catch (e) {}
  applySide(savedSide === "left" ? "left" : "right");
  window.__previewSideToggle = function () {
    var main = document.querySelector(".main");
    var left = main && main.classList.contains("preview-left");
    applySide(left ? "right" : "left");
    toast(left ? "游戏界面已放回右侧" : "游戏界面已移到左侧");
  };
  var sideBtn = $("pvSide");
  if (sideBtn) sideBtn.addEventListener("click", window.__previewSideToggle);

  // ---------- 4. 设置中心「外观」页 ----------
  function addAppearanceTab() {
    var mask = $("settingsModal");
    if (!mask) return;
    var tabs = mask.querySelector(".set-tabs"), content = mask.querySelector(".set-content");
    if (!tabs || !content || $("setAppearanceTab")) return;
    var btn = document.createElement("button");
    btn.type = "button"; btn.className = "set-tab"; btn.id = "setAppearanceTab"; btn.textContent = "外观";
    var pane = document.createElement("div");
    pane.className = "set-pane"; pane.id = "setAppearancePane"; pane.style.display = "none";
    pane.innerHTML = '<h3 class="set-h">外观</h3>' +
      '<p class="set-p">编辑器界面主题，点击立即生效，下次打开沿用。</p>' +
      '<div class="set-row"><button type="button" class="icon-btn" data-theme-pick="dark">深色</button>' +
      '<button type="button" class="icon-btn" data-theme-pick="light">浅色</button></div>' +
      '<p class="set-hint">注意：这里只换编辑器界面；游戏画面的主题（对话框/标题排版）在「游戏界面 → UI 设计区」里改。</p>';
    tabs.appendChild(btn);
    content.appendChild(pane);
    btn.addEventListener("click", function () {
      var all = tabs.querySelectorAll(".set-tab");
      for (var i = 0; i < all.length; i++) all[i].classList.toggle("active", all[i] === btn);
      var panes = content.querySelectorAll(":scope > .set-pane");
      for (var j = 0; j < panes.length; j++) panes[j].style.display = panes[j] === pane ? "block" : "none";
    });
    tabs.addEventListener("click", function (ev) {
      var t = ev.target.closest ? ev.target.closest(".set-tab") : null;
      if (t && t !== btn) pane.style.display = "none";
    });
    var picks = pane.querySelectorAll("[data-theme-pick]");
    for (var k = 0; k < picks.length; k++) {
      picks[k].addEventListener("click", function () { applyTheme(this.getAttribute("data-theme-pick")); });
      picks[k].classList.toggle("on", picks[k].getAttribute("data-theme-pick") === currentTheme());
    }
  }
  addAppearanceTab();
  // 设置中心页面是懒渲染的，DOM 就绪后再补一次
  if (document.readyState !== "complete") document.addEventListener("DOMContentLoaded", addAppearanceTab);

  // ---------- 5. 语言选择也放进设置中心「外观」页（可选） ----------
  window.__openAppearance = function () { var b = $("setAppearanceTab"); if (b) b.click(); };
})();

/* ===================================================================
   顶部显式入口（场景 / 角色 / 素材 / 设置）：
   非技术用户不用先去菜单里找，标签直接看得见、点得开。
   =================================================================== */
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  function wire(id, fn) {
    var el = $(id);
    if (!el) return;
    el.addEventListener("click", function () {
      try { fn(); } catch (e) { if (window.console) console.error("[入口] " + id + " 打开失败", e); }
    });
  }
  wire("mbScene", function () { if (window.__openSceneEditor) window.__openSceneEditor(); });
  wire("mbChars", function () { if (window.__openCharacterManager) window.__openCharacterManager(); });
  wire("mbAsset", function () { var b = $("btnAssets"); if (b) b.click(); });
  wire("mbSet", function () { var b = $("btnSettings"); if (b) b.click(); });
})();

