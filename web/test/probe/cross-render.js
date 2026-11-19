/* 电脑端一致性比对探针（node，不依赖浏览器）。
 *
 * 目的：同一批剧本指令，分别按「手机尺寸布局」（web/myonl-layout.js）与「桌面画布
 * 1280×720」（engine/config 画布 + T10 ui_scale）算几何，逐项对比背景/立绘/对话框/
 * 字号层级/选项。桌面侧几何用与 render_*.py 同一套口径在本探针内复算（注释标明出处），
 * 不改动引擎代码；像素级像素差由 Python 侧 snapshot 探针另出。
 *
 * 跑法：node web/test/probe/cross-render.js
 */
"use strict";

const path = require("path");
const fs = require("fs");
const {layoutFor} = require(path.join(__dirname, "..", "..", "myonl-layout.js"));

// ---- 桌面（py）口径常量，与 engine/config.py / render_*.py 对齐 ----
const DESKTOP_W = 1280, DESKTOP_H = 720;
const DESKTOP_UI_SCALE = DESKTOP_H / 720;          // config.ui_scale(): 画布高/720 = 1.0
const DESKTOP_FONT = 22;                            // render_text 默认字号（720p 基准）
const DESKTOP_PANEL_W = 1142;                       // render_dialog panel_width 默认
const DESKTOP_PANEL_H = 232;                        // render_dialog 默认面板高
const DESKTOP_CHOICE_W = 420;                       // render_dialog choices.width 默认
const DESKTOP_CHOICE_H = 52;                        // CHOICE_ROW_HEIGHT

// 手机侧：取典型手机竖屏 CSS 390×844
function mobileLayout() { return layoutFor(390, 844); }

function probeBackground() {
  // 背景两端都是 cover（py _scale_to_cover / js blitNamed），锚点 focal 两端同读 config。
  return {
    item: "背景图 cover 缩放与 focal 锚点",
    mobile: "cover，focal 缺省 0.5 居中",
    desktop: "cover，focal 缺省 0.5 居中",
    match: true,
    note: "两端同为 max(w/sw,h/sh) 铺铺满 + focal 锚点；_p 竖版两端都仅竖窗回退。",
  };
}

function probeDialogFont() {
  const m = mobileLayout();
  const mScale = Math.min(390 / m.viewW, 844 / m.viewH);
  const mFsCss = m.fs * mScale;
  return {
    item: "对话框正文字号层级",
    mobile: `逻辑 ${m.fs}px ≈ ${mFsCss.toFixed(1)} CSS px`,
    desktop: `画布 ${DESKTOP_FONT}px × ui_scale ${DESKTOP_UI_SCALE.toFixed(2)} = ${Math.round(DESKTOP_FONT * DESKTOP_UI_SCALE)}px @${DESKTOP_W}×${DESKTOP_H}`,
    match: null,
    note: "两端基准不同：js 按物理 CSS 18.5px 反推逻辑字号；py 按 720p 基准 22px 乘 ui_scale。需人工在同一物理屏比对可读性。",
  };
}

function probeDialogPanel() {
  const m = mobileLayout();
  const mScale = Math.min(390 / m.viewW, 844 / m.viewH);
  return {
    item: "对话框宽度 / 一行字数",
    mobile: `逻辑面板 ${m.panelW}×${m.panelH}，正文 ${Math.round(m.textW / m.fs)} 字/行`,
    desktop: `面板 ${DESKTOP_PANEL_W}×${DESKTOP_PANEL_H}，正文宽 ${DESKTOP_PANEL_W - 2 * 40}px`,
    match: null,
    note: "js 一行 ≤40 字按物理宽度钳制；py 面板宽 1142px @720p，1280 宽画布下一行字数需在真机量。",
  };
}

