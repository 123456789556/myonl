/* 浮岛遮挡量化探针（node，不依赖浏览器）。
 *
 * 浮岛 = 游戏态常驻的悬浮控件：右上角 ☰ 菜单键、右上角喇叭、右侧竖列（存档/回顾/设置）。
 * 几何全部照抄 myonl-player.js 里的函数（menuBtnSize / muteRect / menuRect / orbitRect），
 * 这里只算矩形并集，再除以可视画面面积。选项按钮（state.choice）只在分支选择时出现，
 * 属于剧情操作区，不计入"常驻浮岛"。
 *
 * 跑法：node web/test/probe/island-cover.js
 */
"use strict";

const {layoutFor} = require(require("path").join(__dirname, "..", "..", "myonl-layout.js"));

function menuBtnSize(L) {
  const shortSide = Math.min(L.viewW, L.viewH);
  return Math.min(96, Math.max(44, Math.round(shortSide * 0.072)));
}
function muteRect(L) {
  const s = menuBtnSize(L);
  const m = Math.round(Math.min(L.viewW, L.viewH) * 0.022);
  return {x: L.viewW - s - m, y: m, w: s, h: s};
}
function menuRect(L) {
  const s2 = menuBtnSize(L);
  const m = Math.round(Math.min(L.viewW, L.viewH) * 0.03);
  const mr = muteRect(L);
  return {x: mr.x - s2 - Math.round(m * 0.5), y: m, w: s2, h: s2};
}
function orbitRect(L, i, n) {
  const s2 = menuBtnSize(L);
  const m = Math.round(Math.min(L.viewW, L.viewH) * 0.022);
  const gap = Math.round(s2 * 0.18);
  const total = (n - 1) * (s2 + gap) + s2;
  const top = Math.round(L.viewH * (L.landscape ? 0.44 : 0.55) - total / 2);
  return {x: L.viewW - m - s2, y: top + i * (s2 + gap), w: s2, h: s2};
}

function unionArea(rects) {
  // 按钮互不重叠（横向菜单/喇叭、纵向竖列），面积直接相加；若重叠再做矩形差集兜底。
  let area = 0;
  for (const r of rects) area += r.w * r.h;
  // 简单两两去重（重叠部分重复计）
  for (let i = 0; i < rects.length; i++) {
    for (let j = i + 1; j < rects.length; j++) {
      const a = rects[i], b = rects[j];
      const ox = Math.max(0, Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x));
      const oy = Math.max(0, Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y));
      area -= ox * oy;
    }
  }
  return area;
}

function measure(w, h) {
  const L = layoutFor(w, h);
  const rects = [menuRect(L), muteRect(L)];
  const N = 3;
  for (let i = 0; i < N; i++) rects.push(orbitRect(L, i, N));
  const area = unionArea(rects);
  const viewArea = L.viewW * L.viewH;
  const cssArea = w * h;
  return {
    css: `${w}x${h}`,
    tablet: L.tablet,
    landscape: L.landscape,
    view: `${L.viewW}x${L.viewH}`,
    btnCss: Math.round(menuBtnSize(L) * Math.min(w / L.viewW, h / L.viewH)),
    islandAreaView: area,
    viewArea: viewArea,
    pctView: (area / viewArea) * 100,
    pctCss: (area / viewArea) * 100, // 同比例换算，CSS 百分比一致
  };
}

const cases = [
  [390, 844, "手机竖屏"],
  [844, 390, "手机横屏"],
  [800, 1280, "平板竖屏"],
  [1280, 800, "平板横屏"],
  [1024, 600, "小平板横屏"],
  [1280, 720, "电脑横屏"],
];

const rows = cases.map(([w, h, label]) => ({label, ...measure(w, h)}));
for (const r of rows) {
  console.log(`${r.label.padEnd(10)} ${r.css.padEnd(10)} view ${r.view} ` +
    `按钮 ${r.btnCss}px  遮挡 ${r.islandAreaView}/${r.viewArea} ` +
    `= ${r.pctView.toFixed(2)}%`);
}

// 阈值依据：常驻浮岛遮挡可视画面超过 3% 才算"压画面"（galgame 立绘/背景主体区）。
const threshold = 3.0;
const bad = rows.filter((r) => r.pctView > threshold);
console.log(`\n阈值：遮挡 > ${threshold}% 判定为需要底板化/收窄`);
if (bad.length) {
  for (const r of bad) console.log(`  超阈值：${r.label} ${r.pctView.toFixed(2)}%`);
} else {
  console.log("  各尺寸常驻浮岛遮挡均在阈值内。");
}
module.exports = {measure, rows, threshold};
