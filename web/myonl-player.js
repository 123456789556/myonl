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
  const SPEED = 32;                   // 打字机：字/秒

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
    waitUntil: 0,
    ended: false,
    continueRect: null,
    error: "",
  };

  // ---------- 画布尺寸 ----------
  function fit() {
    L = LAYOUT.layoutFor(window.innerWidth, window.innerHeight);
    const dpr = Math.max(1, Math.min(3, window.devicePixelRatio || 1));
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
    state.typeStart -= (state.typedBefore / SPEED) * 1000;
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
    return Math.min(total, Math.max(0, Math.floor(elapsed * SPEED)));
  }

  // ---------- 事件 ----------
  function applyEvent(ev) {
    if (!ev) return;
    switch (ev.type) {
      case "bg":
        if (state.bg && state.bg !== (ev.image || "")) {
          state.fadeFromBg = state.bg;          // 记下旧背景做交叉淡入
          state.fadeT0 = performance.now();
          state.fadeDur = 280;
        }
        state.bg = ev.image || "";
        state.cg = "";          // 切回背景：CG 退场
        break;
      case "cg":
        state.cg = ev.name || "";
        break;
      case "camera":
        applyCamera(ev.kind || "", ev.args || []);
        break;
      case "show":
      case "hide":
        state.sprites = (ev.sprites || []).slice();
        break;
      case "say":
        state.say = ev;
        ctx.font = `${L.fs}px ${FACE}`;
        state.lines = wrap(ev.text, L.textW);
        state.typeStart = performance.now();
        state.typedBefore = 0;
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
          ev.type === "wait" || ev.type === "end") break;
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
    // 读档后补一次"当前画面"：让 bg/立绘/CG/镜头先对上，再继续推进
    state.bg = vm.state.bg || "";
    state.cg = vm.state.cg || "";
    state.sprites = (vm.state.sprites || []).slice();
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
    const p = point(e);

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
      state.typeStart = performance.now() - (totalChars(state.lines) / SPEED) * 1000;
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
    if (moved > 12 || dur > 1200) return;
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

  function drawBackground() {
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
      blitCover(img, prev && t < 1 ? t : 1);
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

  function drawSprites() {
    const list = state.sprites || [];
    if (!list.length) return;
    const n = list.length;
    const baseH = L.spriteH;
    list.forEach((sp, i) => {
      const key = sp.expr ? `${sp.char}_${sp.expr}` : sp.char;
      const img = assets[key] || assets[sp.char];
      if (!img) return;
      const h = baseH;
      const w = img.width * (h / img.height);
      const slotW = L.viewW / n;
      const cx = slotW * (i + 0.5);
      ctx.drawImage(img, cx - w / 2, L.viewH - h, w, h);
    });
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

  /* 面板高度跟着台词行数走：一句话就不要一个大空盒子（至少 3 行高，最多 5 行）。 */
  function panelRect() {
    const rows = Math.max(2, Math.min(L.maxTextRows, (state.lines || []).length || 2));
    const h = Math.min(L.viewH * 0.46, L.padY * 2 + rows * L.lineH + Math.round(L.fs * 0.7));
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
    panelHairline(x, y, w, radius);
    return rect;
  }

  function drawDialogue(vis) {
    if (!state.say || !state.lines) return;
    const rect = drawPanel(vis);
    const say = state.say;

    if (say.char) {
      ctx.font = `600 ${L.nameSize}px ${FACE}`;
      const tw = ctx.measureText(say.char).width;
      const plateH = L.nameSize + 22;
      const plateX = rect.x + Math.round(L.marginX * 0.6);
      const plateY = rect.y - plateH - 14;
      const tint = say.color || vis.accent;
      // 名字牌跟着角色色走：淡色底 + 同色描边，比原来一律黑底更像"这个人说话"
      roundRect(plateX, plateY, tw + 52, plateH, plateH / 2, hexA(tint, 0.30));
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
      ctx.fillStyle = "#ffffff";
      ctx.textBaseline = "middle";
      ctx.fillText(say.char, plateX + 26, plateY + plateH / 2);
    }

    const shown = typedCount();
    let left = shown;
    ctx.font = `${L.fs}px ${FACE}`;
    ctx.textBaseline = "top";
    const tx = rect.x + L.padX + vis.panel.padX;
    const ty = rect.y + L.padY + vis.panel.padY;
    const maxRows = Math.min(rect.rows, L.maxTextRows);
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

  function drawChoices(vis) {
    state.choiceRects = [];
    if (!state.choice) return;
    ctx.save();
    ctx.fillStyle = "rgba(6,8,12,.66)";
    ctx.fillRect(0, 0, L.viewW, L.viewH);
    ctx.restore();

    const bw = L.choiceW;
    const bh = L.choiceH;
    const gap = L.choiceGap;
    const n = state.choice.length;
    const totalH = n * bh + (n - 1) * gap;
    const startY = Math.max(L.marginX, (L.viewH - totalH) / 2);
    const x = (L.viewW - bw) / 2;

    state.choice.forEach((opt, i) => {
      const y = startY + i * (bh + gap);
      const r = 14;
      // 按钮不再用 3px 蓝框圈住（太像表单）：淡底 + 1px 细边 + 左侧一道 accent 竖条
      const g2 = ctx.createLinearGradient(0, y, 0, y + bh);
      g2.addColorStop(0, "rgba(32,38,54,.94)");
      g2.addColorStop(1, "rgba(20,24,36,.96)");
      roundRect(x, y, bw, bh, r, g2);
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
      ctx.fillStyle = vis.textColor;
      ctx.font = `500 ${L.fs}px ${FACE}`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(opt.text, x + bw / 2, y + bh / 2);
      ctx.textAlign = "left";
      state.choiceRects.push({x: x, y: y, w: bw, h: bh, idx: i,
                              text: opt.text, target: opt.target});
    });
  }

  function drawTitle() {
    const g = ctx.createLinearGradient(0, 0, 0, L.viewH);
    g.addColorStop(0, "#171a26");
    g.addColorStop(1, "#07080d");
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, L.viewW, L.viewH);

    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillStyle = "#f4f6ff";
    ctx.font = `700 ${Math.round(Math.min(L.viewW, L.viewH) * 0.10)}px ${FACE}`;
    ctx.fillText(pack.title || "MYONL", L.viewW / 2, L.viewH * (L.landscape ? 0.26 : 0.34));
    ctx.fillStyle = "rgba(240,244,255,.55)";
    ctx.font = `400 ${Math.round(Math.min(L.viewW, L.viewH) * 0.030)}px ${FACE}`;
    ctx.fillText("MYONL · 手机端", L.viewW / 2, L.viewH * (L.landscape ? 0.40 : 0.42));

    const bw = Math.min(L.viewW * 0.62, 620);
    const bh = Math.round(Math.max(88, Math.min(L.viewH * 0.10, 132)));
    const by = L.viewH * (L.landscape ? 0.60 : 0.64);
    roundRect(L.viewW / 2 - bw / 2, by, bw, bh, Math.round(bh / 4), "rgba(79,140,255,.94)");
    ctx.fillStyle = "#fff";
    ctx.font = `600 ${Math.round(Math.min(L.viewW, L.viewH) * 0.038)}px ${FACE}`;
    ctx.fillText("开始新故事", L.viewW / 2, by + bh / 2);

    let hasSave = false;
    try { hasSave = !!localStorage.getItem(saveKey()); } catch (e) { hasSave = false; }
    state.continueRect = null;
    if (hasSave) {
      const cby = by + bh + Math.round(bh * 0.3);
      roundRect(L.viewW / 2 - bw / 2, cby, bw, bh, Math.round(bh / 4), "rgba(255,255,255,.10)");
      ctx.fillStyle = "rgba(240,244,255,.85)";
      ctx.fillText("继续上次", L.viewW / 2, cby + bh / 2);
      state.continueRect = {x: L.viewW / 2 - bw / 2, y: cby, w: bw, h: bh};
    }
    ctx.textAlign = "left";
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
    ctx.restore();
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
      drawDialogue(vis);
      drawChoices(vis);
      drawMute();
      if (state.waitUntil && performance.now() >= state.waitUntil) {
        state.waitUntil = 0;
        next();
      }
    }
    requestAnimationFrame(frame);
  }

  // ---------- 启动 ----------
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
    })
    .catch((err) => {
      state.error = "加载失败：" + err.message
        + "。单文件版可直接双击打开；分目录版需要静态服务器（file:// 取不到 pack.json）。";
    });
})();
