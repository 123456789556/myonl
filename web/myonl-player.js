/* MYONL 播放器：canvas 渲染 + 触控推进，竖屏/横屏自适应。
 *
 * 和桌面端的关系：桌面引擎（pygame）仍是一等公民，作者在桌面编辑器里写剧本、
 * 调 UI；这里只负责"把它放到手机上"。视觉参数**读同一份 pack.json 的 config**
 * （主题色、对话框几何、P53 皮肤键），不是另造一套。
 *
 * 转屏：监听 resize / orientationchange，重算逻辑画布（web/myonl-layout.js），
 * 重排当前台词；正在打字的进度按比例保留，不会跳字也不会重播。
 */
(function () {
  "use strict";

  const CORE = window.MyonlCore;
  const LAYOUT = window.MyonlLayout;
  if (!CORE || !LAYOUT) {
    document.body.innerHTML = "<p style='color:#fff;font:16px sans-serif'>播放器脚本没加载全（myonl-core.js / myonl-layout.js）</p>";
    return;
  }

  const canvas = document.getElementById("game");
  const ctx = canvas.getContext("2d");
  const FACE = '"PingFang SC", "Source Han Sans SC", "Microsoft YaHei", system-ui, sans-serif';
  const BASE_CPS = 32;                // 打字机基准：字/秒（设置里可调）

  // 玩家设置（本机 localStorage，与游戏无关）：文字速度 / 字号 / 音量 / 自动翻页 / 画质 / 快进 /
  // 画面方向 / 对话框样式（P101：经典 · 悬浮 · 极简，见 dlgStyle()）
  const PREF = {speed: 1, text: 1, vol: 0.7, auto: 0, quality: 1, skip: 0, orient: "auto", dlg: 1};
  const PREF_KEY = "myonl:v2:prefs";   // P85：带版本，旧键由 loadPrefs 迁移
  let helpSeen = false;                 // 首次引导标记：跟设置一起存（以前是裸键）
  const UI = {open: false, view: "menu", rects: [], t0: 0, logPage: 0};
  let pack = null;
  let FOCAL = {};          // 构图锚点：{背景名: [x, y]}，0 贴左/上、0.5 居中
  let vm = null;
  const assets = {};
  let L = LAYOUT.layoutFor(window.innerWidth, window.innerHeight);

  // P64：镜头。@camera 在桌面端早就有，手机端之前直接进 unsupported。
  // 语义对齐桌面 runtime：zoom 的终值是持久状态（进存档），pan/shake 是瞬时演出。
  const cam = {
    zoom: 1, zoomFrom: 1, zoomTo: 1, zoomT0: 0, zoomDur: 0,
    panX: 0, panY: 0, panFromX: 0, panFromY: 0, panToX: 0, panToY: 0,
    panT0: 0, panDur: 0,
    shakeUntil: 0, shakeAmp: 0, sx: 0, sy: 0,
  };
  const ZOOM_MS = 620;

  function applyCamera(kind, args) {
    const t = performance.now();
    const a0 = args && args[0];
    const a1 = args && args[1];
    if (kind === "zoom") {
      // 从"当前实际缩放"补间到目标：连续两条 zoom 不会跳变
      cam.zoomFrom = cam.zoom;
      cam.zoomTo = Number(a1) || 1;
      cam.zoomT0 = t;
      cam.zoomDur = ZOOM_MS;
    } else if (kind === "pan") {
      const dir = String(a0 || "");
      const secs = Math.max(0.2, Number(a1) || 1);
      const dist = Math.min(L.viewW, L.viewH) * 0.14;
      let tx = cam.panX;
      let ty = cam.panY;
      if (dir === "左") tx -= dist;
      else if (dir === "右") tx += dist;
      else if (dir === "上") ty -= dist;
      else if (dir === "下") ty += dist;
      cam.panFromX = cam.panX; cam.panFromY = cam.panY;
      cam.panToX = tx; cam.panToY = ty;
      cam.panT0 = t; cam.panDur = secs * 1000;
    } else if (kind === "shake") {
      const secs = Math.max(0.1, Number(a0) || 0.5);
      const amp = Math.abs(Number(a1) || 12);
      cam.shakeUntil = t + secs * 1000;
      cam.shakeAmp = Math.min(amp, Math.min(L.viewW, L.viewH) * 0.12);
    } else if (kind === "reset") {
      const secs = Math.max(0.2, Number(a0) || 0.6);
      cam.zoomFrom = cam.zoom; cam.zoomTo = 1; cam.zoomT0 = t; cam.zoomDur = secs * 1000;
      cam.panFromX = cam.panX; cam.panFromY = cam.panY;
      cam.panToX = 0; cam.panToY = 0; cam.panT0 = t; cam.panDur = secs * 1000;
    }
  }

  function easeInOut(p) {
    return p < 0.5 ? 2 * p * p : 1 - Math.pow(-2 * p + 2, 2) / 2;
  }

  function updateCam(t) {
    if (cam.zoomDur > 0) {
      const p = Math.min(1, (t - cam.zoomT0) / cam.zoomDur);
      cam.zoom = cam.zoomFrom + (cam.zoomTo - cam.zoomFrom) * easeInOut(p);
      if (p >= 1) { cam.zoom = cam.zoomTo; cam.zoomDur = 0; }
    }
    if (cam.panDur > 0) {
      const p = Math.min(1, (t - cam.panT0) / cam.panDur);
      const e = easeInOut(p);
      cam.panX = cam.panFromX + (cam.panToX - cam.panFromX) * e;
      cam.panY = cam.panFromY + (cam.panToY - cam.panFromY) * e;
      if (p >= 1) { cam.panX = cam.panToX; cam.panY = cam.panToY; cam.panDur = 0; }
    }
    cam.sx = 0;
    cam.sy = 0;
    if (t < cam.shakeUntil) {
      const left = (cam.shakeUntil - t) / 1000;
      const decay = Math.min(1, left * 1.6);       // 尾巴渐弱，别戛然而止
      cam.sx = (Math.random() * 2 - 1) * cam.shakeAmp * decay;
      cam.sy = (Math.random() * 2 - 1) * cam.shakeAmp * decay;
    }
  }

  // 平移/抖动会把画面推到画布外，所以底图要按偏移量多铺一点，别露黑边
  function sceneMargin() {
    const offX = (Math.abs(cam.panX) + Math.abs(cam.sx)) * 2 / L.viewW;
    const offY = (Math.abs(cam.panY) + Math.abs(cam.sy)) * 2 / L.viewH;
    const out = Math.max(1 + offX, 1 + offY) * 1.02;
    const z = cam.zoom > 0 ? cam.zoom : 1;
    return out / Math.min(1, z);
  }

  const state = {
    scene: "title",        // title | game | ending
    say: null,
    lines: [],
    fadeFromBg: "",        // P64：背景/CCG 交叉淡入的前一张
    fadeT0: 0,
    fadeDur: 0,
    typeStart: 0,          // 本次打字开始的时间
    typedBefore: 0,        // 转屏前已显示的字数（重排后按比例续上）
    choice: null,
    choiceRects: [],
    bg: "",
    cg: "",                // P63：全屏 CG 名（空 = 没在放）
    sprites: [],
    fg: null,              // P73：@fg 前景贴图
    anim: {},              // P73：@anim 补间（逐参数插值，绘制时才取当前值）
    video: null,           // P73：@video 帧序列背景
    trans: null,           // P73：@transition 待用于下一张背景
    transMode: "dissolve", // 正在播的转场方式
    transDir: "左",
    chapter: null,         // P73：@chapter 章节卡 {title, until}
    waitUntil: 0,
    ended: false,
    continueRect: null,
    error: "",
  };

  // ---------- 画布尺寸 ----------
  function fit() {
    // P84：方向可以手选（设置里「画面方向：自动 / 竖屏 / 横屏」）。
    // 强制横屏时把窗口宽高对调再算布局 —— 布局本身是等比 letterbox（#stage flex 居中），
    // 所以画布会自己变成竖持手机里的一段横屏画面，上下是黑边，跟播放器放横视频一样。
    const force = PREF.orient || "auto";
    let lw = window.innerWidth;
    let lh = window.innerHeight;
    if (force === "landscape" && lw < lh) { const t = lw; lw = lh; lh = t; }
    else if (force === "portrait" && lw > lh) { const t = lw; lw = lh; lh = t; }
    L = LAYOUT.layoutFor(lw, lh);
    applyTextScale();
    // 渲染分辨率：高 DPR 手机（2~3x）按原样画会烧 GPU，弱机直接掉帧。
    // 画质档位乘在 DPR 上，画布逻辑尺寸不变，只是重采样少一点。
    const q = PREF.quality === undefined ? 1 : PREF.quality;
    const dpr = Math.max(0.6, Math.min(3, (window.devicePixelRatio || 1) * q));
    const sw = window.innerWidth;
    const sh = window.innerHeight;
    const scale = Math.min(sw / L.viewW, sh / L.viewH);
    const cssW = Math.max(1, Math.floor(L.viewW * scale));
    const cssH = Math.max(1, Math.floor(L.viewH * scale));
    canvas.style.width = cssW + "px";
    canvas.style.height = cssH + "px";
    canvas.width = Math.floor(cssW * dpr);
    canvas.height = Math.floor(cssH * dpr);
    ctx.setTransform(canvas.width / L.viewW, 0, 0, canvas.height / L.viewH, 0, 0);
    ctx.imageSmoothingQuality = "high";
    rewrap();
  }

  function rewrap() {
    if (!state.say) return;
    const before = typedCount();
    ctx.font = `${L.fs}px ${FACE}`;
    state.lines = wrap(state.say.text || "", L.textW);
    const total = totalChars(state.lines);
    state.typedBefore = Math.min(before, total);
    state.typeStart = performance.now();
    // 让续显从"已显示的位置"接着走，而不是从头再来
    state.typeStart -= (state.typedBefore / cps()) * 1000;
  }

  window.addEventListener("resize", fit);
  window.addEventListener("orientationchange", () => setTimeout(fit, 120));

  // ---------- 视觉参数（读项目 config，缺省回落） ----------
  function cfg(path, dflt) {
    let node = (pack && pack.config) || {};
    for (const key of path.split(".")) {
      if (node && typeof node === "object" && key in node) node = node[key];
      else return dflt;
    }
    return node === undefined ? dflt : node;
  }
  function rgb(arr, dflt) {
    return Array.isArray(arr) && arr.length >= 3
      ? `rgb(${arr[0]},${arr[1]},${arr[2]})`
      : dflt;
  }

  function visual() {
    const dlg = cfg("dialogue.default", {}) || {};
    return {
      surface: rgb(cfg("theme.surface", null), "#14161f"),
      textColor: rgb(cfg("colors.dialog_fg", null), "#f4f6ff"),
      accent: rgb(cfg("theme.primary", null), "#4f8cff"),
      bgAlpha: Math.max(0.62, Math.min(1, (dlg.bg_alpha || 176) / 255 + 0.22)),
      radius: Math.round(Math.max(10, (dlg.radius || 8) * 1.5)),
      panel: {
        image: dlg.panel_image || "",
        slice: dlg.panel_slice === undefined ? 0 : dlg.panel_slice,
        texture: dlg.panel_texture || "",
        texAlpha: Math.max(0, Math.min(1, (dlg.panel_texture_alpha || 0) / 255)),
        alpha: Math.max(0, Math.min(1,
          (dlg.panel_alpha === undefined ? 255 : dlg.panel_alpha) / 255)),
        padY: Math.round(Math.max(0, (dlg.pad_y || 0) * 0.7)),
        padX: Math.round(Math.max(0, (dlg.pad_x || 0) * 0.7)),
      },
    };
  }

  // ---------- 九宫格（与桌面 P53 同一套语义） ----------
  function sliceOf(v) {
    if (Array.isArray(v) && v.length === 4) {
      return v.map((n) => Math.max(0, Math.round(Number(n) || 0)));
    }
    const n = Math.max(0, Math.round(Number(v) || 0));
    return [n, n, n, n];
  }

  function drawNineSlice(img, dx, dy, dw, dh, insets, scale) {
    const sw = img.width;
    const sh = img.height;
    let [l, t, r, b] = insets.map((n) => Math.round(n * scale));
    const capLR = Math.max(0, Math.floor((sw - 1) / 2));
    const capTB = Math.max(0, Math.floor((sh - 1) / 2));
    l = Math.min(l, capLR); r = Math.min(r, capLR);
    t = Math.min(t, capTB); b = Math.min(b, capTB);
    l = Math.min(l, Math.floor((dw - 1) / 2)); r = Math.min(r, Math.floor((dw - 1) / 2));
    t = Math.min(t, Math.floor((dh - 1) / 2)); b = Math.min(b, Math.floor((dh - 1) / 2));
    const sx = [0, l, sw - r, sw];
    const sy = [0, t, sh - b, sh];
    const dxx = [dx, dx + l, dx + dw - r, dx + dw];
    const dyy = [dy, dy + t, dy + dh - b, dy + dh];
    for (let i = 0; i < 3; i++) {
      for (let j = 0; j < 3; j++) {
        const scw = sx[i + 1] - sx[i];
        const sch = sy[j + 1] - sy[j];
        const dcw = dxx[i + 1] - dxx[i];
        const dch = dyy[j + 1] - dyy[j];
        if (scw <= 0 || sch <= 0 || dcw <= 0 || dch <= 0) continue;
        ctx.drawImage(img, sx[i], sy[j], scw, sch, dxx[i], dyy[j], dcw, dch);
      }
    }
  }

  // ---------- 音频（P62） ----------
  // 单文件里音频是 data URI，分目录版是 assets/xxx.ogg，同一个 Audio 构造能吃两种。
  // 浏览器自动播放策略：第一次 @music 一定发生在玩家点过「开始」之后，不会被拦。
  let bgm = null;          // 当前背景音乐（单例，切曲即停旧的）
  let audioOn = true;      // 右上角小喇叭
  let bgmVolume = 1;

  function audioSrc(name) {
    return (pack.audio && pack.audio[name]) || "";
  }

  function fadeTo(audio, to, seconds, done) {
    const from = audio.volume;
    const ms = Math.max(1, (Number(seconds) || 0) * 1000);
    const t0 = performance.now();
    const tick = () => {
      const k = Math.min(1, (performance.now() - t0) / ms);
      audio.volume = Math.max(0, Math.min(1, from + (to - from) * k));
      if (k < 1) requestAnimationFrame(tick);
      else if (done) done();
    };
    requestAnimationFrame(tick);
  }

  function playMusic(track, fadein, fadeout) {
    const src = audioSrc(track);
    if (!src) { console.warn("[MYONL] 找不到音乐：" + track); return; }
    const old = bgm;
    if (old && !old.paused) {
      if (fadeout) {
        fadeTo(old, 0, fadeout, () => { try { old.pause(); } catch (e) {} });
      } else {
        try { old.pause(); } catch (e) {}
      }
    }
    const a = new Audio(src);
    a.loop = true;
    a.volume = fadein ? 0 : bgmVolume;
    if (!audioOn) a.muted = true;
    const p = a.play();
    if (p && p.catch) p.catch(() => { /* 被自动播放拦了就静默，别打断游戏 */ });
    if (fadein) fadeTo(a, bgmVolume, fadein);
    bgm = a;
  }

  function playSfx(name) {
    const src = audioSrc(name);
    if (!src) { console.warn("[MYONL] 找不到音效：" + name); return; }
    const a = new Audio(src);
    a.volume = bgmVolume;
    if (!audioOn) a.muted = true;
    const p = a.play();
    if (p && p.catch) p.catch(() => {});
  }

  // 语音通道（P73）：单独一条，换句时把上一条掐掉，别两句话叠着响
  let voiceAudio = null;
  function stopVoice() {
    if (voiceAudio) {
      try { voiceAudio.pause(); } catch (e) { /* 已结束就算了 */ }
      voiceAudio = null;
    }
  }
  function playVoice(name) {
    stopVoice();
    if (!name) return;
    const src = audioSrc(name);
    if (!src) { console.warn("[MYONL] 找不到语音：" + name); return; }
    const a = new Audio(src);
    a.volume = Math.min(1, bgmVolume + 0.15);   // 语音比 BGM 稍微响一点
    if (!audioOn) a.muted = true;
    const p = a.play();
    if (p && p.catch) p.catch(() => { /* 自动播放被拦就静默 */ });
    voiceAudio = a;
  }

  // 右上角喇叭：尺寸跟 ☰ 同一档（menuBtnSize），两个键才是一个层级
  function muteRect() {
    const s = menuBtnSize();
    const m = Math.round(Math.min(L.viewW, L.viewH) * 0.022);
    return { x: L.viewW - s - m, y: m, w: s, h: s };
  }

  function drawMute() {
    if (state.scene !== "game" || state.error) return;
    const r = muteRect();
    ctx.save();
    ctx.globalAlpha = audioOn ? 0.62 : 0.80;
    roundRect(r.x, r.y, r.w, r.h, r.h / 2, "rgba(12,14,20,.80)");
    ctx.globalAlpha = 1;
    ctx.strokeStyle = "rgba(223,230,245,.18)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.arc(r.x + r.w / 2, r.y + r.h / 2, r.w / 2 - 0.5, 0, Math.PI * 2);
    ctx.stroke();
    ctx.fillStyle = audioOn ? "#dfe6f5" : "#8a91a3";
    ctx.font = `${Math.round(r.h * 0.46)}px sans-serif`;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText("♪", r.x + r.w / 2, r.y + r.h / 2 + 1);
    if (!audioOn) {           // 静音：音符上加一道斜杠（别做成 ×，玩家会以为点了退出）
      ctx.strokeStyle = "#8a91a3";
      ctx.lineWidth = Math.max(2, Math.round(r.h * 0.06));
      ctx.beginPath();
      ctx.moveTo(r.x + r.w * 0.22, r.y + r.h * 0.76);
      ctx.lineTo(r.x + r.w * 0.78, r.y + r.h * 0.24);
      ctx.stroke();
    }
    ctx.restore();
  }

  function toggleMute() {
    audioOn = !audioOn;
    if (bgm) bgm.muted = !audioOn;
  }

  // ---------- 素材 ----------
  function loadAssets() {
    const names = Object.keys(pack.assets || {});
    return new Promise((resolve) => {
      let left = names.length;
      if (!left) return resolve();
      for (const name of names) {
        const img = new Image();
        img.onload = () => { assets[name] = img; if (--left === 0) resolve(); };
        img.onerror = () => { if (--left === 0) resolve(); };
        img.src = pack.assets[name];
      }
    });
  }

  // ---------- 折行（按字符，CJK 友好；拉丁词尽量不劈开） ----------
  function wrap(text, maxW) {
    const out = [];
    for (const para of String(text || "").split("\n")) {
      if (!para) { out.push(""); continue; }
      let line = "";
      let i = 0;
      while (i < para.length) {
        const ch = para[i];
        // 英文/数字连成一个词，避免 mid-word 断行
        const isWord = /[A-Za-z0-9'’]/.test(ch);
        let token = ch;
        if (isWord) {
          let j = i;
          while (j < para.length && /[A-Za-z0-9'’]/.test(para[j])) { j++; }
          token = para.slice(i, j);
        }
        if (line && ctx.measureText(line + token).width > maxW) { out.push(line); line = ""; }
        if (!line && ctx.measureText(token).width > maxW) {
          for (const c of token) {
            if (ctx.measureText(line + c).width > maxW && line) { out.push(line); line = ""; }
            line += c;
          }
        } else {
          line += token;
        }
        i += token.length;
      }
      if (line) out.push(line);
    }
    return out;
  }

  function totalChars(lines) {
    return lines.reduce((n, l) => n + l.length, 0);
  }

  function typedCount() {
    if (!state.say) return 0;
    const total = totalChars(state.lines);
    if (!total) return 0;
    const elapsed = (performance.now() - state.typeStart) / 1000;
    return Math.min(total, Math.max(0, Math.floor(elapsed * cps())));
  }

  // ---------- 事件 ----------
  function applyEvent(ev) {
    if (!ev) return;
    switch (ev.type) {
      case "bg":
        if (state.bg && state.bg !== (ev.image || "")) {
          state.fadeFromBg = state.bg;          // 记下旧背景做交叉淡入
          state.fadeT0 = performance.now();
          const tr = state.trans;
          state.trans = null;                  // 只对紧接着这一张生效
          if (tr && tr.kind === "dissolve") {
            state.fadeDur = Math.max(120, (Number(tr.args[0]) || 0.3) * 1000);
            state.transMode = "dissolve";
          } else if (tr && (tr.kind === "wipe" || tr.kind === "slide")) {
            state.fadeDur = Math.max(120, (Number(tr.args[1]) || 0.3) * 1000);
            state.transMode = tr.kind;
            state.transDir = tr.args[0] || "左";
          } else {
            state.fadeDur = 280;               // 没写 @transition：默认短淡入
            state.transMode = "dissolve";
          }
        }
        state.bg = ev.image || "";
        state.cg = "";          // 切回背景：CG 退场
        state.video = null;     // 视频背景也停（和桌面端 @bg 清 video 一致）
        dropVideoCache();       // 帧图不跟着留：一段 10 秒 24fps 的序列能吃掉上百 MB
        break;
      case "cg":
        state.cg = ev.name || "";
        break;
      case "fg":
        state.fg = ev.fg || null;
        break;
      case "anim":
        state.anim = Object.assign({}, vm.state.anim);
        break;
      case "video":
        state.video = {name: ev.name || "", fps: ev.fps || 24,
                       t0: performance.now()};
        warmVideo();
        break;
      case "camera":
        applyCamera(ev.kind || "", ev.args || []);
        break;
      case "show":
      case "hide": {
        state.sprites = (ev.sprites || []).slice();
        // 进场淡入：角色从 0 透明走到 1，260ms。硬切进场像贴纸啪一下砸上屏幕；
        // 按 char 记时间而不是按「char_表情」——表情差分要立刻换，重新淡入反而闪。
        const at = state.spriteAt || {};
        const seen = {};
        const nowS = performance.now() / 1000;
        state.sprites.forEach((sp) => {
          seen[sp.char] = 1;
          if (!(sp.char in at)) at[sp.char] = nowS;
        });
        for (const c of Object.keys(at)) if (!seen[c]) delete at[c];
        state.spriteAt = at;
        break;
      }
      case "say":
        stopVoice();                                  // 换句就掐掉上一句语音
        state.say = ev;
        // 回顾用的历史：手机上手指一快就点过去了，漏掉的台词必须能翻回来。
        // 只留最近 80 句，够回溯一章，也不让内存跟着剧情线性涨。
        state.history = state.history || [];
        state.history.push({char: ev.char || "", text: ev.text || ""});
        if (state.history.length > 80) state.history.shift();
        ctx.font = `${L.fs}px ${FACE}`;
        state.lines = wrap(ev.text, L.textW);
        state.typeStart = performance.now();
        state.typedBefore = 0;
        break;
      case "voice":
        // @voice 写在台词后面（parser 只允许紧跟台词），执行顺序也是 say → voice
        playVoice(ev.sound || "");
        break;
      case "chapter":
        state.chapter = {title: ev.title || "", t0: performance.now(),
                         dur: Math.max(400, (Number(ev.secs) || 2) * 1000)};
        state.waitUntil = state.chapter.t0 + state.chapter.dur;
        break;
      case "transition":
        // 记下"下一张背景怎么进场"，@bg 时才用得上
        state.trans = {kind: ev.kind || "dissolve",
                       args: (ev.args || []).slice()};
        break;
      case "choice":
        state.choice = ev.options || [];
        break;
      case "wait":
        state.waitUntil = performance.now() + (Number(ev.seconds) || 0) * 1000;
        break;
      case "end":
        state.ended = true;
        state.scene = "ending";
        autoSave();
        break;
      case "music":
        playMusic(ev.track, ev.fadein, ev.fadeout);
        break;
      case "sfx":
        playSfx(ev.sound);
        break;
      default:
        break;
    }
  }

  /* 推进：内核会先吐 bg/show/hide 这类"立即可落"的事件，
   * 播放器必须一路吃到"需要玩家响应"的事件（say/choice/wait/end）才停。 */
  function next() {
    if (!vm) return;
    for (let guard = 0; guard < 200; guard++) {
      const ev = vm.next();
      applyEvent(ev);
      if (!ev) break;
      if (ev.type === "say" || ev.type === "choice" ||
          ev.type === "wait" || ev.type === "end" ||
          ev.type === "chapter") break;   // 章节卡是独立演出，别让台词抢在它前面出来
    }
  }

  /* ---------- 本机存储层（P85）----------
     旧实现：每个存档一个 key，而且 key 里拼了**完整剧本文本**（几 KB）——浏览器里一眼看过去
     全是垃圾键；"设置"和"看过引导"又是另外的裸键；没有版本号、没有迁移、
     写失败还被 catch 吞掉：玩家以为存上了，其实没有。
     现在：一个作品一份记录，读在内存里做，落盘只有 storeFlush 一个出口。 */
  let SAVE = null;                       // 当前作品的存档记录（内存缓存，只读一次盘）

  function hash36(str) {                 // FNV-1a：给 key 用，短且稳定
    let h = 0x811c9dc5;
    for (let i = 0; i < str.length; i++) {
      h ^= str.charCodeAt(i);
      h = (h * 0x01000193) >>> 0;
    }
    return h.toString(36);
  }

  // 作品指纹：标题区分作品，剧本 + 指令数区分"同名换了剧本"。都走短哈希，key 长度恒定
  function storeGid() {
    const t = (pack && pack.title) || "untitled";
    const sc = (pack && pack.script) || "";
    const n = (pack && pack.ins && pack.ins.length) || 0;
    return hash36(t) + "-" + hash36(sc + "|" + n);
  }

  function storeKey() { return "myonl:v2:save:" + storeGid(); }

  function storeRead() {
    if (SAVE) return SAVE;
    SAVE = {v: 2, auto: null, slots: {}};
    try {
      const raw = localStorage.getItem(storeKey());
      if (raw) {
        const d = JSON.parse(raw);
        if (d && typeof d === "object") {
          SAVE = {v: 2, auto: d.auto || null,
                  slots: (d.slots && typeof d.slots === "object") ? d.slots : {}};
        }
      }
    } catch (e) { SAVE = {v: 2, auto: null, slots: {}}; }   // 坏档按空档处理，别让整页崩
    return SAVE;
  }

  function storeFlush() {
    try {
      localStorage.setItem(storeKey(), JSON.stringify(storeRead()));
      UI.storeErr = 0;
      return true;
    } catch (e) {
      UI.storeErr = 1;                   // 满了 / 隐私模式：界面要明说，不能假装存上了
      return false;
    }
  }

  function storeAuto() { const a = storeRead().auto; return (a && a.s) ? a : null; }

  function storeSetAuto(str) {
    const d = storeRead();
    d.auto = str ? {s: str, t: Date.now(), say: previewLine(), bg: state.bg || ""} : null;
    storeFlush();
  }

  function storeSlot(i) {
    const d = storeRead().slots[i];
    return (d && d.s) ? d : null;
  }

  function storeSetSlot(i, data) {
    const d = storeRead();
    if (data) d.slots[i] = data; else delete d.slots[i];
    storeFlush();
  }

  function storeWipe() {
    const d = storeRead();
    d.auto = null;
    d.slots = {};
    storeFlush();
    UI.wipeConfirm = 0;
    UI.wipeDone = performance.now();
  }

  /* ---- 存档带走 / 带回 -------------------------------------------------------
     手机端存档在 localStorage，而 localStorage **按 origin 隔离**：把 HTML 换个文件名、
     换个目录、或者从浏览器打开改成用文件管理器打开，就是另一个 origin —— 旧存档看不见了。
     这堵墙拆不了（浏览器安全模型），能做的是给玩家一条稳的后备路：
     导出成一个文件，换到新位置后再从文件导回来。桌面端不用这套（那边数据在 AppData）。*/

  function b64encode(str) {
    const bytes = new TextEncoder().encode(str);
    let bin = "";
    for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
    return btoa(bin);
  }

  function b64decode(str) {
    const bin = atob(String(str).replace(/\s+/g, ""));
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return new TextDecoder().decode(bytes);
  }

  /* 把本机所有 MYONL 键（各作品的档 + 设置）打包成一段码：换设备/换路径后一条不落 */
  function storeExportCode() {
    const data = {};
    let n = 0;
    try {
      for (let i = 0; i < localStorage.length; i++) {
        const k = localStorage.key(i);
        if (!k || k.indexOf("myonl:") !== 0) continue;
        const v = localStorage.getItem(k);
        if (v === null) continue;
        data[k] = v;
        n++;
      }
    } catch (e) { return ""; }
    if (!n) return "";
    return "MYONL1:" + b64encode(JSON.stringify({app: "MYONL", v: 1, at: Date.now(), data: data}));
  }

  function storeImportCode(raw) {
    let code = String(raw || "").trim();
    if (!code) return {ok: false, msg: "文件是空的"};
    if (code.indexOf("MYONL1:") >= 0) code = code.slice(code.indexOf("MYONL1:") + 7);
    let obj = null;
    try { obj = JSON.parse(b64decode(code)); } catch (e) { return {ok: false, msg: "内容不完整或不是存档文件"}; }
    if (!obj || obj.v !== 1 || !obj.data || typeof obj.data !== "object") {
      return {ok: false, msg: "不是 MYONL 的存档文件"};
    }
    const keys = Object.keys(obj.data);
    if (!keys.length) return {ok: false, msg: "这份存档是空的"};
    let n = 0;
    keys.forEach((k) => {
      if (k.indexOf("myonl:") !== 0) return;       // 只认自家键，别的什么都不碰
      try { localStorage.setItem(k, String(obj.data[k])); n++; } catch (e) {}
    });
    return {ok: true, n: n};
  }

  function storeExportFile(code) {
    try {
      const blob = new Blob([code], {type: "text/plain;charset=utf-8"});
      const a = document.createElement("a");
      const d = new Date();
      const p2 = (x) => (x < 10 ? "0" : "") + x;
      a.href = URL.createObjectURL(blob);
      a.download = "MYONL存档-" + d.getFullYear() + p2(d.getMonth() + 1) + p2(d.getDate())
                   + "-" + p2(d.getHours()) + p2(d.getMinutes()) + ".txt";
      document.body.appendChild(a);
      a.click();
      setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
      return true;
    } catch (e) { return false; }
  }

  /* 导入：走系统文件选择器（手机上下载目录里选那个 .txt），比让人手打一串码现实 */
  function storeImportFile() {
    const inp = document.createElement("input");
    inp.type = "file";
    inp.accept = ".txt,text/plain,.json,application/json";
    inp.style.position = "fixed";
    inp.style.left = "-9999px";
    document.body.appendChild(inp);
    inp.addEventListener("change", () => {
      const f = inp.files && inp.files[0];
      if (!f) { inp.remove(); return; }
      const fr = new FileReader();
      fr.onload = () => { inp.remove(); applyImport(String(fr.result || "")); };
      fr.onerror = () => { inp.remove(); notice("这个文件读不出来", false); };
      fr.readAsText(f);
    });
    inp.click();
  }

  function applyImport(raw) {
    const r = storeImportCode(raw);
    if (!r.ok) { notice("导入失败：" + r.msg, false); return; }
    if (!confirm("导入会覆盖本机已有的 MYONL 进度（共 " + r.n + " 项）。继续？")) return;
    notice("已导入 " + r.n + " 项，正在刷新…", true);
    setTimeout(() => { location.reload(); }, 500);
  }

  /* 面板里的一行结果：绿=成、红=败，4 秒后自己消失（不弹窗打断） */
  function notice(text, ok) {
    UI.notice = text;
    UI.noticeOk = !!ok;
    UI.noticeAt = performance.now();
    UI.t0 = performance.now();
  }

  /* 迁移：旧版散装键搬进来再删掉。只搬本作品 —— 别的作品下次打开时自己搬，
     不去扫全库，免得把别人的档拽进当前作品。 */
  function storeMigrate() {
    const t = (pack && pack.title) || "untitled";
    const sc = (pack && pack.script) || "";
    const n = (pack && pack.ins && pack.ins.length) || 0;
    const d = storeRead();
    let moved = 0;
    try {
      const oldAuto = "myonl:auto:" + t + ":" + sc + ":" + n;
      const rawAuto = localStorage.getItem(oldAuto);
      if (rawAuto) {
        if (!d.auto) { d.auto = {s: rawAuto, t: Date.now(), say: "", bg: ""}; moved++; }
        localStorage.removeItem(oldAuto);
      }
      const base = "myonl:slot:" + t + ":" + sc + ":";
      for (let i = 0; i < slotCount(); i++) {
        const raw = localStorage.getItem(base + i);
        if (!raw) continue;
        if (!d.slots[i]) {
          try {
            const v = JSON.parse(raw);
            if (v && v.s) { d.slots[i] = v; moved++; }
          } catch (e) { /* 单个坏档跳过，别的照搬 */ }
        }
        localStorage.removeItem(base + i);
      }
      if (moved) storeFlush();
    } catch (e) { /* 迁移失败不挡游戏：最坏也就是从零开始 */ }
    return moved;
  }

  function autoSave() { storeSetAuto(vm ? vm.save() : null); }

  function startGame(fromSave) {
    state.panelHc = 0;      // 重开/读档：面板高度重新算，别带着上一局的高度
    state.scene = "game";
    state.ended = false;
    state.choice = null;
    state.choiceRects = [];
    state.waitUntil = 0;
    state.bg = "";
    state.cg = "";
    state.sprites = [];
    state.history = [];
    // 首次进游戏的一次性说明（本机记一次，之后不再弹）
    state.guide = !helpSeen;
    state.guideT0 = performance.now();
    cam.zoom = 1; cam.zoomDur = 0; cam.zoomTo = 1; cam.zoomFrom = 1;
    cam.panX = 0; cam.panY = 0; cam.panDur = 0;
    cam.shakeUntil = 0;
    if (fromSave) {
      const a = storeAuto();
      if (a) vm.load(a.s);
    } else {
      vm.restart();
      storeSetAuto(null);        // 新开局清掉自动档，免得"继续游戏"跳回上一局
    }
    // 读档后补一次"当前画面"：让 bg/立绘/CG/镜头/前景先对上，再继续推进
    state.bg = vm.state.bg || "";
    state.cg = vm.state.cg || "";
    state.sprites = (vm.state.sprites || []).slice();
    state.fg = vm.state.fg || null;
    state.anim = vm.state.anim || {};
    state.video = vm.state.video ? Object.assign({}, vm.state.video) : null;
    if (state.video) { state.video.t0 = performance.now(); warmVideo(); }
    const zoom = Number(vm.state.cameraZoom) || 1;
    if (zoom !== cam.zoom && zoom !== 1) {
      cam.zoomFrom = cam.zoom; cam.zoomTo = zoom;
      cam.zoomT0 = performance.now(); cam.zoomDur = ZOOM_MS;
    }
    // P62：音乐也要续上（存档只记名字，不记播放进度——重头放，玩家基本感知不到）
    if (fromSave && vm.state.music) playMusic(vm.state.music, 0, 0);
    next();
  }

  // ---------- 输入 ----------
  function point(e) {
    const box = canvas.getBoundingClientRect();
    return {
      x: ((e.clientX - box.left) / box.width) * L.viewW,
      y: ((e.clientY - box.top) / box.height) * L.viewH,
    };
  }

  function inRect(p, r) {
    return r && p.x >= r.x && p.x <= r.x + r.w && p.y >= r.y && p.y <= r.y + r.h;
  }

  // P65：手机上「竖屏必须全屏」。点「开始」这一下是用户手势，浏览器允许进全屏；
  // 进了全屏浏览器工具栏/地址栏才消失，画面才是整块屏幕（真机上工具栏吃掉 250px）。
  let fsAsked = false;
  function tryFullscreen() {
    if (fsAsked) return;
    fsAsked = true;
    const el = document.documentElement;
    const req = el.requestFullscreen || el.webkitRequestFullscreen || el.msRequestFullscreen;
    if (!req) return;   // 桌面浏览器/被禁用时不弹窗，静默跳过
    try {
      const p = req.call(el);
      if (p && p.catch) p.catch(() => {});
    } catch (e) { /* 全屏不是必需能力，失败就算了 */ }
  }

  function onTap(e) {
    e.preventDefault();
    if (state.error) return;
    // 引导页：这一下只关引导，不推进剧情（否则第一次点就直接跳过一句话）
    if (state.guide) {
      state.guide = false;
      markHelpSeen();
      return;
    }
    const p = point(e);

    if (UI.open) return onMenuTap(p);
    // 章节卡 / @wait 期间不响应翻页（这是演出节奏，不是玩家该跳过的）
    if (state.waitUntil > performance.now()) return;
    // 菜单键在喇叭左边：点它开菜单，不翻页
    if (state.scene === "game" && inRect(p, menuRect())) return openMenu();

    // 喇叭优先：点它只静音，不翻页
    if (state.scene === "game" && inRect(p, muteRect())) return toggleMute();

    // 右侧竖列：存档/回顾/设置直接开面板，不必先进菜单
    const oi = orbitHit(p);
    if (oi) return openPanel(oi);

    if (state.scene === "title") {
      tryFullscreen();
      if (state.continueRect && inRect(p, state.continueRect)) return startGame(true);
      return startGame(false);
    }
    if (state.scene === "ending") { state.scene = "title"; return; }
    if (state.ended) { state.scene = "ending"; return; }

    if (state.choice) {
      for (const r of state.choiceRects) {
        if (inRect(p, r)) {
          const chosen = vm.choose(r.idx);
          state.choice = null;
          state.choiceRects = [];
          if (chosen && chosen.type === "chosen") next();
          break;
        }
      }
      return;
    }

    // 打字机未完 → 一次全显（玩家不想等）
    if (typedCount() < totalChars(state.lines)) {
      state.typeStart = performance.now() - (totalChars(state.lines) / cps()) * 1000;
      return;
    }
    if (state.waitUntil && performance.now() < state.waitUntil) return;
    autoSave();
    next();
  }

  // P58：点击/触摸改成「按下 → 抬起时判断」。
  // 原来 pointerdown 就推进，手指一滑（想拖动画面或误触）也会翻页；
  // 现在位移 >12px 或按住 >1.2s 不算点击，判定为滑动/长按。
  let tapStart = null;
  canvas.addEventListener("pointerdown", (e) => {
    tapStart = {x: e.clientX, y: e.clientY, t: performance.now(), id: e.pointerId};
  });
  canvas.addEventListener("pointerup", (e) => {
    if (!tapStart || tapStart.id !== e.pointerId) return;
    const moved = Math.hypot(e.clientX - tapStart.x, e.clientY - tapStart.y);
    const dur = performance.now() - tapStart.t;
    tapStart = null;
    if (moved > 12) return;
    // 长按（600ms~1.6s）打开菜单：手机上没有右键，长按是最自然的"叫出菜单"
    if (dur >= 600 && dur <= 1600 && state.scene === "game" && !UI.open && !state.guide) {
      openMenu();
      return;
    }
    if (dur > 1600) return;
    onTap(e);
  });
  canvas.addEventListener("pointercancel", () => { tapStart = null; });
  document.addEventListener("keydown", (e) => {
    if (e.key === " " || e.key === "Enter" || e.key === "ArrowRight") onTap(e);
  });

  // ---------- 绘制 ----------
  // 竖屏优先用竖版构图（images/{名}_p.png），没有就回退主图
  function pickBgName(name) {
    if (!name) return "";
    if (!L.landscape && assets[name + "_p"]) return name + "_p";
    return name;
  }

  // 带锚点的 cover。锚点 = 裁切窗口在「可移动范围」里的位置：
  // 0 贴左/上，0.5 居中，1 贴右/下。16:9 的图铺到 9:16 的屏上，
  // 居中裁掉的是两边各三成，人脸常常被切 —— 给一个锚点就不用改图。
  function blitNamed(name, alpha) {
    const key = pickBgName(name);
    const img = assets[key] || assets[name];
    if (!img) return false;
    const f = FOCAL[name] || FOCAL[key];
    const m = sceneMargin();
    const scale = Math.max(L.viewW / img.width, L.viewH / img.height) * m;
    const dw = img.width * scale;
    const dh = img.height * scale;
    const fx = f ? f[0] : 0.5;
    const fy = f ? f[1] : 0.5;
    const dx = (L.viewW - dw) * fx;
    const dy = (L.viewH - dh) * fy;
    if (alpha !== undefined && alpha < 1) {
      ctx.save();
      ctx.globalAlpha = Math.max(0, alpha);
      ctx.drawImage(img, dx, dy, dw, dh);
      ctx.restore();
    } else {
      ctx.drawImage(img, dx, dy, dw, dh);
    }
    return true;
  }

  function blitCover(img, alpha) {
    const m = sceneMargin();
    const scale = Math.max(L.viewW / img.width, L.viewH / img.height) * m;
    const dw = img.width * scale;
    const dh = img.height * scale;
    if (alpha !== undefined && alpha < 1) {
      ctx.save();
      ctx.globalAlpha = Math.max(0, alpha);
      ctx.drawImage(img, (L.viewW - dw) / 2, (L.viewH - dh) / 2, dw, dh);
      ctx.restore();
    } else {
      ctx.drawImage(img, (L.viewW - dw) / 2, (L.viewH - dh) / 2, dw, dh);
    }
  }

  // ---------- 帧序列背景（P73）----------
  // @video 名 fps= → images/videos/名_001.png 起连续编号，按 fps 循环播。
  //
  // P100（手机/平板）：帧图不能全留。一帧手机分辨率（1080×1920）解码后 8 MB 出头，
  // 10 秒 24fps 就是 240 帧 —— 循环走完第一轮就吃掉 2 GB，手机上直接白屏。
  // 所以只留「最近用过的 N 帧」（N 覆盖约半秒，够回头兜底），超出就丢掉引用交给 GC。
  const VIDEO_KEEP = 14;
  const videoCache = {};        // key → Image
  const videoKeys = [];         // 最近使用的 key，越靠后越新
  let videoCachedFor = "";      // 当前缓的是哪个视频（换视频就清空）

  function dropVideoCache() {
    for (const k of Object.keys(videoCache)) delete videoCache[k];
    videoKeys.length = 0;
    videoCachedFor = "";
  }

  function touchVideo(key, img) {
    videoCache[key] = img;
    const i = videoKeys.indexOf(key);
    if (i >= 0) videoKeys.splice(i, 1);
    videoKeys.push(key);
    while (videoKeys.length > VIDEO_KEEP) delete videoCache[videoKeys.shift()];
  }

  function videoSeq() {
    const v = state.video;
    if (!v || !v.name) return null;
    const seq = (pack && pack.videos && pack.videos[v.name]) || null;
    return (seq && seq.length) ? seq : null;
  }

  function videoLoad(name, i) {
    const seq = videoSeq();
    if (!seq) return;
    const key = name + "#" + i;
    if (videoCache[key]) return;
    const img = new Image();
    img.src = seq[i];
    touchVideo(key, img);
  }

  // 进 @video 先把头几帧叫醒：不然第一帧还在读，画面黑一下才出来。
  function warmVideo() {
    const seq = videoSeq();
    if (!seq) { dropVideoCache(); return; }
    if (videoCachedFor !== state.video.name) {
      dropVideoCache();
      videoCachedFor = state.video.name;
    }
    const n = Math.min(3, seq.length);
    for (let i = 0; i < n; i++) videoLoad(state.video.name, i);
  }

  function videoFrameImg() {
    const seq = videoSeq();
    if (!seq) return null;
    const v = state.video;
    const fps = v.fps > 0 ? v.fps : 24;
    const len = seq.length;
    const raw = Math.floor(((performance.now() - (v.t0 || 0)) / 1000) * fps);
    const idx = ((raw % len) + len) % len;
    videoLoad(v.name, idx);
    videoLoad(v.name, (idx + 1) % len);      // 顺手叫下一帧，帧率才跟得上
    const img = videoCache[v.name + "#" + idx];
    if (img && img.complete && img.naturalWidth) return img;
    // 还没读出来就把能用的最近一帧贴上，别黑
    for (let d = 1; d < Math.min(len, VIDEO_KEEP); d++) {
      const prev = videoCache[v.name + "#" + ((idx - d + len) % len)];
      if (prev && prev.complete && prev.naturalWidth) return prev;
    }
    return null;
  }

  function drawBackground() {
    // @video 帧序列在的话，它先顶上背景位置（静态 bg 被它盖住，和桌面端一致）
    if (state.video) {
      const frameImg = videoFrameImg();
      if (frameImg) { blitCover(frameImg, 1); return; }
    }
    // 交叉淡入：旧背景先铺满，新背景按进度盖上去 —— 硬切太生硬
    let t = 1;
    if (state.fadeDur > 0) {
      t = Math.min(1, (performance.now() - state.fadeT0) / state.fadeDur);
      if (t >= 1) { state.fadeDur = 0; state.fadeFromBg = ""; }
    }
    const prevName = state.fadeFromBg;
    const bgName = state.bg;
    const hasBg = !!(bgName && (assets[bgName] || assets[bgName + "_p"]));
    if (prevName && t < 1) blitNamed(prevName, 1);
    if (hasBg) {
      // @transition wipe / slide：新图按方向推进来；dissolve 就是普通淡入
      const mode = state.transMode || "dissolve";
      if (prevName && t < 1 && mode !== "dissolve") {
        ctx.save();
        ctx.beginPath();
        const dir = state.transDir || "左";
        if (dir === "左" || dir === "右") {
          const w = L.viewW * t;
          ctx.rect(dir === "左" ? 0 : L.viewW - w, 0, w, L.viewH);
        } else {
          const h = L.viewH * t;
          ctx.rect(0, dir === "上" ? 0 : L.viewH - h, L.viewW, h);
        }
        ctx.clip();
        blitNamed(bgName, 1);
        ctx.restore();
      } else {
        blitNamed(bgName, prevName && t < 1 ? t : 1);
      }
      return;
    }
    const g = ctx.createLinearGradient(0, 0, 0, L.viewH);
    g.addColorStop(0, "#1a1d2b");
    g.addColorStop(1, "#0b0d14");
    ctx.save();
    ctx.globalAlpha = prevName ? t : 1;
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, L.viewW, L.viewH);
    ctx.restore();
  }

  // @anim 的当前显示值：逐参数补间取进度。@anim 的 x/y 是「1280 宽基准的像素」，
  // 和桌面端同一套数字，所以这里除缩放系数后面统一换算。
  function animDisp(char) {
    const out = {x: 0, y: 0, alpha: 1, scale: 1};
    const rec = state.anim && state.anim[char];
    if (!rec) return out;
    const now = performance.now();
    for (const p in rec) {
      if (!(p in out)) continue;
      const a = rec[p];
      const k = a.secs > 0 ? Math.max(0, Math.min(1, (now - a.t0) / (a.secs * 1000))) : 1;
      out[p] = a.from + (a.to - a.from) * k;
    }
    return out;
  }

  // P74：立绘的常驻微动（呼吸 + 微摆）。
  // 静态 PNG 贴在屏幕上就是「一张画」；真正让角色像活着的是几处几百分点的小动作：
  // 纵向轻轻一起一伏（呼吸）、以脚底为轴极小幅度地晃（重心）。这两个都在 ±1% 量级，
  // 不抢演出——@anim 的位移/缩放叠在它上面，不受影响。
  // 相位按槽位错开，两个角色不会像机器人一样同步。
  function idleMotion(i, t) {
    const ph = i * 1.9;
    const breath = Math.sin(t * 1.05 + ph) * 0.011;   // ±1.1% 纵向
    const sway = Math.sin(t * 0.58 + ph) * 0.009;     // ±0.9%（0.15° 级）
    return { breath, sway };
  }

  // P98：谁在说话，谁亮。
  // 两个人同屏时两张立绘一样亮，玩家得先读对话框上那两个字才知道谁在开口 ——
  // 这是 galgame 最基本的一条表达，之前完全没有。非发言方退到 0.72，
  // 人自然"退后一步"，明暗就替名字把话说完了。
  // 单人场景不动（场上只有一个人时他永远该是亮的）；切换用 120ms 指数补间，
  // 不是"啪"一下跳档。数值放模块级而不是 state：state 会进存档，不该混进表现层。
  const DIMV = {};
  const DIMT = {};
  function spriteDim(char, target, now) {
    if (!char) return 1;
    const cur = DIMV[char] === undefined ? target : DIMV[char];
    const dt = DIMT[char] ? Math.min(0.3, now - DIMT[char]) : 0;
    DIMT[char] = now;
    const v = cur + (target - cur) * (1 - Math.exp(-dt / 0.12));
    DIMV[char] = Math.abs(target - v) < 0.008 ? target : v;
    return DIMV[char];
  }

  function drawSprites() {
    const list = state.sprites || [];
    if (!list.length) return;
    const n = list.length;
    const baseH = L.spriteH;
    // 竖屏的人要"从头顶到鞋"全露在面板之上：可用高度按「当前」面板现算。
    // 面板是按台词行数收放的（并做了补间），所以一句短台词时人会自动站大一点，
    // 长句把面板顶高又自动收回去 —— 全程连续，不会跳。
    const liveH = L.landscape ? baseH : Math.min(baseH, panelTopY() - 6);
    const k = L.viewW / 1280;   // 剧本里的像素值以桌面 1280 为基准
    const nowT = performance.now() / 1000;
    list.forEach((sp, i) => {
      const key = sp.expr ? `${sp.char}_${sp.expr}` : sp.char;
      const img = assets[key] || assets[sp.char];
      if (!img) return;
      const disp = animDisp(sp.char);
      const h = liveH * (disp.scale > 0 ? disp.scale : 1) * (L.landscape ? 1 : 0.95);
      // 竖长的全身立绘整张塞进横屏，只剩中间细长一条，人小得像贴纸。
      // 横屏就按 galgame 的常态构图：只画上 62%（头顶到膝），按屏高放大，膝盖以下让对话框压住。
      // 阈值原来写 2.2，是按 368×1400（比例 3.8）那种细长图定的；苏晴这张 872×1915
      // 比例 2.198，刚好卡在边界外 → 不走半身裁切，整人塞进 92% 屏高，看着像站远处。
      // 1.5 覆盖所有竖构图立绘（正常立绘宽高比都 > 1.5）。
      const tall = L.landscape && img.height > img.width * 1.5;
      const srcH = tall ? Math.round(img.height * 0.62) : img.height;
      const w = img.width * (h / srcH);
      const slotW = L.viewW / n;
      // 横屏单人时人物偏右三分之二处：左边留白给画面，对话框在底部压住腰——
      // 完整居中的话，两侧空得对称又无聊，人贴在正中像证件照。
      // 竖屏两人同屏收到 0.30 / 0.70（三人 0.30/0.50/0.70）：
      // 0.25/0.75 是等分画布，碰到宽一点的立绘（苏晴 872×1915 那种）左边缘顶出屏幕，
      // 半个手肘和头发被裁掉，看着像图放歪了。横屏仍按槽位等分。
      const cx = (L.landscape && n === 1)
        ? L.viewW * 0.63 + disp.x * k
        : (L.landscape
            ? slotW * (i + 0.5) + disp.x * k
            : L.viewW * (n >= 2 ? 0.30 + 0.40 * (i / Math.max(1, n - 1)) : 0.5) + disp.x * k);
      // 脚底锚点：竖屏让脚沉进去小半截（panelH 的 9%）——脚贴在面板上沿时，
      // 下面还有一大片地板，看着像浮在半空；让面板压住鞋尖，人才像站在前景。
      // 脚底锚在「当前」面板上沿（面板高度是补间的，不能用布局里那个定值）
      const bottom = (L.landscape
        ? L.viewH
        : panelTopY() + Math.round(panelHNow() * 0.09)) + disp.y * k;
      const t0 = (state.spriteAt && state.spriteAt[sp.char]) || 0;
      const fadeIn = t0 ? Math.min(1, (nowT - t0) / 0.26) : 1;
      if (fadeIn <= 0) return;
      const speaker = state.say && state.say.char;
      // 只有"说话的人自己也在场上"才压别人。旁白、或主角（没有立绘）说话时，
      // 场上所有立绘都保持原亮度 —— 否则每句内心独白都让两个人一起变暗，画面在闪。
      const speakerOnStage = !!(speaker && list.some((x) => x.char === speaker));
      const dimTo = (speakerOnStage && n >= 2 && sp.char && sp.char !== speaker) ? 0.72 : 1;
      const dimV = spriteDim(sp.char, dimTo, nowT);
      const alpha = Math.max(0, Math.min(1, disp.alpha)) * fadeIn;
      if (alpha <= 0) return;
      const idle = idleMotion(i, nowT);
      ctx.save();
      if (alpha < 1) ctx.globalAlpha = alpha;
      // 压暗用亮度而不是透明度：半透明的苏晴会透出背后的栏杆，成了"幽灵"。
      // brightness 只降她的亮度、仍不透明，才读得出"退后一步"。老设备不支持 filter 时退回 alpha。
      if (dimV < 0.999) {
        if (typeof ctx.filter === "string") {
          ctx.filter = "brightness(" + dimV.toFixed(3) + ") saturate(" +
                       (0.80 + 0.20 * dimV).toFixed(3) + ")";
        } else {
          ctx.globalAlpha = alpha * dimV;
        }
      }
      // 以脚底中心为锚：先落点，再微摆，再呼吸缩放——顺序决定缩放不会把脚抬离地面
      ctx.translate(cx, bottom);
      ctx.rotate(idle.sway);
      ctx.scale(1 - idle.breath * 0.55, 1 + idle.breath);
      ctx.drawImage(img, 0, 0, img.width, srcH, -w / 2, -h, w, h);
      ctx.restore();
    });
  }

  // ---------- 前景贴图（P73）----------
  // @fg 是压在场景最上的一层（桌面端在立绘/CG 之上、UI 之下），常用于雨雪、光效、
  // 蒙版这类整屏 PNG。x/y 同样是 1280 基准像素；alpha 是整层透明度。
  // 竖屏下不能像桌面 720p 那样原样贴（1280×720 按宽缩到手机宽只剩顶上一小条），
  // 所以这里 cover 铺满再居中裁，x/y 仍按 1280 基准当偏移用。
  function drawFg() {
    const fg = state.fg;
    if (!fg || !fg.name) return;
    const img = assets[fg.name];
    if (!img) return;
    const k = L.viewW / 1280;
    const a = Math.max(0, Math.min(1, fg.alpha === undefined ? 1 : fg.alpha));
    if (a <= 0) return;
    const s = Math.max(L.viewW / img.width, L.viewH / img.height);
    const w = img.width * s;
    const h = img.height * s;
    if (a < 1) ctx.globalAlpha = a;
    ctx.drawImage(img, (L.viewW - w) / 2 + (fg.x || 0) * k,
                  (L.viewH - h) / 2 + (fg.y || 0) * k, w, h);
    if (a < 1) ctx.globalAlpha = 1;
  }

  // ---------- CG（P63）----------
  // @cg 是"全屏一张大图"的演出，桌面端一直有，手机端之前是空白。
  // 语义与桌面端一致：@cg 上图 → 一直盖着（盖住背景和立绘）→ 直到下一条 @bg 才退场。
  function drawCg() {
    if (!state.cg) return;
    const img = assets[state.cg];
    if (!img) {
      ctx.fillStyle = "#191c26";
      ctx.fillRect(0, 0, L.viewW, L.viewH);
      ctx.fillStyle = "#7f8798";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.font = `400 ${Math.round(Math.min(L.viewW, L.viewH) * 0.036)}px ${FACE}`;
      ctx.fillText("CG 素材缺失：" + state.cg, L.viewW / 2, L.viewH / 2);
      return;
    }
    blitCover(img, 1);
  }

  function pathRound(x, y, w, h, r) {
    const rr = Math.min(r, w / 2, h / 2);
    ctx.beginPath();
    ctx.moveTo(x + rr, y);
    ctx.arcTo(x + w, y, x + w, y + h, rr);
    ctx.arcTo(x + w, y + h, x, y + h, rr);
    ctx.arcTo(x, y + h, x, y, rr);
    ctx.arcTo(x, y, x + w, y, rr);
    ctx.closePath();
  }

  function roundRect(x, y, w, h, r, fill, alpha) {
    ctx.save();
    if (alpha !== undefined) ctx.globalAlpha = alpha;
    pathRound(x, y, w, h, r);
    if (fill) { ctx.fillStyle = fill; ctx.fill(); }
    ctx.restore();
  }

  // 按当前 ctx.font 把一行字收进 avail 宽：放得下原样返回，放不下就砍到能放并补「…」。
  // 存档格、选项这类"宽度跟着列数变"的文字都该走它，别再 hard slice 字数。
  function ellipsisTo(s, avail) {
    if (avail <= 0) return "";
    if (ctx.measureText(s).width <= avail) return s;
    let n = s.length;
    while (n > 1 && ctx.measureText(s.slice(0, n) + "…").width > avail) n--;
    return s.slice(0, n) + "…";
  }

  /* 面板高度：跟这一句的实际行数走，逐帧补间过渡。
     以前竖屏钉死 1/3 屏：一句两行的话，面板下半截就是一整块空黑，像没填完的表格；
     横屏更难看 —— 一行字顶着一块 280 高的板子。
     P97 又把兜底压了一档：原来不管几句都留 3.5 行（849 高屏上就是 19% 屏高），
     一句话的面板上下各空一大块 —— 那句"再矮会显得话被截断"其实是眼感，不是度量：
     留 1.9 行已经够呼吸。 */
  function panelTargetH() {
    const rows = Math.max(1, Math.min(L.maxTextRows, (state.lines || []).length || 1));
    const nameH = state.say && state.say.char ? Math.round(L.nameSize * 0.9) : 0;
    const contentH = L.padY * 2 + rows * L.lineH + nameH + Math.round(L.fs * 0.6);
    // P101：原来竖屏硬性留 rows + 0.9 行 —— 一句单行台词也撑出将近三行高的面板，
    // 底下那一整块是空的，等于白占了画面。行数是本句已经折好的行数，不会在打字过程中变，
    // 所以高度按实际行数给，只在"至少几行"上留一点呼吸。
    const minRows = L.landscape ? Math.max(1, rows) : Math.max(1.4, rows);
    const minH = L.padY * 2 + L.lineH * minRows + nameH + L.fs * (L.landscape ? 0.45 : 0.6);
    const maxH = L.viewH * (L.landscape ? 0.52 : 0.46);
    return Math.round(Math.max(minH, Math.min(maxH, contentH)));
  }

  function updatePanelH(now) {
    const target = panelTargetH();
    if (!state.panelHc) { state.panelHc = target; state.panelT = now; return; }
    const dt = Math.min(80, Math.max(1, now - (state.panelT || now)));
    state.panelT = now;
    state.panelHc += (target - state.panelHc) * (1 - Math.exp(-dt / 90));
    if (Math.abs(target - state.panelHc) < 1) state.panelHc = target;
  }

  function panelHNow() {
    return Math.round(state.panelHc || L.panelH);
  }

  function panelTopY() {
    return L.viewH - panelHNow() - L.bottom;
  }

  // P101：对话框不再是"贴满左右、压到全黑的一张纸"。
  //
  // 原来面板顶到屏幕左右边、最底 0.97 不透明度 —— 画面最下面那一条被彻底盖掉，
  // 立绘的鞋和地板全部消失，看着像"图被切了一块再贴张黑纸"。
  // 现在三档可切（设置里「对话框」）：
  //   0 经典   贴边、底厚 —— 想读得稳的人用
  //   1 悬浮   左右内缩、上缘全透、底 0.80 —— 画面从面板里透出来（默认）
  //   2 极简   只留文字和一层很薄的压暗，不铺底 —— 想看图的人用
  function dlgStyle() {
    const s = Number(PREF.dlg);
    return Number.isFinite(s) ? Math.max(0, Math.min(2, Math.trunc(s))) : 1;
  }

  function panelRect() {
    const rows = Math.max(1, Math.min(L.maxTextRows, (state.lines || []).length || 1));
    const h = panelHNow();
    const st = dlgStyle();
    // 内缩按屏幕宽算（不是按字号），手机上约 9 CSS px，平板约 19 CSS px
    const inset = st === 0 ? 0 : Math.round(L.viewW * (L.landscape ? 0.013 : 0.024));
    return {x: L.panelX + inset, y: L.viewH - h - L.bottom,
            w: L.panelW - inset * 2, h: h, rows: rows, style: st};
  }

  /* 「#rrggbb + 透明度」：角色色要能当半透明底/描边用 */
  function hexA(hex, alpha) {
    const m = /^#?([0-9a-f]{6})$/i.exec(String(hex || "").trim());
    if (!m) return "rgba(79,140,255," + alpha + ")";
    const v = parseInt(m[1], 16);
    return "rgba(" + ((v >> 16) & 255) + "," + ((v >> 8) & 255) + "," + (v & 255) + "," + alpha + ")";
  }

  /* 面板底色（只给经典档用）：原来是一块死黑（rgba(10,12,18,.90)）压在背景上，边缘像贴了张黑纸。
     P97：上缘化开、往下才压实 —— 顶上不会留一条亮带。
     P101：1/2 两档根本不走矩形（drawPanel 里铺全宽渐变），底只有经典档需要，所以这里不再分档。 */
  function panelFill(x, y, w, h) {
    const g = ctx.createLinearGradient(0, y, 0, y + h);
    g.addColorStop(0, "rgba(14,17,26,0)");
    g.addColorStop(0.08, "rgba(12,15,23,.86)");
    g.addColorStop(1, "rgba(7,9,14,.90)");
    return g;
  }

  /* 上缘那道线不许等亮度：等亮度就是一条白描边，看着像网页卡片。
     中间亮、两头收进去，才像光落在边上。 */
  function panelHairline(x, y, w, r, alpha) {
    const a1 = typeof alpha === "number" ? alpha : 0.13;
    ctx.save();
    const g = ctx.createLinearGradient(x + r, 0, x + w - r, 0);
    g.addColorStop(0, "rgba(255,255,255,0)");
    g.addColorStop(0.5, "rgba(255,255,255," + a1 + ")");
    g.addColorStop(1, "rgba(255,255,255,0)");
    ctx.strokeStyle = g;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(x + r, y + 0.5);
    ctx.lineTo(x + w - r, y + 0.5);
    ctx.stroke();
    ctx.restore();
  }

  function drawPanel(vis) {
    const rect = panelRect();
    const x = rect.x;
    const y = rect.y;
    const w = rect.w;
    const h = rect.h;
    const radius = Math.max(vis.radius, 16);
    const skin = vis.panel.image && assets[vis.panel.image];
    const classic = rect.style === 0;
    // P101：1 幕 / 2 字幕 —— 两档都不画矩形。
    // 半透明矩形的问题不在透明度，在"它是一条边界"：背景亮的地方露边、暗的地方消失，
    // 同一块面板在画面里时隐时现，那才是真的丑。全宽渐变没有边，永远不会露。
    //   幕：画面 46% 以上一点不压，往下分三级压到 0.86 —— 白字落在白地板上也读得清
    //   字幕：同样无框，但最底只到 0.55，更像影院字幕，画面留得多
    if (rect.style >= 1) {
      const top = L.viewH * (rect.style === 1 ? 0.46 : 0.52);
      const g = ctx.createLinearGradient(0, top, 0, L.viewH);
      if (rect.style === 1) {
        g.addColorStop(0, "rgba(5,7,12,0)");
        g.addColorStop(0.40, "rgba(5,7,12,.32)");
        g.addColorStop(0.72, "rgba(5,7,12,.64)");
        g.addColorStop(1, "rgba(5,7,12,.86)");
      } else {
        g.addColorStop(0, "rgba(5,7,12,0)");
        g.addColorStop(0.50, "rgba(5,7,12,.20)");
        g.addColorStop(1, "rgba(5,7,12,.55)");
      }
      ctx.save();
      ctx.fillStyle = g;
      const ty0 = Math.round(top);
      ctx.fillRect(0, ty0, L.viewW, L.viewH - ty0);
      ctx.restore();
      return rect;
    }
    // 先垫一层不透明底：贴图皮肤本体常是半透明 PNG，不垫的话背景/立绘会透上来，
    // 台词就不好读了（桌面端皮肤是在底板上叠的，这里保持同样的观感）。
    // P97：不再挂大投影 —— 幕式面板靠渐变和画面接续，再加一圈阴影又变回"纸片"。
    roundRect(x, y, w, h, radius, panelFill(x, y, w, h));
    if (skin) {
      ctx.save();
      ctx.globalAlpha = vis.panel.alpha;
      drawNineSlice(skin, x, y, w, h, sliceOf(vis.panel.slice),
                    Math.max(0.8, L.fs / 42));
      ctx.restore();
      const tex = vis.panel.texture && assets[vis.panel.texture];
      if (tex && vis.panel.texAlpha > 0) {
        ctx.save();
        ctx.globalAlpha = vis.panel.texAlpha * vis.panel.alpha;
        ctx.beginPath();
        ctx.rect(x, y, w, h);
        ctx.clip();
        ctx.fillStyle = ctx.createPattern(tex, "repeat");
        ctx.fillRect(x, y, w, h);
        ctx.restore();
      }
    } else {
      roundRect(x, y, w, h, radius, vis.surface, vis.bgAlpha);
    }
    // P97：横屏不画上缘线。竖屏那条线只有 92% 宽，收得住；横屏面板占屏 81%，
    // 一条横贯全屏的亮线就成了"两块板之间的缝"。横屏只留渐隐，不描边。
    if (!L.landscape) panelHairline(x, y, w, radius);
    return rect;
  }

  // 正文左缘：换行是按 L.textW 折的（宽度契约在 layout 里），面板内缩之后
  // 不能再拿 rect.x + padX 当起点 —— 那样左右留白一宽一窄。按面板居中放正文带。
  function textLeft(rect) {
    return rect.x + Math.round((rect.w - L.textW) / 2);
  }

  function drawDialogue(vis) {
    if (!state.say || !state.lines) return;
    // 选项出现时不画对话框：否则上一句面板会压住选项（横屏 390 高时尤其明显）
    if (state.choice) return;
    const rect = drawPanel(vis);
    const say = state.say;
    // 名字占用的高度：和 panelTargetH() 预留的完全是同一个值，两边必须一致，
    // 否则预留多出来的一截会变成面板里的空白（横屏面板"偏松"就是这么来的）
    const nameH = say.char ? Math.round(L.nameSize * 0.9) : 0;

    if (say.char) {
      const nameFs = Math.round(L.nameSize * 0.86);
      ctx.font = `600 ${nameFs}px ${FACE}`;
      const tw = ctx.measureText(say.char).width;
      // P89：名字牌放进面板内部（原来的 nameH 就是给这一块留的位）
      const plateH = nameH;
      const padW = Math.round(plateH * 0.66);
      // 贴着正文左缘起：原来往外探出 0.28 个牌高，和正文缩进差半格，读起来是两条线
      const plateX = textLeft(rect) + vis.panel.padX;
      const plateY = rect.y + L.padY + vis.panel.padY;
      const tint = say.color || vis.accent;
      const pw = tw + padW * 2 + Math.round(plateH * 0.34);
      // 名牌：淡底 + 角色色竖条 + 白字。原来那圈彩色描边胶囊像贴上去的标签，
      // 换一个角色形状就变一次；竖条只用一个色块交代"谁在说"，安静得多，
      // 白字在任何角色色下都读得清。
      roundRect(plateX, plateY, pw, plateH, Math.round(plateH * 0.30), "rgba(255,255,255,.075)");
      roundRect(plateX + Math.round(plateH * 0.28),
                plateY + Math.round(plateH * 0.20),
                Math.max(2, Math.round(plateH * 0.105)),
                plateH - Math.round(plateH * 0.40),
                2, hexA(tint, 0.92));
      ctx.save();
      ctx.fillStyle = "rgba(242,246,255,.96)";
      ctx.textAlign = "left";
      ctx.textBaseline = "middle";
      ctx.fillText(say.char,
                   plateX + Math.round(plateH * 0.28) + Math.round(plateH * 0.34),
                   plateY + plateH / 2 + 1);
      ctx.restore();
    }

    const shown = typedCount();
    let left = shown;
    ctx.globalAlpha = 1;   // 面板/皮肤绘制可能留下半透明状态，台词必须不透明
    ctx.font = `${L.fs}px ${FACE}`;
    ctx.textBaseline = "top";
    const tx = textLeft(rect) + vis.panel.padX;
    const maxRows = Math.min(rect.rows, L.maxTextRows);
    // 垂直居中：面板高度是按行数补间的（短句的面板本来就矮），
    // 再顶着上沿排，底下那块永远多出一截。居中后短句上下留白相等，
    // 行数接近上限时自动退化成顶对齐。
    const innerTop = rect.y + L.padY + vis.panel.padY + nameH;
    const innerH = rect.h - (L.padY + vis.panel.padY) * 2 - nameH;
    const textH = Math.min(maxRows, (state.lines || []).length) * L.lineH;
    const ty = innerTop + Math.max(0, Math.round((innerH - textH) / 2));
    for (let i = 0; i < state.lines.length && i < maxRows; i++) {
      const line = state.lines[i];
      const txt = line.slice(0, Math.max(0, Math.min(line.length, left)));
      left -= line.length;
      if (!txt) continue;
      ctx.save();
      ctx.shadowColor = "rgba(0,0,0,.55)";
      ctx.shadowBlur = 8;
      ctx.shadowOffsetY = 2;
      ctx.fillStyle = vis.textColor;
      ctx.fillText(txt, tx, ty + i * L.lineH);
      ctx.restore();
    }

    // 继续提示：打字完成 / 没有选项时
    if (!state.choice && shown >= totalChars(state.lines)) {
      // 位置跟内容走：一行字的面板变矮了，圆点要贴着字下面，否则会落在面板底部那块空白里
      const ax = rect.x + rect.w - Math.round(L.fs * 1.05);
      const ay = Math.min(rect.y + rect.h - Math.round(L.fs * 0.72),
                          ty + textH + Math.round(L.fs * 0.5));
      // 一个会呼吸的小圆点，比原来的实心三角安静；半径和亮度都再收一档，
      // 它只是"这一句读完了"，不是按钮
      const pulse = 0.35 + 0.35 * (0.5 + 0.5 * Math.sin(performance.now() / 420));
      ctx.save();
      ctx.globalAlpha = pulse;
      ctx.fillStyle = vis.accent;
      ctx.beginPath();
      ctx.arc(ax, ay, Math.max(3, Math.round(L.fs * 0.20)), 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
    }
  }

  /* 选项时的压暗层：要在对话框之前画，否则连台词一起压暗（原来就压在台词上，字看不清）*/
  function drawChoiceVeil() {
    if (!state.choice) return;
    ctx.save();
    ctx.globalAlpha = 1;
    ctx.fillStyle = "rgba(6,8,12,.56)";
    ctx.fillRect(0, 0, L.viewW, L.viewH);
    ctx.restore();
  }

  /* 选项几何：编辑器「选项按钮」组里的 4 个数值 + 2 个颜色。
     数值按 1280 设计稿写，这里换算到当前画布；没写 / 等于默认时和以前完全一样。 */
  function clampN(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }

  function choiceGeom() {
    const c = cfg("ui.choices", {}) || {};
    const dw = Number(c.width) || 0;
    const dh = Number(c.row_height) || 0;
    const dg = c.dialog_gap !== undefined ? Number(c.dialog_gap)
      : (c.gap !== undefined ? Number(c.gap) : 40);
    const dr = Number(c.radius) || 0;
    const bw = dw ? Math.round(clampN(L.choiceW * (dw / 420), L.viewW * 0.5, L.viewW * 0.94)) : L.choiceW;
    const bh = dh ? Math.round(clampN(L.choiceH * (dh / 52), L.fs * 2.2, L.fs * 4.2)) : L.choiceH;
    const dgr = Number.isFinite(dg) ? dg / 40 : 1;   // dialog_gap = 选项组离对话区多远
    // P89：0.66 -> 0.71。竖屏选项块以下原来空掉近四分之一屏（立绘脚与地板都在下面），
    // 往下挪一点让「在答什么 + 按钮」更像一整个重心，而不是浮在半空。
    const centerY = Math.round(clampN(L.viewH * (0.71 - (dgr - 1) * 0.12),
                                      L.viewH * 0.44, L.viewH * 0.88));
    const sg = c.gap === undefined ? 34 : Number(c.gap);   // gap = 选项之间的缝
    const gap = Number.isFinite(sg) ? Math.max(0, Math.round(L.choiceGap * (sg / 34))) : L.choiceGap;
    const radius = dr ? Math.min(Math.round(dr * 1.6), Math.round(bh / 2)) : 14;
    return {
      bw: bw, bh: bh, gap: gap, radius: radius, centerY: centerY,
      bg: String(c.bg || "").trim(),
      fg: String(c.fg || "").trim(),
    };
  }

  function drawChoices(vis) {
    state.choiceRects = [];
    if (!state.choice) return;

    const geom = choiceGeom();
    const bw = geom.bw;
    const bh = geom.bh;
    const gap = geom.gap;
    const n = state.choice.length;
    const totalH = n * bh + (n - 1) * gap;
    // 选项组压在画面 66% 高度：立绘头顶约在 28%，42% 正好挡住脸；
    // 往下放到胸口一带，既不压角色也不贴屏幕底边
    const startY = Math.max(L.marginX, geom.centerY - totalH / 2);
    // 横屏选项靠左：画布 1686 长、人物站右 63%，选项居中就正好压在人腰上。
    // 靠左贴着画面边，人整个露出来，视线从字到人是一条横线。
    const x = L.landscape
      ? Math.round(L.viewW * 0.052)
      : (L.viewW - bw) / 2;

    // 选项上方留一句「在答什么」：选项出现时对话框是藏起来的，
    // 光给几个按钮玩家会失去上下文（尤其横屏一整屏空着的时候）。
    if (state.say && state.lines && state.lines.length) {
      const qfs = Math.round(L.fs * 0.92);
      ctx.save();
      ctx.font = `${qfs}px ${FACE}`;
      const qLines = wrap(state.lines[state.lines.length - 1], bw * 0.94).slice(-2);
      const qBottom = startY - Math.round(bh * 0.55);
      const qCx = L.landscape ? x + bw / 2 : L.viewW / 2;
      // 底衬：原来只有描边阴影，压在夕阳/雨街这种亮背景上就糊成一团。
      // 用一团柔和的暗晕（径向渐变，四边都渐隐）—— 试过圆角矩形带子，
      // 压在画面上就是一块明显的黑补丁，比字糊还难看。
      const qBandTop = qBottom - qLines.length * qfs * 1.3 - Math.round(qfs * 0.6);
      const qBandBot = startY - Math.round(bh * 0.18);
      const qBw = Math.min(L.viewW - L.marginX * 2, Math.round(bw * 1.2));
      const cy = (qBandTop + qBandBot) / 2;
      ctx.save();
      ctx.translate(qCx, cy);
      ctx.scale(1, Math.max(0.35, (qBandBot - qBandTop) / qBw));
      const rq = qBw * 0.62;
      const bandG = ctx.createRadialGradient(0, 0, qBw * 0.10, 0, 0, rq);
      bandG.addColorStop(0, "rgba(9,11,17,.80)");
      bandG.addColorStop(0.62, "rgba(9,11,17,.55)");
      bandG.addColorStop(1, "rgba(9,11,17,0)");
      ctx.fillStyle = bandG;
      ctx.beginPath();
      ctx.arc(0, 0, rq, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
      ctx.textAlign = "center";
      ctx.textBaseline = "bottom";
      ctx.fillStyle = "rgba(238,242,252,.94)";
      ctx.shadowColor = "rgba(0,0,0,.55)";
      ctx.shadowBlur = 6;
      qLines.forEach((ln, i, arr) => {
        ctx.fillText(ln, qCx, qBottom - (arr.length - 1 - i) * qfs * 1.3);
      });
      ctx.restore();
      ctx.textAlign = "left";
    }

    state.choice.forEach((opt, i) => {
      const y = startY + i * (bh + gap);
      const r = geom.radius;
      // 按钮不用 3px 蓝框圈住（太像表单）：淡底 + 1px 细边 + 左侧一道 accent 竖条
      if (geom.bg) {
        roundRect(x, y, bw, bh, r, hexA(geom.bg, 0.94));
      } else {
        const g2 = ctx.createLinearGradient(0, y, 0, y + bh);
        g2.addColorStop(0, "rgba(32,38,54,.94)");
        g2.addColorStop(1, "rgba(20,24,36,.96)");
        roundRect(x, y, bw, bh, r, g2);
      }
      ctx.save();
      ctx.strokeStyle = "rgba(255,255,255,.14)";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(x + r, y);
      ctx.arcTo(x + bw, y, x + bw, y + bh, r);
      ctx.arcTo(x + bw, y + bh, x, y + bh, r);
      ctx.arcTo(x, y + bh, x, y, r);
      ctx.arcTo(x, y, x + bw, y, r);
      ctx.closePath();
      ctx.stroke();
      ctx.fillStyle = vis.accent;
      // 左侧 accent 竖条：别贴着卡片外缘画。原来在 x+1、宽 3（布局单位），2x 屏上只有 2 个
      // 物理像素，又正好压在圆角收口的位置，看起来像屏幕边上的一颗故障小点。挪进卡片内、加厚。
      ctx.fillRect(x + 12, y + Math.round(bh * 0.28), 5, Math.round(bh * 0.44));
      ctx.restore();
      ctx.fillStyle = geom.fg || vis.textColor;
      ctx.font = `500 ${L.fs}px ${FACE}`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(opt.text, x + bw / 2, y + bh / 2);
      ctx.textAlign = "left";
      state.choiceRects.push({x: x, y: y, w: bw, h: bh, idx: i,
                              text: opt.text, target: opt.target});
    });
  }

  /* 标题页封面：优先用打包时挑好的那张（按文件体积算出的最大背景图），
     没有就退回"名字里带 bg 的" —— 但不再从 assets 里抓第一张，
     那常常是程序画的占位图，标题页会变成一堵空墙。 */
  function titleCover() {
    if (pack && pack.cover) {
      // 竖屏优先用封面的竖版构图，没有就主图（配合锚点裁）
      if (!L.landscape && assets[pack.cover + "_p"]) return assets[pack.cover + "_p"];
      if (assets[pack.cover]) return assets[pack.cover];
    }
    const names = Object.keys(assets).filter(n => /bg|cover/i.test(n) && !/_p$/.test(n));
    return names.length ? assets[names[0]] : null;
  }

  /* 字号自适应：长标题缩字号比换行更稳（换行会把底部卡片撑高） */
  function fitFont(text, maxW, fs, weight) {
    let f = fs;
    ctx.font = `${weight} ${f}px ${FACE}`;
    while (f > 12 && ctx.measureText(text).width > maxW) {
      f -= 1;
      ctx.font = `${weight} ${f}px ${FACE}`;
    }
    return f;
  }

  function drawTitle() {
    const W = L.viewW, H = L.viewH, u = Math.min(W, H);
    const land = W > H;

    const cover = titleCover();
    if (cover) {
      // 不糊死：只轻微柔化，否则抽象背景整屏糊成一堵灰墙，什么也看不出来
      ctx.save();
      ctx.filter = "blur(3px)";
      blitCover(cover, 1);
      ctx.restore();
      ctx.filter = "none";
      const rv = ctx.createRadialGradient(W / 2, H * 0.26, 0, W / 2, H * 0.26, Math.max(W, H) * 0.78);
      rv.addColorStop(0, "rgba(9,11,17,.12)");
      rv.addColorStop(.60, "rgba(9,11,17,.38)");
      rv.addColorStop(1, "rgba(9,11,17,.86)");
      ctx.fillStyle = rv;
      ctx.fillRect(0, 0, W, H);
      const gb = ctx.createLinearGradient(0, H * 0.42, 0, H);
      gb.addColorStop(0, "rgba(9,11,17,0)");
      gb.addColorStop(1, "rgba(9,11,17,.78)");
      ctx.fillStyle = gb;
      ctx.fillRect(0, H * 0.42, W, H * 0.58);
    } else {
      const g0 = ctx.createLinearGradient(0, 0, 0, H);
      g0.addColorStop(0, "#1a1f2e");
      g0.addColorStop(1, "#07080d");
      ctx.fillStyle = g0;
      ctx.fillRect(0, 0, W, H);
      const rg = ctx.createRadialGradient(W / 2, H * 0.22, 0, W / 2, H * 0.22, Math.max(W, H) * 0.62);
      rg.addColorStop(0, "rgba(79,140,255,.20)");
      rg.addColorStop(1, "rgba(79,140,255,0)");
      ctx.fillStyle = rg;
      ctx.fillRect(0, 0, W, H);
    }

    // 横屏标题页：光有一张卡片 + 一片（被压暗的）背景，看着像启动屏不像作品页。
    // 把工程里的全身立绘右侧立一个当主视觉，左边卡片就是标题，右边是人 —— 一眼是 galgame。
    if (land) {
      // 立绘的判据不能用名字：打包后键就是「角色_表情」（林晚_微笑），
      // 剧本里的「全身」前缀不会出现在键里。按构图比例认 —— 竖长图 + 不是背景/CG。
      const heroName = Object.keys(assets).find(n => {
        const im = assets[n];
        if (!im || !im.width || !im.height) return false;
        if (/^(bg|cover|cg|title)/i.test(n)) return false;
        return im.height > im.width * 1.4;
      });
      const hero = heroName && assets[heroName];
      if (hero && hero.width && hero.height) {
        const tallSrc = hero.height > hero.width * 2.2;
        const srcH = tallSrc ? Math.round(hero.height * 0.66) : hero.height;
        const hh = H * 0.97;
        const hw = hero.width * (hh / srcH);
        ctx.save();
        ctx.globalAlpha = 0.97;
        ctx.drawImage(hero, 0, 0, hero.width, srcH, W * 0.72 - hw / 2, H - hh, hw, hh);
        ctx.restore();
      }
    }

    let hasSave = false;
    try { hasSave = !!localStorage.getItem(saveKey()); } catch (e) { hasSave = false; }

    // P97：竖屏不要卡片。
    // 一张圆角板贴在底边，无论怎么调圆角和透明度，它都是"网页落地页"的样子 ——
    // 因为它把画面切成了"上半张图 + 下半块板"。改成整宽渐隐：画面完整留到最后一行，
    // 字站在暗处。横屏保留卡片，因为右边站着立绘，左边需要一块压得住的板。
    const k = W / (window.innerWidth || W);
    const cardX = land ? W * 0.05 : 0;
    const cardW = land ? Math.min(W * 0.42, 380 * k) : W;
    const cardH = land ? H * 0.44 : H * 0.50;
    const cardY = land ? (H - cardH) / 2 : H - cardH;

    if (land) {
      const cg = ctx.createLinearGradient(0, cardY, 0, cardY + cardH);
      cg.addColorStop(0, "rgba(20,24,33,.66)");
      cg.addColorStop(0.18, "rgba(17,20,28,.90)");
      cg.addColorStop(1, "rgba(9,11,16,.97)");
      roundRect(cardX, cardY, cardW, cardH, 24 * k, cg);
      const hg = ctx.createLinearGradient(cardX + 40 * k, 0, cardX + cardW - 40 * k, 0);
      hg.addColorStop(0, "rgba(255,255,255,0)");
      hg.addColorStop(0.5, "rgba(255,255,255,.14)");
      hg.addColorStop(1, "rgba(255,255,255,0)");
      ctx.fillStyle = hg;
      ctx.fillRect(cardX + 40 * k, cardY, cardW - 80 * k, Math.max(1, k));
    } else {
      const vg = ctx.createLinearGradient(0, cardY, 0, H);
      vg.addColorStop(0, "rgba(6,8,12,0)");
      vg.addColorStop(0.30, "rgba(6,8,12,.42)");
      vg.addColorStop(0.62, "rgba(6,8,12,.84)");
      vg.addColorStop(1, "rgba(5,7,11,.96)");
      ctx.fillStyle = vg;
      ctx.fillRect(0, cardY, W, H - cardY);
    }

    const pad = 20 * k;
    const innerX = land ? cardX + pad : W * 0.075;
    const innerW = land ? cardW - pad * 2 : W * 0.85;
    const bh = H * (land ? 0.135 : 0.062);
    const gap = 10 * k;
    const btnY = land ? cardY + cardH - Math.round(pad * 0.8) - bh : H - bh - H * 0.052;
    const btnW = land ? innerW : Math.min(innerW, W * 0.60);
    const subW = hasSave ? Math.min(innerW * 0.36, 128 * k) : 0;
    state.startRect = {x: innerX, y: btnY, w: btnW - (hasSave ? subW + gap : 0), h: bh};
    state.continueRect = hasSave
      ? {x: innerX + btnW - subW, y: btnY, w: subW, h: bh}
      : null;

    const fs = fitFont(pack.title || "MYONL", innerW, Math.round(u * (land ? 0.112 : 0.132)), 800);
    // 品牌标记：原来那行「视觉小说 · MYONL」是给开发者看的说明，玩家只认作品名。
    const markY = land ? cardY + pad + Math.round(u * 0.026)
                       : btnY - bh * 0.55 - fs * 1.30;
    ctx.textAlign = "left";
    ctx.textBaseline = "alphabetic";
    ctx.fillStyle = "rgba(79,140,255,.90)";
    ctx.fillRect(innerX, markY - Math.round(u * 0.020), Math.round(u * 0.052), Math.max(2, k));
    ctx.fillStyle = "rgba(240,244,255,.42)";
    ctx.font = `500 ${Math.round(u * 0.024)}px ${FACE}`;
    ctx.fillText("MYONL", innerX + Math.round(u * 0.066), markY);

    ctx.font = `800 ${fs}px ${FACE}`;
    ctx.fillStyle = "#f7f9ff";
    ctx.fillText(pack.title || "MYONL", innerX, btnY - bh * 0.55);

    const r1 = state.startRect;
    roundRect(r1.x, r1.y, r1.w, r1.h, 13 * k, "rgba(79,140,255,.96)");
    // 按钮内高光：纯色块是"网页表单"，顶上一条 1px 白线才有实体感
    {
      const ig = ctx.createLinearGradient(0, r1.y, 0, r1.y + r1.h * 0.5);
      ig.addColorStop(0, "rgba(255,255,255,.22)");
      ig.addColorStop(1, "rgba(255,255,255,0)");
      ctx.save();
      ctx.beginPath();
      ctx.roundRect ? ctx.roundRect(r1.x, r1.y, r1.w, r1.h, 13 * k)
                    : ctx.rect(r1.x, r1.y, r1.w, r1.h);
      ctx.clip();
      ctx.fillStyle = ig;
      ctx.fillRect(r1.x, r1.y, r1.w, r1.h * 0.5);
      ctx.restore();
    }
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillStyle = "#fff";
    ctx.font = `600 ${Math.round(bh * 0.32)}px ${FACE}`;
    ctx.fillText("开始新故事", r1.x + r1.w / 2, r1.y + bh / 2 + 1);

    if (state.continueRect) {
      const r2 = state.continueRect;
      roundRect(r2.x, r2.y, r2.w, r2.h, 14 * k, "rgba(255,255,255,.10)");
      ctx.fillStyle = "rgba(240,244,255,.86)";
      ctx.font = `500 ${Math.round(bh * 0.30)}px ${FACE}`;
      ctx.fillText("继续上次", r2.x + r2.w / 2, r2.y + bh / 2 + 1);
    }
    ctx.textAlign = "left";
    ctx.textBaseline = "alphabetic";
  }

  function drawEnding() {
    drawBackground();
    ctx.fillStyle = "rgba(7,8,13,.74)";
    ctx.fillRect(0, 0, L.viewW, L.viewH);
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillStyle = "#f4f6ff";
    ctx.font = `700 ${Math.round(Math.min(L.viewW, L.viewH) * 0.08)}px ${FACE}`;
    ctx.fillText("完", L.viewW / 2, L.viewH * 0.44);
    ctx.fillStyle = "rgba(240,244,255,.6)";
    ctx.font = `400 ${Math.round(Math.min(L.viewW, L.viewH) * 0.032)}px ${FACE}`;
    ctx.fillText("点击回到标题", L.viewW / 2, L.viewH * 0.56);
    ctx.textAlign = "left";
  }

  function drawError() {
    ctx.fillStyle = "#0b0d12";
    ctx.fillRect(0, 0, L.viewW, L.viewH);
    ctx.fillStyle = "#ff8f8f";
    ctx.font = `400 ${L.fs}px ${FACE}`;
    ctx.textBaseline = "top";
    wrap(state.error, L.viewW - 120).slice(0, 8).forEach((line, i) => {
      ctx.fillText(line, 60, 160 + i * L.lineH);
    });
  }

  // 场景（背景 / 立绘 / CG）套一层镜头变换；对话框和选项永远不跟着镜头动
  function drawScene() {
    ctx.save();
    const cx = L.viewW / 2;
    const cy = L.viewH / 2;
    ctx.translate(cx + cam.panX + cam.sx, cy + cam.panY + cam.sy);
    ctx.scale(cam.zoom, cam.zoom);
    ctx.translate(-cx, -cy);
    drawBackground();
    drawSprites();
    drawCg();
    drawFg();
    ctx.restore();
    drawVignette();
  }

  /* 横屏暗角：横屏画面宽，背景常常是一片渐变，边角不收一下就容易「一整块平色」。
     压在场景之上、UI 之下，边缘收暗、视线往里收，看着像一张画面而不是一个网页。 */
  function drawVignette() {
    if (!L.landscape) return;
    const g = ctx.createRadialGradient(
      L.viewW / 2, L.viewH * 0.46, Math.round(L.viewH * 0.30),
      L.viewW / 2, L.viewH * 0.52, Math.round(Math.max(L.viewW, L.viewH) * 0.66));
    g.addColorStop(0, "rgba(0,0,0,0)");
    g.addColorStop(0.62, "rgba(0,0,0,.10)");
    g.addColorStop(1, "rgba(4,6,12,.46)");
    ctx.save();
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, L.viewW, L.viewH);
    ctx.restore();
  }

  // ---------- 章节卡（P73）----------
  // @chapter 标题 [秒数]：黑场 + 居中大标题，淡入淡出，播完自动继续。
  function drawChapter() {
    const c = state.chapter;
    if (!c) return;
    const el = (performance.now() - c.t0) / c.dur;
    if (el >= 1) { state.chapter = null; return; }
    const fade = 0.16;
    const a = el < fade ? el / fade : (el > 1 - fade ? (1 - el) / fade : 1);
    const W = L.viewW;
    const H = L.viewH;
    ctx.save();
    ctx.globalAlpha = Math.max(0, Math.min(1, a));
    ctx.fillStyle = "#08090f";
    ctx.fillRect(0, 0, W, H);
    const fs = Math.round(Math.min(W, H) * 0.075);
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillStyle = "#f4f6ff";
    ctx.font = `600 ${fs}px ${FACE}`;
    wrap(c.title || "", W * 0.82).slice(0, 3).forEach((line, i, arr) => {
      ctx.fillText(line, W / 2, H * 0.5 + (i - (arr.length - 1) / 2) * fs * 1.4);
    });
    ctx.globalAlpha = Math.max(0, Math.min(1, a)) * 0.75;
    ctx.strokeStyle = "#4f8cff";
    ctx.lineWidth = Math.max(2, Math.round(W * 0.008));
    const lw = W * 0.16;
    ctx.beginPath();
    ctx.moveTo(W / 2 - lw, H * 0.5 + fs * 0.9);
    ctx.lineTo(W / 2 + lw, H * 0.5 + fs * 0.9);
    ctx.stroke();
    ctx.restore();
    ctx.textAlign = "left";
  }

  function frame() {
    const vis = visual();
    const now = performance.now();
    UI.rects = [];        // 一帧一套热点：谁画谁 push，别让上一帧的坐标留到下一帧
    updatePanelH(now);
    updateCam(now);
    if (state.error) {
      drawError();
    } else if (!pack) {
      /* 等加载 */
    } else if (state.scene === "title") {
      drawTitle();
    } else if (state.scene === "ending") {
      drawEnding();
    } else {
      drawScene();
      drawChapter();
      drawChoiceVeil();
      drawDialogue(vis);
      drawChoices(vis);
      drawMute();
      drawMenuButton();
      drawOrbit();
      if (state.guide) drawGuide();
      if (state.waitUntil && performance.now() >= state.waitUntil) {
        state.waitUntil = 0;
        next();
      }
      // 快进（二周目用）：55ms 一句，遇到选项/@wait/结局自动停。开关在菜单里。
      if (PREF.skip && !state.choice && !(state.waitUntil > 0) && !state.ended) {
        if (now - (state.skipAt || 0) > 55) { state.skipAt = now; next(); }
      }
      // 自动翻页：只在打字读完、没有选项、没有 @wait 时走
      if (PREF.auto > 0 && !state.choice && !(state.waitUntil > 0)) {
        const total = totalChars(state.lines);
        if (total && typedCount() >= total) {
          const doneAt = state.typeStart + (total / cps()) * 1000;
          if (now - doneAt >= PREF.auto * 1000) { autoSave(); next(); }
        }
      }
    }
    if (UI.open) drawMenu();
    requestAnimationFrame(frame);
  }

  // ---------- 启动 ----------
  loadPrefs();
  bgmVolume = PREF.vol;
  fit();
  requestAnimationFrame(frame);

  // 调试口：给 tools/web_shot.py 之类的验收脚本读状态（只读，不改剧情）
  window.MYONL_DEBUG = {
    get layout() { return L; },
    // 面板实测几何：验收脚本要看面板有没有出屏（h 超过 viewH 就是被裁）
    get panel() {
      const r = menuPanel();
      return {view: UI.view, open: !!UI.open, x: r.x, y: r.y, w: r.w, h: r.h,
              viewH: L.viewH, viewW: L.viewW};
    },
    // 菜单/存档/设置里当帧可点的按钮（id + 布局坐标），验收脚本靠它点，不靠猜像素
    get rects() { return UI.rects.slice(); },
    get state() {
      return {
        scene: state.scene, say: state.say, choice: state.choice,
        choiceRects: state.choiceRects, sprites: state.sprites, bg: state.bg,
        cg: state.cg,
        lines: state.lines, ended: state.ended, error: state.error,
        guide: !!state.guide,
        panelH: panelHNow(), panelTop: panelTopY(),
      };
    },
    get audio() {
      return bgm ? {paused: bgm.paused, muted: bgm.muted, volume: bgm.volume,
                    on: audioOn} : null;
    },
    // @video 帧池的实测读数：验收脚本用它确认"缓存有上限、切走会释放"
    get video() {
      return {name: state.video ? state.video.name : "", fps: state.video ? state.video.fps : 0,
              cached: videoKeys.length, keep: VIDEO_KEEP,
              ready: Object.keys(videoCache).filter(k => videoCache[k].complete
                                                      && videoCache[k].naturalWidth).length};
    },
    tap: (x, y) => {
      const box = canvas.getBoundingClientRect();
      onTap({
        clientX: box.left + (x / L.viewW) * box.width,
        clientY: box.top + (y / L.viewH) * box.height,
        preventDefault: function () {},
      });
    },
  };

  // P67：作者在编辑器「设置」里选了「竖屏 / 横屏」时，玩家拿反了就提示一句。
  // 不硬锁方向（网页锁方向要全屏权限，各家浏览器不一致），只提示，转过来提示自己消失。
  let orientChip = null;
  function syncOrientationHint(want) {
    if (!want || want === "any") {
      if (orientChip) { orientChip.remove(); orientChip = null; }
      return;
    }
    const isPortrait = window.innerHeight >= window.innerWidth;
    const ok = (want === "portrait") === isPortrait;
    if (ok) {
      if (orientChip) { orientChip.remove(); orientChip = null; }
      return;
    }
    if (!orientChip) {
      orientChip = document.createElement("div");
      orientChip.style.cssText = "position:fixed;left:50%;bottom:calc(24px + env(safe-area-inset-bottom));"
        + "transform:translateX(-50%);z-index:9;padding:9px 16px;border-radius:999px;"
        + "background:rgba(0,0,0,.78);color:#fff;font:13px/1.4 system-ui,sans-serif;"
        + "pointer-events:none;white-space:nowrap";
      document.body.appendChild(orientChip);
    }
    orientChip.textContent = want === "portrait"
      ? "这个作品是竖屏的 · 把手机竖过来 ↕"
      : "这个作品是横屏的 · 把手机横过来 ↔";
  }

  const bootPack = window.__MYONL_PACK__
    ? Promise.resolve(window.__MYONL_PACK__)
    : fetch("pack.json", {cache: "no-store"})
        .then((r) => { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); });

  // 启动遮罩：模板里那块 #boot（纯黑 + 一颗脉动的蓝点 + 作品名）。
  // 素材加载完就撤掉；出错也要撤，否则一块黑屏挡住错误文字。
  function dismissBoot() {
    var el = document.getElementById("boot");
    if (!el) return;
    el.classList.add("gone");
    setTimeout(function () {
      if (el.parentNode) el.parentNode.removeChild(el);
    }, 360);
  }

  bootPack
    .then((data) => {
      pack = data;
      FOCAL = pack.focal || {};
      vm = CORE.createVM(pack);
      return loadAssets();
    })
    .then(() => {
      storeMigrate();            // 旧版散装存档搬进新结构（只搬本作品）
      fit();
      syncOrientationHint(pack.orientation);
      window.addEventListener("resize", () => syncOrientationHint(pack.orientation));
      if (pack.unsupported && pack.unsupported.length) {
        console.warn("[MYONL] 桌面端有、手机端暂不支持：" + pack.unsupported.join("、"));
      }
      dismissBoot();
    })
    .catch((err) => {
      state.error = "加载失败：" + err.message
        + "。单文件版可直接双击打开；分目录版需要静态服务器（file:// 取不到 pack.json）。";
      dismissBoot();
    });
  // ---------- 菜单 / 存档 / 设置（P69）----------
  /* 全部 canvas 自绘：单文件导出版和分目录版共用同一份逻辑，DOM 覆盖层在单文件里会丢样式。
     设置只存本机 localStorage（离线作品没有服务器），键名不分游戏——换作品也沿用同一套手感。*/

  function loadPrefs() {
    try {
      // 旧键迁移：P85 之前的顶层 myonl:prefs 与 myonl:helpSeen
      const legacy = localStorage.getItem("myonl:prefs");
      if (legacy && !localStorage.getItem(PREF_KEY)) {
        localStorage.setItem(PREF_KEY, legacy);
        localStorage.removeItem("myonl:prefs");
      }
      if (localStorage.getItem("myonl:helpSeen") === "1") {
        helpSeen = true;
        localStorage.removeItem("myonl:helpSeen");
      }
      const v = JSON.parse(localStorage.getItem(PREF_KEY) || "{}");
      if (v.helpSeen === 1) helpSeen = true;
      if (typeof v.speed === "number") PREF.speed = v.speed;
      if (typeof v.text === "number") PREF.text = v.text;
      if (typeof v.vol === "number") PREF.vol = v.vol;
      if (typeof v.auto === "number") PREF.auto = v.auto;
      // P84：quality / skip / orient 原来写了但没读回来 —— 玩家关了快进、调了画质，
      // 关掉网页再进就全恢复默认，这种"记不住设置"是最廉价的廉价感。
      if (typeof v.quality === "number") PREF.quality = v.quality;
      if (typeof v.skip === "number") PREF.skip = v.skip;
      if (v.orient === "auto" || v.orient === "portrait" || v.orient === "landscape") {
        PREF.orient = v.orient;
      }
      if (typeof v.dlg === "number") PREF.dlg = Math.max(0, Math.min(2, Math.trunc(v.dlg)));
    } catch (e) { /* 隐私模式禁读 */ }
  }

  function savePrefs() {
    const o = Object.assign({}, PREF, {helpSeen: helpSeen ? 1 : 0});
    try { localStorage.setItem(PREF_KEY, JSON.stringify(o)); } catch (e) { /* 禁写 */ }
  }

  function markHelpSeen() { helpSeen = true; savePrefs(); }

  function cps() { return BASE_CPS * PREF.speed; }

  /* 字号放大后不能只是字变大：行高、名字牌、可用行数都要跟着改，否则会挤出面板 */
  function applyTextScale() {
    if (PREF.text === 1) return;
    const k = PREF.text;
    L.fs = Math.round(L.fs * k);
    L.lineH = Math.round(L.lineH * k);
    L.nameSize = Math.round(L.nameSize * k);
    L.maxTextRows = k > 1 ? 4 : 6;
    L.textW = L.panelW - L.padX * 2;
  }

  function slotCount() { return 6; }

  function previewLine() {
    if (!state.say) return "";
    const who = state.say.char ? state.say.char + "：" : "";
    return (who + (state.say.text || "")).slice(0, 18);
  }

  function readSlot(i) { return storeSlot(i); }

  function writeSlot(i) {
    // 没有在跑的进度就明说（storeErr=2），不要静默 return ——
    // 玩家点了格子、什么都没有发生，只会以为"存上了"。
    if (!vm) { UI.storeErr = 2; return; }
    storeSetSlot(i, {s: vm.save(), t: Date.now(), say: previewLine(), bg: state.bg || ""});
    UI.t0 = performance.now();
  }

  function loadSlot(i) {
    const d = readSlot(i);
    if (!d || !d.s) return;
    UI.open = false;
    state.scene = "game";
    state.ended = false;
    state.say = null;
    state.lines = [];
    state.choice = null;
    state.choiceRects = [];
    state.waitUntil = 0;
    vm.load(d.s);
    state.bg = vm.state.bg || "";
    state.cg = vm.state.cg || "";
    state.sprites = (vm.state.sprites || []).slice();
    state.fg = vm.state.fg || null;
    state.anim = vm.state.anim || {};
    state.video = vm.state.video ? Object.assign({}, vm.state.video) : null;
    if (state.video) { state.video.t0 = performance.now(); warmVideo(); }
    if (vm.state.music) playMusic(vm.state.music, 0, 0);
    next();
  }

  function openMenu() { UI.open = true; UI.view = "menu"; UI.t0 = performance.now(); }

  /* 直接开某一页（右侧竖列用），跳过"先进菜单再点一层" */
  function openPanel(view) { UI.open = true; UI.view = view; UI.t0 = performance.now(); }

  /* 安卓壳的返回键先问这里：面板开着就关掉，游戏里就开菜单，都不是才让系统退出。
     返回 false 时壳会 finish()，所以这里只在自己真的处理了的时候说 true。 */
  window.myonlBack = function () {
    if (UI.open) { UI.open = false; return true; }
    if (state.scene === "game" && !state.error) { openPanel("menu"); return true; }
    return false;
  };

  function stamp(t) {
    const d = new Date(t || 0);
    const p2 = (n) => (n < 10 ? "0" : "") + n;
    return (d.getMonth() + 1) + "-" + p2(d.getDate()) + " " + p2(d.getHours()) + ":" + p2(d.getMinutes());
  }

  function menuBtnSize() {
    // 原来 0.105 → 最小 64px：竖屏 390 宽时是 68，两个键就把右上角占满，
    // 右侧竖列又各 56 —— 五个控件互相争焦点。收到 0.072（最小 44，正好是手指的舒适下限），
    // 让画面回来的第一眼是立绘，不是按钮。
    return Math.min(96, Math.max(44, Math.round(Math.min(L.viewW, L.viewH) * 0.072)));
  }

  /* 菜单键放在喇叭左边：右上角本来就是"两个键"的位置，玩家不用记新手势 */
  function menuRect() {
    const s2 = menuBtnSize();
    const m = Math.round(Math.min(L.viewW, L.viewH) * 0.03);
    const mr = muteRect();
    return {x: mr.x - s2 - Math.round(m * 0.5), y: m, w: s2, h: s2};
  }

  function drawMenuButton() {
    if (state.scene !== "game" || state.error) return;
    const r = menuRect();
    ctx.save();
    // P97：去掉那圈 1px 描边。深色底上一圈等亮度细线就是"图标按钮"的模样，
    // 只留一个半透明圆 + 三条线，它才真的缩进画面里。
    ctx.globalAlpha = 0.55;
    roundRect(r.x, r.y, r.w, r.h, r.h / 2, "rgba(12,14,20,.86)");
    ctx.globalAlpha = 1;
    const cx = r.x + r.w / 2;
    const cy = r.y + r.h / 2;
    const half = r.w * 0.17;
    ctx.strokeStyle = "rgba(240,244,255,.76)";
    ctx.lineWidth = Math.max(1.5, Math.round(r.h * 0.026));
    ctx.lineCap = "round";
    for (let i = -1; i <= 1; i++) {
      ctx.beginPath();
      ctx.moveTo(cx - half, cy + i * r.h * 0.16);
      ctx.lineTo(cx + half, cy + i * r.h * 0.16);
      ctx.stroke();
    }
    ctx.restore();
    // 验收脚本用（onTap 走 menuRect 判定）
    hit("menuBtn", r.x, r.y, r.w, r.h);
  }

  /* ---- 右侧竖列工具条 --------------------------------------------------------
     外壳那套「贴着屏边一列小键」的做法。原来「存档 / 回顾 / 设置」全藏在 ☰ 里，
     玩到关键处想存一档要 点菜单 → 再点一层；菜单面板一开就盖掉大半个屏。
     这里把三个最高频的拎出来常驻屏边，☰ 里剩下的照旧（含快进/自动/回标题）。
     只露半透明底，看不清也不碍事；点开才展开成完整面板。*/
  const ORBIT = [["save", "存"], ["log", "回"], ["settings", "设"]];

  function orbitRect(i) {
    const s2 = menuBtnSize();
    const m = Math.round(Math.min(L.viewW, L.viewH) * 0.022);
    const gap = Math.round(s2 * 0.18);
    // 竖列整体垂直居中偏下：从 34% 屏高硬起排会正好压在人脸上/腰上。
    // P97 再往下挪到 55%：46% 那会儿三条正好卡在立绘腰侧，看着跟人物长在一起。
    const total = (ORBIT.length - 1) * (s2 + gap) + s2;
    const top = Math.round(L.viewH * (L.landscape ? 0.44 : 0.55) - total / 2);
    return {x: L.viewW - m - s2, y: top + i * (s2 + gap), w: s2, h: s2};
  }

  function orbitHit(p) {
    if (state.scene !== "game" || state.error || UI.open || state.guide) return "";
    for (let i = 0; i < ORBIT.length; i++) {
      if (inRect(p, orbitRect(i))) return ORBIT[i][0];
    }
    return "";
  }

  function drawOrbit() {
    if (state.scene !== "game" || state.error || UI.open || state.guide) return;
    for (let i = 0; i < ORBIT.length; i++) {
      const r = orbitRect(i);
      const rad = r.h / 2;
      // P97：纯圆、无描边。底要压得住背景 —— 0.46 在课桌这类花纹上会"消失"，
      // 0.62 才既安静又看得见。
      roundRect(r.x, r.y, r.w, r.h, rad, "rgba(12,14,20,.88)", 0.62);
      ctx.save();
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillStyle = "rgba(240,244,255,.72)";
      ctx.font = "500 " + Math.round(r.w * 0.36) + "px " + FACE;
      ctx.fillText(ORBIT[i][1], r.x + r.w / 2, r.y + r.h / 2 + 1);
      ctx.restore();
      // 只用于验收脚本定位（onTap 走 orbitHit，不读这里）
      hit("orbit:" + ORBIT[i][0], r.x, r.y, r.w, r.h);
    }
    ctx.textAlign = "left";
    ctx.textBaseline = "alphabetic";
  }

  /* 横屏只有 390 高，5 个按钮按竖屏的尺寸会顶到屏幕上下边 */
  // P102：竖屏菜单从 8 行变 9 行，行高 2.3 → 2.12，否则最底下「回到标题」会被屏底裁掉半行
  function menuRowH() { return Math.round(L.fs * (L.landscape ? 1.75 : 2.12)); }
  function menuGap() { return Math.round(L.fs * (L.landscape ? 0.22 : 0.16)); }
  function setRowH() { return Math.round(L.fs * (L.landscape ? 2.0 : 2.4)); }
  /* 回顾一页几行：横屏矮，一页 6 行；竖屏高，7 行 */
  function logRows() { return L.landscape ? 6 : 7; }
  function logRowH() { return Math.round(L.fs * 1.45); }
  function logGap() { return Math.round(L.fs * 0.3); }

  /* 面板高度跟着内容走：写死 74% 会在底部留一大片空，还漏出后面的对话框 */
  function menuPanel() {
    const land = L.landscape;
    const w = land ? Math.min(L.viewW * 0.62, 900) : L.viewW * 0.94;
    const pad = Math.round(w * 0.055);
    const headH = Math.round(L.fs * 2.2);
    const footH = Math.round(L.fs * 2.3);
    const gap = Math.round(L.fs * 0.55);
    let bodyH;
    if (UI.view === "menu") {
      // 列表行：竖屏 9 行一列；横屏 5 行两列（P102 菜单多了「画面方向」，行数跟着改）
      bodyH = Math.round(L.fs * 0.35)
              + (L.landscape ? 5 : 9) * (menuRowH() + menuGap());
    } else if (UI.view === "settings") {
      // 横屏两列（3 行）—— 单列 6 组在横屏里会把面板撑到顶边，一点留白都没有
      bodyH = Math.round(L.fs * 0.3) + (L.landscape ? 3 : 6) * (setRowH() + gap);
    } else if (UI.view === "log") {
      // 按「这一页实际有几条」留高：最后一页常常只剩三四条，
      // 照 7 行的固定高度留位，底下就是一整块空 —— 之前就是这样。
      const hist = state.history || [];
      const per = logRows();
      const pages = Math.max(1, Math.ceil(hist.length / per));
      const pg = Math.min(Math.max(0, UI.logPage || 0), pages - 1);
      const shown = hist.length ? Math.min(per, hist.length - pg * per) : 2;
      bodyH = Math.round(L.fs * 0.5)
               + Math.max(2, shown) * (logRowH() + logGap())
               + Math.round(L.fs * 2.4);
    } else {
      const rows = land ? 2 : 3;
      // 必须和 drawSlots() 里的 ch 一致，否则面板比格子高、底下空出一条
      const ch = Math.round(L.fs * (land ? 4.4 : 3.9));
      bodyH = Math.round(L.fs * 0.4) + rows * (ch + gap);
    }
    // 回顾要一屏能读，比菜单面板宽；横屏设置两列，也要更宽才装得下两组
    const w2 = UI.view === "log"
      ? (land ? Math.min(L.viewW * 0.78, 1100) : L.viewW * 0.92)
      : UI.view === "settings"
        ? (land ? Math.min(L.viewW * 0.78, 1180) : L.viewW * 0.88)
        : w;
    const pad2 = Math.round(w2 * 0.055);
    // 存档页的脚注只有一行，按菜单页的 footH 留位会在格子下面空出一条空洞；
    // 设置页的说明文案 P97 已删，再按 footH 留就是一块纯空。
    const footUsed = (UI.view === "save" || UI.view === "load")
      ? Math.round(L.fs * 1.6)
      : UI.view === "settings" ? Math.round(L.fs * 0.45)
        // P102：菜单页最后一项就是「回到标题」，脚注区没有字可写 —— 按 footH 留 42px
        // 会在列表下面挂一块空幕，背景台词从缝里透出来，一眼就是没画完。
        : UI.view === "menu" ? Math.round(L.fs * 0.5) : footH;
    const h = Math.min(headH + bodyH + footUsed + pad2, L.viewH * (land ? 0.96 : 0.88));
    // 竖屏做成"底部抽屉"：贴屏底、左右留 3% 边。原来垂直居中浮在半空，
    // 上下各一整块黑，看着像一张贴在墙上的纸。
    const y = land
      ? (L.viewH - h) / 2
      : L.viewH - h - Math.round(Math.min(L.viewW, L.viewH) * 0.03);
    return {x: (L.viewW - w2) / 2, y: y, w: w2, h: h, pad: pad2, headH: headH};
  }

  function hit(id, x, y, w, h) { UI.rects.push({id: id, x: x, y: y, w: w, h: h}); }

  function uiButton(id, x, y, w, h, label, opts) {
    const o = opts || {};
    const on = !!o.on;
    const r = Math.round(Math.min(h / 2, 18));
    roundRect(x, y, w, h, r, on ? (o.accent || "#4f8cff") : "rgba(255,255,255,.075)");
    if (!on) {
      ctx.save();
      ctx.strokeStyle = "rgba(255,255,255,.12)";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(x + r, y);
      ctx.arcTo(x + w, y, x + w, y + h, r);
      ctx.arcTo(x + w, y + h, x, y + h, r);
      ctx.arcTo(x, y + h, x, y, r);
      ctx.arcTo(x, y, x + w, y, r);
      ctx.closePath();
      ctx.stroke();
      ctx.restore();
    }
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillStyle = on ? "#fff" : (o.dim ? "rgba(240,244,255,.45)" : "rgba(240,244,255,.92)");
    ctx.font = (o.weight || 600) + " " + (o.fs || Math.round(h * 0.30)) + "px " + FACE;
    ctx.fillText(label, x + w / 2, y + h / 2 + 1);
    ctx.textAlign = "left";
    ctx.textBaseline = "alphabetic";
    if (o.disabled) return;
    hit(id, x, y, w, h);
  }

  // 画面方向的三档文字：菜单里直接点一次循环切换，不用再进「设置 → 画面方向」
  function orientLabel() {
    return PREF.orient === "portrait" ? "竖屏"
      : PREF.orient === "landscape" ? "横屏" : "自动";
  }

  function drawMenuList(x, y, w, p) {
    const items = [
      ["resume", "继续游戏"],
      ["toLog", "回顾台词"],
      ["toSave", "保存进度"],
      ["toLoad", "读取进度"],
      ["skip", PREF.skip ? "快进 · 已开" : "快进 · 关", 1],
      ["autoTgl", PREF.auto ? "自动 · " + PREF.auto + " 秒" : "自动 · 关", 1],
      // P102：演出模式（竖 / 横 / 自动）提到菜单第一层 —— 手机上换个握法是很高的频操作，
      // 藏进设置里要点三层，玩家不会去点。
      ["orient", "画面方向 · " + orientLabel(), 1],
      ["toSet", "设置"],
      ["toTitle", "回到标题"],
    ];
    const land = L.landscape;
    const cols = land ? 2 : 1;
    const perCol = Math.ceil(items.length / cols);
    const colGap = Math.round(L.fs * 0.6);
    const colW = (w - colGap * (cols - 1)) / cols;
    const rowH = menuRowH();
    const gap = menuGap();
    const padX = Math.round(L.fs * 0.66);
    const top = y + Math.round(L.fs * 0.35);
    items.forEach((pair, idx) => {
      const id = pair[0];
      const label = pair[1];
      const toggle = !!pair[2];
      const on = id === "resume"
        || (id === "skip" && !!PREF.skip)
        || (id === "autoTgl" && !!PREF.auto)
        // 画面方向亮着 = 已经锁定了一个方向（自动时不高亮，代表"跟着手机转"）
        || (id === "orient" && PREF.orient !== "auto");
      const ci = Math.floor(idx / perCol);
      const ri = idx % perCol;
      const bx = x + ci * (colW + colGap);
      const by = top + ri * (rowH + gap);
      // P97：行不再各套一层圆角底 —— 八个盒子叠在一个大盒子里，一眼就是"设置页"。
      // 现在只留选中态和分隔线，字直接站在幕上。
      if (on) {
        roundRect(bx, by, colW, rowH, Math.round(rowH * 0.18), "rgba(79,140,255,.10)");
        roundRect(bx, by + Math.round(rowH * 0.26),
                  Math.max(3, Math.round(rowH * 0.055)), rowH - Math.round(rowH * 0.52),
                  2, "#4f8cff");
      }
      if (cols === 1 && idx + 1 < items.length) {
        ctx.save();
        ctx.strokeStyle = "rgba(255,255,255,.055)";
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(bx + padX, by + rowH + Math.round(gap / 2) + 0.5);
        ctx.lineTo(bx + colW - padX * 0.4, by + rowH + Math.round(gap / 2) + 0.5);
        ctx.stroke();
        ctx.restore();
      }
      ctx.textAlign = "left";
      ctx.textBaseline = "middle";
      ctx.fillStyle = on ? "#eaf1ff" : "rgba(240,244,255,.88)";
      ctx.font = (on ? 600 : 500) + " " + Math.round(L.fs * 0.62) + "px " + FACE;
      ctx.fillText(label, bx + padX, by + rowH / 2);

      const ax = bx + colW - padX * 0.7;
      const ay = by + rowH / 2;
      if (toggle) {
        // 开关：右侧一个小圆点，开=蓝、关=灰，比写「已开/关」更省眼
        ctx.beginPath();
        ctx.arc(ax - Math.round(L.fs * 0.2), ay, Math.max(3, Math.round(L.fs * 0.14)), 0, Math.PI * 2);
        ctx.fillStyle = on ? "#4f8cff" : "rgba(240,244,255,.20)";
        ctx.fill();
      } else {
        const s3 = Math.round(L.fs * 0.18);
        ctx.strokeStyle = "rgba(240,244,255,.28)";
        ctx.lineWidth = Math.max(1.5, Math.round(L.fs * 0.06));
        ctx.beginPath();
        ctx.moveTo(ax - s3 * 0.7, ay - s3);
        ctx.lineTo(ax + s3 * 0.3, ay);
        ctx.lineTo(ax - s3 * 0.7, ay + s3);
        ctx.stroke();
      }
      hit(id, bx, by, colW, rowH);
    });

    ctx.textAlign = "left";
  }

  function drawSlotCard(id, x, y, w, h, d, saving, no) {
    const empty = !d;
    const r = Math.round(Math.min(h / 6, 16));
    // P98：有档的格子铺一张当时的背景图。
    // 原来有档和空档长得一样（都是一行字），六个格子读起来是张列表；
    // 铺上图之后"哪一幕"不用读字就认出来了。老档没有 bg 字段 → 退回实底，不报错。
    const shot = empty ? null : (assets[d.bg] || (d.bg ? assets[d.bg + "_p"] : null));
    if (!empty && !shot) roundRect(x, y, w, h, r, "rgba(255,255,255,.085)");
    if (shot) {
      ctx.save();
      pathRound(x, y, w, h, r);
      ctx.clip();
      // cover 裁切、纵向偏上：背景的信息基本都在上半部，居中会把关键区域切掉
      const s = Math.max(w / shot.width, h / shot.height);
      const iw = shot.width * s;
      const ih = shot.height * s;
      ctx.drawImage(shot, x + (w - iw) / 2, y + (h - ih) * 0.35, iw, ih);
      // 左重右轻的压暗：文字压在左侧，右边把画面留出来
      const sg = ctx.createLinearGradient(x, y, x + w, y);
      sg.addColorStop(0, "rgba(6,8,12,.80)");
      sg.addColorStop(0.55, "rgba(6,8,12,.52)");
      sg.addColorStop(1, "rgba(6,8,12,.28)");
      ctx.fillStyle = sg;
      ctx.fillRect(x, y, w, h);
      ctx.restore();
    }
    ctx.save();
    if (empty) ctx.setLineDash([Math.max(4, Math.round(L.fs * 0.17)), Math.max(4, Math.round(L.fs * 0.15))]);
    ctx.strokeStyle = empty ? "rgba(255,255,255,.10)" : "rgba(255,255,255,.15)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
    ctx.stroke();
    ctx.restore();

    const ix = x + Math.round(w * 0.055);
    const avail = w - Math.round(w * 0.055) * 2;   // 卡片里能写字的内宽
    ctx.textAlign = "left";
    ctx.textBaseline = "top";
    ctx.fillStyle = empty ? "rgba(240,244,255,.38)" : "rgba(240,244,255,.96)";
    ctx.font = "600 " + Math.round(L.fs * 0.56) + "px " + FACE;
    ctx.fillText(no + " 号档", ix, y + Math.round(h * 0.11));

    ctx.font = "400 " + Math.round(L.fs * 0.46) + "px " + FACE;
    if (empty) {
      ctx.fillStyle = "rgba(240,244,255,.30)";
      ctx.fillText(saving ? "空 · 点这里存" : "空", ix, y + Math.round(h * 0.40));
    } else {
      ctx.fillStyle = "rgba(240,244,255,.72)";
      // P100：按卡片的真实内宽收字。原来 hard slice(0,16)，
      // 横屏三列时卡片比竖屏两列窄，16 个中文字会横着压到隔壁格子上。
      ctx.fillText(ellipsisTo(String(d.say || "（存档）"), avail), ix, y + Math.round(h * 0.34));
      ctx.fillStyle = "rgba(240,244,255,.34)";
      ctx.font = "400 " + Math.round(L.fs * 0.38) + "px " + FACE;
      ctx.fillText(ellipsisTo(stamp(d.t), avail), ix, y + h - Math.round(L.fs * 0.70));
    }
    ctx.textBaseline = "alphabetic";
    if (!saving && empty) return;
    hit(id, x, y, w, h);
  }

  function drawSlots(x, y, w, p) {
    const land = L.landscape;
    const cols = land ? 3 : 2;
    const gap = Math.round(L.fs * 0.55);
    const cw = (w - gap * (cols - 1)) / cols;
    const ch = Math.round(L.fs * (land ? 4.4 : 3.9));
    const saving = UI.view === "save";
    for (let i = 0; i < slotCount(); i++) {
      const rr = Math.floor(i / cols);
      const cc = i % cols;
      const bx = x + cc * (cw + gap);
      const by = y + Math.round(L.fs * 0.4) + rr * (ch + gap);
      drawSlotCard("s" + i, bx, by, cw, ch, readSlot(i), saving, i + 1);
    }
    // 脚注：左边一句说明，右边「清空存档」。存不下的时候这里换成红字 ——
    // 静默失败最难查：玩家以为存上了，下次打开什么都没有。
    const fy = p.y + p.h - Math.round(L.fs * 1.0);
    const done = !!UI.wipeDone && performance.now() - UI.wipeDone < 2600;
    if (UI.storeErr) {
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillStyle = "rgba(255,120,120,.92)";
      ctx.font = "600 " + Math.round(L.fs * 0.5) + "px " + FACE;
      ctx.fillText("存不下了：浏览器存储已满或被禁止", p.x + p.w / 2, fy);
      ctx.textAlign = "left";
      ctx.textBaseline = "alphabetic";
      return;
    }
    if (done) {
      ctx.textAlign = "left";
      ctx.textBaseline = "middle";
      ctx.fillStyle = "rgba(120,220,160,.9)";
      ctx.font = "600 " + Math.round(L.fs * 0.46) + "px " + FACE;
      ctx.fillText("已清空本作品的进度", p.x, fy);
      ctx.textAlign = "left";
      ctx.textBaseline = "alphabetic";
      return;
    }
    const confirm = !!UI.wipeConfirm && performance.now() - UI.wipeConfirm < 4000;
    const bh = Math.round(L.fs * 1.3);
    // 左边「导出 / 导入」：手机端存档跟 origin 走，换文件就看不见 —— 这是唯一的搬运口
    const bwS = Math.round(L.fs * 3.2);
    const gapB = Math.round(L.fs * 0.3);
    uiButton("exp", p.x, fy - bh / 2, bwS, bh, "导出", {fs: Math.round(L.fs * 0.44)});
    uiButton("imp", p.x + bwS + gapB, fy - bh / 2, bwS, bh, "导入", {fs: Math.round(L.fs * 0.44)});
    const bw = Math.round(L.fs * 4.6);
    uiButton("wipe", p.x + p.w - bw, fy - bh / 2, bw, bh,
             confirm ? "再点一次" : "清空存档",
             {fs: Math.round(L.fs * 0.46), dim: !confirm, on: confirm,
              accent: "rgba(190,60,60,.9)", weight: confirm ? 700 : 500});

    // 中间一行：导出/导入的结果（做成败色），平时是一句提示
    const nx = p.x + bwS * 2 + gapB + Math.round(L.fs * 0.45);
    const nw = p.w - (bwS * 2 + gapB) - bw - Math.round(L.fs * 0.9);
    const fresh = !!UI.notice && performance.now() - (UI.noticeAt || 0) < 4000;
    ctx.textAlign = "left";
    ctx.textBaseline = "middle";
    if (fresh) {
      ctx.fillStyle = UI.noticeOk ? "rgba(120,220,160,.92)" : "rgba(255,120,120,.92)";
      ctx.font = "600 " + Math.round(L.fs * 0.42) + "px " + FACE;
      let t = UI.notice;
      if (ctx.measureText(t).width > nw) {
        let n = t.length;
        while (n > 1 && ctx.measureText(t.slice(0, n) + "…").width > nw) n--;
        t = t.slice(0, n) + "…";
      }
      ctx.fillText(t, nx, fy);
    } else {
      // 写不进存档要当场说清楚，不能"点了没反应、玩家以为存上了"
      const note = UI.storeErr === 2 ? "这局还没在跑，没有可存的进度"
                 : UI.storeErr === 1 ? "这台机器写不进存档（隐私模式或空间不足）"
                 : (saving ? "存在本机 · 换文件前先导出" : "点格子读档");
      ctx.fillStyle = UI.storeErr ? "rgba(255,150,120,.80)" : "rgba(240,244,255,.30)";
      ctx.font = "400 " + Math.round(L.fs * 0.42) + "px " + FACE;
      ctx.fillText(note, nx, fy);
    }
    ctx.textBaseline = "alphabetic";
  }

  // 回顾：手机上一划一点，台词就过去了，漏掉的得能翻回来。
  // 一页放满就停（不做自由滚动 —— canvas 里滚动条手感差），底部用「更早 / 更晚」翻页。
  function drawLog(x, y, w, p) {
    const rows = logRows();
    const rowH = Math.round(L.fs * 1.45);
    const gap = Math.round(L.fs * 0.3);
    const hist = state.history || [];
    const per = rows;
    const pages = Math.max(1, Math.ceil(hist.length / per));
    UI.logPage = Math.min(Math.max(0, UI.logPage || 0), pages - 1);

    let yy = y + Math.round(L.fs * 0.5);
    if (!hist.length) {
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillStyle = "rgba(240,244,255,.4)";
      ctx.font = "400 " + Math.round(L.fs * 0.6) + "px " + FACE;
      ctx.fillText("还没有可回顾的台词", x + w / 2, y + rows * rowH / 2);
      ctx.textAlign = "left";
      return;
    }

    const end = hist.length - UI.logPage * per;
    const start = Math.max(0, end - per);
    const vis = visual();
    for (let i = start; i < end; i++) {
      const h = hist[i];
      const hl = yy + (rowH - L.fs * 1.2) / 2;
      // 一行的结构：名字（角色色）+ 台词，超宽就截断加省略号
      let cx = x;
      if (h.char) {
        ctx.font = "600 " + Math.round(L.fs * 0.58) + "px " + FACE;
        ctx.fillStyle = vis.accent;
        ctx.textAlign = "left";
        ctx.textBaseline = "top";
        ctx.fillText(h.char, cx, hl + Math.round(L.fs * 0.06));
        cx += ctx.measureText(h.char).width + Math.round(L.fs * 0.6);
      }
      ctx.font = "400 " + Math.round(L.fs * 0.58) + "px " + FACE;
      ctx.fillStyle = "rgba(240,244,255,.86)";
      ctx.textAlign = "left";
      ctx.textBaseline = "top";
      let t = h.text || "";
      const room = x + w - cx;
      while (t.length > 1 && ctx.measureText(t).width > room) t = t.slice(0, -1);
      if (t !== (h.text || "")) t = t.slice(0, Math.max(1, t.length - 1)) + "…";
      ctx.fillText(t, cx, hl);
      yy += rowH + gap;
    }

    const per2 = per;
    const total = hist.length;
    const olderAllowed = (UI.logPage + 1) * per2 < total;
    const bw = Math.round(w * 0.28);
    const bh = Math.round(L.fs * 1.6);
    const by = p.y + p.h - Math.round(L.fs * 2.2);
    uiButton("logOlder", x, by, bw, bh, "更早", {dim: !olderAllowed, fs: Math.round(bh * 0.44)});
    uiButton("logNewer", x + w - bw, by, bw, bh, "更晚",
             {dim: UI.logPage === 0, fs: Math.round(bh * 0.44)});
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillStyle = "rgba(240,244,255,.32)";
    ctx.font = "400 " + Math.round(L.fs * 0.46) + "px " + FACE;
    ctx.fillText("第 " + (UI.logPage + 1) + " / " + pages + " 页 · 按更早往回翻",
                 x + w / 2, by + bh / 2);
    ctx.textAlign = "left";
  }

  /* 第一次打开作品的一次性说明。手机上没键盘没右键，用户得先知道点哪、怎么叫菜单 ——
     这一段是「别人愿不愿意继续玩」的门槛，比任何视觉打磨都值。 */
  function drawGuide() {
    const a = Math.min(1, (performance.now() - (state.guideT0 || 0)) / 200);
    ctx.save();
    ctx.globalAlpha = a;
    ctx.fillStyle = "rgba(4,6,12,.78)";
    ctx.fillRect(0, 0, L.viewW, L.viewH);

    const w = L.landscape ? Math.min(L.viewW * 0.54, 820) : L.viewW * 0.86;
    const pad = Math.round(w * 0.058);
    const titleH = Math.round(L.fs * 2.1);
    const rowH = Math.round(L.fs * (L.landscape ? 2.05 : 2.35));
    const btnH = Math.round(L.fs * 2.1);
    const h = titleH + 3 * rowH + btnH + pad * 2;
    const x = (L.viewW - w) / 2;
    const y = (L.viewH - h) / 2;
    const rr = Math.round(w * 0.038);
    roundRect(x, y, w, h, rr, "rgba(17,20,29,.98)");
    ctx.strokeStyle = "rgba(255,255,255,.10)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(x + rr, y);
    ctx.arcTo(x + w, y, x + w, y + h, rr);
    ctx.arcTo(x + w, y + h, x, y + h, rr);
    ctx.arcTo(x, y + h, x, y, rr);
    ctx.arcTo(x, y, x + w, y, rr);
    ctx.closePath();
    ctx.stroke();

    ctx.textAlign = "left";
    ctx.textBaseline = "middle";
    ctx.fillStyle = "#f2f5ff";
    ctx.font = "700 " + Math.round(L.fs * 0.86) + "px " + FACE;
    ctx.fillText("怎么玩", x + pad, y + pad + titleH / 2 - Math.round(L.fs * 0.2));

    const rows = [
      ["轻点画面", "推进一句；读到一半再点，整句立刻显示"],
      ["长按画面", "打开菜单：存档、读档、回顾台词、设置"],
      ["选项出现", "直接点你想选的那一句"],
    ];
    let yy = y + pad + titleH;
    const keyW = Math.round(L.fs * 3.4);
    for (const r of rows) {
      roundRect(x + pad, yy + Math.round(rowH * 0.18), keyW,Math.round(rowH * 0.62),
                Math.round(rowH * 0.2), "rgba(79,140,255,.16)");
      ctx.fillStyle = "#8fb4ff";
      ctx.font = "600 " + Math.round(L.fs * 0.5) + "px " + FACE;
      ctx.textAlign = "center";
      ctx.fillText(r[0], x + pad + keyW / 2, yy + rowH / 2 - Math.round(L.fs * 0.06));
      ctx.textAlign = "left";
      ctx.fillStyle = "rgba(240,244,255,.72)";
      ctx.font = "400 " + Math.round(L.fs * 0.5) + "px " + FACE;
      ctx.fillText(r[1], x + pad + keyW + Math.round(L.fs * 0.7), yy + rowH / 2);
      yy += rowH;
    }

    const bh = btnH;
    uiButton("guideOk", x + pad, y + h - pad - bh, w - pad * 2, bh, "开始",
             {on: true, fs: Math.round(bh * 0.44)});
    ctx.restore();
  }

  function drawSettings(x, y, w, p) {
    const groups = [
      ["文字速度", "speed", ["慢", "中", "快"], [0.6, 1, 1.6], PREF.speed],
      ["字号", "text", ["小", "中", "大"], [0.9, 1, 1.15], PREF.text],
      ["音量", "vol", ["小", "中", "大"], [0.4, 0.7, 1], PREF.vol],
      ["自动翻页", "auto", ["关", "3 秒", "6 秒"], [0, 3, 6], PREF.auto],
      // 弱机自救：降渲染分辨率，字和图会软一点，但帧率能上来
      ["画面质量", "quality", ["流畅", "标准", "清晰"], [0.62, 0.82, 1], PREF.quality],
      // 手选方向：横屏作品在竖持手机上也能玩（画布变成上下留黑的一段横屏），
      // 反过来竖屏作品横持手机也能强制竖排 —— 不用真的转手机
      ["画面方向", "orient", ["自动", "竖屏", "横屏"],
       ["auto", "portrait", "landscape"], PREF.orient || "auto"],
      // P101：对话框占多大画面。三档都保证"读得清"，区别在于挡住多少画面：
      // 经典 = 不透明底板（传统 galgame 手感）；幕 = 全宽暗幕、无框（默认，画面留得住）；
      // 字幕 = 同样无框但更轻，几乎像影院字幕。
      ["对话框", "dlg", ["经典", "幕", "字幕"], [0, 1, 2], PREF.dlg],
    ];
    const rowH = setRowH();
    const gap = Math.round(L.fs * 0.5);
    // P84：横屏改两列（3 组一列）。单列 6 组在 390 高的横屏里顶到上下边，没有留白。
    const cols = L.landscape ? 2 : 1;
    const colGap = Math.round(L.fs * 1.1);
    const colW = (w - colGap * (cols - 1)) / cols;
    const perCol = Math.ceil(groups.length / cols);
    for (let gi = 0; gi < groups.length; gi++) {
      const g = groups[gi];
      const label = g[0], key = g[1], labels = g[2], vals = g[3], cur = g[4];
      const ci = Math.floor(gi / perCol);
      const rowIdx = ci === 0 ? gi : gi - perCol;
      const gx = x + ci * (colW + colGap);
      const yy = y + gap + rowIdx * (rowH + gap);
      ctx.textAlign = "left";
      ctx.textBaseline = "middle";
      ctx.fillStyle = "rgba(240,244,255,.92)";
      ctx.font = "500 " + Math.round(L.fs * 0.56) + "px " + FACE;
      ctx.fillText(label, gx, yy + rowH / 2);

      const segW = Math.round(colW * (cols === 2 ? 0.54 : 0.44));
      const sx = gx + colW - segW;
      const bw = segW / 3;
      const bh = Math.round(L.fs * 1.5);
      const sy = yy + (rowH - bh) / 2;
      // P97：三个独立小盒 -> 一条分段控件。
      // 三个各带圆角底和描边的小盒并排，是"三个按钮"，玩家每次都要认一遍哪个是选中的；
      // 一条胶囊底 + 里面一块实心滑块，位置本身就说清了"三选一、当前在哪个"。
      roundRect(sx, sy, segW, bh, bh / 2, "rgba(255,255,255,.055)");
      for (let i = 0; i < 3; i++) {
        const on = typeof cur === "string"
          ? cur === vals[i]
          : Math.abs(cur - vals[i]) < 0.001;
        const bx = sx + i * bw;
        if (on) {
          roundRect(bx + Math.max(2, Math.round(bw * 0.02)), sy + 2,
                    bw - Math.max(2, Math.round(bw * 0.02)) * 2, bh - 4,
                    (bh - 4) / 2, "#4f8cff");
        }
        ctx.save();
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillStyle = on ? "#fff" : "rgba(240,244,255,.58)";
        ctx.font = (on ? "600 " : "500 ") + Math.round(bh * (cols === 2 ? 0.36 : 0.40)) + "px " + FACE;
        ctx.fillText(labels[i], bx + bw / 2, sy + bh / 2 + 1);
        ctx.restore();
        hit(key + ":" + i, bx, sy, bw, bh);
      }
      // 行分隔线：六组排下来没有分隔就是一张"表单"，有线才像"设置清单"
      if (rowIdx < perCol - 1) {
        ctx.save();
        ctx.strokeStyle = "rgba(255,255,255,.06)";
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(gx, yy + rowH + gap / 2);
        ctx.lineTo(gx + colW, yy + rowH + gap / 2);
        ctx.stroke();
        ctx.restore();
      }
    }
    ctx.textAlign = "left";
  }

  function drawMenu() {
    const p = menuPanel();
    const vis = visual();
    const a = Math.min(1, (performance.now() - UI.t0) / 160);

    ctx.save();
    // P101：原来是 93% 的一块死黑 —— 打开菜单等于把画面关掉，回来还要重新认这是哪一幕。
    // 改成上浅下深的一层膜：看得见画面，还知道自己在哪，面板浮在膜上而不是浮在黑洞里。
    const veil = ctx.createLinearGradient(0, 0, 0, L.viewH);
    veil.addColorStop(0, "rgba(4,6,12," + (0.28 * a) + ")");
    veil.addColorStop(1, "rgba(4,6,12," + (0.66 * a) + ")");
    ctx.fillStyle = veil;
    ctx.fillRect(0, 0, L.viewW, L.viewH);
    ctx.globalAlpha = a;
    ctx.translate(0, (1 - a) * Math.round(L.viewH * 0.03));

    const rr = Math.round(p.w * 0.035);
    // P84：菜单面板也带投影，否则它浮在暗背景上没有厚度，像个纯色矩形
    // P101：投影和底都收一档 —— 底 0.98 的实心块在浅色画面上就是一块黑板
    ctx.save();
    ctx.shadowColor = "rgba(0,0,0,.45)";
    ctx.shadowBlur = Math.round(L.fs * 1.2);
    ctx.shadowOffsetY = Math.round(L.fs * 0.35);
    // P102：菜单是一列字，透出背景就是"字压在台词上"。设置/存档/回顾是有卡片的，透一点反而透气。
    roundRect(p.x, p.y, p.w, p.h, rr,
              UI.view === "menu" ? "rgba(13,16,24,.970)" : "rgba(13,16,24,.90)");
    ctx.restore();
    ctx.strokeStyle = "rgba(255,255,255,.09)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(p.x + rr, p.y);
    ctx.arcTo(p.x + p.w, p.y, p.x + p.w, p.y + p.h, rr);
    ctx.arcTo(p.x + p.w, p.y + p.h, p.x, p.y + p.h, rr);
    ctx.arcTo(p.x, p.y + p.h, p.x, p.y, rr);
    ctx.arcTo(p.x, p.y, p.x + p.w, p.y, rr);
    ctx.closePath();
    ctx.stroke();

    const pad = p.pad;
    const headH = p.headH;
    const titles = {menu: "菜单", save: "保存进度", load: "读取进度", settings: "设置", log: "回顾台词"};
    ctx.textAlign = "left";
    ctx.textBaseline = "middle";
    ctx.fillStyle = "#f2f5ff";
    ctx.font = "700 " + Math.round(L.fs * 0.86) + "px " + FACE;
    ctx.fillText(titles[UI.view] || "菜单", p.x + pad, p.y + headH / 2 + Math.round(L.fs * 0.1));

    const xw = Math.round(L.fs * 1.1);
    uiButton(UI.view === "menu" ? "close" : "back",
             p.x + p.w - pad - xw, p.y + headH / 2 - xw / 2, xw, xw,
             UI.view === "menu" ? "×" : "‹", {fs: Math.round(xw * 0.62)});

    const innerX = p.x + pad;
    const innerW = p.w - pad * 2;
    const top = p.y + headH;

    if (UI.view === "menu") drawMenuList(innerX, top, innerW, p);
    else if (UI.view === "save" || UI.view === "load") drawSlots(innerX, top, innerW, p);
    else if (UI.view === "log") drawLog(innerX, top, innerW, p);
    else drawSettings(innerX, top, innerW, p);

    ctx.restore();
  }

  function act(id) {
    if (id === "wipe") {
      // 第一次点只是"亮起来问一句"，4 秒内再点才真清 —— 手指在手机上很容易点歪
      if (UI.wipeConfirm && performance.now() - UI.wipeConfirm < 4000) {
        storeWipe();
      } else {
        UI.wipeConfirm = performance.now();
      }
      UI.t0 = performance.now();
      return;
    }
    UI.wipeConfirm = 0;
    if (id === "exp") {
      const code = storeExportCode();
      if (!code) { notice("还没有可导出的存档", false); return; }
      const ok = storeExportFile(code);
      notice(ok ? "已导出到下载目录" : "导出被拦，换个浏览器试", ok);
      return;
    }
    if (id === "imp") { storeImportFile(); return; }
    if (id === "close") { UI.open = false; return; }
    if (id === "back") { UI.view = "menu"; return; }
    if (id === "resume") { UI.open = false; return; }
    if (id === "skip") { PREF.skip = PREF.skip ? 0 : 1; savePrefs(); state.skipAt = 0; return; }
    // P102：点一次循环 自动 → 竖屏 → 横屏 → 自动。切完立即按新方向重算布局（fit 内部会 rewrap 正文）
    if (id === "orient") {
      PREF.orient = PREF.orient === "auto" ? "portrait"
        : PREF.orient === "portrait" ? "landscape" : "auto";
      savePrefs();
      fit();
      return;
    }
    if (id === "autoTgl") { PREF.auto = PREF.auto ? 0 : 3; savePrefs(); state.autoAt = 0; return; }
    if (id === "toSave") { UI.view = "save"; return; }
    if (id === "toLoad") { UI.view = "load"; return; }
    if (id === "toLog") { UI.view = "log"; UI.logPage = 0; return; }
    if (id === "logOlder") {
      const per = logRows();
      const maxPage = Math.max(0, Math.ceil((state.history || []).length / per) - 1);
      UI.logPage = Math.min(maxPage, (UI.logPage || 0) + 1);
      return;
    }
    if (id === "logNewer") { UI.logPage = Math.max(0, (UI.logPage || 0) - 1); return; }
    if (id === "toSet") { UI.view = "settings"; return; }
    if (id === "toTitle") {
      autoSave();
      UI.open = false;
      state.scene = "title";
      return;
    }
    if (/^s[0-9]$/.test(id)) {
      const i = Number(id.slice(1));
      if (UI.view === "save") writeSlot(i);
      else loadSlot(i);
      return;
    }
    const parts = String(id).split(":");
    if (parts.length !== 2) return;
    const key = parts[0];
    const i = Number(parts[1]) || 0;
    if (key === "speed") PREF.speed = [0.6, 1, 1.6][i];
    else if (key === "text") { PREF.text = [0.9, 1, 1.15][i]; savePrefs(); fit(); return; }
    else if (key === "vol") {
      PREF.vol = [0.4, 0.7, 1][i];
      bgmVolume = PREF.vol;
      if (bgm) bgm.volume = PREF.vol;
    } else if (key === "auto") PREF.auto = [0, 3, 6][i];
    else if (key === "quality") { PREF.quality = [0.62, 0.82, 1][i]; savePrefs(); fit(); return; }
    else if (key === "orient") {
      PREF.orient = ["auto", "portrait", "landscape"][i];
      savePrefs();
      fit();          // 立刻按新方向重算布局（画布 letterbox 自己居中；fit 内部会 rewrap 正文）
      return;
    }
    // P101：对话框样式只影响下一帧怎么画，不碰布局，存完回设置页即可看到效果
    else if (key === "dlg") PREF.dlg = [0, 1, 2][i];
    savePrefs();
  }

  function onMenuTap(p) {
    for (const r of UI.rects) {
      if (p.x >= r.x && p.x <= r.x + r.w && p.y >= r.y && p.y <= r.y + r.h) {
        act(r.id);
        return;
      }
    }
    const pn = menuPanel();
    const inside = p.x >= pn.x && p.x <= pn.x + pn.w && p.y >= pn.y && p.y <= pn.y + pn.h;
    if (!inside) UI.open = false;
  }

})();
