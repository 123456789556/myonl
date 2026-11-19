// 性能实测专用：在内存里拼一份 MYONL pack，渲染成单文件 HTML 写到 outDir。
// 被 tools/perf_probe 下的 Python 脚本以子进程调用（node），不进正式打包链。
//
// 用法：node tools/perf_probe/make_probe_pack.js <outDir> <mode> [count]
//   mode = empty | images | movie
//     empty  : 无图无视频，首屏冷启动基线
//     images : count 张 1280x720 渐变 PNG（dataURI），背景随场景轮换
//     movie  : 一段 count=1 的真视频（dataURI 由 Python 端写 movies.json 注入）
//   count  : images 模式的图片张数（20 / 60 / 120 …）
//
// 输出：<outDir>/pack.html，以及 <outDir>/movies.json（仅 movie 模式，由调用方填）。

const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..", "..");
require(path.join(ROOT, "engine", "parser.js"));
require(path.join(ROOT, "engine", "pack.js"));

const outDir = process.argv[2];
const mode = process.argv[3] || "empty";
const count = Math.max(0, parseInt(process.argv[4] || "0", 10));

// 生成一张 1280x720 的纯色渐变 PNG dataURI。用极轻量的方式：直接画一张纯色底，
// 再写几行字，保证每张图解码后位图体积一致（1280*720*4 ≈ 3.51MB 位图）。
// 为避免在 node 里引图像库，这里用最小合法 PNG：纯色由浏览器解码成完整位图即可，
// 内存吃的是解出来的位图，不是文件大小。
// —— 但纯 1x1 PNG 浏览器会上采样，位图仍按 naturalWidth*naturalHeight*4 算，
//    所以直接给一张真实尺寸的纯色 PNG（Pillow 在 Python 端已经生成到 assets 目录，
//    这里改为读 Python 生成的 dataURI 清单 images.json，保持单一素材来源）。

function b64PngSolid(w, h, rgb) {
  // 不依赖图像库：返回一个占位，真正的像素图由 Python 端 images.json 提供。
  return { w: w, h: h, rgb: rgb };
}

const imagesJsonPath = path.join(outDir, "images.json");
const moviesJsonPath = path.join(outDir, "movies.json");

let assets = {};
let movies = {};
let videos = {};
let scriptLines = [];

if (mode === "images") {
  if (!fs.existsSync(imagesJsonPath)) {
    console.error("缺 images.json：先跑 Python 端生成素材");
    process.exit(2);
  }
  assets = JSON.parse(fs.readFileSync(imagesJsonPath, "utf8"));
  // 剧本：封面 + count 个背景场景，每张背景配一句台词，循环推进，便于在压力档里
  // 反复 drawImage、观察帧时间与活跃图数量。
  const names = Object.keys(assets);
  scriptLines.push("@bg " + names[0]);
  names.forEach((n, i) => {
    scriptLines.push("@bg " + n);
    scriptLines.push("@[旁白] 第 " + (i + 1) + " 张背景，用于素材量压力实测。");
  });
  // 回到第一张收尾
  scriptLines.push("@bg " + names[0]);
  scriptLines.push("@ 旁白 压力场景结束。");
  scriptLines.push("@end");
} else if (mode === "movie") {
  if (fs.existsSync(moviesJsonPath)) {
    movies = JSON.parse(fs.readFileSync(moviesJsonPath, "utf8"));
  }
  // 静态背景占位：pack.assets 给一张 1x1 透明 PNG，避免播放器找不到图黑屏报错。
  const PNG_1X1 = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==";
  assets["bg_static"] = PNG_1X1;
  const mvName = Object.keys(movies)[0] || "mov1";

  // 帧序列视频清单（可选）：转屏 t0 重置验证用
  const vidsPath = path.join(outDir, "videos.json");
  if (fs.existsSync(vidsPath)) videos = JSON.parse(fs.readFileSync(vidsPath, "utf8"));
  const seqName = Object.keys(videos)[0] || "";

  // 场景流：静态开场 → 帧序列视频（测转屏 t0）→ 切回静态 → 进真视频 → 切走。
  const lines = [
    "@bg bg_static",
    "@[旁白] 视频前的静态场景。",
  ];
  if (seqName) {
    lines.push("@video " + seqName + " fps=12 loop=1");
    lines.push("@[旁白] 帧序列播放中，准备转屏。");
  }
  lines.push(
    "@bg bg_static",
    "@[旁白] 帧序列已切走。",
    "@video " + mvName + " file loop=1",
    "@[旁白] 真视频播放中。",
    "@bg bg_static",
    "@[旁白] 真视频已切走。",
    "@end",
  );
  scriptLines = lines;
} else {
  // empty：纯文本，无素材，冷启动基线（给一张 1x1 透明 PNG 占位背景）
  const PNG_1X1 = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==";
  assets["bg_static"] = PNG_1X1;
  scriptLines = [
    "@bg bg_static",
    "@[旁白] 首屏冷启动基线场景。",
    "@[旁白] 第二句台词。",
    "@end",
  ];
}

const scriptText = scriptLines.join("\n") + "\n";

const r = globalThis.MYONLPack.buildPack({
  title: "性能实测-" + mode,
  scriptText: scriptText,
  assets: assets,
  audio: {},
  videos: videos,
  movies: movies,
  config: {},
  orientation: "any",
});

if (!r.ok) {
  console.error("打包失败 第" + r.error.line + "行 " + r.error.message);
  process.exit(2);
}

const playerSrc = ["myonl-core.js", "myonl-layout.js", "myonl-player.js"].map(function (n) {
  return fs.readFileSync(path.join(ROOT, "web", n), "utf8");
});
const html = globalThis.MYONLPack.renderSingle(r.pack, playerSrc);

fs.mkdirSync(outDir, { recursive: true });
fs.writeFileSync(path.join(outDir, "pack.html"), html, "utf8");
console.log("ok mode=" + mode + " count=" + Object.keys(assets).length +
            " ins=" + r.pack.ins.length + " bytes=" + Buffer.byteLength(html));
