/* ===================================================================
   E9：编辑器三档模式 Level 1–3（用户 2026-11-01 定名）

   - Level 1 新手：只留写剧本最常用的入口（隐藏检查器 / 时间线 / 晾衣绳 /
     富文本工具条 / 语言下拉 / 问题「详细」切换）；
   - Level 2 默认：现有完整布局；
   - Level 3 专业：在默认布局上再开放「源码 / JSON / 卡片」视图页签。

   裁剪本身由 body.editor-level-N + editor.css 实现，本文件只管状态与入口；
   选择记在 localStorage（gal_editor_level），刷新 / 重开沿用。
   =================================================================== */
(function () {
  "use strict";

  var $ = function (id) { return document.getElementById(id); };
  var KEY = "gal_editor_level";
  var DEFAULT_LEVEL = 2;
  var LEVELS = {
    1: { name: "Level 1 · 新手", short: "L1 新手", hint: "只留常用入口" },
    2: { name: "Level 2 · 默认", short: "L2 默认", hint: "完整布局" },
    3: { name: "Level 3 · 专业", short: "L3 专业", hint: "开放全部开发者入口" },
  };

  var current = DEFAULT_LEVEL;

  function normalize(v) {
    v = parseInt(v, 10);
    return (v === 1 || v === 3) ? v : 2;
  }

  function readSaved() {
    try { return normalize(localStorage.getItem(KEY)); } catch (e) { return DEFAULT_LEVEL; }
  }

  function toast(msg) {
    try { if (window.__editor && window.__editor.toast) window.__editor.toast(msg); } catch (e) {}
  }

  function apply(n, opts) {
    n = normalize(n);
    current = n;
    ["editor-level-1", "editor-level-2", "editor-level-3"].forEach(function (c) {
      document.body.classList.remove(c);
    });
    document.body.classList.add("editor-level-" + n);
    document.body.setAttribute("data-editor-level", String(n));

    var sel = $("levelSelect");
    if (sel && sel.value !== String(n)) sel.value = String(n);

    try { localStorage.setItem(KEY, String(n)); } catch (e) {}
    if (!opts || opts.toast !== false) toast("编辑器档位：" + LEVELS[n].name + "（" + LEVELS[n].hint + "）");
    try {
      window.dispatchEvent(new CustomEvent("editor-level-change", { detail: { level: n } }));
    } catch (e) {}
  }

  function buildSelect() {
    var acts = document.querySelector(".mb-acts");
    if (!acts || $("levelSelect")) return;
    var wrap = document.createElement("label");
    wrap.className = "mb-level-wrap";
    wrap.title = "编辑器档位：Level 1 新手 / Level 2 默认 / Level 3 专业（选择会被记住）";
    var sel = document.createElement("select");
    sel.id = "levelSelect";
    sel.className = "mb-level";
    sel.setAttribute("aria-label", "编辑器档位");
    Object.keys(LEVELS).forEach(function (k) {
      var o = document.createElement("option");
      o.value = k;
      o.textContent = LEVELS[k].short;
      o.title = LEVELS[k].name + "：" + LEVELS[k].hint;
      sel.appendChild(o);
    });
    sel.value = String(current);
    sel.addEventListener("change", function () { apply(sel.value); });
    wrap.appendChild(sel);
    acts.appendChild(wrap);
  }

  // 给菜单 / 命令面板用的档位查询（editor_main.js 读这里）
  window.__editorLevel = {
    key: KEY,
    defaultLevel: DEFAULT_LEVEL,
    levels: LEVELS,
    get: function () { return current; },
    set: function (n) { apply(n); },
  };

  current = readSaved();
  apply(current, { toast: false });
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", buildSelect);
  } else {
    buildSelect();
  }
})();
