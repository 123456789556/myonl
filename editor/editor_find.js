/* P199a 查找 / 替换 / 检查 / 过滤 —— 界面层
 *
 * 引擎在 editor_lint.js（纯函数，不碰 DOM）。这里只做 DOM 与交互。
 *
 * 规矩（都是上一轮拍死的）：
 *  - 默认只替换台词正文；指令与 label 必须勾选「包含指令/标签」并二次确认
 *  - 每次替换后立刻跑一遍体检，断链在顶部红条列出、每条可点跳转
 *  - 「全部替换」是一个撤销单元：原文进内存快照，点撤销整次回退（不进 localStorage）
 *  - 点结果只定位、不关浮层 —— 长稿里定位一个角色通常要连着看好几处
 *  - 浮层贴顶，软键盘弹起也压不走它；结果列表自己滚
 *  - 输入 250ms 防抖：300 句扫描桌面 54ms，真机 3 倍以上，不防抖会一顿一顿
 */
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var root = null, listEl = null, alertEl = null, panelEl = null;
  var findEl = null, replEl = null, cmdEl = null;
  var undoBuf = null, undoBtn = null, built = false;
  var q = { char: null, scene: null, say: false, cmd: null };
  var mode = "filter";          // filter | check
  var timer = null;
  var CMD_NAMES = ["anim", "bg", "camera", "cg", "chapter", "choice", "elif", "else", "end",
    "fg", "hide", "if", "jump", "label", "music", "plug", "property", "set", "sfx",
    "show", "transition", "video", "voice", "wait"];

  var CSS = [
    "#mlRoot{position:fixed;left:0;right:0;top:0;z-index:640;display:flex;flex-direction:column;",
    "max-height:62vh;min-height:32vh;background:rgba(18,22,30,.97);color:#e9edf5;",
    "backdrop-filter:blur(10px);box-shadow:0 10px 30px rgba(0,0,0,.45);",
    "border-radius:0 0 16px 16px;",
    "padding:calc(6px + env(safe-area-inset-top)) 10px 0;font:14px/1.4 -apple-system,'PingFang SC','Microsoft YaHei',sans-serif}",
    "#mlRoot.hidden{display:none}",
    "#mlFab{position:fixed;right:12px;bottom:calc(66px + env(safe-area-inset-bottom));width:46px;height:46px;",
    "border-radius:23px;border:0;background:#2b6cf6;color:#fff;font-size:14px;z-index:600;",
    "box-shadow:0 6px 18px rgba(0,0,0,.38);letter-spacing:1px}",
    "#mlFab.hide{display:none}",
    "body.m-home-open #mlFab{display:none !important}",
    ".ml-head{display:flex;gap:6px;align-items:center;padding-bottom:6px}",
    ".ml-in{flex:1;min-width:0;height:34px;border-radius:9px;border:1px solid #2c3444;background:#0f141c;",
    "color:#e9edf5;padding:0 10px;font-size:14px;outline:none}",
    ".ml-in:focus{border-color:#4f8cff}",
    ".ml-x{width:34px;height:34px;flex:0 0 34px;border-radius:9px;border:1px solid #2c3444;background:#161c26;color:#c9d2e0;font-size:15px}",
    ".ml-row2{display:flex;gap:8px;align-items:center;padding:2px 0 8px;flex-wrap:wrap}",
    ".ml-chk{display:flex;gap:5px;align-items:center;font-size:12.5px;color:#aab5c6}",
    ".ml-btn{height:30px;padding:0 11px;border-radius:8px;border:1px solid #2c3444;background:#1a2230;color:#dfe6f2;font-size:12.5px}",
    ".ml-btn.primary{background:#2b6cf6;border-color:#2b6cf6;color:#fff}",
    ".ml-btn:disabled{opacity:.45}",
    ".ml-chips{display:flex;gap:6px;padding:0 0 8px;overflow-x:auto;flex:0 0 auto}",
    ".ml-chip{flex:0 0 auto;height:28px;padding:0 10px;border-radius:14px;border:1px solid #2c3444;",
    "background:#141a24;color:#c6d0df;font-size:12.5px}",
    ".ml-chip.on{background:#1d3a6b;border-color:#3b6fd4;color:#cfe0ff}",
    ".ml-panel{flex:0 0 auto;max-height:32vh;overflow:auto;border:1px solid #26303f;border-radius:10px;",
    "background:#0e131b;margin-bottom:8px;padding:6px}",
    ".ml-panel.hidden{display:none}",
    ".ml-pitem{display:block;width:100%;text-align:left;padding:8px 10px;border:0;border-radius:8px;",
    "background:transparent;color:#dbe4f2;font-size:13px}",
    ".ml-pitem:active{background:#1b2432}",
    ".ml-alert{flex:0 0 auto;max-height:26vh;overflow:auto;border-radius:10px;background:#3a1416;",
    "border:1px solid #7a2530;color:#ffd8dc;padding:8px 10px;margin-bottom:8px;font-size:12.5px}",
    ".ml-alert.hidden{display:none}",
    ".ml-alert b{color:#ff9aa6}",
    ".ml-aline{display:block;padding:4px 0;color:#ffd8dc;text-decoration:none}",
    ".ml-list{flex:1 1 auto;overflow:auto;padding-bottom:calc(10px + env(safe-area-inset-bottom))}",
    ".ml-item{display:flex;gap:8px;align-items:flex-start;padding:8px 6px;border-bottom:1px solid #1d2430;",
    "text-align:left;background:transparent;border-left:0;border-right:0;border-top:0;width:100%;color:#dbe4f2}",
    ".ml-item:active{background:#161d28}",
    ".ml-no{flex:0 0 42px;color:#7f8a9d;font-size:12px;font-variant-numeric:tabular-nums}",
    ".ml-dot{flex:0 0 6px;height:6px;border-radius:3px;margin-top:7px;background:#4f8cff}",
    ".ml-dot.err{background:#ff5d6c}.ml-dot.warn{background:#ffb84d}.ml-dot.info{background:#6c7a8f}",
    ".ml-why{flex:0 0 60px;width:60px;color:#8fa4c4;font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}",
    ".ml-txt{flex:1;min-width:0;overflow-wrap:anywhere}",
    ".ml-empty{color:#78849a;font-size:13px;padding:18px 4px}",
    "@media (min-width:900px){#mlRoot{left:auto;right:16px;width:440px;max-height:82vh;border-radius:0 0 14px 14px}}"
  ].join("");

  function toast(msg) {
    try { if (window.MYONLEditor && MYONLEditor.toast) return MYONLEditor.toast(msg); } catch (e) {}
    var d = document.createElement("div");
    d.textContent = msg;
    d.style.cssText = "position:fixed;left:50%;top:22%;transform:translateX(-50%);z-index:700;" +
      "background:rgba(20,26,36,.95);color:#e9edf5;padding:9px 14px;border-radius:10px;font-size:13px";
    document.body.appendChild(d);
    setTimeout(function () { d.remove(); }, 2000);
  }

  function source() { return $("source"); }
  function text() { var ta = source(); return ta ? String(ta.value || "") : ""; }

  function build() {
    if (built) return;
    built = true;
    var st = document.createElement("style");
    st.textContent = CSS;
    document.head.appendChild(st);

    root = document.createElement("div");
    root.id = "mlRoot";
    root.className = "hidden";
    root.innerHTML =
      '<div class="ml-head">' +
        '<input id="mlFind" class="ml-in" placeholder="查找…" autocomplete="off" spellcheck="false">' +
        '<input id="mlRepl" class="ml-in" placeholder="替换为…" autocomplete="off" spellcheck="false">' +
        '<button class="ml-x" id="mlClose" title="关闭">✕</button>' +
      "</div>" +
      '<div class="ml-row2">' +
        '<label class="ml-chk"><input type="checkbox" id="mlCmd"> 包含指令/标签</label>' +
        '<button class="ml-btn" id="mlUndo" disabled>撤销这次替换</button>' +
        '<button class="ml-btn" id="mlAll">全部替换</button>' +
        '<button class="ml-btn primary" id="mlCheck">检查全文</button>' +
      "</div>" +
      '<div class="ml-chips">' +
        '<button class="ml-chip" data-chip="char">角色</button>' +
        '<button class="ml-chip" data-chip="scene">场景</button>' +
        '<button class="ml-chip" data-chip="say">仅台词</button>' +
        '<button class="ml-chip" data-chip="cmd">更多指令</button>' +
      "</div>" +
      '<div class="ml-panel hidden" id="mlPanel"></div>' +
      '<div class="ml-alert hidden" id="mlAlert"></div>' +
      '<div class="ml-list" id="mlList"></div>';
    document.body.appendChild(root);

    findEl = $("mlFind"); replEl = $("mlRepl"); cmdEl = $("mlCmd");
    listEl = $("mlList"); alertEl = $("mlAlert"); panelEl = $("mlPanel");
    undoBtn = $("mlUndo");

    $("mlClose").addEventListener("click", close);
    findEl.addEventListener("input", function () { pump(); });
    replEl.addEventListener("input", function () {});
    $("mlCheck").addEventListener("click", function () { mode = "check"; refresh(); });
    $("mlAll").addEventListener("click", replaceAll);
    undoBtn.addEventListener("click", undo);
    cmdEl.addEventListener("change", function () {
      if (cmdEl.checked) toast("会连指令行和 label 一起改，label 一改所有 @jump 就断链");
    });
    root.querySelector(".ml-chips").addEventListener("click", function (e) {
      var b = e.target.closest && e.target.closest(".ml-chip");
      if (!b) return;
      chip(b.getAttribute("data-chip"), b);
    });
  }

  function pump() {
    if (timer) clearTimeout(timer);
    timer = setTimeout(function () { timer = null; mode = "filter"; refresh(); }, 250);
  }

  function chip(kind, btn) {
    mode = "filter";
    if (kind === "say") {
      q.say = !q.say;
      btn.classList.toggle("on", q.say);
      panelEl.classList.add("hidden");
      return refresh();
    }
    if (kind === "cmd" && q.cmd) {
      q.cmd = null;
      syncChips();
      panelEl.classList.add("hidden");
      return refresh();
    }
    if ((kind === "char" && q.char) || (kind === "scene" && q.scene)) {
      if (kind === "char") q.char = null; else q.scene = null;
      syncChips();
      panelEl.classList.add("hidden");
      return refresh();
    }
    var r = window.MYONLLint ? MYONLLint.run(text()) : null;
    if (!r) return;
    var items = [], i;
    if (kind === "char") {
      for (var name in r.chars) items.push({ v: name, label: name });
      if (!items.length) items.push({ v: "", label: "还没有 @character 定义" });
    } else if (kind === "scene") {
      var seen = {};
      for (i = 0; i < r.rows.length; i++) {
        var sc = r.rows[i].scene;
        if (sc && !seen[sc]) { seen[sc] = 1; items.push({ v: sc, label: sc }); }
      }
    } else {
      for (i = 0; i < CMD_NAMES.length; i++) items.push({ v: CMD_NAMES[i], label: "@" + CMD_NAMES[i] });
    }
    panelEl.innerHTML = items.map(function (it) {
      return '<button class="ml-pitem" data-v="' + esc(it.v) + '">' + esc(it.label) + "</button>";
    }).join("");
    panelEl.classList.remove("hidden");
    panelEl.onclick = function (e) {
      var b = e.target.closest && e.target.closest(".ml-pitem");
      if (!b) return;
      var v = b.getAttribute("data-v");
      if (!v) { panelEl.classList.add("hidden"); return; }
      if (kind === "char") q.char = v;
      else if (kind === "scene") q.scene = v;
      else q.cmd = v;
      panelEl.classList.add("hidden");
      syncChips();
      mode = "filter";
      refresh();
    };
  }

  var included = {};

  function syncChips() {
    if (!root) return;
    var chips = root.querySelectorAll(".ml-chip");
    for (var i = 0; i < chips.length; i++) {
      var k = chips[i].getAttribute("data-chip");
      var on = (k === "char" && q.char) || (k === "scene" && q.scene) ||
        (k === "say" && q.say) || (k === "cmd" && q.cmd);
      chips[i].classList.toggle("on", !!on);
      chips[i].textContent = k === "char" ? (q.char ? "角色：" + q.char : "角色")
        : k === "scene" ? (q.scene ? "场景：" + q.scene : "场景")
        : k === "cmd" ? (q.cmd ? "@" + q.cmd : "更多指令")
        : (q.say ? "仅台词 ✓" : "仅台词");
    }
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  function refresh() {
    if (!built || !window.MYONLLint) return;
    var t = text();
    if (mode === "check") {
      var r = MYONLLint.run(t);
      var rows = r.issues.map(function (i) {
        return { no: i.line, level: i.level, why: i.code, text: i.msg, scene: i.scene || "" };
      });
      render(rows, "检查结果：错误 " + r.counts.error + " · 提醒 " + r.counts.warn + " · 提示 " + r.counts.info);
      return;
    }
    var qq = { char: q.char, scene: q.scene, onlySay: q.say, cmd: q.cmd, text: findEl.value.trim() || null };
    var f = MYONLLint.filter(t, qq);
    var out = f.rows.slice(0, 300).map(function (x) {
      var why = x.why || (x.kind === "nar" ? "旁白" : (x.kind === "option" ? "选项" : (x.kind === "cmd" ? "@" + x.cmd : "")));
      return { no: x.no, level: "info", why: why, text: String(x.text || "").slice(0, 80), scene: x.scene };
    });
    render(out, f.total ? (f.total + " 处" + (qq.text || q.char || q.scene || q.say || q.cmd ? "命中" : "句子")) : "");
  }

  function render(rows, title) {
    syncChips();
    if (!rows.length) {
      listEl.innerHTML = '<div class="ml-empty">' + esc(title || "没有结果") + "</div>";
      return;
    }
    var head = title ? '<div class="ml-empty" style="padding:6px 4px 10px">' + esc(title) + "</div>" : "";
    listEl.innerHTML = head + rows.map(function (x) {
      return '<button class="ml-item" data-no="' + x.no + '">' +
        '<span class="ml-no">' + x.no + "</span>" +
        '<span class="ml-dot ' + (x.level === "error" ? "err" : x.level === "warn" ? "warn" : "info") + '"></span>' +
        '<span class="ml-why">' + esc(x.why || "") + "</span>" +
        '<span class="ml-txt">' + esc(x.text || "") + "</span></button>";
    }).join("");
    listEl.onclick = function (e) {
      var b = e.target.closest && e.target.closest(".ml-item");
      if (b) jumpTo(parseInt(b.getAttribute("data-no"), 10));
    };
  }

  function jumpTo(n) {
    var ta = source();
    if (!ta || !n) return;
    var lines = String(ta.value || "").split("\n");
    if (n < 1 || n > lines.length) return;
    var start = 0;
    for (var i = 0; i < n - 1; i++) start += lines[i].length + 1;
    try { ta.focus({ preventScroll: true }); } catch (e) { ta.focus(); }
    ta.setSelectionRange(start, start + lines[n - 1].length);
    var lh = parseFloat(getComputedStyle(ta).lineHeight) || 22;
    ta.scrollTop = Math.max(0, (n - 1) * lh - lh * 2);
  }

  function replaceAll() {
    var find = findEl.value;
    if (!find) return toast("先填要查找的内容");
    if (!window.MYONLLint) return;
    var t = text();
    var inc = !!cmdEl.checked;
    if (inc && !window.confirm("会把指令行、label 名和选项一起改。label 改名后所有指向它的 @jump 都会断链，确定？")) return;
    var r = MYONLLint.replace(t, find, replEl.value, { includeCmd: inc });
    if (!r.count) return toast("没找到「" + find + "」");
    undoBuf = t;
    undoBtn.disabled = false;
    var ta = source();
    ta.value = r.text;
    try { ta.dispatchEvent(new Event("input", { bubbles: true })); } catch (e) {}
    afterReplace(r.count);
  }

  // 替换后立刻体检：断链必须当场看见，不能等用户跑起来才发现。
  function afterReplace(count) {
    var r = MYONLLint.run(text());
    var errs = r.issues.filter(function (i) { return i.level === "error"; });
    if (errs.length) {
      alertEl.classList.remove("hidden");
      alertEl.innerHTML = "<b>替换了 " + count + " 处，但有 " + errs.length + " 处断链：</b>" +
        errs.slice(0, 20).map(function (i) {
          return '<button class="ml-aline" data-no="' + i.line + '">第 ' + i.line + " 行 · " + esc(i.msg) + "</button>";
        }).join("");
      alertEl.onclick = function (e) {
        var b = e.target.closest && e.target.closest(".ml-aline");
        if (b) jumpTo(parseInt(b.getAttribute("data-no"), 10));
      };
    } else {
      alertEl.classList.add("hidden");
      toast("替换了 " + count + " 处");
    }
    mode = "check";
    refresh();
  }

  function undo() {
    if (undoBuf == null) return;
    var ta = source();
    if (!ta) return;
    ta.value = undoBuf;
    undoBuf = null;
    undoBtn.disabled = true;
    try { ta.dispatchEvent(new Event("input", { bubbles: true })); } catch (e) {}
    alertEl.classList.add("hidden");
    mode = "check";
    refresh();
    toast("已撤销这次替换");
  }

  function open() {
    // 工作台/首页时 #source 还挂着别的作品的残留文本，查出来的是错的
    if (document.body.classList.contains("m-home-open")) {
      toast("先打开剧本，再查找");
      return;
    }
    // 手机默认落"逐句编辑"，那儿没有光标也没有原文。先切到源码再查，
    // 否则用户查出来点一行，光标落在看不见的地方。
    var codeBtn = document.querySelector('.m-mode[data-mode="code"]');
    if (codeBtn && !codeBtn.classList.contains("on")) codeBtn.click();
    build();
    root.classList.remove("hidden");
    findEl.value = "";
    replEl.value = "";
    mode = "filter";
    alertEl.classList.add("hidden");
    refresh();
    setTimeout(function () { refresh(); }, 260);   // 等切源码后的布局落定再扫一次
    try { if (!isMobile()) findEl.focus(); } catch (e) {}
  }

  function close() {
    if (root) root.classList.add("hidden");
  }

  function isMobile() {
    return window.matchMedia("(max-width: 860px), (pointer: coarse)").matches;
  }

  // 入口：手机顶栏一个「查找」，桌面 Ctrl+F。顶栏按钮插在「菜单」前面，
  // 和「预览」同一排 —— 别人找得到，又不占底栏那三个内容 tab。
  function mountEntry() {
    if (!document.getElementById("mTopFind")) {
      var fm = document.querySelector('.menubar .menu-item[data-menu="file"]');
      if (fm && fm.parentNode) {
        var b = document.createElement("button");
        b.type = "button";
        b.id = "mTopFind";
        b.className = "m-top-preview";
        b.textContent = "查找";
        b.title = "查找 / 替换 / 检查全文";
        b.addEventListener("click", open);
        fm.parentNode.insertBefore(b, fm);
      }
    }
    // 手机上的真入口：场景编辑页会把 menubar 压掉，顶栏那个「查找」在那屏根本看不见。
    // 一颗常驻浮钮，不依赖任何容器，逐句页和源码页都在。
    if (!document.getElementById("mlFab")) {
      var fab = document.createElement("button");
      fab.type = "button";
      fab.id = "mlFab";
      fab.className = isMobile() ? "" : "hide";
      fab.textContent = "查";
      fab.title = "查找 / 替换 / 检查全文";
      fab.addEventListener("click", open);
      document.body.appendChild(fab);
    }
  }

  document.addEventListener("keydown", function (e) {
    if ((e.ctrlKey || e.metaKey) && (e.key === "f" || e.key === "F")) {
      e.preventDefault();
      open();
    } else if (e.key === "Escape") {
      close();
    }
  });

  function boot() {
    mountEntry();
    if (window.MYONLLint && source()) build();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
  window.MYONLLintUI = { open: open, close: close, refresh: refresh };
})();
