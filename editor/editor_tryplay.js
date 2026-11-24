/* P201 · 在编辑器里把整部作品从头跑一遍
 *
 * 为什么以前不行：手机底栏「预览」里那颗「试玩」调的是 /api/run —— 这条路由只存在于电脑那套
 * Python 后端，离线内核（gal_offline.js）里根本没有。点下去必然失败，可旁边的文案写着
 * 「试玩看完整演出」。这一版把它做成真的。
 *
 * 做法不另写第二套播放逻辑：把「导出的那份成品」编出来，塞进全屏 iframe 跑。
 * 成品是唯一真相 —— 试玩跑得通，导出就一定能跑；反过来也成立。代价是每次进来都要重编一遍
 * （素材小的时候一两秒，大项目十几秒，所以有 MAX_MB 上限，超了直接说清并指路导出）。
 *
 * 只在离线内核里接管（__MYONL_OFFLINE）。电脑端那颗「运行」还是拉独立窗口，不动。
 */
(function (global) {
  "use strict";
  if (!global.__MYONL_OFFLINE) return;

  var MAX_MB = 40;   // 手机上一份 40 MB 的 HTML，编一次要十几秒、还可能白屏，不如去导出
  var layer = null, frame = null, srcUrl = null, busy = false, pushed = false;

  function mk(tag, css, text) {
    var n = document.createElement(tag);
    if (css) n.style.cssText = css;
    if (text != null) n.textContent = text;
    return n;
  }

  function note(text) {
    var n = layer && layer.querySelector("[data-msg]");
    if (n) n.textContent = text;
  }

  function fail(msg) {
    busy = false;
    if (!layer) return;
    var body = layer.querySelector("[data-body]");
    if (!body) return;
    body.innerHTML = "";
    body.appendChild(mk("div",
      "padding:30px 22px 8px;color:#c9d7ea;font-size:14px;line-height:1.75;white-space:pre-line", msg));
    body.appendChild(mk("div",
      "padding:0 22px;color:#8fa3bf;font-size:12.5px;line-height:1.7",
      "要看整部，去底部「导出」出网页版 HTML，存到手机里点开——那条出口是通的，而且导出的成品跟这里跑的是同一份。"));
    note("没跑起来");
  }

  function destroy() {
    if (frame) { try { frame.src = "about:blank"; } catch (e) { } frame = null; }
    if (srcUrl) { try { URL.revokeObjectURL(srcUrl); } catch (e) { } srcUrl = null; }
    if (layer) { layer.remove(); layer = null; }
    busy = false;
  }

  function requestClose() {
    if (pushed) {
      pushed = false;
      try { history.back(); return; } catch (e) { }
    }
    destroy();
  }

  function run() {
    var build = global.__myonlBuildPackHtml;
    if (!build) { fail("打包器没加载，刷新一下再来"); return; }
    if (layer) note("正在把剧本编成成品…");
    build().then(function (r) {
      if (!layer) return;                       // 编的过程中人已经退了
      if (r.mb > MAX_MB) {
        fail("素材约 " + r.mb + " MB，超过 " + MAX_MB + " MB 就不在编辑器里跑了——\n" +
             "光编出来就要十几秒，低端机还可能白屏。");
        return;
      }
      srcUrl = URL.createObjectURL(new Blob([r.html], { type: "text/html;charset=utf-8" }));
      frame = document.createElement("iframe");
      frame.title = "试玩";
      frame.style.cssText = "width:100%;height:100%;border:0;display:block;background:#000";
      // 不能往 blob URL 后面拼 ?shellbar=1 —— 一拼 origin 就变成不透明的，外层连
      // contentDocument 都读不到（探针当场报 SecurityError）。改成 load 之后直接写标志：
      // 播放器的 drawExitChip 每帧重算，下一帧就不再画它那颗浮动「退出试玩」。
      frame.addEventListener("load", function () {
        try { frame.contentWindow.__MYONL_HOSTBAR = true; } catch (e) { }
      });
      frame.src = srcUrl;
      var body = layer.querySelector("[data-body]");
      if (!body) return;
      body.innerHTML = "";
      body.appendChild(frame);
      note(r.mb > 0
        ? ("整部从头跑 · 约 " + r.mb + " MB · 改完退出再演一遍")
        : "整部从头跑（还没放素材）· 改完退出再演一遍");
      busy = false;
    }).catch(function (e) {
      if (!layer) return;
      fail(e && e.line ? ("剧本第 " + e.line + " 行：" + e.message) : ((e && e.message) || "编成品失败"));
    });
  }

  function open() {
    if (busy || layer) return;
    busy = true;
    layer = mk("div",
      "position:fixed;inset:0;z-index:2147483000;background:#0b111c;display:flex;flex-direction:column");
    layer.id = "mTryPlay";

    var bar = mk("div",
      "flex:0 0 auto;height:46px;display:flex;align-items:center;gap:10px;padding:0 10px;" +
      "background:#111a29;border-bottom:1px solid rgba(255,255,255,.08);box-sizing:border-box");
    var exit = mk("button",
      "flex:0 0 auto;padding:7px 12px;border-radius:4px;border:1px solid rgba(79,140,255,.5);" +
      "background:rgba(79,140,255,.16);color:#dce8ff;font-size:13px;font-weight:600;font-family:inherit",
      "✕ 退出试玩");
    exit.type = "button";
    exit.addEventListener("click", requestClose);
    var msg = mk("div",
      "flex:1 1 auto;min-width:0;font-size:12px;color:#9fb2d0;overflow:hidden;" +
      "text-overflow:ellipsis;white-space:nowrap", "正在编成品…");
    msg.setAttribute("data-msg", "1");
    bar.appendChild(exit);
    bar.appendChild(msg);

    var body = mk("div", "flex:1 1 auto;position:relative;overflow:hidden;background:#000");
    body.setAttribute("data-body", "1");
    var wait = mk("div",
      "position:absolute;inset:0;display:flex;align-items:center;justify-content:center;text-align:center;" +
      "padding:24px;color:#8fa3bf;font-size:13px;line-height:1.8;white-space:pre-line",
      "正在把剧本编成成品…\n第一次会慢一点，同一份作品再来会快些");
    body.appendChild(wait);

    layer.appendChild(bar);
    layer.appendChild(body);
    document.body.appendChild(layer);

    try { history.pushState({ mTryPlay: 1 }, ""); pushed = true; } catch (e) { pushed = false; }

    // 先让这一层画出来再去干重活：编几十 MB 的字符串会把主线程占满，不先画就是白屏几秒
    setTimeout(run, 20);
  }

  // 手机上那颗「试玩」在预览面板里（.tx-run），它内部会去点 #btnRun。
  // 捕获阶段拦在 document 上：既拦住了 .tx-run 自己的处理，也拦住了 #btnRun 打后端的请求。
  document.addEventListener("click", function (e) {
    var t = e.target && e.target.closest ? e.target.closest("#btnRun, .tx-run") : null;
    if (!t) return;
    if (t.id === "btnRun" && t.disabled) return;
    e.preventDefault();
    e.stopPropagation();
    open();
  }, true);

  global.addEventListener("popstate", function () {
    if (layer) { pushed = false; destroy(); }
  });

  // 播放器自己在嵌入状态下想退出时发这条消息（见 myonl-player.js 的 exitDemo）。
  // 它菜单里的「退出」也能走到这里，不必再点外层那颗按钮。
  global.addEventListener("message", function (e) {
    if (!layer || !e.data || e.data.type !== "myonl-exit-demo") return;
    requestClose();
  });

  global.MYONLTryPlay = {
    open: open,
    close: requestClose,
    state: function () {
      return { layer: !!layer, busy: busy, iframe: !!frame, mb: frame ? null : null };
    }
  };
})(window);
