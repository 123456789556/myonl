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
    "set", "if", "wait", "end", "nvl", "music", "sfx", "stop", "play",
  ]);

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
            const elseBody = ins["else"] || [];
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
      return JSON.stringify({pc: state.pc, vars: state.vars, bg: state.bg,
                             cg: state.cg, music: state.music,
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
