

/* ===================================================================
   角色库（characters.json，项目级角色资产，2026-11-01）
   - 角色 = 一等资产：名字/颜色/对话框布局/立绘表情映射（表达式 → 素材图片）
   - 素材联动：从 images/ 按「角色_表情」自动导入；每行表情可直接选素材并看缩略图
   - 场景视图从这里取角色与表情；保存写 characters.json（引擎启动时作为初始角色表）
   =================================================================== */
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var E = window.__editor || {};
  var pane = document.querySelector(".left-pane"), tabs = $("editorTabs");
  if (!pane || !tabs) return;

  var page = document.createElement("div");
  page.className = "center-page char-page";
  page.id = "charPage";
  page.innerHTML = '<div class="cp-head">' +
    '<span class="cp-title">角色库</span>' +
    '<span class="cp-hint">可选模式：不用角色库也能直接写 @character；用了就更方便管立绘/表情</span>' +
    '<span class="cp-spacer"></span>' +
    '<button type="button" class="cp-btn" id="charAssets" title="打开素材库（角色和素材是同一套文件）">素材库</button><button type="button" class="cp-btn" id="charImport" title="扫描 images/ 里的「角色_表情」素材自动建角色">从素材导入</button>' +
    '<button type="button" class="cp-btn" id="charSave" title="保存到项目 characters.json">保存</button>' +
    '<button type="button" class="cp-btn" id="charClose" title="关闭（Esc）">✕ 关闭</button>' +
    '</div><div class="scene-body"><div class="scene-list"><input class="set-search" id="charSearch" placeholder="搜索角色…"><div id="charList"></div></div><div class="scene-form" id="charForm"></div></div>';
  pane.appendChild(page);

  var listEl = $("charList"), formEl = $("charForm"), searchEl = $("charSearch");
  var data = { schema: 1, characters: [] };
  var cur = -1;
  var images = [];
  var usage = {};        // V4：{角色ID: {lines, files}} 引用计数（来自 /api/characters/usage）

  function fit() { page.style.top = (tabs.offsetTop + tabs.offsetHeight) + "px"; }
  function toast(msg, err) { try { if (E.toast) E.toast(msg, !!err); } catch (e) {} }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function assetUrl(name) { try { return E.assetURL ? E.assetURL("images", name) : ""; } catch (e) { return ""; } }

  function loadAssets() {
    try { var a = E.getAssets ? E.getAssets() : null; images = (a && a.images) || []; } catch (e) { images = []; }
  }

  function avatarOf(c) {
    if (!c.avatars) return "";
    var keys = Object.keys(c.avatars);
    if (!keys.length) return "";
    var preferred = c.avatars["默认"] ? "默认" : c.avatars["normal"] ? "normal" : keys[0];
    return c.avatars[preferred] || "";
  }

  function load() {
    fetch("/api/characters", { cache: "no-store" }).then(function (r) { return r.json(); }).then(function (d) {
      data = (d && d.data) || { schema: 1, characters: [] };
      if (!Array.isArray(data.characters)) data.characters = [];
      window.__characterLib = data;
      renderList();
      applyPendingName();
      if (data.characters.length && (cur < 0 || cur >= data.characters.length)) select(0);
      else if (!data.characters.length) { cur = -1; renderForm(); }
      loadUsage();
    }).catch(function (e) { toast("读取角色库失败：" + e, true); });
  }

  // V4：引用计数（跨 @include 文件）
  function loadUsage() {
    fetch("/api/characters/usage", { cache: "no-store" })
      .then(function (r) { return r.json(); })
      .then(function (d) { usage = (d && d.usage) || {}; renderList(); })
      .catch(function () {});
  }

  function renderList() {
    var q = (searchEl.value || "").trim().toLowerCase();
    var html = "";
    data.characters.forEach(function (c, i) {
      if (q && c.id.toLowerCase().indexOf(q) < 0 && (c.name || "").toLowerCase().indexOf(q) < 0) return;
      var av = avatarOf(c);
      var n = c.avatars ? Object.keys(c.avatars).length : 0;
      var u = usage[c.id];
      var refTxt = u ? (u.lines + " 处引用") : "未引用";
      html += '<div class="scene-item' + (i === cur ? " active" : "") + '" data-i="' + i + '">' +
        (av ? '<img class="char-ava" src="' + esc(assetUrl(av)) + '" alt="">' : '<span class="char-dot" style="background:' + esc(c.color) + '"></span>') +
        '<span class="sc-name">' + esc(c.name || c.id) + "</span>" +
        '<span class="sc-meta">' + n + " 表情 · " + refTxt + "</span></div>";
    });
    html += '<div class="char-add-tile" id="charAddTile"><span class="char-add-plus">＋</span>新角色</div>';
    listEl.innerHTML = html;
  }

  function select(i) { cur = i; renderList(); renderForm(); }

  function newCharacter() {
    return { id: "新角色" + (data.characters.length + 1), name: "新角色", color: "#ffffff", kind: "default", avatars: {}, layers: {}, voice: "", notes: "" };
  }

  function avatarRow(expr, img, i) {
    var opts = '<option value="">（不选素材）</option>';
    images.forEach(function (m) { opts += '<option value="' + esc(m) + '"' + (m === img ? " selected" : "") + ">" + esc(m) + "</option>"; });
    if (img && images.indexOf(img) < 0) opts += '<option value="' + esc(img) + '" selected>' + esc(img) + "（当前）</option>";
    return '<div class="char-av-row" data-i="' + i + '"><input class="char-av-expr" placeholder="表情名" value="' + esc(expr) + '">' +
      '<select class="char-av-img">' + opts + "</select>" +
      (img ? '<img class="char-av-thumb" src="' + esc(assetUrl(img)) + '" alt="">' : '<img class="char-av-thumb" alt="" style="visibility:hidden">') +
      '<button type="button" class="icon-btn char-av-del" data-i="' + i + '">✕</button></div>';
  }

  function layerRow(part, img, i) {
    // V4：分层立绘——部位（如 身体/表情）→ 素材名，引擎 @show 支持「部位:素材」
    var opts = '<option value="">（不选素材）</option>';
    images.forEach(function (m) { opts += '<option value="' + esc(m) + '"' + (m === img ? " selected" : "") + ">" + esc(m) + "</option>"; });
    if (img && images.indexOf(img) < 0) opts += '<option value="' + esc(img) + '" selected>' + esc(img) + "（当前）</option>";
    return '<div class="char-layer-row" data-i="' + i + '"><input class="char-layer-part" placeholder="部位（如 身体）" value="' + esc(part) + '">' +
      '<select class="char-layer-img">' + opts + "</select>" +
      '<button type="button" class="icon-btn char-layer-del" data-i="' + i + '">✕</button></div>';
  }

  function renderForm() {
    if (cur < 0 || !data.characters[cur]) {
      formEl.innerHTML = '<div class="scene-empty">左侧选一个角色，或点「新增角色」。</div>';
      return;
    }
    var c = data.characters[cur];
    var h = [];
    h.push('<div class="sf-row"><span class="sf-label">角色 ID</span><input id="charId" value="' + esc(c.id) + '" title="剧本里 @show/台词用的名字；改名会同步场景视图" ' + (c._existing ? "" : "") + '><button type="button" class="icon-btn" id="charRename" title="改角色名并同步所有 @character/@show/@hide/@anim/台词引用">改名并同步剧本</button><button type="button" class="icon-btn" id="charDelete">删除角色</button></div>');
    h.push('<div class="sf-row"><span class="sf-label">显示名</span><input id="charName" value="' + esc(c.name || c.id) + '"></div>');
    h.push('<div class="sf-row"><span class="sf-label">颜色</span><input id="charColor" type="color" value="' + esc(c.color || "#ffffff") + '" style="max-width:60px;padding:2px"><span class="sf-label" style="margin-left:8px">对话框布局</span><input id="charKind" value="' + esc(c.kind || "default") + '" placeholder="default" style="max-width:160px"></div>');
    h.push('<div class="sf-row"><span class="sf-label">备注</span><input id="charNotes" value="' + esc(c.notes || "") + '" placeholder="只给自己看"></div>');
    h.push('<div class="sf-row"><span class="sf-label">配音前缀</span><input id="charVoice" value="' + esc(c.voice || "") + '" placeholder="如 林晚_（配音文件名前缀，可空）"></div>');
    h.push('<div class="sf-sec">立绘表情 <button type="button" class="icon-btn" id="charAddAv">＋ 加表情</button></div>');
    var keys = Object.keys(c.avatars || {});
    h.push('<div id="charAvs">');
    if (!keys.length) h.push('<div class="set-hint">还没有表情——「＋加表情」选一张 images/ 里的素材（如 林晚_微笑）。</div>');
    keys.forEach(function (k, i) { h.push(avatarRow(k, c.avatars[k], i)); });
    h.push("</div>");
    h.push('<div class="sf-sec">分层立绘 <button type="button" class="icon-btn" id="charAddLayer">＋ 加层</button></div>');
    var lk = Object.keys(c.layers || {});
    h.push('<div id="charLayers">');
    if (!lk.length) h.push('<div class="set-hint">可选：如 身体=林晚_身体、表情=林晚_微笑；不填就用上面的单张表情。</div>');
    lk.forEach(function (k, i) { h.push(layerRow(k, c.layers[k], i)); });
    h.push("</div>");
    formEl.innerHTML = h.join("");
    wireForm();
  }

  function wireForm() {
    var c = data.characters[cur];
    $("charDelete").addEventListener("click", function () {
      if (!confirm("删除角色「" + (c.name || c.id) + "」？只删角色库里的定义，不改剧本。")) return;
      data.characters.splice(cur, 1);
      cur = Math.min(cur, data.characters.length - 1);
      renderList(); renderForm();
    });
    $("charRename").addEventListener("click", function () {
      var oldId = c.id;
      var nv = prompt("把角色「" + oldId + "」改名为：", oldId);
      if (!nv || nv === oldId) return;
      fetch("/api/character/rename", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ old: oldId, new: nv }) })
        .then(function (r) { return r.json(); })
        .then(function (resp) { toast(resp.message || (resp.ok ? "已改名" : "改名失败"), !resp.ok); if (resp.ok) load(); })
        .catch(function (e) { toast("改名失败：" + e, true); });
    });
    $("charAddAv").addEventListener("click", function () { c.avatars = c.avatars || {}; c.avatars["新表情"] = ""; renderForm(); });
    $("charAddLayer").addEventListener("click", function () {
      c.layers = c.layers || {};
      c.layers["新部位"] = "";
      renderForm();
    });
    var lDels = formEl.querySelectorAll(".char-layer-del");
    for (var li = 0; li < lDels.length; li++) {
      lDels[li].addEventListener("click", function () {
        var idx = parseInt(this.getAttribute("data-i"), 10);
        delete c.layers[Object.keys(c.layers)[idx]];
        renderForm();
      });
    }
    var lRows = formEl.querySelectorAll(".char-layer-row");
    for (var lr = 0; lr < lRows.length; lr++) {
      (function (row, idx) {
        var partI = row.querySelector(".char-layer-part"), imgS = row.querySelector(".char-layer-img");
        partI.addEventListener("change", function () {
          var keys = Object.keys(c.layers);
          var oldVal = c.layers[keys[idx]];
          delete c.layers[keys[idx]];
          var nk = partI.value.trim() || "部位";
          c.layers[nk] = oldVal;
          renderForm();
        });
        imgS.addEventListener("change", function () {
          var keys = Object.keys(c.layers);
          c.layers[keys[idx]] = imgS.value;
          renderForm();
        });
      })(lRows[lr], lr);
    }
    var dels = formEl.querySelectorAll(".char-av-del");
    for (var i = 0; i < dels.length; i++) {
      dels[i].addEventListener("click", function () {
        var idx = parseInt(this.getAttribute("data-i"), 10);
        var k = Object.keys(c.avatars)[idx];
        delete c.avatars[k];
        renderForm();
      });
    }
    var rows = formEl.querySelectorAll(".char-av-row");
    for (var j = 0; j < rows.length; j++) {
      (function (row) {
        var exprI = row.querySelector(".char-av-expr"), imgS = row.querySelector(".char-av-img");
        var oldKey = Object.keys(c.avatars)[j];
        exprI.addEventListener("change", function () {
          var oldVal = c.avatars[oldKey];
          delete c.avatars[oldKey];
          var nk = exprI.value.trim() || "默认";
          c.avatars[nk] = oldVal;
          renderForm();
        });
        imgS.addEventListener("change", function () {
          var keys = Object.keys(c.avatars);
          c.avatars[keys[j]] = imgS.value;
          renderForm();
        });
      })(rows[j]);
    }
  }

  function collect() {
    var c = data.characters[cur];
    if (!c) return null;
    c.id = ($("charId").value || "").trim() || c.id;
    c.name = ($("charName").value || "").trim() || c.id;
    c.color = $("charColor").value || "#ffffff";
    c.kind = ($("charKind").value || "default").trim() || "default";
    c.notes = $("charNotes").value || "";
    c.voice = ($("charVoice").value || "").trim();
    c.layers = {};
    var lr = formEl.querySelectorAll(".char-layer-row");
    for (var i = 0; i < lr.length; i++) {
      var part = lr[i].querySelector(".char-layer-part").value.trim();
      var img = lr[i].querySelector(".char-layer-img").value;
      if (part && img) c.layers[part] = img;
    }
    return c;
  }

  function save() {
    collect();
    fetch("/api/characters", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }).then(function (r) { return r.json(); }).then(function (resp) {
      if (!resp.ok) { toast(resp.message || "保存失败", true); return; }
      window.__characterLib = data;
      toast("角色库已保存（characters.json）");
      renderList();
    }).catch(function (e) { toast("保存失败：" + e, true); });
  }

  function importFromAssets() {
    loadAssets();
    var made = 0;
    var skip = { bg: 1, cg: 1, ui: 1, mooki: 1, logo: 1, title: 1 };
    var known = {};
    data.characters.forEach(function (c) { known[c.id] = c; });
    images.forEach(function (name) {
      var base = String(name).replace(/\.[^.]+$/, "");
      var parts = base.split("_");
      if (parts.length < 2) return;
      var cid = parts[0], expr = parts.slice(1).join("_");
      if (skip[cid.toLowerCase()]) return;
      var target = known[cid];
      if (!target) {
        target = { id: cid, name: cid, color: "#ffffff", kind: "default", avatars: {}, notes: "" };
        data.characters.push(target);
        known[cid] = target;
        made++;
      }
      target.avatars = target.avatars || {};
      if (!target.avatars[expr]) target.avatars[expr] = name;
    });
    renderList();
    if (cur < 0 && data.characters.length) select(0);
    toast(made ? ("从素材导入 " + made + " 个角色") : "没有发现新的「角色_表情」素材");
  }

  function open(name) {
    page.classList.add("open"); fit(); loadAssets();
    window.__pendingCharName = name || "";
    load();
  }
  function applyPendingName() {
    var nm = window.__pendingCharName; window.__pendingCharName = "";
    if (!nm) return;
    var idx = -1;
    data.characters.forEach(function (ch, i) { if (ch.id === nm) idx = i; });
    if (idx < 0) { data.characters.push({ id: nm, name: nm, color: "#ffffff", kind: "default", avatars: {}, notes: "" }); idx = data.characters.length - 1; }
    select(idx);
  }
  function close() { page.classList.remove("open"); }
  window.__openCharacterManager = open;
  $("charClose").addEventListener("click", close);
  $("charSave").addEventListener("click", save);
  $("charImport").addEventListener("click", importFromAssets);
  $("charAssets").addEventListener("click", function () {
    var act = document.getElementById("actAssets");
    if (act) act.click();
    toast("素材库：images/ 里 角色_表情 的文件，可从这里「从素材导入」回角色库");
  });
  searchEl.addEventListener("input", renderList);
  listEl.addEventListener("click", function (ev) {
    var add = ev.target.closest ? ev.target.closest("#charAddTile") : null;
    if (add) {
      data.characters.push(newCharacter());
      select(data.characters.length - 1);
      setTimeout(function () { var el = $("charId"); if (el) { el.focus(); el.select(); } }, 20);
      return;
    }
    var it = ev.target.closest ? ev.target.closest(".scene-item") : null;
    if (!it) return;
    select(parseInt(it.getAttribute("data-i"), 10));
  });
  document.addEventListener("keydown", function (ev) {
    if (ev.key === "Escape" && page.classList.contains("open")) { close(); ev.preventDefault(); ev.stopPropagation(); }
  }, true);
  window.addEventListener("resize", function () { if (page.classList.contains("open")) fit(); });

  // ---- 素材面板内嵌「角色」分类（A2）：注入 tab + 捕获点击接管渲染 ----
  function injectAssetTab() {
    var tabsBox = document.getElementById("assetTabs");
    var body = document.getElementById("assetBody");
    if (!tabsBox || !body || tabsBox.querySelector('[data-cat="characters"]')) return;
    var tab = document.createElement("div");
    tab.className = "asset-tab";
    tab.setAttribute("data-cat", "characters");
    tab.textContent = "角色";
    tabsBox.appendChild(tab);
    tabsBox.addEventListener("click", function (ev) {
      var t = ev.target.closest ? ev.target.closest(".asset-tab") : null;
      if (!t || t.getAttribute("data-cat") !== "characters") return;
      ev.stopPropagation(); ev.preventDefault();
      tabsBox.querySelectorAll(".asset-tab").forEach(function (x) { x.classList.toggle("active", x === t); });
      renderAssetCharacters();
    }, true);
  }
  function renderAssetCharacters() {
    var body = document.getElementById("assetBody");
    if (!body) return;
    function draw() {
      body.innerHTML = "";
      var list = data.characters || [];
      if (!list.length) {
        body.innerHTML = '<div class="asset-empty">还没有角色：点下面「从素材导入」或打开角色库新建</div>';
      } else {
        list.forEach(function (ch) {
          var card = document.createElement("div");
          card.className = "asset-card char-asset-card";
          card.title = (ch.name || ch.id) + "（点击打开角色库编辑）";
          var av = avatarOf(ch);
          if (av) {
            var img = document.createElement("img"); img.loading = "lazy"; img.alt = ch.id; img.src = assetUrl(av); card.appendChild(img);
          } else {
            var ph = document.createElement("div"); ph.className = "ph"; ph.textContent = (ch.id || "?").slice(0, 1); card.appendChild(ph);
          }
          var nm = document.createElement("div"); nm.className = "nm"; nm.textContent = ch.name || ch.id; card.appendChild(nm);
          var meta = document.createElement("div"); meta.className = "char-asset-meta";
          meta.textContent = Object.keys(ch.avatars || {}).length + " 表情"; card.appendChild(meta);
          card.addEventListener("click", function () { open(ch.id); });
          body.appendChild(card);
        });
      }
      var bar = document.createElement("div");
      bar.className = "char-asset-bar";
      var imp = document.createElement("button"); imp.type = "button"; imp.className = "icon-btn"; imp.textContent = "从素材导入";
      imp.addEventListener("click", function () { importFromAssets(); draw(); });
      var lib = document.createElement("button"); lib.type = "button"; lib.className = "icon-btn"; lib.textContent = "打开角色库";
      lib.addEventListener("click", open);
      bar.appendChild(imp); bar.appendChild(lib);
      body.appendChild(bar);
    }
    if (!data.characters || !data.characters.length) {
      fetch("/api/characters", { cache: "no-store" }).then(function (r) { return r.json(); })
        .then(function (d) { data = (d && d.data) || data; window.__characterLib = data; draw(); })
        .catch(draw);
    } else draw();
  }
  injectAssetTab();

  // 把「角色库」入口加到场景视图头部 + 动作条（不改 HTML 行数）
  try {
    var scenePage = $("scenePage");
    if (scenePage) {
      var head = scenePage.querySelector(".cp-head");
      var b = document.createElement("button");
      b.type = "button"; b.className = "cp-btn"; b.textContent = "角色库";
      b.title = "角色与立绘素材管理";
      b.addEventListener("click", open);
      var closeBtn = $("sceneClose");
      head.insertBefore(b, closeBtn || head.lastChild);
    }
    var bar = document.querySelector(".editor-toolbar");
    if (bar) {
      var tb = document.createElement("button");
      tb.type = "button"; tb.className = "tb-btn"; tb.id = "btnCharLib";
      tb.title = "角色库：角色与立绘素材";
      tb.innerHTML = '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="9" cy="8" r="3.2"/><path d="M3.5 19.5c0-3.1 2.5-5 5.5-5s5.5 1.9 5.5 5"/><circle cx="17" cy="9.5" r="2.2"/><path d="M15 19.5c.2-2.1 1.6-3.6 3.6-3.6"/></svg><span class="tb-txt">角色</span>';
      tb.addEventListener("click", open);
      bar.insertBefore(tb, bar.firstChild);
    }
  } catch (e) {}
})();
