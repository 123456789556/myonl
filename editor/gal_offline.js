/* ============================================================
   MYONL 离线内核 —— 手机上没有 Python，编辑器也要能编游戏
   ------------------------------------------------------------
   电脑端跑的是 engine/editor.py（Python）。手机装不了 Python，
   但编辑器前端几十处 fetch 都指向 /api/*，没有后端就一片 404，
   首屏直接卡在引导页。

   这里的做法不是把 engine/parser.py 搬成 JS（那等于把内核换一遍，
   规则有 @if 缩进块 / @choice 缩进选项 / @show 八种参数 / @anim 22 种
   easing / @include 递归，搬错了就是静默出错）。而是把编辑器真正
   用到的那些 /api/* 在浏览器里实现一份：

     作品库  → localStorage（一个作品 = 一份 script.gal 文本）
     保存    → 落到 localStorage，另留一份能导出的纯文本
     素材    → 手机上先给空清单，不影响写剧本
     校验    → 本地只做「能不能存」级别的最小检查

   为什么能这么省：editor_scene.js 的 saveCurrent() 本来就是
   「纯文本补丁」——只改 @bg/@music/@video/@show/台词/@choice/@jump，
   其它行（@if/@anim/@include/#注释/未知指令）原样留在原地。
   不动即不坏，所以场景编辑天然不会把复杂指令拍平。

   入口约定：只有当 /api/version 不是 JSON 时才启用（见下方同步探测）。
   电脑端带着 Python 后端时，本文件加载了也立刻 return，不干扰。
   ============================================================ */
