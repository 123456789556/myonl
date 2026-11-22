/* P209 手机端统一弹窗：替掉 confirm / prompt / alert 那套系统框。
   用户原话「删掉弹窗要用现代我们国内的弹窗设计」——
   居中卡片、圆角 18、主按钮蓝 / 危险红、点遮罩等于取消。
   同步的 confirm() 换成 Promise，调用方一律 .then。 */
(function () {
  "use strict";
  var STYLE_ID = "m-dlg-style";

  function ensureStyle() {
    if (document.getElementById(STYLE_ID)) return;
    var st = document.createElement("style");
    st.id = STYLE_ID;
    st.textContent =
      ".m-dlg{position:fixed;inset:0;z-index:700;display:flex;align-items:center;justify-content:center;" +
        "padding:24px;background:rgba(0,0,0,.45);-webkit-backdrop-filter:blur(2px);backdrop-filter:blur(2px)}" +
      ".m-dlg-card{width:min(320px,100%);box-sizing:border-box;background:var(--mantle,#22252f);" +
        "border:1px solid var(--surface0,#333);border-radius:18px;padding:22px 20px 16px;" +
        "box-shadow:0 16px 48px rgba(0,0,0,.4);transform:scale(.95);opacity:0;" +
        "transition:transform .16s ease,opacity .16s ease}" +
      ".m-dlg.on .m-dlg-card{transform:scale(1);opacity:1}" +
      ".m-dlg-t{font-size:17px;font-weight:600;line-height:1.45;color:var(--text,#eee);text-align:center}" +
      ".m-dlg-m{margin-top:8px;font-size:14px;line-height:1.65;color:var(--subtext0,#9aa);word-break:break-word;text-align:center}" +
      ".m-dlg-in{display:block;width:100%;box-sizing:border-box;margin-top:14px;height:46px;" +
        "padding:0 14px;border-radius:12px;border:1px solid var(--surface1,#3a3d48);" +
        "background:var(--base,#181a20);color:var(--text,#eee);font:inherit;font-size:15px;outline:none}" +
      ".m-dlg-in:focus{border-color:var(--blue,#4f8cff)}" +
      ".m-dlg-area{height:150px;padding:12px 14px;line-height:1.5;resize:none;font-size:13.5px;" +
        "font-family:ui-monospace,Menlo,Consolas,monospace}" +
      ".m-dlg-bs{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:22px}" +
      ".m-dlg-bs.one{grid-template-columns:1fr}" +
      ".m-dlg-b{height:46px;border:0;border-radius:12px;font:inherit;font-size:15.5px;font-weight:600;" +
        "cursor:pointer;padding:0 14px}" +
      ".m-dlg-b.cancel{background:var(--surface0,#2c2f38);color:var(--subtext1,#c3c6cf)}" +
      ".m-dlg-b.go{background:var(--blue,#4f8cff);color:#fff}" +
      ".m-dlg-b.go.danger{background:#e05555;color:#fff}" +
      ".m-dlg-b:active{filter:brightness(.92)}" +
      ".m-tst{position:fixed;left:50%;bottom:96px;transform:translate(-50%,8px);z-index:720;" +
        "max-width:82vw;padding:11px 16px;border-radius:12px;background:rgba(20,22,28,.92);" +
        "color:#fff;font-size:13.5px;line-height:1.5;text-align:center;" +
        "box-shadow:0 8px 24px rgba(0,0,0,.35);opacity:0;transition:opacity .18s ease,transform .18s ease}" +
      ".m-tst.on{opacity:1;transform:translate(-50%,0)}";

    document.head.appendChild(st);
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  function open(cfg) {
    ensureStyle();
    return new Promise(function (resolve) {
      var wrap = document.createElement("div");
      wrap.className = "m-dlg";
      var kind = cfg.kind || "confirm";
      var danger = !!cfg.danger;
      var okTxt = cfg.ok || (kind === "info" ? "知道了" : "确定");
      var cancelTxt = cfg.cancel || "取消";
      wrap.innerHTML =
        '<div class="m-dlg-card" role="dialog" aria-modal="true">' +
          '<div class="m-dlg-t">' + esc(cfg.title || "") + '</div>' +
          (cfg.msg ? '<div class="m-dlg-m">' + esc(cfg.msg).replace(/\n/g, "<br>") + '</div>' : "") +
          (kind === "prompt"
            ? '<input class="m-dlg-in" type="text" maxlength="' + (cfg.maxlength || 40) +
              '" placeholder="' + esc(cfg.placeholder || "") + '" value="' + esc(cfg.value || "") + '">'
            : "") +
          (kind === "paste"
            ? '<textarea class="m-dlg-in m-dlg-area" placeholder="' + esc(cfg.placeholder || "") +
              '"></textarea>'
            : "") +
          '<div class="m-dlg-bs' + (kind === "info" ? " one" : "") + '">' +
            (kind === "info" ? "" : '<button type="button" class="m-dlg-b cancel">' + esc(cancelTxt) + '</button>') +
            '<button type="button" class="m-dlg-b go' + (danger ? " danger" : "") + '">' + esc(okTxt) + '</button>' +
          '</div>' +
        '</div>';
      document.documentElement.appendChild(wrap);
      requestAnimationFrame(function () { wrap.classList.add("on"); });

      var input = wrap.querySelector(".m-dlg-in");
      var done = false;
      function close(val) {
        if (done) return;
        done = true;
        wrap.classList.remove("on");
        setTimeout(function () { wrap.remove(); }, 180);
        resolve(val);
      }
      var cancelBtn = wrap.querySelector(".m-dlg-b.cancel");
      if (cancelBtn) cancelBtn.addEventListener("click", function () {
        close(kind === "prompt" || kind === "paste" ? null : false);
      });
      wrap.querySelector(".m-dlg-b.go").addEventListener("click", function () {
        if (kind === "prompt" || kind === "paste") {
          var v = (input.value || "").trim();
          if (!v) { input.focus(); return; }
          close(v);
        } else {
          close(true);
        }
      });
      wrap.addEventListener("click", function (e) {
        if (e.target === wrap) close(kind === "prompt" || kind === "paste" ? null : false);
      });
      if (input) {
        input.focus();
        input.addEventListener("keydown", function (e) {
          if (e.key === "Enter" && kind === "prompt") { e.preventDefault(); wrap.querySelector(".m-dlg-b.go").click(); }
          if (e.key === "Escape") { close(null); }
        });
      }
    });
  }

  // 统一 toast：导出页等地方一直调 window.toast，但之前根本没有这个全局函数，
  // 提示全是空调用（点了导入失败也没人知道）。这里补上一个能看见的。
  function mToast(msg) {
    ensureStyle();
    var old = document.querySelector(".m-tst");
    if (old) old.remove();
    var t = document.createElement("div");
    t.className = "m-tst";
    t.textContent = String(msg == null ? "" : msg);
    document.documentElement.appendChild(t);
    requestAnimationFrame(function () { t.classList.add("on"); });
    setTimeout(function () {
      t.classList.remove("on");
      setTimeout(function () { t.remove(); }, 220);
    }, 2200);
  }

  window.MYONLDialog = {
    confirm: function (o) {
      o = o || {};
      return open({ kind: "confirm", title: o.title, msg: o.msg, ok: o.ok, cancel: o.cancel, danger: o.danger });
    },
    prompt: function (o) {
      o = o || {};
      return open({ kind: "prompt", title: o.title, msg: o.msg, value: o.value,
        placeholder: o.placeholder, maxlength: o.maxlength, ok: o.ok, cancel: o.cancel });
    },
    paste: function (o) {
      o = o || {};
      return open({ kind: "paste", title: o.title, msg: o.msg,
        placeholder: o.placeholder, ok: o.ok, cancel: o.cancel });
    },
    info: function (o) {
      o = o || {};
      return open({ kind: "info", title: o.title, msg: o.msg, ok: o.ok });
    },
    toast: mToast
  };

  // 全局别名：不少页面（导出页、素材页）直接叫 window.toast，之前是空的。
  window.MYONLToast = mToast;
  if (typeof window.toast !== "function") window.toast = mToast;
})();
