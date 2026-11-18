/* ============================================================
   MYONL 解析器 · JS 版（手机端离线出成品用）

   目标不是"另写一个引擎"，而是**逐条复刻 engine/parser.py 的产出**：
   同一份 .gal 文本，Python 版和这里产出的指令数组必须逐字段一致
   （唯一允许不同的是 file 字段：JS 端单文件，没有跨文件定位）。

   对拍脚本 tools/pack_diff.py 会拿 games/ 下所有工程跑两遍比一遍。
   不一致就是 bug，不许"差不多"。

   已覆盖（5 个真实工程用到的全部）：
     character / set / bg / music / sfx / chapter / label / say /
     show / hide / choice / jump / if / end / wait
   未覆盖（遇到就抛清楚的中文错误，不静默走偏）：
     voice / video / anim / fg / cg / camera / transition / plug / @include
   ============================================================ */
(function (global) {
  "use strict";

  // Python 的 \w 在 re.UNICODE 下包含中文（"标签_结局"、"变量 信任"都靠它），
  // JS 的 \w 只有 [A-Za-z0-9_]，所以这里显式把 CJK 区间加进去。
  var W = "[0-9A-Za-z_\\u4e00-\\u9fff\\u3400-\\u4dbf]";
  var HEX6 = /#[0-9a-fA-F]{6}(?![0-9a-fA-F])/;
  var COLOR = /^#[0-9a-fA-F]{6}$/;
  var NAME = new RegExp("^" + W + "+$");
  var SET = new RegExp("^(" + W + "+)\\s*(\\+=|-=|=)\\s*(-?\\d+(?:\\.\\d+)?)$");
  var SET_EXPR = new RegExp("^(" + W + "+)\\s*(\\+=|-=|=)\\s*(.+)$");
  var SET_STR = new RegExp('^(' + W + '+)\\s*=\\s*"([^"]*)"$');
  var COND = new RegExp("^(" + W + "+?)\\s*(==|!=|>=|<=|>|<)\\s*(-?\\d+(?:\\.\\d+)?)$");
  var INT_ARG = /^-?\d+$/;
  var NUMBER = /^-?\d+(?:\.\d+)?$/;

  function num(s) {
    var v = Number(s);
    return v === Math.floor(v) ? Math.floor(v) : v;
  }

  // 等价 Python 的 s.split(None, 1)：只切一刀，第二段保留剩余全部。
  // 注意 JS 的 split(re, 2) 是"最多 2 个元素"，会把 "名字 颜色" 截成 ["名字"]，
  // 这正是第一版对拍 5/5 全崩的原因，别再改回去。
  function cut1(s) {
    var m = /^(\S+)(?:[ \t]+([\s\S]*))?$/.exec(s);
    return m ? [m[1], m[2] === undefined ? "" : m[2]] : ["", ""];
  }

  function synErr(line, message) {
    var e = new Error(message);
    e.line = line;
    e.galMessage = message;
    return e;
  }

  // 去注释：整行 # 注释、行内「空白+#」注释；# 后接 6 位十六进制视为颜色
  function stripComment(line) {
    var ls = line.replace(/^[ \t]+/, "");
    if (ls.charAt(0) === "#" && !HEX6.test(ls)) return "";
    var pos = 0;
    while (true) {
      var idx = line.slice(pos).search(/\s#/);
      if (idx < 0) return line.replace(/\s+$/, "");
      var at = pos + idx;          // 空白的位置
      var hashAt = at + 1;         // # 的位置
      if (HEX6.test(line.slice(hashAt))) { pos = hashAt + 1; continue; }
      return line.slice(0, at).replace(/\s+$/, "");
    }
  }

  function collect(text) {
    var out = [];
    var rows = text.split(/\r?\n/);
    for (var n = 1; n <= rows.length; n++) {
      var raw = rows[n - 1];
      var c = stripComment(raw);
      if (!c.trim()) continue;
      var lead = c.length - c.replace(/^[\t ]+/, "").length;
      var head = c.slice(0, lead);
      if (head.indexOf("\t") >= 0) c = head.replace(/\t/g, "    ") + c.slice(lead);
      var indent = c.length - c.replace(/^ +/, "").length;
      var stripped = c.trim();
      if (stripped.split(/\s+/, 1)[0] === "@include") {
        throw synErr(n, "@include 只能出现在电脑端（手机端作品是单文件，没有别的文件可引入）");
      }
      out.push({ n: n, indent: indent, text: stripped });
    }
    return out;
  }

  function Parser(text) {
    this.lines = collect(text);
    this.i = 0;
    this.characters = {};
    this.labels = {};
  }

  Parser.prototype.peek = function () { return this.lines[this.i]; };
  Parser.prototype.advance = function () { return this.lines[this.i++]; };

  Parser.prototype.block = function (base) {
    var out = [];
    while (this.i < this.lines.length) {
      var L = this.lines[this.i];
      if (L.indent < base) break;
      if (L.indent > base) throw synErr(L.n, "意外的缩进：该行不属于任何 @if 或 @choice 语句块");
      out.push(this.one());
    }
    return out;
  };

  Parser.prototype.indented = function (parentLine, parentIndent, who) {
    if (this.i >= this.lines.length || this.lines[this.i].indent <= parentIndent) {
      throw synErr(parentLine, who + " 后面需要一段缩进的语句块（至少一行，且比本行多缩进）");
    }
    return this.block(this.lines[this.i].indent);
  };

  // @elif / @else 链
  Parser.prototype.elseBlock = function (indent) {
    if (this.i >= this.lines.length) return null;
    var L = this.lines[this.i];
    if (L.indent !== indent || L.text.charAt(0) !== "@") return null;
    var head = L.text.slice(1).split(/\s+/, 1)[0];
    if (["else:", "else", "elif", "elif:"].indexOf(head) < 0) return null;
    var rest = L.text.slice(1).slice(head.length).trim();
    if (head === "else:" || head === "else") {
      if (rest !== "" && rest !== ":") throw synErr(L.n, "@else 不需要条件（写法是单独一行 @else:）");
      this.i++;
      return this.indented(L.n, indent, "@else");
    }
    if (rest.slice(-1) !== ":") throw synErr(L.n, '@elif 的条件后面要以 ":" 结尾，并接一段缩进语句块');
    var cond = this.parseCond(rest.slice(0, -1).trim(), L.n);
    this.i++;
    var body = this.indented(L.n, indent, "@elif");
    var nested = { op: "if", cond: cond, body: body, line: L.n };
    var deeper = this.elseBlock(indent);
    if (deeper !== null) nested.else_body = deeper;
    return [nested];
  };

  Parser.prototype.one = function () {
    var L = this.advance();
    var n = L.n, content = L.text;

    if (content.charAt(0) !== "@") throw synErr(n, '每条指令必须以 "@" 开头');
    var rest = content.slice(1);
    var body = rest.trim();

    if (!body) return this.sayNext(n);
    if (body.charAt(0) === "[") return this.sayBracket(n, body);
    if (/^\s/.test(rest)) return this.say(body);

    var parts = cut1(rest);
    var head = parts[0];
    var argstr = parts[1].trim();

    if (head === "character") {
      var ps = argstr.split(/\s+/);
      if (ps.length !== 2 && ps.length !== 3) {
        throw synErr(n, "@character 需要 2 个参数（名字 颜色），可追加 kind=布局名，实际给了 " + ps.length + " 个");
      }
      var cname = ps[0], color = ps[1];
      if (!COLOR.test(color)) throw synErr(n, '颜色 "' + color + '" 不合法：应为 6 位十六进制，如 #aaccff');
      var kind = "default";
      if (ps.length === 3) {
        if (ps[2].indexOf("kind=") !== 0) throw synErr(n, '@character 第三个参数应为 kind=布局名，实际为 "' + ps[2] + '"');
        kind = ps[2].slice(5);
        if (!kind) throw synErr(n, "@character kind= 后面不能为空");
      }
      if (this.characters[cname]) throw synErr(n, '角色 "' + cname + '" 重复定义');
      this.characters[cname] = true;
      return { op: "character", name: cname, color: color, kind: kind, line: n };
    }

    if (head === "bg" || head === "music" || head === "sfx") {
      var key = { bg: "image", music: "track", sfx: "sound" }[head];
      var ps2 = argstr.split(/\s+/);
      if (head === "sfx") {
        if (ps2.length !== 1 || !ps2[0]) throw synErr(n, f("@sfx 需要 1 个参数（音效名），实际给了 " + ps2.length + " 个"));
        return { op: "sfx", sound: ps2[0], line: n };
      }
      if (!ps2[0]) {
        throw synErr(n, head === "music"
          ? "@music 需要 1 个参数（音乐名），可追加 fadein=秒 / fadeout=秒"
          : "@bg 需要 1 个参数（图片名），可追加 fadein=秒");
      }
      var ins = { op: head, line: n };
      ins[key] = ps2[0];
      var allowed = head === "music" ? ["fadein", "fadeout"] : ["fadein"];
      var tip = allowed.map(function (p) { return p + "=秒"; }).join(" / ");
      for (var k = 1; k < ps2.length; k++) {
        var part = ps2[k];
        if (part.indexOf("=") < 0) throw synErr(n, "@" + head + " 的扩展参数应为 " + tip + '，实际为 "' + part + '"');
        var kv = part.split("=");
        var pname = kv[0], pvalue = part.slice(pname.length + 1);
        if (allowed.indexOf(pname) < 0) throw synErr(n, "@" + head + ' 不支持参数 "' + pname + '="：可用 ' + tip);
        if (!NUMBER.test(pvalue)) throw synErr(n, pname + ' 应为数字（秒），实际为 "' + pvalue + '"');
        var sec = Number(pvalue);
        if (sec < 0) throw synErr(n, pname + " 不能为负数，实际为 " + pvalue);
        if (sec > 0) ins[pname] = num(pvalue);
      }
      return ins;
    }

    if (head === "show") {
      var ps3 = argstr.split(/\s+/);
      if (ps3.length < 2 || ps3.length > 10) {
        throw synErr(n, "@show 需要 2 个参数（角色ID 表情），可追加 anim=动画名 / pos=左|中|右 / scale=0.5~2.0 / z=整数 / x=像素 / y=像素 / 部位:素材，实际给了 " + ps3.length + " 个");
      }
      var char = ps3[0], expr = ps3[1];
      var anim = "呼吸", pos = null, scale = null, z = null, px = null, py = null, layers = null;
      for (var q = 2; q < ps3.length; q++) {
        var p3 = ps3[q];
        if (p3.indexOf(":") >= 0) {
          var lp = p3.slice(0, p3.indexOf(":")), ln = p3.slice(p3.indexOf(":") + 1);
          if (!NAME.test(lp)) throw synErr(n, '部位名 "' + lp + '" 不合法：只能含中英文、数字和下划线');
          if (!NAME.test(ln)) throw synErr(n, '部位 "' + lp + '" 的素材名 "' + ln + '" 不合法');
          layers = layers || {};
          layers[lp] = ln;
          continue;
        }
        if (p3.indexOf("=") < 0) throw synErr(n, '@show 的参数应为 anim=动画名 / pos=左|中|右 / scale=0.5~2.0 / z=整数 / x=像素 / y=像素 / 部位:素材，实际为 "' + p3 + '"');
        var k3 = p3.split("=")[0], v3 = p3.slice(k3.length + 1);
        if (k3 === "anim") anim = v3;
        else if (k3 === "pos") {
          if (["左", "中", "右"].indexOf(v3) < 0) throw synErr(n, 'pos 只能是 左/中/右，实际为 "' + v3 + '"');
          pos = v3;
        } else if (k3 === "scale") {
          var sc = Number(v3);
          if (!NUMBER.test(v3)) throw synErr(n, 'scale 应为数字（范围 0.5~2.0），实际为 "' + v3 + '"');
          if (sc < 0.5 || sc > 2.0) throw synErr(n, "scale 范围 0.5~2.0，实际为 " + v3);
          scale = num(v3);
        } else if (k3 === "z") {
          if (!INT_ARG.test(v3)) throw synErr(n, 'z 应为整数（如 z=1 / z=-1），实际为 "' + v3 + '"');
          z = parseInt(v3, 10);
        } else if (k3 === "x" || k3 === "y") {
          if (!INT_ARG.test(v3) || Math.abs(parseInt(v3, 10)) > 3000) {
            throw synErr(n, k3 + ' 应为 -3000~3000 的整数像素偏移，实际为 "' + v3 + '"');
          }
          if (k3 === "x") px = parseInt(v3, 10); else py = parseInt(v3, 10);
        } else {
          throw synErr(n, '@show 不支持参数 "' + k3 + '="：可用 anim=动画名 / pos=左|中|右 / scale=0.5~2.0 / z=整数 / x=像素 / y=像素');
        }
      }
      var si = { op: "show", char: char, expr: expr, anim: anim, line: n };
      if (pos !== null) si.pos = pos;
      if (scale !== null) si.scale = scale;
      if (z !== null) si.z = z;
      if (px !== null) si.x = px;
      if (py !== null) si.y = py;
      if (layers) si.layers = layers;
      return si;
    }

    if (head === "hide") {
      var hp = argstr.split(/\s+/);
      if (hp.length !== 1 || !hp[0]) throw synErr(n, "@hide 需要 1 个参数（角色ID），实际给了 " + hp.length + " 个");
      return { op: "hide", char: hp[0], line: n };
    }

    if (head === "wait") {
      if (!argstr) throw synErr(n, "@wait 需要等待时长（数字 + 可选单位 s/ms，如 @wait 1.5 / @wait 500ms）");
      var raw = argstr.trim(), unit = "s";
      if (raw.slice(-2) === "ms") { unit = "ms"; raw = raw.slice(0, -2).trim(); }
      else if (raw.slice(-1) === "s") { unit = "s"; raw = raw.slice(0, -1).trim(); }
      if (!NUMBER.test(raw)) throw synErr(n, '@wait 的时长应为数字，实际 "' + raw + '"');
      var wv = num(raw);
      if (wv <= 0) throw synErr(n, "@wait 的时长必须 > 0");
      return { op: "wait", seconds: unit === "ms" ? wv / 1000 : wv, line: n };
    }

    if (head === "chapter") {
      if (!argstr) throw synErr(n, "@chapter 需要章节标题，如 @chapter 第一章 雨夜");
      var titleParts = [], secs = null;
      var cp = argstr.split(/\s+/);
      for (var ci = 0; ci < cp.length; ci++) {
        var cpart = cp[ci];
        if (cpart.indexOf("=") >= 0) {
          var ck = cpart.split("=")[0], cv = cpart.slice(ck.length + 1);
          if (ck !== "secs") throw synErr(n, "@chapter 不认识的参数 " + ck + "=（只支持 secs=）");
          if (!NUMBER.test(cv)) throw synErr(n, '@chapter 的 secs= 应为数字，实际 "' + cv + '"');
          secs = num(cv);
          if (secs <= 0) throw synErr(n, "@chapter 的 secs= 必须 > 0");
          continue;
        }
        titleParts.push(cpart);
      }
      if (!titleParts.length) throw synErr(n, "@chapter 需要章节标题");
      return { op: "chapter", title: titleParts.join(" "), secs: secs, line: n };
    }

    if (head === "label") {
      var lp2 = argstr.split(/\s+/);
      if (lp2.length !== 1 || !lp2[0]) throw synErr(n, "@label 需要 1 个参数（标签名），实际给了 " + lp2.length + " 个");
      if (!NAME.test(lp2[0])) throw synErr(n, '标签名 "' + lp2[0] + '" 不合法：只能含中英文、数字和下划线');
      if (this.labels[lp2[0]]) throw synErr(n, '标签 "' + lp2[0] + '" 重复定义');
      this.labels[lp2[0]] = n;
      return { op: "label", name: lp2[0], line: n };
    }

    if (head === "jump") {
      var jp = argstr.split(/\s+/);
      if (jp.length !== 1 || !jp[0]) throw synErr(n, "@jump 需要 1 个参数（标签名），实际给了 " + jp.length + " 个");
      if (!NAME.test(jp[0])) throw synErr(n, '标签名 "' + jp[0] + '" 不合法：只能含中英文、数字和下划线');
      return { op: "jump", target: jp[0], line: n };
    }

    if (head === "end") {
      if (argstr) throw synErr(n, "@end 不需要参数");
      return { op: "end", line: n };
    }

    if (head === "set") {
      var m;
      if ((m = SET.exec(argstr))) {
        return { op: "set", var: m[1], operator: m[2], value: num(m[3]), line: n };
      }
      if ((m = SET_STR.exec(argstr))) {
        return { op: "set", var: m[1], operator: "=", value: m[2], line: n };
      }
      if ((m = SET_EXPR.exec(argstr))) {
        if (m[2] !== "=") throw synErr(n, m[2] + " 只支持数值（如 @set 好感 += 1）；表达式请用 =（如 @set 好感 = 好感 + 1）");
        return { op: "set", var: m[1], operator: "=", expr: m[3].trim(), line: n };
      }
      throw synErr(n, "变量语句格式应为：@set 变量 += 数值（也支持 -= 和 =），或 @set 变量 = 表达式，或 @set 变量 = \"字符串\"");
    }

    if (head === "if") {
      if (argstr.slice(-1) !== ":") throw synErr(n, '@if 的条件后面要以 ":" 结尾，并接一段缩进语句块');
      var cond = this.parseCond(argstr.slice(0, -1).trim(), n);
      var bodyIns = this.indented(n, L.indent, "@if");
      var ifIns = { op: "if", cond: cond, body: bodyIns, line: n };
      var eb = this.elseBlock(L.indent);
      if (eb !== null) ifIns.else_body = eb;
      return ifIns;
    }

    if (head.split(":")[0] === "else" || head.split(":")[0] === "elif") {
      throw synErr(n, "@" + head.split(":")[0] + " 前面必须紧接一个同缩进的 @if 或 @elif 块（@elif/@else 与对应的 @if 顶格缩进一致）");
    }

    if (head === "choice:" || (head === "choice" && argstr === ":")) return this.choice(n, L.indent);
    if (head === "choice") throw synErr(n, '@choice 后面需要冒号，写法是单独一行 "@choice:"，后接缩进的选项列表');

    throw synErr(n, '未知指令 "@' + head + '"（手机端解析器支持：@character @bg @music @sfx @show @hide @wait @chapter @label '
      + '@jump @end @set @if @choice: "@[角色] 文本" "@ 文本"；@voice/@video/@anim/@fg/@cg/@camera/@transition/@plug 请到电脑端打包）');
  };

  Parser.prototype.sayNext = function (line) {
    if (this.i >= this.lines.length) throw synErr(line, "@ 后面缺少台词：下一行要写要显示的文本");
    var L = this.lines[this.i];
    if (L.text.charAt(0) === "@") throw synErr(line, "@ 后面缺少台词：下一行不能是另一条 @ 指令");
    this.i++;
    return { op: "say", char: null, text: L.text, line: L.n };
  };

  Parser.prototype.sayBracket = function (line, body) {
    var nvl = body.slice(0, 2) === "[[", start = nvl ? 2 : 1, close;
    if (nvl) {
      close = body.indexOf("]]", start);
      if (close < 0) throw synErr(line, '括号没有闭合：写 "@[[名字]] 台词"（整屏独白）');
      var innerN = body.slice(start, close).trim();
      if (innerN.indexOf("[") >= 0 || innerN.indexOf("]") >= 0) throw synErr(line, "整屏独白的 [[...]] 里不能再出现 [ 或 ]");
    } else {
      var depth = 0;
      close = -1;
      for (var k = start; k < body.length; k++) {
        var ch = body.charAt(k);
        if (ch === "[") depth++;
        else if (ch === "]") {
          if (depth === 0) { close = k; break; }
          depth--;
        }
      }
      if (close < 0) throw synErr(line, '括号没有闭合：写 "@[名字] 台词"');
    }
    var inner = body.slice(start, close).trim();
    if (!inner) throw synErr(line, "括号里缺少角色名或整屏文字");
    if (!nvl && inner.length > 20) throw synErr(line, "角色名太长（最多 20 个字符）：" + inner);
    var tail = body.slice(close + (nvl ? 2 : 1)).trim();
    if (tail.charAt(0) === ":" || tail.charAt(0) === "：") tail = tail.slice(1).trim();

    if (nvl && !tail) return { op: "say", char: null, text: inner, layout: "nvl", line: line };
    if (!tail) {
      if (this.i >= this.lines.length) throw synErr(line, '角色 "' + inner + '" 的对话缺少文本');
      var L = this.lines[this.i];
      if (L.text.charAt(0) === "@") throw synErr(line, '角色 "' + inner + '" 的对话缺少文本');
      this.i++;
      return { op: "say", char: inner, text: L.text, line: L.n };
    }
    var ins = { op: "say", char: inner, text: tail, line: line };
    if (nvl) ins.layout = "nvl";
    return ins;
  };

  Parser.prototype.say = function (body) {
    var line = this.lines[this.i - 1].n;
    var parts = cut1(body);
    if (this.characters[parts[0]]) {
      if (!parts[1].trim()) throw synErr(line, '角色 "' + parts[0] + '" 的对话缺少文本');
      return { op: "say", char: parts[0], text: parts[1].trim(), line: line };
    }
    if (parts[0] === "旁白" && parts[1].trim()) {
      return { op: "say", char: null, text: parts[1].trim(), line: line };
    }
    return { op: "say", char: null, text: body, line: line };
  };

  Parser.prototype.choice = function (line, indent) {
    var options = [], optIndent = null;
    while (this.i < this.lines.length) {
      var L = this.lines[this.i];
      if (L.text.charAt(0) !== ">") break;
      if (optIndent === null) optIndent = L.indent;
      else if (L.indent !== optIndent) throw synErr(L.n, "选项行缩进不一致：同一组选项应对齐（要么全顶格，要么缩进相同）");
      options.push(this.option(L.n, L.text.slice(1).trim()));
      this.i++;
    }
    if (!options.length) throw synErr(line, '"@choice:" 后面需要选项列表（每行以 > 开头）');
    return { op: "choice", options: options, line: line };
  };

  Parser.prototype.option = function (line, body) {
    if (body.indexOf("->") < 0) throw synErr(line, '选项缺少 "-> 标签"，格式：> 文本: 条件 -> 标签（条件可省略）');
    var cut = body.lastIndexOf("->");
    var left = body.slice(0, cut), target = body.slice(cut + 2).trim();
    if (!target) throw synErr(line, '选项缺少跳转标签（"->" 后面为空）');
    if (!NAME.test(target)) throw synErr(line, '标签名 "' + target + '" 不合法：只能含中英文、数字和下划线');
    left = left.trim();
    var cond = null, text = left;
    if (left.indexOf(":") >= 0) {
      var ci2 = left.lastIndexOf(":");
      cond = this.parseCond(left.slice(ci2 + 1).trim(), line, "；选项文本中不能含英文冒号，请改用中文“：”");
      text = left.slice(0, ci2).trim();
    }
    if (!text) throw synErr(line, "选项文本不能为空");
    var opt = { text: text, target: target };
    if (cond) opt.cond = cond;
    return opt;
  };

  Parser.prototype.parseCond = function (text, line, hint) {
    var m = COND.exec(text);
    if (m) return { var: m[1], op: m[2], value: num(m[3]) };
    // 表达式条件交给播放器的表达式求值；这里只存原文（Python 版会额外校验语法）
    return { expr: text };
  };

  Parser.prototype.checkTargets = function (prog) {
    var self = this;
    (function walk(list) {
      list.forEach(function (ins) {
        if (ins.op === "jump") {
          if (!self.labels[ins.target]) throw synErr(ins.line, '跳转目标 "' + ins.target + '" 不存在：没有名为 "' + ins.target + '" 的 @label');
        } else if (ins.op === "choice") {
          ins.options.forEach(function (o) {
            if (!self.labels[o.target]) throw synErr(ins.line, '跳转目标 "' + o.target + '" 不存在：没有名为 "' + o.target + '" 的 @label');
          });
        } else if (ins.op === "if") {
          walk(ins.body);
          if (ins.else_body) walk(ins.else_body);
        }
      });
    })(prog);
  };

  function parseText(text) {
    try {
      var p = new Parser(text || "");
      var prog = p.block(0);
      p.checkTargets(prog);
      return { ok: true, instructions: prog, error: null };
    } catch (e) {
      return {
        ok: false,
        instructions: [],
        error: { line: e.line || 0, message: e.galMessage || e.message }
      };
    }
  }

  var API = { parseText: parseText, stripComment: stripComment };
  if (typeof module === "object" && module.exports) module.exports = API;
  global.MYONLParser = API;
})(typeof window !== "undefined" ? window : globalThis);
