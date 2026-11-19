/* N-1 立绘落位字段贯通探针（node，不依赖浏览器）。
 *
 * 背景：web/myonl-core.js 的 show 分支原先只存 char/expr/anim，把 parser IR 里
 * 的 pos/scale/z/x/y/layers 丢了；桌面端 _sprite_rect 却按这些字段落位，两端不一致。
 * 本探针直接喂带全字段的 @show IR，核对：
 *   1. show 事件的 sprite entry 带上 pos/scale/z/x/y/layers；
 *   2. 这些字段进存档，读档后位置/缩放不复位；
 *   3. 下一条没写位置的 @show 清掉上一条残留的位置字段（与桌面端 _show 口径一致）。
 *
 * 跑法：node tools/perf_probe/probe_sprite_fields.js
 */
"use strict";

const assert = require("assert");
const path = require("path");
const {createVM} = require(path.join(__dirname, "..", "..", "web", "myonl-core.js"));

const pack = {
  characters: [{name: "苏晴", color: "#ffb3c8"}],
  ins: [
    {op: "character", name: "苏晴", color: "#ffb3c8"},
    {op: "bg", image: "bg_a"},
    {op: "show", char: "苏晴", expr: "微笑", anim: "呼吸",
     pos: "右", scale: 1.1, z: 2, x: 30, y: -12,
     layers: {"身体": "泳装"}},
    {op: "say", char: "苏晴", text: "站位测试"},
    // 下一条 @show 没写位置：残留字段要被清掉（桌面端 _show 的口径）
    {op: "show", char: "苏晴", expr: "惊讶", anim: "呼吸"},
    {op: "say", char: "苏晴", text: "清掉位置"},
    {op: "end"},
  ],
};

const vm = createVM(pack);
vm.next(); // bg

let ev = vm.next();
assert.strictEqual(ev.type, "show");
const sp = ev.sprite;
assert.strictEqual(sp.pos, "右", "pos 要贯通到 entry");
assert.strictEqual(sp.scale, 1.1, "scale 要贯通到 entry");
assert.strictEqual(sp.z, 2, "z 要贯通到 entry");
assert.strictEqual(sp.x, 30, "x 要贯通到 entry");
assert.strictEqual(sp.y, -12, "y 要贯通到 entry");
assert.deepStrictEqual(sp.layers, {"身体": "泳装"}, "layers 要贯通到 entry");

// 存档：sprites 整对象存取，字段随之进 JSON
const saved = vm.save();
const obj = JSON.parse(saved);
assert.deepStrictEqual(obj.sprites[0], sp, "存档里立绘要带全位置字段");

const vm2 = createVM(pack);
assert.ok(vm2.load(saved));
const sp2 = vm2.state.sprites[0];
assert.strictEqual(sp2.pos, "右", "读档后 pos 不复位");
assert.strictEqual(sp2.scale, 1.1, "读档后 scale 不复位");
assert.strictEqual(sp2.z, 2, "读档后 z 不复位");
assert.strictEqual(sp2.x, 30, "读档后 x 不复位");
assert.strictEqual(sp2.y, -12, "读档后 y 不复位");

// 从存档点往下走：第二条 show（无位置）清掉残留字段
let ev3 = null;
for (let k = 0; k < 6; k++) {
  ev3 = vm2.next();
  if (ev3 && ev3.type === "show" && ev3.sprite && ev3.sprite.expr === "惊讶") break;
}
const sp3 = ev3.sprite || vm2.state.sprites[0];
assert.strictEqual(sp3.pos, null, "本次没写 pos → 清掉");
assert.strictEqual(sp3.scale, 0, "本次没写 scale → 清掉");
assert.strictEqual(sp3.x, 0, "本次没写 x → 清掉");
assert.strictEqual(sp3.y, 0, "本次没写 y → 清掉");
assert.strictEqual(sp3.layers, null, "本次没写 layers → 清掉");

console.log("probe-sprite-fields: 全部通过（pos/scale/z/x/y/layers 贯通 + 存读档不复位）");
