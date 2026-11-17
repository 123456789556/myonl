/* P76：手机端多层交互。
 *
 * 上一版手机端最别扭的地方不是样式，是「层」：底部五个 tab，点进去却是三种完全不同的东西
 * —— 剧本留在原位、素材从上边滑出一个抽屉、外观和导出直接开一个桌面弹窗。每个 tab 都是
 * 一屏塞满的表单（外观页 10 个分组 tab 横排换行、十几个滑杆一次铺开），没有「列表 → 详情」
 * 这一层，手指找不到落点。
 *
 * 这里补两件事，都只在窄屏生效（<=860 宽 或 <=520 高），桌面端一行不跑：
 *   1. 外观页：10 个分组变成一份列表，一行一件事（名称 + 当前值 + ›），点进二级页再调参数，
 *      返回键回到列表。参数面板是原封不动搬过去的，编辑逻辑不动。
 *   2. 素材页：110px 的缩略图选不准图，点卡片先看大图，再决定「插入到剧本」。
 */
(function () {
  "use strict";

  var mq = window.matchMedia("(max-width: 860px), (max-height: 520px)");
  var subEl = null;      // 二级页容器
  var sheetEl = null;    // 素材大图 sheet
  var sheetMask = null;
  var sheetCard = null;
  var guard = false;     // 拦截一次卡片点击，避免「打开 sheet」也触发「插入」

  function narrow() { return mq.matches; }

  /* ============================ 外观：分组列表 ============================ */

  function firstValue(panel) {
    if (!panel) return "";
    var v = panel.querySelector(".uid-val");
    return v ? ("当前 " + v.textContent.trim()) : "";
  }

  function refreshSummaries() {
    var list = document.querySelector(".m-grouplist");
    if (!list) return;
    Array.prototype.forEach.call(list.querySelectorAll(".m-group-row"), function (row) {
      var panel = document.getElementById(row.dataset.panel);
      var slot = row.querySelector(".m-gr-val");
      if (slot) slot.textContent = firstValue(panel);
    });
  }

  function buildGroups() {
    if (!narrow()) return;
    var tabs = document.getElementById("uidTabs");
    if (!tabs || tabs.dataset.mBuilt === "1") return;
    if (document.querySelector(".m-grouplist")) { tabs.dataset.mBuilt = "1"; return; }

    var list = document.createElement("div");
    list.className = "m-grouplist";
    Array.prototype.forEach.call(tabs.querySelectorAll(".uid-tab"), function (btn) {
      var name = (btn.textContent || "").trim();
      var panelId = btn.dataset.panel;
      if (!name || !panelId) return;
      var row = document.createElement("button");
      row.type = "button";
      row.className = "m-group-row";
      row.dataset.panel = panelId;
      row.innerHTML =
        '<span class="m-gr-name"></span>' +
        '<span class="m-gr-val"></span>' +
        '<span class="m-gr-arrow">&#8250;</span>';
      row.querySelector(".m-gr-name").textContent = name;
      row.addEventListener("click", function () { openGroup(btn, name, panelId); });
      list.appendChild(row);
    });
    tabs.parentNode.insertBefore(list, tabs.nextSibling);
    tabs.classList.add("m-tabs-hide");
    tabs.dataset.mBuilt = "1";
    refreshSummaries();
  }

  function ensureSub() {
    if (subEl) return subEl;
    subEl = document.createElement("section");
    subEl.className = "m-subpage";
    subEl.innerHTML =
      '<div class="m-subhead">' +
        '<button type="button" class="m-back" aria-label="返回">&#8249;</button>' +
        '<span class="m-subtitle"></span>' +
      '</div>' +
      '<div class="m-subbody"></div>';
    document.body.appendChild(subEl);
    subEl.querySelector(".m-back").addEventListener("click", closeGroup);
    return subEl;
  }

  function openGroup(tabBtn, name, panelId) {
    var panel = document.getElementById(panelId);
    if (!panel) return;
    var sub = ensureSub();
    sub.querySelector(".m-subtitle").textContent = name;
    var body = sub.querySelector(".m-subbody");
    // 预览跟着分组一起进去：调参数时看得见效果，才是这个页面存在的理由
    var pv = document.querySelector(".ui-design-preview");
    if (pv) body.appendChild(pv);
    panel.dataset.mHome = "1";
    body.appendChild(panel);
    panel.style.display = "block";
    // 搬完再切分组：引擎的定位/预览都按容器尺寸算，搬动之后算才准
    tabBtn.click();
    sub.classList.add("on");
    document.body.classList.add("m-sub-open");
  }

  function closeGroup() {
    if (!subEl) return;
    var panel = subEl.querySelector(".m-subbody .uid-panel");
    var pv = subEl.querySelector(".m-subbody .ui-design-preview");
    var form = document.querySelector(".ui-design-form");
    var db = document.querySelector(".ui-design-body");
    if (pv && db) {
      if (form && form.parentNode === db) db.insertBefore(pv, form.nextSibling);
      else db.appendChild(pv);
    }
    if (panel) {
      if (form) form.appendChild(panel);
      panel.style.display = "none";
      delete panel.dataset.mHome;
    }
    subEl.classList.remove("on");
    document.body.classList.remove("m-sub-open");
    refreshSummaries();
  }

  /* ============================ 素材：看大图 ============================ */

  function ensureSheet() {
    if (sheetEl) return sheetEl;
    sheetMask = document.createElement("div");
    sheetMask.className = "m-sheet-mask";
    sheetMask.addEventListener("click", closeSheet);
    document.body.appendChild(sheetMask);

    sheetEl = document.createElement("div");
    sheetEl.className = "m-sheet";
    sheetEl.innerHTML =
      '<img alt="">' +
      '<div class="m-sheet-cap"></div>' +
      '<div class="m-sheet-acts">' +
        '<button type="button" class="m-sheet-act m-sheet-insert">插入到剧本</button>' +
        '<button type="button" class="m-sheet-act m-sheet-close">关闭</button>' +
      '</div>';
    document.body.appendChild(sheetEl);
    sheetEl.querySelector(".m-sheet-close").addEventListener("click", closeSheet);
    sheetEl.querySelector(".m-sheet-insert").addEventListener("click", function () {
      if (!sheetCard) return;
      guard = true;
      sheetCard.click();   // 走原来的插入逻辑
      guard = false;
      closeSheet();
    });
    return sheetEl;
  }

  function openSheet(card) {
    var img = card.querySelector("img");
    if (!img) return;
    var sheet = ensureSheet();
    sheet.querySelector("img").src = img.getAttribute("src") || "";
    var cap = card.querySelector(".asset-name") || card.querySelector(".asset-cap") || null;
    var name = (cap && cap.textContent.trim()) || card.getAttribute("title") || img.getAttribute("alt") || "";
    // 卡片名后面挂着桌面专属提示（「拖到代码区生成指令」），手机上没那东西，别端上来
    name = name.replace(/（[^）]*拖到[^）]*）$/, "").replace(/（拖[^）]*）$/, "");
    sheet.querySelector(".m-sheet-cap").textContent = name;
    sheetCard = card;
    sheetMask.classList.add("on");
    sheet.classList.add("on");
  }

  function closeSheet() {
    if (!sheetEl) return;
    sheetEl.classList.remove("on");
    sheetMask.classList.remove("on");
    sheetCard = null;
  }

  // 卡片点击在捕获阶段拦下：手机上先看大图，插入放到 sheet 里的按钮上
  document.addEventListener("click", function (e) {
    if (guard || !narrow()) return;
    var t = e.target;
    var card = t && t.closest ? t.closest(".asset-card") : null;
    if (!card) return;
    e.preventDefault();
    e.stopPropagation();
    openSheet(card);
  }, true);

  /* ============================ 启动与重入 ============================ */

  function boot() {
    if (narrow()) {
      buildGroups();
      refreshSummaries();
    } else {
      // 回到桌面宽度：把面板还回去，别留在二级页里
      closeGroup();
      closeSheet();
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }

  if (mq.addEventListener) mq.addEventListener("change", boot);
  else if (mq.addListener) mq.addListener(boot);

  // 打开 UI 设计后要补建列表；分组面板的数值也会被编辑后变化
  document.addEventListener("click", function (e) {
    var t = e.target;
    if (t && t.closest && t.closest("#btnUIDesign")) setTimeout(boot, 80);
  }, true);
  setInterval(function () { if (narrow() && document.querySelector(".m-grouplist")) refreshSummaries(); }, 800);

  window.MYONLMobile = { boot: boot, closeGroup: closeGroup, refresh: refreshSummaries };
})();
