/* 双端对拍执行器：读 tests/golden/at_rules.json（正例）与 at_rules_errors.json（负例），
   用 JS 解析器跑一遍，把结果打到 stdout 交给 pytest 判。
   单独跑也行：  node tools/at_rules_check.js
   退出码 0 = 正例全解析成功、负例全被拒。内容是否逐字段一致由 pytest 判。 */
"use strict";

const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..");
const Parser = require(path.join(ROOT, "engine", "parser.js"));

function load(file) {
  return JSON.parse(fs.readFileSync(path.join(ROOT, "tests", "golden", file), "utf8"));
}

// 与 tools/gen_at_rules.py 的 strip_file 对齐：file 字段两端允许不同
function strip(node) {
  if (Array.isArray(node)) return node.map(strip);
  if (node && typeof node === "object") {
    const out = {};
    Object.keys(node).forEach((k) => {
      if (k !== "file") out[k] = strip(node[k]);
    });
    return out;
  }
  return node;
}

const posCases = load("at_rules.json").cases.map((c) => {
  const r = Parser.parseText(c.script);
  if (!r.ok) return { name: c.name, ok: false, error: r.error };
  return { name: c.name, ok: true, got: strip(r.instructions) };
});

const negCases = load("at_rules_errors.json").cases.map((c) => {
  const r = Parser.parseText(c.script);
  if (r.ok) return { name: c.name, ok: true };  // 本该报错却过了，pytest 会判红
  return { name: c.name, ok: false, line: r.error.line, message: r.error.message };
});

const badPos = posCases.filter((r) => !r.ok).length;
const badNeg = negCases.filter((r) => r.ok).length;

process.stdout.write(JSON.stringify({ cases: posCases, errors: negCases }));
process.exit(badPos + badNeg ? 1 : 0);
