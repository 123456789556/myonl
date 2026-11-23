/* 版本快照：每次保存前把上一版留一份，存独立 IndexedDB，绝不动作品库本体。
   用独立库是有原因的：作品库放 localStorage，配额只有 5MB，一张图就能爆；
   快照放这儿，爆了也只丢快照，正文照旧。 */
(function () {
  if (!window.__MYONL_OFFLINE) return;

  var DB_NAME = "myonl-snapshots";
  var STORE = "snaps";
  var VER = 1;
  var MAX_PER_PROJECT = 20;
  var MAX_TOTAL = 60;
  var MIN_GAP_SECONDS = 20;   // P197d：60→20 秒。写剧本是一分钟存一次，
                              // 一分钟窗口把正常写作全合并成一条，历史看着像没在工作
  var MAX_PER_PROJECT = 30;   // P197d：20→30 版（纯文本，一版才几 KB，多留几格更保险）

  function openDB() {
    return new Promise(function (res, rej) {
      if (!window.indexedDB) { rej(new Error("这个浏览器没有 IndexedDB")); return; }
      var req = indexedDB.open(DB_NAME, VER);
      req.onupgradeneeded = function (e) {
        var db = e.target.result;
        if (!db.objectStoreNames.contains(STORE)) {
          db.createObjectStore(STORE, { keyPath: "key" });
        }
      };
      req.onsuccess = function () { res(req.result); };
      req.onerror = function () { rej(req.error || new Error("打不开快照库")); };
    });
  }

  function all() {
    return openDB().then(function (db) {
      return new Promise(function (res, rej) {
        var t = db.transaction(STORE, "readonly");
        var req = t.objectStore(STORE).getAll();
        req.onsuccess = function () { db.close(); res(req.result || []); };
        req.onerror = function () { db.close(); rej(req.error); };
      });
    });
  }

  function put(rec) {
    return openDB().then(function (db) {
      return new Promise(function (res, rej) {
        var t = db.transaction(STORE, "readwrite");
        t.objectStore(STORE).put(rec);
        t.oncomplete = function () { db.close(); res(); };
        t.onerror = function () { db.close(); rej(t.error); };
      });
    });
  }

  function drop(keys) {
    if (!keys.length) return Promise.resolve();
    return openDB().then(function (db) {
      return new Promise(function (res, rej) {
        var t = db.transaction(STORE, "readwrite");
        keys.forEach(function (k) { t.objectStore(STORE).delete(k); });
        t.oncomplete = function () { db.close(); res(); };
        t.onerror = function () { db.close(); rej(t.error); };
      });
    });
  }

  function now() { return Math.round(Date.now() / 1000); }

  /* 保存前调：project 是 {name, text, mtime}。text 没变就不留，
     免得同内容堆二十份，真出问题时翻半天也找不到"改坏前那版"。 */
  function capture(project, prevText) {
    if (!project || !project.name) return Promise.resolve(0);
    var text = project.text == null ? "" : String(project.text);
    if (text === (prevText == null ? "" : String(prevText))) return Promise.resolve(0);
    if (!text && !prevText) return Promise.resolve(0);

    return all().then(function (rows) {
      var mine = rows.filter(function (r) { return r.name === project.name; })
        .sort(function (a, b) { return b.at - a.at; });

      // 一分钟内连按：把刚才那条换成这版，不新增
      if (mine.length && now() - mine[0].at < MIN_GAP_SECONDS) {
        return put({
          key: mine[0].key,
          name: project.name,
          at: now(),
          size: text.length,
          text: text
        }).then(function () { return mine[0].at; });
      }

      var rec = {
        key: project.name + ":" + now() + ":" + Math.random().toString(36).slice(2, 7),
        name: project.name,
        at: now(),
        size: text.length,
        text: text
      };

      var dropKeys = mine.slice(MAX_PER_PROJECT - 1).map(function (r) { return r.key; });

      var every = rows.sort(function (a, b) { return b.at - a.at; });
      if (every.length + 1 > MAX_TOTAL) {
        every.slice(MAX_TOTAL - 1).forEach(function (r) { dropKeys.push(r.key); });
      }

      return put(rec).then(function () { return drop(dropKeys); }).then(function () { return rec.at; });
    }).catch(function () { return 0; });
  }

  function list(projectName) {
    return all().then(function (rows) {
      var out = rows.filter(function (r) { return !projectName || r.name === projectName; })
        .sort(function (a, b) { return b.at - a.at; });
      return out.map(function (r) { return { key: r.key, name: r.name, at: r.at, size: r.size }; });
    }).catch(function () { return []; });
  }

  function read(key) {
    return openDB().then(function (db) {
      return new Promise(function (res, rej) {
        var t = db.transaction(STORE, "readonly");
        var req = t.objectStore(STORE).get(key);
        req.onsuccess = function () { db.close(); res(req.result || null); };
        req.onerror = function () { db.close(); rej(req.error); };
      });
    }).catch(function () { return null; });
  }

  window.MYONLSnapshots = { capture: capture, list: list, read: read };

  // ---------- 浮层：列历史版本，点一条就退回去 ----------
  function curName() {
    try {
      var lib = JSON.parse(localStorage.getItem("myonl:off:lib:v1") || "");
      return (lib && lib.current) || "";
    } catch (e) { return ""; }
  }

  function fmt(ts) {
    var d = new Date(ts * 1000);
    function p(n) { return n < 10 ? "0" + n : "" + n; }
    return (d.getMonth() + 1) + "-" + p(d.getDate()) + " " +
      p(d.getHours()) + ":" + p(d.getMinutes()) + ":" + p(d.getSeconds());
  }

  function restore(key, name, text) {
    try {
      var lib = JSON.parse(localStorage.getItem("myonl:off:lib:v1") || "");
      var hit = null;
      (lib.projects || []).forEach(function (p) { if (p.name === name) hit = p; });
      if (!hit) { alert("这个作品已经不在列表里了"); return; }
      // 还原前先把"现在这一版"也留一份，免得点错了连当前都没了
      if (hit.text && hit.text !== text) capture({ name: name, text: hit.text }, text);
      hit.text = text;
      hit.mtime = Math.round(Date.now() / 1000);
      localStorage.setItem("myonl:off:lib:v1", JSON.stringify(lib));
      if (window.__editor && window.__editor.setText) window.__editor.setText(text);
      alert("已退回 " + fmt(Math.round(Date.now() / 1000)) + " 之前那一版，当前这版也另存了一份");
      closePanel();
    } catch (e) { alert("还原失败：" + e.message); }
  }

  var panelEl = null;
  function closePanel() {
    if (panelEl && panelEl.parentNode) panelEl.parentNode.removeChild(panelEl);
    panelEl = null;
  }

  function render(rows, name) {
    closePanel();
    panelEl = document.createElement("div");
    panelEl.className = "snap-panel";  // 手机壳要用它把半透明改成实底，不然首页字会透上来
    panelEl.style.cssText = "position:fixed;inset:0;z-index:9999;background:rgba(8,12,20,.96);" +
      "display:flex;flex-direction:column;padding:16px 14px;box-sizing:border-box";
    var head = document.createElement("div");
    head.style.cssText = "display:flex;align-items:center;justify-content:space-between;margin-bottom:10px";
    var t = document.createElement("div");
    // P197d：标题只留四个字，作品名和版数换到下一行。
    // 原来一行硬塞「历史版本 · 作品名（N 个）」，手机上跟右边"关闭"压在一起。
    t.textContent = "历史版本";
    t.style.cssText = "color:#dce8ff;font-size:16px;font-weight:600;flex:0 0 auto";
    var sub = document.createElement("div");
    sub.textContent = (name || "当前作品") + " · " + rows.length + " 版";
    sub.style.cssText = "color:#8fa3c0;font-size:12px;margin:-2px 0 10px;flex:0 0 auto";
    var x = document.createElement("button");
    x.type = "button";
    x.textContent = "关闭";
    x.style.cssText = "flex:0 0 auto;padding:6px 12px;border-radius:8px;border:1px solid rgba(255,255,255,.2);" +
      "background:transparent;color:#9fb2d0;font-size:13px";
    x.onclick = closePanel;
    head.appendChild(t); head.appendChild(x);
    panelEl.appendChild(head);
    panelEl.appendChild(sub);

    var box = document.createElement("div");
    box.style.cssText = "flex:1;overflow:auto;display:flex;flex-direction:column;gap:8px";
    if (!rows.length) {
      var empty = document.createElement("div");
      empty.textContent = "还没有历史版本。改过、保存过之后，每一版都会留在这里。";
      empty.style.cssText = "color:#8fa3c0;font-size:13px;line-height:1.8;padding:20px 4px";
      box.appendChild(empty);
    }
    rows.forEach(function (r) {
      var row = document.createElement("div");
      row.style.cssText = "display:flex;align-items:center;gap:10px;padding:10px 12px;" +
        "border-radius:10px;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.09)";
      var info = document.createElement("div");
      info.style.cssText = "flex:1;min-width:0";
      var l1 = document.createElement("div");
      l1.textContent = fmt(r.at);
      l1.style.cssText = "color:#dce8ff;font-size:13px";
      var l2 = document.createElement("div");
      l2.textContent = r.size + " 字符";
      l2.style.cssText = "color:#8fa3c0;font-size:11px;margin-top:2px";
      info.appendChild(l1); info.appendChild(l2);
      var btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = "退回到这版";
      btn.style.cssText = "padding:7px 11px;border-radius:8px;border:1px solid rgba(79,140,255,.45);" +
        "background:rgba(79,140,255,.18);color:#dce8ff;font-size:12px;white-space:nowrap";
      btn.onclick = function () {
        read(r.key).then(function (rec) {
          if (!rec) { alert("这一版读不出来了"); return; }
          if (!confirm("确定退回 " + fmt(r.at) + " 那一版？现在这版会先另存一份。")) return;
          restore(r.key, rec.name, rec.text);
        });
      };
      row.appendChild(info); row.appendChild(btn);
      box.appendChild(row);
    });
    panelEl.appendChild(box);
    document.body.appendChild(panelEl);
  }

  window.MYONLSnapshotsUI = {
    // P197d：能指定作品名。作品页（还没进工程）也要能翻历史，
    // 原来只看 localStorage 里的 current，在作品页点开就是别的作品的历史。
    open: function (name) {
      var n = name || curName();
      list(n).then(function (rows) { render(rows, n); });
    }
  };
})();
