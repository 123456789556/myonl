/* MYONL P198：静默自动保存 + 草稿恢复 + 保存状态窄条（离线模式）
 *
 * 为什么要有这个东西：离线模式的作品库整个塞在 localStorage 一个键里
 * （gal_offline.js 的 myonl:off:lib:v1），只有点保存才写回去。写到一半
 * 切后台被系统杀、浏览器崩、手滑刷新 —— textarea 里那几百字直接没了。
 * 版本快照救不了：它存的是"上一次点保存时"的样子。
 *
 * 所以草稿和正式内容必须分开：
 *   正式库  myonl:off:lib:v1   点了保存才动，进版本快照
 *   草稿    myonl:off:draft:v1 打字就写，不进快照，不占版本名额
 * 混在一起的后果很具体：每个击键都算一次保存，20 秒合并窗口一过，
 * 30 个版本名额被同一分钟的涂改挤满，真正的里程碑反而被轮换掉。
 *
 * 为什么草稿只有"一份"而不是每个作品一份（不要 draft:index）：
 * 手机端切作品是整页 reload（点作品 = 换根），同一时刻只有一个作品在被编辑。
 * 按作品各存一份再配一个索引，就是又造一套"派生数据"，会出现
 * "草稿写了、索引没写 → 永远不提示恢复"这种不一致 —— P197d 刚治过同类病。
 * 作品数也被 gal_offline 的 trimLib(lib, 8) 压在 8 个量级，遍历没有成本。
 *
 * 为什么不另开 IndexedDB：文本只有几十 KB，localStorage 同步写 1–3ms 可以接受；
 * 而且和正式库同源，判断"草稿是不是比正式库新"只需要比两个 mtime，
 * 不用再处理一遍 dbOpen 可能失败、库版本要升级这些事。
 * 素材那种几百 MB 的东西才该进 IndexedDB，文本不该。
 */
