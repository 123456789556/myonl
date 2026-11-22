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
    var b = moreEl.querySelector("#mMoreBin");
    if (b) b.addEventListener("click", function () { closeMore(); openBin(); });
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
  var LIB_TABS = [["image", "图片"], ["audio", "音频"], ["video", "视频"]];
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
        '<div class="m-tut-p">@choice 下面一行一个选项，箭头后面是跳到哪一幕。</div>' +
        '<div class="m-tut-c">&gt; 追上去 -&gt; 第一章<br>&gt; 转身走 -&gt; 回家</div>' +
        '<div class="m-tut-h">画面与声音</div>' +
        '<div class="m-tut-p">上面三个 tab 放图和音乐，名字对上就能插进剧本。</div>' +
        '<div class="m-tut-h">想动手</div>' +
        '<div class="m-tut-p">回「作品」页点那张虚线「新建项目」，它会给你一份能玩的短作品。</div>' +
        '</div>';
    }

    function paint() {
      var names = A.list ? A.list() : [];
      var cnt = {};
      names.forEach(function (n) { var k = kindOf(n); cnt[k] = (cnt[k] || 0) + 1; });
      var tabs = LIB_TABS.map(function (t) {
        return '<button type="button" class="m-lib-tab' + (libTab === t[0] ? " on" : "") +
          '" data-tab="' + t[0] + '">' + t[1] + '<i>' + (cnt[t[0]] || 0) + '</i></button>';
      }).join("");
      // 教程不占一列（用户：「教程不要单独开一列」）—— 它变成列表底下的一行速查，
      // 想看就点开，不看就一直在那儿收着。
      var arr = names.filter(function (n) { return kindOf(n) === libTab; });
      var one = { image: "图片", audio: "音频", video: "视频" }[libTab];
      var note = '<div class="m-set-note">进作品 → 底部「素材」，把这些名字插进剧本就能用。' +
        '删掉的素材，已经插进剧本的引用会变成断链，体检会提醒。</div>';
      var body;
      if (!arr.length) {
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
          '<button type="button" class="m-bin-act" id="mLibAdd">导入</button>' +
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
      asEl.querySelector("#mLibAdd").addEventListener("click", function () {
        // 安卓 WebView 里 <input type=file> 弹不出系统选择器（实测），点了会像没反应。
        // 与其让人怀疑按钮坏了，不如明说这条路还没通，并指出真能走的那条。
        if (/Android/i.test(navigator.userAgent || "") && !window.__myonlNativeImport) {
          if (window.MYONLDialog) {
            window.MYONLDialog.info({
              title: "这台手机导不了素材",
              msg: "安卓里系统选文件的那个窗弹不出来，这是 WebView 的限制。\n要导入就走「导出」页的「粘贴导入」：把 .json / .gal 整段贴进去，作品和素材一起回来。"
            });
          } else {
            toast("安卓上还弹不出系统选择器，真导入要等原生那层做完");
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
