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
  // P198.1：草稿键只有一份，换作品之后第一次落盘会把上一个作品"还没恢复的"
  // 那份草稿无声顶掉。挤出来的一份放这里 —— 仍然是一个固定键，不是索引。
  var ORPHAN_KEY = "myonl:off:draft:v1:orphan";
  var ORPHAN_DAYS = 7;
  var SESSION_KEY = "myonl:draftShown";
  var DEBOUNCE_MS = 1500;   // 停止输入 1.5 秒写一次
  var CEIL_MS = 30000;      // 连续码字时防抖一直在重置，这条保证 30 秒内必落一次

  var last = "";            // 上一次落盘成功的内容
  var loadedName = "";      // 当前这一屏的 #source 装的是哪个作品
  var loadGen = 0;          // 装载代际：每换一次"这一屏装的是谁"就 +1
  var readyGen = -1;        // 正文真正就位后追平成 loadGen；追不上就一律不写
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

  function readKey(k) {
    try {
      var d = JSON.parse(localStorage.getItem(k) || "null");
      return (d && typeof d === "object" && typeof d.text === "string") ? d : null;
    } catch (e) { return null; }
  }
  function readDraft() { return readKey(DRAFT_KEY); }
  function readOrphan() { return readKey(ORPHAN_KEY); }

  function clearDraft() {
    try { localStorage.removeItem(DRAFT_KEY); } catch (e) {}
  }
  function clearOrphan() {
    try { localStorage.removeItem(ORPHAN_KEY); } catch (e) {}
  }

  function findProj(lib, name) {
    if (!lib || !lib.projects) return null;
    for (var i = 0; i < lib.projects.length; i++) {
      if (lib.projects[i].name === name) return lib.projects[i];
    }
    return null;
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
      // P261：窄条原来是 11px 胶囊 + 写死的深蓝底，两套皮都不跟 —— 改成 4px 硬边、
      // 底色吃卡片、描边吃 surface0，字色走语义变量（两套皮各自保证对比度）。
      "z-index:520;height:22px;line-height:22px;padding:0 10px;border-radius:4px;" +
      "font-size:12px;color:var(--text);background:var(--card-bg);" +
      "border:1px solid var(--surface0);pointer-events:none;" +
      "transition:opacity .5s ease;opacity:1;white-space:nowrap;";
    document.body.appendChild(el);
    return el;
  }

  // 窄条只在编辑器里出现。首页/作品页/播放页一律藏 —— 那几屏底下突然飘一条
  // "已保存 18:00"，比没有更让人困惑（那几屏根本没有"保存"这件事）。
  function visible() {
    if (document.body.classList.contains("m-home-open")) return false;
    return !!document.getElementById("source");
  }

  function paint() {
    if (!state) return;
    var el = bar();
    if (!visible()) { el.style.display = "none"; return; }
    el.style.display = "block";
    // 状态写到属性上：手机壳里 saved 态由 ui-layout.css 压掉（状态栏已经在说「已保存」）。
    // 交给 CSS 是因为 m-shell 类可能比这次 paint 晚一步打上，窄条 fixed 常驻不重绘，JS 判一次会漏。
    el.setAttribute("data-state", state);
    var text = "", color = "var(--text)";
    // 本作品已保存、但另一个作品还压着一份没恢复的草稿：窄条改成这条，
    // 让"在工作台漏看了提示"的人还有第二个地方能捞回来。
    var orp = (state === "saved" || state === "draft") ? readOrphan() : null;
    if (orp) {
      var days = Math.max(1, Math.round((now() - (orp.at || 0)) / 86400000));
      text = "「" + orp.name + "」有未恢复草稿 · " + days + " 天前";
      color = "var(--yellow)";
    } else if (state === "saved") {
      text = "已保存 " + stamp; color = "var(--green)";
    }
    else if (state === "dirty") { text = "存草稿中…"; color = "var(--yellow)"; }
    // 草稿态窄条本身就是丢弃入口（作品工作台屏撤掉后唯一能"不要这版"的地方）。
    else if (state === "draft") { text = "草稿 " + stamp + " · 点这里丢弃"; color = "var(--blue-ink)"; }
    else if (state === "fail") { text = "自动保存失败 · 点这里重试"; color = "var(--red)"; }
    el.textContent = text;
    el.style.color = color;
    el.style.opacity = "1";
    el.style.pointerEvents = (state === "fail" || state === "draft" || orp) ? "auto" : "none";
    el.onclick = state === "fail" ? function () { flush(); }
      : (orp ? function () {
          try { window.__editor.toast("回作品页打开「" + orp.name + "」，进去就会接上那份内容"); }
          catch (e) {}
        } : state === "draft" ? function () { var q = currentProject(readLib()); drop(q && q.name); }
        : null);
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
    // 不在编辑器那屏就一律不写。首页/作品页时 #source 还挂在 DOM 上，
    // 但里面是上一个作品的残留文本 —— 在这里写会造出一份"空草稿"，
    // 再被下一个作品挤进 orphan 槽，最后表现为"别的作品有未恢复草稿"。
    if (!visible()) return;
    var ta = document.getElementById("source");
    if (!ta) return;
    var lib = readLib();
    var p = currentProject(lib);
    if (!p) return;

    // 切作品时最容易毁数据的一刻：/api/project 已经把 lib.current 换成新作品，
    // 但页面还停在旧作品的编辑器上（reload 还没发生），pagehide 一 flush，
    // 就会把"旧作品的正文"记成"新作品的草稿"，下次进新作品直接把它覆盖掉。
    // 屏幕里装的是哪个作品，只有这一层知道 —— 对不上就整次丢弃。
    var text = ta.value;
    if (loadedName && loadedName !== p.name) {
      loadedName = p.name;
      loadGen++;            // 这一屏装的东西作废，等新正文就位再重新点火
      readyGen = -1;
      last = "";
      return;
    }
    // 代际追不上就是"装载还没完成"，一个字符都不许写。
    // 以前这里靠"启动后 1.5 秒"点火，那是在赌低端机上正文一定换得完；
    // 现在只认确定事件（input / applyTo / boot 后内容基线），不认时钟。
    if (readyGen !== loadGen) return;

    // 跨作品覆盖守卫（路径 A）：换到别的作品之后第一次落盘，会把上一个作品
    // "还没恢复"的那份草稿顶掉，用户全程看不到任何提示。这里先把它挤到
    // orphan 槽 —— 还是固定键，不建索引，也不遍历。
    var old = readDraft();
    if (old && old.name && old.name !== p.name) {
      var op = findProj(lib, old.name);
      // 只有"确实还没落进正式库"的那份才值得留；已经保存过的旧草稿直接作废
      if (!op || old.text !== (op.text || "")) {
        try { localStorage.setItem(ORPHAN_KEY, JSON.stringify(old)); } catch (e) {}
      }
    }

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
    // 用户真的在这个作品的编辑器里动手了 —— 这是最可靠的就位信号
    readyGen = loadGen;
    last = "";
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
    readyGen = loadGen;     // 正文已就位；dispatch 的 input 也会把代际追平，这条是双保险
    last = "";              // 强制下一次 flush 重新写（内容还是没正式落库）
    setState("draft");
    return true;
  }

  // 丢弃要按作品名丢：草稿键和 orphan 槽可能分属两个作品，
  // 一刀全清会把另一个作品还没认领的草稿也带走。
  function drop(name) {
    var d = readDraft(), o = readOrphan();
    if (!name || (d && d.name === name)) clearDraft();
    if (name && o && o.name === name) clearOrphan();
    // 编辑器 DOM 里那份 textarea 还留着草稿内容。不还原的话，pagehide / 30 秒兜底
    // 会把它原样写回来 —— 用户点了「丢弃」，两秒后草稿又"复活"了。
    var ta = document.getElementById("source");
    var p = findProj(readLib(), name || (d && d.name));
    if (ta && p && ta.value !== (p.text || "")) {
      ta.value = p.text || "";
      try { ta.dispatchEvent(new Event("input", { bubbles: true })); } catch (e) {}
    }
    last = "";
    setState("saved");
  }

  // 跨页恢复：工作台点「恢复并进入」之后要整页 reload 去编辑器，
  // 内存变量带不过去，所以把"要恢复哪个作品"写进 sessionStorage。
  // 等编辑器把正文填进 #source 之后再灌草稿，否则会被初始化覆盖掉。
  // 上限 20 次：进的是播放页或别的地方就自然放弃，不能无限轮询。
  function autoApply(tries) {
    tries = tries || 0;
    var p = currentProject(readLib());
    var ta = document.getElementById("source");
    var d = readDraft();
    if (!p || !ta || !d || d.name !== p.name) return;
    if (d.text === (p.text || "")) { clearDraft(); return; }  // 和正式库一模一样，没必要灌
    if (ta.value !== (p.text || "")) {
      if (tries < 20) setTimeout(function () { autoApply(tries + 1); }, 300);
      return;
    }
    applyTo(ta);
  }

  function diffText(d) {
    if (!d) return { chars: 0, lines: 0 };
    // 比的是"这份草稿"和它自己那个作品的正文，不是当前打开的作品 ——
    // 随手用了 currentProject 会把字数算成隔壁作品的长度。
    var lib = readLib();
    var p = findProj(lib, d.name) || currentProject(lib);
    var base = (p && p.text) || "";
    return { chars: d.text.length - base.length, lines: d.text.split("\n").length - base.split("\n").length };
  }

  // ---- 启动 ----
  function boot() {
    // 只接管离线模式。PC 服务模式没有这个键，保存是真 HTTP，别搅进来。
    if (!readLib()) return;
    var ta = document.getElementById("source");
    if (!ta) return;
    loadedName = (currentProject(readLib()) || {}).name || "";
    loadGen++;
    readyGen = loadGen;   // boot 时 last 已设成 ta.value，没变化就不会误写
    last = ta.value;

    // orphan 收编：压着的那份草稿如果正是当前作品，说明用户终于打开它了 ——
    // 提回主键、清 orphan，然后走下面的自动接上。
    // 但提回会覆盖主键：如果主键里正压着"另一个作品"的未落库草稿，先把它挤进
    // orphan，再提回来。不先挤就走的话，B 的草稿会被 A 的提回无声顶掉。
    var orp = readOrphan();
    if (orp) {
      var lib0 = readLib();
      var cur = (currentProject(lib0) || {}).name;
      if (orp.name === cur) {
        var prev = readDraft();
        var moved = false;
        if (prev && prev.name && prev.name !== orp.name) {
          var pp = findProj(lib0, prev.name);
          if (!pp || prev.text !== (pp.text || "")) {
            try { localStorage.setItem(ORPHAN_KEY, JSON.stringify(prev)); } catch (e) {}
            moved = true;
          }
        }
        try { localStorage.setItem(DRAFT_KEY, JSON.stringify(orp)); } catch (e) {}
        if (!moved) clearOrphan();   // moved 时 orphan 现在装的是 prev，别清
      } else if ((now() - (orp.at || 0)) > ORPHAN_DAYS * 86400000) {
        clearOrphan();   // 7 天都没人回来认领，别挂着当僵尸数据
      }
    }

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
    // 自动接上（路径 B）：进编辑器就把草稿灌进去，不靠用户再点一下恢复。
    // 不想要的人点草稿窄条丢弃（见 paint() 的 draft 分支），草稿删了这里就接不到。
    setTimeout(function () { autoApply(0); }, 250);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }

  window.MYONLDraft = {
    peek: peek, markShown: markShown, applyTo: applyTo, drop: drop, flush: flush,
    autoApply: autoApply, diffText: diffText, readDraft: readDraft,
    readOrphan: readOrphan, DRAFT_KEY: DRAFT_KEY
  };
})();
