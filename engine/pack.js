/* ============================================================
   MYONL 打包器 · JS 版（手机端"出成品"用）

   作用：把「剧本文本 + 素材 data URI」编成一个 **单文件 HTML**，
   结构和电脑端 engine/webpack.py::build_single 完全一致：
     <div id="boot"> 启动画面
     <div id="stage"><canvas id="game">
     window.__MYONL_PACK__ = {...}
     三个播放器脚本（core / layout / player）
   差别只有两处，都是刻意的：
     1) 不带 PWA manifest / apple-touch-icon —— 手机上是本地文件，图标那套没用；
     2) 不带图片压缩 —— 浏览器里没有 PIL，压缩留在电脑端做。
   所以 JS 出的包会比电脑端大一点，但**能跑、能发、能自己带走**，这是重点。
   ============================================================ */
(function (global) {
  "use strict";

  var BOOT_CSS = [
    "  #boot { position: fixed; inset: 0; z-index: 9; background: #0b0d12;",
    "    display: flex; flex-direction: column; align-items: center; justify-content: center;",
    "    gap: 14px; transition: opacity .32s ease; }",
    "  #boot.gone { opacity: 0; pointer-events: none; }",
    "  #boot .dot { width: 10px; height: 10px; border-radius: 50%; background: #4f8cff;",
    "    animation: bootpulse 1.5s ease-out infinite; }",
    "  #boot .bt { max-width: 78vw; text-align: center;",
    '    font: 500 15px/1.5 -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;',
    "    color: #8a90a2; letter-spacing: .05em; }",
    "  @keyframes bootpulse {",
    "    0% { box-shadow: 0 0 0 0 rgba(79,140,255,.42); }",
    "    100% { box-shadow: 0 0 0 18px rgba(79,140,255,0); }",
    "  }",
  ].join("\n");

  var APPLE_META = [
    '<meta name="apple-mobile-web-app-capable" content="yes">',
    '<meta name="mobile-web-app-capable" content="yes">',
    '<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">',
    '<meta name="apple-mobile-web-app-title" content="{short}">',
    '<meta name="format-detection" content="telephone=no">',
  ].join("\n");

  function esc(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  // 拼标签时不能写字面标签：这段代码本身会被内联进宿主的脚本块里，
  // 字面开头标签会让浏览器把宿主脚本当成双转义状态、提前断开（真踩过：
  // 编辑器单文件里 pack.js 被切成两段，MYONLPack 直接 undefined）。
  var T_OPEN = "<" + "script" + ">";
  var T_CLOSE = "<" + "/" + "script" + ">";

  // 内联进宿主脚本里的文本：掐掉会提前闭合宿主的收尾标签
  function jsSafe(t) {
    return String(t).replace(/<\/script/gi, "<\\/script");
  }

  function charactersOf(ins) {
    var out = [];
    ins.forEach(function (item) {
      if (item && item.op === "character" && item.name) {
        var e = { name: item.name, color: item.color || "#ffffff" };
        if (item.kind && item.kind !== "default") e.kind = item.kind;
        out.push(e);
      }
    });
    return out;
  }

  /* 造 pack。opts:
       title        作品名
       scriptText   .gal 全文
       assets       {名: dataURI}   图片/立绘
       audio        {名: dataURI}   音乐/音效
       videos       {名: [dataURI]} @video 帧序列
       movies       {名: {src, mime}} @video file 真视频文件
       config       播放器配置（可空，播放器有默认值）
       orientation  "any" | "portrait" | "landscape"
       cover        封面素材名（空则播放器走渐变）
     返回 {ok, pack, error, bytes, fileMb, fileWarning}。 */

  // 单文件体积口径与电脑端 webpack.py 一致：40 MB 起提醒，80 MB 硬线。
  var FILE_SOFT_WARN = 40 * 1024 * 1024;
  var FILE_HARD_WARN = 80 * 1024 * 1024;

  function dataUriByteLen(uri) {
    // data URI 的 base64 部分比原文件胖 37%；算体积按成品里真正落盘的字节估。
    var comma = String(uri || "").indexOf(",");
    var b64 = comma >= 0 ? uri.slice(comma + 1) : uri;
    return Math.ceil(b64.replace(/\s/g, "").length * 3 / 4);
  }

  function sizeReport(pack) {
    var bytes = 0;
    Object.keys(pack.assets || {}).forEach(function (k) { bytes += dataUriByteLen(pack.assets[k]); });
    Object.keys(pack.audio || {}).forEach(function (k) { bytes += dataUriByteLen(pack.audio[k]); });
    Object.keys(pack.videos || {}).forEach(function (k) {
      (pack.videos[k] || []).forEach(function (u) { bytes += dataUriByteLen(u); });
    });
    Object.keys(pack.movies || {}).forEach(function (k) {
      var mv = pack.movies[k];
      if (mv && mv.src) bytes += dataUriByteLen(mv.src);
    });
    var fileMb = Math.round(bytes / (1024 * 1024) * 10) / 10;
    var fileWarning = "";
    // 告警等级与电脑端 webpack.py 同一口径：soft=超 40MB 提醒，hard=超 80MB 硬线。
    var fileWarningLevel = "";
    if (bytes > FILE_HARD_WARN) {
      fileWarningLevel = "hard";
      fileWarning = "单文件约 " + fileMb + " MB，超过 80 MB 硬线。手机要先把整个文件读进内存才显示第一句，"
        + "这个体积大概率白屏或闪退；视频内联成 base64 还会再胖约 37%，建议删素材或拆章。";
    } else if (bytes > FILE_SOFT_WARN) {
      fileWarningLevel = "soft";
      fileWarning = "单文件约 " + fileMb + " MB。低端机打开会明显慢一拍，还能用，但别再加素材了"
        + "（视频内联成 base64 会再胖约 37%）。";
    }
    return { bytes: bytes, fileMb: fileMb, fileWarning: fileWarning,
             fileWarningLevel: fileWarningLevel };
  }

  function buildPack(opts) {
    opts = opts || {};
    if (!global.MYONLParser) {
      return { ok: false, pack: null, error: { line: 0, message: "解析器没加载（engine/parser.js 缺失）" } };
    }
    var r = global.MYONLParser.parseText(opts.scriptText || "");
    if (!r.ok) return { ok: false, pack: null, error: r.error };

    var assets = opts.assets || {};
    var pack = {
      version: 1,
      title: opts.title || "未命名作品",
      script: "script.gal",
      characters: charactersOf(r.instructions),
      config: opts.config || {},
      assets: assets,
      audio: opts.audio || {},
      videos: opts.videos || {},
      movies: opts.movies || {},
      ins: r.instructions,
      orientation: ["portrait", "landscape"].indexOf(opts.orientation) >= 0 ? opts.orientation : "any",
      cover: opts.cover || "",
      unsupported: [],
    };
    if (!pack.cover) {
      // 和电脑端同一口味：挑第一张名字里带 bg 的图当封面；没有就留空走渐变
      var names = Object.keys(assets);
      for (var i = 0; i < names.length; i++) {
        if (/bg/i.test(names[i])) { pack.cover = names[i]; break; }
      }
    }
    var rep = sizeReport(pack);
    return { ok: true, pack: pack, error: null, bytes: rep.bytes,
             fileMb: rep.fileMb, fileWarning: rep.fileWarning,
             fileWarningLevel: rep.fileWarningLevel };
  }

  /* 渲染成单文件 HTML。playerSrc = [core.js 文本, layout.js 文本, player.js 文本] */
  function renderSingle(pack, playerSrc) {
    var title = pack && pack.title ? pack.title : "MYONL";
    var short = String(title).trim().slice(0, 12) || "MYONL";
    var orient = ["portrait", "landscape"].indexOf(pack.orientation) >= 0 ? pack.orientation : "any";
    var scripts = (playerSrc || []).map(function (s) {
      return T_OPEN + jsSafe(s) + T_CLOSE;
    }).join("\n");

    return "<!DOCTYPE html>\n" +
      '<html lang="zh-CN">\n<head>\n<meta charset="utf-8">\n' +
      '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover,user-scalable=no">\n' +
      '<meta name="theme-color" content="#14161f">\n' +
      '<meta name="myonl-orientation" content="' + orient + '">\n' +
      APPLE_META.replace("{short}", esc(short)) + "\n" +
      "<title>" + esc(title) + "</title>\n<style>\n" +
      "  html, body { margin: 0; padding: 0; background: #0b0d12; overflow: hidden;\n" +
      "    -webkit-tap-highlight-color: transparent; user-select: none; }\n" +
      "  #stage { position: fixed; inset: 0; display: flex; align-items: center; justify-content: center; }\n" +
      "  #game { display: block; background: #000; box-shadow: 0 0 40px rgba(0,0,0,.6); }" + BOOT_CSS + "\n" +
      "</style>\n</head>\n<body>\n" +
      '<div id="boot"><span class="dot"></span><span class="bt">' + esc(title) + "</span></div>\n" +
      '<div id="stage"><canvas id="game"></canvas></div>\n' +
      T_OPEN + "window.__MYONL_PACK__=" + jsSafe(JSON.stringify(pack)) + ";" + T_CLOSE + "\n" +
      scripts + "\n</body>\n</html>\n";
  }

  /* 外链模式：把 pack 里的 dataURI 全部换成相对路径，并交出该写盘的文件表。

     为什么要有这一条：单文件内联在 30 MB 上就开始崩（浏览器得先把整个
     HTML 读进内存才显示第一句）。外链模式下剧本里只留 "img/bg.png" 这种
     路径，素材以独立文件躺在旁边——播放器的 img.src 本来就认相对路径，
     所以播放器一行都不用改，改的只是"素材怎么过去"。

     返回 {pack, files}：pack 是替换后的新对象（原对象不动），
     files 是 {"img/bg.png": dataURI}，调用方负责把它真的写到磁盘/塞进 APK。
     prefix 给空串即可——APK 里 assets/ 本身就是根，game.html 和 img/ 同级。 */
  function externalize(pack, prefix) {
    prefix = prefix || "";
    var files = {};
    var out = {};
    Object.keys(pack || {}).forEach(function (k) { out[k] = pack[k]; });
    function take(kind, name, uri) {
      var rel = prefix + kind + "/" + name;
      files[rel] = uri;
      return rel;
    }
    out.assets = {};
    Object.keys(pack.assets || {}).forEach(function (n) {
      out.assets[n] = take("img", n, pack.assets[n]);
    });
    out.audio = {};
    Object.keys(pack.audio || {}).forEach(function (n) {
      out.audio[n] = take("audio", n, pack.audio[n]);
    });
    // 视频同一条规则；movies 的值是 {src,mime}，只换 src 不丢 mime
    out.movies = {};
    Object.keys(pack.movies || {}).forEach(function (n) {
      var mv = pack.movies[n] || {};
      out.movies[n] = { src: take("movie", n, mv.src), mime: mv.mime || "video/mp4" };
    });
    return { pack: out, files: files };
  }

  global.MYONLPack = {
    buildPack: buildPack,
    renderSingle: renderSingle,
    externalize: externalize,
  };
})(typeof window !== "undefined" ? window : globalThis);
