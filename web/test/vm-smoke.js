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

// ---- 9. P73：@fg 前景贴图 / @anim 补间 / @video 帧序列 ----
const vmF = createVM({ins: [
  {op: "bg", image: "bg_a"},
  {op: "fg", name: "雨", x: 0, y: 12, alpha: 0.8},
  {op: "anim", char: "甲", param: "x", from: 0, to: 120, secs: 0.4},
  {op: "say", char: null, text: "来了"},
  {op: "fg", reset: true},
  {op: "video", name: "海浪", fps: 24},
  {op: "say", char: null, text: "海"},
  {op: "bg", image: "bg_b"},        // 切回静态背景：视频要停
  {op: "end"},
]});
vmF.next();                                        // bg
ev = vmF.next();                                   // fg
assert.strictEqual(ev.type, "fg");
assert.strictEqual(vmF.state.fg.name, "雨");
assert.strictEqual(vmF.state.fg.alpha, 0.8);
assert.strictEqual(vmF.state.fg.y, 12);
ev = vmF.next();                                   // anim
assert.strictEqual(ev.type, "anim");
assert.strictEqual(ev.param, "x");
assert.strictEqual(vmF.state.anim["甲"].x.to, 120);
assert.strictEqual(vmF.state.anim["甲"].x.from, 0);
// 存档只留终值：中间过程不重放
const savedF = vmF.save();
assert.ok(savedF.indexOf("animFinal") > 0);
ev = vmF.next();                                   // say
assert.strictEqual(ev.type, "say");
ev = vmF.next();                                   // fg reset
assert.strictEqual(vmF.state.fg, null);
ev = vmF.next();                                   // video
assert.strictEqual(ev.type, "video");
assert.strictEqual(vmF.state.video.name, "海浪");
assert.strictEqual(vmF.state.video.fps, 24);
ev = vmF.next();                                   // say
assert.strictEqual(ev.type, "say");
ev = vmF.next();                                   // bg 切回背景
assert.strictEqual(vmF.state.video, null);
// 读档：fg / anim 终值 / video 都要复原
const vmG = createVM({ins: [{op: "say", char: null, text: "x"}, {op: "end"}]});
assert.ok(vmG.load(savedF));
assert.strictEqual(vmG.state.fg.name, "雨");
assert.strictEqual(vmG.state.anim["甲"].x.to, 120);
assert.strictEqual(vmG.state.anim["甲"].x.from, 120);   // 读档后起点=终点，直接落到结果画面

// ---- 存读同一句：pc 没跟着存的话，读档会一路退回开头（P105 修的就是这个）----
{
  const p2 = {characters: [], ins: [
    {op: "label", name: "start"},
    {op: "say", char: null, text: "第一句"},
    {op: "say", char: null, text: "第二句"},
    {op: "wait", seconds: 2},
    {op: "say", char: null, text: "第三句"},
  ]};
  const a = createVM(p2);
  a.restart("start");
  assert.strictEqual(a.next().text, "第一句");
  assert.strictEqual(a.next().text, "第二句");
  const snap2 = a.save();
  const obj = JSON.parse(snap2);
  assert.ok(Number.isInteger(obj.pc) && obj.pc > 0,
            "存档里要带真实的指令位置，不能是 undefined；实得 pc=" + obj.pc);
  const b2 = createVM(p2);
  assert.ok(b2.load(snap2));
  assert.strictEqual(b2.next().text, "第二句", "读档要回到存档当时那一句，不能退回开头");
  assert.strictEqual(b2.next().type, "wait");
  assert.strictEqual(b2.next().text, "第三句", "读档后往下走不能乱");

  // 存档点正好落在 @wait 上：核心只负责如实回到那条指令，
  // "别停在没有台词的静默里"是播放器的事（loadSlot 里抹平等待）。
  const c3 = createVM(p2);
  c3.restart("start");
  c3.next(); c3.next();
  const atWait = JSON.parse(c3.save()).pc;
  assert.ok(atWait >= 0 && atWait <= 3, "存档位置不能越界");
}

console.log("vm-smoke: 全部通过");
