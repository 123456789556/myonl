/* P74：手机连接 / 插线推送 / AI 助手（预留）—— 三块面板塞进「设置」里。

   思路：协同不需要另做一套同步。编辑器本身就是电脑上的一个 HTTP 服务，
   手机打开同一个地址 = 同一个工程、同一份文件。所以这里只解决两件小事：
   手机怎么找到地址（二维码），以及做好的成品怎么塞进手机（adb push）。

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

  // ---------- 手机连接 ----------
  function buildLink() {
    var box = el("div", "lk-block");
    box.appendChild(el("div", "lk-title", "手机连接"));
    var row = el("div", "lk-row");

    var qrWrap = el("div", "lk-qr");
    var img = el("img", "");
    img.id = "lkQrImg";
    img.alt = "手机扫码";
    qrWrap.appendChild(img);
    row.appendChild(qrWrap);

    var side = el("div", "lk-side");
    var url = el("div", "lk-url");
    url.id = "lkUrl";
    url.textContent = "探测中…";
    side.appendChild(url);
    var hint = el("div", "lk-hint");
    hint.id = "lkHint";
    side.appendChild(hint);

    var btns = el("div", "lk-btns");
    var copy = el("button", "lk-btn", "复制地址");
    copy.id = "lkCopy";
    btns.appendChild(copy);
    var reload = el("button", "lk-btn", "重新探测");
    reload.id = "lkReload";
    btns.appendChild(reload);
    side.appendChild(btns);
    row.appendChild(side);
    box.appendChild(row);
    return box;
  }

  function loadLink() {
    api("/api/mobile-link").then(function (r) {
      var url = $("lkUrl"), img = $("lkQrImg"), hint = $("lkHint");
      if (!url) return;
      url.textContent = r.url || "没探测到局域网地址";
      hint.textContent = r.hint || "";
      if (img) {
        if (r.qr) { img.src = r.qr; img.style.display = "block"; }
        else { img.removeAttribute("src"); img.style.display = "none"; }
      }
      var copy = $("lkCopy");
      if (copy) {
        copy.onclick = function () {
          var text = r.url || "";
          if (!text) return;
          if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(text).then(function () { copy.textContent = "已复制"; });
          } else {
            copy.textContent = "请手动复制";
          }
          setTimeout(function () { copy.textContent = "复制地址"; }, 1600);
        };
      }
    }).catch(function () {
      var hint = $("lkHint");
      if (hint) hint.textContent = "读不到连接信息（后端没响应）";
    });
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

  // ---------- AI 助手（预留） ----------
  function buildAi() {
    var box = el("div", "lk-block");
    box.appendChild(el("div", "lk-title", "AI 助手（预留）"));
    [["aiBase", "接口地址（OpenAI 兼容）", "https://api.openai.com/v1"],
     ["aiModel", "模型名", "例如 gpt-4o-mini"],
     ["aiKey", "API Key（只存本机，不写进工程）", "sk-..."]
    ].forEach(function (f) {
      var row = el("div", "lk-field");
      row.appendChild(el("label", "", f[1]));
      var input = document.createElement("input");
      input.id = f[0];
      input.placeholder = f[2];
      if (f[0] === "aiKey") input.type = "password";
      row.appendChild(input);
      box.appendChild(row);
    });
    var msg = el("div", "lk-hint");
    msg.id = "aiMsg";
    box.appendChild(msg);
    var btns = el("div", "lk-btns");
    var save = el("button", "lk-btn lk-primary", "保存");
    save.id = "aiSave";
    btns.appendChild(save);
    var ping = el("button", "lk-btn", "测试连接");
    ping.id = "aiPing";
    btns.appendChild(ping);
    box.appendChild(btns);
    box.appendChild(el("div", "lk-hint",
      "现在只是把配置位置留好：key 存用户目录的 .myonl/ai.json，不进导出包、不进 git。" +
      "真正让 AI 改剧本的能力接在这后面。"));
    return box;
  }

  function loadAi() {
    api("/api/ai").then(function (r) {
      var base = $("aiBase"), model = $("aiModel"), key = $("aiKey"), msg = $("aiMsg");
      if (base) base.value = r.base_url || "";
      if (model) model.value = r.model || "";
      if (key) {
        key.value = "";
        key.placeholder = r.has_key ? ("已配置 " + (r.key_mask || "")) : "sk-...";
      }
      if (msg) msg.textContent = r.has_key ? "已有一把 key（不会再显示明文）" : "还没配 key";
    }).catch(function () {});
  }

  function saveAi() {
    var msg = $("aiMsg");
    api("/api/ai", {
      base_url: ($("aiBase") || {}).value,
      model: ($("aiModel") || {}).value,
      key: ($("aiKey") || {}).value,
      enabled: true
    }).then(function (r) {
      if (msg) msg.textContent = r.ok ? "已保存：" + (r.path || "") : ("失败：" + (r.message || ""));
      if (r.ok) loadAi();
    }).catch(function () { if (msg) msg.textContent = "保存失败（后端没响应）"; });
  }

  function pingAi() {
    var msg = $("aiMsg");
    if (msg) msg.textContent = "测试中…";
    api("/api/ai/ping", {}).then(function (r) {
      if (msg) msg.textContent = (r.ok ? "" : "失败：") + (r.message || "");
    }).catch(function () { if (msg) msg.textContent = "测试失败（后端没响应）"; });
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
    wrap.appendChild(buildLink());
    wrap.appendChild(buildAdb());
    wrap.appendChild(buildAi());
    if (anchor && anchor.parentNode) anchor.parentNode.insertBefore(wrap, anchor);
    else modal.appendChild(wrap);
    mounted = true;

    var reload = $("lkReload");
    if (reload) reload.onclick = loadLink;
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
    var save = $("aiSave");
    if (save) save.onclick = saveAi;
    var ping = $("aiPing");
    if (ping) ping.onclick = pingAi;

    loadLink();
    loadAdb(true);
    loadAi();
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
