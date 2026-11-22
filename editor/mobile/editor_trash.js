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

  function del(name) {
    var api = libApi();
    if (!api) { toast("这台设备没有离线内核"); return; }
    var lib = api.read();
    var at = -1;
    for (var i = 0; i < lib.projects.length; i++) {
      if (lib.projects[i].name === name) { at = i; break; }
    }
    if (at < 0) { toast("没有这个作品"); return; }
    var p = lib.projects.splice(at, 1)[0];
    var rows = readTrash();
    rows.push({
      name: p.name, text: p.text, ctime: p.ctime, mtime: p.mtime, delAt: Date.now()
    });
    writeTrash(rows);
    if (lib.current === p.name) lib.current = lib.projects[0] ? lib.projects[0].name : "";
    api.write(lib);
    // 草稿跟着走，否则同名新建会把旧草稿接上去
    try {
      if (window.MYONLDraft && window.MYONLDraft.drop) window.MYONLDraft.drop(p.name);
    } catch (e) {}
    location.reload();
  }

  function restore(name) {
    var api = libApi();
    if (!api) return;
    var rows = readTrash(), at = -1;
    for (var i = 0; i < rows.length; i++) if (rows[i].name === name) { at = i; break; }
    if (at < 0) { toast("垃圾箱里没有它"); return; }
    var lib = api.read();
    if (lib.projects.some(function (p) { return p.name === name; })) {
      toast("已经有同名作品，先改个名再还原");
      return;
    }
    var r = rows.splice(at, 1)[0];
    lib.projects.push({ name: r.name, text: r.text, ctime: r.ctime, mtime: r.mtime });
    api.write(lib);
    writeTrash(rows);
    toast("已还原「" + r.name + "」");
    location.reload();
  }

  function purge(name) {
    var rows = readTrash().filter(function (r) { return r.name !== name; });
    writeTrash(rows);
    toast("已彻底删除");
    if (binEl) openBin(true);
  }

  // ---- 「⋯」更多菜单：底部三行，够大够厚，不弹键盘
  var moreEl = null;
  function closeMore() { if (moreEl) { moreEl.remove(); moreEl = null; } }
  function more(name, hasBin) {
    closeMore();
    moreEl = document.createElement("div");
    moreEl.className = "m-sheet m-more-sheet on";
    moreEl.innerHTML =
      '<div class="m-sheet-mask"></div>' +
      '<div class="m-sheet-body m-more-body">' +
        '<div class="m-sheet-grab"></div>' +
        '<div class="m-more-name">' + esc(name) + '</div>' +
        '<button type="button" class="m-more-row" id="mMoreRen">改名</button>' +
        // 删除单独一色：这是唯一一个会让人丢东西的按钮，不能跟改名长得一样
        '<button type="button" class="m-more-row m-more-danger" id="mMoreDel">删除</button>' +
        (hasBin ? '<button type="button" class="m-more-row" id="mMoreBin">垃圾箱</button>' : '') +
        '<button type="button" class="m-more-row m-more-plain" id="mMoreCancel">取消</button>' +
      '</div>';
    document.documentElement.appendChild(moreEl);
    moreEl.querySelector(".m-sheet-mask").addEventListener("click", closeMore);
    moreEl.querySelector("#mMoreCancel").addEventListener("click", closeMore);
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
    moreEl.querySelector("#mMoreDel").addEventListener("click", function () {
      // 删完就 reload，来不及说"进垃圾箱了"，所以把归宿写进这句确认里；
      // 误触一下就要多点一次还原，问一句比事后道歉便宜。
      if (!confirm("把「" + name + "」删掉？会先进垃圾箱，" + KEEP_DAYS + " 天内能还原。")) return;
      closeMore();
      del(name);
    });
    var b = moreEl.querySelector("#mMoreBin");
    if (b) b.addEventListener("click", function () { closeMore(); openBin(); });
  }

  // ---- 垃圾箱页
  var binEl = null;
  function openBin(redraw) {
    if (binEl && !redraw) { binEl.remove(); binEl = null; return; }
    if (binEl) { binEl.remove(); binEl = null; }
    var rows = readTrash();
    var body = rows.length
      ? rows.map(function (r) {
          return '<div class="m-bin-row">' +
            '<span class="m-bin-t">' + esc(r.name) + '</span>' +
            '<button type="button" class="m-bin-a" data-back="' + esc(r.name) + '">还原</button>' +
            '<button type="button" class="m-bin-x" data-drop="' + esc(r.name) + '">彻底删</button>' +
            '</div>';
        }).join("")
      : '<div class="m-bin-empty">垃圾箱是空的</div>';
    binEl = document.createElement("div");
    binEl.className = "m-sheet m-set-sheet on";
    binEl.innerHTML =
      '<div class="m-sheet-mask"></div>' +
      '<div class="m-sheet-body">' +
        '<div class="m-sheet-grab"></div>' +
        '<div class="m-sheet-title">垃圾箱' +
          '<button type="button" class="m-set-done" id="mBinDone">完成</button></div>' +
        '<div class="m-set-note">删掉的作品在这里留 ' + KEEP_DAYS + ' 天，随时能还原；到期自动清掉。</div>' +
        body +
      '</div>';
    document.documentElement.appendChild(binEl);
    binEl.querySelector(".m-sheet-mask").addEventListener("click", function () { binEl.remove(); binEl = null; });
    binEl.querySelector("#mBinDone").addEventListener("click", function () { binEl.remove(); binEl = null; });
    binEl.querySelectorAll("[data-back]").forEach(function (b) {
      b.addEventListener("click", function () { restore(b.dataset.back); });
    });
    binEl.querySelectorAll("[data-drop]").forEach(function (b) {
      b.addEventListener("click", function () { purge(b.dataset.drop); });
    });
  }

  // ---- 素材库页：手机上的素材本来就全在 IndexedDB，这里只是给它一张脸
  var asEl = null;
  function openAssets() {
    if (asEl) { asEl.remove(); asEl = null; return; }
    var A = window.MYONLAssets;
    if (!A) { toast("素材库没加载，刷新一下页面"); return; }
    asEl = document.createElement("div");
    asEl.className = "m-sheet m-set-sheet on";
    document.documentElement.appendChild(asEl);

    // 每次删完 / 加完只重画内容，不重建整层 —— 重建会把刚点的那一下连同遮罩一起拆掉
    function paint() {
      var names = A.list ? A.list() : [];
      var kindOf = A.kindOf || function () { return "image"; };
      function rowsOf(k, label) {
        var arr = names.filter(function (n) { return kindOf(n) === k; });
        if (!arr.length) return "";
        return '<div class="m-lib-sec">' + label + '<i>' + arr.length + '</i></div>' +
          arr.map(function (n) {
            return '<div class="m-lib-row">' +
              '<span class="m-lib-n">' + esc(n) + '</span>' +
              '<button type="button" class="m-bin-x" data-un="' + esc(n) + '">删</button>' +
              '</div>';
          }).join("");
      }
      asEl.innerHTML =
        '<div class="m-sheet-mask"></div>' +
        '<div class="m-sheet-body">' +
          '<div class="m-sheet-grab"></div>' +
          '<div class="m-sheet-title">素材库' +
            '<button type="button" class="m-set-done" id="mLibDone">完成</button></div>' +
          '<button type="button" class="m-tut-start" id="mLibAdd">' +
            '＋ 导入素材<span>图片、音乐、视频都收在这里</span></button>' +
          (names.length
            ? rowsOf("image", "图片") + rowsOf("audio", "音频") + rowsOf("video", "视频") +
              '<div class="m-set-note">进作品 → 底部「素材」，把这些名字插进剧本就能用。' +
              '删掉的素材，已经插进剧本的引用会变成断链，体检会提醒。</div>'
            : '<div class="m-bin-empty">还没有素材</div>') +
        '</div>';
      asEl.querySelector(".m-sheet-mask").addEventListener("click", function () {
        asEl.remove(); asEl = null;
      });
      asEl.querySelector("#mLibDone").addEventListener("click", function () {
        asEl.remove(); asEl = null;
      });
      asEl.querySelector("#mLibAdd").addEventListener("click", function () {
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
      asEl.querySelectorAll("[data-un]").forEach(function (b) {
        b.addEventListener("click", function () {
          var n = b.dataset.un;
          if (!confirm("删掉素材「" + n + "」？已插进剧本的引用会变成断链。")) return;
          Promise.resolve(A.remove(n)).then(function () {
            toast("已删掉");
            paint();
          }).catch(function (e) { toast("删不掉：" + (e.message || e)); });
        });
      });
    }
    paint();
  }

  window.MYONLTrash = {
    nextName: nextName, more: more, del: del, openBin: openBin,
    list: readTrash, restore: restore, purge: purge
  };
  window.MYONLAssetLib = { open: openAssets };
})();
