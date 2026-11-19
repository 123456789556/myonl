/* 外链模式的契约测试：素材从 dataURI 变成相对路径，原 pack 不被改动。
   这是"作品能长到几百 MB"那一层的第一块地基 —— 跑在 node 里，不依赖浏览器。 */
const fs = require("fs");
const path = require("path");
const assert = require("assert");

const src = fs.readFileSync(path.join(__dirname, "..", "..", "engine", "pack.js"), "utf8");
// pack.js 用 IIFE 挂到 globalThis（node 里没有 window），执行后从真全局取
new Function(src)();
const Pack = globalThis.MYONLPack;

assert.ok(Pack && typeof Pack.externalize === "function", "externalize 应该存在");

// 造一个最小 pack：一张图、一段语音、一段视频
const pack = {
  version: 1,
  title: "测试",
  assets: { "bg.png": "data:image/png;base64,AAAA" },
  audio: { "voice.mp3": "data:audio/mpeg;base64,BBBB" },
  movies: { "op.mp4": { src: "data:video/mp4;base64,CCCC", mime: "video/mp4" } },
};

const out = Pack.externalize(pack, "");

// 1) 素材值变成相对路径
assert.strictEqual(out.pack.assets["bg.png"], "img/bg.png", "图片应走 img/");
assert.strictEqual(out.pack.audio["voice.mp3"], "audio/voice.mp3", "音频应走 audio/");
assert.strictEqual(out.pack.movies["op.mp4"].src, "movie/op.mp4", "视频应走 movie/");
assert.strictEqual(out.pack.movies["op.mp4"].mime, "video/mp4", "mime 不能丢");

// 2) 文件表里有原始 dataURI，路径和 pack 里的一致
assert.strictEqual(out.files["img/bg.png"], pack.assets["bg.png"]);
assert.strictEqual(out.files["audio/voice.mp3"], pack.audio["voice.mp3"]);
assert.strictEqual(out.files["movie/op.mp4"], pack.movies["op.mp4"].src);
assert.strictEqual(Object.keys(out.files).length, 3, "三个素材三个文件");

// 3) 原 pack 不能被改（调用方可能还要拿去出单文件）
assert.ok(pack.assets["bg.png"].startsWith("data:"), "原 pack 的图应保持 dataURI");
assert.ok(pack.movies["op.mp4"].src.startsWith("data:"), "原 pack 的视频应保持 dataURI");

// 4) 剧本以外的字段原样带过去
assert.strictEqual(out.pack.title, "测试");
assert.strictEqual(out.pack.version, 1);

console.log("externalize OK");
