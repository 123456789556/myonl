// 对拍用 runner：读一份 .gal，用 JS 解析器解析，把结果打到 stdout（JSON）。
// 只给 tools/pack_diff.py 调用，不是产品代码。
const fs = require("fs");
const path = require("path");

const file = process.argv[2];
const P = require(path.resolve(__dirname, "..", "engine", "parser.js"));

let text;
try {
  text = fs.readFileSync(file, "utf8").replace(/^\uFEFF/, "");
} catch (e) {
  process.stdout.write(JSON.stringify({ ok: false, error: { line: 0, message: "读不到文件：" + e.message } }));
  process.exit(0);
}

const r = P.parseText(text);
process.stdout.write(JSON.stringify(r));
