/* ============================================================
   P219 桌面「换作品」
   ------------------------------------------------------------
   以前电脑端想换一部作品，唯一的办法是进设置中心改「工程目录」那一格路径，
   或者重新开一遍编辑器。可编辑器里明明有作品台（/api/home 就在返回
   games/* 的清单），只是从来没人把它接到桌面上 —— 前端 0 处调用。

   这里补一个入口：文件菜单 →「换作品」，把 games/ 下的工程列出来，
   点一行 POST /api/project，切成功就整页重载（切工程必须重载，前端状态
   全是按上一份剧本算的，不重载等于半新半旧）。

   只用 /api/home + /api/project 两条现有路由，不新增后端接口。
   样式全部内联：editor.css 已到行数上限，为一个弹窗去改它不划算。
   ============================================================ */
(function () {
  "use strict";
  if (window.__openProjectSwitch) return;

  var maskEl = null, boxEl = null, listEl = null, tipEl = null, busy = false;

  function el(tag, css, text) {
    var n = document.createElement(tag);
    if (css) n.style.cssText = css;
    if (text != null) n.textContent = text;
    return n;
  }

  function ensure() {
    if (maskEl) return;
    maskEl = el("div", "position:fixed;inset:0;z-index:9000;background:rgba(8,12,20,.55);" +
      "display:flex;align-items:center;justify-content:center;padding:18px");
    maskEl.id = "projSwitchMask";
    boxEl = el("div", "width:min(420px,100%);max-height:min(70vh,560px);display:flex;flex-direction:column;" +
      "background:var(--bg-2,#1c2331);border:1px solid rgba(255,255,255,.10);border-radius:4px;" +
      "box-shadow:0 18px 50px rgba(0,0,0,.45);overflow:hidden");
    var head = el("div", "padding:14px 16px 10px;border-bottom:1px solid rgba(255,255,255,.08)");
    head.appendChild(el("div", "font-size:15px;font-weight:600;color:var(--fg,#e8eefc)", "换一个作品"));
    tipEl = el("div", "margin-top:4px;font-size:12px;line-height:1.6;color:#8fa3bf", "正在读作品列表…");
    head.appendChild(tipEl);
    boxEl.appendChild(head);
    listEl = el("div", "flex:1;overflow:auto;padding:6px");
    boxEl.appendChild(listEl);
    var foot = el("div", "padding:10px 16px 14px;display:flex;justify-content:flex-end;gap:8px;" +
      "border-top:1px solid rgba(255,255,255,.08)");
    var cancel = el("button", "height:32px;padding:0 14px;border-radius:4px;cursor:pointer;" +
      "background:transparent;border:1px solid rgba(255,255,255,.14);color:#b8c6de", "取消");
    cancel.type = "button";
    cancel.addEventListener("click", close);
    foot.appendChild(cancel);
    boxEl.appendChild(foot);
    maskEl.appendChild(boxEl);
    maskEl.addEventListener("click", function (e) { if (e.target === maskEl) close(); });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && maskEl && maskEl.parentNode) close();
    });
    document.body.appendChild(maskEl);
  }

  function close() {
    if (maskEl && maskEl.parentNode) maskEl.parentNode.removeChild(maskEl);
    maskEl = boxEl = listEl = tipEl = null;
  }

  function row(p) {
    var on = !!p.current;
    var r = el("button", "display:flex;align-items:center;gap:10px;width:100%;text-align:left;" +
      "padding:10px 12px;margin-bottom:4px;border-radius:4px;cursor:pointer;border:1px solid transparent;" +
      (on ? "background:rgba(79,140,255,.14);border-color:rgba(79,140,255,.45);" : "background:transparent;") +
      "color:var(--fg,#e8eefc)");
    r.type = "button";
    var name = el("span", "flex:1;font-size:14px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap",
      String(p.name || p.folder || ""));
    r.appendChild(name);
    r.appendChild(el("span", "font-size:12px;color:#8fa3bf;flex:0 0 auto", (p.ins || 0) + " 句"));
    if (on) r.appendChild(el("span", "font-size:12px;color:#4f8cff;flex:0 0 auto", "现在这部"));
    if (!on) {
      r.addEventListener("mouseenter", function () { r.style.background = "rgba(255,255,255,.06)"; });
      r.addEventListener("mouseleave", function () { r.style.background = "transparent"; });
      r.addEventListener("click", function () { pick(p); });
    }
    return r;
  }

  function pick(p) {
    if (busy) return;
    busy = true;
    if (tipEl) tipEl.textContent = "正在切到「" + (p.name || "") + "」…";
    // 桌面 /api/project 只收 {folder}（games/ 的直接子目录名），传绝对路径会被挡回来
    var abs = p.folder || "";
    fetch("/api/project", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ folder: abs })
    }).then(function (r) { return r.json(); }).then(function (r) {
      if (!r.ok) throw new Error(r.message || "切不过去");
      location.reload();          // 切工程必须整页重载，见文件头
    }).catch(function (e) {
      busy = false;
      if (tipEl) tipEl.textContent = "没切成：" + ((e && e.message) || e);
    });
  }

  window.__openProjectSwitch = function () {
    ensure();
    listEl.innerHTML = "";
    fetch("/api/home").then(function (r) { return r.json(); }).then(function (d) {
      var rows = (d && d.projects) || [];
      rows.forEach(function (p) {
        if (!p.folder) p.folder = String(p.name || "");
      });
      if (!rows.length) {
        tipEl.textContent = "这个 games 目录里还没有作品";
        listEl.appendChild(el("div", "padding:18px 12px;font-size:13px;line-height:1.7;color:#8fa3bf",
          "先「新建游戏」建一部，它会出现在这里。"));
        return;
      }
      tipEl.textContent = rows.length + " 个作品 · 点一行切过去（会自动重载）";
      rows.forEach(function (p) { listEl.appendChild(row(p)); });
    }).catch(function (e) {
      if (tipEl) tipEl.textContent = "读不到作品列表：" + ((e && e.message) || e);
    });
  };
})();
