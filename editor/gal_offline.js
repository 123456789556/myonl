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
    try {
      var raw = localStorage.getItem(LIB_KEY);
      if (raw) {
        var lib = JSON.parse(raw);
        if (lib && lib.projects && lib.projects.length) return lib;
      }
    } catch (e) { /* 坏数据或禁用，重建 */ }
    memLib = blankLib();
    writeLib(memLib);
    return memLib;
  }
  function writeLib(lib) {
    memLib = lib;
    try { localStorage.setItem(LIB_KEY, JSON.stringify(lib)); }
    catch (e) {
      // 超配额：保住当前作品，砍掉最旧的
      try {
        lib.projects.sort(function (a, b) { return (b.mtime || 0) - (a.mtime || 0); });
        lib.projects = lib.projects.slice(0, 8);
        localStorage.setItem(LIB_KEY, JSON.stringify(lib));
      } catch (e2) { toast("本地存储写不进去了，先导出剧本再继续"); }
    }
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
    return jsonRes({ ok: true, assets: { images: [], videos: [], anims: [], audio: [], fonts: [] } });
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

  // 预览大图：手机上直接说「看中间舞台」，别让它挂
  ROUTES["POST /api/preview"] = function () {
    return jsonRes({ ok: false, message: "手机上用中间的舞台看效果" });
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
  function download(text, filename) {
    var blob = new Blob([text], { type: "text/plain;charset=utf-8" });
    try {
      if (navigator.canShare && navigator.share) {
        var file = new File([blob], filename, { type: "text/plain" });
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
      toast("已导出 " + filename);
    } catch (e) {
      toast("导出失败，改用复制全文", true);
    }
  }
  window.__myonlExportGal = function () {
    var p = curProject();
    download(p.text, p.name + ".gal");
  };
  window.__myonlExportLib = function () {
    download(JSON.stringify(readLib(), null, 1), "myonl-作品库.json");
  };
  window.__myonlImportLib = function (json) {
    try {
      var lib = typeof json === "string" ? JSON.parse(json) : json;
      if (!lib || !lib.projects || !lib.projects.length) throw new Error("格式不对");
      writeLib(lib);
      toast("已导入 " + lib.projects.length + " 个作品");
      return true;
    } catch (e) { toast("导入失败：" + e, true); return false; }
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
    tip.textContent = "手机本地模式：作品存在这台设备里，不上云。剧本现在就能带走；" +
      "要打成能直接双击玩的成品，得在电脑上打包——数据线把 .gal 拷过去即可。";
    bar.appendChild(tip);

    [["拿出这个作品（.gal）", function () { window.__myonlExportGal(); }],
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
  document.addEventListener("click", function (e) {
    var row = e.target && e.target.closest ? e.target.closest(".m-group-row, .uid-tab, .m-tab, button") : null;
    if (!row) return;
    if (/导出/.test(row.textContent || "")) {
      // 打开中心页有 260/760 两次动画修补，跟着补两次
      setTimeout(injectExportBar, 320);
      setTimeout(injectExportBar, 820);
    }
  }, true);

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
      setTimeout(function () { toast("手机本地模式：作品存在这台设备里"); }, 500);
    }
  } catch (e) { /* ignore */ }
})();
