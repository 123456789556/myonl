/* P202 手机版面护栏（脚本层）
   干四件事：
   1. 给 html 打 m-shell / m-wide，横屏顶栏从「一排文字」压成「图标 + 更多」
   2. 顶栏作品名可点 → 改名（先建后名的后半截：不用在新建时被迫起名）
   3. 页面切换前清浮层，别留异物压在上一页上
   4. 对外给一个检查口 window.__myonlOverflowAudit()：把出界/折行的控件列出来
   全部只碰手机壳（pointer: coarse），桌面端一行不改。 */
(function () {
  "use strict";
  var DE = document.documentElement;
  var LIB = "myonl:off:lib:v1";
  var DRAFT = "myonl:off:draft:v1";
  var ORPHAN = "myonl:off:draft:v1:orphan";

  function shell() {
    // 真机是 pointer:coarse；窄窗口（平板分屏 / 网页预览）也当手机壳，否则一窄就露桌面顶栏
    try { if (window.matchMedia("(pointer: coarse)").matches) return true; } catch (e) {}
    return window.innerWidth <= 900 || /Android|iPhone|iPad/i.test(navigator.userAgent || "");
  }
  function wide() { return window.innerWidth > window.innerHeight && window.innerHeight <= 560; }

  function iconify(el, on, txt, icon, label) {
    if (!el) return;
    if (on) {
      if (el.getAttribute("data-p202") !== "1") {
        el.setAttribute("data-p202", "1");
        el.setAttribute("data-p202-txt", el.textContent);
      }
      el.textContent = icon;
      el.setAttribute("aria-label", label);
    } else if (el.getAttribute("data-p202") === "1") {
      el.textContent = el.getAttribute("data-p202-txt") || txt;
      el.removeAttribute("aria-label");
    }
  }

  /* ---- P264 横屏分栏：左栏可拖宽、预览可收起、编辑与预览换位 ----
     用户原话「横屏编辑和预览区换一下位置，预览区可关闭，左边区域收一些可以拖动宽度，自适应做好」。
     拖动只改 --m-rail，没有任何元素写死 width；收起只给 html 挂 m-stage-off，版式全交给 CSS。 */
  var RAIL = "myonl:off:railW:v1", STAGE = "myonl:off:stageOff:v1";
  function railPx() {
    var v = 0; try { v = parseInt(localStorage.getItem(RAIL) || "", 10) || 0; } catch (e) {}
    return v > 0 ? v : 232;
  }
  function stageOff() { try { return localStorage.getItem(STAGE) === "1"; } catch (e) { return false; } }
  // 左栏最多 320，整块编辑区至少留 380：宽度不够时先压缩左栏，不允许把编辑区挤成一条缝
  function railMax() { return Math.max(150, Math.min(320, window.innerWidth - 380)); }
  function applyPane() {
    if (!shell()) { DE.classList.remove("m-stage-off"); DE.style.removeProperty("--m-rail"); return; }
    DE.style.setProperty("--m-rail", Math.min(Math.max(railPx(), 150), railMax()) + "px");
    DE.classList.toggle("m-stage-off", stageOff());
    // 分栏只在横屏且 ≥700 宽成立（同 @media (orientation:landscape) and (min-width:700px)）；竖屏不许多出手柄和按钮
    var split = window.innerWidth >= 700 && window.innerWidth > window.innerHeight;
    var g = document.getElementById("mRailGrip"), b = document.getElementById("mStageBtn");
    if (g) g.style.display = split ? "" : "none";
    if (b) {
      b.style.display = split ? "" : "none";
      b.textContent = stageOff() ? "\u9884\u89C8" : "\u00D7";
      b.setAttribute("aria-label", stageOff() ? "展开画面预览" : "收起画面预览");
    }
  }
  function toggleStage() {
    try { localStorage.setItem(STAGE, stageOff() ? "0" : "1"); } catch (e) {}
    applyPane();
  }
  function ensurePane() {
    var p = document.getElementById("scenePage");
    if (!p) return;
    if (!document.getElementById("mRailGrip")) {
      var g = document.createElement("div");
      g.id = "mRailGrip"; g.className = "m-rail-grip"; g.setAttribute("role", "separator");
      p.appendChild(g);
      g.addEventListener("pointerdown", function (e) {
        e.preventDefault(); e.stopPropagation();
        try { g.setPointerCapture(e.pointerId); } catch (err) {}
        p.classList.add("m-dragging");
        function move(ev) {
          var w = Math.min(Math.max(Math.round(ev.clientX - p.getBoundingClientRect().left), 150), railMax());
          DE.style.setProperty("--m-rail", w + "px");
        }
        function up() {
          p.classList.remove("m-dragging");
          g.removeEventListener("pointermove", move); g.removeEventListener("pointerup", up);
          try { localStorage.setItem(RAIL, String(parseInt(DE.style.getPropertyValue("--m-rail"), 10) || 232)); } catch (err) {}
        }
        g.addEventListener("pointermove", move); g.addEventListener("pointerup", up);
      });
    }
    var sw = p.querySelector(".sf-stage-wrap");
    if (sw && !document.getElementById("mStageBtn")) {
      var btn = document.createElement("button");
      btn.type = "button"; btn.id = "mStageBtn"; btn.className = "m-stage-btn";
      btn.addEventListener("click", function (e) { e.preventDefault(); e.stopPropagation(); toggleStage(); });
      sw.appendChild(btn);
    }
    applyPane();
  }

  function apply() {
    if (!shell()) return;
    DE.classList.add("m-shell"); if (window.visualViewport) DE.style.setProperty("--m-vvh", Math.round(window.visualViewport.height) + "px");
    applyPane(); ensurePane();
    var w = wide();
    DE.classList.toggle("m-wide", w);
    iconify(document.querySelector('.menubar .menu-item[data-menu="file"]'), w, "菜单", "☰", "菜单");
    iconify(document.getElementById("mTopPreview"), w, "预览", "▶", "预览");
  }

  /* ---- 改名：lib 与草稿一起改，漏一处就等于把内容丢掉 ---- */
  function readLib() {
    try { return JSON.parse(localStorage.getItem(LIB) || "{}"); } catch (e) { return null; }
  }
  function currentName() {
    var lib = readLib();
    return (lib && lib.current) || "";
  }
  // 草稿是单键、按 name 区分作品：改名不同步，下次打开会被判成「别人的草稿」而丢弃
  function renameDrafts(oldName, newName) {
    [DRAFT, ORPHAN].forEach(function (k) {
      try {
        var d = JSON.parse(localStorage.getItem(k) || "null");
        if (d && d.name === oldName) { d.name = newName; localStorage.setItem(k, JSON.stringify(d)); }
      } catch (e) {}
    });
  }
  function renameProject(oldName, newName) {
    // P203：离线内核把作品库缓存在 memLib 里，直接改 localStorage 会被下一次 writeLib
    // 用旧对象整体覆盖回去（名字看着改了，刷新又变回来）。有 __myonlLib 就只走它。
    var api = window.__myonlLib;
    var lib = api ? api.read() : readLib();
    if (!lib || !lib.projects) return "这本机上还没有作品库";
    if (lib.projects.some(function (p) { return p.name === newName; })) return "已经有同名作品了";
    var hit = null;
    lib.projects.forEach(function (p) { if (p.name === oldName) hit = p; });
    if (!hit) return "找不到「" + oldName + "」";
    hit.name = newName;
    hit.mtime = Math.round(Date.now() / 1000);
    if (lib.current === oldName) lib.current = newName;
    if (api) api.write(lib);
    else try { localStorage.setItem(LIB, JSON.stringify(lib)); } catch (e) { return "写不进去，存储可能满了"; }
    renameDrafts(oldName, newName);
    try { if (sessionStorage.getItem("myonl:projName") === oldName) sessionStorage.setItem("myonl:projName", newName); } catch (e) {}
    var t = document.querySelector(".m-title2");
    if (t && t.textContent === oldName) { t.textContent = newName; t.title = newName; }
    var fp = document.getElementById("filePath");
    if (fp && fp.textContent.trim() === oldName) fp.textContent = newName;
    return "";
  }
  // 作品卡的「⋯ → 改名」在 editor_trash.js，它没有自己去改库的权限，只能调这一个
  window.MYONLRenameProject = renameProject;

  function openRename() {
    if (!shell() || document.getElementById("p202Mask")) return;
    var oldName = currentName();
    if (!oldName) return;
    var mask = document.createElement("div");
    mask.id = "p202Mask";
    mask.className = "p202-mask";
    mask.innerHTML =
      '<div class="p202-box" role="dialog" aria-label="改个名字">' +
        '<h4>改个名字</h4>' +
        '<input class="p202-in" id="p202In" maxlength="24" autocomplete="off" spellcheck="false">' +
        '<div class="p202-row">' +
          '<button type="button" class="p202-cancel" id="p202Cancel">取消</button>' +
          '<button type="button" class="p202-ok" id="p202Ok">改名</button>' +
        '</div>' +
      '</div>';
    document.body.appendChild(mask);
    var inp = mask.querySelector("#p202In");
    inp.value = oldName;
    inp.focus();
    inp.select();
    function done() { mask.remove(); }
    mask.addEventListener("click", function (e) { if (e.target === mask) done(); });
    mask.querySelector("#p202Cancel").addEventListener("click", done);
    function submit() {
      var v = String(inp.value || "").trim();
      if (!v || v === oldName) { done(); return; }
      var err = renameProject(oldName, v);
      if (err) { inp.value = v; inp.setAttribute("placeholder", err); inp.value = ""; return; }
      done();
    }
    mask.querySelector("#p202Ok").addEventListener("click", submit);
    inp.addEventListener("keydown", function (e) { if (e.key === "Enter") submit(); });
  }

  /* ---- 页面切换不许留异物 ---- */
  function cleanOverlays() {
    ["mlRoot", "mTryPlay", "p202Mask"].forEach(function (id) {
      var el = document.getElementById(id);
      if (!el) return;
      el.classList.add("hidden");
      el.style.display = "none";
    });
    Array.prototype.forEach.call(document.querySelectorAll(".m-sheet, .modal-mask, .insert-menu"), function (el) {
      if (el.parentNode) el.parentNode.removeChild(el);
    });
  }
  window.__myonlCleanOverlays = cleanOverlays;

  /* ---- 检查口：出界 / 折行，一个都不许有 ---- */
  window.__myonlOverflowAudit = function () {
    var vw = window.innerWidth, vh = window.innerHeight, bad = [];
    var sel = "button, .menu-item, .m-top-preview, .m-title2, .m-tabbar .m-tab, .m-home-card, .m-card-name";
    function inScroller(el) {
      for (var p = el.parentNode; p && p.nodeType === 1; p = p.parentNode) {
        var cs = getComputedStyle(p);
        if (/(auto|scroll)/.test(cs.overflowY) || /(auto|scroll)/.test(cs.overflowX)) return true;
      }
      return false;
    }
    Array.prototype.forEach.call(document.querySelectorAll(sel), function (el) {
      var r = el.getBoundingClientRect();
      if (!r.width || !r.height) return;
      var cs = getComputedStyle(el);
      if (cs.visibility === "hidden" || cs.display === "none") return;
      // 省略号截断是设计内行为，不是折行
      if (cs.textOverflow === "ellipsis" && cs.whiteSpace === "nowrap") return;
      // 完全在屏幕外（左侧收纳条 / 视口下方待滚动内容）不算遮挡
      if (r.right <= 0 || r.top >= vh || r.bottom <= 0) return;
      if (r.right > vw + 1 || r.bottom > vh + 1 || (r.left < -1 && r.right > 0)) {
        if (inScroller(el)) return;
        bad.push({ el: el.id || el.className, why: "出界", box: [Math.round(r.left), Math.round(r.top), Math.round(r.right), Math.round(r.bottom)] });
      } else if (el.scrollWidth > el.clientWidth + 1 && cs.whiteSpace !== "nowrap") {
        bad.push({ el: el.id || el.className, why: "折行", w: [el.scrollWidth, el.clientWidth] });
      }
    });
    return bad;
  };

  // 返回首页 / 退出编辑器时先清一遍，别把浮层带到上一页
  document.addEventListener("click", function (e) {
    var t = e.target && e.target.closest ? e.target.closest("#mHomeBack, .m-work-back, .mb-back") : null;
    if (t) cleanOverlays();
  }, true);

  // 场景页是后建的：点进某一幕才把拖动手柄与「收起预览」按钮挂上去（P264）
  document.addEventListener("click", function (e) {
    var t = e.target && e.target.closest ? e.target.closest("#sceneList .scene-item") : null;
    if (t) setTimeout(ensurePane, 0);
  }, true);

  // 作品名可点改名
  document.addEventListener("click", function (e) {
    var t = e.target && e.target.closest ? e.target.closest(".m-title2") : null;
    if (t) openRename();
  }, false);

  window.addEventListener("resize", apply); try { if (window.visualViewport) window.visualViewport.addEventListener("resize", apply); } catch (e) {}
  window.addEventListener("orientationchange", function () { setTimeout(apply, 260); });
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", apply);
  else apply();
  setTimeout(apply, 400);
  setTimeout(apply, 1200);
})();
