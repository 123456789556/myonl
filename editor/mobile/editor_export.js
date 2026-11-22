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
    ["hist", "版本历史", "改坏了退回上一版，不用重写", "↺"],
    ["imp", "粘贴导入", "把 .json / .gal 的内容整段贴进来，手机上也能导", "⤒"]
  ];

  // 手机上弹不出系统文件选择器（实测），粘贴是唯一真能走通的导入路。
  // 导入别人那份时先按名字合并，别把本机已有的作品盖掉。
  function importPaste() {
    var D = window.MYONLDialog;
    if (!D || !D.paste) { if (window.toast) window.toast("导入面板没加载，刷新一下页面"); return; }
    D.paste({
      title: "粘贴导入",
      msg: "用记事本打开 .json / .gal，全选复制，整段贴进来。同名作品不会覆盖。",
      placeholder: '{"projects":[{"name":"..."}]}',
      ok: "导入"
    }).then(function (txt) {
      if (!txt) return;
      var lib;
      try { lib = JSON.parse(txt); } catch (e) {
        if (window.toast) window.toast("这段不是完整 JSON，可能少复制了尾巴");
        return;
      }
      if (!lib || !lib.projects || !lib.projects.length) {
        if (window.toast) window.toast("里面没有作品");
        return;
      }
      var cur = window.__myonlLib && window.__myonlLib.read ? window.__myonlLib.read() : null;
      if (cur && cur.projects && cur.projects.length) {
        var have = {};
        cur.projects.forEach(function (p) { have[p.name] = 1; });
        var add = lib.projects.filter(function (p) { return !have[p.name]; });
        if (!add.length) { if (window.toast) window.toast("这些作品本机都有了，没覆盖"); return; }
        // __myonlImportLib 是整表替换，所以合并后的完整列表交给它，本机老作品才留得住
        lib.projects = add.concat(cur.projects).slice(0, 200);
      }
      if (!window.__myonlImportLib) {
        if (window.toast) window.toast("导入模块没加载，刷新一下页面");
        return;
      }
      window.__myonlImportLib(lib).then(function (ok) {
        if (!ok) return;
        if (window.toast) window.toast("导入完成");
        setTimeout(function () { location.reload(); }, 900);
      });
    });
  }

  function call(id) {
    if (id === "pack" && window.__myonlExportPack) window.__myonlExportPack();
    else if (id === "apk" && window.__myonlExportApk) window.__myonlExportApk();
    else if (id === "gal" && window.__myonlExportGal) window.__myonlExportGal();
    else if (id === "lib" && window.__myonlExportLib) window.__myonlExportLib();
    else if (id === "hist") {
      if (window.MYONLSnapshotsUI && window.MYONLSnapshotsUI.open) window.MYONLSnapshotsUI.open();
      else if (window.toast) window.toast("版本历史没加载，刷新一下页面");
    } else if (id === "imp") importPaste();
    else if (window.toast) window.toast("这一项还没准备好，刷新一下页面");
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
      if (i === 5) sec = '<div class="m-exp-sec">从别处拿回来</div>';
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
        '<div class="m-set-note">导出的东西都在本机，不出网。网页版就是一份纯 html 文件，' +
        '里面脚本没压缩，开发者可以打开直接改；发给别人双击就玩。</div>' +
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
