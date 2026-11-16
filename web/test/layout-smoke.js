/* 布局冒烟（node）：横屏/竖屏/方屏都要给出合理的字号与面板，且不能溢出。
 * 跑法：node web/test/layout-smoke.js
 */
"use strict";

const assert = require("assert");
const path = require("path");
const {layoutFor} = require(path.join(__dirname, "..", "myonl-layout.js"));

function check(name, w, h, expectLandscape) {
  const L = layoutFor(w, h);
  assert.strictEqual(L.landscape, expectLandscape, name + "：横竖屏判定");
  assert.ok(L.viewW >= 1080 && L.viewH >= 1080, name + "：短边不小于 1080");
  assert.ok(L.fs >= 28 && L.fs <= 64, name + "：字号在区间内（" + L.fs + "）");
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
const tablet = check("iPad 820×1180", 820, 1180, false);
const square = check("方屏 600×600", 600, 600, false);
const ultraWide = check("超宽 2400×900", 2400, 900, true);
const ultraNarrow = check("超窄 360×1200", 360, 1200, false);

// 横竖屏字号要接近（转屏不该变蚂蚁或巨字）
const fsDiff = Math.abs(landscape.fs - portrait.fs);
assert.ok(fsDiff <= 4, "横竖屏字号差 ≤4（实际 " + fsDiff + "）");

// 横屏面板更矮更宽（视觉上不挡住立绘）
assert.ok(landscape.panelH < portrait.panelH || landscape.viewH < portrait.viewH,
          "横屏面板高度按自己的画布比例算");

// 极端窗口也不爆
assert.ok(ultraWide.viewW / ultraWide.viewH <= 2.2);
assert.ok(ultraNarrow.viewW / ultraNarrow.viewH >= 0.42);
assert.ok(square.panelH > 0 && tablet.panelH > 0);
// 竖屏画布应该又高又窄（390×844 这种真手机比例）
assert.ok(portrait.viewH > portrait.viewW * 1.8, "手机竖屏画布是竖长的（" + portrait.viewW + "×" + portrait.viewH + "）");
assert.ok(landscape.viewW > landscape.viewH * 1.8, "手机横屏画布是横宽的（" + landscape.viewW + "×" + landscape.viewH + "）");

console.log("layout-smoke: 全部通过（竖屏字 " + portrait.fs + "px / 横屏字 " + landscape.fs + "px）");
