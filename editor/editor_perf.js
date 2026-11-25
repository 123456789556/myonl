/* 演出指令面板 —— @voice / @cg / @fg / @camera / @transition 的参数表单（P273）
 *
 * 为什么单独一个文件：editor_scene.js 已经顶到 1207 行预算上限。
 *
 * 这几年这 5 条只能在源码里整行改：卡片视图给个中文名和一句摘要，
 * 想改 x= / alpha= / 秒数 就得切走去看语法。这个文件把参数拆成输入框。
 *
 * 契约：
 *   scan(line)        一行文本 → 对象（认不出返回 null，绝不吃掉别人的行）
 *   line(p)           对象 → 一行文本（缺省值不写进命令，保持原文干净）
 *   render(model, t)  只产出 DOM，不接管事件
 *   read(formEl, m)   从 DOM 取值，空名字的整条丢弃（等于删掉）
 *   fixVoices(lines)  @voice 必须紧跟台词：位置不对的搬到上一个台词后面，前面没有台词就丢掉并计数
 */
(function () {
  "use strict";

  var DIRS = { "左": "左", "右": "右", "上": "上", "下": "下", left: "左", right: "右", up: "上", down: "下" };
  var SAY_RE = /^@\s+\S/;
  var SAY_BR = /^@\[/;
  var VOICE_RE = /^@voice\b/;

  var LABEL = { voice: "配音", cg: "CG", fg: "前景", camera: "镜头", transition: "转场" };
  var OPS = ["voice", "cg", "fg", "camera", "transition"];

  function num(v, d) { var n = Number(v); return isFinite(n) ? n : d; }
  function fmt(n) { return String(Number(n)); }
  function clamp01(n) { return Math.max(0, Math.min(1, n)); }
  function isSay(l) { return SAY_RE.test(l) || SAY_BR.test(l); }

  // ---------- 解析 ----------
  function scan(t) {
    var b = String(t == null ? "" : t).trim();
    var m;
    if ((m = b.match(/^@voice\s+(\S+)$/))) return { op: "voice", sound: m[1] };
    if ((m = b.match(/^@cg\s+(\S+)$/))) return { op: "cg", name: m[1] };
    if ((m = b.match(/^@fg\s+(.+)$/))) {
      var toks = m[1].trim().split(/\s+/);
      var name = toks.shift() || "";
      var x = 0, y = 0, a = 1;
      toks.forEach(function (tk) {
        var k = tk.split("=")[0], v = tk.slice(k.length + 1);
        if (k === "x") x = num(v, 0);
        else if (k === "y") y = num(v, 0);
        else if (k === "alpha") a = clamp01(num(v, 1));
      });
      if (name === "none") name = "无";
      return { op: "fg", name: name, x: x, y: y, alpha: a };
    }
    if ((m = b.match(/^@camera\s+(\S+)\s*(.*)$/))) {
      var ck = m[1];
      if (ck !== "pan" && ck !== "zoom" && ck !== "shake" && ck !== "reset") return null;
      var ca = (m[2] || "").trim().split(/\s+/).filter(Boolean);
      var p = { op: "camera", kind: ck };
      if (ck === "pan") { p.dir = DIRS[ca[0]] || "左"; p.secs = num(ca[1], 1); }
      else if (ck === "zoom") { p.from = num(ca[0], 1); p.to = num(ca[1], 1.2); }
      else if (ck === "shake") { p.secs = num(ca[0], 0.4); p.amp = num(ca[1], 12); }
      else { p.secs = num(ca[0], 0.6); }
      return p;
    }
    if ((m = b.match(/^@transition\s+(\S+)\s*(.*)$/))) {
      var tk = m[1];
      if (tk !== "dissolve" && tk !== "wipe" && tk !== "slide") return null;
      var ta = (m[2] || "").trim().split(/\s+/).filter(Boolean);
      var q = { op: "transition", kind: tk };
      if (tk === "dissolve") q.secs = num(ta[0], 0.6);
      else { q.dir = DIRS[ta[0]] || "左"; q.secs = num(ta[1], 0.6); }
      return q;
    }
    return null;
  }

  // ---------- 反拼 ----------
  function line(p) {
    if (!p) return "";
    if (p.op === "voice") return "@voice " + (p.sound || "");
    if (p.op === "cg") return "@cg " + (p.name || "");
    if (p.op === "fg") {
      var s = "@fg " + (p.name || "无");
      if (num(p.x, 0)) s += " x=" + fmt(num(p.x, 0));
      if (num(p.y, 0)) s += " y=" + fmt(num(p.y, 0));
      var a = clamp01(num(p.alpha, 1));
      if (a !== 1) s += " alpha=" + fmt(a);
      return s;
    }
    if (p.op === "camera") {
      if (p.kind === "pan") return "@camera pan " + (p.dir || "左") + " " + fmt(num(p.secs, 1));
      if (p.kind === "zoom") return "@camera zoom " + fmt(num(p.from, 1)) + " " + fmt(num(p.to, 1.2));
      if (p.kind === "shake") return "@camera shake " + fmt(num(p.secs, 0.4)) + " " + fmt(num(p.amp, 12));
      return "@camera reset " + fmt(num(p.secs, 0.6));
    }
    if (p.op === "transition") {
      if (p.kind === "dissolve") return "@transition dissolve " + fmt(num(p.secs, 0.6));
      return "@transition " + p.kind + " " + (p.dir || "左") + " " + fmt(num(p.secs, 0.6));
    }
    return "";
  }

  // ---------- 渲染 ----------
  function esc(v) {
    return String(v == null ? "" : v).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  function dirSel(value) {
    return '<select class="sf-p-dir">' + ["左", "右", "上", "下"].map(function (d) {
      return '<option value="' + d + '"' + (value === d ? " selected" : "") + ">" + d + "</option>";
    }).join("") + "</select>";
  }

  function kindSel(list, value) {
    return '<select class="sf-p-kind">' + list.map(function (k) {
      return '<option value="' + k[0] + '"' + (value === k[0] ? " selected" : "") + ">" + k[1] + "</option>";
    }).join("") + "</select>";
  }

  function numInput(cls, value, step, min, max, ph) {
    return '<input class="' + cls + '" type="number" inputmode="decimal" step="' + step + '"' +
      (min == null ? "" : ' min="' + min + '"') + (max == null ? "" : ' max="' + max + '"') +
      ' placeholder="' + esc(ph || "") + '" value="' + esc(value == null ? "" : value) + '">';
  }

  function card(p, idx) {
    var del = '<button type="button" class="icon-btn sf-del" data-kind="perf" data-i="' + idx + '" title="删掉这条演出">✕</button>';
    var h = '<div class="sf-perf" data-i="' + idx + '" data-op="' + p.op + '">';
    function row(tag, ctl, tail) {
      return '<div class="sf-prow"><span class="sf-ptag">' + tag + "</span>" + ctl + (tail || "") + "</div>";
    }
    if (p.op === "voice") {
      h += row("配音", '<input class="sf-p-sound" list="sfPerfAudio" placeholder="音频名" value="' + esc(p.sound) + '">', del);
    } else if (p.op === "cg") {
      h += row("CG", '<input class="sf-p-name" list="sfPerfImage" placeholder="CG 名称" value="' + esc(p.name) + '">', del);
    } else if (p.op === "fg") {
      h += row("前景", '<input class="sf-p-name" list="sfPerfImage" placeholder="素材名 / 无" value="' + esc(p.name) + '">',
        '<button type="button" class="icon-btn sf-p-clear" title="清掉前景">清除</button>' + del);
      h += row("位置", numInput("sf-p-x", p.x, "1", null, null, "x") +
        numInput("sf-p-y", p.y, "1", null, null, "y") +
        numInput("sf-p-alpha", p.alpha, "0.1", 0, 1, "透明度"));
    } else if (p.op === "camera") {
      h += row("镜头", kindSel([["pan", "摇镜"], ["zoom", "缩放"], ["shake", "震动"], ["reset", "复位"]], p.kind), del);
      if (p.kind === "pan") {
        h += row("往哪", dirSel(p.dir) + numInput("sf-p-secs", p.secs, "0.1", 0.1, null, "秒"));
      } else if (p.kind === "zoom") {
        h += row("缩放", numInput("sf-p-from", p.from, "0.05", 0.1, null, "起始") +
          numInput("sf-p-to", p.to, "0.05", 0.1, null, "结束"));
      } else if (p.kind === "shake") {
        h += row("震动", numInput("sf-p-secs", p.secs, "0.1", 0.1, null, "秒") +
          numInput("sf-p-amp", p.amp, "1", 0.1, null, "幅度"));
      } else {
        h += row("复位", numInput("sf-p-secs", p.secs, "0.1", 0.1, null, "秒"));
      }
    } else if (p.op === "transition") {
      h += row("转场", kindSel([["dissolve", "淡入淡出"], ["wipe", "擦除"], ["slide", "推移"]], p.kind), del);
      if (p.kind === "dissolve") {
        h += row("时长", numInput("sf-p-secs", p.secs, "0.1", 0.1, null, "秒"));
      } else {
        h += row("方向", dirSel(p.dir) + numInput("sf-p-secs", p.secs, "0.1", 0.1, null, "秒"));
      }
    }
    h += '<div class="sf-pcmd">' + esc(line(p)) + "</div>";
    h += "</div>";
    return h;
  }

  function render(model, t) {
    model.perf = model.perf || [];
    var live = model.perf.filter(function (p) { return !p.del; });
    var h = [];
    h.push('<details class="sf-fold sf-perf-box"' + (model.perfOpen ? " open" : "") + '><summary class="sf-sec">演出 <span class="sf-hint">配音 · CG · 前景 · 镜头 · 转场' +
      (live.length ? " · " + live.length + " 条" : "") + "</span></summary>");
    h.push('<div class="sf-padd">' + OPS.map(function (o) {
      return '<button type="button" class="icon-btn sf-p-add" data-perf="' + o + '">＋' + LABEL[o] + "</button>";
    }).join("") + "</div>");
    h.push('<div id="sfPerf">');
    model.perf.forEach(function (p, i) { if (!p.del) h.push(card(p, i)); });
    h.push("</div></details>");
    var imgs = (t && t.images) || [], auds = (t && t.audios) || [], vids = (t && t.videos) || [];
    var uniq = function (a) { var s = {}; return a.filter(function (x) { if (s[x]) return false; s[x] = 1; return true; }); };
    h.push('<datalist id="sfPerfImage">' + uniq(imgs.concat(vids)).map(function (x) {
      return '<option value="' + esc(x) + '">';
    }).join("") + "</datalist>");
    h.push('<datalist id="sfPerfAudio">' + uniq(auds).map(function (x) {
      return '<option value="' + esc(x) + '">';
    }).join("") + "</datalist>");
    return h.join("");
  }

  // ---------- 取值 ----------
  function val(el, cls) { var e = el.querySelector("." + cls); return e ? String(e.value || "").trim() : ""; }
  function numOf(el, cls, d) { var s = val(el, cls); return s === "" ? d : num(s, d); }

  function read(host, model) {
    var out = [];
    model.perf = model.perf || [];
    var els = host.querySelectorAll(".sf-perf");
    for (var i = 0; i < els.length; i++) {
      var el = els[i];
      var idx = parseInt(el.getAttribute("data-i"), 10);
      var base = (idx >= 0 && model.perf[idx]) ? model.perf[idx] : {};
      var op = el.getAttribute("data-op");
      if (op === "voice") {
        var snd = val(el, "sf-p-sound");
        if (!snd) continue;                              // 空名字 = 删掉，不留 "@voice " 这种坏行
        out.push({ i: base.i, op: "voice", sound: snd });
      } else if (op === "cg") {
        var nm = val(el, "sf-p-name");
        if (!nm) continue;
        out.push({ i: base.i, op: "cg", name: nm });
      } else if (op === "fg") {
        var fname = val(el, "sf-p-name");
        if (!fname) continue;
        out.push({ i: base.i, op: "fg", name: fname,
          x: Math.round(numOf(el, "sf-p-x", 0)),
          y: Math.round(numOf(el, "sf-p-y", 0)),
          alpha: clamp01(numOf(el, "sf-p-alpha", 1)) });
      } else if (op === "camera") {
        var ck = val(el, "sf-p-kind") || (base.kind || "pan");
        var cp = { i: base.i, op: "camera", kind: ck };
        if (ck === "pan") { cp.dir = val(el, "sf-p-dir") || "左"; cp.secs = Math.max(0.1, numOf(el, "sf-p-secs", 1)); }
        else if (ck === "zoom") { cp.from = Math.max(0.1, numOf(el, "sf-p-from", 1)); cp.to = Math.max(0.1, numOf(el, "sf-p-to", 1.2)); }
        else if (ck === "shake") { cp.secs = Math.max(0.1, numOf(el, "sf-p-secs", 0.4)); cp.amp = Math.max(0.1, numOf(el, "sf-p-amp", 12)); }
        else { cp.secs = Math.max(0.1, numOf(el, "sf-p-secs", 0.6)); }
        out.push(cp);
      } else if (op === "transition") {
        var tk = val(el, "sf-p-kind") || (base.kind || "dissolve");
        var tp = { i: base.i, op: "transition", kind: tk };
        if (tk === "dissolve") tp.secs = Math.max(0.1, numOf(el, "sf-p-secs", 0.6));
        else { tp.dir = val(el, "sf-p-dir") || "左"; tp.secs = Math.max(0.1, numOf(el, "sf-p-secs", 0.6)); }
        out.push(tp);
      }
    }
    return out;
  }

  // ---------- @voice 归位 ----------
  // 归位规则：每条配音挂到它最近的台词上（先看前一句，前面没有就挂到后面第一句）；
  // 整场一条台词都没有 = 这条配音没地方挂，丢掉并计数（宁可少演一次配音，也不写出一行必报错的指令）。
  function fixVoices(lines) {
    var says = [], pending = {}, moved = 0, dropped = 0;
    lines.forEach(function (l, i) { if (isSay(l)) says.push(i); });
    lines.forEach(function (l, i) {
      if (!VOICE_RE.test(l)) return;
      var k = -1;
      for (var j = i - 1; j >= 0; j--) if (isSay(lines[j])) { k = j; break; }
      if (k < 0) for (var f = i + 1; f < lines.length; f++) if (isSay(lines[f])) { k = f; break; }
      if (k < 0) { dropped++; return; }
      (pending[k] = pending[k] || []).push(l);
      if (i !== k + 1) moved++;                        // 原本就在台词正下方的不算搬
    });
    var out = [];
    lines.forEach(function (l, i) {
      if (VOICE_RE.test(l)) return;                    // 配音不按原位置输出，统一挂在台词后
      out.push(l);
      if (pending[i]) out.push.apply(out, pending[i]);
    });
    return { lines: out, moved: moved, dropped: dropped };
  }

  window.MYONLPerf = { scan: scan, line: line, render: render, read: read, fixVoices: fixVoices,
    LABEL: LABEL, OPS: OPS };
})();
