/* ===================================================================
   P51/P52 游戏内 UI 设计区（六组：对话框/名字框/选项/快捷栏/菜单/设置页/全局）。
   从 editor_main.js 拆出（T16 域拆分）：本模块只读写 config.json 的 ui 段，
   通过 /api/ui-design(/preview) 与后端交互，不碰剧本正文。
   =================================================================== */
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  function postJSON(url, body) {
    return fetch(url, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body),
    }).then(r => r.json());
  }
  function toast(msg, isErr) {
    try { if (window.__editor && window.__editor.toast) window.__editor.toast(msg, isErr); } catch (e) {}
  }
  // ===== P51/P52：游戏内 UI 设计区（对话框/名字框/选项/快捷栏/菜单/设置页/配色/全局） =====
  let uidTimer = null;
  let uidScene = "dialog";
  let uidThemeDefaults = {};   // GET /api/ui-design 返回的引擎兜底色
  let uidThemeCleared = new Set(); // 点过「恢复引擎默认」的键 → 保存时用 null 清掉覆盖

  const UID_FIELDS = [
    // 对话框（dialogue.default）
    {id: "uidRadius", key: "radius", section: "dialogue"},
    {id: "uidOffsetX", key: "offset_x", section: "dialogue"},
    {id: "uidOffsetY", key: "offset_y", section: "dialogue"},
    {id: "uidPanelWidth", key: "panel_width", section: "dialogue"},
    {id: "uidHeight", key: "height", section: "dialogue"},
    // 名字框（dialogue.default）
    {id: "uidNameY", key: "name_y", section: "dialogue"},
    {id: "uidNameGap", key: "name_gap", section: "dialogue"},
    // 选项按钮（ui.choices）
    {id: "uidChoiceW", key: "width", section: "choices"},
    {id: "uidChoiceH", key: "row_height", section: "choices"},
    {id: "uidChoiceGap", key: "dialog_gap", section: "choices"},
    {id: "uidChoiceRadius", key: "radius", section: "choices"},
    // 快捷栏（ui.quickbar）
    {id: "uidQbW", key: "button_width", section: "quickbar"},
    {id: "uidQbH", key: "button_height", section: "quickbar"},
    {id: "uidQbGap", key: "gap", section: "quickbar"},
    {id: "uidQbMx", key: "margin_x", section: "quickbar"},
    {id: "uidQbMy", key: "margin_y", section: "quickbar"},
    {id: "uidQbAlpha", key: "alpha", section: "quickbar"},
    {id: "uidQbRadius", key: "radius", section: "quickbar"},
    {id: "uidQbPos", key: "position", section: "quickbar", isString: true},
    {id: "uidQbAlign", key: "align", section: "quickbar", isString: true},
    // 游戏内菜单（ui.menu）
    {id: "uidMenuW", key: "row_width", section: "menu"},
    {id: "uidMenuH", key: "row_height", section: "menu"},
    {id: "uidMenuTop", key: "top", section: "menu"},
    {id: "uidMenuRadius", key: "radius", section: "menu"},
    // 设置页（ui.settings）
    {id: "uidSetW", key: "row_width", section: "settings"},
    {id: "uidSetH", key: "row_height", section: "settings"},
    {id: "uidSetNav", key: "nav_width", section: "settings"},
    {id: "uidSetTop", key: "top", section: "settings"},
    // 全局（ui 顶层 + font/lh）
    {id: "uidPixelated", key: "pixelated", section: "ui", isBool: true},
    {id: "uidPixelScale", key: "pixel_scale", section: "ui"},
    {id: "uidCorner", key: "corner_radius", section: "ui"},
    {id: "uidFontBody", key: "body", section: "font"},
    {id: "uidLineHeight", key: "body", section: "line_height"},
  ];

  // 配色（config.json theme 段）：只暴露语义主题色，shadow 不调
  const THEME_FIELDS = [
    {id: "uidThemePrimary", key: "primary"},
    {id: "uidThemePrimarySoft", key: "primary_soft"},
    {id: "uidThemeAccent", key: "accent"},
    {id: "uidThemeSurface", key: "surface"},
    {id: "uidThemeSurfaceAlt", key: "surface_alt"},
    {id: "uidThemeText", key: "text"},
    {id: "uidThemeTextDim", key: "text_dim"},
    {id: "uidThemeBorder", key: "border"},
    {id: "uidThemeDanger", key: "danger"},
    {id: "uidThemeSuccess", key: "success"},
  ];

  function rgbToHex(v) {
    const arr = Array.isArray(v) && v.length >= 3 ? v : [255, 255, 255];
    const h = (n) => Math.max(0, Math.min(255, Math.round(Number(n) || 0)))
      .toString(16).padStart(2, "0");
    return "#" + h(arr[0]) + h(arr[1]) + h(arr[2]);
  }
  function hexToRgb(hex) {
    const m = /^#?([0-9a-f]{6})$/i.exec(String(hex || "").trim());
    if (!m) return [255, 255, 255];
    const n = parseInt(m[1], 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }
  function uidSetThemeColor(id, value) {
    const el = $(id);
    if (!el) return;
    const hex = rgbToHex(value);
    el.value = hex;
    const valEl = $(id + "Val");
    if (valEl) valEl.textContent = hex.toUpperCase();
  }

  // 配色行由 JS 生成：index.html 只留一个空面板，守住入口文件行数目标
  const THEME_LABELS = {
    primary: "主色", primary_soft: "主色暗面", accent: "强调色",
    surface: "面板底", surface_alt: "次级面板", text: "正文",
    text_dim: "次级文字", border: "边框", danger: "危险色", success: "成功色",
  };
  function uidBuildThemePanel() {
    const box = $("uidPanelTheme");
    if (!box) return;
    box.innerHTML = THEME_FIELDS.map((f) =>
      '<div class="ui-dl row"><span>' + THEME_LABELS[f.key] + "（" + f.key + "）</span>" +
      '<input class="uid-color" id="' + f.id + '" type="color">' +
      '<span class="uid-val" id="' + f.id + 'Val">#000000</span></div>'
    ).join("") +
      '<div class="modal-hint" style="margin-top:6px">「恢复引擎默认」会把配色清空' +
      "（回落到引擎兜底色）；保存后写入项目 config.json 的 theme 段。</div>";
  }
  uidBuildThemePanel();

  // 入口 HTML 行数目标：快捷栏图标 / 字体文件 / 界面开关三块控件由 JS 注入
  function uidBuildExtraPanels() {
    const quick = $("uidPanelQuick");
    if (quick) {
      quick.insertAdjacentHTML("beforeend",
        '<div class="ui-dl row"><span>按钮图标（icons）</span>' +
        '<input id="uidQbIcons" type="text" ' +
        'placeholder="SAVE=ui_save;LOAD=ui_load（图片名，留空=文字）"></div>');
    }
    const global = $("uidPanelGlobal");
    if (global) {
      global.insertAdjacentHTML("beforeend",
        '<div class="ui-dl row"><span>字体文件（font_file）</span>' +
        '<input id="uidFontFile" type="text" ' +
        'placeholder="fonts/我的字体.ttf（留空=自动查找）"></div>');
    }
    const iface = $("uidPanelIface");
    if (iface) {
      iface.innerHTML =
        '<div class="ui-dl row"><span>显示快捷栏（quickbar_enabled）</span>' +
        '<select id="uidIfIfaceQb"><option value="1">显示</option>' +
        '<option value="0">隐藏（快捷键仍可用）</option></select></div>' +
        '<div class="ui-dl row"><span>启用桌宠（pet_enabled）</span>' +
        '<select id="uidIfIfacePet"><option value="1">启用</option>' +
        '<option value="0">关闭</option></select></div>' +
        '<div class="modal-hint" style="margin-top:6px">这两项是玩家默认值，写入项目 settings.json；' +
        '玩家仍可在游戏内「设置 → 界面」改。桌宠只随源码模式生效，打包后的游戏不含桌宠。</div>';
    }
  }
  uidBuildExtraPanels();

  // 每个 tab 的 scene 与面板由 data-scene / data-panel 驱动（见 uidSelectTab）

  function uidGetConfig() {
    const out = {ui: {}, dialogue: {}, font: {}, line_height: {},
                 choices: {}, quickbar: {}, menu: {}, settings: {}, theme: {}};
    for (const f of UID_FIELDS) {
      const el = $(f.id);
      if (!el) continue;
      // select 的 value 是字符串：布尔要转成真正的 true/false，位置/对齐保持字符串
      const v = f.isBool ? (el.value === "true" || el.value === "1")
        : f.isString ? el.value
          : Number(el.value);
      out[f.section][f.key] = v;
    }
    // 配色：null = 清掉覆盖（回落到引擎默认）；否则写 [r,g,b]
    for (const f of THEME_FIELDS) {
      const el = $(f.id);
      out.theme[f.key] = uidThemeCleared.has(f.key)
        ? null
        : hexToRgb(el ? el.value : "#ffffff");
    }
    // 1080p 预设：画布尺寸（顶层 canvas_size，保存后下一帧生效）
    const cv = $("uidCanvas");
    if (cv) {
      const parts = String(cv.value || "1280x720").split("x");
      out.canvas = {size: [parseInt(parts[0], 10) || 1280, parseInt(parts[1], 10) || 720]};
    }
    // 自定义字体（顶层 font_file）+ 快捷栏图标映射（ui.quickbar.icons）
    const ff = $("uidFontFile");
    out.font_file = ff ? String(ff.value || "").trim() : "";
    const ic = $("uidQbIcons");
    out.quickbar.icons = uidParseIcons(ic ? ic.value : "");
    // 界面开关（写项目 settings.json，作为玩家默认值）
    const qbIf = $("uidIfIfaceQb");
    const petIf = $("uidIfIfacePet");
    out.interface = {
      quickbar_enabled: qbIf ? Number(qbIf.value) : 1,
      pet_enabled: petIf ? Number(petIf.value) : 0,
    };
    return out;
  }

  // 图标映射文本 ⇄ {标签: 图片名}：接受 "SAVE=ui_save;LOAD=ui_load"（也支持换行/逗号）
  function uidParseIcons(text) {
    const out = {};
    String(text || "").split(/[;\n,]+/).forEach((part) => {
      const i = part.indexOf("=");
      if (i <= 0) return;
      const k = part.slice(0, i).trim().toUpperCase();
      const v = part.slice(i + 1).trim();
      if (k && v) out[k] = v;
    });
    return out;
  }

  function uidFormatIcons(icons) {
    return Object.keys(icons || {}).map((k) => k + "=" + icons[k]).join(";");
  }

  function uidApplyLoaded(data) {
    // 面板初始值 = 项目 config.json 现值（未写键为引擎默认）
    const truthy = (v) => v === true || v === 1 || v === "true" || v === "1";
    const set = (id, v, isBool, isString) => {
      const el = $(id);
      if (!el) return;
      if (isBool) { el.value = truthy(v) ? "true" : "false"; return; }
      if (isString || el.tagName === "SELECT") { el.value = String(v == null ? "" : v); return; }
      el.value = Number(v);
      const valEl = $(id + "Val");
      if (valEl) valEl.textContent = v;
    };
    for (const f of UID_FIELDS) {
      const sec = data[f.section] || {};
      set(f.id, sec[f.key], f.isBool, f.isString);
    }
    // 画布尺寸（含非预设值时临时加一项，避免下拉显示空白）
    // 配色：GET 一定返回 theme；恢复默认时另走 uidThemeDefaults
    if (data.theme) {
      for (const f of THEME_FIELDS) uidSetThemeColor(f.id, data.theme[f.key]);
    }
    const size = (data.canvas && data.canvas.size) || [1280, 720];
    const cv = $("uidCanvas");
    if (cv) {
      const val = size[0] + "x" + size[1];
      const exists = Array.prototype.some.call(cv.options, (o) => o.value === val);
      if (!exists) {
        const opt = document.createElement("option");
        opt.value = val;
        opt.textContent = size[0] + "×" + size[1] + "（当前）";
        cv.appendChild(opt);
      }
      cv.value = val;
    }
    // 自定义字体与快捷栏图标文本回填（未配置时为空串 = 走引擎默认）
    const ffEl = $("uidFontFile");
    if (ffEl) ffEl.value = String(data.font_file || "");
    const icEl = $("uidQbIcons");
    if (icEl) icEl.value = uidFormatIcons((data.quickbar && data.quickbar.icons) || {});
    // 界面开关：GET 已按引擎默认补齐（快捷栏开 / 桌宠关）
    const iface = data.interface || {};
    const qbIfEl = $("uidIfIfaceQb");
    if (qbIfEl) qbIfEl.value = (iface.quickbar_enabled === 0) ? "0" : "1";
    const petIfEl = $("uidIfIfacePet");
    if (petIfEl) petIfEl.value = (iface.pet_enabled === 1) ? "1" : "0";
  }

  function uidSchedulePreview() {
    clearTimeout(uidTimer);
    uidTimer = setTimeout(uidPreview, 250);
  }

  let lastPreviewUrl = "";   // 保留当前预览 blob，供「放大」复用

  async function uidPreview() {
    const payload = uidGetConfig();
    payload.scene = uidScene;
    $("uidErr").textContent = "";
    try {
      const resp = await fetch("/api/ui-design/preview", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload),
      });
      if (!resp.ok) { throw new Error("HTTP " + resp.status); }
      const blob = await resp.blob();
      if (lastPreviewUrl) { try { URL.revokeObjectURL(lastPreviewUrl); } catch (e) {} }
      const url = URL.createObjectURL(blob);
      lastPreviewUrl = url;
      const img = new Image();
      img.alt = "UI 设计预览";
      img.src = url;
      img.title = "点击放大";
      $("uidPreviewWrap").innerHTML = "";
      $("uidPreviewWrap").appendChild(img);
      const zoomImg = $("uidZoomImg");
      if (zoomImg && $("uidZoomMask") && $("uidZoomMask").style.display !== "none") {
        zoomImg.src = url;   // 放大状态下调参数也能实时更新
      }
    } catch (e) {
      $("uidPreviewWrap").innerHTML = `<div class="preview-placeholder">预览失败：${e}</div>`;
    }
  }

  function openZoom() {
    if (!lastPreviewUrl) return;
    const img = $("uidZoomImg");
    if (img) img.src = lastPreviewUrl;
    const mask = $("uidZoomMask");
    if (mask) mask.style.display = "flex";
  }

  function closeZoom() {
    const mask = $("uidZoomMask");
    if (mask) mask.style.display = "none";
  }

  function uidSelectTab(tabEl) {
    document.querySelectorAll("#uidTabs .uid-tab").forEach(t => t.classList.remove("active"));
    tabEl.classList.add("active");
    const panel = $(tabEl.dataset.panel);
    document.querySelectorAll(".uid-panel").forEach(p => { p.style.display = "none"; });
    if (panel) panel.style.display = "block";
    uidScene = tabEl.dataset.scene;
    uidSchedulePreview();
  }

  async function openUIDesign() {
    $("uidErr").textContent = "";
    $("uidPathHint").textContent = "";
    $("uidPreviewWrap").innerHTML = `<div class="preview-placeholder">加载中…</div>`;
    try {
      const resp = await fetch("/api/ui-design");
      const data = await resp.json();
      if (!data.ok) throw new Error(data.message || "读取失败");
      uidThemeDefaults = data.theme_defaults || {};
      uidThemeCleared = new Set();
      uidApplyLoaded(data);
      $("uiDesignModal").style.display = "flex";
      // 打开时回到对话框分组，预览对话框场景
      const firstTab = document.querySelector("#uidTabs .uid-tab");
      if (firstTab) uidSelectTab(firstTab);
      uidPreview();
    } catch (e) {
      $("uidErr").textContent = "读取 UI 配置失败：" + e;
      $("uiDesignModal").style.display = "flex";
    }
  }

  function closeUIDesign() {
    closeZoom();
    $("uiDesignModal").style.display = "none";
    clearTimeout(uidTimer);
  }

  async function saveUIDesign() {
    $("uidErr").textContent = "";
    try {
      const payload = uidGetConfig();
      const resp = await postJSON("/api/ui-design", payload);
      if (!resp.ok) { $("uidErr").textContent = resp.message || "保存失败"; return; }
      $("uidPathHint").textContent = "已保存：" + (resp.path || "") +
        (resp.settings_path ? "；界面开关 → " + resp.settings_path : "");
      toast("UI 设计已写入项目配置");
    } catch (e) {
      $("uidErr").textContent = "保存请求失败：" + e;
    }
  }

  function uidResetDefaults() {
    // 恢复引擎默认：像素化开 / scale 4 / 圆角 10 / 无偏移 / 全宽 / 高 180 /
    // 名字 12+8 / 选项 420×52 gap40 radius8 / 快捷栏 64×26 gap8 margin24/10 alpha185
    // radius15 bottom/right / 菜单 380×54 top240 radius12 / 设置 620×72 nav180 top210 / 字号 28 / 行距 1.6
    uidApplyLoaded({
      ui: {pixelated: true, pixel_scale: 4, corner_radius: 10},
      dialogue: {radius: 10, offset_x: 0, offset_y: 0, panel_width: 0, height: 180,
                 name_y: 12, name_gap: 8},
      choices: {width: 420, row_height: 52, dialog_gap: 40, radius: 8},
      quickbar: {button_width: 64, button_height: 26, gap: 8, margin_x: 24,
                 margin_y: 10, alpha: 185, radius: 15, position: "bottom", align: "right"},
      menu: {row_width: 380, row_height: 54, top: 240, radius: 12},
      settings: {row_width: 620, row_height: 72, nav_width: 180, top: 210},
      font: {body: 28},
      line_height: {body: 1.6},
      canvas: {size: [1280, 720]},
      interface: {quickbar_enabled: 1, pet_enabled: 0},
    });
    // 配色恢复引擎兜底色，并标记「保存时清空 theme 覆盖」
    if (Object.keys(uidThemeDefaults).length) {
      for (const f of THEME_FIELDS) uidSetThemeColor(f.id, uidThemeDefaults[f.key]);
    }
    uidThemeCleared = new Set(THEME_FIELDS.map((f) => f.key));
    uidSchedulePreview();
  }

  $("btnUIDesign").addEventListener("click", openUIDesign);
  $("uidClose").addEventListener("click", closeUIDesign);
  $("uidSave").addEventListener("click", saveUIDesign);
  $("uidReset").addEventListener("click", uidResetDefaults);
  const uidCanvasEl = $("uidCanvas");
  if (uidCanvasEl) uidCanvasEl.addEventListener("change", uidSchedulePreview);
  ["uidFontFile", "uidQbIcons", "uidIfIfaceQb", "uidIfIfacePet"].forEach((id) => {
    const el = $(id);
    if (el) el.addEventListener("change", uidSchedulePreview);
  });
  // 预览放大：点「放大」按钮或缩略图打开；点遮罩 / Esc 关闭
  const uidZoomBtn = $("uidZoom");
  if (uidZoomBtn) uidZoomBtn.addEventListener("click", openZoom);
  const uidZoomMask = $("uidZoomMask");
  if (uidZoomMask) uidZoomMask.addEventListener("click", closeZoom);
  const uidPreviewWrapEl = $("uidPreviewWrap");
  if (uidPreviewWrapEl) {
    uidPreviewWrapEl.addEventListener("click", (e) => {
      if (e.target && e.target.tagName === "IMG") openZoom();
    });
  }
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && uidZoomMask && uidZoomMask.style.display !== "none") {
      closeZoom();
      e.stopPropagation();
    }
  }, true);
  document.querySelectorAll("#uidTabs .uid-tab").forEach(tab => {
    tab.addEventListener("click", () => uidSelectTab(tab));
  });
  for (const f of UID_FIELDS) {
    const el = $(f.id);
    if (!el) continue;
    el.addEventListener("input", () => {
      const valEl = $(f.id + "Val");
      if (valEl && !f.isBool) valEl.textContent = el.value;
      uidSchedulePreview();
    });
    el.addEventListener("change", () => {
      if (f.isBool) uidSchedulePreview();
    });
  }
  // 配色色块：改色即预览；改过的键不再被「恢复默认」清空
  for (const f of THEME_FIELDS) {
    const el = $(f.id);
    if (!el) continue;
    el.addEventListener("input", () => {
      const valEl = $(f.id + "Val");
      if (valEl) valEl.textContent = String(el.value || "").toUpperCase();
      uidThemeCleared.delete(f.key);
      uidSchedulePreview();
    });
  }
})();
