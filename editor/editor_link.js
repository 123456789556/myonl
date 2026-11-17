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
