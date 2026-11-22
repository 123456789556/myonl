/* P206：导出页 —— 一张自己的整页，不再往「界面设计中心」里插一条。
   用户看过那页：皮肤参数一大堆、真正要点的五个动作埋在底下，说「设计显然不大好」。

   这一页只答三个问题：这份有多大、要发给别人还是给自己留后路、点哪个。
   骨架跟垃圾箱/素材页同一套：左上 ‹ 回去，标题居中，正文一条条分组卡。 */
(function () {
  "use strict";

  var el = null;

  function fmtMB(n) { return (n / 1048576).toFixed(1) + " MB"; }

  // 体积先算出来摆着：点完才发现打不开是最糟的体验
  function estimate() {
    if (!window.MYONLAssets || !window.MYONLAssets.allSplit) return Promise.resolve(-1);
    return Promise.resolve(window.MYONLAssets.allSplit()).then(function (sp) {
      var o = Object.assign({}, (sp && sp.assets) || {}, (sp && sp.audio) || {});
      var n = 0;
      Object.keys(o).forEach(function (k) { n += String(o[k] || "").length; });
      return n;
    }).catch(function () { return -1; });
  }

  var ROWS = [
    ["pack", "网页版 HTML", "一个文件，浏览器打开就能玩，发给谁都能开", "⬇"],
    ["apk", "安装包 APK", "装到手机上像 App，图标点开就是游戏", "⬇"],
    ["gal", "项目备份 .gal", "把这一份连素材打包，换设备能接着改", "⤓"],
    ["lib", "全部作品 .json", "所有作品合成一份，当总备份", "⤓"],
    ["hist", "版本历史", "改坏了退回上一版，不用重写", "↺"]
  ];

  function call(id) {
    if (id === "pack" && window.__myonlExportPack) window.__myonlExportPack();
    else if (id === "apk" && window.__myonlExportApk) window.__myonlExportApk();
    else if (id === "gal" && window.__myonlExportGal) window.__myonlExportGal();
    else if (id === "lib" && window.__myonlExportLib) window.__myonlExportLib();
    else if (id === "hist") {
      if (window.MYONLSnapshotsUI && window.MYONLSnapshotsUI.open) window.MYONLSnapshotsUI.open();
      else if (window.toast) window.toast("版本历史没加载，刷新一下页面");
    } else if (window.toast) window.toast("这一项还没准备好，刷新一下页面");
  }

  function close() { if (el) { el.remove(); el = null; } }

  function paint(size) {
    var mb = size < 0 ? 0 : size / 1048576;
    var sizeTxt = size < 0 ? "体积待算" :
      ("现在约 " + fmtMB(size) + (mb > 30 ? " · 超过 30 MB，建议走 APK" : " · 能单文件发"));
    var rows = ROWS.map(function (r, i) {
      var sec = "";
      if (i === 0) sec = '<div class="m-exp-sec">发给别人</div>';
      if (i === 2) sec = '<div class="m-exp-sec">给自己留后路</div>';
      return sec +
        '<button type="button" class="m-exp-row" data-act="' + r[0] + '">' +
          '<span class="m-exp-ic">' + r[3] + '</span>' +
          '<span class="m-exp-b"><b>' + r[1] + '</b><span>' + r[2] + '</span></span>' +
          '<em>›</em></button>';
    }).join("");
    el.innerHTML =
      '<div class="m-bin-top">' +
        '<button type="button" class="m-back" id="mExpLeft" aria-label="返回">‹</button>' +
        '<span class="m-bin-title">导出</span>' +
        '<span></span>' +
      '</div>' +
      '<div class="m-exp-size" id="mExpSize">' + sizeTxt + '</div>' +
      '<div class="m-lib-body">' + rows +
        '<div class="m-set-note">导出的东西都在本机，不出网。给别人发的时候，' +
        '网页版最省事：对方拿到一个 html，双击就玩。</div>' +
      '</div>';
    el.querySelector("#mExpLeft").addEventListener("click", close);
    el.querySelectorAll("[data-act]").forEach(function (b) {
      b.addEventListener("click", function () { call(b.dataset.act); });
    });
  }

  function open() {
    if (el) { close(); return; }
    el = document.createElement("div");
    el.className = "m-bin-page m-exp-page";
    document.documentElement.appendChild(el);
    paint(-1);
    estimate().then(function (n) {
      var s = el && el.querySelector("#mExpSize");
      if (!s) return;
      var mb = n < 0 ? 0 : n / 1048576;
      s.textContent = n < 0 ? "体积待算" :
        ("现在约 " + fmtMB(n) + (mb > 30 ? " · 超过 30 MB，建议走 APK" : " · 能单文件发"));
    });
  }

  window.MYONLExport = { open: open, close: close };
})();
