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
    // P58：手机上字要能看清。短边 1080 时 42px 逻辑 ≈ 390 宽屏上的 15 CSS px（偏小），
    // 改成短边的 1/22 ≈ 49px → 约 18 CSS px，横竖屏仍然一致。
    const fs = Math.round(clamp(unit / 22, 34, 78));
    const lineH = Math.round(fs * 1.65);
    const nameSize = Math.round(fs * 1.18);

    const marginX = Math.round(viewW * (landscape ? 0.045 : 0.035));
    const panelH = Math.round(clamp(viewH * (landscape ? 0.34 : 0.33),
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
      // 面板能装几行由面板高度算（竖屏面板固定约三分之一屏，横屏是内容驱动）。
      // 装不下的就分页让玩家点，不缩字号 —— 缩了更难读。
      maxTextRows: Math.max(3, Math.min(8, Math.floor(
        ((landscape ? Math.round(viewH * 0.46) : panelH) - padY * 2 - Math.round(fs * 0.7))
        / lineH))),
      // P74：竖屏立绘从 0.72 提到 0.86，但真正的上限是「对话框上沿」——
      // 全身立绘要让人从头到脚都看见，脚就不能落到底边（那里被对话框盖住）。
      // 所以身高取 min(屏高比例, panelY - 6)，头顶不会顶出屏幕。
      // P74：竖屏立绘从 0.72 提到 0.86，但上限是「对话框上沿」——
      // 竖屏看的是全身（脚要落在面板之上，不能被面板盖掉）；
      // 横屏反过来要人「大」，贴底边让人被对话框压住小腿，这是横屏 galgame 的标准构图。
      spriteH: Math.round(landscape
        ? viewH * 0.94
        : Math.min(viewH * 0.86, viewH - panelH - bottom - 6)),
      choiceW: Math.round(landscape ? Math.min(viewW * 0.62, 900) : viewW - marginX * 4),
      // P58：选项按钮按手指来算——最小 120 逻辑 px（1080 短边下约 43 CSS px，接近 44pt 触摸推荐值）
      choiceH: Math.round(clamp(fs * 2.8, 120, 170)),
      choiceGap: Math.round(fs * 0.7),
    };
  }

  const api = {layoutFor: layoutFor};
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.MyonlLayout = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
