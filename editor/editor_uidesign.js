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
    // P53 对话框皮肤（贴图九宫格 / 渐变蒙版 / 纹理 / 内边距）
    {id: "uidPanelFade", key: "panel_fade", section: "dialogue"},
    {id: "uidFadeBottom", key: "panel_fade_bottom", section: "dialogue"},
    {id: "uidPanelAlpha", key: "panel_alpha", section: "dialogue"},
    {id: "uidTexAlpha", key: "panel_texture_alpha", section: "dialogue"},
    {id: "uidPadX", key: "pad_x", section: "dialogue"},
    {id: "uidPadY", key: "pad_y", section: "dialogue"},
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

  // P53：皮肤控件——九宫格四边合成 panel_slice 数组，贴图/纹理是字符串键
  const UID_SKIN_SLICE_IDS = ["uidSliceL", "uidSliceT", "uidSliceR", "uidSliceB"];
  const UID_SKIN_STR_IDS = {"uidPanelImage": "panel_image", "uidPanelTexture": "panel_texture"};
  function uidNum(id) { const el = $(id); return el ? Number(el.value) || 0 : 0; }
  function uidSetRange(id, v) {
    const el = $(id);
    if (!el) return;
    el.value = String(v == null ? 0 : v);
    const valEl = $(id + "Val");
    if (valEl) valEl.textContent = el.value;
  }

  function rgbToHex(v) {    const arr = Array.isArray(v) && v.length >= 3 ? v : [255, 255, 255];
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
    // P53：皮肤——九宫格四边合成 [左,上,右,下]，贴图/纹理名去空白
    out.dialogue.panel_slice = UID_SKIN_SLICE_IDS.map((id) => uidNum(id));
    for (const [id, key] of Object.entries(UID_SKIN_STR_IDS)) {
      const el = $(id);
      out.dialogue[key] = el ? String(el.value || "").trim() : "";
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
    // P53：九宫格四边（单值 → 四边同宽；数组 → 逐边回填）
    const slice = (data.dialogue && data.dialogue.panel_slice != null)
      ? data.dialogue.panel_slice : 0;
    const sliceArr = Array.isArray(slice) ? slice : [slice, slice, slice, slice];
    UID_SKIN_SLICE_IDS.forEach((id, i) => uidSetRange(id, Number(sliceArr[i]) || 0));
    for (const [id, key] of Object.entries(UID_SKIN_STR_IDS)) {
      const el = $(id);
      if (el) el.value = String((data.dialogue && data.dialogue[key]) || "");
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

  // ===== P53：画布拖拽（预览图即画布，拖对话框改位置/高度，不用填数字） =====
  function uidCanvasSize() {
    const raw = ($("uidCanvas") && $("uidCanvas").value) || "1280x720";
    const parts = String(raw).split("x");
    return [parseInt(parts[0], 10) || 1280, parseInt(parts[1], 10) || 720];
  }

  function uidPanelRect() {
    const [cw, ch] = uidCanvasSize();
    const height = Math.max(40, uidNum("uidHeight"));
    const offX = uidNum("uidOffsetX");
    const offY = uidNum("uidOffsetY");
    const pw = uidNum("uidPanelWidth");
    const w = pw > 0 ? Math.min(pw, cw) : cw - 36;
    const left = pw > 0 ? (cw - w) / 2 + offX : 18 + offX;
    return {left, top: ch - height + offY, w, h: Math.max(1, height - 8), cw, ch};
  }

  function uidPositionStage() {
    const body = $("uidDragBody");
    const edge = $("uidDragTop");
    const vedge = $("uidDragLeft");
    const sel = $("uidSel");
    if (!body || !edge) return;
    if (uidScene !== "dialog") {
      body.style.display = "none";
      edge.style.display = "none";
      if (vedge) vedge.style.display = "none";
      if (sel) sel.classList.remove("on");
      return;
    }
    body.style.display = "";
    edge.style.display = "";
    const r = uidPanelRect();
    const px = (v, base) => (v / base) * 100 + "%";
    body.style.left = px(r.left, r.cw);
    body.style.top = px(r.top, r.ch);
    body.style.width = px(r.w, r.cw);
    body.style.height = px(r.h, r.ch);
    edge.style.left = px(r.left, r.cw);
    edge.style.width = px(r.w, r.cw);
    edge.style.top = px(r.top, r.ch);
    if (vedge) {
      vedge.style.display = "";
      vedge.style.left = px(r.left, r.cw);
      vedge.style.top = px(r.top, r.ch);
      vedge.style.height = px(r.h, r.ch);
    }
    if (sel) {
      // P57：选择框按屏幕 px 定位（百分比在 flex/图片未加载时会算歪，命中判区跟着一起歪）
      const box = $("uidStage").getBoundingClientRect();
      if (!box.width || !box.height) { sel.classList.remove("on"); return; }
      const sx = box.width / r.cw;
      const sy = box.height / r.ch;
      sel.classList.add("on");
      sel.style.left = (r.left * sx) + "px";
      sel.style.top = (r.top * sy) + "px";
      sel.style.width = (r.w * sx) + "px";
      sel.style.height = (r.h * sy) + "px";
    }
  }

  let uidDrag = null;

  function uidDragStart(mode, e) {
    const stage = $("uidStage");
    if (!stage || uidScene !== "dialog") return;
    const box = stage.getBoundingClientRect();
    if (!box.height || !box.width) return;
    e.preventDefault();
    const [cw, ch] = uidCanvasSize();
    uidDrag = {
      mode, x: e.clientX, y: e.clientY, off0: uidNum("uidOffsetY"),
      offX0: uidNum("uidOffsetX"), h0: uidNum("uidHeight"),
      w0: uidPanelRect().w,
      r0: uidNum("uidRadius"),
      stageH: box.height, stageW: box.width, ch, cw,
    };
    document.body.style.userSelect = "none";
  }

  function uidDragMove(e) {
    if (!uidDrag) return;
    const dy = ((e.clientY - uidDrag.y) / uidDrag.stageH) * uidDrag.ch;
    const dx = ((e.clientX - uidDrag.x) / uidDrag.stageW) * uidDrag.cw;
    if (uidDrag.mode === "move") {
      // 拖本体：纵向改 offset_y、横向改 offset_x（都是 2px 步长，夹 ±160）
      const vy = Math.max(-160, Math.min(160, uidDrag.off0 + dy));
      const vx = Math.max(-160, Math.min(160, uidDrag.offX0 + dx));
      uidSetRange("uidOffsetY", Math.round(vy / 2) * 2);
      uidSetRange("uidOffsetX", Math.round(vx / 2) * 2);
    } else if (uidDrag.mode === "width") {
      // 拖左边缘：改面板宽度（原本贴边全宽时，从这里开始收窄）
      const v = Math.max(240, Math.min(uidDrag.cw, uidDrag.w0 - dx * 2));
      uidSetRange("uidPanelWidth", Math.round(v / 4) * 4);
    } else if (uidDrag.mode === "e" || uidDrag.mode === "w") {
      // P57：拖左右手柄——改宽度，同时反着挪 offset_x，让另一条边钉住不动
      const dir = uidDrag.mode === "e" ? 1 : -1;
      const v = Math.max(240, Math.min(uidDrag.cw, uidDrag.w0 + dir * dx));
      uidSetRange("uidPanelWidth", Math.round(v / 4) * 4);
      const off = uidDrag.offX0 + (v - uidDrag.w0) / 2;
      uidSetRange("uidOffsetX", Math.round(off / 2) * 2);
    } else if (uidDrag.mode === "ne" || uidDrag.mode === "se" ||
               uidDrag.mode === "nw" || uidDrag.mode === "sw") {
      // 拖四个角：横向当左右手柄（改宽 + 钉住对边），纵向当上下手柄（改高）
      const east = uidDrag.mode === "ne" || uidDrag.mode === "se";
      const north = uidDrag.mode === "nw" || uidDrag.mode === "ne";
      const wv = Math.max(240, Math.min(uidDrag.cw, uidDrag.w0 + (east ? 1 : -1) * dx));
      uidSetRange("uidPanelWidth", Math.round(wv / 4) * 4);
      uidSetRange("uidOffsetX", Math.round((uidDrag.offX0 + (wv - uidDrag.w0) / 2) / 2) * 2);
      if (north) {
        const hv = Math.max(60, Math.min(400, uidDrag.h0 - dy));
        uidSetRange("uidHeight", Math.round(hv / 4) * 4);
      } else {
        const hv = Math.max(60, Math.min(400, uidDrag.h0 + dy));
        uidSetRange("uidHeight", Math.round(hv / 4) * 4);
        uidSetRange("uidOffsetY", Math.round((uidDrag.off0 + (hv - uidDrag.h0)) / 2) * 2);
      }
    } else if (uidDrag.mode === "n") {
      // 拖上边缘：底边钉住，改高度
      const v = Math.max(60, Math.min(400, uidDrag.h0 - dy));
      uidSetRange("uidHeight", Math.round(v / 4) * 4);
    } else if (uidDrag.mode === "s") {
      // 拖下边缘：顶边钉住（offset_y 跟着走），改高度
      const v = Math.max(60, Math.min(400, uidDrag.h0 + dy));
      uidSetRange("uidHeight", Math.round(v / 4) * 4);
      uidSetRange("uidOffsetY", Math.round((uidDrag.off0 + (v - uidDrag.h0)) / 2) * 2);
    } else if (uidDrag.mode === "radius") {
      // P57：拖绿点改圆角——往右下拖变大，范围 0~40（和滑杆同一上限）
      const d = (dx + dy) / 2;
      const v = Math.max(0, Math.min(40, uidDrag.r0 + d * 0.35));
      uidSetRange("uidRadius", Math.round(v));
    } else {
      const v = Math.max(100, Math.min(400, uidDrag.h0 - dy));
      uidSetRange("uidHeight", Math.round(v / 4) * 4);
    }
    uidPositionStage();
    uidSchedulePreview();
  }

  function uidDragEnd() {
    if (!uidDrag) return;
    uidDrag = null;
    document.body.style.userSelect = "";
    for (const id of ["uidDragBody", "uidDragTop", "uidDragLeft"]) {
      const el = $(id);
      if (el) el.classList.remove("dragging");
    }
  }

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
      const img = $("uidStageImg");
      if (img) {
        img.alt = "UI 设计预览";
        img.title = "点击放大";
        // 图换了尺寸就变，选择框/拖拽层必须跟着重新定位（否则会停在上一帧的位置）
        img.onload = function () { uidPositionStage(); };
        img.src = url;
      }
      const stage = $("uidStage");
      if (stage) stage.classList.add("on");
      const hint = $("uidPreviewHint");
      if (hint) hint.style.display = "none";
      const zoomImg = $("uidZoomImg");
      if (zoomImg && $("uidZoomMask") && $("uidZoomMask").style.display !== "none") {
        zoomImg.src = url;   // 放大状态下调参数也能实时更新
      }
      uidPositionStage();
    } catch (e) {
      const stage = $("uidStage");
      if (stage) stage.classList.remove("on");
      const hint = $("uidPreviewHint");
      if (hint) { hint.style.display = ""; hint.textContent = "预览失败：" + e; }
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
    uidPositionStage();
    uidSchedulePreview();
  }

  async function openUIDesign() {
    $("uidErr").textContent = "";
    $("uidPathHint").textContent = "";
    const hint = $("uidPreviewHint");
    if (hint) { hint.style.display = ""; hint.textContent = "加载中…"; }
    try {
      const resp = await fetch("/api/ui-design");
      const data = await resp.json();
      if (!data.ok) throw new Error(data.message || "读取失败");
      uidThemeDefaults = data.theme_defaults || {};
      uidThemeCleared = new Set();
      uidApplyLoaded(data);
      $("uiDesignModal").style.display = "flex";
      uidLoadImageNames();
      // 打开时回到对话框分组，预览对话框场景
      const firstTab = document.querySelector("#uidTabs .uid-tab");
      if (firstTab) uidSelectTab(firstTab);
      uidPreview();
    } catch (e) {
      $("uidErr").textContent = "读取 UI 配置失败：" + e;
      $("uiDesignModal").style.display = "flex";
    }
  }

  // P53：贴图/纹理候选来自项目素材库（只列文件名）
  async function uidLoadImageNames() {
    const list = $("uidImageList");
    if (!list) return;
    try {
      const resp = await fetch("/api/assets");
      const data = await resp.json();
      const names = ((data.assets || {}).images) || [];
      list.innerHTML = names.map((n) =>
        '<option value="' + String(n) + '"></option>').join("");
    } catch (e) { /* 素材库读不到不影响设计面板 */ }
  }

  // P53：预设库——一键套一组参数，不用一个个拖滑杆
  const UID_PRESETS = [
    {name: "极简无框", dlg: {radius: 0, height: 170, panel_width: 0, offset_x: 0,
      offset_y: 0, panel_image: "", panel_slice: [0, 0, 0, 0], panel_fade: 50,
      panel_fade_bottom: 0, panel_alpha: 150, panel_texture: "",
      panel_texture_alpha: 0, pad_x: 8, pad_y: 0}},
    {name: "玻璃卡片", dlg: {radius: 18, height: 200, panel_width: 1080, offset_x: 0,
      offset_y: -20, panel_image: "", panel_slice: [0, 0, 0, 0], panel_fade: 0,
      panel_alpha: 215, pad_x: 14, pad_y: 6}},
    {name: "贴图九宫格", dlg: {panel_image: "textbox", panel_slice: [28, 12, 28, 12],
      panel_fade: 0, panel_fade_bottom: 0, panel_alpha: 255, panel_texture_alpha: 0,
      pad_x: 10, pad_y: 4}},
    {name: "纸张纹理", dlg: {radius: 12, height: 190, panel_width: 0, panel_texture: "paper",
      panel_texture_alpha: 90, panel_alpha: 230, panel_fade: 0, pad_x: 10, pad_y: 4}},
    {name: "电影字幕", dlg: {radius: 0, height: 150, panel_width: 0, offset_y: 0,
      panel_image: "", panel_fade: 70, panel_fade_bottom: 0, panel_alpha: 170,
      panel_texture_alpha: 0, pad_x: 0, pad_y: 0}},
  ];

  // P53：皮肤分页控件与预览画布结构由 JS 注入（入口 HTML 保持精简，行数门禁不变）
  function uidBuildSkinControls() {
    const box = $("uidPanelSkin");
    if (!box) return;
    const range = (id, key, max, label) =>
      '<div class="ui-dl row"><span>' + label + "（" + key + '）</span>' +
      '<input id="' + id + '" type="range" min="0" max="' + max + '" step="' +
      (max > 200 ? "1" : "2") + '"><span class="uid-val" id="' + id + 'Val">0</span></div>';
    box.innerHTML =
      '<div class="modal-hint" style="margin-top:0">别人的做法是「一张固定尺寸 PNG 整张替换」；' +
      "这里是「一张 PNG 按九宫格自适应」——四角不拉伸、边与中段拉伸，分辨率或面板尺寸一变也不变形。" +
      "渐变与纹理在引擎里叠加，不用回 PS 重做图。</div>" +
      '<div class="uid-presets" id="uidSkinPresets"></div>' +
      '<div class="ui-dl row"><span>贴图（panel_image）</span>' +
      '<input id="uidPanelImage" type="text" list="uidImageList" ' +
      'placeholder="textbox（留空 = 引擎绘制）">' +
      '<datalist id="uidImageList"></datalist></div>' +
      range("uidSliceL", "slice 左", 200, "九宫格 左") +
      range("uidSliceT", "slice 上", 200, "九宫格 上") +
      range("uidSliceR", "slice 右", 200, "九宫格 右") +
      range("uidSliceB", "slice 下", 200, "九宫格 下") +
      range("uidPanelFade", "panel_fade", 120, "顶部渐变羽化") +
      range("uidFadeBottom", "panel_fade_bottom", 120, "底部渐变羽化") +
      range("uidPanelAlpha", "panel_alpha", 255, "面板不透明度") +
      '<div class="ui-dl row"><span>纹理（panel_texture）</span>' +
      '<input id="uidPanelTexture" type="text" list="uidImageList" ' +
      'placeholder="paper（留空 = 不叠）"></div>' +
      range("uidTexAlpha", "panel_texture_alpha", 255, "纹理强度") +
      range("uidPadX", "pad_x", 140, "左右内边距") +
      range("uidPadY", "pad_y", 80, "内部上边距");
  }

  // P54/P56：手机版与可迁移包都放在弹窗底部（不是皮肤页签里）——切页签也不影响，作者不会找不到
  function uidBuildWebExport() {
    const hint = $("uidPathHint");
    if (!hint || $("uidExportWeb")) return;
    hint.insertAdjacentHTML("afterend",
      '<div class="uid-web"><div class="modal-hint" style="margin-top:0">手机端：把当前工程编成静态网页包，' +
      "竖屏横屏都能跑（转屏自动重排），整包可上传 itch.io 或任意静态托管。可迁移包：导成 Ren'Py 工程或通用 " +
      'JSON，随时能带走、换引擎。</div>' +
      '<div class="ui-dl row"><span>手机版（H5）</span>' +
      '<button type="button" class="btn" id="uidExportWeb">导出手机版</button>' +
      '<span class="uid-val" id="uidExportWebMsg"></span></div>' +
      '<div class="ui-dl row"><span>可迁移包</span>' +
      '<button type="button" class="btn" id="uidExportPortable">导出 Ren' +
      "'Py + JSON</button>" +
      '<span class="uid-val" id="uidExportPortableMsg"></span></div></div>');
    const btn = $("uidExportWeb");
    if (btn) btn.addEventListener("click", uidExportWeb);
    const btn2 = $("uidExportPortable");
    if (btn2) btn2.addEventListener("click", uidExportPortable);
  }
  uidBuildWebExport();

  // P56：导出可迁移包（Ren'Py 工程 + 通用 JSON）——产物落在 <发行根>/dist/portable/<工程名>，
  // 每种引擎一个 zip，点链接直接下载
  async function uidExportPortable() {
    const btn = $("uidExportPortable");
    const msg = $("uidExportPortableMsg");
    if (!btn || !msg) return;
    btn.disabled = true;
    msg.textContent = "导出中…";
    try {
      const resp = await postJSON("/api/export-portable", {engine: "both"});
      if (!resp.ok) { msg.textContent = resp.message || "导出失败"; return; }
      msg.innerHTML = "";
      (resp.items || []).forEach((it, i) => {
        if (i) msg.appendChild(document.createTextNode("　"));
        const a = document.createElement("a");
        a.href = new URL(it.url, window.location.href).href;
        a.textContent = it.engine === "renpy" ? "下载 Ren'Py 工程" : "下载通用 JSON";
        msg.appendChild(a);
        msg.appendChild(document.createTextNode(
          "（" + (it.instructions || 0) + " 条指令 / " + (it.images || 0) + " 张素材 / " + (it.zip_mb || 0) + " MB）"));
      });
      toast("已导出可迁移包（Ren'Py + JSON）");
    } catch (e) {
      msg.textContent = "导出请求失败：" + e;
    } finally {
      btn.disabled = false;
    }
  }

  // P54：导出手机版（竖屏 / 横屏都能跑）——产物落在 <发行根>/web/<工程名>，
  // 后端同时把目录挂到 /web-preview/ 上，点一下就能在浏览器里真跑一遍
  async function uidExportWeb() {
    const btn = $("uidExportWeb");
    const msg = $("uidExportWebMsg");
    if (!btn || !msg) return;
    btn.disabled = true;
    msg.textContent = "编译中…";
    try {
      const resp = await postJSON("/api/export-web", {});
      if (!resp.ok) { msg.textContent = resp.message || "导出失败"; return; }
      const url = new URL(resp.url, window.location.href).href;
      msg.innerHTML = "";
      const a = document.createElement("a");
      a.href = url;
      a.target = "_blank";
      a.rel = "noopener";
      a.textContent = "打开手机版预览";
      msg.appendChild(a);
      msg.appendChild(document.createTextNode(
        "（" + (resp.instructions || 0) + " 条指令 / " + (resp.images || 0) + " 张素材）"));
      const notes = [];
      if (resp.missing && resp.missing.length) notes.push("缺素材：" + resp.missing.join("、"));
      if (resp.unsupported && resp.unsupported.length) {
        notes.push("桌面有、手机端暂不支持：" + resp.unsupported.join("、"));
      }
      if (notes.length) msg.appendChild(document.createTextNode("　" + notes.join("；")));
      toast("已导出手机版（竖屏 / 横屏都能跑）");
    } catch (e) {
      msg.textContent = "导出请求失败：" + e;
    } finally {
      btn.disabled = false;
    }
  }

  function uidBuildStage() {
    const wrap = $("uidPreviewWrap");
    if (!wrap || $("uidStage")) return;
    wrap.insertAdjacentHTML("afterbegin",
      '<div class="uid-stage" id="uidStage">' +
      '<img id="uidStageImg" alt="UI 设计预览" title="点击放大">' +
      '<div class="uid-drag-body" id="uidDragBody" title="拖动：上下移动对话框"></div>' +
      '<div class="uid-drag-edge" id="uidDragTop" title="拖上边缘：改对话框高度"></div>' +
      '<div class="uid-drag-edge-v" id="uidDragLeft" title="拖左边缘：改面板宽度"></div>' +
      "</div>");
    uidBuildSel();
  }

  // ===== P57：PPT / 虚幻式可视化操控（选中框 + 八个手柄 + 角上的圆角手柄） =====
  // 之前只有三块拖拽热区，改圆角还得低头填数字。这里给面板加一套选择框：
  // 拖本体=移动，拖四边=改宽高，拖左上角的小圆点=改圆角——手上看到的就是画布上那块面板。
  function uidBuildSel() {
    const stage = $("uidStage");
    if (!stage || $("uidSel")) return;
    stage.insertAdjacentHTML("beforeend",
      '<div class="uid-sel" id="uidSel">' +
      ["nw", "n", "ne", "e", "se", "s", "sw", "w"].map(function (h) {
        return '<span class="uid-sel-h" data-h="' + h + '"></span>';
      }).join("") +
      '<span class="uid-sel-r" id="uidRadiusGrip" title="拖我改圆角"></span>' +
      '<span class="uid-sel-tag">对话框面板 · 拖角改圆角</span>' +
      "</div>");
  }

  function uidStyleCanvas() {
    if ($("uidSelStyle")) return;
    const css = [
      ".uid-sel{position:absolute;pointer-events:none;box-sizing:border-box;",
      "border:1px dashed #4f8cff;border-radius:2px;z-index:3;display:none}",
      ".uid-sel.on{display:block}",
      // 手柄必须整块落在框内：预览区 overflow:hidden，压在框外的那半会被裁掉，
      // 结果「看得见但点不到」——所以用负 margin 把 12px 手柄往里收，而不是往外悬。
      ".uid-sel-h{position:absolute;width:12px;height:12px;background:#4f8cff;",
      "border:1px solid #e6eeff;border-radius:2px;pointer-events:auto}",
      '.uid-sel-h[data-h="nw"]{left:0;top:0}',
      '.uid-sel-h[data-h="n"]{left:50%;top:0;margin-left:-6px}',
      '.uid-sel-h[data-h="ne"]{right:0;top:0}',
      '.uid-sel-h[data-h="e"]{right:0;top:50%;margin-top:-6px;cursor:ew-resize}',
      '.uid-sel-h[data-h="se"]{right:0;bottom:0}',
      '.uid-sel-h[data-h="s"]{left:50%;bottom:0;margin-left:-6px}',
      '.uid-sel-h[data-h="sw"]{left:0;bottom:0}',
      '.uid-sel-h[data-h="w"]{left:0;top:50%;margin-top:-6px;cursor:ew-resize}',
      ".uid-sel-r{position:absolute;left:34px;top:34px;width:13px;height:13px;",
      "margin:-6px 0 0 -6px;border-radius:50%;background:#7ee787;",
      "border:1px solid #0b0d12;pointer-events:auto;cursor:move;z-index:4}",
      ".uid-sel-tag{position:absolute;right:0;top:-18px;font-size:11px;line-height:16px;",
      "padding:0 6px;color:#cfe0ff;background:rgba(11,13,18,.75);border-radius:3px;white-space:nowrap}",
    ].join("");
    const st = document.createElement("style");
    st.id = "uidSelStyle";
    st.textContent = css;
    document.head.appendChild(st);
  }
  uidStyleCanvas();
  uidBuildSkinControls();
  uidBuildStage();

  function uidIdForKey(key) {
    for (const f of UID_FIELDS) {
      if (f.key === key) return f.id;
    }
    for (const [id, k] of Object.entries(UID_SKIN_STR_IDS)) {
      if (k === key) return id;
    }
    return "";
  }

  function uidApplyPreset(preset) {
    for (const [key, val] of Object.entries((preset && preset.dlg) || {})) {
      if (key === "panel_slice") {
        const arr = Array.isArray(val) ? val : [val, val, val, val];
        UID_SKIN_SLICE_IDS.forEach((id, i) => uidSetRange(id, Number(arr[i]) || 0));
        continue;
      }
      const id = uidIdForKey(key);
      const el = id ? $(id) : null;
      if (!el) continue;
      if (el.tagName === "SELECT") el.value = String(val);
      else if (el.type === "range") uidSetRange(id, val);
      else el.value = String(val);
    }
    uidPositionStage();
    uidSchedulePreview();
    toast("已套用预设：" + (preset ? preset.name : ""));
  }

  function uidBuildSkinPanel() {
    const box = $("uidSkinPresets");
    if (!box) return;
    box.innerHTML = UID_PRESETS.map((p, i) =>
      '<button type="button" class="uid-preset" data-preset="' + i + '">' + p.name +
      "</button>").join("");
    box.addEventListener("click", (e) => {
      const t = e.target.closest(".uid-preset");
      if (!t) return;
      box.querySelectorAll(".uid-preset").forEach((b) => b.classList.remove("active"));
      t.classList.add("active");
      uidApplyPreset(UID_PRESETS[Number(t.dataset.preset)] || UID_PRESETS[0]);
    });
  }
  uidBuildSkinPanel();

  // P53：导出成品面板 PNG（写进项目 images/，可直接当 panel_image 回填，
  // 也能拿去给其它引擎/工具用——产出的是资产，不是配置）
  async function uidExportTextbox() {
    $("uidErr").textContent = "";
    try {
      const payload = uidGetConfig();
      const raw = String((payload.dialogue && payload.dialogue.panel_image) || "").trim();
      payload.name = (raw || "textbox_export").replace(/[^\w-]/g, "_");
      const resp = await postJSON("/api/ui-design/export-textbox", payload);
      if (!resp.ok && resp.exists) {
        // 同名图已存在：先问人，再带 overwrite 重发（不静默覆盖已有素材）
        if (!window.confirm((resp.message || "同名图已存在") + "\n覆盖会替换 images 里那张图。"))
          return;
        payload.overwrite = true;
        const again = await postJSON("/api/ui-design/export-textbox", payload);
        if (!again.ok) { $("uidErr").textContent = again.message || "导出失败"; return; }
        $("uidPathHint").textContent = "已覆盖：" + (again.path || "");
        toast("已覆盖成品面板 PNG");
        return;
      }
      if (!resp.ok) {
        $("uidErr").textContent = resp.message || "导出失败";
        return;
      }
      $("uidPathHint").textContent = "已导出：" + (resp.path || "") +
        "（可直接当 panel_image，也给别的引擎用）";
      toast("已导出成品面板 PNG");
    } catch (e) {
      $("uidErr").textContent = "导出请求失败：" + e;
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
                 name_y: 12, name_gap: 8,
                 // P53：皮肤回到「无贴图」——引擎绘制的圆角面板，旧行为
                 panel_image: "", panel_slice: 0, panel_tint: null,
                 panel_fade: 0, panel_fade_bottom: 0, panel_texture: "",
                 panel_texture_alpha: 0, panel_alpha: 255, pad_x: 0, pad_y: 0},
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

  // ===== P53：皮肤控件接线（九宫格四边 / 贴图名 / 纹理名 / 导出按钮） =====
  UID_SKIN_SLICE_IDS.concat(Object.keys(UID_SKIN_STR_IDS)).forEach((id) => {
    const el = $(id);
    if (!el) return;
    const onChange = () => {
      const valEl = $(id + "Val");
      if (valEl) valEl.textContent = el.value;
      uidSchedulePreview();
    };
    el.addEventListener("input", onChange);
    el.addEventListener("change", onChange);
  });
  const uidExportBtn = $("uidExport");
  if (uidExportBtn) uidExportBtn.addEventListener("click", uidExportTextbox);

  // 画布拖拽：拖本体 = 上下左右移动；拖上边缘 = 改高度；拖左边缘 = 改宽度
  const uidDragBodyEl = $("uidDragBody");
  const uidDragTopEl = $("uidDragTop");
  const uidDragLeftEl = $("uidDragLeft");
  if (uidDragBodyEl) {
    uidDragBodyEl.addEventListener("mousedown", (e) => {
      uidDragBodyEl.classList.add("dragging");
      uidDragStart("move", e);
    });
    uidDragBodyEl.addEventListener("click", (e) => e.stopPropagation());
  }
  if (uidDragTopEl) {
    uidDragTopEl.addEventListener("mousedown", (e) => {
      uidDragTopEl.classList.add("dragging");
      uidDragStart("resize", e);
    });
  }
  if (uidDragLeftEl) {
    uidDragLeftEl.addEventListener("mousedown", (e) => {
      uidDragLeftEl.classList.add("dragging");
      uidDragStart("width", e);
    });
  }
  document.addEventListener("mousemove", uidDragMove);
  document.addEventListener("mouseup", uidDragEnd);

  // P57：八个手柄 + 圆角绿点接线（手柄各自带 data-h，拖哪个改哪个）
  const uidSelEl = $("uidSel");
  if (uidSelEl) {
    uidSelEl.querySelectorAll(".uid-sel-h").forEach((h) => {
      h.addEventListener("mousedown", (e) => {
        e.stopPropagation();
        uidDragStart(h.dataset.h || "move", e);
      });
    });
    const grip = $("uidRadiusGrip");
    if (grip) {
      grip.addEventListener("mousedown", (e) => {
        e.stopPropagation();
        uidDragStart("radius", e);
      });
    }
    // 选择框本身不吃点击，避免挡住「点图放大」
    uidSelEl.addEventListener("click", (e) => e.stopPropagation());
  }

  // P57：按坐标判命中（PPT 那样：不要求精准戳到 12px 小方块，边/角附近 12px 都算）
  // 只靠 DOM 手柄会「看着能拖、点不到」——预览区 overflow 裁剪 + 层叠顺序都可能吃掉点击。
  const uidStageEl = $("uidStage");
  const uidStageImgEl = $("uidStageImg");
  let uidJustDragged = false;
  if (uidStageEl && uidStageImgEl) {
    // 用 document 捕获 + 纯坐标判命中：不挑 target、也不要求精准戳手柄，
    // 落点落在面板里就接管，落在外面就放行（留给点图放大）。
    document.addEventListener("mousedown", (e) => {
      if (uidScene !== "dialog") return;
      const img = $("uidStageImg");
      if (!img) return;
      const box = img.getBoundingClientRect();
      if (!box.width || !box.height) return;
      if (e.clientX < box.left || e.clientX > box.right ||
          e.clientY < box.top || e.clientY > box.bottom) return;
      const r = uidPanelRect();
      const sx = box.width / r.cw;      // 画布 → 屏幕 px
      const sy = box.height / r.ch;
      const lx = e.clientX - box.left;
      const ly = e.clientY - box.top;
      const L = r.left * sx, R = (r.left + r.w) * sx;
      const T = r.top * sy, B = (r.top + r.h) * sy;
      const hit = 14;                    // 命中带宽（屏幕 px）
      if (lx < L - hit || lx > R + hit || ly < T - hit || ly > B + hit) return;  // 面板外：不管
      const nearL = Math.abs(lx - L) <= hit;
      const nearR = Math.abs(lx - R) <= hit;
      const nearT = Math.abs(ly - T) <= hit;
      const nearB = Math.abs(ly - B) <= hit;
      const gripX = L + 34, gripY = T + 34;   // 绿点就在左上角内侧 34px
      let mode = "move";
      if (Math.hypot(lx - gripX, ly - gripY) <= 13) mode = "radius";
      else if (nearT && nearL) mode = "nw";
      else if (nearT && nearR) mode = "ne";
      else if (nearB && nearL) mode = "sw";
      else if (nearB && nearR) mode = "se";
      else if (nearL) mode = "w";
      else if (nearR) mode = "e";
      else if (nearT) mode = "n";
      else if (nearB) mode = "s";
      e.preventDefault();
      e.stopPropagation();
      uidJustDragged = true;
      uidDragStart(mode, e);
    }, true);
    // 拖完松手会跟一个 click，别让它触发「点图放大」
    document.addEventListener("click", (e) => {
      if (uidJustDragged) { uidJustDragged = false; e.stopPropagation(); }
    }, true);
  }
})();
