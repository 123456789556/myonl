/* MYONL 移动端播放器内核（纯逻辑，无 DOM / 无 canvas）。
 *
 * 设计：PY 端只当"编译器"——把 script.gal 解析成指令数组（IR）塞进 pack.json；
 * 这里只负责**执行**这套 IR，不重复实现剧本语法（语法永远只有一份）。
 *
 * 事件流：next() / choose(i) 返回一个事件对象，渲染层照着画：
 *   {type:"say"}        显示台词（带打字机，由渲染层做）
 *   {type:"bg"}         换背景
 *   {type:"show"}       显示立绘
 *   {type:"hide"}       隐藏立绘
 *   {type:"wait"}       停 N 秒
 *   {type:"choice"}     弹选项
 *   {type:"end"}        剧本结束
 * 变量插值 {var} 也在这里做（与桌面端 runtime._interpolate 语义一致）。
 */
(function (root) {
  "use strict";

  const OPS = new Set([
    "character", "bg", "cg", "show", "hide", "say", "choice", "jump", "label",
    "set", "if", "wait", "end", "nvl", "music", "sfx", "camera", "stop", "play",
    "fg", "anim", "video",   // P73：前景贴图 / 立绘补间 / 帧序列背景（之前只有桌面端有）
    "voice", "chapter", "transition",   // P73：语音 / 章节卡 / 转场（之前只 console.warn）
  ]);

  // @anim 没写起始值时的缺省显示值（与桌面端 renderer 的 disp 默认一致）
  const ANIM_DEF = {x: 0, y: 0, alpha: 1, scale: 1};

  function nowMs() {
    return typeof performance !== "undefined" && performance.now
      ? performance.now() : Date.now();
  }

  function formatValue(v) {
    if (v === true) return "真";
    if (v === false) return "假";
    if (v === null || v === undefined) return "";
    return String(v);
  }

  /* 台词插值：{名字} → 变量值；{{ }} 转义成字面花括号。 */
  function interpolate(text, vars) {
    if (!text || text.indexOf("{") < 0) return text || "";
    return String(text).replace(/\{([^{}]+)\}/g, function (whole, name) {
      const key = String(name).trim();
      if (key === "") return "";
      if (Object.prototype.hasOwnProperty.call(vars, key)) {
        return formatValue(vars[key]);
      }
      return whole;          // 未定义变量原样保留，方便作者发现写错
    });
  }

  function compare(cond, vars) {
    if (!cond || typeof cond !== "object") return false;
    const left = Object.prototype.hasOwnProperty.call(vars, cond.var) ? vars[cond.var] : 0;
    const right = cond.value;
    switch (cond.op) {
      case "==": return left === right || String(left) === String(right);
      case "!=": return !(left === right || String(left) === String(right));
      case ">": return Number(left) > Number(right);
      case ">=": return Number(left) >= Number(right);
      case "<": return Number(left) < Number(right);
      case "<=": return Number(left) <= Number(right);
      default: return !!left;
    }
  }

  /* 指令数组 → 执行器。index 指向"当前还没执行的那条"。 */
  function createVM(pack) {
    const instrs = (pack && pack.ins) || [];
    const labels = Object.create(null);
    for (let i = 0; i < instrs.length; i++) {
      if (instrs[i] && instrs[i].op === "label" && instrs[i].name) {
        labels[instrs[i].name] = i;
      }
    }
    const chars = Object.create(null);
    for (const c of (pack && pack.characters) || []) {
      if (c && c.name) chars[c.name] = c;
    }

    const state = {
      pc: 0,
      vars: {},
      bg: "",
      cg: "",            // P63：当前全屏 CG（空 = 没在放）
      sprites: [],       // [{char, expr, anim}]
      music: "",         // P62：当前背景音乐名（存档带上，读档能续上）
      cameraZoom: 1,     // P64：@camera zoom 的持久缩放（reset 回 1.0，和桌面端 runtime 一致）
      fg: null,          // P73：@fg 前景贴图 {name,x,y,alpha}；null = 没在放
      anim: {},          // P73：@anim 补间 {char: {param: {from,to,secs,t0}}}
      video: null,       // P73：@video 帧序列背景 {name,fps}；@bg 时清空
      ended: false,
      warnings: [],      // 不支持的指令：不崩，记下来给作者看
      choice: null,      // 当前挂起的选项
      lastSay: null,
    };

    // 栈式执行：if 的 body 直接展开成帧，避免递归太深
    let frame = {ins: instrs, pc: 0, root: true};

    function record(message) {
      if (state.warnings.length < 64 && state.warnings.indexOf(message) < 0) {
        state.warnings.push(message);
      }
    }

    function jumpTo(name) {
      const at = labels[name];
      if (at === undefined) {
        record("跳转目标不存在：" + name);
        return false;
      }
      frame = {ins: instrs, pc: at + 1, root: true};
      return true;
    }

    function execSet(ins) {
      const name = ins.var;
      const raw = ins.value;
      const cur = Object.prototype.hasOwnProperty.call(state.vars, name) ? state.vars[name] : 0;
      const num = Number(raw);
      const isNum = typeof raw === "number" || (!isNaN(num) && String(raw).trim() !== "");
      switch (ins.operator || "=") {
        case "=": state.vars[name] = raw; break;
        case "+=":
          state.vars[name] = isNum ? Number(cur || 0) + num : String(cur) + String(raw);
          break;
        case "-=": state.vars[name] = Number(cur || 0) - num; break;
        case "*=": state.vars[name] = Number(cur || 0) * num; break;
        case "/=": state.vars[name] = num === 0 ? 0 : Number(cur || 0) / num; break;
        default: state.vars[name] = raw;
      }
    }

    /* 执行到下一条"需要渲染层响应"的指令为止。 */
    function next() {
      if (state.ended) return {type: "end", final: true};
      let guard = 0;
      while (guard++ < 100000) {
        if (frame.pc >= frame.ins.length) {
          if (frame.root) {
            state.ended = true;
            return {type: "end", final: true};
          }
          frame = frame.ret;          // if body 跑完 → 回父帧
          continue;
        }
        const ins = frame.ins[frame.pc++];
        if (!ins || typeof ins !== "object") continue;
        const op = ins.op;
        if (!OPS.has(op)) { record("不支持的指令：" + op); continue; }

        switch (op) {
          case "character": break;                     // 角色登记在 load 时已建表
          case "label": break;
          case "set": execSet(ins); break;
          case "bg":
            state.bg = ins.image || "";
            state.cg = "";                    // 切回背景：CG 退场（和桌面端语义一致）
            state.video = null;               // 同时停掉帧序列视频
            return {type: "bg", image: state.bg};
          case "cg":
            state.cg = ins.name || "";
            return {type: "cg", name: state.cg};
          case "show": {
            const entry = {char: ins.char, expr: ins.expr || "", anim: ins.anim || ""};
            const idx = state.sprites.findIndex((s) => s.char === entry.char);
            if (idx >= 0) state.sprites[idx] = entry; else state.sprites.push(entry);
            return {type: "show", sprite: entry, sprites: state.sprites.slice()};
          }
          case "hide": {
            if (!ins.char) state.sprites = [];
            else state.sprites = state.sprites.filter((s) => s.char !== ins.char);
            return {type: "hide", char: ins.char || "", sprites: state.sprites.slice()};
          }
          case "nvl":
          case "say": {
            const text = interpolate(ins.text || "", state.vars);
            const who = ins.char || null;
            const color = who && chars[who] ? (chars[who].color || "#ffffff") : "#ffffff";
            state.lastSay = {type: "say", char: who, text: text, color: color,
                             layout: ins.layout || ""};
            return state.lastSay;
          }
          case "choice": {
            const options = (ins.options || []).map((o) => ({text: o.text, target: o.target || ""}));
            state.choice = options;
            return {type: "choice", options: options};
          }
          case "jump":
            state.choice = null;
            if (!jumpTo(ins.target)) { state.ended = true; return {type: "end", final: true}; }
            continue;
          case "if": {
            state.choice = null;
            const body = ins.body || [];
            // 字段名是 parser 的 else_body（不是 else）。读错过一次：条件为假时不进 else，
            // 直接顺着往下执行，落进紧随其后的 @label —— 手机端结局会整条走错。
            const elseBody = ins["else_body"] || ins["else"] || [];
            const branch = compare(ins.cond, state.vars) ? body : elseBody;
            if (branch && branch.length) {
              frame = {ins: branch, pc: 0, root: false, ret: frame};
            }
            continue;
          }
          case "wait":
            return {type: "wait", seconds: Number(ins.seconds) || 0};
          case "music":
            state.music = ins.track || "";
            return {type: "music", track: ins.track || "",
                    fadein: ins.fadein || 0, fadeout: ins.fadeout || 0};
          case "sfx":
            return {type: "sfx", sound: ins.sound || ""};
          case "voice":
            // 语音：紧跟着的那句 @[角色] 台词开播，播放器负责接住
            return {type: "voice", sound: ins.sound || ""};
          case "chapter": {
            // 章节卡（黑场 + 大标题），独立演出，播完才继续
            const secs = Number(ins.secs);
            return {type: "chapter", title: ins.title || "",
                    secs: secs > 0 ? secs : 2.0};
          }
          case "transition": {
            // 假装下一张背景怎么进来：dissolve 淡入 / wipe·slide 按方向推入
            const args = (ins.args || []).slice();
            return {type: "transition", kind: ins.kind || "dissolve", args: args};
          }
          case "camera": {
            // 与桌面端 runtime 同一套语义：zoom 的终值持久（进存档），pan/shake 是瞬时的
            const kind = ins.kind || "";
            const args = (ins.args || []).slice();
            if (kind === "zoom") state.cameraZoom = Number(args[1]) || 1;
            else if (kind === "reset") state.cameraZoom = 1;
            return {type: "camera", kind: kind, args: args};
          }
          case "video": {
            // 帧序列背景（images/videos/名字_001.png 起连续编号），fps 缺省 24。
            // P131：真视频文件那条路。`file` 为真 = 这段不是帧序列，播放器走 <video> 解码。
            // 两套解析器键名不一样：js 侧叫 file，py 侧叫 movie_file —— py 的 `file` 已经被
            // 「源文件定位」这个公共字段占了，只能让位。这里统一收口，别让播放器和存档去猜。
            const fpsRaw = Number(ins.fps);
            const isFile = ins.file === true || ins.movie_file === true;
            state.video = {name: ins.name || "",
                           fps: fpsRaw > 0 ? fpsRaw : 24,
                           file: isFile,
                           loop: ins.loop !== false,
                           mute: ins.mute === true,
                           t0: nowMs()};
            return {type: "video", name: state.video.name, fps: state.video.fps,
                    file: isFile, loop: state.video.loop, mute: state.video.mute};
          }
          case "fg": {
            // 前景贴图：@fg 无 / reset 清掉；否则整条替换（和桌面端 runtime 一致）
            const fgName = String(ins.name || "");
            if (ins.reset || fgName === "无" || fgName === "none") state.fg = null;
            else {
              state.fg = {name: ins.name || "", x: Number(ins.x) || 0,
                          y: Number(ins.y) || 0,
                          alpha: ins.alpha === undefined || ins.alpha === null
                            ? 1 : Number(ins.alpha)};
            }
            return {type: "fg", fg: state.fg ? Object.assign({}, state.fg) : null};
          }
          case "anim": {
            // 立绘参数补间：起点缺省时接着上一次的终点（桌面端 Timeline 也是这么接的）
            const ch = ins.char || "";
            const p = ins.param || "x";
            const toRaw = Number(ins.to);
            const to = isNaN(toRaw) ? 0 : toRaw;
            const secs = Math.max(0, Number(ins.secs) || 0);
            const rec = state.anim[ch] || (state.anim[ch] = {});
            const prev = rec[p];
            let from;
            if (ins.from === undefined || ins.from === null) {
              from = prev ? prev.to : (ANIM_DEF[p] === undefined ? 0 : ANIM_DEF[p]);
            } else {
              const f = Number(ins.from);
              from = isNaN(f) ? 0 : f;
            }
            rec[p] = {from: from, to: to, secs: secs, t0: nowMs()};
            return {type: "anim", char: ch, param: p, from: from, to: to, secs: secs};
          }
          case "end":
            state.ended = true;
            return {type: "end", final: true};
          default:
            record("暂不支持的指令：" + op);
            continue;
        }
      }
      record("执行步数超限，剧本可能有死循环");
      state.ended = true;
      return {type: "end", final: true, error: true};
    }

    function choose(index) {
      if (!state.choice) return null;
      const opts = state.choice;
      const opt = opts[index];
      state.choice = null;
      if (!opt) return null;
      if (opt.target) {
        if (!jumpTo(opt.target)) { state.ended = true; return {type: "end", final: true}; }
      }
      return {type: "chosen", text: opt.text, target: opt.target || ""};
    }

    function save() {
      // @anim 只存终值：补间过程不重放，读档直接落到结果画面（和桌面端一致）
      const finals = {};
      for (const c in state.anim) {
        const d = finals[c] = {};
        for (const p in state.anim[c]) d[p] = state.anim[c][p].to;
      }
      // P105：pc 之前写的是 state.pc —— 那个字段从来没更新过，永远是 undefined，
      // 于是 JSON 里没有 pc，读档一律从第 0 条指令重来，玩家读的是"开头"不是"存档点"。
      // frame.pc 在取指令时先取后自增，所以它指向**下一条**；这里存 -1 让读档重放
      // 存档当时显示的那一句，而不是悄悄跳到下一句。
      return JSON.stringify({pc: Math.max(0, frame.pc - 1), vars: state.vars, bg: state.bg,
                             cg: state.cg, music: state.music,
                             cameraZoom: state.cameraZoom, fg: state.fg,
                             video: state.video ? {name: state.video.name,
                                                   fps: state.video.fps,
                                                   // P131：真视频的开关也要进存档，否则读档会把
                                                   // 一段 mp4 当成帧序列去找连号 PNG，画面直接黑
                                                   file: state.video.file === true,
                                                   loop: state.video.loop !== false,
                                                   mute: state.video.mute === true} : null,
                             animFinal: finals,
                             sprites: state.sprites, ended: state.ended,
                             framePc: frame.pc, frameRoot: frame.root});
    }

    function load(json) {
      try {
        const s = typeof json === "string" ? JSON.parse(json) : json;
        state.vars = s.vars || {};
        state.bg = s.bg || "";
        state.cg = s.cg || "";
        state.music = s.music || "";
        state.cameraZoom = Number(s.cameraZoom) || 1;
        state.fg = s.fg || null;
        // 老存档没有这三个字段：file 缺省 false 就是帧序列，loop 缺省 true，和改之前的行为一致
        state.video = s.video ? {name: s.video.name || "",
                                 fps: Number(s.video.fps) || 24,
                                 file: s.video.file === true,
                                 loop: s.video.loop !== false,
                                 mute: s.video.mute === true,
                                 t0: nowMs()} : null;
        state.anim = {};
        const finals = s.animFinal || {};
        for (const c in finals) {
          const d = state.anim[c] = {};
          for (const p in finals[c]) {
            const v = Number(finals[c][p]) || 0;
            d[p] = {from: v, to: v, secs: 0, t0: 0};
          }
        }
        state.sprites = s.sprites || [];
        state.ended = !!s.ended;
        frame = {ins: instrs, pc: Math.max(0, Number(s.pc) || 0), root: true};
        state.choice = null;
        return true;
      } catch (e) {
        record("存档读取失败：" + e.message);
        return false;
      }
    }

    function restart(atLabel) {
      state.vars = {};
      state.bg = "";
      state.cg = "";
      state.music = "";
      state.cameraZoom = 1;
      state.fg = null;
      state.video = null;
      state.anim = {};
      state.sprites = [];
      state.ended = false;
      state.choice = null;
      state.warnings = [];
      frame = {ins: instrs, pc: 0, root: true};
      if (atLabel) jumpTo(atLabel);
    }

    return {
      next: next,
      choose: choose,
      save: save,
      load: load,
      restart: restart,
      labels: labels,
      characters: chars,
      state: state,
    };
  }

  const api = {createVM: createVM, interpolate: interpolate, compare: compare};
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.MyonlCore = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
