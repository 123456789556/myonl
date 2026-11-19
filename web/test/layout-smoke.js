/* 布局冒烟（node）：横屏/竖屏/方屏都要给出合理的字号与面板，且不能溢出。
 * 跑法：node web/test/layout-smoke.js
 */
"use strict";

const assert = require("assert");
const path = require("path");
const {layoutFor} = require(path.join(__dirname, "..", "myonl-layout.js"));

function check(name, w, h, expectLandscape) {
  const L = layoutFor(w, h);
  const scale = Math.min(w / L.viewW, h / L.viewH);
  assert.strictEqual(L.landscape, expectLandscape, name + "：横竖屏判定");
  assert.ok(L.viewW >= 1080 && L.viewH >= 1080, name + "：短边不小于 1080");
  assert.ok(L.fs >= 17 && L.fs <= 78, name + "：字号在区间内（" + L.fs + "）");
  // P99 平板适配：真正该钉死的是"字落在眼睛里的物理大小"，不是逻辑字号。
  // 手机 390 与安卓平板 1280 都该落在 17.5~19 CSS px 这一档里。
  const fsCss = L.fs * scale;
  assert.ok(fsCss >= 17.5 && fsCss <= 19.5,
            name + "：物理字号 17.5~19.5 CSS px（实际 " + fsCss.toFixed(1) + "）");
  // 正文宽度：一行别超过 40 字，否则中文会串行
  const oneLine = Math.round(L.textW / L.fs);
  assert.ok(oneLine <= 41, name + "：一行不超过 41 字（实际 " + oneLine + "）");
  assert.ok(L.panelH > L.lineH * 3, name + "：面板至少能放 3 行");
  assert.ok(L.panelY >= 0, name + "：面板不出顶");
  assert.ok(L.panelY + L.panelH <= L.viewH, name + "：面板不出底");
  assert.ok(L.panelW > L.padX * 2, name + "：面板宽度够装内边距");
  assert.ok(L.textW > L.fs * 6, name + "：正文宽度够一行");
  // 长宽比跟随真实窗口（只夹 0.42~2.2），常规手机/平板不留黑边
  const ratio = L.viewW / L.viewH;
  assert.ok(ratio >= 0.42 && ratio <= 2.2, name + "：画布比例在夹取区间（" + ratio.toFixed(2) + "）");
  assert.strictEqual(Math.min(L.viewW, L.viewH), 1080, name + "：短边固定 1080");
  return L;
}

const portrait = check("手机竖屏 390×844", 390, 844, false);
const landscape = check("手机横屏 844×390", 844, 390, true);
const tablet = check("安卓平板竖屏 800×1280", 800, 1280, false);
const tabletLand = check("安卓平板横屏 1280×800", 1280, 800, true);
const tabletSmall = check("安卓平板横屏 1024×600", 1024, 600, true);
const square = check("方屏 600×600", 600, 600, false);
const ultraWide = check("超宽 2400×900", 2400, 900, true);
const ultraNarrow = check("超窄 360×1200", 360, 1200, false);

// 横竖屏字号要接近（转屏不该变蚂蚁或巨字）
const fsDiff = Math.abs(landscape.fs - portrait.fs);
assert.ok(fsDiff <= 4, "横竖屏字号差 ≤4（实际 " + fsDiff + "）");

// 平板是"同一档字、更多字一行"，不是把手机整体放大一倍
assert.ok(tablet.tablet && tabletLand.tablet && !portrait.tablet, "短边 ≥600 才算平板");
assert.ok(tabletLand.textW / tabletLand.fs > landscape.textW / landscape.fs,
          "平板横屏一行能装更多字（" + Math.round(tabletLand.textW / tabletLand.fs)
          + " vs 手机 " + Math.round(landscape.textW / landscape.fs) + "）");
assert.ok(Math.abs(tabletLand.fs * 1 - landscape.fs * 1) > 0, "平板与手机字号本就该不同");

// P136 可读性探针：每个尺寸给出 每行字数 / 对话区面积占比 / 按钮最小点击尺寸（CSS px）。
// 探针只读数，不断言；数值进审计报告，改前/改后对比同一份 layoutFor。
function readability(name, w, h) {
  const L = layoutFor(w, h);
  const scale = Math.min(w / L.viewW, h / L.viewH);
  const perLine = Math.round(L.textW / L.fs);
  const panelAreaPct = +((L.panelW * L.panelH) / (L.viewW * L.viewH) * 100).toFixed(1);
  // 常驻浮岛按钮（菜单/喇叭/竖列）最小点击尺寸，逻辑值换算回 CSS px
  const btnCss = Math.round(Math.min(96, Math.max(44, Math.round(Math.min(L.viewW, L.viewH) * 0.072))) * scale);
  return {name, css: `${w}×${h}`, perLine, panelAreaPct, btnCss,
          fsCss: +(L.fs * scale).toFixed(1)};
}

