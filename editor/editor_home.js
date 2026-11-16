/* ===================================================================
   P65：手机端第一层「工作台」
   打开就是工程卡片（最近用的排前面），点一张才进编辑器。
   桌面端（>860px）不接管，直接进编辑器 —— 电脑上三列 IDE 是合适的。
   =================================================================== */
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };

  var EDIT_KEY = "myonl:editing";
  var isMobile = function () { return window.matchMedia && window.matchMedia("(max-width:860px)").matches; };
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
      '<div class="m-home-title">我的作品</div>' +
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

  function card(p) {
    return '<button type="button" class="m-home-card" data-folder="' +
      p.folder.replace(/"/g, "&quot;") + '">' +
      '<span class="m-card-name">' + p.name.replace(/</g, "&lt;") + '</span>' +
      '<span class="m-card-meta">' + p.ins + ' 条指令 · ' + p.assets + ' 个素材 · ' + ago(p.mtime) + '</span>' +
      '<span class="m-card-go">›</span></button>';
  }

  function render(projects) {
    var list = $("mHomeList");
    if (!list) return;
    var cards = projects.map(card).join("");
    list.innerHTML = cards +
      '<button type="button" class="m-home-card m-home-new" id="mHomeNew">' +
        '<span class="m-card-name">＋ 新建作品</span>' +
        '<span class="m-card-meta">空剧本，一行示例台词，够你先看到画面</span>' +
      '</button>';
    list.querySelectorAll(".m-home-card[data-folder]").forEach(function (b) {
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

  // ---- 设置：主题 / 字号 / 关于。做成一页，别学桌面端散在五个地方 ----
  var sheet = null;
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
        '<div class="m-set-row"><span>作品列表</span>' +
          '<button type="button" class="m-set-btn" id="mSetHome">返回</button></div>' +
        '<div class="m-set-note">MYONL 编辑器 · 全部本地运行，工程和素材都在你自己的电脑/手机上，不上传任何服务器。</div>' +
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
  }

  fetch("/api/home").then(function (r) { return r.json(); }).then(function (res) {
    if (!res.ok) throw new Error("读不到作品列表");
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
