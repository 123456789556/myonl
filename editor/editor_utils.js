/* 编辑器纯函数工具层：只依赖入参，不读写 editor_main.js 的闭包状态。
   抽出的目的：把可独立测试/复用的 DOM 与格式化小工具从 3000+ 行主脚本里分离。 */
(() => {
  function escapeText(t) {
    return String(t).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  function lineIndent(s) { return (s.match(/^\s*/) || [""])[0]; }

  function _clKey(cat, name) { return cat + ":" + name; }

  function assetURL(cat, name) {
    return "/api/asset/" + cat + "/" + encodeURIComponent(name);
  }

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  function field(value, ph) {
    const i = document.createElement("input");
    i.value = value || "";
    if (ph) i.placeholder = ph;
    return i;
  }

  function selectField(options, value) {
    const s = document.createElement("select");
    let found = false;
    options.forEach(([v, label]) => {
      const o = document.createElement("option");
      o.value = v; o.textContent = label;
      if (v === value) { o.selected = true; found = true; }
      s.appendChild(o);
    });
    if (value && !found) {
      const o = document.createElement("option");
      o.value = value; o.textContent = value; o.selected = true;
      s.appendChild(o);
    }
    return s;
  }

  function row(label, control) {
    const r = el("div", "insp-row");
    r.appendChild(el("label", "", label));
    r.appendChild(control);
    return r;
  }

  function iconBtn(text, title, handler) {
    const b = document.createElement("button");
    b.className = "icon-btn";
    b.type = "button";
    b.textContent = text;
    b.title = title;
    b.addEventListener("click", handler);
    return b;
  }

  function summaryOf(ins) {
    switch (ins.op) {
      case "say": return (ins.char ? ins.char + "：" : "旁白：") + (ins.text || "");
      case "bg": return "背景 → " + (ins.image || "");
      case "music": return "音乐 → " + (ins.track || "");
      case "sfx": return "音效 → " + (ins.sound || "");
      case "show": return "立绘 " + (ins.char || "") + " / " + (ins.expr || "");
      case "hide": return "隐藏 " + (ins.char || "");
      case "character": return (ins.name || "") + " " + (ins.color || "");
      case "label": return "标签 " + (ins.name || "");
      case "jump": return "跳到 → " + (ins.target || "");
      case "set": return (ins.var || "") + " " + (ins.operator || "") + " " + ins.value;
      case "if": {
        const c = ins.cond || {};
        return "若 " + (c.var || "") + " " + (c.op || "") + " " + c.value + " 则执行 " + (ins.body || []).length + " 条";
      }
      case "choice": return (ins.options || []).length + " 个选项";
      case "end": return "剧本结束";
      default: return ins.op || "未知";
    }
  }

  function fieldRow(labelText, el) {
    const d = document.createElement("div");
    d.className = "field";
    const l = document.createElement("label");
    l.textContent = labelText;
    d.appendChild(l); d.appendChild(el);
    return d;
  }

  function mkInput(field, value, type) {
    const el = document.createElement("input");
    if (type === "color") { el.type = "color"; } else if (type === "number") { el.type = "number"; el.step = "any"; }
    else { el.type = "text"; }
    el.dataset.f = field;
    el.value = value === undefined || value === null ? "" : value;
    return el;
  }

  function mkTextarea(field, value) {
    const el = document.createElement("textarea");
    el.dataset.f = field;
    el.value = value === undefined || value === null ? "" : value;
    return el;
  }

  function mkSelect(field, value, options) {
    const el = document.createElement("select");
    el.dataset.f = field;
    options.forEach(([v, label]) => {
      const o = document.createElement("option");
      o.value = v; o.textContent = label;
      el.appendChild(o);
    });
    el.value = value;
    return el;
  }

  window.MyonlEditorUtils = {
    escapeText, lineIndent, _clKey, assetURL, el, field, selectField, row,
    iconBtn, summaryOf, fieldRow, mkInput, mkTextarea, mkSelect,
  };
})();