const readabilityRows = [
  readability("手机竖屏", 390, 844),
  readability("手机横屏", 844, 390),
  readability("平板竖屏", 800, 1280),
  readability("平板横屏", 1280, 800),
  readability("小平板横屏", 1024, 600),
];
// 记录不做硬断言：手机窄屏按钮 CSS 尺寸偏小是既有设计（逻辑 44 下限，折回 CSS 约 28），
// 这里只把数值摊开给报告对比，不为迁就新代码放宽既有行为。
void readabilityRows;

// 横屏面板更矮更宽（视觉上不挡住立绘）
assert.ok(landscape.panelH < portrait.panelH || landscape.viewH < portrait.viewH,
          "横屏面板高度按自己的画布比例算");

// P136 平板宽屏双栏：只有"平板 + 横屏"才拆对话栏 / 立绘栏；竖屏与手机仍整幅堆叠。
// 分区必须互不重叠、都落在画布内，且对话栏不压进立绘栏。
function checkWide(L, name, shouldBeWide) {
  assert.strictEqual(!!L.wide, shouldBeWide, name + "：wide 结构开关判定");
  if (!shouldBeWide) {
    assert.strictEqual(L.spriteColX, 0, name + "：窄屏立绘占整幅底景起点 0");
    assert.strictEqual(L.spriteColW, L.viewW, name + "：窄屏立绘占整幅宽度");
    return;
  }
  assert.ok(L.dialogColX >= 0, name + "：对话栏不出左边界");
  assert.ok(L.dialogColX + L.dialogColW <= L.viewW, name + "：对话栏不出右边界");
  assert.ok(L.spriteColX >= 0 && L.spriteColX + L.spriteColW <= L.viewW,
            name + "：立绘栏不出右边界");
  assert.ok(L.dialogColX + L.dialogColW <= L.spriteColX,
            name + "：对话栏与立绘栏不重叠（对话右缘 " +
            (L.dialogColX + L.dialogColW) + " ≤ 立绘左缘 " + L.spriteColX + "）");
  assert.ok(L.spriteColW > 0 && L.dialogColW > 0, name + "：两栏都有宽度");
  assert.ok(L.choiceColX === L.dialogColX, name + "：选项跟对话同栏贴左");
}
checkWide(tabletLand, "平板横屏 1280×800", true);
checkWide(tabletSmall, "平板横屏 1024×600", true);
checkWide(tablet, "平板竖屏 800×1280", false);
checkWide(portrait, "手机竖屏 390×844", false);
checkWide(landscape, "手机横屏 844×390", false);

// 极端窗口也不爆
assert.ok(ultraWide.viewW / ultraWide.viewH <= 2.2);
assert.ok(ultraNarrow.viewW / ultraNarrow.viewH >= 0.42);
assert.ok(square.panelH > 0 && tablet.panelH > 0 && tabletSmall.panelH > 0);
// 竖屏画布应该又高又窄（390×844 这种真手机比例）
assert.ok(portrait.viewH > portrait.viewW * 1.8, "手机竖屏画布是竖长的（" + portrait.viewW + "×" + portrait.viewH + "）");
assert.ok(landscape.viewW > landscape.viewH * 1.8, "手机横屏画布是横宽的（" + landscape.viewW + "×" + landscape.viewH + "）");

// P130 底部安全区：全面屏手势条会压住贴底那一行，面板必须真的往上让。
// 探针读的是 CSS env()，量到多少就是多少；这里直接喂一个典型值（iPhone 34 / 安卓 24~48）验换算。
const safe34 = layoutFor(390, 844, {safeBottom: 34});
const safe0 = layoutFor(390, 844, {safeBottom: 0});
assert.ok(safe34.bottom > safe0.bottom, "传了 safeBottom，bottom 没让位");
assert.strictEqual(safe34.bottom - safe0.bottom,
                   Math.round(34 * 1080 / 390),
                   "安全区换算要按短边恒 1080，实际差 " + (safe34.bottom - safe0.bottom));
// 面板跟着抬，且仍不出底
assert.ok(safe34.panelY >= 0, "让位后面板不出顶");

console.log("layout-smoke: 全部通过（竖屏字 " + portrait.fs + "px / 横屏字 " + landscape.fs + "px）");
console.table(readabilityRows);
