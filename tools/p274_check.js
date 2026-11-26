/* P274 对拍执行器：@anim 在手机端解析器 / 演出表单两侧都跑一遍，结果打到 stdout 交给 pytest 判。
   单独跑也行：  node tools/p274_check.js
   退出码 0 = 正例全解析成功、负例全被拒；字段是否一致由 pytest 判。 */
"use strict";

const path = require("path");
const ROOT = path.join(__dirname, "..");
const Parser = require(path.join(ROOT, "engine", "parser.js"));

// editor_perf.js 是挂在 window 上的 IIFE，node 里先给个 window 壳
global.window = {};
require(path.join(ROOT, "editor", "editor_perf.js"));
const PERF = global.window.MYONLPerf;

const OK_SCRIPTS = [
  "@label start\n@anim 玛丽 x=-100~0 1.5\n@end",
  "@label start\n@anim 玛丽 alpha=0 0\n@end",
  "@label start\n@anim 玛丽 scale=1~1.5 2 ease=ease_in\n@end",
  "@label start\n@anim 玛丽 y=-40~0 1.2 ease=ease_out_back\n@end",
];

const BAD_SCRIPTS = [
  "@label start\n@anim 玛丽\n@end",                 // 参数不足
  "@label start\n@anim 玛丽 旋转=0 1\n@end",         // 不支持的参数
  "@label start\n@anim 玛丽 x 1\n@end",              // 缺 "="
  "@label start\n@anim 玛丽 alpha=2 1\n@end",        // alpha 越界
  "@label start\n@anim 玛丽 scale=5 1\n@end",        // scale 越界
  "@label start\n@anim 玛丽 x=一~0 1\n@end",         // 数值非数字
  "@label start\n@anim 玛丽 x=0 -1\n@end",           // 秒数为负
  "@label start\n@anim 玛丽 x=0 1 ease=弹跳\n@end",  // 不支持的缓动
  "@label start\n@anim 玛丽 x=0 1 很快\n@end",        // 第四个参数不是 ease=
];

const PERF_LINES = [
  "@anim 玛丽 x=-100~0 1.5",
  "@anim 玛丽 alpha=0 0",
  "@anim 玛丽 scale=1~1.5 2 ease=ease_in",
];

const out = {
  parse: OK_SCRIPTS.map((s) => Parser.parseText(s)),
  errors: BAD_SCRIPTS.map((s) => {
    const r = Parser.parseText(s);
    return { ok: r.ok, message: r.error ? r.error.message : "", line: r.error ? r.error.line : 0 };
  }),
  // 演出表单：scan → line 必须能原样写回（缺省值不往命令里塞）
  perfRoundtrip: PERF_LINES.map((t) => {
    const p = PERF.scan(t);
    return { input: t, parsed: p, back: p ? PERF.line(p) : null };
  }),
  perfOps: PERF.OPS,
};
process.stdout.write(JSON.stringify(out));
