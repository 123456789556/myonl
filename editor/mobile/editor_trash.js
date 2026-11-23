/* P203 作品更多操作 / 垃圾箱 / 素材库页。
   手机离线内核只有一个写路由 /api/new，作品删不掉、改不了名 —— 用户四个
   「未命名」只能一直堆在列表里。这里补三件事，全部走同一个 localStorage
   作品库，不新增后端路由（在线端本来就各有各的接口，不该被这套覆盖）：
   1) 每张卡的「⋯」→ 改名 / 删除；
   2) 删除先进垃圾箱（30 天可还原），彻底删才真没了；
   3) 底栏「素材库」：列出现有素材（图 / 音频 / 视频）、删除、导入。
   依赖：window.__myonlLib（gal_offline.js 暴露 read/write）、
        window.MYONLRenameProject（ui_layout.js 暴露的三处同步改名）。 */
(function () {
  "use strict";
  var TRASH_KEY = "myonl:off:trash:v1";
  var DAY = 86400000;          // 垃圾箱按毫秒算日子，作品库里的时间戳是秒
  var KEEP_DAYS = 30;

  function libApi() { return window.__myonlLib || null; }
  function $(id) { return document.getElementById(id); }
  // P209：统一弹窗（editor_dialog.js）。没加载成功就退回系统框，别让按钮哑掉。
  function dlgConfirm(o) {
    if (window.MYONLDialog) return window.MYONLDialog.confirm(o);
    return Promise.resolve(!!window.confirm(((o && o.title) || "") + "\n" + ((o && o.msg) || "")));
  }
  function esc(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;")
      .replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
  function toast(msg) {
    var t = document.createElement("div");
    t.className = "m-home-toast";
    t.textContent = msg;
    document.body.appendChild(t);
    setTimeout(function () { t.remove(); }, 2400);
  }

  // ---- 默认名：未命名 1 / 未命名 2 ……
  // P202 用「未命名 · MMDD-HHMM」，四个作品同一天建的，前 12 个字全一样，
  // 卡片上被省略号切完就分不清谁是谁。序号最短、最好认。
  function nextName(lib) {
    var n = 0, seen = {};
    (lib.projects || []).forEach(function (p) {
      var m = /^未命名(?:\s*(\d+))?$/.exec(String(p.name || ""));
      if (!m) return;
      seen[Number(m[1] || 1)] = 1;
      n = Math.max(n, Number(m[1] || 1));
    });
    n += 1;
    while (seen[n]) n += 1;
    return "未命名 " + n;
  }

  // ---- 垃圾箱读写
  function readTrash() {
    var rows = [];
    try { rows = JSON.parse(localStorage.getItem(TRASH_KEY) || "[]") || []; } catch (e) { rows = []; }
    if (!Array.isArray(rows)) rows = [];
    var cut = Date.now() - KEEP_DAYS * DAY;
    var keep = rows.filter(function (r) { return r && r.delAt && r.delAt > cut; });
    if (keep.length !== rows.length) writeTrash(keep);   // 超期的当场清掉
    return keep;
  }
  function writeTrash(rows) {
    try { localStorage.setItem(TRASH_KEY, JSON.stringify(rows)); } catch (e) {}
  }

  // 批量删除：一次搬 N 个进垃圾箱，只 reload 一次。
  // 一个个删会连续 reload N 次，选五个就像卡死了。
  function delMany(names) {
    var api = libApi();
    if (!api) { toast("这台设备没有离线内核"); return; }
    var lib = api.read(), rows = readTrash(), gone = [];
    names.forEach(function (nm) {
      for (var i = 0; i < lib.projects.length; i++) {
        if (lib.projects[i].name === nm) {
          var p = lib.projects.splice(i, 1)[0];
          rows.push({ name: p.name, text: p.text, ctime: p.ctime, mtime: p.mtime, delAt: Date.now() });
          gone.push(p.name);
          break;
        }
      }
    });
    if (!gone.length) { toast("没有可删的"); return; }
    writeTrash(rows);
    if (gone.indexOf(lib.current) >= 0) lib.current = lib.projects[0] ? lib.projects[0].name : "";
    api.write(lib);
    // 草稿跟着走，否则同名新建会把旧草稿接上去
    gone.forEach(function (nm) {
      try { if (window.MYONLDraft && window.MYONLDraft.drop) window.MYONLDraft.drop(nm); } catch (e) {}
    });
    location.reload();
  }

  function del(name) { delMany([name]); }

  function restoreMany(names) {
    var api = libApi();
    if (!api || !names || !names.length) return;
    var rows = readTrash(), lib = api.read(), done = 0, dup = 0;
    names.forEach(function (nm) {
      var at = -1;
      for (var i = 0; i < rows.length; i++) if (rows[i].name === nm) { at = i; break; }
      if (at < 0) return;
      // 库里有同名就跳过：硬塞进去会出现两个同名的，之后改名/删除都会挑错
      if (lib.projects.some(function (p) { return p.name === nm; })) { dup++; return; }
      var r = rows.splice(at, 1)[0];
      lib.projects.push({ name: r.name, text: r.text, ctime: r.ctime, mtime: r.mtime });
      done++;
    });
    api.write(lib);
    writeTrash(rows);
    if (!done) {
      toast(dup ? "都有同名作品，先改个名再还原" : "垃圾箱里没有它们");
      return;
    }
    if (dup) toast("还原 " + done + " 个，另有 " + dup + " 个同名跳过");
    location.reload();
  }

  function restore(name) { restoreMany([name]); }

  function purgeMany(names) {
    if (!names || !names.length) return;
    var rows = readTrash().filter(function (r) { return names.indexOf(r.name) < 0; });
    writeTrash(rows);
    binSel = {};
    toast("已彻底删除 " + names.length + " 个");
    if (binEl) openBin(true);
  }

  function purge(name) { purgeMany([name]); }

  // ---- 「⋯」：贴着那颗按钮弹的小菜单（不是底部抽屉、不铺灰罩）
  // P257 用户原话：「不要出现灰色」「弹窗会出现在省略号附近，不遮挡选中的卡片」
  // 「不占全屏，只占少部分屏幕，而不是靠着屏幕边缘」。
  var moreEl = null, moreOff = null, moreAnchor = null;
  function closeMore() {
    if (moreEl) { moreEl.remove(); moreEl = null; }
    if (moreOff) { document.removeEventListener("pointerdown", moreOff, true); moreOff = null; }
    moreAnchor = null;
  }
  var MOR_ICON = {
    ren: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"><path d="M2.6 12.2l.5-2.5 6.6-6.6 2 2-6.6 6.6-2.5.5zM9.4 3.6l2 2"/></svg>',
    exp: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"><path d="M8 2.2v7M5.5 6.8L8 9.3l2.5-2.5M3.2 11.4v1.6h9.6v-1.6"/></svg>',
    imp: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"><path d="M8 9.3V2.3M5.5 4.8L8 2.3l2.5 2.5M3.2 11.4v1.6h9.6v-1.6"/></svg>',
    dup: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"><rect x="5.6" y="5.6" width="7.8" height="7.8" rx="1.8"/><path d="M10.4 2.6H3.6a1 1 0 0 0-1 1v6.8"/></svg>',
    hist: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"><circle cx="8" cy="8" r="5.6"/><path d="M8 5.1v3.2l2.1 1.3"/></svg>',
    del: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"><path d="M2.9 4.4h10.2M6.3 4.4V2.9h3.4v1.5M4.5 4.4l.7 9h5.6l.7-9"/></svg>'
  };

  // 落点：先试卡片下方（不盖住正在看的那张卡），放不下挪到卡片上方，再不行才贴底；
  // 左右右对齐到那颗 ⋯，四周至少留 12px —— 用户明确说「不要靠着屏幕边缘」。
  function placeMore(anchor) {
    var w = moreEl.offsetWidth, h = moreEl.offsetHeight;
    var vw = window.innerWidth, vh = window.innerHeight, M = 12;
    var top, left;
    var ar = (anchor && anchor.getBoundingClientRect) ? anchor.getBoundingClientRect() : null;
    // 垂直按「整张卡」算，不按那颗 ⋯ 算 —— 按按钮算会压住卡片下半截
    var host = (anchor && anchor.closest) ? anchor.closest(".m-home-card, .m-home-hero") : null;
    var r = (host && host.getBoundingClientRect && host.getBoundingClientRect().width) ? host.getBoundingClientRect() : ar;
    if (r && r.width && r.height) {
      left = Math.max(M, Math.min(vw - w - M, (ar ? ar.right : r.right) - w));
      if (vh - r.bottom - M >= h + 8) top = r.bottom + 8;
      else if (r.top - M >= h + 8) top = r.top - h - 8;
      else top = Math.max(M, Math.min(vh - h - M, r.bottom + 8));
    } else {
      left = Math.max(M, Math.min(vw - w - M, (vw - w) / 2));
      top = Math.max(M, vh - h - 96);
    }
    moreEl.style.left = Math.round(left) + "px";
    moreEl.style.top = Math.round(top) + "px";
  }

  function more(name, hasBin, anchor) {
    // 再点同一颗 ⋯ = 收起（不然点一下又重开，看着像没反应）
    var hostCard = (anchor && anchor.closest) ? anchor.closest(".m-home-card") : null;
    var folder = (hostCard && hostCard.dataset && hostCard.dataset.folder) ? hostCard.dataset.folder : null;
    var same = moreEl && moreAnchor === anchor;
    closeMore();
    if (same) return;
    moreEl = document.createElement("div");
    moreEl.className = "m-more-pop";
    moreEl.innerHTML =
      // 不再写一行作品名：卡片上就有，多一行灰字既重复又难看
      '<button type="button" class="m-more-row2" id="mMoreRen">' + MOR_ICON.ren + '重命名</button>' +
      '<button type="button" class="m-more-row2" id="mMoreExp">' + MOR_ICON.exp + '导出这个作品</button>' +
      '<button type="button" class="m-more-row2" id="mMoreImp">' + MOR_ICON.imp + '导入文件</button>' +
      '<button type="button" class="m-more-row2" id="mMoreDup">' + MOR_ICON.dup + '复制一份</button>' +
      '<button type="button" class="m-more-row2" id="mMoreHist">' + MOR_ICON.hist + '版本历史</button>' +
      // 删除单独一色：这是唯一会让人丢东西的那一项
      '<button type="button" class="m-more-row2 danger" id="mMoreDel">' + MOR_ICON.del + '删除</button>';
    document.documentElement.appendChild(moreEl);
    moreAnchor = anchor || null;
    placeMore(anchor);
    moreOff = function (e) {
      if (!moreEl) return;
      if (moreEl.contains(e.target)) return;
      if (anchor && anchor.contains && anchor.contains(e.target)) return; // 交给 click 去 toggle
      closeMore();
    };
    document.addEventListener("pointerdown", moreOff, true);
    // 滚动、转屏、窗口一变，浮层就停在旧坐标了 —— 直接收起，比追着挪干净
    window.addEventListener("scroll", closeMore, { passive: true, once: true });
    window.addEventListener("resize", closeMore, { passive: true, once: true });

    moreEl.querySelector("#mMoreRen").addEventListener("click", function () {
      closeMore();
      var box = document.createElement("div");
      // 复用 P202 那套 p202-* 改名层：居中、四边不越屏、不自动 focus（focus 会立刻弹键盘）
      box.innerHTML =
        '<div class="p202-mask"></div>' +
        '<div class="p202-box"><h4>改个名字</h4>' +
          '<input class="p202-in" id="mRenIn" value="' + esc(name) + '" maxlength="40">' +
          '<div class="p202-row">' +
            '<button type="button" class="p202-cancel" id="mRenNo">取消</button>' +
            '<button type="button" class="p202-ok" id="mRenOk">改名</button>' +
          '</div>' +
        '</div>';
      document.documentElement.appendChild(box);
      var inp = box.querySelector("#mRenIn");
      box.querySelector(".p202-mask").addEventListener("click", function () { box.remove(); });
      box.querySelector("#mRenNo").addEventListener("click", function () { box.remove(); });
      function go() {
        var v = String(inp.value || "").trim();
        if (!v) { toast("名字不能空着"); return; }
        if (v === name) { box.remove(); return; }
        box.remove();
        if (!window.MYONLRenameProject) { toast("改名功能没加载"); return; }
        var err = window.MYONLRenameProject(name, v);
        if (err) { toast(err); return; }
        location.reload();   // 列表上的名字是 /api/home 拉的，不刷新还是旧的
      }
      box.querySelector("#mRenOk").addEventListener("click", go);
      inp.addEventListener("keydown", function (e) { if (e.key === "Enter") go(); });
      // 不自动 focus：手机上 focus 会立刻弹键盘，把弹窗下半截顶出屏（P202 的错）
    });

    moreEl.querySelector("#mMoreExp").addEventListener("click", function () {
      closeMore();
      if (window.MYONLExport && MYONLExport.exportOne) MYONLExport.exportOne(name);
      else toast("导出没加载，刷新一下页面");
    });
    moreEl.querySelector("#mMoreImp").addEventListener("click", function () {
      closeMore();
      if (window.MYONLExport && MYONLExport.import) MYONLExport.import();
      else toast("导入没加载，刷新一下页面");
    });
    moreEl.querySelector("#mMoreDup").addEventListener("click", function () {
      closeMore();
      if (window.MYONLExport && MYONLExport.dupOne) MYONLExport.dupOne(name);
      else toast("复制没加载，刷新一下页面");
    });
    moreEl.querySelector("#mMoreHist").addEventListener("click", function () {
      closeMore();
      // 历史版本本来就是按目录存的，手机上原来埋在导出页第三行，等于没有；搬进 ⋯ 里
      if (window.MYONLSnapshotsUI && folder) window.MYONLSnapshotsUI.open(folder);
      else toast("这个设备上没有历史版本模块");
    });
    moreEl.querySelector("#mMoreDel").addEventListener("click", function () {
      // 删完就 reload，来不及说"进垃圾箱了"，所以把归宿写进这句确认里；
      // 误触一下就要多点一次还原，问一句比事后道歉便宜。
      closeMore();  // 别让菜单留在确认框底下被压成灰片
      dlgConfirm({
        title: "删除「" + name + "」？",
        msg: "会先进垃圾箱，" + KEEP_DAYS + " 天内能还原。",
        ok: "删除", danger: true
      }).then(function (yes) {
        if (!yes) return;
        closeMore();
        del(name);
      });
    });
  }

  // ---- 垃圾箱：照相册「最近删除」——整页、左上返回箭头、标题居中、右上「选择」
  var binEl = null, binSel = {}, binSelOn = false;

  function binPick() {
    var out = [];
    for (var k in binSel) if (binSel[k]) out.push(k);
    return out;
  }

  function binLeft(delAt) {
    var days = KEEP_DAYS - Math.floor((Date.now() - (delAt || 0)) / DAY);
    if (days < 0) days = 0;
    return days + " 天";
  }

  function paintBin() {
    if (!binEl) return;
    var picked = binPick(), cells = binEl.querySelectorAll("[data-row]");
    var total = cells.length;
    cells.forEach(function (c) {
      c.classList.toggle("pick", binSelOn);
      c.classList.toggle("on", !!binSel[c.dataset.row]);
    });
    var l = binEl.querySelector("#mBinLeft");
    var t = binEl.querySelector("#mBinTitle");
    var r = binEl.querySelector("#mBinRight");
    var bar = binEl.querySelector("#mBinBar");
    // P217c：选择态左上那颗从「‹」变成「取消」两个字，44px 的箭头按钮装不下会折行。
    // 打个类让 CSS 把它按文字按钮排（见 ui-layout.css .m-bin-sel）。
    binEl.classList.toggle("m-bin-sel", binSelOn);
    if (binSelOn) {
      if (l) l.textContent = "取消";
      if (t) t.textContent = "已选 " + picked.length;
      if (r) { r.textContent = (total && picked.length >= total) ? "取消全选" : "全选"; r.disabled = !total; }
      if (bar) bar.hidden = false;
      var rs = binEl.querySelector("#mBinRestore"), pg = binEl.querySelector("#mBinPurge");
      if (rs) { rs.disabled = !picked.length; rs.textContent = picked.length ? ("还原（" + picked.length + "）") : "还原"; }
      if (pg) { pg.disabled = !picked.length; pg.textContent = picked.length ? ("彻底删除（" + picked.length + "）") : "彻底删除"; }
    } else {
      if (l) l.textContent = "‹";
      if (t) t.textContent = "已删除";
      if (r) { r.textContent = "选择"; r.disabled = !total; }
      if (bar) bar.hidden = true;
    }
  }

  function openBin(redraw) {
    if (binEl && !redraw) { binEl.remove(); binEl = null; return; }
    if (binEl) { binEl.remove(); binEl = null; }
    var rows = readTrash();
    if (!rows.length) { binSel = {}; binSelOn = false; }
    var grid = rows.length
      ? rows.map(function (r) {
          return '<div class="m-bin-cell" data-row="' + esc(r.name) + '">' +
            '<span class="m-bin-th">' + esc(String(r.name).slice(0, 1)) + '</span>' +
            '<span class="m-bin-nm">' + esc(r.name) + '</span>' +
            '<span class="m-bin-lt">' + binLeft(r.delAt) + '</span>' +
            '</div>';
        }).join("")
      : '<div class="m-bin-empty">这里还是空的。<br>删掉的作品会先来这里，' +
        KEEP_DAYS + ' 天内随时能还原。</div>';
    binEl = document.createElement("div");
    binEl.className = "m-bin-page";
    binEl.innerHTML =
      '<div class="m-bin-top">' +
        '<button type="button" class="m-back" id="mBinLeft" aria-label="返回">‹</button>' +
        '<span class="m-bin-title" id="mBinTitle">已删除</span>' +
        '<button type="button" class="m-bin-act" id="mBinRight">选择</button>' +
      '</div>' +
      '<div class="m-bin-note">已删除的作品仅保留 ' + KEEP_DAYS + ' 天，逾期永久删掉。</div>' +
      '<div class="m-bin-grid">' + grid + '</div>' +
      '<div class="m-bin-bar" id="mBinBar" hidden>' +
        '<button type="button" class="m-bin-b" id="mBinRestore" disabled>还原</button>' +
        '<button type="button" class="m-bin-b m-bin-bp" id="mBinPurge" disabled>彻底删除</button>' +
      '</div>';
    document.documentElement.appendChild(binEl);

    binEl.querySelector("#mBinLeft").addEventListener("click", function () {
      if (binSelOn) { binSelOn = false; binSel = {}; paintBin(); return; }
      binEl.remove(); binEl = null;
    });
    binEl.querySelector("#mBinRight").addEventListener("click", function () {
      if (!binSelOn) { binSelOn = true; paintBin(); return; }
      var all = binEl.querySelectorAll("[data-row]").length, on = binPick().length;
      binSel = {};
      if (on < all) binEl.querySelectorAll("[data-row]").forEach(function (c) { binSel[c.dataset.row] = 1; });
      paintBin();
    });
    binEl.querySelectorAll("[data-row]").forEach(function (c) {
      c.addEventListener("click", function () {
        // 普通态点一下：直接进选择并选上它，少按一次「选择」
        if (!binSelOn) binSelOn = true;
        var nm = c.dataset.row;
        if (binSel[nm]) delete binSel[nm]; else binSel[nm] = 1;
        paintBin();
      });
    });
    var rs = binEl.querySelector("#mBinRestore");
    if (rs) rs.addEventListener("click", function () { restoreMany(binPick()); });
    var pg = binEl.querySelector("#mBinPurge");
    if (pg) pg.addEventListener("click", function () {
      var picked = binPick();
      if (!picked.length) return;
      dlgConfirm({
        title: "彻底删除 " + picked.length + " 个？",
        msg: "删完就真的没了，没法还原。",
        ok: "彻底删除", danger: true
      }).then(function (yes) {
        if (!yes) return;
        purgeMany(picked);
      });
    });
    paintBin();
  }

  // ---- 素材库页：手机上的素材全在 IndexedDB，这里给它一张脸；
  // 教程也收进来（用户：教程不要单独出，放素材库里），于是这一页下面有四个 tab。
  var asEl = null, libTab = "image";
  // 笔记：素材页里第四个 tab。素材是图/音/视频，笔记是自己写的字——
  // 都算"做东西要用的料"，所以跟素材放一页，不进作品里。
  // 存 localStorage，一条一个对象；标题取正文第一行，跟笔记 App 一个习惯。
  var LIB_TABS = [["image", "图片"], ["audio", "音频"], ["video", "视频"], ["note", "笔记"]];
  var NOTES_KEY = "myonl:off:notes:v1";
  function readNotes() {
    try {
      var a = JSON.parse(localStorage.getItem(NOTES_KEY) || "[]");
      return Array.isArray(a) ? a : [];
    } catch (e) { return []; }
  }
  function writeNotes(a) {
    try { localStorage.setItem(NOTES_KEY, JSON.stringify(a)); }
    catch (e) { toast("本机存不下，笔记太长了"); }
  }
  function noteTitle(n) {
    var first = String((n && n.body) || "").split("\n")[0].trim();
    return first ? (first.length > 18 ? first.slice(0, 18) + "…" : first) : "空白笔记";
  }
  function noteAgo(t) {
    var s = Math.max(0, Math.floor((Date.now() - (t || 0)) / 1000));
    if (s < 60) return "刚刚";
    if (s < 3600) return Math.floor(s / 60) + " 分钟前";
    if (s < 86400) return Math.floor(s / 3600) + " 小时前";
    return Math.floor(s / 86400) + " 天前";
  }
  // 笔记编辑页：整页，顶上只有返回和「存」，正文占满——写的时候不需要看别的。
  // 给外部（将来的备份导出、以及自动化验收）留一个读写口，别让笔记只能靠点界面改
  window.__MYONLNotes = { list: readNotes, save: writeNotes };
  function openNoteEditor(idx, onDone) {
    var notes = readNotes();
    var item = idx >= 0 ? notes[idx] : { body: "", at: Date.now() };
    var ed = document.createElement("div");
    ed.className = "m-bin-page m-note-page";
    ed.innerHTML =
      '<div class="m-bin-top">' +
        '<button type="button" class="m-back" id="mNoteLeft" aria-label="返回">‹</button>' +
        '<span class="m-bin-title">笔记</span>' +
        '<button type="button" class="m-bin-act" id="mNoteDone">存</button>' +
      '</div>' +
      '<textarea class="m-note-ta" id="mNoteTa" placeholder="第一行当标题，后面随便写。"></textarea>';
    document.documentElement.appendChild(ed);
    var ta = ed.querySelector("#mNoteTa");
    ta.value = String(item.body || "");
    var saved = ta.value;
    function commit() {
      var body = ta.value;
      if (body === saved && idx >= 0) return;
      var arr = readNotes();
      if (idx >= 0) {
        if (!arr[idx]) return;
        arr[idx].body = body;
        arr[idx].at = Date.now();
        writeNotes(arr);
      } else {
        // 新建：先落盘再改 idx —— 顺序反了就会"看着存了、其实没存"
        arr.unshift({ body: body, at: Date.now() });
        writeNotes(arr);
        idx = 0;
      }
      saved = body;
    }
    ta.addEventListener("input", function () {
      clearTimeout(ta._t);
      ta._t = setTimeout(commit, 800);     // 边写边存，不给"忘了保存"留坑
    });
    function close() {
      commit();
      ed.remove();
      if (onDone) onDone();
    }
    ed.querySelector("#mNoteLeft").addEventListener("click", close);
    ed.querySelector("#mNoteDone").addEventListener("click", close);
    setTimeout(function () { ta.focus(); }, 200);
  }

  var tutOpen = false;
  function openAssets() {
    if (asEl) { asEl.remove(); asEl = null; return; }
    var A = window.MYONLAssets;
    if (!A) { toast("素材库没加载，刷新一下页面"); return; }
    asEl = document.createElement("div");
    asEl.className = "m-lib-page";
    document.documentElement.appendChild(asEl);

    function kindOf(n) { return (A.kindOf || function () { return "image"; })(n); }

    // 教程：跟首页那份同一套说法，只是不再单独弹一个抽屉
    function tutBody() {
      return '<div class="m-lib-tut">' +
        '<div class="m-tut-h">一行就是一屏</div>' +
        '<div class="m-tut-p">剧本里写的每一行，就是玩家看到的一屏。方括号里写谁在说，后面是说出来的话。</div>' +
        '<div class="m-tut-c">@[小满] 你终于来了。</div>' +
        '<div class="m-tut-h">旁白是画外音</div>' +
        '<div class="m-tut-p">不想让某个角色说话，名字就写「旁白」。</div>' +
        '<div class="m-tut-c">@[旁白] 雨还在下。</div>' +
        '<div class="m-tut-h">分叉只要两行</div>' +
        '<div class="m-tut-p">@choice: 下面一行一个选项，箭头后面是跳到哪一幕。</div>' +
        '<div class="m-tut-c">@choice:<br>&gt; 追上去 -&gt; 第一章<br>&gt; 转身走 -&gt; 回家</div>' +
        '<div class="m-tut-h">画面与声音</div>' +
        '<div class="m-tut-p">上面三个 tab 放图和音乐，名字对上就能插进剧本。</div>' +
        // P217：教程与示范案例绑定，能玩的那份只有「示范案例」一个。
        // 「新建项目」同步改成给空白（原来它也塞一份示范正文，等于每建一个都要先删干净）。
        '<div class="m-tut-h">想动手</div>' +
        '<div class="m-tut-p">首页那份「示范案例」就是能玩能改的成品，点开照着改；写自己的再点「新建项目」。</div>' +
        '<button type="button" class="m-tut-open" id="mLibTutDemo">打开示范案例</button>' +
        '</div>';
    }

    function paint() {
      var names = A.list ? A.list() : [];
      var cnt = {};
      names.forEach(function (n) { var k = kindOf(n); cnt[k] = (cnt[k] || 0) + 1; });
      var notes = readNotes();
      var tabs = LIB_TABS.map(function (t) {
        var num = t[0] === "note" ? notes.length : (cnt[t[0]] || 0);
        return '<button type="button" class="m-lib-tab' + (libTab === t[0] ? " on" : "") +
          '" data-tab="' + t[0] + '">' + t[1] + '<i>' + num + '</i></button>';
      }).join("");
      // 教程不占一列（用户：「教程不要单独开一列」）—— 它变成列表底下的一行速查，
      // 想看就点开，不看就一直在那儿收着。
      var arr = names.filter(function (n) { return kindOf(n) === libTab; });
      var one = { image: "图片", audio: "音频", video: "视频", note: "笔记" }[libTab];
      var note = '<div class="m-set-note">进作品 → 底部「素材」，把这些名字插进剧本就能用。' +
        '删掉的素材，已经插进剧本的引用会变成断链，体检会提醒。</div>';
      var body;
      if (libTab === "note") {
        // 笔记不跟素材混：它没有"名字插进剧本"这回事，列表就按最近写的在上面。
        body = notes.length
          ? '<div class="m-note-list">' + notes.map(function (n, i) {
              return '<div class="m-note-row" data-note="' + i + '">' +
                '<div class="m-note-b"><b>' + esc(noteTitle(n)) + '</b>' +
                  '<span>' + noteAgo(n.at) + ' · ' + ((String(n.body || "").length) || 0) + ' 字</span></div>' +
                '<button type="button" class="m-bin-x" data-note-del="' + i + '">删</button>' +
              '</div>';
            }).join("") + '</div>' +
            '<div class="m-set-note">笔记只存在这台设备上：卸载 App 或清浏览器数据就一起没了，重要的话另存一份。</div>'
          : '<div class="m-bin-empty">还没有笔记。<br>点右上「新写」，想到什么写什么，第一行自动当标题。</div>';
      } else if (!arr.length) {
        body = '<div class="m-bin-empty">还没有' + one + '。<br>点右上「导入」，图片、音乐、视频都收在这里。</div>';
      } else if (libTab === "image") {
        // P209：图片按相册那样两列铺 —— 一行一条太扁，图片本来就该先看见画面
        body = '<div class="m-lib-grid">' + arr.map(function (n) {
          return '<div class="m-lib-cell">' +
            '<div class="m-lib-th"><img alt="" data-th="' + esc(n) + '">' +
              '<button type="button" class="m-lib-x" data-un="' + esc(n) + '" aria-label="删">×</button>' +
            '</div>' +
            '<span class="m-lib-nm">' + esc(n) + '</span>' +
          '</div>';
        }).join("") + '</div>' + note;
      } else {
        body = arr.map(function (n) {
          return '<div class="m-lib-row">' +
            '<span class="m-lib-ic">' + (libTab === "audio" ? "♪" : "▶") + '</span>' +
            '<span class="m-lib-n">' + esc(n) + '</span>' +
            '<button type="button" class="m-bin-x" data-un="' + esc(n) + '">删</button>' +
            '</div>';
        }).join("") + note;
      }
      asEl.innerHTML =
        '<div class="m-bin-top">' +
          '<button type="button" class="m-back" id="mLibLeft" aria-label="返回">‹</button>' +
          '<span class="m-bin-title" id="mLibTitle">素材</span>' +
          '<button type="button" class="m-bin-act" id="mLibAdd">' +
            (libTab === "note" ? "新写" : "导入") + '</button>' +
        '</div>' +
        '<div class="m-lib-tabs" id="mLibTabs">' + tabs + '</div>' +
        '<div class="m-lib-body">' + body +
          '<div class="m-lib-tutbox">' +
            '<button type="button" class="m-lib-tutlink" id="mLibTut">写法速查 ' +
              (tutOpen ? "· 收起" : "· 展开") + '</button>' +
            '<div class="m-lib-tut" id="mLibTutBody"' + (tutOpen ? "" : " hidden") + '>' +
              tutBody() + '</div>' +
          '</div>' +
        '</div>';
      asEl.querySelector("#mLibLeft").addEventListener("click", function () {
        asEl.remove(); asEl = null;
      });
      asEl.querySelector("#mLibTabs").addEventListener("click", function (e) {
        var b = e.target.closest ? e.target.closest("[data-tab]") : null;
        if (!b || b.dataset.tab === libTab) return;
        libTab = b.dataset.tab;
        paint();
      });
      asEl.querySelector("#mLibTut").addEventListener("click", function () {
        tutOpen = !tutOpen;
        var tb = asEl.querySelector("#mLibTutBody"), lb = asEl.querySelector("#mLibTut");
        if (tb) tb.hidden = !tutOpen;
        if (lb) lb.textContent = "写法速查 " + (tutOpen ? "· 收起" : "· 展开");
      });
      // P217：速查里那颗按钮直接开首页那份示范案例，不再让人自己回首页找。
      var td = asEl.querySelector("#mLibTutDemo");
      if (td) td.addEventListener("click", function () {
        if (window.MYONLOpenDemo) { asEl.remove(); asEl = null; window.MYONLOpenDemo(); }
        else toast("回「作品」页点「示范案例」");
      });
      asEl.querySelector("#mLibAdd").addEventListener("click", function () {
        if (libTab === "note") { openNoteEditor(-1, paint); return; }
        // 安卓壳从 v1.2.52 起补了 onShowFileChooser，会打 __MYONL_CAN_PICK；老壳没有这个标记。
        // 老壳点下去等于"没反应"，那就别装能选，直接告诉人怎么走。
        if (/Android/i.test(navigator.userAgent || "") && !window.__MYONL_CAN_PICK) {
          if (window.MYONLDialog) {
            window.MYONLDialog.info({
              title: "这个安装包还选不了文件",
              msg: "装的还是旧包，壳里少了「打开系统选择器」那一步。换成新包就能选；现在可以先走「导出」页的「粘贴导入」。"
            });
          } else {
            toast("旧包选不了文件，先用粘贴导入");
          }
          return;
        }
        var inp = document.createElement("input");
        inp.type = "file"; inp.accept = "image/*,audio/*,video/*"; inp.multiple = true;
        inp.style.display = "none";
        document.body.appendChild(inp);
        inp.addEventListener("change", function () {
          var fl = Array.prototype.slice.call(inp.files || []);
          inp.remove();
          if (!fl.length) return;
          toast("正在收……");
          Promise.resolve(A.add(fl)).then(function (r) {
            toast("加进去 " + ((r && r.length) || 0) + " 个");
            paint();
          }).catch(function (e) { toast("加不进去：" + (e.message || e)); });
        });
        inp.click();
      });
      // 笔记：点一行进去写，点「删」问一次再删
      asEl.querySelectorAll("[data-note]").forEach(function (row) {
        row.addEventListener("click", function (e) {
          if (e.target.closest && e.target.closest("[data-note-del]")) return;
          openNoteEditor(parseInt(row.dataset.note, 10), paint);
        });
      });
      asEl.querySelectorAll("[data-note-del]").forEach(function (b) {
        b.addEventListener("click", function (e) {
          e.stopPropagation();
          var i = parseInt(b.dataset.noteDel, 10);
          var notes = readNotes();
          if (!notes[i]) return;
          dlgConfirm({
            title: "删掉这条笔记？",
            msg: noteTitle(notes[i]) + " · 删了就找不回来。",
            ok: "删除", danger: true
          }).then(function (yes) {
            if (!yes) return;
            var n2 = readNotes();
            n2.splice(i, 1);
            writeNotes(n2);
            paint();
          });
        });
      });
      // 缩略图异步取：先摆好方块，谁先到谁先亮，别让整页等图片
      asEl.querySelectorAll("[data-th]").forEach(function (img) {
        var nm = img.dataset.th;
        Promise.resolve(A.thumbOf(nm)).then(function (u) {
          if (u) img.src = u;
        }).catch(function () {});
      });
      asEl.querySelectorAll("[data-un]").forEach(function (b) {        b.addEventListener("click", function () {
          var n = b.dataset.un;
          dlgConfirm({
            title: "删掉素材「" + n + "」？",
            msg: "已经插进剧本的地方会变成断链。",
            ok: "删除", danger: true
          }).then(function (yes) {
            if (!yes) return;
            Promise.resolve(A.remove(n)).then(function () {
              toast("已删掉");
              paint();
            }).catch(function (e) { toast("删不掉：" + (e.message || e)); });
          });
        });
      });
    }
    paint();
  }

  window.MYONLTrash = {
    nextName: nextName, more: more, del: del, delMany: delMany, openBin: openBin,
    list: readTrash, restore: restore, restoreMany: restoreMany,
    purge: purge, purgeMany: purgeMany
  };
  window.MYONLAssetLib = { open: openAssets };
})();
