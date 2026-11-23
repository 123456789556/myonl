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
    ["proj", "作品文件 .myonl", "剧本和素材打成一个文件，换手机、换电脑接着改", "⤓"],
    ["lib", "全部作品 .json", "所有作品合成一份，当总备份", "⤓"],
    ["hist", "版本历史", "改坏了退回上一版，不用重写", "↺"],
    ["imp", "导入别人的作品", "粘贴、选文件、网页版 html 三条路，都能导", "⤒"]
  ];

  // P212：这格原来叫「项目备份 .gal」，副题写「把这一份连素材打包」—— 但 __myonlExportGal
  // 只 download(p.text)，素材一个没带。用户换手机恢复出来一堆找不着图的作品，比没备份更上火。
  // .gal 本来就是纯剧本文本（导入他人文本还要靠它），所以另开一个真包：.myonl。
  function bare(n) { return String(n).replace(/\.[A-Za-z0-9]{1,5}$/, ""); }

  // 剧本里被点名的素材：@bg 教室 / @music 雨.mp3 这类指令的首个参数
  function refNames(text) {
    var out = {};
    String(text || "").split(/\r?\n/).forEach(function (ln) {
      var m = /^@(bg|cg|fg|music|sfx|voice|video)\s+([^\s#]+)/.exec(ln.replace(/^\s+/, ""));
      if (!m) return;
      var v = m[2];
      if (/^(无|none|off)$/i.test(v)) return;
      out[bare(v)] = 1;
    });
    return out;
  }

  // 只带这个作品真正用到的素材。一个都没点名（或名字对不上）就全带 —— 宁可多带，不能少带。
  function pickAssets(text, sp) {
    var want = refNames(text), named = Object.keys(want).length > 0;
    var out = { assets: {}, audio: {}, movies: {}, kinds: {} };
    [["assets", "image"], ["audio", "audio"], ["movies", "video"]].forEach(function (pair) {
      var k = pair[0], kind = pair[1], src = (sp && sp[k]) || {};
      Object.keys(src).forEach(function (n) {
        if (named && !want[bare(n)]) return;
        out[k][n] = src[n];
        out.kinds[n] = kind;
      });
    });
    return out;
  }

  // 落地：安卓壳走 __MYONLSave 桥（WebView 不理 a[download]），浏览器走 blob 下载
  function saveText(text, filename, mime) {
    var type = mime || "text/plain;charset=utf-8";
    var bridge = window.__MYONLSave;
    if (bridge && typeof bridge.save === "function") {
      try {
        var b64 = btoa(unescape(encodeURIComponent(text)));
        bridge.save(filename, type.split(";")[0], b64);
        if (window.toast) window.toast("已导出 " + filename);
        return;
      } catch (e) { /* 桥坏了退回浏览器 */ }
    }
    try {
      var a = document.createElement("a");
      a.href = URL.createObjectURL(new Blob([text], { type: type }));
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      setTimeout(function () { try { URL.revokeObjectURL(a.href); a.remove(); } catch (e2) {} }, 4000);
      if (window.toast) window.toast("已导出 " + filename + "（在下载里找）");
    } catch (e3) {
      if (window.toast) window.toast("这个环境不让直接下载", true);
    }
  }

  function currentProj() {
    var lib = (window.__myonlLib && window.__myonlLib.read) ? (window.__myonlLib.read() || {}) : {};
    var list = lib.projects || [], p = null;
    for (var i = 0; i < list.length; i++) if (list[i].name === lib.current) p = list[i];
    return p || list[0] || null;
  }

  // ---------- 电脑端：同一份作品、同一个包，只是料从后端拿 ----------
  // 桌面上没有 IndexedDB 素材库（gal_offline.js 一开局就 return 了），
  // 剧本在 games/、素材在 images|audio，只能问后端。这里不新增后端路由：
  // /api/script 给正文与路径，/api/assets 给清单，/api/asset/<类别>/<名字> 给字节。
  function deskOn() { return !window.__MYONL_OFFLINE; }

  function toDataURL(blob) {
    return new Promise(function (res, rej) {
      var fr = new FileReader();
      fr.onload = function () { res(String(fr.result || "")); };
      fr.onerror = function () { rej(new Error("读不出字节")); };
      fr.readAsDataURL(blob);
    });
  }

  function deskExport() {
    if (window.toast) window.toast("正在把剧本和素材打成一个文件…");
    var skipped = [];
    return fetch("/api/script", { cache: "no-store" }).then(function (r) {
      if (!r.ok) throw new Error("读剧本失败");
      return r.json();
    }).then(function (sc) {
      var text = String((sc && sc.text) || ""), path = String((sc && sc.path) || "");
      var name = bare((path.split(/[\\/]/).pop() || "作品"));
      return fetch("/api/assets", { cache: "no-store" }).then(function (r) {
        return r.ok ? r.json() : { assets: {} };
      }).then(function (a) {
        var as = (a && a.assets) || {}, want = refNames(text), named = Object.keys(want).length > 0;
        var out = { assets: {}, audio: {}, movies: {}, kinds: {} }, jobs = [];
        // 只取两类：图与音频。视频在桌面上是帧序列（images/videos/名字_001.png），
        // 拿单帧塞进包会被当成一张图，播出来是静帧 —— 不如不带，坦白说清楚。
        [["images", "assets", "image"], ["audio", "audio", "audio"]].forEach(function (t) {
          (as[t[0]] || []).forEach(function (n) {
            if (named && !want[bare(n)]) return;
            jobs.push({ cat: t[0], key: t[1], kind: t[2], name: n });
          });
        });
        return Promise.all(jobs.map(function (j) {
          var url = "/api/asset/" + j.cat + "/" + encodeURIComponent(j.name);
          return fetch(url, { cache: "no-store" }).then(function (r) {
            if (!r.ok) throw new Error("缺 " + j.name);
            return r.blob();
          }).then(toDataURL).then(function (u) {
            out[j.key][j.name] = u; out.kinds[j.name] = j.kind;
          }).catch(function () { skipped.push(j.name); });
        })).then(function () {
          var now = Math.round(Date.now() / 1000);
          var pack = {
            myonl: "proj", v: 1, name: name, text: text, ctime: now, mtime: now,
            assets: out.assets, audio: out.audio, movies: out.movies, kinds: out.kinds
          };
          saveText(JSON.stringify(pack), String(name).replace(/[\\/:*?"<>|]/g, "_") + ".myonl",
            "application/json;charset=utf-8");
          var na = Object.keys(out.assets).length, nu = Object.keys(out.audio).length;
          var parts = ["剧本"];
          if (na) parts.push(na + " 张图");
          if (nu) parts.push(nu + " 段音频");
          var tail = skipped.length ? ("；缺 " + skipped.length + " 个没能读出来：" + skipped.slice(0, 3).join("、")) : "";
          if (window.toast) window.toast("已导出「" + name + "」：" + parts.join("、") + tail, !!skipped.length);
        });
      });
    }).catch(function (e) {
      if (window.toast) window.toast("导出失败：" + (e && e.message ? e.message : e), true);
    });
  }

  // 电脑端导入 .myonl：不走 localStorage 库（那是离线内核的东西，桌面上写了等于没写）。
  // 桌面真正的库是磁盘：games/<名字>/script.gal + images|audio。所以落盘要问后端。
  // 复用三条现成路由，不新增后端接口：/api/new 建工程、/api/script 存正文、/api/import 存素材。
  function mimeExt(u, key) {
    if (/\.[A-Za-z0-9]{2,5}$/.test(String(key))) return "";
    // FileReader 给的是 `data:image/png;base64`，split 出来的头部带 `;base64` ——
    // 忘了剥它，整张表一个都对不上，扩展名推成空，后端直接 400「要加扩展名」。
    var m = String(u || "").split(",")[0].toLowerCase().replace(/;base64$/, "");
    var map = {
      "data:image/png": ".png", "data:image/jpeg": ".jpg", "data:image/webp": ".webp",
      "data:image/gif": ".gif",
      "data:audio/mpeg": ".mp3", "data:audio/mp3": ".mp3", "data:audio/ogg": ".ogg",
      "data:audio/wav": ".wav", "data:audio/x-wav": ".wav", "data:audio/webm": ".webm"
    };
    return map[m] || "";
  }

  function postJSON(url, body) {
    return fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    }).then(function (r) { return r.json().catch(function () { return {}; }); });
  }

  // 桌面工程名要过 engine/newgame.py 的白名单：只许中文/字母/数字/下划线、最长 20。
  // 手机端能叫「我的作品 v1.0（2）」，桌面目录不行 —— 不洗一遍就是连点 9 次 400。
  function safeName(n) {
    var s = String(n || "").replace(/[^0-9A-Za-z_\u4e00-\u9fff]/g, "_").replace(/^_+|_+$/g, "");
    return s.slice(0, 18) || "导入的作品";
  }

  function importProjDesk(obj) {
    var text = String(obj.text || "");
    if (!text.trim()) { if (window.toast) window.toast("这个包里没有剧本内容"); return; }
    var base = safeName(obj.name || "导入的作品");
    if (window.toast) window.toast("正在把作品放到本机工程里…");

    // 建新工程要落在「放所有作品的那个 games 目录」。
    // 不显式给 base_dir 的话，/api/new 会按当前工程推 —— 而当前工程可能已经是
    // games/xxx（上一步刚切过去），于是新工程被建成 games/xxx/games/yyy 这种套娃。
    var gamesDir = fetch("/api/config", { cache: "no-store" })
      .then(function (r) { return r.ok ? r.json() : {}; })
      .then(function (c) {
        var pr = String((c && c.project_root) || "");
        var m = pr.match(/^(.+?[\\/]games)[\\/]+/i);
        return m ? m[1] : "";
      }).catch(function () { return ""; });

    // 重名时 /api/new 会 400。换「名字_2」重试，不覆盖已有工程。
    // 这里用下划线而不是手机端的「（2）」：工程名要过 newgame 的白名单，全角括号不合法。
    var tries = [base].concat([2, 3, 4, 5, 6, 7, 8, 9].map(function (i) { return base + "_" + i; }));
    var name = "", root = "";
    function mk(gdir, i) {
      if (i >= tries.length) return Promise.resolve(null);
      var body = { name: tries[i] };
      if (gdir) body.base_dir = gdir;
      return postJSON("/api/new", body).then(function (r) {
        if (r && r.ok && r.path) { name = tries[i]; root = r.path; return r; }
        return mk(gdir, i + 1);
      });
    }
    return gamesDir.then(function (gdir) {
      return mk(gdir, 0);
    }).then(function (r) {
      if (!r) {
        if (window.toast) window.toast("建不了新工程，名字可能不合法：" + base, true);
        return;
      }
      var scriptPath = root.replace(/[\\/]+$/, "") + "/script.gal";
      return postJSON("/api/script", { text: text, path: scriptPath }).then(function (s) {
        if (!(s && s.ok)) throw new Error((s && s.message) || "剧本没写进去");
        var sets = [["assets", "images", "images"], ["audio", "audio", "audio"]];
        var jobs = [], why = [];
        sets.forEach(function (t) {
          Object.keys(obj[t[0]] || {}).forEach(function (k) {
            var u = obj[t[0]][k];
            if (!/^data:/.test(String(u)) || !String(u).includes(",")) { why.push(k + "：不是 dataURL"); return; }
            jobs.push({
              category: t[2],
              filename: k + mimeExt(u, k),
              data_b64: String(u).slice(String(u).indexOf(",") + 1),
              _k: k
            });
          });
        });
        return Promise.all(jobs.map(function (j) {
          return postJSON("/api/import", {
            category: j.category, filename: j.filename, data_b64: j.data_b64
          }).then(function (x) {
            if (!(x && x.ok)) why.push(j._k + "：" + ((x && x.message) || "后端没收"));
            return !!(x && x.ok);
          }).catch(function (e) { why.push(j._k + "：" + (e && e.message)); return false; });
        })).then(function (rs) {
          var okn = rs.filter(Boolean).length;
          var msg = "已导入「" + name + "」：" +
            (okn ? okn + " 个素材放进工程" : "剧本已就位（包里没有素材）") + "，刷新后可编辑";
          if (why.length) msg += "；" + why.length + " 个没进去：" + why.slice(0, 2).join("，");
          if (window.toast) window.toast(msg, !!why.length);
        });
      });
    }).catch(function (e) {
      if (window.toast) window.toast("导入失败：" + (e && e.message ? e.message : e), true);
    });
  }

  // 单个作品包：剧本原文 + 它用到的素材，一个文件。两端（手机 / 电脑）都按这个格式认。
  // P214：电脑端也能导出 —— 同一个格式，料从后端拿（deskExport）。
  function exportProj() {
    if (deskOn()) return deskExport();
    var p = currentProj();
    if (!p) { if (window.toast) window.toast("还没有作品可导出"); return; }
    var sp = (window.MYONLAssets && window.MYONLAssets.allSplit)
      ? window.MYONLAssets.allSplit() : Promise.resolve({ assets: {}, audio: {}, movies: {} });
    if (window.toast) window.toast("正在把剧本和素材打成一个文件…");
    sp.then(function (s) {
      var bag = pickAssets(p.text, s || {});
      var out = {
        myonl: "proj", v: 1, name: p.name, text: String(p.text || ""),
        ctime: p.ctime || 0, mtime: p.mtime || 0,
        assets: bag.assets, audio: bag.audio, movies: bag.movies, kinds: bag.kinds
      };
      var na = Object.keys(bag.assets).length, nu = Object.keys(bag.audio).length,
          nv = Object.keys(bag.movies).length;
      saveText(JSON.stringify(out), String(p.name).replace(/[\\/:*?"<>|]/g, "_") + ".myonl",
        "application/json;charset=utf-8");
      var parts = ["剧本"];
      if (na) parts.push(na + " 张图");
      if (nv) parts.push(nv + " 段视频");
      if (nu) parts.push(nu + " 段音频");
      if (window.toast) window.toast("已导出「" + p.name + "」：" + parts.join("、"));
    }).catch(function (e) {
      if (window.toast) window.toast("素材没读出来：" + (e && e.message ? e.message : e), true);
    });
  }

  // P257：卡片「⋯」里那两项「导出这个作品 / 复制一份」。
  // 导出以前只能导"当前作品"，而菜单点的可能是别的作品；这里按名字取，不切 current，
  // 不动用户正在编辑的那一份，也不产生任何"打开/切换"的副作用。
  function findProj(name) {
    var lib = localLib(), list = lib.projects || [];
    for (var i = 0; i < list.length; i++) if (list[i] && list[i].name === name) return list[i];
    return null;
  }

  function exportOne(name) {
    var p = findProj(name);
    if (!p) { if (window.toast) window.toast("找不到这个作品，刷新一下"); return; }
    var sp = (window.MYONLAssets && window.MYONLAssets.allSplit)
      ? window.MYONLAssets.allSplit() : Promise.resolve({ assets: {}, audio: {}, movies: {} });
    if (window.toast) window.toast("正在把「" + name + "」打成一个文件…");
    Promise.resolve(sp).then(function (s) {
      var bag = pickAssets(p.text, s || {});
      var out = {
        myonl: "proj", v: 1, name: p.name, text: String(p.text || ""),
        ctime: p.ctime || 0, mtime: p.mtime || 0,
        assets: bag.assets, audio: bag.audio, movies: bag.movies, kinds: bag.kinds
      };
      var na = Object.keys(bag.assets).length, nu = Object.keys(bag.audio).length,
          nv = Object.keys(bag.movies).length;
      saveText(JSON.stringify(out), String(p.name).replace(/[\\/:*?"<>|]/g, "_") + ".myonl",
        "application/json;charset=utf-8");
      var parts = ["剧本"];
      if (na) parts.push(na + " 张图");
      if (nv) parts.push(nv + " 段视频");
      if (nu) parts.push(nu + " 段音频");
      if (window.toast) window.toast("已导出「" + p.name + "」：" + parts.join("、"));
    }).catch(function (e) {
      if (window.toast) window.toast("素材没读出来：" + (e && e.message ? e.message : e), true);
    });
  }

  function dupOne(name) {
    var p = findProj(name);
    if (!p) { if (window.toast) window.toast("找不到这个作品，刷新一下"); return; }
    var cur = localLib(), taken = {};
    (cur.projects || []).forEach(function (x) { if (x) taken[x.name] = 1; });
    var base = name + " 副本", nm = base, i = 2;
    while (taken[nm]) { nm = base + " " + i; i++; }
    var now = Math.round(Date.now() / 1000);
    mergeProj([{ name: nm, folder: "dup" + Date.now().toString(36), text: String(p.text || ""),
                 ctime: now, mtime: now }]);
  }

  // 单作品包导入：素材先按原名进库，再建一条作品；同名不覆盖，改成「名字（2）」
  function importProj(obj) {
    var text = String(obj.text || "");
    if (!text.trim()) { if (window.toast) window.toast("这个包里没有剧本内容"); return; }
    var cur = localLib(), taken = {};
    (cur.projects || []).forEach(function (p) { if (p) taken[p.name] = 1; });
    var name = String(obj.name || "").trim() || "导入的作品", base = name, i = 2;
    while (taken[name]) { name = base + "（" + i + "）"; i++; }
    var now = Math.round(Date.now() / 1000);
    var proj = { name: name, folder: "imp" + Date.now().toString(36),
      text: text, ctime: obj.ctime || now, mtime: now };
    finishImport({
      projects: [proj].concat(cur.projects || []).slice(0, 200),
      current: name,
      assets: obj.assets, audio: obj.audio, movies: obj.movies, kinds: obj.kinds
    }, 1);
  }

  // 手机上弹不出系统文件选择器（实测），粘贴是唯一真走通的导入路；P210 起按内容认三种：作品库 .json / 单个作品 JSON / 纯剧本文本（.gal）。
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
    // P258 包版本门：现在只有 v1，但 v2 加字段后旧设备吞下去会静默丢 —— 认不出就明说，别装作导进来了
    if (obj && obj.myonl === "proj" && Number(obj.v || 1) > 1) { if (window.toast) window.toast("这个 .myonl 是更新版本（v" + obj.v + "）导出的，先用同版本打开"); return; }
    if (obj && obj.myonl === "proj") return deskOn() ? importProjDesk(obj) : importProj(obj);
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

  // 网页版 html：只有播放数据（window.__MYONL_PACK__），没有剧本原文 —— 把图/音/视频按原名还回素材库，作品本身不假装能还原。
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
      if (window.toast) window.toast("素材回来 " + ok + " 个（网页版里没有剧本原文，文字请用 .myonl 导）", true);
    });
  }

  function importPaste() {
    var D = window.MYONLDialog;
    if (!D || !D.paste) { if (window.toast) window.toast("导入面板没加载，刷新一下页面"); return; }
    D.paste({
      title: "粘贴导入",
      msg: ".myonl 作品文件、.gal 全文、作品库 .json、网页版 html 都能贴，会自动认出是哪种。同名作品不会覆盖。",
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
    // 安卓壳从 v1.2.52 起补了 onShowFileChooser，系统选择器能弹了，壳会打 __MYONL_CAN_PICK。
    // 老壳没有这个标记：那就别假装能选，直接说清楚怎么走。
    if (/Android/i.test(navigator.userAgent || "") && !window.__MYONL_CAN_PICK) {
      if (window.MYONLDialog) {
        window.MYONLDialog.info({
          title: "这个安装包还选不了文件",
          msg: "装的还是旧包，壳里少了「打开系统选择器」那一步。换成新包就能选；现在可以先走「粘贴内容」。"
        });
      } else if (window.toast) window.toast("旧包选不了文件，先用粘贴");
      return;
    }
    var inp = document.createElement("input");
    inp.type = "file";
    // 安卓的系统选择器按 MIME 过滤，按扩展名过滤会把 .gal/.myonl 全部灰掉；
    // 内容本来就靠 importText 自己认，这里放宽成 */*。
    inp.accept = /Android/i.test(navigator.userAgent || "") ? "*/*"
      : ".json,.myonl,.gal,.html,.txt,application/json,text/plain";
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
          '<span class="m-exp-b"><b>粘贴内容</b><span>.myonl、.gal、作品库 .json，整段贴，自动认</span></span>' +
          '<em>›</em></button>' +
        '<button type="button" class="m-exp-row" data-src="file">' +
          '<span class="m-exp-ic">📄</span>' +
          '<span class="m-exp-b"><b>选文件</b><span>电脑上直接挑；安卓系统窗弹不出，用上面那条</span></span>' +
          '<em>›</em></button>' +
        '<button type="button" class="m-exp-row" data-src="html">' +
          '<span class="m-exp-ic">🌐</span>' +
          '<span class="m-exp-b"><b>从网页版 html 取素材</b><span>图画声音放回素材库；剧本取不回</span></span>' +
          '<em>›</em></button>' +
        '<div class="m-set-note">同名不重复，本机已有的作品不会被盖掉。</div>' +
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
    else if (id === "proj") exportProj();
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
        '<div class="m-set-note">导出的东西都在本机，不上网。</div>' +
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

  // P249：设置页要一个能直接调「导入」的入口，把 openImport 也放出去。
  window.MYONLExport = { open: open, close: close, import: openImport, exportOne: exportOne, dupOne: dupOne };
})();