(function () {
  "use strict";

  var LIB_KEY = "myonl:off:lib:v1";
  var DRAFT_KEY = "myonl:off:draft:v1";
  var SESSION_KEY = "myonl:draftShown";
  var DEBOUNCE_MS = 1500;   // 停止输入 1.5 秒写一次
  var CEIL_MS = 30000;      // 连续码字时防抖一直在重置，这条保证 30 秒内必落一次

  var last = "";            // 上一次落盘成功的内容
  var timer = null;
  var state = "";           // "" | saved | dirty | draft | fail
  var stamp = "";

  function now() { return Date.now(); }

  function readLib() {
    try { return JSON.parse(localStorage.getItem(LIB_KEY) || "null"); }
    catch (e) { return null; }
  }

  function currentProject(lib) {
    if (!lib || !lib.projects || !lib.projects.length) return null;
    for (var i = 0; i < lib.projects.length; i++) {
      if (lib.projects[i].name === lib.current) return lib.projects[i];
    }
    return lib.projects[0];
  }

  function readDraft() {
    try {
      var d = JSON.parse(localStorage.getItem(DRAFT_KEY) || "null");
      return (d && typeof d === "object" && typeof d.text === "string") ? d : null;
    } catch (e) { return null; }
  }

  function clearDraft() {
    try { localStorage.removeItem(DRAFT_KEY); } catch (e) {}
  }

  function hhmm(ts) {
    var d = new Date(ts || now());
    var h = d.getHours(), m = d.getMinutes();
    return (h < 10 ? "0" : "") + h + ":" + (m < 10 ? "0" : "") + m;
  }

  // ---- 窄条 ----
  // 绝对不能参与 flex 高度计算：软键盘弹出时会让编辑区反复重排、光标跳。
  // 所以走 position:fixed，只在透明度上做文章。
  function bar() {
    var el = document.getElementById("mDraftBar");
    if (el) return el;
    el = document.createElement("div");
    el.id = "mDraftBar";
    el.style.cssText =
      "position:fixed;left:50%;transform:translateX(-50%);" +
      "bottom:calc(52px + env(safe-area-inset-bottom) + 6px);" +
      "z-index:520;height:22px;line-height:22px;padding:0 10px;border-radius:11px;" +
      "font-size:12px;color:#9fb3d1;background:rgba(16,22,34,.86);" +
      "border:1px solid rgba(120,160,220,.22);pointer-events:none;" +
      "transition:opacity .5s ease;opacity:1;white-space:nowrap;";
    document.body.appendChild(el);
    return el;
  }

  // 窄条只在编辑器里出现。首页/作品页/播放页一律藏 —— 那几屏底下突然飘一条
  // "已保存 18:00"，比没有更让人困惑（那几屏根本没有"保存"这件事）。
  function visible() {
    if (document.body.classList.contains("m-home-open")) return false;
    var ta = document.getElementById("source");
    return !!(ta && ta.offsetParent !== null);
  }

  function paint() {
    if (!state) return;
    var el = bar();
    if (!visible()) { el.style.display = "none"; return; }
    el.style.display = "block";
    var text = "", color = "#9fb3d1";
    if (state === "saved") { text = "已保存 " + stamp; color = "#7fd6a0"; }
    else if (state === "dirty") { text = "存草稿中…"; color = "#e0c46a"; }
    else if (state === "draft") { text = "草稿 " + stamp + " · 未保存"; color = "#8fb8e8"; }
    else if (state === "fail") { text = "自动保存失败 · 点这里重试"; color = "#e07a6a"; }
    el.textContent = text;
    el.style.color = color;
    el.style.opacity = "1";
    el.style.pointerEvents = state === "fail" ? "auto" : "none";
    el.onclick = state === "fail" ? function () { flush(); } : null;
    // 稳定态 2.5 秒后淡下去，但不清空 —— 点一下/鼠标移上来还能看到
    if (el._fade) clearTimeout(el._fade);
    if (state === "saved" || state === "draft") {
      el._fade = setTimeout(function () { try { el.style.opacity = ".45"; } catch (e) {} }, 2500);
    }
  }

  function setState(s) {
    if (s === state) return;      // 每次击键都 setState 会反复改 DOM，状态没变就别动
    state = s;
    stamp = hhmm();
    paint();
  }

  // ---- 落草稿 ----
  // 三个前置判断按顺序拦：没有文本域 / 不是离线模式 / 正文已经和正式库一致。
  // 最后这条是自动清理：用户点了保存之后，正式库的 p.text 就等于 textarea，
  // 草稿立刻失去意义，必须立刻删掉，否则下次进作品会弹"发现未保存内容"——假的。
  function flush(force) {
    var ta = document.getElementById("source");
    if (!ta) return;
    var p = currentProject(readLib());
    if (!p) return;
    var text = ta.value;

    if (text === (p.text || "")) {
      if (last !== text) { clearDraft(); last = text; }
      setState("saved");
      return;
    }
    if (!force && text === last) return;
    if (!text && !last && force !== 2) return;

    var d = {
      name: p.name,
      text: text,
      at: now(),
      baseMtime: p.mtime || 0,
      baseLen: (p.text || "").length
    };
    try {
      localStorage.setItem(DRAFT_KEY, JSON.stringify(d));
      last = text;
      setState("draft");
    } catch (e) {
      setState("fail");
    }
  }

  // 保存成功之后草稿要立刻消失。不能只靠 30 秒兜底 —— 那 30 秒里
  // 窄条还写着"草稿 · 未保存"，用户会以为没存上，再去点一次保存。
  // 保存是异步的（要等快照事务提交），所以轮询正式库，不按固定延时赌。
  function watchSaved(n) {
    n = n || 0;
    var ta = document.getElementById("source");
    var p = currentProject(readLib());
    if (!ta || !p) return;
    if ((p.text || "") === ta.value) { clearDraft(); last = ta.value; setState("saved"); return; }
    if (n < 8) setTimeout(function () { watchSaved(n + 1); }, 400);
  }

  function onInput() {
    setState("dirty");
    if (timer) clearTimeout(timer);
    timer = setTimeout(function () { timer = null; flush(); }, DEBOUNCE_MS);
  }

  // ---- 给 editor_home.js 用的三件套 ----
  // peek(name)：这个作品有没有"比正式库新"的草稿。顺手把失效草稿删掉。
  function peek(name) {
    var d = readDraft();
    if (!d) return null;
    if (name && d.name !== name) return null;
    var p = currentProject(readLib());
    if (!p || p.name !== d.name) { clearDraft(); return null; }
    if (d.text === (p.text || "")) { clearDraft(); return null; }
    if ((d.at || 0) <= (p.mtime || 0)) { clearDraft(); return null; }
    // 草稿的底稿和当前正式库不是同一版（中间回退过/导入过）→ 标出来让用户自己选
    d.stale = ((d.baseMtime || 0) !== (p.mtime || 0));
    try {
      if (sessionStorage.getItem(SESSION_KEY) === d.name + ":" + d.at) return null;
    } catch (e) {}
    return d;
  }

  function markShown(d) {
    try { if (d) sessionStorage.setItem(SESSION_KEY, d.name + ":" + d.at); } catch (e) {}
  }

  // 把草稿灌回编辑器。不自动保存 —— 自动保存会立刻拍一版快照，
  // 把"用户打算丢弃的那一版"占掉一格；而且人可能只是想看看再改。
  function applyTo(ta) {
    var d = readDraft();
    if (!d) return false;
    ta = ta || document.getElementById("source");
    if (!ta) return false;
    ta.value = d.text;
    try { ta.dispatchEvent(new Event("input", { bubbles: true })); } catch (e) {}
    last = "";              // 强制下一次 flush 重新写（内容还是没正式落库）
    setState("draft");
    return true;
  }

  function drop() { clearDraft(); last = ""; setState("saved"); }

  // 跨页恢复：工作台点「恢复并进入」之后要整页 reload 去编辑器，
  // 内存变量带不过去，所以把"要恢复哪个作品"写进 sessionStorage。
  var APPLY_KEY = "myonl:applyDraft";
  function requestApply(name) {
    try { sessionStorage.setItem(APPLY_KEY, String(name || "")); } catch (e) {}
  }
  // 等编辑器把正文填进 #source 之后再灌草稿，否则会被初始化覆盖掉。
  // 上限 20 次：进的是播放页或别的地方就自然放弃，不能无限轮询。
  function tryApply(tries) {
    tries = tries || 0;
    var want = "";
    try { want = sessionStorage.getItem(APPLY_KEY) || ""; } catch (e) {}
    if (!want) return;
    var p = currentProject(readLib());
    var ta = document.getElementById("source");
    if (!p || p.name !== want || !ta || ta.value !== (p.text || "") || tries > 20) {
      if (tries > 20) { try { sessionStorage.removeItem(APPLY_KEY); } catch (e) {} return; }
      setTimeout(function () { tryApply(tries + 1); }, 300);
      return;
    }
    try { sessionStorage.removeItem(APPLY_KEY); } catch (e) {}
    applyTo(ta);
  }

  function diffText(d) {
    if (!d) return { chars: 0, lines: 0 };
    var p = currentProject(readLib());
    var base = (p && p.text) || "";
    return { chars: d.text.length - base.length, lines: d.text.split("\n").length - base.split("\n").length };
  }

  // ---- 启动 ----
  function boot() {
    // 只接管离线模式。PC 服务模式没有这个键，保存是真 HTTP，别搅进来。
    if (!readLib()) return;
    var ta = document.getElementById("source");
    if (!ta) return;
    last = ta.value;
    ta.addEventListener("input", onInput);
    // 切后台/关页：WebView 里 beforeunload 不可靠，用这两个
    document.addEventListener("visibilitychange", function () {
      if (document.visibilityState === "hidden") flush(true);
    });
    window.addEventListener("pagehide", function () { flush(true); });
    var btn = document.getElementById("btnSave");
    if (btn) btn.addEventListener("click", function () {
      setTimeout(function () { watchSaved(0); }, 500);
    });
    setInterval(function () {
      var t = document.getElementById("source");
      if (!t) return;
      if (t.value !== last) flush();
      else { var p = currentProject(readLib()); if (p && (p.text || "") === t.value) setState("saved"); }
    }, CEIL_MS);
    // 申请持久化存储：不申的话 Chrome 在存储压力下会驱逐非持久化 origin 的本地数据，
    // 用户会遇到"作品在、草稿没了"，比直接丢更难排查。
    try {
      if (navigator.storage && navigator.storage.persist) {
        navigator.storage.persisted().then(function (ok) {
          if (!ok) navigator.storage.persist();
        }).catch(function () {});
      }
    } catch (e) {}
    setState("saved");
    // 首页/作品页/播放页都是切层不换页，窄条要跟着"现在在哪一屏"重算可见性
    try {
      new MutationObserver(function () { paint(); })
        .observe(document.body, { attributes: true, attributeFilter: ["class"] });
    } catch (e) {}
    // 工作台点了「恢复并进入」：等编辑器初始化把正文填进 #source 再灌草稿
    setTimeout(function () { tryApply(0); }, 400);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }

  window.MYONLDraft = {
    peek: peek, markShown: markShown, applyTo: applyTo, drop: drop, flush: flush,
    requestApply: requestApply, diffText: diffText, readDraft: readDraft, DRAFT_KEY: DRAFT_KEY
  };
})();
