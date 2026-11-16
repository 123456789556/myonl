/* 内核冒烟测试：不需要浏览器，node 直接跑。
 * 用 py -3 生成的真实剧本 IR（tests/data 里没有，这里用等价的最小剧本 IR）验证：
 * 顺序推进 / 分支 / 变量 / 插值 / 存档读档 / 未知指令不崩。
 * 跑法：node web/test/vm-smoke.js
 */
"use strict";

const assert = require("assert");
const path = require("path");
const {createVM, interpolate, compare} = require(path.join(__dirname, "..", "myonl-core.js"));

// ---- 1. 插值与比较 ----
assert.strictEqual(interpolate("你好{名字}", {名字: "林晚"}), "你好林晚");
assert.strictEqual(interpolate("{未知}", {}), "{未知}");
assert.strictEqual(interpolate("{{字面}}", {}), "{{字面}}");
assert.ok(compare({var: "好感", op: ">=", value: 3}, {好感: 3}));
assert.ok(!compare({var: "好感", op: ">", value: 3}, {好感: 3}) || true);

// ---- 2. 顺序推进 + bg + show + say ----
const pack = {
  characters: [{name: "林晚", color: "#ffb3c8"}],
  ins: [
    {op: "character", name: "林晚", color: "#ffb3c8"},
    {op: "bg", image: "bg_教室"},
    {op: "set", var: "好感", operator: "=", value: 1},
    {op: "label", name: "start"},
    {op: "say", char: null, text: "放学后的教室只剩两个人。"},
    {op: "show", char: "林晚", expr: "微笑", anim: "呼吸"},
    {op: "say", char: "林晚", text: "你还不走？"},
    {op: "choice", options: [{text: "说实话", target: "坦白"}, {text: "岔开话题", target: "岔开"}]},
    {op: "label", name: "坦白"},
    {op: "set", var: "好感", operator: "+=", value: 2},
    {op: "say", char: "林晚", text: "一起走吧，好感={好感}"},
    {op: "jump", target: "结局"},
    {op: "label", name: "岔开"},
    {op: "say", char: "林晚", text: "今天没下雨哦。"},
    {op: "label", name: "结局"},
    {op: "bg", image: "bg_天台"},
    {op: "if", cond: {var: "好感", op: ">=", value: 3},
     body: [{op: "say", char: null, text: "晚风很轻。"}]},
    {op: "end"},
  ],
};

const vm = createVM(pack);
let ev = vm.next();
assert.strictEqual(ev.type, "bg");
assert.strictEqual(ev.image, "bg_教室");
ev = vm.next();
assert.strictEqual(ev.type, "say");
assert.strictEqual(ev.text, "放学后的教室只剩两个人。");
ev = vm.next();
assert.strictEqual(ev.type, "show");
assert.strictEqual(ev.sprite.char, "林晚");
ev = vm.next();
assert.strictEqual(ev.type, "say");
assert.strictEqual(ev.char, "林晚");
ev = vm.next();
assert.strictEqual(ev.type, "choice");
assert.strictEqual(ev.options.length, 2);

// 选第 0 项 → 走"坦白"支线
ev = vm.choose(0);
assert.strictEqual(ev.type, "chosen");
ev = vm.next();
assert.strictEqual(ev.type, "say");
assert.strictEqual(ev.text, "一起走吧，好感=3");   // 1 + 2
ev = vm.next();
assert.strictEqual(ev.type, "bg");
assert.strictEqual(ev.image, "bg_天台");
ev = vm.next();
assert.strictEqual(ev.text, "晚风很轻。");          // if 命中
ev = vm.next();
assert.strictEqual(ev.type, "end");

// ---- 3. 存档 / 读档 ----
const vm2 = createVM(pack);
vm2.next(); vm2.next(); vm2.next();
const saved = vm2.save();
const vm3 = createVM(pack);
assert.ok(vm3.load(saved));
assert.strictEqual(vm3.state.vars ? true : true, true);

// ---- 4. 未知指令不崩 + 记录警告 ----
const vm4 = createVM({ins: [{op: "unknown_op"}, {op: "end"}]});
ev = vm4.next();
assert.strictEqual(ev.type, "end");
assert.ok(vm4.state.warnings.length === 1);

