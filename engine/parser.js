/* ============================================================
   MYONL 解析器 · JS 版（手机端离线出成品用）

   目标不是"另写一个引擎"，而是**逐条复刻 engine/parser.py 的产出**：
   同一份 .gal 文本，Python 版和这里产出的指令数组必须逐字段一致
   （唯一允许不同的是 file 字段：JS 端单文件，没有跨文件定位）。

   对拍脚本 tools/pack_diff.py 会拿 games/ 下所有工程跑两遍比一遍。
   不一致就是 bug，不许"差不多"。

   已覆盖：
     character / set / bg / music / sfx / chapter / label / say /
     show / hide / choice / jump / if / end / wait / video /
     voice / cg / fg / camera / transition（P192 补齐；字段与校验照 parser.py 逐条对齐）
   未覆盖（遇到就抛清楚的中文错误，不静默走偏）：
     plug / @include（@anim 已由 P274 补齐）
   ============================================================ */
(function (global) {
  "use strict";

  // 解析 @video 的扩展参数：file（真视频文件）/ fps=N / loop=0|1 / mute（静音）
  // 与 parser.py 同一套规则；fps 只对帧序列有意义，file 形式接受但忽略。
  function parseVideoArgs(n, argstr) {
    var parts = argstr.split(/\s+/).filter(Boolean);
    if (!parts[0]) {
      throw synErr(n, "@video 需要 1 个参数（视频名），可追加 file / fps=帧率 / loop=0|1 / mute");
    }
    var name = parts[0];
    var fps = 30, file = false, loop = true, mute = false;
    for (var k = 1; k < parts.length; k++) {
      var part = parts[k];
      if (part === "file") { file = true; continue; }
      if (part === "mute") { mute = true; continue; }
      if (part.indexOf("=") < 0) {
        throw synErr(n, '@video 的扩展参数应为 file / fps=帧率 / loop=0|1 / mute，实际为 "' + part + '"');
      }
      var kv = part.split("=");
      var pname = kv[0], pvalue = part.slice(pname.length + 1);
      if (pname === "fps") {
        if (!INT_ARG.test(pvalue) || parseInt(pvalue, 10) <= 0) {
          throw synErr(n, '@video 的 fps= 应为正整数（如 fps=24），实际为 "' + pvalue + '"');
        }
        fps = parseInt(pvalue, 10);
      } else if (pname === "loop") {
        if (pvalue !== "0" && pvalue !== "1") {
          throw synErr(n, '@video 的 loop= 只能是 0（播完停在最后一帧）或 1（循环），实际为 "' + pvalue + '"');
        }
        loop = pvalue === "1";
      } else {
        throw synErr(n, '@video 不支持参数 "' + pname + '="：可用 file / fps=帧率 / loop=0|1 / mute');
      }
    }
    return { op: "video", name: name, fps: fps, file: file, loop: loop, mute: mute, line: n };
  }

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
  // _DIR_ALIAS 的 JS 版：@camera / @transition 的方向参数，中英都认，输出统一中文
  var DIRS = { "左": "左", left: "左", "右": "右", right: "右",
               "上": "上", up: "上", "下": "下", down: "下" };

  /* 手机端解析器不产出的指令：单一来源。
     报错文案由它拼，测试也从它读 —— 放开一条只改这个数组，
     别再把条数或名单写死进中文句子（写死过一次，改文案就得同步改测试）。
     P192 已从这里移出 voice / cg / fg / camera / transition；P274 移出 anim。 */
  var UNSUPPORTED_DIRECTIVES = ["plug", "include"];

  // 缓动曲线名单单一来源：照 engine/timeline.py 的 EASINGS 22 条抄一份（Python 那边是函数表，
  // JS 只做校验，播放器另有同名实现 web/myonl-player.js 的 EASE）。
  var EASE_NAMES = ["linear", "ease_in", "ease_out", "none",
    "ease_in_quad", "ease_out_quad", "ease_in_out_quad",
    "ease_in_cubic", "ease_out_cubic", "ease_in_out_cubic",
    "ease_in_quart", "ease_out_quart", "ease_in_out_quart",
    "ease_in_sine", "ease_out_sine", "ease_in_out_sine",
    "ease_in_expo", "ease_out_expo", "ease_in_out_expo",
    "ease_in_back", "ease_out_back", "ease_in_out_back"];

  // @anim 的参数只能补这 4 个（照 parser.py 的 _ANIM_PARAMS）
  var ANIM_PARAMS = ["x", "y", "alpha", "scale"];

  function num(s) {
    var v = Number(s);
    return v === Math.floor(v) ? Math.floor(v) : v;
  }

  // 等价 parser.py 的 _anim_value：x/y 不限、alpha 0~1、scale 0.5~2.0
  function animValue(line, param, text) {
    if (!NUMBER.test(text)) throw synErr(line, '@anim 的数值应为数字，实际为 "' + text + '"');
    var v = num(text);
    if (param === "alpha" && (v < 0 || v > 1)) throw synErr(line, "alpha 范围 0~1，实际为 " + text);
    if (param === "scale" && (v < 0.5 || v > 2)) throw synErr(line, "scale 范围 0.5~2.0，实际为 " + text);
    return v;
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
      var one = this.one();
      // parser.py:193 同一条约束：@voice 只能紧跟台词，中间不能夹别的指令
      if (one.op === "voice" && (!out.length || out[out.length - 1].op !== "say")) {
        throw synErr(one.line, '@voice 必须紧跟在一条台词之后（前一行应是 "@ 角色 文本" 或 "@ 旁白"，中间不能有其他指令）');
      }
      out.push(one);
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

    if (head === "video") {
      return parseVideoArgs(n, argstr);
    }

    /* ---- P192：补上 5 条演出指令的解析 ----
     * 播放器（web/myonl-player.js）早就实现了 cg / fg / voice / camera / transition，
     * 一直只拦在解析器这层，作者在手机上连写都写不出来。字段名、参数个数、取值范围
     * 全部照 engine/parser.py 对齐，双端由 tests/golden/at_rules.json 对拍兜着，
     * 谁单方面改动都会让 CI 变红。 */
    if (head === "voice") {
      var av = argstr.split(/\s+/).filter(Boolean);
      if (av.length !== 1 || !av[0]) {
        throw synErr(n, "@voice 需要 1 个参数（配音文件名），实际给了 " + av.length + " 个");
      }
      return { op: "voice", sound: av[0], line: n };
    }

    if (head === "cg") {
      var ac = argstr.split(/\s+/).filter(Boolean);
      if (ac.length !== 1 || !ac[0]) {
        throw synErr(n, "@cg 需要 1 个参数（CG 名称），实际给了 " + ac.length + " 个");
      }
      return { op: "cg", name: ac[0], line: n };
    }

    if (head === "fg") {
      var fgArgs = argstr.split(/\s+/).filter(Boolean);
      if (!fgArgs.length || fgArgs.length > 4) {
        throw synErr(n, "@fg 需要 1 个参数（前景素材名 / 无），可追加 x=像素 / y=像素 / alpha=0~1");
      }
      var fgn = fgArgs[0], fx = 0, fy = 0, falpha = 1;
      for (var fi = 1; fi < fgArgs.length; fi++) {
        var fp = fgArgs[fi];
        if (fp.indexOf("=") < 0) {
          throw synErr(n, '@fg 的扩展参数应为 x=像素 / y=像素 / alpha=0~1，实际为 "' + fp + '"');
        }
        var fk = fp.split("=")[0], fv = fp.slice(fk.length + 1);
        if (fk === "x" || fk === "y") {
          if (!INT_ARG.test(fv)) throw synErr(n, fk + ' 应为整数（像素偏移），实际为 "' + fv + '"');
          if (fk === "x") fx = parseInt(fv, 10); else fy = parseInt(fv, 10);
        } else if (fk === "alpha") {
          if (!NUMBER.test(fv)) throw synErr(n, 'alpha 应为数字（范围 0~1），实际为 "' + fv + '"');
          falpha = Number(fv);
          if (falpha < 0 || falpha > 1) throw synErr(n, "alpha 范围 0~1，实际为 " + fv);
        } else {
          throw synErr(n, '@fg 不支持参数 "' + fk + '="：可用 x=像素 / y=像素 / alpha=0~1');
        }
      }
      if (fgn === "none") fgn = "无";
      else if (fgn !== "无" && !NAME.test(fgn)) {
        throw synErr(n, '前景素材名 "' + fgn + '" 不合法：只能含中英文、数字和下划线');
      }
      return { op: "fg", name: fgn, x: fx, y: fy, alpha: falpha, line: n };
    }

    if (head === "anim") {
      /* P274：立绘参数补间（x / y / alpha / scale）。以前这条只能在电脑端写，
         手机端解析器直接报「暂时写不了」，但播放器（myonl-core.js / myonl-player.js）
         早就会演了 —— 只差这一层语法。字段与校验逐条照 engine/parser.py。 */
      var animArgs = argstr.split(/\s+/).filter(Boolean);
      if (animArgs.length < 3 || animArgs.length > 4) {
        throw synErr(n, "@anim 需要 3 个参数（角色ID 参数=起始~结束|目标 秒数），"
          + "可追加 ease=linear|ease_in|ease_out|ease_in_cubic|...（T7 共 22 种）");
      }
      var animChar = animArgs[0];
      if (animArgs[1].indexOf("=") < 0) {
        throw synErr(n, '@anim 的参数应为 参数=值（如 x=-100~0），实际为 "' + animArgs[1] + '"');
      }
      var apName = animArgs[1].split("=")[0];
      var apVal = animArgs[1].slice(apName.length + 1);
      if (ANIM_PARAMS.indexOf(apName) < 0) {
        throw synErr(n, '@anim 支持的参数：x / y / alpha / scale，实际为 "' + apName + '"');
      }
      var animFrom = null;
      if (apVal.indexOf("~") >= 0) {
        var tilde = apVal.indexOf("~");
        animFrom = animValue(n, apName, apVal.slice(0, tilde));
        apVal = apVal.slice(tilde + 1);
      }
      var animTo = animValue(n, apName, apVal);
      if (!NUMBER.test(animArgs[2])) {
        throw synErr(n, '@anim 的秒数应为数字，实际为 "' + animArgs[2] + '"');
      }
      if (Number(animArgs[2]) < 0) throw synErr(n, "@anim 的秒数不能为负，实际为 " + animArgs[2]);
      var animEase = "linear";
      if (animArgs.length === 4) {
        if (animArgs[3].indexOf("ease=") !== 0) {
          throw synErr(n, 'ease 格式应为 ease=<曲线名>，实际为 "' + animArgs[3] + '"');
        }
        animEase = animArgs[3].slice(5);
        if (EASE_NAMES.indexOf(animEase) < 0) {
          throw synErr(n, 'ease 只能是 ' + EASE_NAMES.slice().sort().join(" / ") + ' 之一，实际为 "' + animEase + '"');
        }
      }
      var animIns = { op: "anim", char: animChar, param: apName, to: animTo,
        secs: num(animArgs[2]), ease: animEase, line: n };
      if (animFrom !== null) animIns.from = animFrom;
      return animIns;
    }

    if (head === "camera") {
      var camArgs = argstr.split(/\s+/).filter(Boolean);
      if (camArgs.length < 2) throw synErr(n, "@camera 需要 子命令(pan/zoom/shake/reset) + 参数");
      var ck = camArgs[0];
      if (["pan", "zoom", "shake", "reset"].indexOf(ck) < 0) {
        throw synErr(n, '@camera 子命令 "' + ck + '" 不支持（pan/zoom/shake/reset）');
      }
      var ca = camArgs.slice(1);
      if (ck === "pan") {
        if (ca.length !== 2 || !DIRS[ca[0]]) {
          throw synErr(n, "@camera pan 格式：@camera pan 方向(左/右/上/下，也可 left/right/up/down) 秒数");
        }
        if (!NUMBER.test(ca[1])) throw synErr(n, '@camera pan 的秒数应为数字，实际 "' + ca[1] + '"');
        if (!(Number(ca[1]) > 0)) throw synErr(n, "@camera pan 的秒数必须 > 0");
        return { op: "camera", kind: "pan", args: [DIRS[ca[0]], num(ca[1])], line: n };
      }
      if (ck === "zoom") {
        if (ca.length !== 2) throw synErr(n, "@camera zoom 格式：@camera zoom 起始缩放 结束缩放");
        for (var zi = 0; zi < 2; zi++) {
          if (!NUMBER.test(ca[zi])) throw synErr(n, '@camera zoom 的缩放比例应为数字，实际 "' + ca[zi] + '"');
        }
        return { op: "camera", kind: "zoom", args: [num(ca[0]), num(ca[1])], line: n };
      }
      if (ck === "shake") {
        if (ca.length !== 2) throw synErr(n, "@camera shake 格式：@camera shake 秒数 幅度");
        if (!NUMBER.test(ca[0]) || !NUMBER.test(ca[1])) throw synErr(n, "@camera shake 的秒数和幅度应为数字");
        if (!(Number(ca[0]) > 0)) throw synErr(n, "@camera shake 的秒数必须 > 0");
        return { op: "camera", kind: "shake", args: [num(ca[0]), num(ca[1])], line: n };
      }
      // reset
      if (ca.length !== 1) throw synErr(n, "@camera reset 格式：@camera reset 秒数");
      if (!NUMBER.test(ca[0])) throw synErr(n, '@camera reset 的秒数应为数字，实际 "' + ca[0] + '"');
      if (!(Number(ca[0]) > 0)) throw synErr(n, "@camera reset 的秒数必须 > 0");
      return { op: "camera", kind: "reset", args: [num(ca[0])], line: n };
    }

    if (head === "transition") {
      var trArgs = argstr.split(/\s+/).filter(Boolean);
      if (!trArgs.length) throw synErr(n, "@transition 需要 子命令(dissolve/wipe/slide) + 参数");
      var tk = trArgs[0];
      if (["dissolve", "wipe", "slide"].indexOf(tk) < 0) {
        throw synErr(n, '@transition 子命令 "' + tk + '" 不支持（dissolve/wipe/slide）');
      }
      var ta = trArgs.slice(1);
      if (tk === "dissolve") {
        if (ta.length !== 1) throw synErr(n, "@transition dissolve 格式：@transition dissolve 秒数");
        if (!NUMBER.test(ta[0])) throw synErr(n, '@transition dissolve 的秒数应为数字，实际 "' + ta[0] + '"');
        if (!(Number(ta[0]) > 0)) throw synErr(n, "@transition dissolve 的秒数必须 > 0");
        return { op: "transition", kind: "dissolve", args: [num(ta[0])], line: n };
      }
      if (ta.length !== 2 || !DIRS[ta[0]]) {
        throw synErr(n, "@transition " + tk + " 格式：@transition " + tk + " 方向(左/右/上/下，也可 left/right/up/down) 秒数");
      }
      if (!NUMBER.test(ta[1])) throw synErr(n, '@transition ' + tk + ' 的秒数应为数字，实际 "' + ta[1] + '"');
      if (!(Number(ta[1]) > 0)) throw synErr(n, "@transition " + tk + " 的秒数必须 > 0");
      return { op: "transition", kind: tk, args: [DIRS[ta[0]], num(ta[1])], line: n };
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
          // P115：中文和英文别名都认，但输出统一成中文（播放器只认中文，一行不用改）
          var POSA = { "左": "左", left: "左", "中": "中", center: "中", mid: "中", "右": "右", right: "右" };
          if (!POSA[v3]) throw synErr(n, 'pos 只能是 左/中/右（也可写 left/center/right），实际为 "' + v3 + '"');
          pos = POSA[v3];
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

    // 拒收名单单一来源（UNSUPPORTED_DIRECTIVES），但两条分开说，别用一句「暂不支持」糊：
    // include 是电脑端多文件写法，手机单文件用不上，引导删掉；plug 这台设备没有插件、成品也不演。
    var baseName = head.split(":")[0];
    if (baseName === "include") {
      throw synErr(n, "@include 是电脑端拆多文件的写法：手机上作品就是一份单文件，用不上它，这行可以删掉。"
        + "（@include 的成品在手机上能演：电脑端打包时已内联展开，成品里根本没有这条指令）");
    }
    if (baseName === "plug") {
      throw synErr(n, "@plug 是电脑端的插件指令：这台设备上没有插件实现，@plug 连成品也不演（播放器没有插件实现）。");
    }

    var unsNames = UNSUPPORTED_DIRECTIVES.map(function (d) { return "@" + d; }).join(" / ");
    throw synErr(n, '未知指令 "@' + head + '"（手机端解析器支持：@character @bg @music @sfx @show @hide @wait '
      + '@chapter @label @jump @end @set @if @video @voice @cg @fg @anim @camera @transition @choice: '
      + '"@[角色] 文本" "@ 文本"；另外写不了的是 ' + unsNames + '）');
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
