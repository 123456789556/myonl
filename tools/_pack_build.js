// 用 JS 侧解析器 + 打包器造一个单文件成品，供 tools/pack_js_e2e.py 验证。
// 参数：<script.gal> <输出 html>
// 只验证"能跑"，不带素材（无图时播放器走渐变底色，这是设计好的降级）。
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const gal = process.argv[2];
const out = process.argv[3];

require(path.join(ROOT, "engine", "parser.js"));
require(path.join(ROOT, "engine", "pack.js"));

const title = path.basename(path.dirname(gal));
const r = globalThis.MYONLPack.buildPack({
  title: title,
  scriptText: fs.readFileSync(gal, "utf8").replace(/^\uFEFF/, ""),
  assets: {}, audio: {}, videos: {}, config: {}, orientation: "any",
});
if (!r.ok) {
  console.error("打包失败 第" + r.error.line + "行 " + r.error.message);
  process.exit(2);
}

const playerSrc = ["myonl-core.js", "myonl-layout.js", "myonl-player.js"].map(function (n) {
  return fs.readFileSync(path.join(ROOT, "web", n), "utf8");
});
const html = globalThis.MYONLPack.renderSingle(r.pack, playerSrc);

fs.mkdirSync(path.dirname(out), { recursive: true });
fs.writeFileSync(out, html, "utf8");
console.log("ok ins=" + r.pack.ins.length + " bytes=" + Buffer.byteLength(html));
