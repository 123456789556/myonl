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

  // 玩家设置（本机 localStorage，与游戏无关）：文字速度 / 字号 / 音量 / 自动翻页 / 画质 / 快进 / 画面方向
  const PREF = {speed: 1, text: 1, vol: 0.7, auto: 0, quality: 1, skip: 0, orient: "auto"};
  const PREF_KEY = "myonl:prefs";
  const UI = {open: false, view: "menu", rects: [], t0: 0, logPage: 0};
  let pack = null;
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

  // 右上角喇叭：逻辑坐标下 ~43 个屏幕像素，游戏内常驻
  function muteRect() {
    const s = Math.min(160, Math.max(60, Math.round(Math.min(L.viewW, L.viewH) * 0.11)));
    const m = Math.round(Math.min(L.viewW, L.viewH) * 0.03);
    return { x: L.viewW - s - m, y: m, w: s, h: s };
  }

  function drawMute() {
    if (state.scene !== "game" || state.error) return;
    const r = muteRect();
    ctx.save();
    ctx.globalAlpha = audioOn ? 0.5 : 0.85;
    roundRect(r.x, r.y, r.w, r.h, Math.round(r.h / 4), "rgba(12,14,20,.84)");
    ctx.globalAlpha = 1;
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

  // 存档 key：标题 + 剧本名 + 指令条数。只按标题会串档——两个游戏都叫"我的游戏"时，
  // 后开的那个会读到前一个的存档（进度对不上，甚至跳到不存在的 label）。
  function saveKey() {
    const t = (pack && pack.title) || "untitled";
    const s = (pack && pack.script) || "";
    const n = (pack && pack.ins && pack.ins.length) || 0;
    return "myonl:auto:" + t + ":" + s + ":" + n;
  }

  function autoSave() {
    try { localStorage.setItem(saveKey(), vm.save()); } catch (e) { /* 隐私模式禁写 */ }
  }

  function startGame(fromSave) {
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
    let seenHelp = false;
    try { seenHelp = localStorage.getItem("myonl:helpSeen") === "1"; } catch (err) { seenHelp = false; }
    state.guide = !seenHelp;
    state.guideT0 = performance.now();
    cam.zoom = 1; cam.zoomDur = 0; cam.zoomTo = 1; cam.zoomFrom = 1;
    cam.panX = 0; cam.panY = 0; cam.panDur = 0;
    cam.shakeUntil = 0;
    if (fromSave) {
      const saved = localStorage.getItem(saveKey());
      if (saved) vm.load(saved);
    } else {
      vm.restart();
      try { localStorage.removeItem(saveKey()); } catch (e) { /* ignore */ }
    }
    // 读档后补一次"当前画面"：让 bg/立绘/CG/镜头/前景先对上，再继续推进
    state.bg = vm.state.bg || "";
    state.cg = vm.state.cg || "";
    state.sprites = (vm.state.sprites || []).slice();
    state.fg = vm.state.fg || null;
    state.anim = vm.state.anim || {};
    state.video = vm.state.video || null;
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
      try { localStorage.setItem("myonl:helpSeen", "1"); } catch (err) { /* 隐私模式 */ }
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
  // 帧图懒加载；还没加载完就把上一帧继续贴着，避免黑一下。
  const videoCache = {};
  function videoFrameImg() {
    const v = state.video;
    if (!v || !v.name) return null;
    const seq = (pack && pack.videos && pack.videos[v.name]) || null;
    if (!seq || !seq.length) return null;
    const fps = v.fps > 0 ? v.fps : 24;
    const len = seq.length;
    const raw = Math.floor(((performance.now() - (v.t0 || 0)) / 1000) * fps);
    const idx = ((raw % len) + len) % len;
    const key = v.name + "#" + idx;
    let img = videoCache[key];
    if (!img) {
      img = new Image();
      img.src = seq[idx];
      videoCache[key] = img;
    }
    if (img.complete && img.naturalWidth) return img;
    for (let d = 1; d < len; d++) {
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
    const prev = state.fadeFromBg && assets[state.fadeFromBg];
    const img = state.bg && assets[state.bg];
    if (prev && t < 1) blitCover(prev, 1);
    if (img) {
      // @transition wipe / slide：新图按方向推进来；dissolve 就是普通淡入
      const mode = state.transMode || "dissolve";
      if (prev && t < 1 && mode !== "dissolve") {
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
        blitCover(img, 1);
        ctx.restore();
      } else {
        blitCover(img, prev && t < 1 ? t : 1);
      }
      return;
    }
    const g = ctx.createLinearGradient(0, 0, 0, L.viewH);
    g.addColorStop(0, "#1a1d2b");
    g.addColorStop(1, "#0b0d14");
    ctx.save();
    ctx.globalAlpha = prev ? t : 1;
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

  function drawSprites() {
    const list = state.sprites || [];
    if (!list.length) return;
    const n = list.length;
    const baseH = L.spriteH;
    const k = L.viewW / 1280;   // 剧本里的像素值以桌面 1280 为基准
    const nowT = performance.now() / 1000;
    list.forEach((sp, i) => {
      const key = sp.expr ? `${sp.char}_${sp.expr}` : sp.char;
      const img = assets[key] || assets[sp.char];
      if (!img) return;
      const disp = animDisp(sp.char);
      const h = baseH * (disp.scale > 0 ? disp.scale : 1) * (L.landscape ? 1 : 0.95);
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
      const cx = (L.landscape && n === 1)
        ? L.viewW * 0.63 + disp.x * k
        : slotW * (i + 0.5) + disp.x * k;
      // 脚底锚点：竖屏让脚沉进去小半截（panelH 的 9%）——脚贴在面板上沿时，
      // 下面还有一大片地板，看着像浮在半空；让面板压住鞋尖，人才像站在前景。
      const bottom = (L.landscape
        ? L.viewH
        : L.panelY + Math.round(L.panelH * 0.09)) + disp.y * k;
      const t0 = (state.spriteAt && state.spriteAt[sp.char]) || 0;
      const fadeIn = t0 ? Math.min(1, (nowT - t0) / 0.26) : 1;
      if (fadeIn <= 0) return;
      const alpha = Math.max(0, Math.min(1, disp.alpha)) * fadeIn;
      if (alpha <= 0) return;
      const idle = idleMotion(i, nowT);
      ctx.save();
      if (alpha < 1) ctx.globalAlpha = alpha;
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

  function roundRect(x, y, w, h, r, fill, alpha) {
    ctx.save();
    if (alpha !== undefined) ctx.globalAlpha = alpha;
    const rr = Math.min(r, w / 2, h / 2);
    ctx.beginPath();
    ctx.moveTo(x + rr, y);
    ctx.arcTo(x + w, y, x + w, y + h, rr);
    ctx.arcTo(x + w, y + h, x, y + h, rr);
    ctx.arcTo(x, y + h, x, y, rr);
    ctx.arcTo(x, y, x + w, y, rr);
    ctx.closePath();
    if (fill) { ctx.fillStyle = fill; ctx.fill(); }
    ctx.restore();
  }

  /* 面板高度：竖屏固定占约三分之一屏（`L.panelH`），横屏跟台词行数走。
     竖屏为什么要固定：一句话就要演一个矮盒子，面板每句都变高变矮，立绘脚下还留一大块空，
     看着像没做完；固定成一条，立绘脚正好踩在上沿，对话框也不会跳。 */
  function panelRect() {
    const rows = Math.max(2, Math.min(L.maxTextRows, (state.lines || []).length || 2));
    const contentH = L.padY * 2 + rows * L.lineH + Math.round(L.fs * 0.7);
    const h = L.landscape
      ? Math.min(L.viewH * 0.46, contentH)
      : L.panelH;
    return {x: L.panelX, y: L.viewH - h - L.bottom, w: L.panelW, h: h, rows: rows};
  }

  /* 「#rrggbb + 透明度」：角色色要能当半透明底/描边用 */
  function hexA(hex, alpha) {
    const m = /^#?([0-9a-f]{6})$/i.exec(String(hex || "").trim());
    if (!m) return "rgba(79,140,255," + alpha + ")";
    const v = parseInt(m[1], 16);
    return "rgba(" + ((v >> 16) & 255) + "," + ((v >> 8) & 255) + "," + (v & 255) + "," + alpha + ")";
  }

  /* 面板底色：原来是一块死黑（rgba(10,12,18,.90)）压在背景上，边缘像贴了张黑纸。
     改为自上而下的深色渐变 + 顶部一道极淡的高光线，和底下的背景有过渡。 */
  function panelFill(x, y, w, h) {
    const g = ctx.createLinearGradient(0, y, 0, y + h);
    g.addColorStop(0, "rgba(20,23,32,.92)");
    g.addColorStop(1, "rgba(9,11,16,.96)");
    return g;
  }

  function panelHairline(x, y, w, r) {
    ctx.save();
    ctx.strokeStyle = "rgba(255,255,255,.08)";
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
    // 先垫一层不透明底：贴图皮肤本体常是半透明 PNG，不垫的话背景/立绘会透上来，
    // 台词就不好读了（桌面端皮肤是在底板上叠的，这里保持同样的观感）。
    // P84：垫底时带一道投影 —— 面板和背景之间没有过渡时，整块像切纸贴上去的。
    ctx.save();
    ctx.shadowColor = "rgba(0,0,0,.55)";
    ctx.shadowBlur = Math.round(L.fs * 0.9);
    ctx.shadowOffsetY = Math.round(L.fs * 0.28);
    roundRect(x, y, w, h, radius, panelFill(x, y, w, h));
    ctx.restore();
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
    panelHairline(x, y, w, radius);
    return rect;
  }

  function drawDialogue(vis) {
    if (!state.say || !state.lines) return;
    // 选项出现时不画对话框：否则上一句面板会压住选项（横屏 390 高时尤其明显）
    if (state.choice) return;
    const rect = drawPanel(vis);
    const say = state.say;

    if (say.char) {
      ctx.font = `600 ${L.nameSize}px ${FACE}`;
      const tw = ctx.measureText(say.char).width;
      const plateH = L.nameSize + 22;
      const plateX = rect.x + Math.round(L.marginX * 0.6);
      const plateY = rect.y - plateH - 14;
      const tint = say.color || vis.accent;
      // 名字牌：深色胶囊保证任何角色色都读得清，角色色只用于描边（纯当标签太淡就看不见字）
      roundRect(plateX, plateY, tw + 52, plateH, plateH / 2, "rgba(12,14,20,.92)");
      ctx.save();
      ctx.strokeStyle = hexA(tint, 0.62);
      ctx.lineWidth = 1;
      ctx.beginPath();
      const rrp = plateH / 2;
      ctx.moveTo(plateX + rrp, plateY);
      ctx.arcTo(plateX + tw + 52, plateY, plateX + tw + 52, plateY + plateH, rrp);
      ctx.arcTo(plateX + tw + 52, plateY + plateH, plateX, plateY + plateH, rrp);
      ctx.arcTo(plateX, plateY + plateH, plateX, plateY, rrp);
      ctx.arcTo(plateX, plateY, plateX + tw + 52, plateY, rrp);
      ctx.closePath();
      ctx.stroke();
      ctx.restore();
      ctx.fillStyle = vis.textColor;
      ctx.textBaseline = "middle";
      ctx.fillText(say.char, plateX + 26, plateY + plateH / 2);
    }

    const shown = typedCount();
    let left = shown;
    ctx.globalAlpha = 1;   // 面板/皮肤绘制可能留下半透明状态，台词必须不透明
    ctx.font = `${L.fs}px ${FACE}`;
    ctx.textBaseline = "top";
    const tx = rect.x + L.padX + vis.panel.padX;
    const maxRows = Math.min(rect.rows, L.maxTextRows);
    // 竖屏面板是固定高度（约占三分之一屏），台词就从顶部排：一行字居中的话，
    // 看着像「对话框里空了一大块」；从顶部起就是标准对话框，下面的留白是给后续行的。
    const ty = rect.y + L.padY + vis.panel.padY;
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
      const ax = rect.x + rect.w - Math.round(L.fs * 1.3);
      const ay = rect.y + rect.h - Math.round(L.fs * 1.1);
      // 一个会呼吸的小圆点，比原来的实心三角安静
      const pulse = 0.55 + 0.45 * (0.5 + 0.5 * Math.sin(performance.now() / 380));
      ctx.save();
      ctx.globalAlpha = pulse;
      ctx.fillStyle = vis.accent;
      ctx.beginPath();
      ctx.arc(ax, ay, Math.max(4, Math.round(L.fs * 0.28)), 0, Math.PI * 2);
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
    const centerY = Math.round(clampN(L.viewH * (0.66 - (dgr - 1) * 0.12),
                                      L.viewH * 0.42, L.viewH * 0.82));
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
      ctx.textAlign = "center";
      ctx.textBaseline = "bottom";
      ctx.fillStyle = "rgba(236,241,255,.9)";
      ctx.shadowColor = "rgba(0,0,0,.72)";
      ctx.shadowBlur = 12;
      const qBottom = startY - Math.round(bh * 0.55);
      const qCx = L.landscape ? x + bw / 2 : L.viewW / 2;
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
      ctx.fillRect(x + 1, y + Math.round(bh * 0.28), 3, Math.round(bh * 0.44));
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

  /* 标题页封面：拿工程里第一张背景图模糊铺满，比纯渐变更像"一个故事"而不是启动屏 */
  function titleCover() {
    const names = Object.keys(assets);
    if (!names.length) return null;
    return assets[names.find(n => /bg/i.test(n)) || names[0]];
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
      const heroName = Object.keys(assets).find(n => /全身/.test(n));
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

    // 底部信息卡：标题和按钮收在同一张卡里，别摊在屏幕两头（中间大片空）。
    // 尺寸一律按 viewW/viewH 的比例算 —— 这两个是物理像素，写死 CSS 值会随 DPR 变形。
    const k = W / (window.innerWidth || W);
    const cardX = land ? W * 0.05 : W * 0.037;
    const cardW = land ? Math.min(W * 0.42, 380 * k) : W * 0.926;
    const cardH = land ? H * 0.47 : H * 0.242;
    const cardY = land ? (H - cardH) / 2 : H - cardH - H * 0.022;
    roundRect(cardX, cardY, cardW, cardH, 20 * k, "rgba(22,26,36,.92)");
    ctx.fillStyle = "rgba(255,255,255,.09)";
    ctx.fillRect(cardX + 18 * k, cardY, cardW - 36 * k, Math.max(1, k));

    const pad = 18 * k;
    const innerX = cardX + pad;
    const innerW = cardW - pad * 2;
    const bh = H * (land ? 0.135 : 0.062);
    const gap = 10 * k;
    const btnY = cardY + cardH - pad - bh;
    const subW = hasSave ? Math.min(innerW * 0.36, 128 * k) : 0;
    state.startRect = {x: innerX, y: btnY, w: innerW - (hasSave ? subW + gap : 0), h: bh};
    state.continueRect = hasSave
      ? {x: innerX + innerW - subW, y: btnY, w: subW, h: bh}
      : null;

    ctx.textAlign = "left";
    ctx.textBaseline = "alphabetic";
    ctx.fillStyle = "rgba(240,244,255,.50)";
    ctx.font = `400 ${Math.round(u * 0.030)}px ${FACE}`;
    ctx.fillText("视觉小说 · MYONL", innerX, cardY + pad + Math.round(u * 0.030));

    const fs = fitFont(pack.title || "MYONL", innerW, Math.round(u * (land ? 0.112 : 0.125)), 700);
    ctx.font = `700 ${fs}px ${FACE}`;
    ctx.fillStyle = "#f7f9ff";
    ctx.fillText(pack.title || "MYONL", innerX, btnY - bh * 0.58);

    const r1 = state.startRect;
    roundRect(r1.x, r1.y, r1.w, r1.h, 14 * k, "rgba(79,140,255,.96)");
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
    get state() {
      return {
        scene: state.scene, say: state.say, choice: state.choice,
        choiceRects: state.choiceRects, sprites: state.sprites, bg: state.bg,
        cg: state.cg,
        lines: state.lines, ended: state.ended, error: state.error,
      };
    },
    get audio() {
      return bgm ? {paused: bgm.paused, muted: bgm.muted, volume: bgm.volume,
                    on: audioOn} : null;
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
      vm = CORE.createVM(pack);
      return loadAssets();
    })
    .then(() => {
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
      const v = JSON.parse(localStorage.getItem(PREF_KEY) || "{}");
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
    } catch (e) { /* 隐私模式禁读 */ }
  }

  function savePrefs() {
    try { localStorage.setItem(PREF_KEY, JSON.stringify(PREF)); } catch (e) { /* 禁写 */ }
  }

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

  function slotBase() {
    const t = (pack && pack.title) || "untitled";
    const s2 = (pack && pack.script) || "";
    return t + ":" + s2;
  }
  function slotKey(i) { return "myonl:slot:" + slotBase() + ":" + i; }
  function slotCount() { return 6; }

  function previewLine() {
    if (!state.say) return "";
    const who = state.say.char ? state.say.char + "：" : "";
    return (who + (state.say.text || "")).slice(0, 18);
  }

  function readSlot(i) {
    try { return JSON.parse(localStorage.getItem(slotKey(i)) || "null"); } catch (e) { return null; }
  }

  function writeSlot(i) {
    if (!vm) return;
    const d = {s: vm.save(), t: Date.now(), say: previewLine(), bg: state.bg || ""};
    try { localStorage.setItem(slotKey(i), JSON.stringify(d)); } catch (e) { /* 满了/禁写 */ }
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
    state.video = vm.state.video || null;
    if (vm.state.music) playMusic(vm.state.music, 0, 0);
    next();
  }

  function openMenu() { UI.open = true; UI.view = "menu"; UI.t0 = performance.now(); }

  function stamp(t) {
    const d = new Date(t || 0);
    const p2 = (n) => (n < 10 ? "0" : "") + n;
    return (d.getMonth() + 1) + "-" + p2(d.getDate()) + " " + p2(d.getHours()) + ":" + p2(d.getMinutes());
  }

  function menuBtnSize() {
    return Math.min(160, Math.max(64, Math.round(Math.min(L.viewW, L.viewH) * 0.105)));
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
    ctx.globalAlpha = 0.5;
    roundRect(r.x, r.y, r.w, r.h, Math.round(r.h / 4), "rgba(12,14,20,.84)");
    ctx.globalAlpha = 1;
    ctx.strokeStyle = "#dfe6f5";
    ctx.lineWidth = Math.max(2, Math.round(r.h * 0.052));
    const cx = r.x + r.w / 2;
    const cy = r.y + r.h / 2;
    const half = r.w * 0.17;
    for (let i = -1; i <= 1; i++) {
      ctx.beginPath();
      ctx.moveTo(cx - half, cy + i * r.h * 0.19);
      ctx.lineTo(cx + half, cy + i * r.h * 0.19);
      ctx.stroke();
    }
    ctx.restore();
  }

  /* 横屏只有 390 高，5 个按钮按竖屏的尺寸会顶到屏幕上下边 */
  function menuRowH() { return Math.round(L.fs * (L.landscape ? 2.1 : 2.7)); }
  function setRowH() { return Math.round(L.fs * (L.landscape ? 2.0 : 2.4)); }
  /* 回顾一页几行：横屏矮，一页 6 行；竖屏高，7 行 */
  function logRows() { return L.landscape ? 6 : 7; }
  function logRowH() { return Math.round(L.fs * 1.45); }
  function logGap() { return Math.round(L.fs * 0.3); }

  /* 面板高度跟着内容走：写死 74% 会在底部留一大片空，还漏出后面的对话框 */
  function menuPanel() {
    const land = L.landscape;
    const w = land ? Math.min(L.viewW * 0.58, 860) : L.viewW * 0.88;
    const pad = Math.round(w * 0.055);
    const headH = Math.round(L.fs * 2.2);
    const footH = Math.round(L.fs * 2.3);
    const gap = Math.round(L.fs * 0.55);
    let bodyH;
    if (UI.view === "menu") {
      // 网格：竖屏 2 列 → 4 行；横屏 4 列 → 2 行
      bodyH = Math.round(L.fs * 0.3) + (L.landscape ? 2 : 4) * (menuRowH() + gap);
    } else if (UI.view === "settings") {
      // 横屏两列（3 行）—— 单列 6 组在横屏里会把面板撑到顶边，一点留白都没有
      bodyH = Math.round(L.fs * 0.3) + (L.landscape ? 3 : 6) * (setRowH() + gap);
    } else if (UI.view === "log") {
      bodyH = Math.round(L.fs * 0.5)
               + logRows() * (logRowH() + logGap())
               + Math.round(L.fs * 2.4);
    } else {
      const rows = land ? 2 : 3;
      // 必须和 drawSlots() 里的 ch 一致，否则面板比格子高、底下空出一条
      const ch = Math.round(L.fs * (land ? 5.8 : 5.2));
      bodyH = Math.round(L.fs * 0.4) + rows * (ch + gap);
    }
    // 回顾要一屏能读，比菜单面板宽；横屏设置两列，也要更宽才装得下两组
    const w2 = UI.view === "log"
      ? (land ? Math.min(L.viewW * 0.78, 1100) : L.viewW * 0.92)
      : UI.view === "settings"
        ? (land ? Math.min(L.viewW * 0.78, 1180) : L.viewW * 0.88)
        : w;
    const pad2 = Math.round(w2 * 0.055);
    // 存档页的脚注只有一行，按菜单页的 footH 留位会在格子下面空出一条空洞
    const footUsed = (UI.view === "save" || UI.view === "load")
      ? Math.round(L.fs * 1.6)
      : footH;
    const h = Math.min(headH + bodyH + footUsed + pad2, L.viewH * (land ? 0.96 : 0.94));
    return {x: (L.viewW - w2) / 2, y: (L.viewH - h) / 2, w: w2, h: h, pad: pad2, headH: headH};
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

  function drawMenuList(x, y, w, p) {
    const rowH = menuRowH();
    const gap = Math.round(L.fs * 0.55);
    const items = [
      ["resume", "继续游戏"],
      ["toLog", "回顾台词"],
      ["toSave", "保存进度"],
      ["toLoad", "读取进度"],
      ["skip", PREF.skip ? "快进 · 已开" : "快进 · 关"],
      // 第 8 项补「自动」：正好 2×4 / 4×2 装满，不留空格，而且自动翻页不用每次进设置
      ["autoTgl", PREF.auto ? "自动 · " + PREF.auto + " 秒" : "自动 · 关"],
      ["toSet", "设置"],
      ["toTitle", "回到标题"],
    ];
    let yy = y + gap;
    // P84：菜单从「7 条通栏长条」改成网格卡片。
    // 长条竖排看起来像设置项列表（劣质感主要来源）；商业作品的菜单都是格位按钮，
    // 一屏 2×4 或 4×2，视线一眼扫完，且高度砍半，面板能收得干净。
    const cols = L.landscape ? 4 : 2;
    const colGap = Math.round(L.fs * 0.5);
    const cellW = (w - (cols - 1) * colGap) / cols;
    items.forEach((pair, idx) => {
      const id = pair[0];
      const label = pair[1];
      const accent = id === "resume" || (id === "skip" && !!PREF.skip);
      const col = idx % cols;
      const row = Math.floor(idx / cols);
      const bx = x + col * (cellW + colGap);
      const by = yy + row * (rowH + gap);
      uiButton(id, bx, by, cellW, rowH, label,
               {on: accent, weight: accent ? 700 : 500, fs: Math.round(L.fs * 0.72)});
    });
    yy += Math.ceil(items.length / cols) * (rowH + gap);
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillStyle = "rgba(240,244,255,.34)";
    ctx.font = "400 " + Math.round(L.fs * 0.5) + "px " + FACE;
    ctx.fillText("进度保存在本机浏览器里 · 换设备不会同步", p.x + p.w / 2, p.y + p.h - Math.round(L.fs * 1.1));
    ctx.textAlign = "left";
  }

  function drawSlotCard(id, x, y, w, h, d, saving, no) {
    const empty = !d;
    const r = Math.round(Math.min(h / 6, 16));
    roundRect(x, y, w, h, r, empty ? "rgba(255,255,255,.045)" : "rgba(255,255,255,.075)");
    ctx.strokeStyle = "rgba(255,255,255,.10)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
    ctx.stroke();

    const ix = x + Math.round(w * 0.055);
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
      ctx.fillText(String(d.say || "（存档）").slice(0, 16), ix, y + Math.round(h * 0.34));
      ctx.fillStyle = "rgba(240,244,255,.34)";
      ctx.font = "400 " + Math.round(L.fs * 0.38) + "px " + FACE;
      ctx.fillText(stamp(d.t), ix, y + h - Math.round(L.fs * 0.70));
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
    const ch = Math.round(L.fs * (land ? 5.4 : 4.6));
    const saving = UI.view === "save";
    for (let i = 0; i < slotCount(); i++) {
      const rr = Math.floor(i / cols);
      const cc = i % cols;
      const bx = x + cc * (cw + gap);
      const by = y + Math.round(L.fs * 0.4) + rr * (ch + gap);
      drawSlotCard("s" + i, bx, by, cw, ch, readSlot(i), saving, i + 1);
    }
    // 存档页也吃到底部那行脚注位：只画格子不写字，面板底下会空出一整条
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillStyle = "rgba(240,244,255,.32)";
    ctx.font = "400 " + Math.round(L.fs * 0.48) + "px " + FACE;
    ctx.fillText(saving ? "进度存在本机浏览器里 · 换设备不会同步" : "点一个格子读档 · 空位不用点",
                 p.x + p.w / 2, p.y + p.h - Math.round(L.fs * 1.0));
    ctx.textAlign = "left";
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
    ctx.fillStyle = "rgba(4,6,12,.86)";
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
      const btnGap = Math.round(L.fs * (cols === 2 ? 0.24 : 0.34));
      const bw = (segW - btnGap * 2) / 3;
      const bh = Math.round(L.fs * 1.5);
      for (let i = 0; i < 3; i++) {
        const on = typeof cur === "string"
          ? cur === vals[i]
          : Math.abs(cur - vals[i]) < 0.001;
        uiButton(key + ":" + i, sx + i * (bw + btnGap), yy + (rowH - bh) / 2, bw, bh,
                 labels[i], {on: on, fs: Math.round(bh * (cols === 2 ? 0.36 : 0.42))});
      }
    }
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillStyle = "rgba(240,244,255,.32)";
    ctx.font = "400 " + Math.round(L.fs * 0.48) + "px " + FACE;
    ctx.fillText("设置存在本机 · 换作品也沿用", p.x + p.w / 2, p.y + p.h - Math.round(L.fs * 1.0));
    ctx.textAlign = "left";
  }

  function drawMenu() {
    const p = menuPanel();
    const vis = visual();
    const a = Math.min(1, (performance.now() - UI.t0) / 160);
    UI.rects = [];

    ctx.save();
    ctx.fillStyle = "rgba(4,6,12," + (0.82 * a) + ")";
    ctx.fillRect(0, 0, L.viewW, L.viewH);
    ctx.globalAlpha = a;
    ctx.translate(0, (1 - a) * Math.round(L.viewH * 0.03));

    const rr = Math.round(p.w * 0.035);
    // P84：菜单面板也带投影，否则它浮在暗背景上没有厚度，像个纯色矩形
    ctx.save();
    ctx.shadowColor = "rgba(0,0,0,.7)";
    ctx.shadowBlur = Math.round(L.fs * 1.6);
    ctx.shadowOffsetY = Math.round(L.fs * 0.5);
    roundRect(p.x, p.y, p.w, p.h, rr, "rgba(17,20,29,.98)");
    ctx.restore();
    ctx.strokeStyle = "rgba(255,255,255,.10)";
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
    if (id === "close") { UI.open = false; return; }
    if (id === "back") { UI.view = "menu"; return; }
    if (id === "resume") { UI.open = false; return; }
    if (id === "skip") { PREF.skip = PREF.skip ? 0 : 1; savePrefs(); state.skipAt = 0; return; }
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