function probeChoiceLayout() {
  return {
    item: "选项按钮：宽度 / 位置 / 行高",
    mobile: "choiceW 按竖屏 0.86 宽钳 760 逻辑；竖屏合成底部板，按钮居中",
    desktop: `row_w=${DESKTOP_CHOICE_W} 居中（w//2-row_w//2），row_h=${DESKTOP_CHOICE_H}，贴对话板上方排布`,
    match: false,
    note: "宽度口径不同（js 随屏宽、py 固定 420@720p×ui_scale）；两端都水平居中，纵向都在对话板上方。",
  };
}

function probeSpritePos() {
  return {
    item: "立绘位置：@show pos=左/右 落位",
    mobile: "core.js show 分支只存 char/expr/anim，**丢弃 pos/scale/z/x/y**；player.js 未读 pos，按槽位均分/单人 0.63 排",
    desktop: "runtime 存 pos/scale/z/x/y；_sprite_rect 按 pos=左/右贴边、scale 缩放、z 排序",
    match: false,
    note: "同一剧本写 pos=左，桌面贴左、手机按均分槽位走 —— 位置对不上。根因在 core.js（手机 VM 状态），player.js 只负责画。",
  };
}

function probeCgScaling() {
  return {
    item: "CG 缩放方式",
    mobile: "drawCg 用 blitCover（铺满裁切）",
    desktop: "_draw_cg 用 _scale_to_fit（等比缩进、两侧留黑）",
    match: false,
    note: "同一张 CG，手机铺满裁、桌面留黑边，构图可见范围不同。",
  };
}

function probeSpriteCrop() {
  return {
    item: "横屏立绘半身裁切",
    mobile: "横屏且图高>宽×1.5 时只取上 62% 源图（头顶到膝）",
    desktop: "_sprite_rect 不做半身裁切，整图等比收进槽位",
    match: false,
    note: "横屏两端立绘可见部位不同；属构图策略差异，需确认哪端是设计意图。",
  };
}

function probeAudio() {
  return {
    item: "背景音乐 / 音效触发",
    mobile: "事件 music/sfx/voice 由播放器接管 <audio>，自动播放策略下未交互先静音",
    desktop: "pygame mixer 播 ogg；无头/无设备自动静音",
    match: true,
    note: "触发时机两端同一指令流；差异是平台自动播放策略，非渲染 bug。",
  };
}

function probeCgState() {
  return {
    item: "CG 持久化与退场",
    mobile: "core.js state.cg 进存档；@bg 时清 cg（切回背景退场）",
    desktop: "_cg_showing 是纯展示层状态，**不进 GameState**：读档/重启不还原；@bg 事件只切背景，不清 _cg_showing",
    match: false,
    note: "桌面侧 CG 不随存档还原、且 bg 切换后可能残留；手机侧 bg 会退场。属于桌面渲染侧状态管理缺口。",
  };
}

function probeFgScaling() {
  return {
    item: "前景贴图（@fg）缩放方式",
    mobile: "drawFg 按 viewW/img.width、viewH/img.height 取大值 cover 铺满，x/y 按 1280 基准换算偏移",
    desktop: "_draw_fg 按原始像素 blit 到 (x,y)，不按画布缩放；1280 基准坐标在 720p 画布上需另行换算",
    match: false,
    note: "同一张蒙版/前景，手机铺满、桌面按原图尺寸贴，可见范围与位置不同。",
  };
}

const rows = [
  probeBackground(),
  probeDialogFont(),
  probeDialogPanel(),
  probeChoiceLayout(),
  probeSpritePos(),
  probeCgScaling(),
  probeCgState(),
  probeFgScaling(),
  probeSpriteCrop(),
  probeAudio(),
];

let bad = 0, unk = 0;
for (const r of rows) {
  if (r.match === false) bad++;
  if (r.match === null) unk++;
  console.log(`\n【${r.item}】 ${r.match === true ? "一致" : r.match === false ? "不一致" : "待人工量"}`);
  console.log("  手机：" + r.mobile);
  console.log("  电脑：" + r.desktop);
  console.log("  依据：" + r.note);
}
console.log(`\n汇总：明确不一致 ${bad} 项，待同屏人工量 ${unk} 项，一致 ${rows.length - bad - unk} 项`);

module.exports = {rows};
