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

  // 判据必须和 editor_shell.js 的 MOBILE_MQ 一模一样。
  // 两边不一致时会出现"底部五个 tab 已经建好了，但场景表单没建"的缝合状态——
  // 平板横屏 1280×800 就是这么漏出来的（860 判不到，触摸那一条能判到）。
  var mq = window.matchMedia("(max-width: 860px), (max-height: 520px), " +
    "(pointer: coarse) and (hover: none) and (max-width: 1400px)");
  var subEl = null;      // 二级页容器
  var sheetEl = null;    // 素材大图 sheet
  var sheetMask = null;
  var sheetCard = null;
  var guard = false;     // 拦截一次卡片点击，避免「打开 sheet」也触发「插入」

  function narrow() { return mq.matches; }

  /* ============================ 外观：分组列表 ============================ */

  // 每组一句人话：说清"点进去能改什么"。原来这里显示「当前 10」「当前 420」，
  // 那是开发者参数，创作者不知道 10 是什么单位；数字留在二级页的滑杆旁边（README 13.④）。
  var GROUP_HINT = {
    "对话框": "位置 · 大小 · 文字",
    "名字框": "说话人名字怎么显示",
    "对话框皮肤": "换一套跟画风搭的外观",
    "选项按钮": "分支选项长什么样",
    "快捷栏": "存档 / 读档 / 自动那一排",
    "游戏内菜单": "玩家点菜单看到的",
    "设置页": "玩家能调的音量与文字速度",
    "配色": "主色与文字颜色",
    "界面开关": "哪些界面要显示",
    "全局": "字体 · 缩放 · 整体风格"
  };

  function refreshSummaries() {
    var list = document.querySelector(".m-grouplist");
    if (!list) return;
    Array.prototype.forEach.call(list.querySelectorAll(".m-group-row"), function (row) {
      var slot = row.querySelector(".m-gr-val");
      if (!slot) return;
      var name = (row.querySelector(".m-gr-name") || {}).textContent || "";
      slot.textContent = GROUP_HINT[name.trim()] || "";
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

  /* ======================= 剧本页：逐句 / 源码（P110） =======================
   * 关键判断：手机上「看不见的场景编辑器」= 认知负担的根。
   * 桌面顶栏那个「场景」小字在窄屏是隐藏的，所以手机用户只能面对 @character 文本。
   * 这里在剧本正文上方放一个两格切换：默认「逐句编辑」直接开可视化场景页，
   * 「源码」才是那一坨 @ 指令。不写代码的人永远不会被丢进源码。
   */
  var modeBar = null;

  function buildScriptModes() {
    if (!narrow() || modeBar) return;
    var wrap = document.getElementById("sourceWrap");
    if (!wrap || !wrap.parentNode) return;
    modeBar = document.createElement("div");
    modeBar.className = "m-modebar";
    modeBar.innerHTML =
      '<button type="button" class="m-mode on" data-mode="sent">逐句编辑</button>' +
      '<button type="button" class="m-mode" data-mode="code">源码</button>';
    wrap.parentNode.insertBefore(modeBar, wrap);
    modeBar.addEventListener("click", function (e) {
      var b = e.target.closest ? e.target.closest(".m-mode") : null;
      if (!b) return;
      setScriptMode(b.dataset.mode);
    });
  }

  function sceneOpen() {
    var p = document.getElementById("scenePage");
    return !!(p && p.classList.contains("open"));
  }

  function markMode(m) {
    if (!modeBar) return;
    Array.prototype.forEach.call(modeBar.querySelectorAll(".m-mode"), function (b) {
      b.classList.toggle("on", b.dataset.mode === m);
    });
  }

  function setScriptMode(m) {
    markMode(m);
    if (m === "sent") {
      // P217：只有「真的从源码切过来」才回列表。原来无条件 exitDetail()，
      // 于是任何一次重入（底栏「剧本」tab 的 80ms 兜底会点一下「逐句」按钮）
      // 都把正在读的那一幕踢回场景列表 —— 用户看到的就是「打开作品弹出个陌生界面」。
      if (window.__openSceneEditor && !sceneOpen()) {
        window.__openSceneEditor();
        // 重开时回到用户上次待的那一态：正在读第一幕就还回第一幕，
        // 自己点过「‹ 场景列表」的就留在列表。wantDetail 只由人的动作改。
        if (wantDetail) setTimeout(enterDetail, 0); else exitDetail();
      }
    } else if (sceneOpen()) {
      var c = document.getElementById("sceneClose");
      if (c) c.click();
    }
  }

  /* ==================== 场景页：手机上的「列表 → 单个场景」 ==================== */
  var scnBack = null, scnMore = null, scnPop = null;
  var autoEnterDone = false;   // P217：本次进作品是否已自动落到第一幕（整页 reload 会重置）
  var wantDetail = false;      // P217：用户此刻想待在「某一幕」还是「场景列表」，只由人的动作改

  function closePop() { if (scnPop) scnPop.classList.remove("on"); }

  function enterDetail() {
    var p = document.getElementById("scenePage");
    if (p) p.classList.add("m-detail");
    closePop();
  }

  function exitDetail() {
    var p = document.getElementById("scenePage");
    if (p) p.classList.remove("m-detail");
    closePop();
  }

  function buildSceneMobile() {
    if (!narrow()) return;
    var p = document.getElementById("scenePage");
    if (!p || p.dataset.mBuilt === "1") return;
    var head = p.querySelector(".cp-head");
    if (!head) return;

    // 返回：从「单个场景」退回「场景列表」，只在详情页出现
    scnBack = document.createElement("button");
    scnBack.type = "button";
    scnBack.className = "cp-btn scn-back";
    scnBack.innerHTML = "&#8249; 场景列表";
    scnBack.addEventListener("click", function () { wantDetail = false; exitDetail(); });
    head.insertBefore(scnBack, head.firstChild);

    // ⋯：复制/删除/刷新原来挤在顶栏，窄屏上根本点不准，收进一个弹层
    if (!scnPop) {
      scnPop = document.createElement("div");
      scnPop.className = "scn-pop";
      [["sceneCopy", "复制这一幕"], ["sceneRename", "重命名这一幕"], ["sceneDel", "删除这一幕"], ["sceneRefresh", "重新读取剧本"]]
        .forEach(function (it) {
          var b = document.createElement("button");
          b.type = "button";
          b.textContent = it[1];
          b.addEventListener("click", function () {
            var src = document.getElementById(it[0]);
            closePop();
            if (src) src.click();
          });
          scnPop.appendChild(b);
        });
      p.appendChild(scnPop);
    }
    scnMore = document.createElement("button");
    scnMore.type = "button";
    scnMore.className = "cp-btn scn-more";
    scnMore.textContent = "\u22EF";
    scnMore.addEventListener("click", function (e) {
      e.stopPropagation();
      if (scnPop) scnPop.classList.toggle("on");
    });
    var closeBtn = document.getElementById("sceneClose");
    if (closeBtn) head.insertBefore(scnMore, closeBtn);
    else head.appendChild(scnMore);

    // 顶栏原来 7 个按钮，窄屏一律挤成两行还被截断。
    // 只留「＋新场景 / 保存修改 / ✕」三个，其余（角色库、复制、删除…）标成 scn-extra 由 CSS 收进 ⋯。
    var KEEP = { sceneAdd: 1, sceneSave: 1, sceneClose: 1 };
    Array.prototype.forEach.call(head.querySelectorAll(".cp-btn"), function (b) {
      if (b === scnBack || b === scnMore) return;
      if (b.id && KEEP[b.id]) return;
      b.classList.add("scn-extra");
    });

    p.dataset.mBuilt = "1";
  }

  // 捕获阶段：不阻断原来的 selectScene（它在 listEl 上冒泡），只管切页
  document.addEventListener("click", function (e) {
    if (!narrow()) return;
    var t = e.target;
    if (t && t.closest && t.closest("#sceneList .scene-item")) {
      wantDetail = true;
      buildSceneMobile();
      setTimeout(enterDetail, 0);
      return;
    }
    closePop();
  }, true);

  // 关掉场景页（✕）就回到「源码」那格的高亮，不能让两格都说自己是当前
  document.addEventListener("click", function (e) {
    var t = e.target;
    if (t && t.closest && t.closest("#sceneClose")) markMode("code");
  });

  /* ============================ 启动与重入 ============================ */

  function boot() {
    if (narrow()) {
      buildGroups();
      refreshSummaries();
      buildScriptModes();
      buildSceneMobile();
      // 按钮默认就高亮「逐句」，但以前只建了按钮、没真的打开场景页，
      // 结果用户看到「逐句编辑」是选中的、界面却还是源码 + 一片空白。
      // 但点「外观」会 80ms 后再 boot 一次，那时 UI 设计区已经开了，
      // 这里再 setScriptMode("sent") 就把场景页重新盖回去，用户点外观画面还是场景表单。
      var otherPageOpen = Array.prototype.some.call(
        document.querySelectorAll(".center-page.open"),
        function (p) { return p.id !== "scenePage"; });
      // 底栏停在「外观」「导出」时不该再把场景页盖回来：导出会先关掉所有 center-page，
      // 80ms 后 boot 跑到这里，那些页还没重新出现，只看 otherPageOpen 拦不住。
      var curTab = document.querySelector(".m-tab.active");
      var onScript = !curTab || curTab.dataset.tab === "script";
      // P217：场景页已经开着就别再 setScriptMode("sent") —— 它里面有一句 exitDetail()，
      // boot 每次重入都会把人从「正在读的那一幕」踢回场景列表。只补高亮即可。
      if (onScript && !otherPageOpen && !document.body.classList.contains("m-home-open")) {
        if (sceneOpen()) markMode("sent"); else setScriptMode("sent");
      }
      // P217：进作品第一眼必须是台词，不是「场景列表」。
      // 原来只有「恰好一幕」才自动进详情，多幕（示范案例就有 start/坦白/岔开 三幕）
      // 停在列表上：顶栏「＋新场景 / 搜索场景名 / 逐句编辑|源码（高级）」，下面三行幕名 + 整屏空白。
      // 用户原话「我打开一个作品，它直接给我弹出一个莫名其妙的界面，那是肯定不可能允许的」。
      // autoEnterDone 只在本模块生命周期内生效（进作品是整页 reload），
      // 所以用户主动点「‹ 场景列表」退回列表后，后续 boot 不会把他再踢回详情。
      // 场景列表是读完剧本后才渲染的，260ms 时可能还是空的 —— 一次不中就再等一会儿，
      // 最多试 12 次（约 2.4s）。只试一次的话，慢一点的机器上永远停在列表。
      var tries = 0;
      (function autoEnter() {
        if (autoEnterDone) return;
        var p = document.getElementById("scenePage");
        if (!p || p.classList.contains("m-detail") || document.body.classList.contains("m-home-open")) return;
        var tab = document.querySelector(".m-tab.active");
        if (tab && tab.dataset.tab !== "script") return;   // 从「预览/导出」进来的，别抢人家的页
        var items = document.querySelectorAll("#sceneList .scene-item");
        if (!items.length) { if (++tries < 12) setTimeout(autoEnter, 200); return; }
        autoEnterDone = true;
        wantDetail = true;
        items[0].click();
        enterDetail();
      })();
    } else {
      // 回到桌面宽度：把面板还回去，别留在二级页里
      closeGroup();
      closeSheet();
      exitDetail();
      markMode("code");
    }
  }

  /* ======================= 源码字号（手机上字太小） ======================= */
  // 360 宽、15px 一行只能塞约 20 字，长剧本看着就是一片糊。这里给一个直接能调的：
  // 双击左边的行号栏放大一档（行号栏 user-select:none，不会跟选词打架），⋯ 菜单里也有一项。
  var SRC_PX = [15, 18, 21];
  var SRC_FONT_KEY = "myonl:srcFont";

  function applySrcFont(px) {
    var src = document.getElementById("source");
    if (!src) return;
    src.style.fontSize = px + "px";
    // 行号栏跟着放大，否则 21px 正文旁边还是 11px 的小数字，宽度也不够两位数
    var ln = document.getElementById("lineNumbers");
    if (ln) { ln.style.fontSize = Math.round(px * 0.72) + "px"; ln.style.width = Math.round(px * 2.4) + "px"; }
    Array.prototype.forEach.call(document.querySelectorAll(".hl-layer"), function (h) {
      h.style.fontSize = px + "px";
    });
    try { localStorage.setItem(SRC_FONT_KEY, String(px)); } catch (e) {}
  }

  function bumpSrcFont() {
    var src = document.getElementById("source");
    var cur = parseInt((src && src.style.fontSize) || "15", 10);
    applySrcFont(SRC_PX[(SRC_PX.indexOf(cur) + 1) % SRC_PX.length]);
  }
  window.__bumpSrcFont = bumpSrcFont;

  function bindSrcFont() {
    var ln = document.getElementById("lineNumbers");
    if (ln && !ln.__fontBound) {
      ln.__fontBound = true;
      ln.title = "双击放大源码字号";
      ln.addEventListener("dblclick", bumpSrcFont);
    }
    var saved = 0;
    try { saved = parseInt(localStorage.getItem(SRC_FONT_KEY), 10); } catch (e) {}
    if (SRC_PX.indexOf(saved) >= 0) applySrcFont(saved);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
  setTimeout(bindSrcFont, 900);

  if (mq.addEventListener) mq.addEventListener("change", boot);
  else if (mq.addListener) mq.addListener(boot);

  // 打开 UI 设计后要补建列表；分组面板的数值也会被编辑后变化
  document.addEventListener("click", function (e) {
    var t = e.target;
    if (t && t.closest && t.closest("#btnUIDesign")) setTimeout(boot, 80);
  }, true);
  setInterval(function () { if (narrow() && document.querySelector(".m-grouplist")) refreshSummaries(); }, 800);

  // 空台词卡下的「试一句」：点一下直接把那句话填进那个输入框。
  // 新手对着空框不知道第一句写什么，这就是给他一个起手式的台阶。
  document.addEventListener("click", function (e) {
    var t = e.target && e.target.closest ? e.target.closest(".sf-tip") : null;
    if (!t) return;
    var box = t.closest(".sf-tipbox");
    var ta = box && box.parentNode.querySelector(".sf-text");
    if (!ta) return;
    e.preventDefault();
    ta.value = t.textContent;
    ta.focus();
    ta.dispatchEvent(new Event("input", { bubbles: true }));
  }, true);

  // P197：手机上「检查器 / 时间线」是桌面右栏的分段，点了只切右栏内部区块 ——
  // 手机右栏在抽屉里，主界面看不到任何变化，于是这两个按钮在真机上就是"点了没反应"。
  // 手机上直接收掉：预览有底栏那一格，检查器/时间线留给电脑。
  function dropRightTabs() {
    var t = document.getElementById("rightTabs");
    if (t && narrow()) t.remove();
  }
  dropRightTabs();
  document.addEventListener("click", function (e) {
    var t = e.target;
    if (t && t.closest && t.closest("#btnUIDesign")) setTimeout(function () { boot(); dropRightTabs(); }, 80);
  }, true);

  // P197b：手机端「导出」不该是"打开一整个界面设计弹窗、还要自己滑到底才看见导出"。
  // 点导出就把弹窗收成导出页：只留导出条（.off-export / .uid-web），参数区全部收起；
  // 切回「外观」或关弹窗时再放回来。桌面端不动。原来单独一个 export_sheet.js，
  // 但静态路由是白名单，多一个文件就要多一条路由 + 多一个打包清单项，合进来省两处。
  var attHidden = [];   // [元素, 原 display]
  var txtHidden = [];   // [元素, 原文字]
  function exportModal() { return document.getElementById("uiDesignModal") || document.querySelector(".ui-design-modal"); }
  function hideEl(el) {
    if (!el || !el.style || el.style.display === "none") return;
    attHidden.push([el, el.style.display]);
    el.style.display = "none";
  }
  function focusExport() {
    if (!(navigator.maxTouchPoints > 0 && Math.min(window.innerWidth, window.innerHeight) < 700)) return;
    var m = exportModal();
    if (!m) return;
    restoreExport();
    m.querySelectorAll(".ui-design-form, .m-subbody, .modal-body").forEach(function (f) {
      f.childNodes.forEach(function (c) {
        if (c.nodeType !== 1) return;
        if (c.classList.contains("off-export") || c.classList.contains("uid-web")) return;
        if (!c.textContent.trim() && !c.querySelector("button, input, img")) return;
        hideEl(c);
      });
    });
    m.querySelectorAll(".right-tabs, .uid-tabs, .ui-design-tabs, .uid-nav, .ui-dl").forEach(hideEl);
    m.querySelectorAll(".cp-title, .uid-title, .modal-title").forEach(function (t) {
      if (/导出/.test(t.textContent)) return;
      txtHidden.push([t, t.textContent]);
      t.textContent = "导出";
    });
    var bar = m.querySelector(".off-export, .uid-web");
    if (bar && bar.scrollIntoView) bar.scrollIntoView({ block: "start" });
  }
  function restoreExport() {
    attHidden.forEach(function (h) { if (h[0].style) h[0].style.display = h[1]; });
    txtHidden.forEach(function (h) { h[0].textContent = h[1]; });
    attHidden = [];
    txtHidden = [];
  }
  window.__mExport = { focus: focusExport, restore: restoreExport };
  document.addEventListener("click", function (e) {
    var t = e.target;
    if (t && t.closest && t.closest("#uidClose, .uid-close")) setTimeout(restoreExport, 60);
  }, true);

  window.MYONLMobile = { boot: boot, closeGroup: closeGroup, refresh: refreshSummaries };
})();
