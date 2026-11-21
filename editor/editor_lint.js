/* MYONL 剧本体检 / 查找替换 / 过滤 —— P199a 引擎层
 *
 * 纯函数，不碰 DOM、不读 localStorage、不写任何东西。输入永远是一整份剧本文本。
 * 离线模式一个作品就是一份文本（没有 @include 多文件），所以本文件里"全文"就是"工程"。
 * 将来接多文件时，把 text 换成"合并后的全文"即可，规则不用改。
 *
 * 判据定死（UI 只渲染，不再各自判断）：
 *   unregistered   @ 名字 文本，名字不在 @character 定义集        warn  会被静默当旁白，角色名消失
 *   bracket-stray  @[名字]，名字不在定义集                        warn  渲染正常，但角色库里没有
 *   char-unused    @character 定义了却没在任何台词里出现         info  可能是改名后遗留
 *   jump-broken    @jump 目标不存在                              error 走到这里会卡死
 *   label-orphan   @label 没人跳、也不是第一个 label              info
 *   asset-missing  @bg/@cg/@fg/@music/@sfx/@voice/@video 引用的素材不在清单里  warn  成品那一屏缺画面/缺声音
 */
(function () {
  var CMD = ["anim", "bg", "camera", "cg", "chapter", "character", "choice", "elif", "else",
    "end", "fg", "hide", "if", "include", "jump", "label", "music", "plug", "property",
    "set", "sfx", "show", "transition", "video", "voice", "wait"];
  // 首 token 是素材名的指令。@show/@hide 首 token 是角色名，归 unregistered 管，不在这里重复报。
  var ASSET_CMD = ["bg", "cg", "fg", "music", "sfx", "voice", "video"];

  function text0(t) { return String(t == null ? "" : t).replace(/^\uFEFF/, ""); }

  // 把一行拆成「角色名 / 正文起点 / 风格」。前缀（缩进 @ 名字 括号 冒号 空白）永远不参与替换，
  // 所以替换「教室」不会改到角色名，也不会改到 @bg 的参数。
  function sayParts(raw) {
    var i0 = raw.search(/\S/);
    if (i0 < 0) return null;
    if (raw.charAt(i0) !== "@") return null;
    var rest = raw.slice(i0 + 1);

    if (rest.charAt(0) === "[") {
      var dbl = rest.charAt(1) === "[";
      var start = dbl ? 2 : 1;
      var close = -1;
      for (var k = start; k < rest.length; k++) {
        if (rest.charAt(k) === "]") {
          if (dbl) { if (rest.charAt(k + 1) === "]") { close = k; break; } }
          else { close = k; break; }
        }
      }
      if (close < 0) return null;
      var nameEnd = close + (dbl ? 2 : 1);
      var who = rest.slice(start, close).trim();
      if (!who) return null;
      var after = raw.slice(i0 + 1 + nameEnd);
      var lead = (after.match(/^\s*[：:]?\s*/) || [""])[0].length;
      return { who: who, style: dbl ? "nvl" : "bracket", bodyStart: i0 + 1 + nameEnd + lead };
    }

    var m = rest.match(/^(\s+)(\S+)(\s+)([\s\S]*)$/);
    if (m) return {
      who: m[2], style: "plain",
      bodyStart: i0 + 1 + m[1].length + m[2].length + m[3].length
    };
    return null; // "@" 单独一行：下一行整行旁白
  }

  function scan(text, opts) {
    var lines = text0(text).split("\n");
    var chars = {}, labels = {}, jumps = [], rows = [], used = {};
    var i, t, m;

    // 第一遍：先拿定义集，第二遍才判得出"未登记"
    for (i = 0; i < lines.length; i++) {
      t = lines[i].trim();
      if (!t || t.charAt(0) === "#") continue;
      if ((m = t.match(/^@character\s+([^\s#]+)/))) { chars[m[1]] = i + 1; continue; }
      if ((m = t.match(/^@label\s+(\S+)/))) { labels[m[1]] = i + 1; }
    }

    var scene = "开场设置";
    var firstLabel = null;
    for (i = 0; i < lines.length; i++) {
      var raw = lines[i];
      t = raw.trim();
      if (!t || t.charAt(0) === "#") { rows.push({ no: i + 1, kind: "blank" }); continue; }

      if ((m = t.match(/^@label\s+(\S+)/))) {
        scene = m[1];
        if (firstLabel === null) firstLabel = m[1];
        rows.push({ no: i + 1, kind: "label", name: m[1], scene: scene });
        continue;
      }
      if ((m = t.match(/^@character\s+([^\s#]+)/))) {
        rows.push({ no: i + 1, kind: "char", name: m[1], scene: scene });
        continue;
      }
      if ((m = t.match(/^@jump\s+(\S+)/))) {
        jumps.push({ target: m[1], no: i + 1 });
        rows.push({ no: i + 1, kind: "cmd", cmd: "jump", scene: scene, arg: m[1] });
        continue;
      }
      if ((m = t.match(/^@(\w+)/)) && CMD.indexOf(m[1]) >= 0) {
        rows.push({ no: i + 1, kind: "cmd", cmd: m[1], scene: scene, arg: t.slice(m[0].length).trim() });
        continue;
      }
      if (t.charAt(0) === ">") {
        rows.push({ no: i + 1, kind: "option", scene: scene, text: t.replace(/^>\s*/, "") });
        continue;
      }

      var p = sayParts(raw);
      if (p) {
        var body = raw.slice(p.bodyStart);
        var isNar = p.style === "plain" && p.who === "旁白" && !chars[p.who];
        var stray = p.style !== "plain" && !chars[p.who];
        if (!isNar && !stray) used[p.who] = true;
        rows.push({
          no: i + 1, kind: isNar ? "nar" : "say", scene: scene,
          text: body, char: isNar ? null : p.who,
          bodyStart: p.bodyStart, style: p.style,
          unregistered: p.style === "plain" && !isNar && !chars[p.who],
          stray: stray
        });
        continue;
      }

      if (t === "@") {
        rows.push({ no: i + 1, kind: "nar", scene: scene, text: "", char: null, nextLine: true });
        continue;
      }
      rows.push({ no: i + 1, kind: "nar", scene: scene, text: t, char: null });
    }

    var issues = [];
    for (i = 0; i < rows.length; i++) {
      var r = rows[i];
      if (r.kind === "say" && r.unregistered) {
        issues.push({ level: "warn", code: "unregistered", line: r.no, scene: r.scene, name: r.char });
      } else if (r.kind === "say" && r.stray) {
        issues.push({ level: "warn", code: "bracket-stray", line: r.no, scene: r.scene, name: r.char });
      }
    }
    for (var name in chars) {
      if (!used[name]) {
        issues.push({ level: "info", code: "char-unused", line: chars[name], name: name });
      }
    }
    for (i = 0; i < jumps.length; i++) {
      if (!labels[jumps[i].target]) {
        issues.push({ level: "error", code: "jump-broken", line: jumps[i].no, name: jumps[i].target });
      }
    }
    for (var lb in labels) {
      if (lb === firstLabel) continue;
      var hit = false;
      for (i = 0; i < jumps.length; i++) if (jumps[i].target === lb) { hit = true; break; }
      if (!hit) {
        for (i = 0; i < rows.length; i++) {
          var o = rows[i];
          if (o.kind !== "option") continue;
          var tail = String(o.text).split("->").pop().trim();
          if (tail === lb) { hit = true; break; }
        }
      }
      if (!hit) {
        issues.push({ level: "info", code: "label-orphan", line: labels[lb], name: lb });
      }
    }

    // 素材缺失：清单由调用方给（纯函数不读库）；不传就不查，免得还没导素材的新作品满屏报错。
    var known = (opts && opts.assets) || null;
    if (known) {
      var kset = {};
      for (i = 0; i < known.length; i++) kset[String(known[i])] = true;
      for (i = 0; i < rows.length; i++) {
        var q = rows[i];
        if (q.kind !== "cmd" || ASSET_CMD.indexOf(q.cmd) < 0) continue;
        var an = String(q.arg || "").split("#")[0].trim().split(/\s+/)[0].replace(/\.[A-Za-z0-9]+$/, "");
        if (!an || an === "无" || an === "none" || kset[an]) continue;
        issues.push({ level: "warn", code: "asset-missing", line: q.no, scene: q.scene, name: an });
      }
    }

    var order = { error: 0, warn: 1, info: 2 };
    issues.sort(function (a, b) { return (order[a.level] - order[b.level]) || (a.line - b.line); });
    return { lines: lines, rows: rows, chars: chars, labels: labels, jumps: jumps, issues: issues };
  }

  // 体检只回 code + 参数，消息由界面层按语言组装。
  // 这样翻译不会被塞进纯函数里，也不必为了换语言重跑一遍分析。
  function msgOf(i) {
    var T = window.MYONLI18N ? window.MYONLI18N.t : function (k, a) { return k + (a ? " " + a : ""); };
    return T("lint." + i.code, i.name);
  }

  function counts(issues) {
    var c = { error: 0, warn: 0, info: 0 };
    for (var i = 0; i < issues.length; i++) c[issues[i].level]++;
    return c;
  }

  function run(text, opts) {
    var s = scan(text, opts);
    return { issues: s.issues, counts: counts(s.issues), rows: s.rows, chars: s.chars, labels: s.labels };
  }

  // 替换。默认只动台词正文与旁白；指令行、label 行、选项行一个字符都不碰。
  // includeCmd 为 true 时才动它们 —— 改 label 会让 @jump 断链，调用方必须先二次确认。
  function replace(text, find, repl, opts) {
    opts = opts || {};
    var src = text0(text);
    if (!find) return { text: src, count: 0, changed: [] };
    var lines = src.split("\n");
    var s = scan(src);
    var bodyAt = {};
    for (var i = 0; i < s.rows.length; i++) {
      var r = s.rows[i];
      if (r.bodyStart != null) bodyAt[r.no] = r.bodyStart;
    }
    var count = 0, changed = [];
    for (i = 0; i < lines.length; i++) {
      var no = i + 1, raw = lines[i], bs = bodyAt[no];
      if (bs != null) {
        var body = raw.slice(bs);
        var n = body.split(find).length - 1;
        if (n) { lines[i] = raw.slice(0, bs) + body.split(find).join(repl); count += n; changed.push(no); }
        continue;
      }
      if (!opts.includeCmd) continue;
      var t = raw.trim();
      if (!t || t.charAt(0) === "#") continue;
      n = raw.split(find).length - 1;
      if (n) { lines[i] = raw.split(find).join(repl); count += n; changed.push(no); }
    }
    return { text: lines.join("\n"), count: count, changed: changed };
  }

  // 过滤：不给条件返回全部"句"。q.char 按角色名、q.scene 按场景名、
  // q.onlySay 只要台词、q.cmd 只要某类指令、q.text 按正文关键词。
  function filter(text, q) {
    q = q || {};
    var s = scan(text);
    var out = [];
    for (var i = 0; i < s.rows.length; i++) {
      var r = s.rows[i];
      if (r.kind !== "say" && r.kind !== "cmd" && r.kind !== "nar" && r.kind !== "option") continue;
      if (q.cmd) {
        if (r.kind !== "cmd" || r.cmd !== q.cmd) continue;
      } else if (q.onlySay) {
        if (r.kind !== "say") continue;
      }
      if (q.char) {
        if (r.kind !== "say" || r.char !== q.char) continue;
      }
      if (q.scene && r.scene !== q.scene) continue;
      if (q.text && String(r.text || "") .indexOf(q.text) < 0) continue;
      out.push({
        no: r.no, kind: r.kind, char: r.char || null, scene: r.scene,
        text: r.text || r.arg || "", cmd: r.cmd || null,
        whyKind: q.char ? "char" : (q.cmd ? "cmd" : (q.onlySay ? "say" : "")),
        whyArg: q.char || q.cmd || ""
      });
    }
    return { rows: out, total: out.length };
  }

  window.MYONLLint = { run: run, scan: scan, replace: replace, filter: filter, msgOf: msgOf };
})();
