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
    // P217：默认只给这一份「示范案例」，教程与它是同一个东西，不再另建「新手教程」。想写自己的点「新建项目」。
    return { current: "示范案例", projects: [{ name: "示范案例", text: t, ctime: now(), mtime: now() }] };
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
          if (lib && Array.isArray(lib.projects)) return lib;  // 空数组也算数：作品被删进垃圾箱，不许再造一个「示范案例」
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
  window.__myonlLib = { read: readLib, write: writeLib };   // P203：作品「⋯」与垃圾箱在 editor_trash.js，库只有这一份
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

  // 新作品不再给「hello world」三行白屏：直接给一份 14 句能跑、能改、带分支的开场。
  // 打开就能点「预览」看到画面，改两句就变成自己的故事。
  function starterText() {
    return "# 这是「示范案例」：一份真能玩、真能改的作品。不想要就删掉，写自己的点「新建项目」\n# 以 # 开头的是注释，不上屏；一行就是游戏里的一屏。写法看不清就点底部「素材」→ 底下那条「写法速查」\n\n@label start\n@[旁白] 末班车还有四分钟到站。\n@[小满] 你也在等这趟？\n@[我] 嗯。等一个人，等不到就走。\n@[小满] 那要是等到了呢？\n\n@choice:\n    > 跟她说实话 -> 坦白\n    > 说在等朋友 -> 岔开\n\n@label 坦白\n@[我] 其实是在等你。\n@[小满] 那你挺会等的。\n@[旁白] 车进站了。她先上去，回头朝你招手。\n@end\n\n@label 岔开\n@[我] 一个朋友，大概不来了。\n@[小满] 那我陪你等。\n@end\n";
  }

  function toast(msg, isErr) {
    try {
      if (window.__editor && window.__editor.toast) { window.__editor.toast(msg, isErr); return; }
    } catch (e) { /* ignore */ }
    var el = document.createElement("div");
    el.textContent = msg;
    el.style.cssText = "position:fixed;left:50%;bottom:calc(56px + env(safe-area-inset-bottom) + 12px);transform:translateX(-50%);z-index:99999;" +
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
    try { localStorage.setItem(IDX_KEY, JSON.stringify(a)); return true; }
    catch (e) { return false; }
  }

  // 素材分两类，处置方式不一样：图压过再存、进成品当画面；
  // 音频里 WAV 转 webm（未压缩 PCM，一分钟 10 MB），mp3/ogg/m4a 原样存。
  // 类型另存一份（名字索引里只有名字），这样同步的 /api/assets 也能把两类分开答。
  var KIND_KEY = "myonl:assets:kind:v1";
  function kindRead() {
    try {
      var o = JSON.parse(localStorage.getItem(KIND_KEY) || "{}");
      return (o && typeof o === "object") ? o : {};
    } catch (e) { return {}; }
  }
  function kindWrite(o) {
    try { localStorage.setItem(KIND_KEY, JSON.stringify(o || {})); return true; }
    catch (e) { return false; }
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
        var settled = false;
        function settle(fn, v) { if (settled) return; settled = true; fn(v); }
        var r = fn(st);
        if (r) r.onsuccess = function () { out = r.result; };
        tx.oncomplete = function () { settle(res, out); };
        tx.onerror = function () { settle(rej, tx.error || new Error("素材库写入失败")); };
        // 事务中止（配额满 / 约束冲突 / 并发写冲突）只触发 abort 不一定走 onerror；
        // 不挂 onabort，Promise 就永远 pending，调用方一直等，进度卡在「导入中」像卡死。
        tx.onabort = function () { settle(rej, tx.error || new Error("素材库事务中止")); };
      });
    });
  }

  // 原图原样存：缩了画质就永久没了。列表要的小图另存一份（见 persistAsset 的 thumb）。
  function readDataUrl(file) {
    return new Promise(function (res, rej) {
      var fr = new FileReader();
      fr.onload = function () { res(String(fr.result || "")); };
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

  // WAV 是唯一一个「没压缩过」的音频格式：一分钟 CD 音质约 10 MB，
  // 一段台词几百 KB，一部全语音作品光语音就能上百 MB。
  // mp3/ogg/m4a 原样存是对的（再转一道只掉质量不掉体积），WAV 不是。
  // 转成 webm/opus：同样的语音小一个数量级，安卓 WebView 都能放。
  // 转不了的（不支持 MediaRecorder、解码失败、太长）一律回退原样，不拦导入。
  var WAV_MAX_SECONDS = 90;        // 超过就算「该自己剪一下」，不在手机上硬转
  function looksLikeWav(file) {
    return /\.wav$/i.test(file.name || "") || /audio\/(x-)?wav/i.test(file.type || "");
  }
  function wavToOpus(file) {
    return new Promise(function (res, rej) {
      if (typeof MediaRecorder === "undefined") { rej(new Error("这个环境不支持转码")); return; }
      var AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) { rej(new Error("这个环境没有 Web Audio")); return; }
      var ac = new AC();
      var fr = new FileReader();
      fr.onerror = function () { rej(new Error("读文件失败")); };
      fr.onload = function () {
        ac.decodeAudioData(fr.result).then(function (buf) {
          if (buf.duration > WAV_MAX_SECONDS) {
            ac.close();
            rej(new Error("超过 " + WAV_MAX_SECONDS + " 秒，先在手机里剪短"));
            return;
          }
          var dest = ac.createMediaStreamDestination();
          var src = ac.createBufferSource();
          src.buffer = buf;
          src.connect(dest);
          var rec = new MediaRecorder(dest.stream, { mimeType: "audio/webm" });
          var chunks = [];
          rec.ondataavailable = function (e) { if (e.data && e.data.size) chunks.push(e.data); };
          rec.onstop = function () {
            var blob = new Blob(chunks, { type: "audio/webm" });
            blob.arrayBuffer().then(function (ab) {
              var u8 = new Uint8Array(ab);
              var bin = "", CH = 4096;
              for (var i = 0; i < u8.length; i += CH) {
                bin += String.fromCharCode.apply(null, u8.subarray(i, i + CH));
              }
              ac.close();
              res("data:audio/webm;base64," + btoa(bin));
            });
          };
          src.onended = function () { try { rec.stop(); } catch (e) {} };
          rec.start();
          src.start();
        }, function () { ac.close(); rej(new Error("这个 WAV 解不开")); });
      };
      fr.readAsArrayBuffer(file);
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
  function persistAsset(wantName, kind, dataUrl, taken, kinds, thumb) {
    var name = uniqueName(wantName, taken);
    // 先把素材体写进 IndexedDB，成功后才写名字 / 类型索引；顺序反过来，
    // put 失败就会在索引里留下幽灵名字——列表看得见、素材体取不到。
    return dbRun("readwrite", function (st) {
      return st.put({ dataUrl: dataUrl, kind: kind, thumb: thumb || null }, name);
    }).then(function () {
      taken.push(name);
      kinds[name] = kind;
      var iok = idxWrite(taken), kok = kindWrite(kinds);
      if (!iok || !kok) {
        // 索引没写进去：把刚存的素材体撤掉，不留「库里有、索引里没有」的半截状态
        delete kinds[name];
        return dbRun("readwrite", function (st) { return st.delete(name); })
          .then(function () { throw new Error("素材索引写不进本机存储"); });
      }
      return name;
    }).catch(function (e) {
      // DB 写失败（或上面回滚路径）：把内存里刚推的名字撤掉，别让脏名字卡住下次重选
      var ti = taken.indexOf(name);
      if (ti >= 0) taken.splice(ti, 1);
      delete kinds[name];
      throw e;
    });
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
    // 图片：原图原样存（画质不丢），另存一张 240 边小图给列表显示；音频 / 视频原样存；其它类型不收
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
            ? readDataUrl(f).then(function (u) {
                // 原图原样存；另出一张 240 边的小图，只给素材列表显示用
                var t = window.MYONLThumb
                  ? window.MYONLThumb.fromDataUrl(u, 240).catch(function () { return null; })
                  : Promise.resolve(null);
                return t.then(function (th) { return { dataUrl: u, kind: "image", thumb: th }; });
              })
            : isVid
              ? videoDataUrl(f).then(function (u) { return { dataUrl: u, kind: "video" }; })
              : (looksLikeWav(f)
                // WAV 先转，转不了就算了——退回原样存，别让导入失败
                ? wavToOpus(f)
                    .then(function (u) { return { dataUrl: u, kind: "audio" }; })
                    .catch(function () {
                      return audioDataUrl(f).then(function (u) {
                        if (onEach) onEach(null, added.length, list.length, new Error("这段 WAV 没能转小，原样存了（成品会很大）"));
                        return { dataUrl: u, kind: "audio" };
                      });
                    })
                : audioDataUrl(f).then(function (u) { return { dataUrl: u, kind: "audio" }; }));
          return step.then(function (r) {
            return persistAsset(baseName(f), r.kind, r.dataUrl, taken, kinds, r.thumb).then(function (name) {
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
    // 列表用的小图：老素材没存过缩略图就退回原图，别因为缺一张就显示空白
    thumbOf: function (name) {
      return dbRun("readonly", function (st) { return st.get(name); }).then(function (v) {
        if (!v) return null;
        if (v.thumb) return v.thumb;
        return v.kind === "image" ? v.dataUrl : null;
      });
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
    // 成功后删掉 inbox 键；SW 失败会留 inbox:error:<ts> 记录 {stage, message}，
    // 导入侧据此区分「真没给文件」和「解析 / 写库失败」。任何异常都吞掉返回，
    // 不许抛到页面顶层（index.html 只 .then/.catch 收结果）。
    importShared: function () {
      var self = this;
      return new Promise(function (resolve) {
        var names = [];
        var error = null;
        function done() { resolve({ names: names, error: error }); }
        try {
          if (!window.indexedDB) { done(); return; }
          dbRun("readonly", function (st) { return st.getAllKeys(); }).then(function (keys) {
            var allKeys = (keys || []).filter(function (k) { return String(k).indexOf("inbox:") === 0; });
            var errKeys = allKeys.filter(function (k) { return String(k).indexOf("inbox:error:") === 0; });
            var inbox = allKeys.filter(function (k) { return String(k).indexOf("inbox:error:") !== 0; });
            // 先读失败标记，读完删掉，避免下次进来重复报同一条失败
            var errChain = errKeys.reduce(function (chain, key) {
              return chain.then(function () {
                return dbRun("readonly", function (st) { return st.get(key); }).then(function (rec) {
                  if (rec && !error) error = { stage: rec.stage || "unknown", message: rec.message || "" };
                  return dbRun("readwrite", function (st) { return st.delete(key); });
                });
              });
            }, Promise.resolve());
            return errChain.then(function () {
              if (!inbox.length) { done(); return; }
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
              }, Promise.resolve()).then(done);
            });
          }).catch(function () { done(); });
        } catch (e) { done(); }
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
      var failed = [];
      return list.reduce(function (chain, n) {
        return chain.then(function () {
          var k = (kinds && kinds[n]) || "image";
          return dbRun("readwrite", function (st) {
            return st.put({ dataUrl: map[n], kind: k }, n);
          }).then(function () {
            // 落库成功才进索引：失败的名字不进，避免索引项指向缺素材体
            if (names.indexOf(n) < 0) { names.push(n); changed = true; }
            kd[n] = k;
          }).catch(function () {
            failed.push(n);
          });
        });
      }, Promise.resolve()).then(function () {
        if (!failed.length) {
          if (changed) idxWrite(names);
          kindWrite(kd);
        } else {
          // 有失败条目就不整体提交索引；索引写本身失败也记进清单，交上层如实上报
          var iok = changed ? idxWrite(names) : true;
          var kok = kindWrite(kd);
          if (!iok || !kok) failed.push("__index__");
        }
        return { ok: list.length - failed.length, fail: failed };
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

  // 从网址导入：电脑端由后端下载（Python 没有跨站限制）。
  // 手机端做不到——浏览器按同源策略读不到别的站点的二进制，硬做只会静默失败。
  // 所以这里直接给一句能照做的指引，而不是假装成功。
  ROUTES["POST /api/import_url"] = function () {
    return jsonRes({
      ok: false,
      message: "手机端不能直接从网址抓图（浏览器跨站限制读不到文件）。"
        + "请先把图存到相册，再用「＋」从相册导入。"
    });
  };

  // P188：编辑器「导入」按钮走 POST /api/import（base64）。离线内核以前只有 import_url，
  // 这条路在手机上必失败（素材进不来、动作单不弹）。补路由，落库复用 persistAsset 同一套。
  ROUTES["POST /api/import"] = function (input, init) {
    var b = bodyOf(init);
    var cat = String(b.category || "");
    var fname = String(b.filename || "素材");
    var b64 = String(b.data_b64 || "");
    if (!b64) return jsonRes({ ok: false, message: "没收到文件内容" }, 400);
    if (cat === "fonts") return jsonRes({ ok: false, message: "手机端暂不收字体素材，请在电脑上导入" });
    var ext = (fname.split(".").pop() || "").toLowerCase();
    var mime = cat === "audio"
      ? ({ wav: "audio/wav", mp3: "audio/mpeg", ogg: "audio/ogg" }[ext] || "audio/mpeg")
      : ({ png: "image/png", jpg: "image/jpeg", jpeg: "image/jpeg", webp: "image/webp" }[ext] || "image/png");
    var url = "data:" + mime + ";base64," + b64;
    var stem = fname.replace(/\.[^.]+$/, "").slice(0, 40) || "素材";
    var taken = idxRead(), kinds = kindRead();
    var kind = cat === "audio" ? "audio" : "image";
    var existed = taken.indexOf(stem) >= 0;
    var pre = Promise.resolve();
    if (b.overwrite && existed) {
      pre = dbRun("readwrite", function (st) { return st.delete(stem); }).then(function () {
        taken.splice(taken.indexOf(stem), 1); delete kinds[stem];
      });
    }
    var th = kind === "image" && window.MYONLThumb
      ? window.MYONLThumb.fromDataUrl(url, 240).catch(function () { return null; })
      : Promise.resolve(null);
    return Promise.all([pre, th]).then(function (r) {
      return persistAsset(stem, kind, url, taken, kinds, r[1]);
    }).then(function (name) {
      return jsonRes({
        ok: true, name: name, path: name,
        overwritten: !!(b.overwrite && existed),
        renamed_from: name !== stem ? stem : undefined
      });
    }).catch(function (e) {
      return jsonRes({ ok: false, message: String((e && e.message) || e) }, 500);
    });
  };

  // 保存是核心：btnSave → /api/file/save {path, content}
  ROUTES["POST /api/file/save"] = function (input, init) {
    var b = bodyOf(init);
    var lib = readLib();
    // 手机本地一个作品只有一个 script.gal，path 用来判断来源，不参与定位
    var p = curProject(lib);
    var next = String(b.content == null ? (b.text || "") : b.content);
    // 落盘之前先把"改之前那一版"留一份：以后要还原，靠的就是它。
    // 存独立 IndexedDB，不动作品库本身；写坏了也只丢快照，正文照旧。
    // P197d：这里改成等快照写完再落正文 —— 原来人手一按就跳走/杀进程，
    // IndexedDB 事务还没提交，那一版就没了，回退时少一格。首版（空稿）也留，
    // 否则改坏之后连"从哪儿开始的"都查不到。
    function commit() {
      p.text = next;
      p.mtime = now();
      writeLib(lib);
      return jsonRes({ ok: true, path: "script.gal", message: "已保存到手机本地" });
    }
    if (p.text !== next && window.MYONLSnapshots) {
      return Promise.resolve(window.MYONLSnapshots.capture({ name: p.name, text: p.text }, next))
        .catch(function () { return 0; })   // 快照写失败也不挡正文
        .then(commit);
    }
    return commit();
  };

  ROUTES["POST /api/script"] = function (input, init) {
    var b = bodyOf(init);
    var lib = readLib();
    var p = curProject(lib);
    var next = String(b.text == null ? "" : b.text);
    // P197d：这条也是写正文的路，原来不拍快照 —— 走这条路改的内容回退不了。
    function commit() {
      p.text = next;
      p.mtime = now();
      writeLib(lib);
      return jsonRes({ ok: true, path: "script.gal" });
    }
    if (p.text !== next && window.MYONLSnapshots) {
      return Promise.resolve(window.MYONLSnapshots.capture({ name: p.name, text: p.text }, next))
        .catch(function () { return 0; })
        .then(commit);
    }
    return commit();
  };

  ROUTES["POST /api/new"] = function (input, init) {
    var b = bodyOf(init);
    var lib = readLib(); var name = String(b.name || "").trim();
    // P202 先建后名：空名不报错，按时间给默认名（之后点顶栏作品名就能改）；P203 改「未命名 N」，时间戳名字前 12 字全一样，卡片上分不清
    if (!name) { name = (window.MYONLTrash && window.MYONLTrash.nextName) ? window.MYONLTrash.nextName(lib) : "未命名"; }
    if (/[\/\\]/.test(name)) return jsonRes({ ok: false, message: "名字里不能有斜杠" }, 400);
    if (findProject(lib, name)) return jsonRes({ ok: false, message: "已经有同名作品了：" + name }, 400);
    // P217：新建给真空白（一幕零台词）。示范内容只在默认那一份「示范案例」里 —— 每建一个都塞 15 句别人的台词，等于逼人先删干净。
    var seed = typeof b.text === "string" && b.text ? b.text : "@label start\n";
    lib.projects.push({ name: name, text: seed, ctime: now(), mtime: now() });
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
      message: (navigator.maxTouchPoints > 0 || window.innerWidth < 720)
        ? "手机版不画画面，先写剧本；想看画面去电脑上打开"
        : "这一版不渲染画面，请用完整版",
    });
  };
  ROUTES["GET /api/thumb"] = function (input) {
    var n = queryOf(input).name || "";
    if (!n) return jsonRes({ ok: false, message: "没给素材名" });
    return window.MYONLAssets.thumbOf(n).then(function (u) {
      return u ? dataUrlToResponse(u) : jsonRes({ ok: false, message: "这条素材没有缩略图" });
    });
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

  // P171：打 APK 要的两样东西。手机上它们跟 index.html 放在同一个 assets 目录，
  // 直接按相对路径取原文件就行 —— 不走后端，也不进内存缓存。
  //
  // 注意必须用绝对 URL：直接 fetch("template.apk") 会被本文件的劫持再抓一次，
  // path 还是 /template.apk，就自己调自己死循环了。
  function fetchAsset(name) {
    var abs = new URL(name, window.location.href).href;
    return origFetch(abs);
  }
  ROUTES["GET /template.apk"] = function () {
    return fetchAsset("template.apk").then(function (r) {
      if (!r.ok) throw new Error("assets 里没有 template.apk");
      return r;
    });
  };
  ROUTES["GET /signkey.json"] = function () {
    return fetchAsset("signkey.json").then(function (r) {
      if (!r.ok) throw new Error("assets 里没有 signkey.json");
      return r;
    });
  };

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
  /** 二进制下载（APK 用）。文本那条走 UTF-8 编码，二进制不能那么转。 */
  function downloadBinary(bytes, filename, mime) {
    var bin = "", CH = 4096;
    for (var i = 0; i < bytes.length; i += CH) {
      bin += String.fromCharCode.apply(null, bytes.subarray(i, i + CH));
    }
    var b64 = btoa(bin);
    var bridge = window.__MYONLSave;
    if (bridge && typeof bridge.save === "function") {
      try {
        bridge.save(filename, mime, b64);
        if (typeof bridge.share === "function") {
          try { bridge.share(filename, mime, b64); } catch (e2) {}
        }
        return;
      } catch (e) { /* 桥坏了再往下退 */ }
    }
    var blob = new Blob([bytes], { type: mime });
    var url = URL.createObjectURL(blob);
    var a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    setTimeout(function () { URL.revokeObjectURL(url); }, 3000);
  }

  /**
   * P171：在手机上直接出一个能装的 APK。
   *
   * 剧本 -> 单文件 html（复用做成成品那条路）-> 换进模板壳 -> 用 WebCrypto 签 v2。
   * 全程不联网、不需要电脑、不需要 Java。
   */
  /** dataURL → 字节。打外链包时每个素材都要落成独立条目，不能留成字符串。 */
  function dataUrlToBytes(uri) {
    var comma = String(uri || "").indexOf(",");
    var b64 = comma >= 0 ? uri.slice(comma + 1) : uri;
    var bin = atob(b64.replace(/\s/g, ""));
    var out = new Uint8Array(bin.length);
    for (var i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
    return out;
  }

  window.__myonlExportApk = function () {
    if (!(window.crypto && window.crypto.subtle)) {
      toast("这个环境没有 WebCrypto，签不了名", true);
      return;
    }
    if (!window.MYONLApkSign) { toast("签名模块没加载，刷新一下", true); return; }
    if (!window.MYONLPack || !window.MYONLParser) { toast("打包器没加载，刷新一下", true); return; }

    var p = curProject();
    toast("正在打 APK…");
    var assetsP = (window.MYONLAssets ? window.MYONLAssets.allSplit()
      : Promise.resolve({ assets: {}, audio: {} }));

    Promise.all([playerSources(), assetsP]).then(function (both) {
      var src = both[0], sp = both[1] || {};
      var assets = sp.assets || {}, audio = sp.audio || {};
      var moviesPack = moviesOf(sp, assets);
      var r = window.MYONLPack.buildPack({
        title: p.name, scriptText: p.text,
        assets: assets, audio: audio, videos: {}, movies: moviesPack,
        config: {}, orientation: "any",
      });
      if (!r.ok) { toast("剧本第 " + r.error.line + " 行：" + r.error.message, true); return; }

      // 30 MB 是个分水岭：以下照旧全内联（一个文件最省事），
      // 以上改走外链——素材作为独立条目进包，HTML 只剩剧本。
      // 不这么做，素材一多，浏览器要先把整个 HTML 读进内存才显示第一句。
      var ext = r.bytes > 30 * 1048576 ? window.MYONLPack.externalize(r.pack) : null;
      if (ext && r.bytes > 300 * 1048576) {
        toast("素材超过 300 MB，手机内存可能顶不住，建议先分成几章", true);
      }
      var html = window.MYONLPack.renderSingle(ext ? ext.pack : r.pack, src);
      var payload = new TextEncoder().encode(html);
      var repl = {};
      repl["assets/game.html"] = payload;
      if (ext) {
        Object.keys(ext.files).forEach(function (rel) {
          repl["assets/" + rel] = dataUrlToBytes(ext.files[rel]);
        });
        toast("素材单独进包（" + Object.keys(ext.files).length + " 个），HTML 只剩剧本");
      }

      return Promise.all([
        fetch("/template.apk").then(function (res) {
          if (!res.ok) throw new Error("模板没找到");
          return res.arrayBuffer();
        }),
        fetch("/signkey.json").then(function (res) {
          if (!res.ok) throw new Error("签名材料没找到");
          return res.json();
        }),
      ]).then(function (pair) {
        return window.MYONLApkSign.signApk(
          new Uint8Array(pair[0]), repl, pair[1]
        );
      }).then(function (apk) {
        downloadBinary(apk, p.name + ".apk", "application/vnd.android.package-archive");
        toast("APK 好了：" + (apk.length / 1048576).toFixed(2) + " MB，传到手机上点开就能装");
      });
    }).catch(function (e) {
      toast("打 APK 失败：" + ((e && e.message) || e), true);
    });
  };

  /** P201：把当前作品编成一份成品 HTML，不落盘。
   *  试玩层与「导出网页版」共用这一条 —— 试玩跑的必须就是导出的那份，不能是第二套实现，
   *  否则「试玩通过、导出翻车」这类事永远查不清。 */
  function buildPackHtml(p) {
    if (!window.MYONLPack || !window.MYONLParser) return Promise.reject(new Error("打包器没加载，刷新一下"));
    var assetsP = (window.MYONLAssets ? window.MYONLAssets.allSplit()
                                      : Promise.resolve({ assets: {}, audio: {} }));
    return Promise.all([playerSources(), assetsP]).then(function (both) {
      var src = both[0], sp = both[1] || {};
      var assets = sp.assets || {}, audio = sp.audio || {}, moviesPack = moviesOf(sp, assets);
      var r = window.MYONLPack.buildPack({
        title: p.name, scriptText: p.text, assets: assets, audio: audio,
        videos: {}, movies: moviesPack, config: {}, orientation: "any",
      });
      if (!r.ok) { var err = new Error(r.error.message || "剧本有问题"); err.line = r.error.line; throw err; }
      return {
        html: window.MYONLPack.renderSingle(r.pack, src), mb: r.fileMb || 0, bytes: r.bytes || 0,
        warn: r.fileWarning || "", warnLevel: r.fileWarningLevel || "",
        images: Object.keys(assets).length, audio: Object.keys(audio).length, movies: Object.keys(moviesPack).length,
      };
    });
  }
  window.__myonlBuildPackHtml = function () { return buildPackHtml(curProject()); };

  window.__myonlExportPack = function () {
    var p = curProject();
    toast("正在把剧本编成成品…");
    buildPackHtml(p).then(function (r) {
      if (r.warnLevel === "hard") toast("⚠ 硬线告警：" + r.warn, true);
      download(r.html, p.name + ".html", "text/html;charset=utf-8");
      var parts = [];
      if (r.images) parts.push(r.images + " 张图");
      if (r.movies) parts.push(r.movies + " 段视频");
      if (r.audio) parts.push(r.audio + " 段音频");
      if (r.warnLevel === "soft") toast("体积提醒：" + r.warn, true);
      toast(parts.length ? ("成品好了：带了 " + parts.join(" + ") + "，约 " + r.mb + " MB")
                         : "成品好了（还没有素材，画面是渐变色）");
    }).catch(function (e) {
      if (e && e.line) toast("剧本第 " + e.line + " 行：" + e.message, true);
      else toast((e && e.message) || "这台设备取不到播放器内核，成品导出请在装好的 APK 里用", true);
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
      return Promise.resolve(false);
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
    return window.MYONLAssets.restore(all, kinds).then(function (r) {
      var failed = (r && r.fail) || [];
      var okCount = (r && typeof r.ok === "number") ? r.ok : Object.keys(all).length;
      if (failed.length) {
        // 部分失败必须如实上报：返回 false，调用方不 reload —— 一刷新就把
        // 「哪几项没写进去」的现场刷没了，用户还以为备份恢复成功。
        var shown = failed.filter(function (x) { return x !== "__index__"; }).slice(0, 3).join("、");
        var tail = failed.length > 3 ? " 等" : "";
        toast("部分素材没恢复：" + failed.length + " 个没写进去" + (shown ? "（" + shown + tail + "）" : "") + "，请重新导入", true);
        return false;
      }
      var parts = [n + " 个作品", okCount + " 个素材（原名放回）"];
      if (legacy) parts.push("旧格式备份：视频类型没带走，若有视频会按图片还原");
      toast("已导入 " + parts.join("、"), legacy);
      return true;
    }).catch(function (e) {
      // 整条链路抛错也算失败：不能再 return true 让调用方照常刷新
      toast("作品导入了，素材没铺完：" + (e.message || e), true);
      return false;
    });
  };

  // 导出条：手机上原来的「导出」分组点开是皮肤参数 + 三个打后端的按钮，
  // 离线时全是废的。所以点到名字含「导出」的分组时，往子页顶部插一条
  function exportBar() {
    var light = document.documentElement.getAttribute("data-theme") === "light";   // 下面几处颜色按深底写的，浅色下浅字配浅底看不见
    var bar = document.createElement("div");
    bar.className = "off-export";
    bar.style.cssText = "padding:12px 14px 14px;border-bottom:1px solid rgba(255,255,255,.08);" +
      "background:rgba(79,140,255,.07)";
    var tip = document.createElement("div");
    tip.style.cssText = "font-size:12px;line-height:1.6;color:" + (light ? "#5a6577" : "#9fb2d0") + ";margin-bottom:10px";
    tip.textContent = "⬇ 网页版；APK 装到手机";
    bar.appendChild(tip);
    // 先让人看见有多大，再决定走哪条：单文件发人，还是打成 APK。
    // 点完才发现"打不开"是最糟的体验。
    var sizeLine = document.createElement("div");
    sizeLine.style.cssText = "font-size:12px;line-height:1.6;color:" + (light ? "#6b7787" : "#8fa3bf") + ";margin:0 0 4px";
    sizeLine.textContent = "正在算体积…";
    bar.appendChild(sizeLine);
    (window.MYONLAssets ? window.MYONLAssets.allSplit() : Promise.resolve({ assets: {}, audio: {} }))
      .then(function (sp) {
        var n = 0, o = Object.assign({}, sp.assets || {}, sp.audio || {});
        Object.keys(o).forEach(function (k) { n += String(o[k] || "").length; });
        var mb = n / 1048576;
        sizeLine.textContent = "现在约 " + mb.toFixed(1) + " MB · " +
          (mb > 30 ? "超过 30 MB，走 APK" : "能单文件发");
      })
      .catch(function () { sizeLine.textContent = ""; });

    [["⬇ 网页版 HTML", "浏览器打开就能玩", function () { window.__myonlExportPack(); }, 1],
     ["⬇ 安装包 APK", "装到手机像 App", function () { window.__myonlExportApk(); }, 1],
     ["↺ 版本历史", "改坏了能退回", function () { if (window.MYONLSnapshotsUI) window.MYONLSnapshotsUI.open(); }, 0],
     ["⬇ 项目备份 .gal", "换设备接着改", function () { window.__myonlExportGal(); }, 0],
     ["⬇ 全部作品 .json", "打成一个文件", function () { window.__myonlExportLib(); }, 0]
    ].forEach(function (it) {
      var b = document.createElement("button");
      b.type = "button";
      // 两行：第一行动作，第二行说清「导出去干什么用、还能不能接着编辑」。
      // 只写「能发人」这种口语，用户既不知道该点哪个，也不知道导完还能不能改。
      var t = document.createElement("span");
      t.textContent = it[0];
      t.style.cssText = "display:block;font-size:14px;font-weight:600";
      var s = document.createElement("span");
      s.textContent = it[1];
      s.style.cssText = "display:block;margin-top:3px;font-size:11.5px;line-height:1.5;font-weight:400;opacity:.72";
      b.appendChild(t); b.appendChild(s);
      var primary = it[3];
      b.style.cssText = "display:block;width:100%;margin:8px 0 0;padding:10px 13px;border-radius:12px;" +
        "border:1px solid rgba(79,140,255," + (primary ? ".55" : ".22") + ");" +
        "background:rgba(79,140,255," + (primary ? ".22" : ".07") + ");" +
        "color:" + (primary ? (light ? "#0f52ba" : "#dce8ff") : (light ? "#42506a" : "#9fb2d0")) + ";" +
        "font-size:14px;line-height:1.3;box-sizing:border-box;text-align:left;min-height:0";
      b.style.height = "auto";
      b.addEventListener("click", it[2]);
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
  // 手机端做游戏真正卡住的地方是素材进不来：相册里翻半天、也不确定压没压。
  // 这条给一个「投递区」——点选文件（相册也在里面），桌面还能直接拖进来；
  // 收什么、压多大、存哪儿全写在框里，不用猜。
  var MAX_FILES = 20;
  var MAX_BYTES = 24 * 1024 * 1024;
  function mbText(n) { return (Math.round((n / 1048576) * 10) / 10).toFixed(1) + " MB"; }

  function assetBar() {
    var light = document.documentElement.getAttribute("data-theme") === "light";
    var bar = document.createElement("div");
    bar.className = "off-assets";
    bar.style.cssText = "padding:12px 14px 14px;border-bottom:1px solid " +
      (light ? "rgba(0,0,0,.08)" : "rgba(255,255,255,.08)") + ";background:rgba(79,140,255,.07)";

    var drop = document.createElement("div");
    drop.style.cssText = "border:1.5px dashed rgba(79,140,255,.52);border-radius:14px;" +
      "background:rgba(79,140,255,.05);padding:16px 12px 15px;text-align:center;cursor:pointer;" +
      "transition:background .15s,border-color .15s;-webkit-tap-highlight-color:transparent";

    var t1 = document.createElement("div");
    t1.style.cssText = "font-size:15px;line-height:1.4;color:" + (light ? "#123d78" : "#dce8ff") + ";font-weight:600";
    t1.textContent = "把文件放进来";

    var btns = document.createElement("div"); btns.style.cssText = "display:flex;gap:8px;justify-content:center;margin-top:10px;flex-wrap:wrap";
    [["从相册选图", "album"], ["导入本地文件", "local"]].forEach(function (b) {
      var el = document.createElement("button");
      el.type = "button"; el.dataset.pick = b[1]; el.textContent = b[0];
      el.style.cssText = "padding:7px 14px;border-radius:9px;border:1px solid rgba(79,140,255,.55);background:rgba(79,140,255,.16);color:" + (light ? "#0f52ba" : "#dce8ff") + ";font-size:13px"; btns.appendChild(el);
    });
    var t2 = document.createElement("div");
    t2.style.cssText = "font-size:12px;line-height:1.75;color:" + (light ? "#66727f" : "#8fa3c0") + ";margin-top:8px";
    t2.innerHTML = "图片原样存（列表用 240 边小图）· WAV 转成 webm · 其余音频原样存<br>" +
      "单个不超过 24 MB，一次最多 " + MAX_FILES + " 个";

    drop.appendChild(t1);
    drop.appendChild(btns);
    drop.appendChild(t2);
    bar.appendChild(drop);

    var input = document.createElement("input");
    input.type = "file";
    input.accept = "image/*,audio/*,video/*,.ttf,.otf,.ttc";
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

    // 整框可点（大目标），两个按钮各自指定要选哪类；相册里没有音频，混进去只会让人以为自己选错了
    drop.addEventListener("click", function (e) {
      var pick = (e.target && e.target.dataset) ? e.target.dataset.pick : "";
      input.accept = pick === "album" ? "image/*,video/*" : "image/*,audio/*,video/*,.ttf,.otf,.ttc";
      input.click();
    });
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
      if (window.MYONLExport) { window.MYONLExport.open(); return; }  // P206：导出开自己的整页，不再插进参数页
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
  // 只兜首页作品卡（?folder=）；素材库列表的 ?name= 是本机素材库真能给图的，必须放行，否则卡片空框。
  try {
    var srcDesc = Object.getOwnPropertyDescriptor(HTMLImageElement.prototype, "src");
    if (srcDesc && srcDesc.set) {
      Object.defineProperty(HTMLImageElement.prototype, "src", {
        configurable: true,
        get: function () { return srcDesc.get.call(this); },
        set: function (v) {
          if (typeof v === "string" && v.indexOf("/api/thumb") >= 0 && v.indexOf("name=") < 0) return;
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
  // 2026-11-19：开机不再弹「本地模式」提示。
  // 这条一开机就横在屏幕下沿，压住底部导航（实测盖掉「导入/设置」两项），
  // 而它说的内容——存在这台设备、不联网——属于「软件详情」，
  // 现在常驻在「设置」里，想确认时自己看，不再开机糊一次。
  // 下面这段保留作历史，不再执行。
  // try {
  //   if (!sessionStorage.getItem("myonl:off:told")) { ... }
  // } catch (e) { /* ignore */ }

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
        window.MYONLAssets.importShared().then(function (res) {
          // 兼容旧返回（纯名字数组）；新返回 {names, error}：error 区分解析失败 / 写库失败
          var names = (res && res.names) || (Array.isArray(res) ? res : []);
          var error = res && !Array.isArray(res) ? res.error : null;
          if (error) {
            var why = error.stage === "parse" ? "解析分享文件失败" : "写入素材库失败";
            toast("分享" + why + "，重新分享一次试试", true);
          } else if (names && names.length) {
            toast("从分享收下 " + names.length + " 个素材：" + names.join("、"));
          } else {
            toast("这次分享里没拿到能用的素材", true);
          }
        }).catch(function () {
          toast("分享进来的素材没存上，重新分享一次试试", true);
        });
      });
    }
  } catch (e) { /* ignore */ }
})();
