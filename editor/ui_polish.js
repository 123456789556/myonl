/* P188 主链路收口（诊断第二轮）：只补"从打开到做出第一个能玩的游戏"路上的断点。
 *
 * 为什么单独一个文件：editor_main / editor_pro / editor_shell 都已顶到行数预算，
 * 规矩是「要加功能就加在新文件里」。这里全部走 DOM 层增量，不改主脚本逻辑：
 *   1 顶栏说清"我在哪、能回哪"：‹ 作品列表 + 作品名，「文件」改叫「菜单」；
 *   2 保存状态说人话：✓ 已保存·刚刚 / ● 未保存·点按保存（点一下就存）；
 *   3 回「剧本」tab 永远落逐句编辑；源码标成高级，附一行语法提示 + ? 面板；
 *   4 预览有台词就直接演那一句（背景有就铺背景），不再说"去电脑上打开"；
 *   5 「检查无误·N 条」改成"共 N 行"，点一下看检查器逐行明细；
 *   6 导入素材后的指令菜单在手机上改成底部动作单：设为背景 / 插入剧本 / 稍后再说。
 */
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var MQ = window.matchMedia("(max-width: 860px), (max-height: 520px), " +
    "(pointer: coarse) and (hover: none) and (max-width: 1400px)");
  function narrow() { return MQ.matches; }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  /* ---- 1 顶栏：返回要有名字，中间要是作品名而不是 script.gal ---- */
  function fixTopbar() {
    if (!narrow()) return;
    var back = $("mHomeBack");
    if (back && !back.querySelector(".mb-back-txt")) {
      var s = document.createElement("span");
      s.className = "mb-back-txt";
      s.textContent = "作品列表";
      back.appendChild(s);
    }
    var fm = document.querySelector('.menubar .menu-item[data-menu="file"]');
    if (fm && fm.textContent !== "菜单") fm.textContent = "菜单";
    var t2 = document.querySelector(".m-title2");
    if (!t2) {
      t2 = document.createElement("span");
      t2.className = "m-title m-title2";
      var anchor = fm || $("mFullscreen");
      if (anchor && anchor.parentNode) anchor.parentNode.insertBefore(t2, anchor);
    }
    var name = "";
    try { name = JSON.parse(localStorage.getItem("myonl:off:lib:v1") || "{}").current || ""; } catch (e) { }
    if (!name) name = (($("filePath") || {}).textContent || "").trim();
    if (t2.textContent !== name) { t2.textContent = name; t2.title = name; }
  }

  /* ---- 2 保存状态：多久前存的 / 未保存点一下就存 ---- */
  var lastSaveAt = 0, wasDirty = false;
  function relTime(ts) {
    var d = Math.max(0, Date.now() - ts) / 1000;
    if (d < 45) return "刚刚";
    if (d < 3600) return Math.round(d / 60) + " 分钟前";
    if (d < 86400) return Math.round(d / 3600) + " 小时前";
    return Math.round(d / 86400) + " 天前";
  }
  function syncSave() {
    var sb = $("sbSave");
    if (!sb) return;
    // 手机状态栏有一条 :not(#status):not(#sbLine) 的 display:none!important（两个 id  specificity），
    // 样式表压不过它，用内联 important 把保存状态放出来——手机上看不见保存状态等于没有。
    if (narrow()) sb.style.setProperty("display", "inline-flex", "important");
    else sb.style.removeProperty("display");
    var dirty = !!(window.__proDirty && window.__proDirty());
    if (wasDirty && !dirty) lastSaveAt = Date.now();
    wasDirty = dirty;
    if (dirty) {
      sb.textContent = "● 未保存 · 点按保存";
      sb.title = "有未保存修改：点这里或 Ctrl+S 保存";
    } else {
      sb.textContent = lastSaveAt ? ("✓ 已保存 · " + relTime(lastSaveAt)) : "✓ 已保存";
      sb.title = lastSaveAt ? ("上次保存：" + relTime(lastSaveAt)) : "所有修改已保存";
    }
    sb.classList.toggle("dirty", dirty);
  }
  function hookSaveSync() {
    var orig = window.__statusSaveSync;
    if (!orig || orig.__polished) return;
    var wrapped = function () { orig(); syncSave(); };
    wrapped.__polished = true;
    window.__statusSaveSync = wrapped;
  }
  document.addEventListener("click", function (e) {
    var sb = e.target && e.target.closest ? e.target.closest("#sbSave") : null;
    if (!sb) return;
    if (window.__proDirty && window.__proDirty()) { var b = $("btnSave"); if (b) b.click(); }
  });

  /* ---- 3 剧本 tab：回来永远落逐句；源码是高级选项 ---- */
  document.addEventListener("click", function (e) {
    var t = e.target && e.target.closest ? e.target.closest('.m-tab[data-tab="script"]') : null;
    if (!t || !narrow()) return;
    setTimeout(function () {
      if (document.querySelector("#scenePage.open")) return;  // 已经在逐句里，别把详情踢回列表
      var b = document.querySelector('.m-mode[data-mode="sent"]');
      if (b) b.click();
    }, 80);
  });
  var synEl = null;
  function openSyntax() {
    if (synEl) { synEl.remove(); synEl = null; return; }
    synEl = document.createElement("div");
    synEl.className = "m-syntax";
    var rows = [
      ["@[名字] 台词内容", "让角色说一句"],
      ["@ 台词内容", "旁白（不写说话人）"],
      ["@bg 图片名", "换背景（素材库里的名字）"],
      ["@music 音频名", "换音乐"],
      ["@show 角色 表情", "角色登场"],
      ["@label 名字", "一幕的开始"],
      ["@jump 名字", "演完跳到另一幕"],
      ["# 任意文字", "注释：给自己看的，不会演出来"]
    ];
    synEl.innerHTML = '<div class="m-syntax-head">常用语法 · 点外面关闭</div>' +
      rows.map(function (r) {
        return '<div class="m-syntax-row"><code>' + esc(r[0]) + "</code><span>" + esc(r[1]) + "</span></div>";
      }).join("") +
      '<div class="m-syntax-foot">选项、跳转不用背指令：逐句编辑页里直接加。</div>';
    document.body.appendChild(synEl);
    setTimeout(function () {
      document.addEventListener("click", function off(ev) {
        if (synEl && !synEl.contains(ev.target) && !ev.target.closest(".m-codehelp")) {
          synEl.remove(); synEl = null;
        }
        document.removeEventListener("click", off);
      });
    }, 0);
  }
  function fixModeBar() {
    var code = document.querySelector('.m-mode[data-mode="code"]');
    if (code && code.textContent === "源码") code.textContent = "源码（高级）";
    var bar = document.querySelector(".m-modebar");
    if (!bar) return;
    var hint = document.querySelector(".m-codehint");
    var on = code && code.classList.contains("on");
    if (on && !hint) {
      hint = document.createElement("div");
      hint.className = "m-codehint";
      hint.innerHTML = "<span># 开头是注释，@ 开头是台词或指令</span>" +
        '<button type="button" class="m-codehelp">? 语法</button>';
      bar.parentNode.insertBefore(hint, bar.nextSibling);
      hint.querySelector(".m-codehelp").addEventListener("click", openSyntax);
    } else if (!on && hint) hint.remove();
  }

  /* ---- 4 预览：有台词就演那一句，背景有就铺上 ---- */
  // 认法跟 engine/parser.py 对齐（不是跟场景表单对齐）：
  //   "@ 文本" 是旁白；只有首词是已登记角色（@character）才算角色台词；
  //   "@[名字] 文本" 角色台词；"@[[名字]] 文本" 整屏独白；"@[[文本]]" 整屏旁白；
  //   "@" 或 "@[名字]" 单独一行时，下一行整行是台词。
  function parseSay(t, chars) {
    if (t === "@") return { who: "", text: "", next: true, nvl: false };
    if (t.indexOf("@[[") === 0) {
      var c2 = t.indexOf("]]", 3);
      if (c2 > 3) {
        var inner = t.slice(3, c2).trim(), rest2 = t.slice(c2 + 2).trim();
        return rest2 ? { who: inner, text: rest2, nvl: true } : { who: "", text: inner, nvl: true };
      }
      return null;
    }
    if (t.indexOf("@[") === 0) {
      var depth = 0, close = -1;
      for (var k = 2; k < t.length; k++) {
        var ch = t.charAt(k);
        if (ch === "[") depth += 1;
        else if (ch === "]") { if (depth === 0) { close = k; break; } depth -= 1; }
      }
      if (close > 2) {
        var w = t.slice(2, close).trim(), rest = t.slice(close + 1).trim();
        if (w) return rest ? { who: w, text: rest, nvl: false } : { who: w, text: "", next: true, nvl: false };
      }
      return null;
    }
    if (t.charAt(0) !== "@" || !/^@\s/.test(t)) return null;
    var body = t.slice(1).trim();
    if (!body) return null;
    var sp = body.indexOf(" ");
    var head = sp > 0 ? body.slice(0, sp) : body;
    var tail = sp > 0 ? body.slice(sp + 1).trim() : "";
    if (chars[head] && tail) return { who: head, text: tail, nvl: false };
    if (head === "旁白" && tail) return { who: "", text: tail, nvl: false };
    return { who: "", text: body, nvl: false };
  }
  function previewInfo() {
    var ta = (window.__editor && window.__editor.sourceEl) || $("source");
    if (!ta) return null;
    var lines = String(ta.value || "").split("\n");
    var anchor = window.__previewAnchorLine || 0;
    var chars = {}, says = [], bg = "";
    for (var c = 0; c < lines.length; c++) {
      var mc = lines[c].trim().match(/^@character\s+(\S+)/);
      if (mc) chars[mc[1]] = 1;
    }
    for (var i = 0; i < lines.length; i++) {
      var t = lines[i].trim();
      if (!t || t.charAt(0) === "#") continue;
      var mb = t.match(/^@bg\s+(\S+)/);
      if (mb) { if (!anchor || i + 1 <= anchor) bg = mb[1]; continue; }
      var s = parseSay(t, chars);
      if (!s) continue;
      if (s.next) {
        var nx = (lines[i + 1] || "").trim();
        if (!nx || nx.charAt(0) === "@") continue;
        s.text = nx; i += 1;
      }
      if (s.text) says.push({ line: i + 1, who: s.who, text: s.text, nvl: s.nvl });
    }
    if (!says.length) return null;
    var pick = null;
    if (anchor) for (var j = 0; j < says.length; j++) if (says[j].line <= anchor) pick = says[j];
    if (!pick) pick = says[says.length - 1];
    return { say: pick, bg: bg, total: says.length };
  }
  function renderTextPreview() {
    var wrap = $("previewWrap");
    if (!wrap) return;
    var ph = wrap.querySelector(".preview-placeholder");
    if (!ph) return;
    var bar = document.querySelector(".preview-bar span");
    var info = previewInfo();
    if (!info) {
      if (bar && /手机版不画画面|这一版不渲染画面/.test(bar.textContent))
        bar.textContent = "先写一句台词，预览就会把那一句演出来";
      return;
    }
    var sig = info.say.line + "|" + info.say.who + "|" + info.say.text + "|" + info.bg;
    if (ph.getAttribute("data-txtsig") === sig) return;
    ph.setAttribute("data-txtsig", sig);
    ph.classList.add("txt-stage");
    var who = info.say.who, text = info.say.text;
    ph.innerHTML =
      (info.bg ? '<img class="tx-bg" alt="" src="/api/asset/images/' + encodeURIComponent(info.bg) + '">' : "") +
      '<div class="tx-top"><span>第 ' + info.say.line + " 行 · 共 " + info.total + " 句</span>" +
      '<button type="button" class="tx-run">试玩</button></div>' +
      '<div class="tx-box' + (info.say.nvl ? " tx-nvl" : "") + '">' + (who ? '<div class="tx-who">' + esc(who) + "</div>" : "") +
      '<div class="tx-text">' + esc(text) + "</div></div>";
    var img = ph.querySelector(".tx-bg");
    if (img) {
      img.addEventListener("error", function () { img.classList.add("miss"); });
      img.addEventListener("load", function () { img.classList.remove("miss"); });
    }
    ph.querySelector(".tx-run").addEventListener("click", function () { var r = $("btnRun"); if (r) r.click(); });
    if (bar) bar.textContent = info.bg
      ? "背景与台词按剧本生成 · 试玩看完整演出"
      : "当前场景未设置背景图 · 试玩时会自动使用渐变背景";
  }

  /* ---- 5 检查状态：说清 N 是什么，点一下看明细 ---- */
  function fixStatus() {
    var st = $("status");
    if (!st) return;
    var m = st.textContent.match(/^检查无误 · (\d+) 条$/);
    if (m) {
      st.textContent = "检查无误 · 共 " + m[1] + " 行";
      st.title = "点一下看每一行是什么";
      st.classList.add("sb-tap");
    }
  }
  document.addEventListener("click", function (e) {
    var st = e.target && e.target.closest ? e.target.closest("#status.sb-tap") : null;
    if (!st) return;
    if (narrow()) { var pv = document.querySelector('.m-tab[data-tab="preview"]'); if (pv) pv.click(); }
    setTimeout(function () {
      var it = document.querySelector('.right-tab[data-right-tab="inspector"]');
      if (it) it.click();
    }, 120);
  });

  /* ---- 6 导入后的指令菜单：手机上改成底部动作单 ---- */
  function fixInsertMenu(menu) {
    if (!narrow() || menu.__polished) return;
    menu.__polished = true;
    var head = document.createElement("div");
    head.className = "ins-head";
    head.textContent = "素材已添加 · 拿它做什么？";
    menu.insertBefore(head, menu.firstChild);
    Array.prototype.forEach.call(menu.querySelectorAll("button"), function (b) {
      var t = b.textContent, m;
      if ((m = t.match(/^@bg (.+)（作背景）$/))) b.innerHTML = "<b>设为背景</b><i>" + esc(m[1]) + "</i>";
      else if ((m = t.match(/^@cg (.+)（作 CG \/ 回忆画面）$/))) b.innerHTML = "<b>插成 CG 画面</b><i>" + esc(m[1]) + "</i>";
      else if ((m = t.match(/^@show (.+)（(?:登场立绘|作立绘[^）]*)）$/))) b.innerHTML = "<b>插角色登场到剧本</b><i>" + esc(m[1]) + (/需补参数/.test(t) ? "（把角色ID/表情换成真名字）" : "") + "</i>";
      else if ((m = t.match(/^@character (.+)（注册角色）$/))) b.innerHTML = "<b>登记成角色</b><i>" + esc(m[1]) + "</i>";
      else if ((m = t.match(/^@music (.+)（.*）$/))) b.innerHTML = "<b>设为音乐</b><i>" + esc(m[1]) + "</i>";
      else if ((m = t.match(/^@ (.+)（写一句台词）$/))) b.innerHTML = "<b>给这个角色写一句</b><i>" + esc(m[1]) + "</i>";
      else if (/^跳过/.test(t)) b.innerHTML = "<b>稍后再说</b><i>只放进素材库，不插进剧本</i>";
    });
  }
  new MutationObserver(function (muts) {
    muts.forEach(function (mu) {
      Array.prototype.forEach.call(mu.addedNodes, function (n) {
        if (n.nodeType === 1 && n.classList && n.classList.contains("insert-menu")) fixInsertMenu(n);
      });
    });
  }).observe(document.body, { childList: true });

  /* ---- 7 从首页点「新建」：取消要回首页，别把人留在空编辑器里 ---- */
  var newFromHome = false;
  document.addEventListener("click", function (e) {
    var t = e.target;
    if (!t || !t.closest) return;
    if (t.closest("#mHomeNew") || t.closest('.m-nav-item[data-nav="new"]')) newFromHome = true;
    if (t.closest("#newGameCancel") && newFromHome) {
      newFromHome = false;
      if (window.__myonlShowHome) window.__myonlShowHome();
    }
  }, true);

  /* ---- 8 「设为背景」要属于正在写的这一句 ----
     指令默认插在光标处（当前行末尾→下一行），而预览锚点是光标所在那句台词：
     背景落在锚点之后就被判成「下一段的背景」，预览不铺。
     把刚插的 @bg/@cg 行挪到「当前这一句」前面。光标停在末尾空行（写完还没写下一句）
     是常态，这时回退到最后一条正文行——用户点「设为背景」说的是这一场景，不是下一段。 */
  document.addEventListener("click", function (e) {
    var b = e.target && e.target.closest ? e.target.closest(".insert-menu button") : null;
    if (!b) return;
    var bb = b.querySelector("b"), ii = b.querySelector("i");
    if (!bb || !ii) return;
    var pre = bb.textContent === "设为背景" ? "@bg " : (bb.textContent === "插成 CG 画面" ? "@cg " : "");
    if (!pre) return;
    var ta = $("source");
    if (!ta) return;
    var preLine = ta.value.slice(0, ta.selectionStart).split("\n").length - 1;
    var dir = pre + ii.textContent;
    setTimeout(function () {
      var lines = ta.value.split("\n"), idx = -1;
      for (var i = lines.length - 1; i >= 0; i--) if (lines[i].trim() === dir) { idx = i; break; }
      if (idx < 0) return;
      var pick = Math.min(preLine, lines.length - 1);
      while (pick > 0 && (!lines[pick].trim() || lines[pick].trim() === dir || lines[pick].trim().charAt(0) === "#")) pick--;
      if (!lines[pick] || !lines[pick].trim() || lines[pick].trim() === dir) pick = 0;
      if (idx === pick) return;
      lines.splice(idx, 1);
      lines.splice(pick, 0, dir);
      ta.value = lines.join("\n");
      var pos = 0;
      for (var j = 0; j <= pick + 1 && j < lines.length; j++) pos += lines[j].length + 1;
      ta.selectionStart = ta.selectionEnd = Math.min(pos, ta.value.length);
      ta.dispatchEvent(new Event("input", { bubbles: true }));
    }, 0);
  }, true);

  /* ---- 9 逐句/源码分段提为固定条 ----
     分段原来埋在左栏里，场景页（fixed 全屏）一开就把它盖住：默认逐句之后
     用户永远摸不到「源码」。剧本 tab 且没有别的二级页时提为固定条，
     场景页整体下移让位；源码态左栏加 padding 不被压。 */
  function syncModeSlot() {
    var b = document.body;
    var cur = document.querySelector(".m-tab.active");
    var onScript = narrow() && (!cur || cur.dataset.tab === "script") && !b.classList.contains("m-home-open");
    var other = false;
    document.querySelectorAll(".center-page.open").forEach(function (p) {
      if (p.id !== "scenePage") other = true;
    });
    var on = onScript && !other;
    b.classList.toggle("m-script-tab", on);
    if (on) {
      var mb = document.querySelector(".menubar");
      if (mb) document.documentElement.style.setProperty("--mb-top", Math.round(mb.getBoundingClientRect().bottom) + "px");
    }
    // 打字时快捷条压在状态栏上，保存点不到：把状态栏抬到快捷条上面
    if (b.classList.contains("m-typing")) {
      var kb = document.querySelector(".m-keybar");
      if (kb) document.documentElement.style.setProperty("--kb-bottom", kb.style.bottom || "30px");
    }
  }

  /* ---- 启动 ---- */
  function tick() {
    fixTopbar(); hookSaveSync(); syncSave(); fixModeBar(); fixStatus(); renderTextPreview(); syncModeSlot();
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { tick(); setInterval(tick, 700); });
  } else { tick(); setInterval(tick, 700); }
  var pw = $("previewWrap");
  if (pw) new MutationObserver(renderTextPreview).observe(pw, { childList: true, subtree: true });
})();