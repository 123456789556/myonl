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
  layer.innerHTML =
    '<div class="m-home-head">' +
      '<div><div class="m-home-title">我的作品</div>' +
      '<div class="m-home-sub" id="mHomeSub">本地保存 · 不上云</div></div>' +
      '<button type="button" class="m-home-gear" id="mHomeSet" title="设置">' +
        '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" ' +
        'stroke-width="1.7" stroke-linecap="round" aria-hidden="true">' +
        '<circle cx="12" cy="12" r="3.2"/>' +
        '<path d="M12 3v2.2M12 18.8V21M21 12h-2.2M5.2 12H3M18.4 5.6l-1.6 1.6M7.2 16.8l-1.6 1.6' +
        'M18.4 18.4l-1.6-1.6M7.2 7.2L5.6 5.6"/></svg></button>' +
    '</div>' +
    '<div class="m-home-list" id="mHomeList"></div>' +
    '<div class="m-home-foot">本地作品 · 不上传云端</div>';
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
    var cards = projects.map(card).join("");    list.innerHTML = cards +
      '<button type="button" class="m-home-card m-home-new" id="mHomeNew">' +
        '<span class="m-card-thumb m-card-thumb-new">＋</span>' +
        '<span class="m-card-body">' +
          '<span class="m-card-name">新建作品</span>' +
          '<span class="m-card-meta">空剧本，一行示例台词，够你先看到画面</span>' +
        '</span>' +
      '</button>';
    // 缩略图单独请求：拿不到就留个空底，不阻塞列表
    list.querySelectorAll(".m-card-thumb[data-folder], .m-hero-cover[data-folder]").forEach(function (th) {
      var f = th.dataset.folder;
      var img = new Image();
      img.onload = function () {
        th.style.backgroundImage = 'url("/api/thumb?folder=' + encodeURIComponent(f) + '")';
        th.classList.add("has");
      };
      img.src = "/api/thumb?folder=" + encodeURIComponent(f);
    });
    list.querySelectorAll(".m-home-card[data-folder], .m-home-hero[data-folder]").forEach(function (b) {
      b.addEventListener("click", function () { openProject(b.dataset.folder, b); });
    });
    var nb = $("mHomeNew");
    if (nb) nb.addEventListener("click", function () {
      // 复用编辑器自己的「新建游戏」弹窗：先进编辑器，再点它
      enterEditor();
      setTimeout(function () {
        var menuFile = document.querySelector('.menu-item[data-menu="file"]');
        if (menuFile) menuFile.click();
        var ng = $("menuNewGame") || $("btnNewGame");
        if (ng) ng.click();
      }, 120);
    });
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
  }

  // ---- 设置：主题 / 游戏方向 / 返回作品列表。做成一页，别学桌面端散在五个地方 ----
  var sheet = null;
  var orient = "any";
  function openSettings() {
    if (sheet) { sheet.remove(); sheet = null; return; }
    var theme = "dark";
    try { theme = localStorage.getItem("gal_editor_theme") === "light" ? "light" : "dark"; } catch (e) {}
    sheet = document.createElement("div");
    sheet.className = "m-sheet";
    sheet.innerHTML =
      '<div class="m-sheet-mask"></div>' +
      '<div class="m-sheet-body">' +
        '<div class="m-sheet-grab"></div>' +
        '<div class="m-sheet-title">设置</div>' +
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
        '<div class="m-set-row"><span>作品列表</span>' +
          '<button type="button" class="m-set-btn" id="mSetHome">返回</button></div>' +
        '<div class="m-set-note">「游戏画面」是给玩家看的：竖屏 / 横屏时，导出的网页会提示对方把手机转过来；选「跟随」就横竖都行。' +
        'MYONL 编辑器全部本地运行，工程和素材都在你自己的电脑/手机上，不上传任何服务器。</div>' +
      '</div>';
    document.body.appendChild(sheet);

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

    var hb = sheet.querySelector("#mSetHome");
    if (hb) hb.addEventListener("click", function () { window.__myonlShowHome(); });

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

  var gear = $("mHomeSet");
  if (gear) gear.addEventListener("click", openSettings);
})();