(function () {
  "use strict";

  // ---------- 1. 探测：真的有后端吗 ----------
  // 两种情况不用问就知道没有后端，直接判离线：
  //   file://           —— 手机上双击打开单文件
  //   appassets.android —— APK 里的 WebView 资源域名
  // 这样可以少掉一次必然失败的请求（file:// 下还会在控制台刷 CORS 红字）。
  // 剩下的 http(s) 情况才用同步 XHR 问一次 /api/version：
  // Python 后端回 JSON，静态服务回 404。
  var offline = false;
  if (/^(file|content):/i.test(location.protocol) ||
      /appassets\.androidplatform\.net/i.test(location.hostname || "")) {
    offline = true;
  } else {
    try {
      var probe = new XMLHttpRequest();
      probe.open("GET", "/api/version", false);
      probe.send(null);
      var ctype = String(probe.getResponseHeader("content-type") || "").toLowerCase();
      offline = !(probe.status === 200 && ctype.indexOf("json") >= 0);
    } catch (e) {
      offline = true;
    }
  }
  if (!offline) return;
  window.__MYONL_OFFLINE = true;

  // ---------- 2. 作品库 ----------
  // 结构：{ current: 作品名, projects: [{name, text, ctime, mtime}] }
  // 没有素材字段——手机上先不做素材库，免得 localStorage 被 base64 撑爆。
  var LIB_KEY = "myonl:off:lib:v1";
  var memLib = null;   // 隐私模式禁用 localStorage 时的兜底

  function blankLib() {
    var t = starterText();
    return { current: "我的第一个游戏", projects: [{ name: "我的第一个游戏", text: t, ctime: now(), mtime: now() }] };
  }
  function now() { return Math.round(Date.now() / 1000); }

  function readLib() {
    if (memLib) return memLib;
    var raw = "";
    try {
      raw = localStorage.getItem(LIB_KEY) || "";
      if (raw) {
        try {
          var lib = JSON.parse(raw);
          if (lib && lib.projects && lib.projects.length) return lib;
        } catch (pe) {
          // P130：坏 JSON 原来直接落进下面的"重建空白并覆写"——
          // 用户的作品就在那一瞬间被顶掉了，而且他看到的只是"我的作品变空了"。
          // 先把原始串原样留一份，再重建；留不住也要告诉他去哪找。
          keepBroken(raw);
        }
      }
    } catch (e) { /* localStorage 被禁用 */ }
    memLib = blankLib();
    writeLib(memLib);
    return memLib;
  }
  // 把读坏的原始数据另存一份，绝不就地丢弃
  function keepBroken(raw) {
    if (!raw) return;
    var key = LIB_KEY + ":broken:" + now();
    try {
      localStorage.setItem(key, raw);
      toast("本地作品库读坏了，原数据已另存一份（键 " + key + "），先别关页面，导出一份备份");
      return;
    } catch (e) { /* 满了，落到 IndexedDB */ }
    try {
      dbRun("readwrite", function (st) { st.put(raw, "lib-broken:" + now()); })
        .then(function () {
          toast("本地作品库读坏了，原数据已存进本机素材库，先导出一份备份再继续");
        })
        .catch(function () {
          toast("本地作品库读坏了，原始数据没留住。别新建作品，先找我要恢复办法");
        });
    } catch (e2) { toast("本地作品库读坏了，原始数据没留住"); }
  }
  // 按"当前作品优先、其次最近改的"挑出要留下的，保持原有顺序。
  // 原来这里是 sort 完 slice(0,8) —— 列表顺序被打乱，而且砍掉哪些没说。
  function trimLib(lib, keep) {
    var cur = lib.current;
    var order = lib.projects.map(function (p, i) {
      return { i: i, t: (p.mtime || 0), cur: p.name === cur ? 1 : 0 };
    }).sort(function (a, b) { return (b.cur - a.cur) || (b.t - a.t); });
    var keepIdx = {};
    order.slice(0, keep).forEach(function (o) { keepIdx[o.i] = 1; });
    var kept = [], dropped = [];
    lib.projects.forEach(function (p, i) { (keepIdx[i] ? kept : dropped).push(p); });
    lib.projects = kept;
    return dropped;
  }
  function writeLib(lib) {
    memLib = lib;
    try { localStorage.setItem(LIB_KEY, JSON.stringify(lib)); return; }
    catch (e) { /* 超配额 */ }
    // 超配额：保住当前作品 + 最近改的 7 个，其余停用。
    // 但"停用"不等于"扔掉"——先塞进 IndexedDB，塞不进去也要当用户的面说清楚。
    var dropped = trimLib(lib, 8);
    var ok = false;
    try { localStorage.setItem(LIB_KEY, JSON.stringify(lib)); ok = true; } catch (e2) { }
    if (!ok) {
      // 连 8 个都写不下：不再继续砍。内存里留着，提示用户立刻导出。
      toast("本机存储已满，这次没写进去。先导出一份备份，再删掉些旧作品");
      return;
    }
    var n = dropped.length;
    if (!n) return;
    var saved = false;
    try {
      dbRun("readwrite", function (st) {
        dropped.forEach(function (p, i) {
          st.put(JSON.stringify(p), "lib-trim:" + now() + ":" + p.name);
        });
      }).then(function () { saved = true; }).catch(function () { });
    } catch (e3) { }
    toast("本机存储不够，已把最旧的 " + n + " 个作品从列表拿掉（" +
          (saved ? "原文已存进本机素材库" : "原文没能备份") +
          "）。导出当前作品后就腾出空间了");
  }
  function curProject(lib) {
    lib = lib || readLib();
    for (var i = 0; i < lib.projects.length; i++) {
      if (lib.projects[i].name === lib.current) return lib.projects[i];
    }
    return lib.projects[0];
  }
  function findProject(lib, name) {
    for (var i = 0; i < lib.projects.length; i++) if (lib.projects[i].name === name) return lib.projects[i];
    return null;
  }

  // 新作品给一句能立刻改的旁白，跟电脑端「新建游戏 = hello 模板」一致
  function starterText() {
    return "# 在这里写你的第一句台词，改完点右上角保存\n@ hello world!\n";
  }

  function toast(msg, isErr) {
    try {
      if (window.__editor && window.__editor.toast) { window.__editor.toast(msg, isErr); return; }
    } catch (e) { /* ignore */ }
    var el = document.createElement("div");
    el.textContent = msg;
    el.style.cssText = "position:fixed;left:50%;bottom:96px;transform:translateX(-50%);z-index:99999;" +
      "padding:10px 16px;border-radius:12px;font-size:14px;color:#fff;" +
      "background:" + (isErr ? "#c0392b" : "rgba(20,24,36,.92)") + ";box-shadow:0 6px 24px rgba(0,0,0,.35)";
    document.body.appendChild(el);
    setTimeout(function () { try { el.remove(); } catch (e) {} }, 2200);
  }

  // ---------- 2b. 素材库（IndexedDB） ----------
  // 为什么不能用 localStorage 存图：它总共 5MB 出头，手机拍的一张图转 base64 就三四兆，
  // 两张直接爆，然后整段作品库被挤坏。IndexedDB 在安卓 WebView 里通常几百 MB，
  // 图放这里才装得下、也不会拖累文案。
  //
  // 名字索引另存一份在 localStorage：/api/assets 是同步接口，得能立刻答上「有哪些图」，
  // 真图才走异步的 IndexedDB。
  var IDX_KEY = "myonl:assets:index:v1";
  var ADB = "myonl-assets";
  var ASTORE = "files";

  function idxRead() {
    try {
      var a = JSON.parse(localStorage.getItem(IDX_KEY) || "[]");
      return Array.isArray(a) ? a : [];
    } catch (e) { return []; }
  }
  function idxWrite(a) {
    try { localStorage.setItem(IDX_KEY, JSON.stringify(a)); } catch (e) {}
  }

  // 素材分两类，处置方式不一样：图压过再存、进成品当画面；音频原样存、进成品当 BGM / 音效。
  // 类型另存一份（名字索引里只有名字），这样同步的 /api/assets 也能把两类分开答。
  var KIND_KEY = "myonl:assets:kind:v1";
  function kindRead() {
    try {
      var o = JSON.parse(localStorage.getItem(KIND_KEY) || "{}");
      return (o && typeof o === "object") ? o : {};
    } catch (e) { return {}; }
  }
  function kindWrite(o) {
    try { localStorage.setItem(KIND_KEY, JSON.stringify(o || {})); } catch (e) {}
  }
  function kindOf(name) {
    var k = kindRead()[name];
    return k === "audio" || k === "video" ? k : "image";
  }

  function dbOpen() {
    return new Promise(function (res, rej) {
      if (!window.indexedDB) { rej(new Error("这个浏览器没有 IndexedDB")); return; }
      var req = window.indexedDB.open(ADB, 1);
      req.onupgradeneeded = function () {
        var db = req.result;
        if (!db.objectStoreNames.contains(ASTORE)) db.createObjectStore(ASTORE);
      };
      req.onsuccess = function () { res(req.result); };
      req.onerror = function () { rej(req.error || new Error("打不开素材库")); };
    });
  }
  function dbRun(mode, fn) {
    return dbOpen().then(function (db) {
      return new Promise(function (res, rej) {
        var tx = db.transaction(ASTORE, mode);
        var st = tx.objectStore(ASTORE);
        var out;
        var r = fn(st);
        if (r) r.onsuccess = function () { out = r.result; };
        tx.oncomplete = function () { res(out); };
        tx.onerror = function () { rej(tx.error || new Error("素材库写入失败")); };
      });
    });
  }

  // 压一下再存：手机相册原图动辄 4000px / 6MB，直接塞进作品，
  // 导出成 HTML 会变成几十兆，发给谁都打不开。
  // 最长边 1280、jpg 0.82 —— 视觉小说满屏看也够，一张大概 100~200KB。
  var MAX_SIDE = 1280;
  function shrinkImage(file) {
    return new Promise(function (res, rej) {
      var fr = new FileReader();
      fr.onload = function () {
        var img = new Image();
        img.onload = function () {
          var w = img.naturalWidth || img.width;
          var h = img.naturalHeight || img.height;
          var m = Math.max(w, h);
          if (m > MAX_SIDE) { var k = MAX_SIDE / m; w = Math.round(w * k); h = Math.round(h * k); }
          var cv = document.createElement("canvas");
          cv.width = w; cv.height = h;
          var cx = cv.getContext("2d");
          // 透明底（png/webp）铺黑：播放器舞台本来就是深色，白底会在黑边里炸出来
          var isPng = /png|webp/i.test(file.type || "");
          if (!isPng) { cx.fillStyle = "#000"; cx.fillRect(0, 0, w, h); }
          cx.drawImage(img, 0, 0, w, h);
          var out = isPng ? cv.toDataURL("image/png") : cv.toDataURL("image/jpeg", 0.82);
          res({ dataUrl: out, w: w, h: h, type: isPng ? "image/png" : "image/jpeg" });
        };
        img.onerror = function () { rej(new Error("这张图读不出来（可能不是图片）")); };
        img.src = fr.result;
      };
      fr.onerror = function () { rej(new Error("读文件失败")); };
      fr.readAsDataURL(file);
    });
  }

  function baseName(file) {
    var n = String(file.name || "图片").replace(/\.[^.]+$/, "").trim() || "图片";
    return n.slice(0, 40);
  }
  function uniqueName(want, taken) {
    if (taken.indexOf(want) < 0) return want;
    var i = 2;
    while (taken.indexOf(want + "_" + i) >= 0) i++;
    return want + "_" + i;
  }

  // 音频不压：mp3 / ogg / m4a 本来就是有损或用专门编码压过的，
  // 再转一道只有掉质量、不掉体积。原样转 dataURL 存着，成品里 base64 直接喂给 new Audio。
  function audioDataUrl(file) {
    return new Promise(function (res, rej) {
      var fr = new FileReader();
      fr.onload = function () { res(String(fr.result || "")); };
      fr.onerror = function () { rej(new Error("这段音频读不出来")); };
      fr.readAsDataURL(file);
    });
  }

  // 视频同样不压、不转码、不抽帧：mp4 / webm / mov 已经是专门编码压过的，
  // 再走一道 canvas 或重编码只会掉质量；原样转 dataURL 存着，成品里直接喂给 <video>。
  function videoDataUrl(file) {
    return new Promise(function (res, rej) {
      var fr = new FileReader();
      fr.onload = function () { res(String(fr.result || "")); };
      fr.onerror = function () { rej(new Error("这段视频读不出来")); };
      fr.readAsDataURL(file);
    });
  }

  // 落库一条素材：起不重名的名字、写名字索引 / 类型索引、存进 IndexedDB。
  // add()（选文件、拖进来）和 importShared()（别的 App 分享进来）共用这一套，
  // 避免两条链路对重名、类型、落库的处理出现分叉。
  function persistAsset(wantName, kind, dataUrl, taken, kinds) {
    var name = uniqueName(wantName, taken);
    taken.push(name);
    kinds[name] = kind;
    idxWrite(taken); kindWrite(kinds);
    return dbRun("readwrite", function (st) {
      return st.put({ dataUrl: dataUrl, kind: kind }, name);
    }).then(function () { return name; });
  }

  function dataUrlToResponse(dataUrl) {
    var comma = dataUrl.indexOf(",");
    var meta = dataUrl.slice(5, comma);          // image/png;base64
    var mime = (meta.split(";")[0] || "image/png").trim();
    var body = dataUrl.slice(comma + 1);
    var bin;
    if (/;base64/i.test(meta)) {
      var raws = atob(body);
      bin = new Uint8Array(raws.length);
      for (var i = 0; i < raws.length; i++) bin[i] = raws.charCodeAt(i);
    } else {
      var dec = decodeURIComponent(body);
      bin = new Uint8Array(dec.length);
      for (var j = 0; j < dec.length; j++) bin[j] = dec.charCodeAt(j);
    }
    return new Response(bin, { status: 200, headers: { "Content-Type": mime } });
  }

  window.MYONLAssets = {
    list: function () { return idxRead(); },
    kindOf: kindOf,
    // 加一组文件，返回真的加进去的名字（重名会自动加 _2）
    // 图片：压到最长边 1280；音频 / 视频：原样存；其它类型一律不收（成品里用不上，收了只是白占空间）
    add: function (files, onEach) {
      var list = Array.prototype.slice.call(files || []);
      var taken = idxRead();
      var kinds = kindRead();
      var added = [];
      return list.reduce(function (chain, f) {
        return chain.then(function () {
          var t = String(f.type || "");
          var isImg = /^image\//i.test(t);
          var isAud = /^audio\//i.test(t);
          var isVid = /^video\//i.test(t);
          if (!isImg && !isAud && !isVid) {
            // 跳过也要回一次，否则多选里混进一个不收的类型，进度条就永远卡在"导入中"
            if (onEach) onEach(null, added.length, list.length, new Error("只收图片、音频和视频"));
            return null;
          }
          if (isVid && (f.size || 0) > MAX_BYTES) {
            var bigErr = new Error("这段视频超过 24 MB，先在手机里剪短或压一下再导");
            if (onEach) onEach(null, added.length, list.length, bigErr);
            return null;
          }
          var step = isImg
            ? shrinkImage(f).then(function (r) { return { dataUrl: r.dataUrl, kind: "image" }; })
            : isVid
              ? videoDataUrl(f).then(function (u) { return { dataUrl: u, kind: "video" }; })
              : audioDataUrl(f).then(function (u) { return { dataUrl: u, kind: "audio" }; });
          return step.then(function (r) {
            return persistAsset(baseName(f), r.kind, r.dataUrl, taken, kinds).then(function (name) {
              added.push(name);
              if (onEach) onEach(name, added.length, list.length);
            });
          });
        }).catch(function (e) {
          if (onEach) onEach(null, added.length, list.length, e);
        });
      }, Promise.resolve()).then(function () { return added; });
    },
    get: function (name) {
      return dbRun("readonly", function (st) { return st.get(name); });
    },
    remove: function (name) {
      return dbRun("readwrite", function (st) { return st.delete(name); }).then(function () {
        idxWrite(idxRead().filter(function (n) { return n !== name; }));
        var k = kindRead(); delete k[name]; kindWrite(k);
      });
    },
    // 导出用：{名字: dataURL}，一次全取（图片 / 音频合在一起，调用方自己分）
    all: function () {
      var names = idxRead();
      var map = {};
      return names.reduce(function (chain, n) {
        return chain.then(function () {
          return dbRun("readonly", function (st) { return st.get(n); }).then(function (v) {
            if (v && v.dataUrl) map[n] = v.dataUrl;
          });
        });
      }, Promise.resolve()).then(function () { return map; });
    },
    // 导出时直接能用的三份：画面素材 / 声音素材 / 真视频文件
    // 视频同时留在 assets（播放器只认名字，分桶靠 kind），movies 单独给打包器直接用。
    allSplit: function () {
      var names = idxRead();
      var kinds = kindRead();
      var out = { assets: {}, audio: {}, movies: {} };
      return names.reduce(function (chain, n) {
        return chain.then(function () {
          return dbRun("readonly", function (st) { return st.get(n); }).then(function (v) {
            if (!v || !v.dataUrl) return;
            if (kinds[n] === "audio") out.audio[n] = v.dataUrl;
            else if (kinds[n] === "video") {
              out.assets[n] = v.dataUrl;
              out.movies[n] = v.dataUrl;
            }
            else out.assets[n] = v.dataUrl;
          });
        });
      }, Promise.resolve()).then(function () { return out; });
    },
    // 别的 App 分享进来：SW 把 multipart 里的文件暂存在 inbox:<时间戳>:<序号> 键下，
    // 值形状 { name, type, blob, ts }。这里把它们搬进正式素材，走 add() 同一套落库逻辑，
    // 成功后删掉 inbox 键；没有 inbox 记录就 resolve 空数组；任何异常都吞掉返回 []，
    // 不许抛到页面顶层（index.html 只 .then/.catch 收名字数组）。
    importShared: function () {
      var self = this;
      return new Promise(function (resolve) {
        var names = [];
        try {
          if (!window.indexedDB) { resolve([]); return; }
          dbRun("readonly", function (st) { return st.getAllKeys(); }).then(function (keys) {
            var inbox = (keys || []).filter(function (k) { return String(k).indexOf("inbox:") === 0; });
            if (!inbox.length) { resolve([]); return; }
            return inbox.reduce(function (chain, key) {
              return chain.then(function () {
                return dbRun("readonly", function (st) { return st.get(key); }).then(function (rec) {
                  if (!rec || !rec.blob) return null;
                  var file;
                  try {
                    file = new File([rec.blob], String(rec.name || ("分享_" + Date.now())),
                      { type: rec.type || "application/octet-stream" });
                  } catch (e) { return null; }
                  return self.add([file]).then(function (added) {
                    if (added && added.length) names.push(added[0]);
                    return dbRun("readwrite", function (st) { return st.delete(key); });
                  }).catch(function () { /* 这条没存上，inbox 键留着，下次进来再试 */ });
                });
              });
            }, Promise.resolve()).then(function () { resolve(names); });
          }).catch(function () { resolve([]); });
        } catch (e) { resolve([]); }
      });
    },
    // 恢复备份用：**按原名写回，不再压缩、不改名**。
    // 名字就是剧本里 @bg / @音乐 后面那个词，改名等于把整部作品的图全变成缺图——
    // 所以这里绝不能走 add()（它会 uniqueName + 重新压一遍）。
    restore: function (map, kinds) {
      var names = idxRead();
      var kd = kindRead();
      var list = Object.keys(map || {});
      var changed = false;
      return list.reduce(function (chain, n) {
        return chain.then(function () {
          var k = (kinds && kinds[n]) || "image";
          if (names.indexOf(n) < 0) { names.push(n); changed = true; }
          kd[n] = k;
          return dbRun("readwrite", function (st) {
            return st.put({ dataUrl: map[n], kind: k }, n);
          });
        });
      }, Promise.resolve()).then(function () {
        if (changed) idxWrite(names);
        kindWrite(kd);
        return list.length;
      });
    },
    totalBytes: function () {
      return this.all().then(function (map) {
        var n = 0;
        Object.keys(map).forEach(function (k) { n += map[k].length; });
        return n;
      });
    },
  };

  // ---------- 2c. 从别的 App 分享进来 ----------
  // 安卓壳（MainActivity）把文件读成 base64 直推过来，这里还原成 File 再走同一条素材链路。
  // 手机分屏把文件拖进 WebView 做不到（WebView 不接系统级拖放），分享是安卓上那条稳定的路。
  function dataUrlToFile(o) {
    var s = String((o && o.dataUrl) || "");
    var comma = s.indexOf(",");
    if (comma < 0) throw new Error("分享过来的不是文件");
    var meta = s.slice(5, comma);
    var bin = atob(s.slice(comma + 1));
    var arr = new Uint8Array(bin.length);
    for (var i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
    return new File([arr], o.name || ("分享_" + Date.now()), { type: o.type || "application/octet-stream" });
  }
  window.__MYONLShareReceive = function (items) {
    if (!items || !items.length || !window.MYONLAssets) return;
    var files = [];
    for (var i = 0; i < items.length; i++) {
      try { files.push(dataUrlToFile(items[i])); } catch (e) {}
    }
    if (!files.length) return;
    window.MYONLAssets.add(files).then(function (names) {
      if (window.__refreshAssets) window.__refreshAssets();
      var bar = document.querySelector(".off-assets");
      if (bar && bar.__refresh) bar.__refresh();
      if (names.length) toast("已收到分享的 " + names.length + " 个：" + names.join("、"));
      else toast("分享的内容收不了：只收图片、音频和视频", true);
    }).catch(function () { toast("分享的文件没存进去，重试一次", true); });
  };

  // ---------- 3. HTTP 小工具 ----------
  function jsonRes(obj, status) {
    return new Response(JSON.stringify(obj), {
      status: status || 200,
      headers: { "Content-Type": "application/json; charset=utf-8" }
    });
  }
  function bodyOf(init) {
    try {
      if (!init || !init.body) return {};
      if (typeof init.body === "string") return JSON.parse(init.body);
      return {};
    } catch (e) { return {}; }
  }
  function pathOf(input) {
    var url = typeof input === "string" ? input : (input && input.url) || "";
    var cut = url.split("#")[0].split("?")[0];
    // 只保留从 /api 起的部分，且必须带前导斜杠——路由表键是 "GET /api/xxx"
    var m = cut.match(/(\/api\/.*)$/);
    if (m) return m[1];
    if (cut.indexOf("/") === 0) return cut;
    return "";
  }
  function queryOf(input) {
    var url = typeof input === "string" ? input : (input && input.url) || "";
    var q = url.split("?")[1] || "";
    var out = {};
    q.split("&").forEach(function (kv) {
      if (!kv) return;
      var p = kv.split("=");
      out[decodeURIComponent(p[0])] = decodeURIComponent(p[1] || "");
    });
    return out;
  }

  // 指令数（跟电脑端 _home 同口径：以 @ 开头的行）
  function countIns(text) {
    return String(text || "").split("\n").filter(function (l) { return l.trim().charAt(0) === "@"; }).length;
  }

  // ---------- 4. 路由表 ----------
  var ROUTES = {};

  ROUTES["GET /api/version"] = function () {
    return jsonRes({ ok: true, version: "offline" });
  };

  ROUTES["GET /api/config"] = function () {
    return jsonRes({
      ok: true,
      project_root: "浏览器本地",
      data_root: "浏览器本地",
      default_data_root: "浏览器本地",
      custom_data_root: false,
      auto_insert: true,
      config_path: "（手机本地存储）"
    });
  };

  ROUTES["GET /api/home"] = function () {
    var lib = readLib();
    var rows = lib.projects.map(function (p) {
      return {
        folder: p.name,
        name: p.name,
        ins: countIns(p.text),
        assets: 0,
        mtime: p.mtime || 0,
        current: p.name === lib.current
      };
    });
    rows.sort(function (a, b) { return (b.mtime || 0) - (a.mtime || 0); });
    return jsonRes({ ok: true, current: lib.current, games_dir: "", orientation: "any", projects: rows });
  };

  ROUTES["GET /api/files"] = function () {
    return jsonRes({ ok: true, files: ["script.gal"], current: "script.gal" });
  };

  ROUTES["GET /api/file/read"] = function (input) {
    var rel = queryOf(input).path || "script.gal";
    var p = curProject();
    if (rel !== "script.gal") return jsonRes({ ok: false, message: "手机本地只有一个 script.gal" }, 404);
    return jsonRes({ ok: true, path: rel, text: p.text });
  };

  ROUTES["GET /api/script"] = function () {
    return jsonRes({ path: "script.gal", text: curProject().text });
  };

  // 保存是核心：btnSave → /api/file/save {path, content}
  ROUTES["POST /api/file/save"] = function (input, init) {
    var b = bodyOf(init);
    var lib = readLib();
    // 手机本地一个作品只有一个 script.gal，path 用来判断来源，不参与定位
    var p = curProject(lib);
    p.text = String(b.content == null ? (b.text || "") : b.content);
    p.mtime = now();
    writeLib(lib);
    return jsonRes({ ok: true, path: "script.gal", message: "已保存到手机本地" });
  };

  ROUTES["POST /api/script"] = function (input, init) {
    var b = bodyOf(init);
    var lib = readLib();
    var p = curProject(lib);
    p.text = String(b.text == null ? "" : b.text);
    p.mtime = now();
    writeLib(lib);
    return jsonRes({ ok: true, path: "script.gal" });
  };

  ROUTES["POST /api/new"] = function (input, init) {
    var b = bodyOf(init);
    var name = String(b.name || "").trim();
    if (!name) return jsonRes({ ok: false, message: "名字不能为空" }, 400);
    if (/[\/\\]/.test(name)) return jsonRes({ ok: false, message: "名字里不能有斜杠" }, 400);
    var lib = readLib();
    if (findProject(lib, name)) return jsonRes({ ok: false, message: "已经有同名作品了：" + name }, 400);
    lib.projects.push({ name: name, text: starterText(), ctime: now(), mtime: now() });
    lib.current = name;
    writeLib(lib);
    return jsonRes({ ok: true, path: name, message: "已新建「" + name + "」" });
  };

  ROUTES["POST /api/project"] = function (input, init) {
    var b = bodyOf(init);
    // 工作台卡片传 {folder}；电脑端设置面板传 {project_root}（绝对路径）
    var name = String(b.folder || b.project_root || b.name || "").trim();
    var base = name.replace(/[\\/]+$/, "").split(/[\\/]/).pop();
    var lib = readLib();
    var p = findProject(lib, base) || findProject(lib, name);
    if (!p) return jsonRes({ ok: false, message: "没有这个作品：" + (name || "（名字是空的）") }, 400);
    lib.current = p.name;
    writeLib(lib);
    return jsonRes({ ok: true, project_root: p.name, message: "已切换到「" + p.name + "」" });
  };

  ROUTES["GET /api/assets"] = function () {
    // 手机上现在真的有素材了（从相册/文件选进来、压在 IndexedDB 里），
    // 名字从 localStorage 索引同步读，所以这个同步接口照样答得上来。
    // 图片和音频分开报：图片列表里不能混进 mp3 的名字，否则前端会拿它当立绘。
    var kinds = kindRead(), imgs = [], auds = [], vids = [];
    idxRead().forEach(function (n) {
      (kinds[n] === "audio" ? auds : kinds[n] === "video" ? vids : imgs).push(n);
    });
    return jsonRes({ ok: true, assets: {
      images: imgs, videos: vids, anims: [], audio: auds, fonts: []
    } });
  };

  ROUTES["GET /api/characters"] = function () {
    return jsonRes({ ok: true, data: { characters: [] } });
  };

  ROUTES["POST /api/characters"] = function () {
    return jsonRes({ ok: true, message: "手机本地暂不保存角色库" });
  };

  ROUTES["GET /api/adb"] = function () {
    return jsonRes({ ok: false, message: "手机上不需要推送到手机" });
  };
  ROUTES["POST /api/adb"] = function () {
    return jsonRes({ ok: false, message: "手机上不需要推送到手机" });
  };

  // 校验：只做最小一档（@jump 指向不存在的 @label）。
  // 不假装跟 Python 一样严——宁可放过，也不误报把人拦住。
  // 字段名照前端实际读的给：count（状态栏「通过 · N 条」）、instructions（JSON 视图）。
  ROUTES["POST /api/check"] = function (input, init) {
    var b = bodyOf(init);
    var text = String(b.text || (window.__editor && window.__editor.getText ? window.__editor.getText() : "") || "");
    var labels = {}, errs = [], list = [];
    text.split("\n").forEach(function (l, i) {
      var m = l.match(/^@label\s+(\S+)/);
      if (m) labels[m[1]] = 1;
      if (l.trim().charAt(0) === "@") list.push({ line: i + 1, op: l.trim().split(/\s+/)[0].slice(1), text: l.trim() });
    });
    text.split("\n").forEach(function (l, i) {
      var m = l.match(/^@jump\s+(\S+)/);
      if (m && !labels[m[1]]) {
        errs.push({ line: i + 1, message: "跳转目标不存在：" + m[1] });
      }
    });
    if (errs.length) {
      return jsonRes({ ok: false, line: errs[0].line, file: "script.gal",
                       message: errs[0].message, summary: errs[0].message, count: list.length,
                       errors: errs, instructions: list });
    }
    return jsonRes({ ok: true, count: list.length, errors: [], instructions: list });
  };

  // 预览大图：这一版没有渲染服务，直接让人看中间舞台，别挂在那儿转
  ROUTES["POST /api/preview"] = function () {
    return jsonRes({
      ok: false,
      message: window.innerWidth < 720
        ? "手机上用中间的舞台看效果"
        : "电脑上要看实时画面请用完整版；这一版请直接看中间的舞台",
    });
  };
  ROUTES["GET /api/thumb"] = function () {
    return jsonRes({ ok: false, message: "手机本地没有缩略图" });
  };

  // 导出：整个作品库打包成一个 JSON 文本，也支持单份 .gal
  ROUTES["GET /api/off/export"] = function (input) {
    var what = queryOf(input).what || "gal";
    var p = curProject();
    if (what === "lib") {
      return jsonRes({ ok: true, name: "myonl-作品库.json", text: JSON.stringify(readLib(), null, 1) });
    }
    return jsonRes({ ok: true, name: p.name + ".gal", text: p.text });
  };

  // ---------- 5. 劫持 fetch ----------
  var origFetch = window.fetch ? window.fetch.bind(window) : null;
  window.fetch = function (input, init) {
    var method = String((init && init.method) || (input && input.method) || "GET").toUpperCase();
    var path = pathOf(input);
    var h = ROUTES[method + " " + path];
    if (h) {
      try {
        var r = h(input, init);
        if (r) return Promise.resolve(r);
      } catch (e) {
        return Promise.resolve(jsonRes({ ok: false, message: "本地实现出错：" + e }, 500));
      }
    }
    // 素材真图：路径里带名字，精确键匹配不上，这里单独接一段。
    // 编辑器里所有缩略图都是 <img src="/api/asset/images/名字">，
    // 离线时从 IndexedDB 取出来直接回二进制，缩略图才有东西显示。
    var am = path.match(/^\/api\/asset\/(images|videos)\/(.*)$/);
    if (am) {
      var nm = decodeURIComponent(am[2]);
      return window.MYONLAssets.get(nm).then(function (v) {
        if (v && v.dataUrl) return dataUrlToResponse(v.dataUrl);
        return new Response("", { status: 404 });
      }).catch(function () {
        return new Response("", { status: 404 });
      });
    }
    if (/\/api\//.test(path)) {
      // 没实现的接口一律回一个「软失败」的 JSON，
      // 免得 404 的 HTML 被当 JSON 解析，控制台刷 "Unexpected token '<'"
      return Promise.resolve(jsonRes({ ok: false, message: "手机本地没有这个接口：" + path }));
    }
    if (origFetch) return origFetch(input, init);
    return Promise.reject(new Error("no fetch"));
  };

  // ---------- 6. 导出入口 ----------
  // 手机没有「另存为」对话框，能落地的只有两条路：
  //   1) Blob 下载（部分浏览器给「保存到文件」）
  //   2) 系统分享（安卓 Chrome 支持 navigator.share 带文件）
  // 两条都试，谁成算谁；都不成至少有「复制全文」兜底。
  // 文本 -> base64（按 UTF-8 走，中文不会乱；分块只为别把大文件一次性摊成几百万个字符）
  function b64OfText(text) {
    var bytes = new TextEncoder().encode(text);
    var bin = "", CH = 4096;
    for (var i = 0; i < bytes.length; i += CH) {
      bin += String.fromCharCode.apply(null, bytes.subarray(i, i + CH));
    }
    return btoa(bin);
  }
  function download(text, filename, mime) {
    var type = mime || "text/plain;charset=utf-8";
    // 安卓壳里必须有这条：WebView 不理 <a download> + blob，不走保存桥就永远落不了地，
    // 而下面那句 toast 还会照喊「已导出」—— 那就是骗人。
    var bridge = window.__MYONLSave;
    if (bridge && typeof bridge.save === "function") {
      try {
        bridge.save(filename, type.split(";")[0], b64OfText(text));
        // P136：落地后直接弹系统分享「发给朋友」。壳里有 share 桥才调；
        // 旧壳/浏览器没有就静默跳过，保存已经成功，不影响落地。
        if (typeof bridge.share === "function") {
          try { bridge.share(filename, type.split(";")[0], b64OfText(text)); } catch (e2) {}
        }
        return;
      } catch (e) { /* 桥坏了再往下退 */ }
    }
    var blob = new Blob([text], { type: type });
    try {
      if (navigator.canShare && navigator.share) {
        var file = new File([blob], filename, { type: type.split(";")[0] });
        if (navigator.canShare({ files: [file] })) {
          navigator.share({ files: [file], title: filename }).catch(function () { save(blob, filename); });
          return;
        }
      }
    } catch (e) { /* 落到下载 */ }
    save(blob, filename);
  }
  function save(blob, filename) {
    try {
      var a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      setTimeout(function () { try { URL.revokeObjectURL(a.href); a.remove(); } catch (e) {} }, 4000);
      toast("已导出 " + filename + "（在浏览器的下载里找）");
    } catch (e) {
      toast("这个环境不让直接下载，改用「复制全文」", true);
    }
  }
  window.__myonlExportGal = function () {
    var p = curProject();
    download(p.text, p.name + ".gal");
  };
  // 备份要连素材一起走：只带剧本的备份是假备份 —— 换台手机恢复出来是一堆找不着图的作品，
  // 比没备份更让人上火。素材在 IndexedDB，所以这一步是异步的。
  window.__myonlExportLib = function () {
    var bag = readLib();
    var sp = window.MYONLAssets ? window.MYONLAssets.allSplit()
      : Promise.resolve({ assets: {}, audio: {}, movies: {} });
    toast("正在打包作品和素材…");
    return sp.then(function (s) {
      var assets = (s && s.assets) || {};
      var audio = (s && s.audio) || {};
      var movies = (s && s.movies) || {};
      // 视频在 allSplit 里同时留在 assets（播放器只认名字）；备份不存两遍，摘到 movies 桶，
      // 类型单独记进 kinds。以前导出只带 assets+audio，导入又把 assets 一律标成图 ——
      // 带 mp4 的作品换机恢复后视频全变回图片，播放器按图处理，等于假备份。
      var kinds = {};
      Object.keys(movies).forEach(function (k) { delete assets[k]; kinds[k] = "video"; });
      Object.keys(audio).forEach(function (k) { kinds[k] = "audio"; });
      Object.keys(assets).forEach(function (k) { kinds[k] = "image"; });
      var ni = Object.keys(assets).length;
      var nu = Object.keys(audio).length;
      var nv = Object.keys(movies).length;
      var out = {
        myonl: "lib", v: 3,
        projects: bag.projects || [], current: bag.current || "",
        assets: assets, audio: audio, movies: movies, kinds: kinds
      };
      download(JSON.stringify(out, null, 1), "myonl-作品库.json");
      var parts = [out.projects.length + " 个作品"];
      if (ni) parts.push(ni + " 张图");
      if (nv) parts.push(nv + " 段视频");
      if (nu) parts.push(nu + " 段音频");
      toast("已导出 " + parts.join("、"));
    }).catch(function () {
      // 素材读不出来也至少把剧本带走，别让整件事白跑
      download(JSON.stringify({ myonl: "lib", v: 1, projects: bag.projects || [], current: bag.current || "" }, null, 1),
        "myonl-作品库.json");
      toast("素材没读到，只导出了剧本", true);
    });
  };

  // 成品导出：手机上**自己**把剧本编成能双击就玩的单文件 HTML。
  // 解析走 engine/parser.js（和电脑端 Python 逐字段一致，tools/pack_diff.py 对拍），
  // 拼装走 engine/pack.js。播放器那三个脚本在 APK 里跟 index.html 同级，
  // 所以这里直接 fetch；桌面上 file:// 取不到会诚实报错，不假装成功。
  function playerSources() {
    return Promise.all(["myonl-core.js", "myonl-layout.js", "myonl-player.js"].map(function (n) {
      return fetch(n, { cache: "no-store" }).then(function (r) {
        if (!r.ok) throw new Error(n);
        return r.text();
      });
    }));
  }
  // allSplit 把视频同时留在 assets；进 pack 前摘出去走 movies，
  // 转成 {src, mime} 给打包器，避免同一段视频体积在两边算两遍。
  function moviesOf(sp, assets) {
    var pack = {};
    Object.keys((sp && sp.movies) || {}).forEach(function (k) {
      var u = sp.movies[k], comma = u.indexOf(","), mime = "video/mp4";
      if (comma > 5) mime = (u.slice(5, comma).split(";")[0] || mime).trim();
      pack[k] = { src: u, mime: mime };
      delete assets[k];
    });
    return pack;
  }
  window.__myonlExportPack = function () {
    var p = curProject();
    if (!window.MYONLPack || !window.MYONLParser) { toast("打包器没加载，刷新一下", true); return; }
    toast("正在把剧本编成成品…");
    // 素材以前一律传空 —— 于是手机上出的成品永远是纯文字配渐变底。
    // 现在从 IndexedDB 把素材全取出来：画面归 assets，声音归 audio，真视频归 movies。
    var assetsP = (window.MYONLAssets ? window.MYONLAssets.allSplit() : Promise.resolve({ assets: {}, audio: {} }));
    Promise.all([playerSources(), assetsP]).then(function (both) {
      var src = both[0], sp = both[1] || {};
      var assets = sp.assets || {}, audio = sp.audio || {};
      var moviesPack = moviesOf(sp, assets);
      var names = Object.keys(assets);
      var r = window.MYONLPack.buildPack({
        title: p.name, scriptText: p.text,
        assets: assets, audio: audio, videos: {}, movies: moviesPack, config: {}, orientation: "any",
      });
      if (!r.ok) { toast("剧本第 " + r.error.line + " 行：" + r.error.message, true); return; }
      // 体积口径跟打包器走（data URI 按 base64 还原成字节估），不再自己拿字符串长度瞎算。
      var mb = r.fileMb || 0;
      var html = window.MYONLPack.renderSingle(r.pack, src);
      // P136：硬线（>80MB）在手机上大概率白屏/闪退，不能跟软线一样只喊一句"成品好了"。
      if (r.fileWarningLevel === "hard") {
        toast("⚠ 硬线告警：" + r.fileWarning, true);
      }
      download(html, p.name + ".html", "text/html;charset=utf-8");
      var parts = [];
      if (names.length) parts.push(names.length + " 张图");
      if (Object.keys(moviesPack).length) parts.push(Object.keys(moviesPack).length + " 段视频");
      if (Object.keys(audio).length) parts.push(Object.keys(audio).length + " 段音频");
      if (r.fileWarningLevel === "soft") toast("体积提醒：" + r.fileWarning, true);
      toast(parts.length
        ? ("成品好了：带了 " + parts.join(" + ") + "，约 " + mb + " MB")
        : "成品好了（还没有素材，画面是渐变色）");
    }).catch(function () {
      toast("这台设备取不到播放器内核，成品导出请在装好的 APK 里用", true);
    });
  };
  // 导入：剧本先落地，素材再按原名铺回去。返回 Promise<boolean>，
  // 调用方必须等它 —— 素材没铺完就 reload，等于恢复了一半。
  window.__myonlImportLib = function (json) {
    var lib;
    try {
      lib = typeof json === "string" ? JSON.parse(json) : json;
      if (!lib || !lib.projects || !lib.projects.length) throw new Error("这份文件里没有作品");
      writeLib({ projects: lib.projects, current: lib.current || "" });
    } catch (e) {
      toast("导入失败：" + (e.message || e), true);
      return Promise.resolve(false);
    }
    var n = lib.projects.length;
    var assets = (lib.assets && typeof lib.assets === "object") ? lib.assets : {};
    var audio = (lib.audio && typeof lib.audio === "object") ? lib.audio : {};
    var movies = (lib.movies && typeof lib.movies === "object") ? lib.movies : {};
    var kindsIn = (lib.kinds && typeof lib.kinds === "object") ? lib.kinds : null;
    // 旧格式（v1/v2）只有 assets+audio，没有类型索引：assets 按图、audio 按音频还原。
    // 旧文件里混进去的视频当时就被标成了图，救不回来；提示必须说实话，不能假装视频回来了。
    var legacy = !kindsIn && !Object.keys(movies).length;
    var na = Object.keys(assets).length, nu = Object.keys(audio).length, nv = Object.keys(movies).length;
    if (!na && !nu && !nv) {
      toast("已导入 " + n + " 个作品（这份备份里没有素材）");
      return Promise.resolve(true);
    }
    if (!window.MYONLAssets || !window.MYONLAssets.restore) {
      toast("已导入 " + n + " 个作品；素材这条链路没加载，图和声音要重新放", true);
      return Promise.resolve(true);
    }
    var all = {};
    var kinds = {};
    // 同一名字在多个桶里出现时 movies 优先：既是真视频就不能被 assets 覆盖回图片。
    function put(k, v, kind) {
      if (all[k] !== undefined) return;
      all[k] = v; kinds[k] = kind;
    }
    Object.keys(audio).forEach(function (k) { put(k, audio[k], "audio"); });
    Object.keys(movies).forEach(function (k) { put(k, movies[k], "video"); });
    Object.keys(assets).forEach(function (k) {
      var kind = kindsIn && (kindsIn[k] === "audio" || kindsIn[k] === "video") ? kindsIn[k] : "image";
      put(k, assets[k], kind);
    });
    return window.MYONLAssets.restore(all, kinds).then(function (cnt) {
      var parts = [n + " 个作品", cnt + " 个素材（原名放回）"];
      if (legacy) parts.push("旧格式备份：视频类型没带走，若有视频会按图片还原");
      toast("已导入 " + parts.join("、"), legacy);
      return true;
    }).catch(function (e) {
      toast("作品导入了，素材没铺完：" + (e.message || e), true);
      return true;
    });
  };

  // 导出条：手机上原来的「导出」分组点开是皮肤参数 + 三个打后端的按钮，
  // 离线时全是废的。所以点到名字含「导出」的分组时，往子页顶部插一条
  // 真能用的：拿出剧本 / 拿出整个作品库 / 塞回作品库。
  function exportBar() {
    var bar = document.createElement("div");
    bar.className = "off-export";
    bar.style.cssText = "padding:12px 14px 14px;border-bottom:1px solid rgba(255,255,255,.08);" +
      "background:rgba(79,140,255,.07)";
    var tip = document.createElement("div");
    tip.style.cssText = "font-size:12px;line-height:1.6;color:#9fb2d0;margin-bottom:10px";
    tip.textContent = "作品存在这台设备里，不上云。剧本能带走，成品也能在这台手机上直接出——" +
      "下面第一个按钮就是打包，出来的 .html 发给谁都能双击玩。";
    bar.appendChild(tip);

    [["做成成品（.html，能发人）", function () { window.__myonlExportPack(); }],
     ["拿出这个作品（.gal）", function () { window.__myonlExportGal(); }],
     ["拿出全部作品（.json）", function () { window.__myonlExportLib(); }]
    ].forEach(function (it) {
      var b = document.createElement("button");
      b.type = "button";
      b.textContent = it[0];
      b.style.cssText = "display:block;width:100%;margin:6px 0 0;padding:11px 14px;border-radius:12px;" +
        "border:1px solid rgba(79,140,255,.45);background:rgba(79,140,255,.14);color:#dce8ff;" +
        "font-size:14px;line-height:1.3;box-sizing:border-box;text-align:left;min-height:0";
      b.style.height = "auto";
      b.addEventListener("click", it[1]);
      bar.appendChild(b);
    });
    return bar;
  }
  function injectExportBar() {
    // 点「导出」后打开的是界面设计中心页，真正装按钮的卡是 .uid-web；
    // 插到它前面，用户第一眼看到的就是这条，而不是三个打后端的废按钮。
    var web = document.querySelector(".uid-web");
    if (web) {
      if (!web.parentNode.querySelector(".off-export")) {
        web.parentNode.insertBefore(exportBar(), web);
      }
      // 那三个按钮全打后端（/api/export-single 等），离线点了只会“请求失败”。
      // 收起来，也省得用户以为自己点坏了。
      web.style.setProperty("display", "none", "important");
      return;
    }
    var host = document.querySelector(".m-subbody") || document.querySelector(".modal-body");
    if (!host || host.querySelector(".off-export")) return;
    host.insertBefore(exportBar(), host.firstChild);
  }
  // 素材条：手机上原来素材页永远是空的（/api/assets 回空清单），
  // 用户只能用编辑器自带的渐变当背景 —— 这就是"看着像 demo 不像游戏"的根。
  // 这条给一个真入口：从相册选图 → 压缩 → 存进 IndexedDB → 素材页立刻看得到。
  // 手机端做游戏真正卡住的地方是素材进不来：相册里翻半天、也不确定压没压。
  // 这条给一个「投递区」——点一下选文件，桌面还能直接把文件拖进来。
  // 收什么、压多大、存哪儿，全写在框里，不用猜。
  var MAX_FILES = 20;
  var MAX_BYTES = 24 * 1024 * 1024;
  function mbText(n) { return (Math.round((n / 1048576) * 10) / 10).toFixed(1) + " MB"; }

  function assetBar() {
    var bar = document.createElement("div");
    bar.className = "off-assets";
    bar.style.cssText = "padding:12px 14px 14px;border-bottom:1px solid rgba(255,255,255,.08);" +
      "background:rgba(79,140,255,.07)";

    var drop = document.createElement("div");
    drop.style.cssText = "border:1.5px dashed rgba(79,140,255,.52);border-radius:14px;" +
      "background:rgba(79,140,255,.05);padding:16px 12px 15px;text-align:center;cursor:pointer;" +
      "transition:background .15s,border-color .15s;-webkit-tap-highlight-color:transparent";

    var t1 = document.createElement("div");
    t1.style.cssText = "font-size:15px;line-height:1.4;color:#dce8ff;font-weight:600";
    t1.textContent = "把文件放进来";

    var t2 = document.createElement("div");
    t2.style.cssText = "font-size:12px;line-height:1.75;color:#8fa3c0;margin-top:6px";
    t2.innerHTML = "点这里选，桌面上也可以直接拖进来<br>" +
      "图片压到最长边 1280 · 音频原样存 · 视频原样存，单个不超过 24 MB<br>" +
      "一次最多 " + MAX_FILES + " 个";

    drop.appendChild(t1);
    drop.appendChild(t2);
    bar.appendChild(drop);

    var input = document.createElement("input");
    input.type = "file";
    input.accept = "image/*,audio/*";
    input.accept += ",video/*";
    input.multiple = true;
    input.style.display = "none";
    bar.appendChild(input);

    var usage = document.createElement("div");
    usage.style.cssText = "font-size:12px;line-height:1.6;color:#8fa3c0;margin-top:9px";
    bar.appendChild(usage);

    function refreshUsage() {
      if (!window.MYONLAssets) return;
      var names = window.MYONLAssets.list();
      var img = 0, aud = 0, vid = 0;
      names.forEach(function (n) {
        var k = window.MYONLAssets.kindOf(n);
        if (k === "audio") aud++;
        else if (k === "video") vid++;
        else img++;
      });
      var parts = [];
      if (img) parts.push(img + " 张图");
      if (vid) parts.push(vid + " 段视频");
      if (aud) parts.push(aud + " 段音频");
      window.MYONLAssets.totalBytes().then(function (n) {
        usage.textContent = names.length
          ? ("已存 " + parts.join(" / ") + "，共 " + mbText(n))
          : "这个作品还没有素材，成品会用蓝渐变当背景";
      }).catch(function () {});
    }
    refreshUsage();
    bar.__refresh = refreshUsage;   // 分享进来 / 别处加完图，让用量行跟着动

    function take(files) {
      if (!window.MYONLAssets) { toast("素材库没加载，刷新一下页面", true); return; }
      var arr = Array.prototype.slice.call(files || []);
      if (!arr.length) return;
      if (arr.length > MAX_FILES) {
        toast("一次最多 " + MAX_FILES + " 个，先挑了前 " + MAX_FILES + " 个", true);
        arr = arr.slice(0, MAX_FILES);
      }
      var big = arr.filter(function (f) { return (f.size || 0) > MAX_BYTES; });
      if (big.length) {
        var bigVid = big.filter(function (f) { return /^video\//i.test(f.type || ""); });
        var bigOther = big.filter(function (f) { return !/^video\//i.test(f.type || ""); });
        if (bigVid.length) toast("这段视频超过 24 MB，先在手机里剪短或压一下再导", true);
        if (bigOther.length) {
          toast(bigOther.length + " 个超过 24 MB 没放进来：" +
            bigOther.slice(0, 2).map(function (f) { return f.name; }).join("、"), true);
        }
        arr = arr.filter(function (f) { return (f.size || 0) <= MAX_BYTES; });
      }
      if (!arr.length) return;

      var names = [], failed = 0, errMsg = "";
      drop.style.pointerEvents = "none";
      drop.style.opacity = ".6";
      t1.textContent = "导入中 0/" + arr.length;
      window.MYONLAssets.add(arr, function (name, done, total, err) {
        if (name) names.push(name);
        if (err) { failed++; errMsg = err.message || ""; }
        var settled = done + failed;
        t1.textContent = settled >= total ? "把文件放进来" : ("导入中 " + settled + "/" + total);
        if (settled >= total) {
          drop.style.pointerEvents = "";
          drop.style.opacity = "";
          if (window.__refreshAssets) window.__refreshAssets();
          refreshUsage();
          if (names.length) {
            toast("已加入 " + names.length + " 个：" + names.join("、") +
              (failed ? "（" + failed + " 个没收：" + errMsg + "）" : ""));
          } else {
            toast("一个都没加进去" + (errMsg ? "：" + errMsg : ""), true);
          }
          input.value = "";
        }
      });
    }

    drop.addEventListener("click", function () { input.click(); });
    input.addEventListener("change", function () { take(input.files); });

    // 桌面上拖拽：进来时框亮起来，松手就收
    function lit(on) {
      drop.style.background = on ? "rgba(79,140,255,.18)" : "rgba(79,140,255,.05)";
      drop.style.borderColor = on ? "rgba(79,140,255,.95)" : "rgba(79,140,255,.52)";
    }
    ["dragenter", "dragover"].forEach(function (ev) {
      drop.addEventListener(ev, function (e) {
        e.preventDefault(); e.stopPropagation(); lit(true);
      });
    });
    ["dragleave", "dragend"].forEach(function (ev) {
      drop.addEventListener(ev, function () { lit(false); });
    });
    drop.addEventListener("drop", function (e) {
      e.preventDefault(); e.stopPropagation(); lit(false);
      take(e.dataTransfer && e.dataTransfer.files);
    });

    return bar;
  }
  function injectAssetBar() {
    // 素材面板真实容器：手机端点「素材」后弹出的是 aside.asset-pane，
    // 里面 div.asset-body 放列表 —— 条要插在列表之前，不能盖住面板标题。
    var body = document.querySelector("div.asset-body");
    if (body && body.parentNode) {
      if (body.parentNode.querySelector(".off-assets")) return;
      body.parentNode.insertBefore(assetBar(), body);
      return;
    }
    var host = document.querySelector(".m-subbody") || document.querySelector(".modal-body") || document.querySelector("aside.asset-pane");
    if (!host) return;
    if (host.querySelector(".off-assets")) return;
    host.insertBefore(assetBar(), host.firstChild);
  }
  document.addEventListener("click", function (e) {
    var row = e.target && e.target.closest ? e.target.closest(".m-group-row, .m-tab, .uid-tab, button") : null;
    if (!row) return;
    if (/素材|图片|立绘/.test(row.textContent || "") && !/角色/.test(row.textContent || "")) {
      setTimeout(injectAssetBar, 320);
      setTimeout(injectAssetBar, 820);
      setTimeout(injectAssetBar, 1400);
    }
  }, true);

  document.addEventListener("click", function (e) {
    var row = e.target && e.target.closest ? e.target.closest(".m-group-row, .uid-tab, .m-tab, button") : null;
    if (!row) return;
    if (/导出/.test(row.textContent || "")) {
      // 打开中心页有 260/760 两次动画修补，跟着补两次
      setTimeout(injectExportBar, 320);
      setTimeout(injectExportBar, 820);
    }
  }, true);

  // 缩略图补丁：<img src="/api/asset/images/x"> 走的是浏览器自己的取图通道，
  // 绕不过 fetch 劫持 —— 不补的话素材页永远是一排空框（naturalWidth 0）。
  // 这里把地址里的名字取出来，换成真 dataURL，图上就出来了。
  function fixAssetImages() {
    var ims = document.querySelectorAll('img[src*="/api/asset/images/"]');
    for (var i = 0; i < ims.length; i++) {
      var im = ims[i];
      if (im.dataset.offFixed) continue;
      im.dataset.offFixed = "1";
      var m = String(im.getAttribute("src") || "").match(/\/api\/asset\/images\/(.*)$/);
      if (!m || !window.MYONLAssets) continue;
      (function (img, nm) {
        window.MYONLAssets.get(nm).then(function (v) {
          if (v && v.dataUrl) img.src = v.dataUrl;
        }).catch(function () {});
      })(im, decodeURIComponent(m[1]));
    }
  }
  setInterval(fixAssetImages, 700);
  document.addEventListener("DOMContentLoaded", fixAssetImages);

  // 视频缩略补丁：视频卡片原本也按 <img> 渲染，<img> 解不了 mp4。
  // 这里按名字查出 kind=video 的卡片，把 <img> 换成 <video>（静音、内联、只取元数据），
  // src 直接用 dataURL；点一下播一次，播完停在最后一帧，不循环。
  function fixAssetVideos() {
    if (!window.MYONLAssets) return;
    var vids = window.MYONLAssets.list().filter(function (n) {
      return window.MYONLAssets.kindOf(n) === "video";
    });
    if (!vids.length) return;
    var cards = document.querySelectorAll("div.asset-card");
    for (var i = 0; i < cards.length; i++) {
      var card = cards[i];
      if (card.querySelector("video[data-off-video]")) continue;
      var nm = card.querySelector(".nm");
      var name = nm ? nm.textContent : "";
      if (vids.indexOf(name) < 0) continue;
      (function (c, n) {
        window.MYONLAssets.get(n).then(function (v) {
          if (!v || !v.dataUrl || c.querySelector("video[data-off-video]")) return;
          var video = document.createElement("video");
          video.muted = true;
          video.playsInline = true;
          video.setAttribute("playsinline", "");
          video.setAttribute("preload", "metadata");
          video.setAttribute("data-off-video", "1");
          video.src = v.dataUrl;
          video.style.cssText = "width:100%;height:110px;object-fit:contain;display:block;background:#0d1420";
          var oldImg = c.querySelector("img");
          if (oldImg) c.replaceChild(video, oldImg);
          else c.insertBefore(video, c.firstChild);
          video.addEventListener("click", function (e) {
            e.stopPropagation();
            if (video.paused) {
              var pr = video.play();
              if (pr && pr.catch) pr.catch(function () {});
            } else {
              video.pause();
            }
          });
        }).catch(function () {});
      })(card, name);
    }
  }
  setInterval(fixAssetVideos, 700);
  document.addEventListener("DOMContentLoaded", fixAssetVideos);

  // ---------- 7. 封面与缩略图 ----------
  // 手机上没有任何素材，工作台卡片原本是一块纯黑（这就是"劣质感"的来源）。
  // 离线时按作品名算一个稳定的蓝系渐变铺上去，小卡再压一个首字，
  // 让每张卡有身份、不像空壳。
  // 同时把缩略图元素上的 data-folder 摘掉：Image() 绕不过 fetch 劫持，
  // 留着它只会白发一次必然 404 的请求。点击用的 data-folder 在父级，不动。
  // 蓝系为主（#4f8cff 一带），深浅拉开让每张卡能区分；不掺橙黄
  var PALETTE = [
    ["#101a2e", "#2f5fa8"],
    ["#12172b", "#4f8cff"],
    ["#0f1a2a", "#2a7fbf"],
    ["#151530", "#5b6bd6"],
    ["#101c33", "#3a86d6"],
    ["#141428", "#6d7ef0"]
  ];
  function hueOf(s) {
    var h = 0;
    for (var i = 0; i < s.length; i++) h = (h * 33 + s.charCodeAt(i)) >>> 0;
    return h;
  }
  function coverCss(name) {
    var pair = PALETTE[hueOf(name) % PALETTE.length];
    return "radial-gradient(120% 90% at 78% 12%, rgba(255,255,255,.30) 0%, rgba(255,255,255,0) 46%)," +
      "repeating-linear-gradient(115deg, rgba(255,255,255,.055) 0 2px, rgba(255,255,255,0) 2px 7px)," +
      "linear-gradient(140deg, " + pair[1] + " 0%, " + pair[0] + " 74%)";
  }
  function decorateOne(card) {
    var name = card.getAttribute("data-folder");
    if (!name) return;
    var cover = card.querySelector(".m-hero-cover");
    var thumb = card.querySelector(".m-card-thumb");
    if (cover) {
      cover.removeAttribute("data-folder");
      cover.style.backgroundImage = coverCss(name);
      cover.style.backgroundSize = "cover";
    }
    if (thumb && thumb.parentNode) {
      thumb.removeAttribute("data-folder");
      thumb.style.backgroundImage = coverCss(name);
      thumb.style.backgroundSize = "cover";
      if (!thumb.querySelector(".off-glyph") && !/m-card-thumb-new/.test(thumb.className)) {
        var g = document.createElement("span");
        g.className = "off-glyph";
        g.textContent = name.slice(0, 1);
        g.style.cssText = "position:absolute;inset:0;display:flex;align-items:center;justify-content:center;" +
          "font-size:26px;font-weight:600;color:rgba(255,255,255,.82);text-shadow:0 2px 10px rgba(0,0,0,.35)";
        thumb.style.position = "relative";
        thumb.style.overflow = "hidden";
        thumb.appendChild(g);
      }
    }
  }
  function decorate(root) {
    if (!root || root.nodeType !== 1) return;
    // 关键：querySelectorAll 不包含 root 自己，而 innerHTML 出来后
    // 新增节点往往就是那张卡本身，所以先判自己再扫子树。
    if (root.matches && root.matches(".m-home-hero, .m-home-card")) decorateOne(root);
    var kids = root.querySelectorAll(".m-home-hero, .m-home-card");
    for (var i = 0; i < kids.length; i++) decorateOne(kids[i]);
  }
  decorate(document);
  // editor_home.js 是「先 innerHTML 再同步 new Image()」，MutationObserver 追不上它。
  // 所以直接在 HTMLImageElement.src 上兜一道：离线时 /api/thumb 一律不加载。
  try {
    var srcDesc = Object.getOwnPropertyDescriptor(HTMLImageElement.prototype, "src");
    if (srcDesc && srcDesc.set) {
      Object.defineProperty(HTMLImageElement.prototype, "src", {
        configurable: true,
        get: function () { return srcDesc.get.call(this); },
        set: function (v) {
          if (typeof v === "string" && v.indexOf("/api/thumb") >= 0) return;   // 静默丢弃
          srcDesc.set.call(this, v);
        }
      });
    }
  } catch (e) { /* 定义不了就算了，最多留一条 404 */ }
  try {
    new MutationObserver(function (muts) {
      for (var i = 0; i < muts.length; i++) {
        var added = muts[i].addedNodes;
        for (var j = 0; j < added.length; j++) {
          if (added[j].nodeType === 1) decorate(added[j]);
        }
      }
    }).observe(document.body, { childList: true, subtree: true });
  } catch (e) { /* 老浏览器就算了 */ }

  // ---------- 8. 开机提示 ----------
  // 只提示一次，别每次进编辑器都糊一脸
  try {
    if (!sessionStorage.getItem("myonl:off:told")) {
      sessionStorage.setItem("myonl:off:told", "1");
      setTimeout(function () {
        // 同一句话在电脑上不能叫"手机本地模式"：宽屏按电脑说法讲
        var narrow = window.innerWidth < 720;
        toast(narrow ? "手机本地模式：作品存在这台设备里"
                     : "本地模式：作品和素材都存在这台电脑上，不联网也能用");
      }, 500);
    }
  } catch (e) { /* ignore */ }

  // ---------- 9. P131：PWA 分享进来 ----------
  // 相册里长按「分享到 MYONL」→ 系统 POST 到 /share-target → sw.js 把文件存进素材库 inbox →
  // 跳回带 ?shared= 的首页 → 这里把 inbox 搬进正式素材。
  // 为什么放在这个文件而不是 index.html：入口页有 <600 行的硬上限（tests 会查），
  // 而分享链路本来就和素材落库是同一件事，搁一起才不用跨文件传状态。
  // file:// 与 WebView 里没有 serviceWorker，整段静默跳过，不影响别的功能。
  try {
    if (window.navigator && "serviceWorker" in window.navigator
        && /^https?:$/.test(window.location.protocol)) {
      window.navigator.serviceWorker.register("/sw.js").catch(function () {
        /* 装不上就算了：没分享入口也不能连累编辑器 */
      });
    }
    if (/[?&]shared=/.test(window.location.search)
        && window.MYONLAssets && typeof window.MYONLAssets.importShared === "function") {
      window.addEventListener("load", function () {
        window.MYONLAssets.importShared().then(function (names) {
          if (names && names.length) toast("从分享收下 " + names.length + " 个素材：" + names.join("、"));
          else toast("这次分享里没拿到能用的素材", true);
        }).catch(function () {
          toast("分享进来的素材没存上，重新分享一次试试", true);
        });
      });
    }
  } catch (e) { /* ignore */ }
})();
