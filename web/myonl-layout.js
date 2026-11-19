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

  /* cssW/cssH = 窗口 CSS 像素；c = 可选的 {safeBottom}（底部安全区，CSS 像素）。
     返回逻辑画布与所有排布尺寸。 */
  function layoutFor(cssW, cssH, c) {
    const w = Math.max(1, Math.round(cssW || 1));
    const h = Math.max(1, Math.round(cssH || 1));
    const aspect = clamp(w / h, ASPECT_MIN, ASPECT_MAX);
    const landscape = aspect > 1.02;

    // 短边统一 1080，长边按真实比例（竖屏 1080×2338、横屏 2333×1080）
    const shortSide = 1080;
    const viewW = Math.round(shortSide * (aspect >= 1 ? aspect : 1));
    const viewH = Math.round(shortSide * (aspect >= 1 ? 1 : 1 / aspect));

    const unit = Math.min(viewW, viewH);          // 字号/间距的基准
    // 字号（P99 平板适配）：以前是 unit/22 —— 而 unit 恒 1080，等于"字号只跟逻辑画布挂钩"。
    // 手机上 49 逻辑 ≈ 17.7 CSS px 刚好，但平板窗口 768 CSS 宽时缩放系数是 0.71（手机 0.36），
    // 同样 49 逻辑就变成 34.8 CSS px —— 整屏内容等于被放大了近一倍，这才是"平板没适配"的真身。
    // 反过来按"物理 CSS 字号"反推：逻辑画布短边恒 1080，所以 fs = 目标CSS × 1080 / 短边CSS，
    // 任何尺寸的设备落到眼睛里的字都一样大，大屏多出来的地方留给"一屏更多字"。
    const cssShort = Math.min(w, h);
    const fsCss = 18.5;                            // 目标：约 18.5 CSS px（正文舒适区）
    const fs = Math.round(clamp(fsCss * shortSide / Math.max(1, cssShort), 17, 78));
    // 短边 ≥600 CSS 视为平板（7 寸以上 / 折叠屏展开都落在这边）
    const tablet = cssShort >= 600;
    const lineH = Math.round(fs * 1.65);
    const nameSize = Math.round(fs * 1.18);

    const marginX = Math.round(viewW * (landscape ? 0.045 : 0.035));
    // ---- 平板宽屏分区（P136）：先算结构，后面面板/选项都能引用 ----
    // 以前 tablet 标志只被用来放大几个尺寸，没有"结构"：宽屏上对话区/立绘区/操作区
    // 仍是手机那套上下堆叠，宽出来的地方全空着。这里把宽屏的三块区域拆成显式区间，
    // 交给播放器按区间排布（双栏）；手机尺寸下这些区间退回手机默认的上下堆叠。
    // 只在逻辑画布上给比例与边界，不碰具体绘制（绘制在 player.js 独占）。
    const panelH = Math.round(clamp(viewH * (landscape ? 0.34 : 0.33),
                                    lineH * 3 + 60, viewH * 0.5));
    // 底部安全区：全面屏手机上系统手势条会压住贴底那一行。
    // 传进来的是 CSS 像素，这里按"逻辑短边恒 1080"换算成逻辑值，和字号同一套换算。
    const safeCss = Math.max(0, Number((c && c.safeBottom) || 0));
    const shortCss = Math.min(w, h);
    const safeLogical = Math.round(safeCss * (1080 / Math.max(1, shortCss)));
    const bottom = Math.round(clamp(unit / 26, 20, 56)) + safeLogical;
    const padX = Math.round(fs * 1.1);
    const padY = Math.round(fs * 0.85);

    // 正文别横跨太远：中文一行超过 40 字左右就开始"串行"，眼睛回不到下一行开头。
    // "多少字一行"= 物理宽度 / 物理字号，两个都该钉死 —— 所以限制的不是字数，
    // 而是正文的物理宽度：任何设备上都不超过 ~720 CSS px（720/18.5 ≈ 39 字）。
    // 手机 390 宽时这条不起作用（面板本来就只到 363 CSS），限制的是安卓平板横屏
    // 那种 1280×800、1024×600 的宽画布 —— 不然面板铺满就是一行 50 多字。
    const scale = Math.min(w / viewW, h / viewH);
    const maxPanelW = Math.round(720 / Math.max(0.2, scale)) + padX * 2;
    const panelW = Math.round(Math.min(
      landscape ? viewW * 0.80 : viewW - marginX * 2,
      maxPanelW));
    // ---- 平板宽屏分区（P136）：面板几何算完后再算双栏边界 ----
    // 以前 tablet 标志只被用来放大几个尺寸，没有"结构"：宽屏上对话区/立绘区/操作区
    // 仍是手机那套上下堆叠，宽出来的地方全空着。这里把宽屏的三块区域拆成显式区间，
    // 交给播放器按区间排布（双栏）；手机尺寸下这些区间退回手机默认的上下堆叠。
    // 只在逻辑画布上给比例与边界，不碰具体绘制（绘制在 player.js 独占）。
    const wide = tablet && landscape;
    // 立绘槽位：宽屏给右侧一栏，左侧留给对话/选项；窄屏（手机/平板竖屏）立绘占整幅底景。
    const spriteColW = wide ? Math.round(viewW * 0.42) : viewW;
    const spriteColX = wide ? viewW - spriteColW : 0;
    // 对话区：宽屏左侧一栏，宽度按"一行不超过 40 字"另给上限，不铺满整栏。
    const dialogColW = wide ? Math.min(Math.round(viewW * 0.52), maxPanelW) : panelW;
    const dialogColX = wide ? Math.round(viewW * 0.04) : Math.round((viewW - panelW) / 2);
    // 操作区（选项）：宽屏跟对话区同栏、贴左；手机沿用浮岛/底部板的既有几何。
    const choiceColW = wide ? Math.min(Math.round(viewW * 0.46), 640) : 0;

    return {
      // CSS / 逻辑 的换算比。播放器要按"CSS 像素"定触摸下限（44），
      // 必须拿它把 CSS 反推成逻辑值，否则 360 宽的竖屏上 78 逻辑只有 26 CSS。
      scale: scale,
      landscape: landscape,
      tablet: tablet,
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
      // 竖屏立绘上限只给"屏高比例"，不再在这里减面板高 —— 面板是按台词行数收放的
      // （一句台词约 1.9 行、长句会涨到 8 行），用布局里这个静态值算，人就被锁死在
      // 一个偏小的尺寸：平板上明明只有三行字，上面却按"九行面板"留空，人像站远处。
      // 实际可用高度由播放器按「当前」面板高度现算（panelTopY）。
      // P125：平板横屏单独收一档。手机上"人物贴底、被面板压住小腿"是横屏 galgame 的
      // 标准构图，但平板横屏有 1280 CSS 宽、800 高，人物按 0.92 撑满就变成一堵墙，
      // 面板再压上来只剩一张脸 —— 这是"平板没适配"最直观的那一条。收到 0.82。
      spriteH: Math.round(viewH * (landscape ? (tablet ? 0.82 : 0.92) : 0.86)),
      // 横屏选项靠左占 0.42：再宽就压到人物身上，再窄中文字会换行
      // P125：平板横屏给 0.36 —— 宽画布上 0.42 会长到 500 多 CSS，按钮拉成一条带子
      choiceW: Math.round(landscape
        ? Math.min(viewW * (tablet ? 0.36 : 0.42), tablet ? 640 : 720)
        // P125：平板竖屏按手机比例铺就是 86% 宽的一条带子，字和按钮离得太远。
        // 收到 760 逻辑（800 CSS 竖屏上约 63%），和正文同一个"一行别太长"的道理。
        : Math.min(viewW - marginX * 4, tablet ? 760 : viewW - marginX * 4)),
      // P58：选项按钮按手指来算——最小 120 逻辑 px（1080 短边下约 43 CSS px，接近 44pt 触摸推荐值）
      choiceH: Math.round(clamp(fs * 2.8, 120, 170)),
      choiceGap: Math.round(fs * (landscape ? 1.0 : 0.7)),
      // 宽屏双栏结构开关与三块区域的逻辑画布边界（仅 wide 时生效；否则退回整幅）。
      wide: wide,
      spriteColX: spriteColX,
      spriteColW: spriteColW,
      dialogColX: dialogColX,
      dialogColW: dialogColW,
      choiceColX: dialogColX,
      choiceColW: choiceColW,
    };
  }

  const api = {layoutFor: layoutFor};
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.MyonlLayout = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
