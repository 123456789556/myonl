/* ===================================================================
   P65：手机端第一层「工作台」
   打开就是工程卡片（最近用的排前面），点一张才进编辑器。
   桌面端（>860px）不接管，直接进编辑器 —— 电脑上三列 IDE 是合适的。
   =================================================================== */
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };

  var EDIT_KEY = "myonl:editing";
  var isMobile = function () { return window.matchMedia && window.matchMedia("(max-width:860px), (max-height:520px)").matches; };
  if (!isMobile()) return;

  // 编辑器里的「‹ 作品」按钮调它：清掉「已在编辑」标记后重载回工作台
  window.__myonlShowHome = function () {
    try { sessionStorage.removeItem(EDIT_KEY); } catch (e) {}
    location.reload();
  };
  try { if (sessionStorage.getItem(EDIT_KEY) === "1") return; } catch (e) {}

  // 编辑器自己的层先别渲染，等用户从工作台点进去
  function hideEditor(on) {
    var main = document.querySelector(".main");
    var menu = document.querySelector(".menubar");
    var st = document.querySelector(".statusbar");
    [main, menu, st].forEach(function (el) {
      if (!el) return;
      el.style.visibility = on ? "hidden" : "";
    });
  }
  hideEditor(true);

  var layer = document.createElement("div");
  layer.className = "m-home";
  // P116：首页自成一屏，不掺编辑器那套 tab —— 那五个 tab 是「作品内部」的事，
  // 摆在工作台底下等于让人以为首页还有五个没展开的页。
  document.body.classList.add("m-home-open");
  // 书架还空着的时候，说明卡（"都在你手上…"）和三步上手说的是同一件事：先建作品。
  // 第一次打开的人面前不该同时摆七块可读的东西 —— 说明卡收起来，留三步上手当唯一指引。
  try {
    var lib0 = JSON.parse(localStorage.getItem("myonl:off:lib:v1") || "{}");
    if (!((lib0 && lib0.projects) || []).length) document.body.classList.add("m-home-empty");
  } catch (e) { }
  layer.innerHTML =
    '<div class="m-home-head">' +
      '<div><div class="m-home-title">我的作品</div>' +
      '<div class="m-home-sub" id="mHomeSub">本地保存 · 不上云</div></div>' +
      '<button type="button" class="m-home-set" id="mHomeSet">设置</button>' +
    '</div>' +
    '<div class="m-home-list" id="mHomeList"></div>' +
    '<div class="m-home-side">' +
      '<div class="m-home-sec">开始新的</div>' +
      '<div class="m-quick">' +
        '<button type="button" class="m-quick-item" id="mHomeNew">' +
          '<b>＋</b><span>新建作品</span></button>' +
        '<button type="button" class="m-quick-item" id="mHomeImport">' +
          '<b>&#8615;</b><span>导入作品</span></button>' +
      '</div>' +
      '<div class="m-home-note">' +
        '<div class="m-home-note-t">都在你手上</div>' +
        '<div class="m-home-note-b">作品、素材、存档只存这台设备，不上传。' +
        '想给别人看，进作品后点底部「导出」里的「做成成品」——一个 .html，发过去就能打开。</div>' +
      '</div>' +
      '<div class="m-home-steps">' +
        '<div class="m-home-sec">三步上手</div>' +
        '<button type="button" class="m-step" data-step="script">' +
          '<span class="m-step-n">1</span>' +
          '<span class="m-step-t">写第一句台词</span>' +
          '<span class="m-step-s">场景页里直接改，不用记语法</span></button>' +
        '<button type="button" class="m-step" data-step="asset">' +
          '<span class="m-step-n">2</span>' +
          '<span class="m-step-t">挑一张背景</span>' +
          '<span class="m-step-s">没有图也能先跑起来</span></button>' +
        '<button type="button" class="m-step" data-step="export">' +
          '<span class="m-step-n">3</span>' +
          '<span class="m-step-t">做成成品发给朋友</span>' +
          '<span class="m-step-s">一个 .html，对方手机直接打开</span></button>' +
      '</div>' +
    '</div>';
  document.body.appendChild(layer);

  function ago(ts) {
    var d = (Date.now() / 1000) - ts;
    if (d < 3600) return Math.max(1, Math.round(d / 60)) + " 分钟前";
    if (d < 86400) return Math.round(d / 3600) + " 小时前";
    if (d < 86400 * 30) return Math.round(d / 86400) + " 天前";
    return new Date(ts * 1000).toLocaleDateString();
  }

  function card(p, idx) {
    var folder = p.folder.replace(/"/g, "&quot;");
    var name = p.name.replace(/</g, "&lt;");
    if (idx === 0) {
      // 第一张做成整宽大卡（借 Kazumi 的「今日开播」）：封面铺满 + 底部渐深 + 直接继续编辑
      return '<button type="button" class="m-home-hero" data-folder="' + folder + '">' +
        '<span class="m-hero-cover" data-folder="' + folder + '"></span>' +
        '<span class="m-hero-veil"></span>' +
        '<span class="m-hero-text">' +
          '<span class="m-hero-tag">最近编辑</span>' +
          '<span class="m-hero-name">' + name + '</span>' +
          '<span class="m-hero-meta">' + ago(p.mtime) + '改过 · ' + p.ins + ' 条指令</span>' +
        '</span>' +
        '<span class="m-hero-go">继续编辑</span></button>';
    }
    return '<button type="button" class="m-home-card" data-folder="' + folder + '">' +
      '<span class="m-card-thumb" data-folder="' + folder + '"></span>' +
      '<span class="m-card-body">' +
        '<span class="m-card-name">' + name + '</span>' +
        '<span class="m-card-chips">' +
          '<span class="m-chip">' + p.ins + ' 条指令</span>' +
          '<span class="m-chip">' + p.assets + ' 个素材</span>' +
          '<span class="m-chip m-chip-dim">' + ago(p.mtime) + '</span>' +
        '</span>' +
      '</span>' +
      '<span class="m-card-go">›</span></button>';
  }

  function render(projects) {
    var list = $("mHomeList");
    if (!list) return;
    var sub = $("mHomeSub");
    if (sub) sub.textContent = projects.length + " 个作品 · 本地保存 · 不上云";
    if (!projects.length) {
      list.innerHTML = '<div class="m-home-empty">还没有作品。点下面「新建作品」，' +
        '它自带一句示例台词，你能立刻看到画面。</div>';
    } else {
      list.innerHTML = projects.map(card).join("");
    }
    // 缩略图单独请求：拿不到就留个空底，不阻塞列表
    list.querySelectorAll(".m-card-thumb[data-folder], .m-hero-cover[data-folder]").forEach(function (th) {
      var f = th.dataset.folder;
      var img = new Image();
      img.onload = function () {
        th.style.backgroundImage = 'url("/api/thumb?folder=' + encodeURIComponent(f) + '")';
        th.classList.add("has");
        // 有真封面才让大卡长起来（空工程铺满一整屏渐变像没加载完）
        var hero = th.closest ? th.closest(".m-home-hero") : null;
        if (hero) hero.classList.add("cover-on");
      };
      img.src = "/api/thumb?folder=" + encodeURIComponent(f);
    });
    list.querySelectorAll(".m-home-card[data-folder], .m-home-hero[data-folder]").forEach(function (b) {
      b.addEventListener("click", function () { openProject(b.dataset.folder, b); });
    });
  }

  function newProject() {
    // 复用编辑器自己的「新建游戏」弹窗：先进编辑器，再点它
    enterEditor();
    setTimeout(function () {
      var menuFile = document.querySelector('.menu-item[data-menu="file"]');
      if (menuFile) menuFile.click();
      var ng = $("menuNewGame") || $("btnNewGame");
      if (ng) ng.click();
    }, 120);
  }

  // 导入：手机上没有「打开文件对话框」以外的路子，所以走 <input type=file>。
  // 只认离线作品库那份 JSON（和导出的同一格式），别的一律明确拒绝，不猜。
  function importProject() {
    var inp = document.createElement("input");
    inp.type = "file";
    inp.accept = ".json,application/json";
    inp.style.display = "none";
    document.body.appendChild(inp);
    inp.addEventListener("change", function () {
      var f = inp.files && inp.files[0];
      if (!f) { inp.remove(); return; }
      var rd = new FileReader();
      rd.onload = function () {
        var ok = false;
        try {
          if (window.__myonlImportLib) ok = window.__myonlImportLib(String(rd.result || ""));
        } catch (e) { ok = false; }
        if (ok) setTimeout(function () { location.reload(); }, 400);
        else toast("这份文件读不出来——只认「导出」里导出的作品库 JSON。");
        inp.remove();
      };
      rd.onerror = function () { toast("文件读不出来"); inp.remove(); };
      rd.readAsText(f);
    });
    inp.click();
  }

  function toast(msg) {
    var t = document.createElement("div");
    t.className = "m-home-toast";
    t.textContent = msg;
    document.body.appendChild(t);
    setTimeout(function () { t.remove(); }, 2400);
  }

  function openProject(folder, btn) {
    if (btn) { btn.disabled = true; btn.classList.add("busy"); }
    fetch("/api/project", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ folder: folder })
    }).then(function (r) { return r.json(); }).then(function (res) {
      if (!res.ok) throw new Error(res.message || "打不开这个工程");
      enterEditor();
      location.reload();     // 工程根变了：文件树/素材/预览全部要重来，reload 最省事也最可靠
    }).catch(function (e) {
      if (btn) { btn.disabled = false; btn.classList.remove("busy"); }
      var t = document.createElement("div");
      t.className = "m-home-toast";
      t.textContent = e.message || "打不开这个工程";
      layer.appendChild(t);
      setTimeout(function () { t.remove(); }, 2200);
    });
  }

  function enterEditor() {
    try { sessionStorage.setItem(EDIT_KEY, "1"); } catch (e) {}
    hideEditor(false);
    layer.style.display = "none";
    document.body.classList.remove("m-home-open");   // 回到作品内部，底部五个 tab 归位
  }

  // ---- 设置：主题 / 游戏方向 / 返回作品列表。做成一页，别学桌面端散在五个地方 ----
  var sheet = null;
  var orient = "any";
  function openSettings() {
    if (sheet) { sheet.remove(); sheet = null; return; }
    var theme = "dark";
    try { theme = localStorage.getItem("gal_editor_theme") === "light" ? "light" : "dark"; } catch (e) {}
    sheet = document.createElement("div");
    // 必须带 on：.m-sheet 默认是 translateY(100%) 藏在视口下方的抽屉，只有 .on 才归位。
    // 上一版少了它，于是「设置」点开时抽屉其实一直在屏幕外面 —— 看着就像没反应。
    sheet.className = "m-sheet m-set-sheet on";
    sheet.innerHTML =
      '<div class="m-sheet-mask"></div>' +
      '<div class="m-sheet-body">' +
        '<div class="m-sheet-grab"></div>' +
        '<div class="m-sheet-title">设置' +
          '<button type="button" class="m-set-done" id="mSetDone">完成</button></div>' +
        '<div class="m-set-row"><span>界面</span>' +
          '<span class="m-seg" id="mSetTheme">' +
            '<button type="button" data-v="dark" class="' + (theme === "dark" ? "on" : "") + '">深色</button>' +
            '<button type="button" data-v="light" class="' + (theme === "light" ? "on" : "") + '">浅色</button>' +
          '</span></div>' +
        '<div class="m-set-row"><span>游戏画面</span>' +
          '<span class="m-seg" id="mSetOrient">' +
            '<button type="button" data-v="any" class="' + (orient === "any" ? "on" : "") + '">跟随</button>' +
            '<button type="button" data-v="portrait" class="' + (orient === "portrait" ? "on" : "") + '">竖屏</button>' +
            '<button type="button" data-v="landscape" class="' + (orient === "landscape" ? "on" : "") + '">横屏</button>' +
          '</span></div>' +
        '<div class="m-set-note">拿不准就选「跟随」—— 横过来竖着都能玩，导出时不用再选。</div>' +
      '</div>';
    // 抽屉挂 <html> 而不是 <body>：body 上挂了编辑器各种档位类，fixed 定位在里面被算成流的位置
  // （实测顶边跑到 1007，正好是内容底部）。挂 html 之后 fixed 的包含块就是视口本身。
  document.documentElement.appendChild(sheet);

    sheet.querySelector(".m-sheet-mask").addEventListener("click", function () {
      sheet.remove(); sheet = null;
    });

    var seg = sheet.querySelector("#mSetTheme");
    seg.addEventListener("click", function (e) {
      var b = e.target.closest ? e.target.closest("button[data-v]") : null;
      if (!b) return;
      var v = b.dataset.v;
      try { localStorage.setItem("gal_editor_theme", v); } catch (err) {}
      document.documentElement.setAttribute("data-theme", v);
      seg.querySelectorAll("button").forEach(function (x) { x.classList.toggle("on", x === b); });
    });

    // 「返回」那一行删了：抽屉点遮罩本来就能关，多一行「作品列表 / 返回」反而像在问"要回哪去"。
    // 现在只有一个入口——标题栏的「完成」，点它关抽屉，回哪儿去不用想。
    var dn = sheet.querySelector("#mSetDone");
    if (dn) dn.addEventListener("click", function () {
      if (sheet) { sheet.remove(); sheet = null; }
    });

    var ob = sheet.querySelector("#mSetOrient");
    if (ob) ob.addEventListener("click", function (e) {
      var b = e.target.closest ? e.target.closest("button[data-v]") : null;
      if (!b) return;
      var v = b.dataset.v;
      fetch("/api/orientation", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ orientation: v })
      }).then(function (r) { return r.json(); }).then(function (res) {
        if (!res.ok) throw new Error(res.message || "存不下来");
        orient = res.orientation;
        ob.querySelectorAll("button").forEach(function (x) {
          x.classList.toggle("on", x.dataset.v === orient);
        });
      }).catch(function (err) {
        var t = document.createElement("div");
        t.className = "m-home-toast";
        t.textContent = err.message || "存不下来";
        document.body.appendChild(t);
        setTimeout(function () { t.remove(); }, 2000);
      });
    });
  }

  fetch("/api/home").then(function (r) { return r.json(); }).then(function (res) {
    if (!res.ok) throw new Error("读不到作品列表");
    orient = res.orientation || "any";
    render(res.projects || []);
  }).catch(function (e) {
    var list = $("mHomeList");
    if (list) list.innerHTML = '<div class="m-home-err">' + (e.message || "读不到作品列表") + '</div>' +
      '<button type="button" class="m-home-card" id="mHomeSkip">还是直接进编辑器</button>';
    var sk = $("mHomeSkip");
    if (sk) sk.addEventListener("click", enterEditor);
  });

  // 点「三步上手」直接落到那一步：省掉「先找菜单再找图标」这一步，
  // 这是手机端最容易劝退的地方（不知道从哪下手，就关掉了）。
  function goStep(step) {
    var label = step === "asset" ? "素材" : (step === "export" ? "导出" : "剧本");
    enterEditor();
    setTimeout(function () {
      var tabs = document.querySelectorAll(".m-tab");
      for (var i = 0; i < tabs.length; i++) {
        if ((tabs[i].textContent || "").trim() === label) { tabs[i].click(); return; }
      }
    }, 380);
  }

  // 设置只剩页头右上角一个入口（三格里的那个删了，同一功能摆两处会让人以为是两件事）
  var sb = $("mHomeSet");
  if (sb) sb.addEventListener("click", openSettings);
  var nb = $("mHomeNew");
  if (nb) nb.addEventListener("click", newProject);
  var ib = $("mHomeImport");
  if (ib) ib.addEventListener("click", importProject);
  Array.prototype.forEach.call(layer.querySelectorAll(".m-step"), function (b) {
    b.addEventListener("click", function () { goStep(b.dataset.step); });
  });
})();
