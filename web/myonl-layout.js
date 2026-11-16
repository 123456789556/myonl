/* 布局计算（纯函数，node 可测）：同一份设计竖屏/横屏都能用。
 *
 * 逻辑画布不写死分辨率，而是跟着窗口比例走：
 *   - 竖屏（h > w）：画布又高又窄，背景 cover 裁切，面板贴底
 *   - 横屏（w > h）：画布又宽又矮，面板贴底、更矮更宽
 *   - 只夹极端比例，普通手机/平板都是满屏（不留黑边）
 * 字号按"短边"算，所以横竖屏看到字一样大，不会转屏后变成蚂蚁或巨字。
 */
(function (root) {
  "use strict";

  const ASPECT_MIN = 0.42;      // 比 iPhone 竖屏（0.46）还窄一点，极端窗口才夹
  const ASPECT_MAX = 2.2;       // 比手机横屏（2.16）略宽

  function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }

  /* cssW/cssH = 窗口 CSS 像素；返回逻辑画布与所有排布尺寸。 */
  function layoutFor(cssW, cssH) {
    const w = Math.max(1, Math.round(cssW || 1));
    const h = Math.max(1, Math.round(cssH || 1));
    const aspect = clamp(w / h, ASPECT_MIN, ASPECT_MAX);
    const landscape = aspect > 1.02;

    // 短边统一 1080，长边按真实比例（竖屏 1080×2338、横屏 2333×1080）
    const shortSide = 1080;
    const viewW = Math.round(shortSide * (aspect >= 1 ? aspect : 1));
    const viewH = Math.round(shortSide * (aspect >= 1 ? 1 : 1 / aspect));

    const unit = Math.min(viewW, viewH);          // 字号/间距的基准
    const fs = Math.round(clamp(unit / 26, 28, 64));
    const lineH = Math.round(fs * 1.65);
    const nameSize = Math.round(fs * 1.18);

    const marginX = Math.round(viewW * (landscape ? 0.045 : 0.035));
    const panelH = Math.round(clamp(viewH * (landscape ? 0.34 : 0.30),
                                    lineH * 3 + 60, viewH * 0.5));
    const bottom = Math.round(clamp(unit / 26, 20, 56));
    const padX = Math.round(fs * 1.1);
    const padY = Math.round(fs * 0.85);

    const panelW = Math.round(landscape
      ? Math.min(viewW - marginX * 2, viewW * 0.82)
      : viewW - marginX * 2);

    return {
      landscape: landscape,
      aspect: aspect,
      viewW: viewW,
      viewH: viewH,
      fs: fs,
      lineH: lineH,
      nameSize: nameSize,
      marginX: marginX,
      bottom: bottom,
      panelH: panelH,
      panelW: panelW,
      panelX: Math.round((viewW - panelW) / 2),
      panelY: viewH - panelH - bottom,
      padX: padX,
      padY: padY,
      textW: panelW - padX * 2,
      maxTextRows: 5,          // 面板最多 5 行，再多等玩家点（不缩字）
      spriteH: Math.round(viewH * (landscape ? 0.94 : 0.72)),
      choiceW: Math.round(landscape ? Math.min(viewW * 0.62, 900) : viewW - marginX * 4),
      choiceH: Math.round(clamp(fs * 2.6, 96, 150)),
      choiceGap: Math.round(fs * 0.7),
    };
  }

  const api = {layoutFor: layoutFor};
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.MyonlLayout = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
