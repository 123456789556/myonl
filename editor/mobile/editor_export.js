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
    ["imp", "导入别人的作品", "粘贴、选文件、网页版 html 三条路，都能导", "⤒"]
  ];

  // 手机上弹不出系统文件选择器（实测），粘贴是唯一真能走通的导入路。
  // P210：以前只认 {projects:[...]}，用户把之前导出的 .gal 贴进来只会看到「不是完整 JSON」。
  // 现在按内容认三种：作品库 .json / 单个作品 JSON / .gal 纯剧本文本。
  function importText(txt) {
    txt = String(txt || "").trim();
    if (!txt) return;
    if (/^<!doctype html|<html[\s>]/i.test(txt) || txt.indexOf("__MYONL_PACK__") >= 0) {
      return importHtml(txt);
    }
    var obj = null, jsonish = txt.charAt(0) === "{";
    if (jsonish) { try { obj = JSON.parse(txt); } catch (e) { obj = null; } }
    if (jsonish && !obj) {
      if (window.toast) window.toast("这不是完整的 JSON，看下是不是没复制全");
      return;
    }
    if (obj && Array.isArray(obj.projects)) return mergeLib(obj);
    if (obj && (obj.title || obj.scenes || obj.lines)) return importOne(obj.title || null, JSON.stringify(obj, null, 1));
    // 剩下的当剧本文本：@bg 教室 / 小明：你好 这种，就是 .gal 里的内容
    return importOne(null, txt);
  }

  function importOne(name, text) {
    var D = window.MYONLDialog;
    var asked = name
      ? Promise.resolve(name)
      : (D && D.prompt ? D.prompt({
          title: "给这个作品起个名",
          msg: ".gal 里只存了剧本，没存作品名。起一个，列表里好认。",
          placeholder: "导入的作品", value: "导入的作品", maxlength: 20, ok: "导入"
        }) : Promise.resolve("导入的作品"));
    return asked.then(function (nm) {
      nm = String(nm || "").trim();
      if (!nm) return;
      var now = Math.round(Date.now() / 1000);
      mergeProj([{ name: nm, folder: "imp" + Date.now().toString(36),
        text: String(text || ""), ctime: now, mtime: now }]);
    });
  }

  function localLib() {
    return (window.__myonlLib && window.__myonlLib.read) ? (window.__myonlLib.read() || {}) : {};
  }

  function finishImport(lib, n) {
    if (!window.__myonlImportLib) { if (window.toast) window.toast("导入模块没加载，刷新一下页面"); return; }
    window.__myonlImportLib(lib).then(function (ok) {
      if (!ok) return;
      if (window.toast) window.toast("导入完成：" + n + " 个作品");
      setTimeout(function () { location.reload(); }, 900);
    });
  }

  function mergeProj(add) {
    var cur = localLib();
    var have = {};
    (cur.projects || []).forEach(function (p) { have[p.name] = 1; });
    add = add.filter(function (p) { return p && p.name && !have[p.name]; });
    if (!add.length) { if (window.toast) window.toast("这些作品本机都有了，没覆盖"); return; }
    // __myonlImportLib 是整表替换，所以合并后的完整列表交给它，本机老作品才留得住
    finishImport({ projects: add.concat(cur.projects || []).slice(0, 200) }, add.length);
  }

  function mergeLib(obj) {
    var list = (obj.projects || []).filter(function (p) { return p && p.name; }).map(function (p) {
      p.text = String(p.text || "");
      if (!p.folder) p.folder = "imp" + Date.now().toString(36) + Math.random().toString(36).slice(2, 5);
      return p;
    });
    if (!list.length) { if (window.toast) window.toast("这份文件里没有作品"); return; }
    var cur = localLib();
    var have = {};
    (cur.projects || []).forEach(function (p) { have[p.name] = 1; });
    list = list.filter(function (p) { return !have[p.name]; });
    if (!list.length) { if (window.toast) window.toast("这些作品本机都有了，没覆盖"); return; }
    finishImport({
      projects: list.concat(cur.projects || []).slice(0, 200),
      assets: obj.assets, audio: obj.audio, movies: obj.movies, kinds: obj.kinds
    }, list.length);
  }

  // 网页版 html：里面只有播放用的数据（window.__MYONL_PACK__），剧本原文没存。
  // 能做的是把图/音/视频按原名还回素材库，作品本身不假装能还原。
  function importHtml(txt) {
    var i = txt.indexOf("__MYONL_PACK__");
    var start = i < 0 ? -1 : txt.indexOf("{", i);
    if (start < 0) { if (window.toast) window.toast("这份网页版里没找到作品数据"); return; }
    var dep = 0, inStr = false, esc = false, end = -1;
    for (var k = start; k < txt.length; k++) {
      var c = txt.charAt(k);
      if (inStr) {
        if (esc) esc = false;
        else if (c === "\\") esc = true;
        else if (c === '"') inStr = false;
        continue;
      }
      if (c === '"') inStr = true;
      else if (c === "{") dep++;
      else if (c === "}") { dep--; if (dep === 0) { end = k + 1; break; } }
    }
    if (end < 0) { if (window.toast) window.toast("数据不完整，可能没复制全"); return; }
    var pack;
    try { pack = JSON.parse(txt.slice(start, end)); } catch (e) {
      if (window.toast) window.toast("这份网页版的数据读不出来");
      return;
    }
    var na = Object.keys(pack.assets || {}).length + Object.keys(pack.audio || {}).length
      + Object.keys(pack.movies || {}).length;
    if (!na) { if (window.toast) window.toast("这份网页版里没带素材，只剩剧本文本，导不回来"); return; }
    if (!window.MYONLAssets || !window.MYONLAssets.restore) {
      if (window.toast) window.toast("素材层没加载，刷新一下页面");
      return;
    }
    var all = {}, kinds = {};
    Object.keys(pack.audio || {}).forEach(function (k) { all[k] = pack.audio[k]; kinds[k] = "audio"; });
    Object.keys(pack.movies || {}).forEach(function (k) { all[k] = pack.movies[k]; kinds[k] = "video"; });
    Object.keys(pack.assets || {}).forEach(function (k) { if (all[k] === undefined) { all[k] = pack.assets[k]; kinds[k] = "image"; } });
    if (window.toast) window.toast("正在把 " + na + " 个素材放回去…");
    window.MYONLAssets.restore(all, kinds).then(function (r) {
      var ok = (r && r.ok) || 0;
      if (window.toast) window.toast("素材回来 " + ok + " 个（网页版里没有剧本原文，文字请用 .gal 导）", true);
    });
  }

  function importPaste() {
    var D = window.MYONLDialog;
    if (!D || !D.paste) { if (window.toast) window.toast("导入面板没加载，刷新一下页面"); return; }
    D.paste({
      title: "粘贴导入",
      msg: ".gal 全文、作品库 .json、网页版 html 都能贴，会自动认出是哪种。同名作品不会覆盖。",
      placeholder: "@bg 教室\n小明：你好\n—— 或者贴 {\"projects\":[...]}",
      ok: "导入"
    }).then(function (txt) {
      if (!txt) return;
      importText(txt);
    });
  }

  // P210：导入不再只有「粘贴」一条 —— 用户说「只有一个选项很局促」。
  // 整页列三个来源，哪个环境能走通就用哪个。
  var impEl = null;

  function closeImport() { if (impEl) { impEl.remove(); impEl = null; } }

  function pickFile() {
    if (/Android/i.test(navigator.userAgent || "")) {
      if (window.MYONLDialog) {
        window.MYONLDialog.info({
          title: "安卓选不了文件",
          msg: "系统选文件的那个窗被 WebView 挡住了。走「粘贴内容」：文件用记事本打开，全选复制再贴进来。"
        });
      } else if (window.toast) window.toast("安卓上选不了文件，用粘贴");
      return;
    }
    var inp = document.createElement("input");
    inp.type = "file";
    inp.accept = ".json,.gal,.html,.txt,application/json,text/plain";
    inp.style.display = "none";
    document.body.appendChild(inp);
    inp.addEventListener("change", function () {
      var f = (inp.files || [])[0];
      inp.remove();
      if (!f) return;
      var rd = new FileReader();
      rd.onload = function () { importText(rd.result); };
      rd.onerror = function () { if (window.toast) window.toast("这个文件读不出来"); };
      rd.readAsText(f);
    });
    inp.click();
  }

  function pick(src) {
    if (src === "paste") return importPaste();
    if (src === "html") {
      var D = window.MYONLDialog;
      if (!D || !D.paste) { if (window.toast) window.toast("面板没加载，刷新一下页面"); return; }
      return D.paste({
        title: "贴网页版 html",
        msg: "用记事本打开导出的 .html，全选复制整份贴进来。只把里面的图、音频、视频按原名取回素材库。",
        placeholder: "<!DOCTYPE html> …",
        ok: "取回素材"
      }).then(function (t) { if (t) importHtml(t); });
    }
    return pickFile();
  }

  function openImport() {
    if (impEl) { closeImport(); return; }
    impEl = document.createElement("div");
    impEl.className = "m-bin-page m-exp-page";
    impEl.innerHTML =
      '<div class="m-bin-top">' +
        '<button type="button" class="m-back" id="mImpLeft" aria-label="返回">‹</button>' +
        '<span class="m-bin-title">导入</span>' +
        '<span></span>' +
      '</div>' +
      '<div class="m-lib-body">' +
        '<div class="m-exp-sec">三种来源，用能走通的那个</div>' +
        '<button type="button" class="m-exp-row" data-src="paste">' +
          '<span class="m-exp-ic">⤒</span>' +
          '<span class="m-exp-b"><b>粘贴内容</b><span>.gal 全文、作品库 .json，整段贴，自动认</span></span>' +
          '<em>›</em></button>' +
        '<button type="button" class="m-exp-row" data-src="file">' +
          '<span class="m-exp-ic">📄</span>' +
          '<span class="m-exp-b"><b>选文件</b><span>电脑上直接挑；安卓系统窗弹不出，用上面那条</span></span>' +
          '<em>›</em></button>' +
        '<button type="button" class="m-exp-row" data-src="html">' +
          '<span class="m-exp-ic">🌐</span>' +
          '<span class="m-exp-b"><b>从网页版 html 取素材</b><span>图画声音放回素材库；剧本取不回</span></span>' +
          '<em>›</em></button>' +
        '<div class="m-set-note">同一份东西贴两遍不会重复：名字一样就跳过，本机已有的作品不会被盖掉。</div>' +
      '</div>';
    document.documentElement.appendChild(impEl);
    impEl.querySelector("#mImpLeft").addEventListener("click", closeImport);
    impEl.querySelectorAll("[data-src]").forEach(function (b) {
      b.addEventListener("click", function () { pick(b.dataset.src); });
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
    } else if (id === "imp") openImport();
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
