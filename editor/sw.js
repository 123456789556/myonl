/* ============================================================
   MYONL 编辑器 Service Worker · 只做分享入口这一件事

   拦截 POST /share-target（PWA share_target 把相册 / 别的 App
   分享过来的文件丢到这个地址）：解析 multipart/form-data，
   把字段 media 里的每个文件先放进 IndexedDB 的收件箱前缀
   inbox:，再 303 跳回编辑器；页面 load 时 importShared()
   会把收件箱里的记录搬进正式素材库。

   其余请求一律原样放行：这里不做离线缓存、不预置离线包
   ——编辑器走热更新，缓存会和它打架。
   ============================================================ */

var DB_NAME = "myonl-assets";
var STORE = "files";

function dbOpen() {
  return new Promise(function (res, rej) {
    var req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = function () {
      var db = req.result;
      if (!db.objectStoreNames.contains(STORE)) db.createObjectStore(STORE);
    };
    req.onsuccess = function () { res(req.result); };
    req.onerror = function () { rej(req.error || new Error("打不开素材库")); };
  });
}

function putInbox(ts, seq, file) {
  return dbOpen().then(function (db) {
    return new Promise(function (res, rej) {
      var tx = db.transaction(STORE, "readwrite");
      var st = tx.objectStore(STORE);
      var key = "inbox:" + ts + ":" + seq;
      st.put({
        name: file.name || ("shared-" + seq),
        type: file.type || "",
        blob: file,
        ts: ts,
      }, key);
      tx.oncomplete = function () { res(key); };
      tx.onerror = function () { rej(tx.error || new Error("写入收件箱失败")); };
      tx.onabort = function () { rej(tx.error || new Error("写入收件箱事务中止")); };
    });
  });
}

// 失败也留一条可区分的记录：stage 标明是 multipart 解析失败还是写库失败。
// 导入侧读到 inbox:error: 键才能把「真没给文件」和「写库失败」分开提示。
// 注意：这条链路没在真机 / 真 Chromium PWA 环境跑过（见审计 O2），这里只做到
// 「失败可区分」，不宣称真机上已复现两种失败分支。
function putError(ts, stage, err) {
  return dbOpen().then(function (db) {
    return new Promise(function (res) {
      var tx = db.transaction(STORE, "readwrite");
      var st = tx.objectStore(STORE);
      st.put({
        stage: stage,
        message: String((err && err.message) || err || "未知错误"),
        ts: ts,
      }, "inbox:error:" + ts);
      tx.oncomplete = function () { res(); };
      // 错误记录本身写不进就放弃，不能把分享入口卡死
      tx.onerror = function () { res(); };
      tx.onabort = function () { res(); };
    });
  }).catch(function () { /* 收件箱都打不开，只能放弃 */ });
}

function handleShare(request) {
  var ts = Date.now();
  return request.formData().then(function (form) {
    var files = form.getAll("media").filter(function (f) {
      return f && typeof Blob !== "undefined" && f instanceof Blob;
    });
    var chain = Promise.resolve();
    files.forEach(function (file, i) {
      chain = chain.then(function () { return putInbox(ts, i + 1, file); });
    });
    // 写库失败单独标 stage=write，与解析失败分开
    return chain.catch(function (err) {
      return putError(ts, "write", err);
    });
  }).catch(function (err) {
    // multipart 解析失败 / 请求体拿不到：标 stage=parse
    return putError(ts, "parse", err);
  }).then(function () {
    var dest = new URL("/index.html?shared=1", self.location.href).toString();
    return Response.redirect(dest, 303);
  });
}

self.addEventListener("fetch", function (event) {
  var request = event.request;
  if (request.method === "POST" &&
      new URL(request.url).pathname === "/share-target") {
    event.respondWith(handleShare(request));
    return;
  }
  // 其余请求直接放行：不缓存、不预置离线包、不截胡
  return;
});