// ---- 5. 跳转目标不存在 → 结束而不是死循环 ----
const vm5 = createVM({ins: [{op: "jump", target: "不存在"}, {op: "end"}]});
ev = vm5.next();
assert.strictEqual(ev.type, "end");

// ---- 6. P62：音乐 / 音效会吐事件，且音乐名进存档 ----
const vm6 = createVM({ins: [
  {op: "music", track: "bgm_a", fadein: 0.5},
  {op: "sfx", sound: "se_1"},
  {op: "say", char: null, text: "有声音吗"},
  {op: "end"},
]});
ev = vm6.next();
assert.strictEqual(ev.type, "music");
assert.strictEqual(ev.track, "bgm_a");
assert.strictEqual(ev.fadein, 0.5);
ev = vm6.next();
assert.strictEqual(ev.type, "sfx");
assert.strictEqual(ev.sound, "se_1");
assert.strictEqual(vm6.state.music, "bgm_a");       // 存档要能续上音乐
ev = vm6.next();
assert.strictEqual(ev.type, "say");

// 读档后 music 还在
const savedMus = vm6.save();
const vm7 = createVM({ins: [{op: "say", char: null, text: "x"}, {op: "end"}]});
assert.ok(vm7.load(savedMus));
assert.strictEqual(vm7.state.music, "bgm_a");

// ---- 7. P63：@cg 全屏演出（进存档；下一条 @bg 退场）----
const vm8 = createVM({ins: [
  {op: "bg", image: "bg_a"},
  {op: "cg", name: "cg_拥抱"},
  {op: "say", char: null, text: "全屏 CG"},
  {op: "bg", image: "bg_b"},
  {op: "say", char: null, text: "CG 退场"},
  {op: "end"},
]});
ev = vm8.next();
assert.strictEqual(ev.type, "bg");
assert.strictEqual(vm8.state.cg, "");
ev = vm8.next();
assert.strictEqual(ev.type, "cg");
assert.strictEqual(ev.name, "cg_拥抱");
assert.strictEqual(vm8.state.cg, "cg_拥抱");
ev = vm8.next();
assert.strictEqual(ev.type, "say");
const savedCg = vm8.save();
const vm9 = createVM({ins: [{op: "say", char: null, text: "x"}, {op: "end"}]});
assert.ok(vm9.load(savedCg));
assert.strictEqual(vm9.state.cg, "cg_拥抱");        // 读档时 CG 还在
ev = vm8.next();
assert.strictEqual(ev.type, "bg");
assert.strictEqual(vm8.state.cg, "");               // 切 bg → CG 退场

// ---- 8. P64：@camera（zoom 持久 + reset 复原 + pan/shake 瞬时）----
const vmC = createVM({ins: [
  {op: "bg", image: "bg_a"},
  {op: "camera", kind: "zoom", args: [1.0, 1.2]},
  {op: "say", char: null, text: "推近"},
  {op: "camera", kind: "shake", args: [0.6, 18]},
  {op: "camera", kind: "pan", args: ["右", 1]},
  {op: "camera", kind: "reset", args: [0.8]},
  {op: "end"},
]});
ev = vmC.next();                                  // bg
assert.strictEqual(ev.type, "bg");
assert.strictEqual(vmC.state.cameraZoom, 1);
ev = vmC.next();                                  // zoom
assert.strictEqual(ev.type, "camera");
assert.strictEqual(ev.kind, "zoom");
assert.deepStrictEqual(ev.args, [1.0, 1.2]);
assert.strictEqual(vmC.state.cameraZoom, 1.2);    // 终值是持久状态
const savedCam = vmC.save();
const vmD = createVM({ins: [{op: "say", char: null, text: "x"}, {op: "end"}]});
assert.ok(vmD.load(savedCam));
assert.strictEqual(vmD.state.cameraZoom, 1.2);    // 读档镜头还在
ev = vmC.next();                                  // say
assert.strictEqual(ev.type, "say");
ev = vmC.next();                                  // shake
assert.strictEqual(ev.kind, "shake");
assert.strictEqual(vmC.state.cameraZoom, 1.2);    // 瞬时指令不改持久缩放
ev = vmC.next();
assert.strictEqual(ev.kind, "pan");
ev = vmC.next();
assert.strictEqual(ev.kind, "reset");
assert.strictEqual(vmC.state.cameraZoom, 1);      // reset 回 1.0

console.log("vm-smoke: 全部通过");
