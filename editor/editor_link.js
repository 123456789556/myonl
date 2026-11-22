/* 插线推送到手机 —— 设置中心里的一小块。

   P88 砍掉了「手机连接」（扫码 + 局域网地址探测）：真机上一次都没跑通。
   P89 又砍掉了「AI 助手」：只有一张填 key 的表单，没有任何真的改剧本能力。
   现在把成品送进手机只有一条路 —— 插数据线，adb push 到 Download/MYONL/。

   DOM 全部由本文件创建：index.html 已经到行数硬限，不能再往里加结构。 */
(function () {
  "use strict";

  var mounted = false;

  function $(id) { return document.getElementById(id); }
  function api(path, body) {
    var opt = body
      ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }
      : {};
    return fetch(path, opt).then(function (r) { return r.json(); });
  }

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }

  // ---------- 插线推送 ----------
  function buildAdb() {
    var box = el("div", "lk-block");
    box.appendChild(el("div", "lk-title", "插线推送到手机"));
    var msg = el("div", "lk-hint");
    msg.id = "adbMsg";
    msg.textContent = "检测中…";
    box.appendChild(msg);
    var btns = el("div", "lk-btns");
    var check = el("button", "lk-btn", "检测数据线");
    check.id = "adbCheck";
    btns.appendChild(check);
    var push = el("button", "lk-btn lk-primary", "把成品推到手机");
    push.id = "adbPush";
    btns.appendChild(push);
    box.appendChild(btns);
    box.appendChild(el("div", "lk-hint",
      "推到手机的 Download/MYONL/，用手机任何浏览器点开就能玩。需要先在「导出」里导一次单文件。"));
    return box;
  }

  function loadAdb(silent) {
    api("/api/adb").then(function (r) {
      var msg = $("adbMsg");
      if (msg) msg.textContent = r.message || "";
    }).catch(function () {
      if (!silent) {
        var msg = $("adbMsg");
        if (msg) msg.textContent = "读不到 adb 状态（后端没响应）";
      }
    });
  }

  // ---------- 装进设置弹窗 ----------
  // 编辑器会把 #settingsModal 里的 .modal 搬进中间的「设置中心」页面（editor_pro.js），
  // 所以不能只认 #settingsModal 下的节点 —— 两种位置都要认。
  function findModal() {
    return document.querySelector(".center-page .modal") ||
      document.querySelector("#settingsModal .modal");
  }

  function mount() {
    var modal = findModal();
    if (!modal || mounted) return;
    var anchor = modal.querySelector(".modal-hint");
    var wrap = el("div", "lk-wrap");
    wrap.appendChild(buildAdb());
    if (anchor && anchor.parentNode) anchor.parentNode.insertBefore(wrap, anchor);
    else modal.appendChild(wrap);
    mounted = true;

    var check = $("adbCheck");
    if (check) check.onclick = function () { loadAdb(false); };
    var push = $("adbPush");
    if (push) {
      push.onclick = function () {
        var msg = $("adbMsg");
        if (msg) msg.textContent = "推送中…";
        api("/api/adb", { mode: "push" }).then(function (r) {
          if (msg) msg.textContent = (r.ok ? "" : "失败：") + (r.message || "");
        }).catch(function () { if (msg) msg.textContent = "推送失败（后端没响应）"; });
      };
    }
    loadAdb(true);
  }

  function init() {
    var btn = $("btnSettings");
    if (btn) btn.addEventListener("click", function () { setTimeout(mount, 60); });
    // 设置中心是「中间页」形态：打开时 .modal 被搬进 .center-page，DOM 位置会变，
    // 所以整体盯着 body，出现 .modal 就补一次。
    var mo = new MutationObserver(function () {
      if (mounted) return;
      setTimeout(mount, 0);
    });
    mo.observe(document.body, { childList: true, subtree: true });
    mount();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();

/* 设置中心「关于」页：这一版是哪版 + 有没有新版。
   只在电脑端：桌面有网，能真去问 GitHub。手机安装包按设计不申网络权限，那边只显示版本号。 */
(function () {
  function verMeta() {
    var m = document.querySelector('meta[name="myonl-version"]');
    var v = m ? String(m.content || "").trim() : "";
    return (v && v.indexOf("__") !== 0) ? v : "";
  }
  function newer(a, b) {
    var x = String(a).split("."), y = String(b).split(".");
    for (var i = 0; i < Math.max(x.length, y.length); i++) {
      var p = parseInt(x[i], 10) || 0, q = parseInt(y[i], 10) || 0;
      if (p !== q) return p > q;
    }
    return false;
  }
  function pane() {
    var ps = document.querySelectorAll(".set-pane");
    for (var i = 0; i < ps.length; i++) if (/关于/.test(ps[i].textContent || "")) return ps[i];
    return null;
  }
  function mount() {
    var p = pane();
    if (!p || p.querySelector("#myonlVer")) return;
    var box = document.createElement("div");
    box.innerHTML =
      '<p class="set-p">这一版：v<b id="myonlVer">…</b></p>' +
      '<button type="button" class="icon-btn" id="myonlUpd">检查更新</button>' +
      '<p class="set-hint">覆盖安装、解压覆盖都不会动作品和素材；会一次全没的只有卸载和清数据。</p>';
    p.appendChild(box);
    var cur = verMeta();
    fetch("/api/version").then(function (r) { return r.json(); }).then(function (j) {
      cur = (j && (j.version || j.VERSION)) || cur;
      box.querySelector("#myonlVer").textContent = cur || "开发版";
    }).catch(function () {
      box.querySelector("#myonlVer").textContent = cur || "开发版";
    });
    var btn = box.querySelector("#myonlUpd");
    btn.addEventListener("click", function () {
      if (btn.dataset.url) { try { window.open(btn.dataset.url, "_blank"); } catch (e) {} return; }
      btn.disabled = true;
      btn.textContent = "正在问…";
      fetch("https://api.github.com/repos/123456789556/myonl/releases/latest")
        .then(function (r) { return r.json(); })
        .then(function (j) {
          var tag = String((j && j.tag_name) || "").replace(/^v/, "");
          btn.disabled = false;
          if (!tag) { btn.textContent = "没问到，稍后再试"; return; }
          if (cur && newer(tag, cur)) {
            btn.dataset.url = (j && j.html_url) || "";
            btn.textContent = "有新版 v" + tag + " · 点这里去下载";
          } else {
            btn.textContent = "已是最新（v" + (cur || tag) + "）";
          }
        })
        .catch(function () { btn.disabled = false; btn.textContent = "连不上网，稍后再试"; });
    });
  }
  function boot() {
    mount();
    var mo = new MutationObserver(function () { if (!document.querySelector("#myonlVer")) mount(); });
    mo.observe(document.body, { childList: true, subtree: true });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
