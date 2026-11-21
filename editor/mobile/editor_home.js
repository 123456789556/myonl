/* ===================================================================
   P65：手机端第一层「工作台」
   打开就是工程卡片（最近用的排前面），点一张才进编辑器。
   桌面端（>860px）不接管，直接进编辑器 —— 电脑上三列 IDE 是合适的。
   =================================================================== */
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };

  var EDIT_KEY = "myonl:editing";
  // 横屏「左列表 / 右详情」里当前选中的作品目录。竖屏用不到，但两种形态共用同一个渲染函数。
  var selFolder = null;
  // 搜索：全量列表留一份，输入即过滤。空字符串 = 不筛。
  var allProjects = [];
  var findQ = "";

  var isMobile = function () { return window.matchMedia && window.matchMedia("(max-width:860px), (max-height:520px)").matches; };
  if (!isMobile()) return;

  // 编辑器里的「‹ 作品」按钮调它：清掉「已在编辑」标记后重载回工作台
  window.__myonlShowHome = function () {
    try { sessionStorage.removeItem(EDIT_KEY); } catch (e) {}
    location.reload();
  };

  // 安卓返回键协议：壳（MainActivity.onBackPressed）会问 window.myonlBack()，
  // 只有拿到 true 才不 finish()。实测编辑器页以前根本没有这个函数 ——
  // 按一下返回，整个应用直接退出，没保存的编辑全丢。
  // 必须挂在下面两条早退之前：第二条「已经在编辑器里」一 return，
  // 这个函数就永远没被挂上，正好是最需要它的那个页面。
  window.myonlBack = function () {
    // 1. 试玩层开着 → 先关层。用户按返回的本意是"退出试玩"，不是"退出应用"
    if ($("mDemoLayer")) {
      try { closeDemo(); } catch (e) { }
      return true;
    }
    // 1.5 设置 / 教程抽屉开着 → 先关抽屉。返回键逐层退：抽屉 → 作品列表 → 退出应用
    if (sheet) { sheet.remove(); sheet = null; return true; }
    if (tutSheet) { tutSheet.remove(); tutSheet = null; return true; }
    // 1.6 作品页开着 → 退回作品列表（P197：这一层是新增的，返回键要认得它）
    if (typeof workEl !== "undefined" && workEl) { workEl.remove(); workEl = null; return true; }
    // 2. 正在编辑某个作品 → 回工作台，而不是把应用退掉
    try {
      if (sessionStorage.getItem(EDIT_KEY) === "1") {
        window.__myonlShowHome();
        return true;
      }
    } catch (e) { /* 隐私模式下 sessionStorage 会抛，按工作台处理 */ }
    // 3. 工作台本身就是最外层，返回就是退出应用 —— 交给壳
    return false;
  };

  // P197：作品页点「播放 / 素材 / 导出」会整页 reload（工程根变了）。reload 后这个 IIFE
  // 会先撞上下面那条「已在编辑器里就 return」，所以接住待打开 tab 的代码必须放在它前面。
  function firePendingTab() {
    var tab = null;
    try { tab = sessionStorage.getItem("myonl:enterTab"); } catch (e) {}
    if (!tab) return;
    var tries = 0;
    var tick = function () {
      var b = document.querySelector('.m-tab[data-tab="' + tab + '"]');
      if (b) {
        try { sessionStorage.removeItem("myonl:enterTab"); } catch (e) {}
        b.click();
        return;
      }
      if (++tries < 15) setTimeout(tick, 120);
    };
    setTimeout(tick, 200);
  }
  firePendingTab();

  try { if (sessionStorage.getItem(EDIT_KEY) === "1") return; } catch (e) {}

  // 编辑器自己的层先别渲染，等用户从工作台点进去
  function hideEditor(on) {
    var main = document.querySelector(".main");
    var menu = document.querySelector(".menubar");
    var st = document.querySelector(".statusbar");
    // P193：编辑器那条「剧本 / 素材 / 导出」底栏也要一起藏。editor.css 里那条
    // body.m-home-open .m-tabbar 实测没进 CSSOM（10 条 tabbar 规则独缺它），所以首页
    // 第一层和第二层两套导航同时在场。这里用 visibility 兜住，不赌样式表顺序。
    var tb = document.querySelector(".m-tabbar");
    [main, menu, st, tb].forEach(function (el) {
      if (!el) return;
      el.style.visibility = on ? "hidden" : "";
    });
  }
  hideEditor(true);
  // 底栏比这层晚一点才建好（shell 的 buildMobileUI），补一次，别让它漏出来
  setTimeout(function () { hideEditor(true); }, 400);

  var layer = document.createElement("div");
  layer.className = "m-home";
  // P116：首页自成一屏，不掺编辑器那套 tab —— 那五个 tab 是「作品内部」的事，
  // 摆在工作台底下等于让人以为首页还有五个没展开的页。
  document.body.classList.add("m-home-open");
  // 书架空着时说明卡（"都在你手上…"）收起来：第一次打开的人面前不该同时摆七块可读的东西。
  // 这个类名改由 render 按 /api/home 的真实条数来加 —— 原来这里读 localStorage 的离线库，
  // 服务端有作品、离线库还没同步时，首页会同时处于"空态样式"和"有卡"的矛盾状态
  // （空态下 CSS 会藏掉卡片里的说明文本、把列表当空容器）。
  layer.innerHTML =
    '<div class="m-home-head">' +
      '<div class="m-home-hid">' +
        '<div class="m-home-title">我的作品</div>' +
        '<div class="m-home-sub" id="mHomeSub"></div></div>' +
      '<button type="button" class="m-home-find" id="mHomeFind" aria-label="搜作品">' +
        '<svg viewBox="0 0 16 16" width="18" height="18" fill="none" stroke="currentColor" ' +
          'stroke-width="1.5" stroke-linecap="round" aria-hidden="true">' +
          '<circle cx="6.8" cy="6.8" r="4.2"/><path d="M9.9 9.9L13.4 13.4"/></svg>' +
      '</button>' +
    '</div>' +
    // 搜索是真过滤：打字就把卡片筛掉，不是摆一个假框。作品多了才用得上。
    '<div class="m-home-findbox" id="mHomeFindBox" hidden>' +
      '<input type="search" id="mHomeFindInput" placeholder="搜作品名" autocomplete="off" ' +
        'enterkeyhint="search">' +
      '<button type="button" id="mHomeFindClear">取消</button>' +
    '</div>' +
    '<div class="m-home-list" id="mHomeList"></div>' +
    // P193d：横屏（平板 / 横过来的手机）右侧的「最近在改」详情。
    // 竖屏不显示（CSS 收掉）—— 竖屏一屏只放一个主角，列表就是主角。
    '<div class="m-home-detail" id="mHomeDetail"></div>' +
    '<div class="m-home-side">' +
      // P194：这组「新建作品 / 导入作品」两格删了 —— 底栏第三、四格就是同一个动作，
      // 一屏摆两处同一件事，人会以为是两条不同的路。
      // P194：新手教程引导卡也整条删了（用户：这块可以删）。教程入口收进底栏第二格。
      // 用户要的那段说明保留：一句话、讲清"现在能做什么"。
      '<div class="m-home-tip">没图没音乐也能先写台词，画面在「素材」里补。</div>' +
      // P176：这里原本还有一块「三步上手」。删了 —— 编辑器菜单里已经有
      // 「帮助 → 新手引导」，同一套教程摆两处，首页就多占五六行高度。
    '</div>' +
    // 底部导航：手机/平板拇指够得到的位置。P194 起五格，全是真动作，不留哑按钮：
    // 作品 / 教程 / 新建 / 导入 / 设置。教程和设置原来散在首页卡片和页头右上角，
    // 收进底栏后首页正文只剩作品列表，一屏一个主角。
    '<div class="m-home-nav" id="mHomeNav">' +
      '<button type="button" class="m-nav-item on" data-nav="home">' +
        ico('M2.6 4.2h10.8v8.2a.8.8 0 0 1-.8.8H3.4a.8.8 0 0 1-.8-.8V4.2zM2.6 6.6h10.8') +
        '<span>作品</span></button>' +
      '<button type="button" class="m-nav-item" data-nav="tut" id="mHomeTut">' +
        ico('M3 2.8h7.2a2 2 0 0 1 2 2v8.4H5a2 2 0 0 1-2-2V2.8zM5.4 5.6h4.4M5.4 8h4.4') +
        '<span>教程</span></button>' +
      '<button type="button" class="m-nav-item m-nav-main" data-nav="new">' +
        '<span class="m-nav-main-ic">' + ico('M8 2.2v11.6M2.2 8h11.6') + '</span>' +
        '<span>新建</span></button>' +
      '<button type="button" class="m-nav-item" data-nav="import">' +
        ico('M8 2.2v7.4M4.9 6.6l3.1 3.1 3.1-3.1M2.6 12.6h10.8') +
        '<span>导入</span></button>' +
      '<button type="button" class="m-nav-item" data-nav="set">' +
        ico('M8 5.4a2.6 2.6 0 1 0 0 5.2 2.6 2.6 0 0 0 0-5.2zM8 2.4v1.4M8 12.2v1.4M2.4 8h1.4M12.2 8h1.4M4 4l1 1M11 11l1 1M12 4l-1 1M5 11l-1 1') +
        '<span>设置</span></button>' +
    '</div>';
  document.body.appendChild(layer);

  // 一个图标：单色线条、16 网格、跟着父级颜色（currentColor），
  // 这样深色浅色两套主题都不用为图标写第二份样式。
  function ico(d) {
    return '<svg viewBox="0 0 16 16" width="17" height="17" fill="none" ' +
      'stroke="currentColor" stroke-width="1.4" stroke-linecap="round" ' +
      'stroke-linejoin="round" aria-hidden="true"><path d="' + d + '"/></svg>';
  }

  function ago(ts) {
    var d = (Date.now() / 1000) - ts;
    if (d < 3600) return Math.max(1, Math.round(d / 60)) + " 分钟前";
    if (d < 86400) return Math.round(d / 3600) + " 小时前";
    if (d < 86400 * 30) return Math.round(d / 86400) + " 天前";
    return new Date(ts * 1000).toLocaleDateString();
  }

  function card(p, old) {
    var folder = p.folder.replace(/"/g, "&quot;");
    var name = p.name.replace(/</g, "&lt;");
    // 以前第一张做成整宽大卡（封面铺满、底部渐深）。一张卡吃满一屏，
    // 作品一多就变成"上面一大块、下面挤成一条"，而且没封面时那块空的
    // 蓝色渐变比什么都重。现在统一成横向小卡：一屏能看到五六个，
    // 「新建 / 导入」也不会被压到底。
    return '<button type="button" class="m-home-card' + (old ? " m-card-old" : "") +
      '" data-folder="' + folder + '">' +
      '<span class="m-card-thumb" data-folder="' + folder + '"></span>' +
      '<span class="m-card-body">' +
        '<span class="m-card-name">' + name + '</span>' +
        // 三个胶囊换成一行灰字：胶囊是表单元素，一屏四条卡叠起来全是圆角块，
        // 看着像设置项而不是"我的作品"。一行文字重量轻，也省 16px 高度。
        '<span class="m-card-meta">' + p.ins + ' 句 · ' + p.assets + ' 素材 · ' + ago(p.mtime) + '</span>' +
      '</span>' +
      '<span class="m-card-go">›</span></button>';
  }

  function render(projects) {
    var list = $("mHomeList");
    if (!list) return;
    allProjects = projects;
    var q = findQ.trim().toLowerCase();
    var shown = q ? projects.filter(function (x) {
      return String(x.name).toLowerCase().indexOf(q) >= 0;
    }) : projects;
    var sub = $("mHomeSub");
    if (sub) sub.textContent = q
      ? ("搜到 " + shown.length + " 个")
      : (projects.length + " 个作品");
    // 三步上手只在书架空着时出现：已经有作品的用户早就知道怎么写第一句，
    // 那三块一直挂着等于天天给人上第一课。要重看走「帮助 → 新手引导」。
    document.body.classList.toggle("m-has-projects", projects.length > 0);
    // 空态类叫 m-home-blank，不叫 m-home-empty：后者是旧空态卡的类名，
    // 同名挂在 body 上会把那张卡的虚线框/居中样式套到整页（P193d 实测踩过）。
    document.body.classList.toggle("m-home-blank", !projects.length);
    // 作品少的时候列表不该把整屏撑满：撑满的结果就是一张小卡孤零零挂在
    // 顶上、底下空出大半屏，「新建 / 导入」被顶到屏幕尽头。少的时候
    // 让列表收到内容高度，「开始新的」自然跟上来。
    document.body.classList.toggle("m-few-projects", projects.length > 0 && projects.length <= 2);
    if (!projects.length) {
      // 空态给样例，不给一句「暂无」（总纲第 5 / 9 节）。
      // 一句话说明 + 一句成品台词，比"点新建"更像"这东西做出来是什么样"。
      list.innerHTML = '<div class="m-empty">' +
        '<span class="m-empty-ic">' + ico("M3.4 2.6h9.2v11H3.4zM5.6 6.2h4.8M5.6 8.8h4.8") + '</span>' +
        '<div class="m-empty-t">还没有作品</div>' +
        '<div class="m-empty-d">建一份就自带一句台词，点开立刻能看到画面。</div>' +
        '<div class="m-empty-say">她推开门，雨顺着伞骨往下淌。</div>' +
        '</div>';
    } else if (!shown.length) {
      // 搜了但没命中：说清"搜的是什么"，别给一片空白
      list.innerHTML = '<div class="m-empty">' +
        '<div class="m-empty-t">没搜到「' + findQ.replace(/</g, "&lt;") + '」</div>' +
        '<div class="m-empty-d">作品名对不上。换个词，或点右边「取消」看全部 ' +
        projects.length + ' 个。</div>' +
        '</div>';
    } else {
      // 按最后修改时间分两段：七天内算「最近在改」，其余归「更早」。
      // 只有两段都非空才分组——一段内容加两个标题，标题比内容还多。
      var now = Date.now() / 1000, recent = [], older = [];
      shown.forEach(function (p) { ((now - p.mtime < 604800) ? recent : older).push(p); });
      if (recent.length && older.length) {
        list.innerHTML =
          '<div class="m-home-grp"><b>最近在改</b><i>' + recent.length + ' 个</i></div>' +
          recent.map(function (p) { return card(p, false); }).join("") +
          '<div class="m-home-grp"><b>更早</b><i>' + older.length + ' 个</i></div>' +
          older.map(function (p) { return card(p, true); }).join("");
      } else {
        list.innerHTML = shown.map(function (p) { return card(p, false); }).join("");
      }
      // 只有一个作品时补一张虚线卡：空白在列表末尾是正常的，但一整片白会让人
      // 以为没加载完。QQ 的分组列表末尾也是这么放「创建」入口，动作就在需要它的位置。
      if (projects.length === 1) {
        list.innerHTML += '<button type="button" class="m-home-card m-card-ghost" id="mHomeGhost">' +
          '<span class="m-card-thumb m-card-thumb-new">＋</span>' +
          '<span class="m-card-body"><span class="m-card-name">再写一个</span>' +
          '<span class="m-card-meta">新作品自带一句台词</span>' +
          '</span></button>';
      }
    }
    // 缩略图单独请求：拿不到就留个空底，不阻塞列表
    list.querySelectorAll(".m-card-thumb[data-folder], .m-hero-cover[data-folder]").forEach(function (th) {
      var f = th.dataset.folder;
      var img = new Image();
      img.onload = function () {
        th.style.backgroundImage = 'url("/api/thumb?folder=' + encodeURIComponent(f) + '")';
        th.classList.add("has");
        // 有真封面才让大卡长起来（空工程铺满一整屏渐变像没加载完）
        var hero = th.closest ? th.closest(".m-home-hero") : null;
        if (hero) hero.classList.add("cover-on");
      };
      img.src = "/api/thumb?folder=" + encodeURIComponent(f);
    });
    list.querySelectorAll(".m-home-card[data-folder], .m-home-hero[data-folder]").forEach(function (b) {
      b.addEventListener("click", function () {
        // 横屏走「先选中、右侧看详情、点继续编辑才进」；
        // 竖屏保持一点就进 —— 一屏只有一个主角，多一步反而累。
        if (splitMode()) { selFolder = b.dataset.folder; paintDetail(projects); return; }
        openWork(b.dataset.folder);
      });
    });
    var gh = $("mHomeGhost");
    if (gh) gh.addEventListener("click", newProject);
    // 右栏详情：默认选中第一个（列表已按最近改排序），选中项离列表了就回落到第一个。
    // 空列表也要画 —— 横屏把「开始新的」整块收掉了，右栏是教程入口唯一所在，
    // 不画的话横屏第一次打开的人找不到新手教程。
    if (projects.length && (!selFolder ||
        !projects.some(function (p) { return p.folder === selFolder; }))) {
      selFolder = projects[0].folder;
    }
    paintDetail(projects);
  }

  // 横屏（平板 / 横过来的手机）：宽度够、高度矮。竖屏那套竖着堆五段在这里会全挤成条。
  function splitMode() {
    return !!(window.matchMedia &&
      window.matchMedia("(min-width:700px) and (max-height:520px)").matches);
  }

  // 右栏详情：缩略图 + 名字 + 三个数 + 唯一主操作。
  // 竖屏由 CSS 收掉，所以两套文案不会同屏出现两次。
  // P194 删掉这里的「新手教程」条与说明：教程已经进底栏第二格，说明那句留在竖屏列表下，
  // 右栏再摆一遍就是同一件事第三个位置。
  function paintDetail(projects) {
    var box = $("mHomeDetail");
    if (!box) return;
    var p = projects.filter(function (x) { return x.folder === selFolder; })[0] || projects[0];
    if (!p) {
      // 空列表：右栏只说"去哪儿开始"。入口都在底栏，不再重复画按钮
      box.innerHTML = '<div class="m-det-empty">还没有作品。<br>' +
        '点底部「教程」照着走一遍，或「新建」直接开写。</div>';
      return;
    }
    var f = p.folder.replace(/"/g, "&quot;");
    // 版面：大一点的方图 + 名字 + 两格数字 + 一整条主按钮，竖着填满右栏。
    // 原来是「铺满整列的 72px 高封面」—— 380px 宽只要 72px 高，5:1 的扁条，
    // 图被拉成一条横带（用户原话「比例不对」）。正方形不裁不拉；
    // 再补两格数字把右栏的高度撑起来，不至于上面一行、下面空 250px。
    box.innerHTML =
      '<div class="m-det-top">' +
        '<span class="m-det-thumb" data-folder="' + f + '"></span>' +
        '<span class="m-det-id">' +
          '<span class="m-det-name">' + p.name.replace(/</g, "&lt;") + '</span>' +
          '<span class="m-det-meta">最近改在 ' + ago(p.mtime) + '</span>' +
        '</span>' +
      '</div>' +
      '<div class="m-det-kv">' +
        '<div><b>' + p.ins + '</b><span>句台词</span></div>' +
        '<div><b>' + p.assets + '</b><span>个素材</span></div>' +
      '</div>' +
      '<button type="button" class="m-det-go">继续编辑</button>';
    // 封面单独请求：拿不到就留空底，不阻塞
    var hero = box.querySelector(".m-det-thumb");
    var img = new Image();
    img.onload = function () {
      hero.style.backgroundImage = 'url("/api/thumb?folder=' + encodeURIComponent(p.folder) + '")';
      hero.classList.add("has");
    };
    img.src = "/api/thumb?folder=" + encodeURIComponent(p.folder);
    box.querySelector(".m-det-go").addEventListener("click", function () { openWork(p.folder); });
    // 选中态：左列表里同目录的那张卡描一圈，人一眼知道右边这块说的是谁
    var list = $("mHomeList");
    if (list) list.querySelectorAll(".m-home-card").forEach(function (c) {
      c.classList.toggle("on", c.dataset.folder === p.folder);
    });
  }

  function newProject() {
    // 直接点工具栏的「新建游戏」，别绕下拉菜单绕一圈：
    // 菜单项的 id 对不上时，菜单会留在屏幕上、新建弹窗又没打开，用户就看到一个悬着的菜单
    enterEditor();
    setTimeout(function () { var nb = $("btnNew"); if (nb) nb.click(); }, 120);
  }

  // 导入：手机上没有「打开文件对话框」以外的路子，所以走 <input type=file>。
  // 只认离线作品库那份 JSON（和导出的同一格式），别的一律明确拒绝，不猜。
  function importProject() {
    var inp = document.createElement("input");
    inp.type = "file";
    inp.accept = ".json,application/json";
    inp.style.display = "none";
    document.body.appendChild(inp);
    inp.addEventListener("change", function () {
      var f = inp.files && inp.files[0];
      if (!f) { inp.remove(); return; }
      var rd = new FileReader();
      rd.onload = function () {
        var txt = String(rd.result || "");
        if (!window.__myonlImportLib) { toast("这台设备没有离线内核，导入不了"); inp.remove(); return; }
        // 必须等它：素材是按 IndexedDB 一个个铺回去的，铺到一半就 reload 等于恢复了一半
        Promise.resolve(window.__myonlImportLib(txt)).then(function (ok) {
          inp.remove();
          if (ok) setTimeout(function () { location.reload(); }, 600);
        }).catch(function (e) {
          inp.remove();
          toast("导入失败：" + (e.message || e));
        });
      };
      rd.onerror = function () { toast("文件读不出来"); inp.remove(); };
      rd.readAsText(f);
    });
    inp.click();
  }

  function toast(msg) {
    var t = document.createElement("div");
    t.className = "m-home-toast";
    t.textContent = msg;
    document.body.appendChild(t);
    setTimeout(function () { t.remove(); }, 2400);
  }

  function openProject(folder, btn, tab) {
    if (btn) { btn.disabled = true; btn.classList.add("busy"); }
    // 切作品之前，先把"这一屏正在编的正文"落掉。不留这一步的话，唯一能写草稿的时机
    // 就只剩 pagehide —— 那时 lib.current 已经被改成新作品，旧正文会被记成新作品的草稿。
    try { if (window.MYONLDraft && MYONLDraft.flush) MYONLDraft.flush(2); } catch (e) {}
    // P193：进作品前把作品名记下来。进去之后是整页 reload，编辑器顶栏只剩一个文件名
    // （script.gal），人分不清在改哪个作品。名字走 sessionStorage 传过去，reload 不掉。
    try {
      sessionStorage.setItem("myonl:projName", String(folder).split(/[\\/]/).pop());
      // P197：作品页上点「播放 / 素材 / 导出」进编辑器后要自动落到那一格
      if (tab) sessionStorage.setItem("myonl:enterTab", tab);
      else sessionStorage.removeItem("myonl:enterTab");
    } catch (e) {}
    fetch("/api/project", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ folder: folder })
    }).then(function (r) { return r.json(); }).then(function (res) {
      if (!res.ok) throw new Error(res.message || "打不开这个工程");
      enterEditor();
      location.reload();     // 工程根变了：文件树/素材/预览全部要重来，reload 最省事也最可靠
    }).catch(function (e) {
      if (btn) { btn.disabled = false; btn.classList.remove("busy"); }
      var t = document.createElement("div");
      t.className = "m-home-toast";
      t.textContent = e.message || "打不开这个工程";
      layer.appendChild(t);
      setTimeout(function () { t.remove(); }, 2200);
    });
  }

  // ---- 作品页（P197）：点作品先进这一屏，不直接进编辑器 ----
  // 为什么加这一层：点卡就进编辑器，等于第一次用的人打开就是行号、等宽字、@ 指令。
  // 这一屏先给封面和「播放」，人能立刻知道"这是个能玩的东西"，再决定改不改。
  var workEl = null;
  function openWork(folder) {
    var p = null;
    for (var i = 0; i < allProjects.length; i++) {
      if (allProjects[i].folder === folder) p = allProjects[i];
    }
    if (!p) return;
    if (workEl) workEl.remove();
    workEl = document.createElement("div");
    workEl.className = "m-work";
    // P197b 作品工作台：封面 + 「写 / 玩」两个入口 + 创作资源清单。
    // 不走纯编辑器那一套：这一屏要先让人看见"这是个能玩的作品"，
    // 再由他自己点进去改。资源清单里的每一项都是真入口，点了就跳对应页。
    workEl.innerHTML =
      '<div class="m-work-head">' +
        '<button type="button" class="m-work-back" id="mWorkBack">‹ 作品</button>' +
        '<span class="m-work-dot">' + ago(p.mtime) + '</span>' +
      '</div>' +
      '<div class="m-work-body">' +
        '<div class="m-work-hero">' +
          '<div class="m-work-cover"><img alt=""></div>' +
          '<div class="m-work-title">' + String(p.name).replace(/</g, "&lt;") + '</div>' +
          '<div class="m-work-meta">' + (p.ins || 0) + ' 句台词 · ' + ago(p.mtime) + '</div>' +
          '<button type="button" class="m-work-play" id="mWorkPlay">▶ 播放看一遍</button>' +
          '<button type="button" class="m-work-write" id="mWorkWrite">✎ 继续创作</button>' +
        '</div>' +
        '<div class="m-work-side">' +
          '<div class="m-work-sec"><span>创作资源</span><i></i></div>' +
          '<div class="m-work-rows">' +
            '<button type="button" data-tab="script"><b>剧本</b><span>' + (p.ins || 0) + ' 句台词</span><em>›</em></button>' +
            '<button type="button" data-tab="assets"><b>素材</b><span>立绘 背景 音频 语音</span><em>›</em></button>' +
            '<button type="button" data-tab="look"><b>外观</b><span>画面比例 字号 主题</span><em>›</em></button>' +
            '<button type="button" data-tab="export"><b>导出</b><span>出成能发出去的包</span><em>›</em></button>' +
            '<button type="button" class="m-work-hist" id="mWorkHist"><b>历史</b>' +
              '<span id="mWorkHistNum">每次保存都自动留一版</span><em>›</em></button>' +
          '</div>' +
        '</div>' +
      '</div>';
    document.body.appendChild(workEl);
    // P198：这一屏本来就是"决定要不要改"的地方，所以未保存草稿在这里就摆出来，
    // 不等到进了编辑器再弹。不做模态 —— 模态会把封面和「播放」盖住，
    // 而人可能只是想先看一遍，看完再决定留不留那版草稿。
    var dft = (window.MYONLDraft && window.MYONLDraft.peek(p.name)) || null;
    if (dft) {
      var dt = new Date(dft.at);
      var hh = (dt.getHours() < 10 ? "0" : "") + dt.getHours();
      var mm = (dt.getMinutes() < 10 ? "0" : "") + dt.getMinutes();
      var df = window.MYONLDraft.diffText(dft);
      var tip = document.createElement("div");
      tip.className = "m-draft-tip";
      tip.style.cssText = "margin:0 0 12px;padding:10px 12px;border-radius:12px;" +
        "background:rgba(224,196,106,.10);border:1px solid rgba(224,196,106,.34);";
      tip.innerHTML =
        '<div style="font-size:13px;color:#e0c46a;line-height:1.5">' +
          '上次没保存的内容会自动接上 · ' + hh + ':' + mm + ' · ' +
          (df.chars >= 0 ? "多 " + df.chars : "少 " + (-df.chars)) + ' 字' +
          (dft.stale ? '<br><span style="color:#e08a6a">草稿基于的版本已经变过（回退或导入过）</span>' : '') +
        '</div>' +
        '<div style="display:flex;gap:8px;margin-top:8px">' +
          '<button type="button" id="mDraftGo" style="flex:1;height:34px;border:0;border-radius:9px;' +
            'background:#4f8cff;color:#fff;font-size:13px">继续创作（接上次内容）</button>' +
          '<button type="button" id="mDraftNo" style="flex:0 0 76px;height:34px;' +
            'border:1px solid rgba(160,180,210,.4);border-radius:9px;background:transparent;' +
            'color:#9fb3d1;font-size:13px">丢弃</button>' +
        '</div>';
      var hero = workEl.querySelector(".m-work-hero");
      if (hero && hero.parentNode) hero.parentNode.insertBefore(tip, hero.nextSibling);
      else workEl.insertBefore(tip, workEl.firstChild);
      // P198.1：这里不再"问要不要恢复" —— 进去会自动接上，所以按钮就是"继续创作"。
      // 留「丢弃」是因为"我不要那版"必须有个地方按，不然自动接上就成了强制。
      tip.querySelector("#mDraftGo").addEventListener("click", function () {
        window.MYONLDraft.markShown(dft);
        openProject(folder, null, "script");
      });
      tip.querySelector("#mDraftNo").addEventListener("click", function () {
        window.MYONLDraft.drop(p.name);
        tip.remove();
      });
    }
    // P197c：这一屏原来把底栏盖住了 —— 首页那条导航在 .m-home 层里，层被 .m-work 压下去，
    // 进作品页底部就空了，看着像"tab 被砍了"。这里带一条同样的导航下来，
    // 点击转给首页那条真导航（新建/导入/教程/设置各自只有一份逻辑）。
    var nav = document.getElementById("mHomeNav");
    if (nav) {
      var clone = nav.cloneNode(true);
      clone.removeAttribute("id");
      clone.querySelectorAll("[id]").forEach(function (n) { n.removeAttribute("id"); });
      clone.classList.add("m-work-nav");
      clone.querySelectorAll(".m-nav-item").forEach(function (b) { b.classList.remove("on"); });
      var first = clone.querySelector('.m-nav-item[data-nav="home"]');
      if (first) first.classList.add("on");
      workEl.appendChild(clone);
      clone.addEventListener("click", function (e) {
        var it = e.target.closest ? e.target.closest(".m-nav-item") : null;
        if (!it) return;
        if (it.dataset.nav === "home") {
          if (workEl) { workEl.remove(); workEl = null; }
          return;
        }
        var orig = nav.querySelector('.m-nav-item[data-nav="' + it.dataset.nav + '"]');
        if (orig) orig.click();
      });
    }
    var img = workEl.querySelector(".m-work-cover img");
    var cv = workEl.querySelector(".m-work-cover");
    // 先把渐变 + 首字垫上，图真加载出来再换成图。反过来做的话没图的工程
    // 会先闪一块死灰（离线设备 / 新作品都是这个情形）。
    cv.classList.add("empty");
    cv.dataset.ch = String(p.name || "作").trim().charAt(0);
    img.addEventListener("load", function () { cv.classList.remove("empty"); cv.classList.add("on"); });
    img.src = "/api/thumb?folder=" + encodeURIComponent(folder);
    workEl.querySelector("#mWorkBack").addEventListener("click", function () {
      if (workEl) { workEl.remove(); workEl = null; }
    });
    workEl.querySelector("#mWorkPlay").addEventListener("click", function () {
      openProject(folder, null, "preview");
    });
    workEl.querySelector("#mWorkWrite").addEventListener("click", function () {
      openProject(folder, null, "script");
    });
    workEl.querySelectorAll(".m-work-rows button").forEach(function (b) {
      if (!b.dataset.tab) return;   // 「历史」那行没有 tab，单独绑
      b.addEventListener("click", function () { openProject(folder, null, b.dataset.tab); });
    });
    // 历史版本：P197d 把入口从「导出 → 第三行」搬到这里 ——
    // 之前它埋在导出页里，没有人点得到，等于没有。
    var hist = workEl.querySelector("#mWorkHist");
    if (hist) {
      hist.addEventListener("click", function () {
        if (window.MYONLSnapshotsUI) window.MYONLSnapshotsUI.open(folder);
        else alert("这个设备上没有历史版本模块");
      });
      if (window.MYONLSnapshots) {
        window.MYONLSnapshots.list(folder).then(function (rows) {
          var n = workEl && workEl.querySelector("#mWorkHistNum");
          if (!n) return;
          n.textContent = rows.length
            ? (rows.length + " 版 · 最近 " + ago(rows[0].at))
            : "每次保存都自动留一版";
        }).catch(function () {});
      }
    }
  }

  function enterEditor() {
    try { sessionStorage.setItem(EDIT_KEY, "1"); } catch (e) {}
    hideEditor(false);
    layer.style.display = "none";
    document.body.classList.remove("m-home-open");   // 回到作品内部，底部五个 tab 归位
  }

  // ---- 设置：主题 / 游戏方向 / 返回作品列表。做成一页，别学桌面端散在五个地方 ----
  var sheet = null;
  var orient = "any";
  // 预览框比例：设置里切，启动时按上次的选择恢复。
  // 16:9 = 56.25% 高，20:9 全面屏 = 45%，4:3 老手机 = 75%。
  var RATIO_PAD = { "16:9": "56.25%", "20:9": "45%", "4:3": "75%" };
  try {
    var _rp = RATIO_PAD[localStorage.getItem("myonl_preview_ratio")];
    if (_rp) document.documentElement.style.setProperty("--sf-pad", _rp);
  } catch (e) {}
  // 主题色：启动时按上次选的恢复，否则每次开都跳回蓝
  try {
    var _ac = localStorage.getItem("myonl_accent");
    if (_ac) {
      document.documentElement.style.setProperty("--blue", _ac);
      document.documentElement.style.setProperty("--lavender", _ac);
    }
  } catch (e) {}
  function openSettings() {
    if (sheet) { sheet.remove(); sheet = null; return; }
    var theme = "dark";
    try { theme = localStorage.getItem("gal_editor_theme") === "light" ? "light" : "dark"; } catch (e) {}
    sheet = document.createElement("div");
    // 必须带 on：.m-sheet 默认是 translateY(100%) 藏在视口下方的抽屉，只有 .on 才归位。
    // 上一版少了它，于是「设置」点开时抽屉其实一直在屏幕外面 —— 看着就像没反应。
    sheet.className = "m-sheet m-set-sheet on";
    sheet.innerHTML =
      '<div class="m-sheet-mask"></div>' +
      '<div class="m-sheet-body">' +
        '<div class="m-sheet-grab"></div>' +
        '<div class="m-sheet-title">设置' +
          '<button type="button" class="m-set-done" id="mSetDone">完成</button></div>' +
        '<div class="m-set-row"><span>界面</span>' +
          '<span class="m-seg" id="mSetTheme">' +
            '<button type="button" data-v="dark" class="' + (theme === "dark" ? "on" : "") + '">深色</button>' +
            '<button type="button" data-v="light" class="' + (theme === "light" ? "on" : "") + '">浅色</button>' +
          '</span></div>' +
        '<div class="m-set-row"><span>游戏画面</span>' +
          '<span class="m-seg" id="mSetOrient">' +
            '<button type="button" data-v="any" class="' + (orient === "any" ? "on" : "") + '">跟随</button>' +
            '<button type="button" data-v="portrait" class="' + (orient === "portrait" ? "on" : "") + '">竖屏</button>' +
            '<button type="button" data-v="landscape" class="' + (orient === "landscape" ? "on" : "") + '">横屏</button>' +
          '</span></div>' +
        '<div class="m-set-note">拿不准就选「跟随」—— 横过来竖着都能玩，导出时不用再选。</div>' +
        '<div class="m-set-row"><span>预览比例</span>' +
          '<span class="m-seg" id="mSetRatio">' +
            '<button type="button" data-v="16:9" class="on">16:9</button>' +
            '<button type="button" data-v="20:9">20:9</button>' +
            '<button type="button" data-v="4:3">4:3</button>' +
          '</span></div>' +
        '<div class="m-set-note">只改上面那块预览框的形状，不动导出结果。做的时候拿它对照自己手机的屏幕。</div>' +
        '<div class="m-set-row"><span>主题色</span>' +
          '<span class="m-swatches" id="mSetAccent">' +
            '<button type="button" data-c="#4f8cff" style="background:#4f8cff"></button>' +
            '<button type="button" data-c="#8b7cf6" style="background:#8b7cf6"></button>' +
            '<button type="button" data-c="#22c1c3" style="background:#22c1c3"></button>' +
            '<button type="button" data-c="#3ecf8e" style="background:#3ecf8e"></button>' +
          '</span></div>' +
        '<div class="m-set-note">选中态、按钮、作品卡上的蓝都跟着换。深色浅色都生效。</div>' +
        '<div class="m-set-sec">软件详情</div>' +
        '<div class="m-set-row"><span>存储方式</span><span class="m-set-val">本地，不上云</span></div>' +
        '<div class="m-set-row"><span>数据位置</span><span class="m-set-val">这台设备</span></div>' +
        '<div class="m-set-note">存储方式：本地存储，数据留在这台设备上，不联网也不上传。<br>' +
        '需要转移或分享？→ 进作品 → 底部「导出」→ 选择导出格式。</div>' +
      '</div>';
    // 抽屉挂 <html> 而不是 <body>：body 上挂了编辑器各种档位类，fixed 定位在里面被算成流的位置
  // （实测顶边跑到 1007，正好是内容底部）。挂 html 之后 fixed 的包含块就是视口本身。
  document.documentElement.appendChild(sheet);

    sheet.querySelector(".m-sheet-mask").addEventListener("click", function () {
      sheet.remove(); sheet = null;
    });

    var seg = sheet.querySelector("#mSetTheme");
    seg.addEventListener("click", function (e) {
      var b = e.target.closest ? e.target.closest("button[data-v]") : null;
      if (!b) return;
      var v = b.dataset.v;
      try { localStorage.setItem("gal_editor_theme", v); } catch (err) {}
      document.documentElement.setAttribute("data-theme", v);
      seg.querySelectorAll("button").forEach(function (x) { x.classList.toggle("on", x === b); });
    });

    // 「返回」那一行删了：抽屉点遮罩本来就能关，多一行「作品列表 / 返回」反而像在问"要回哪去"。
    // 现在只有一个入口——标题栏的「完成」，点它关抽屉，回哪儿去不用想。
    var dn = sheet.querySelector("#mSetDone");
    if (dn) dn.addEventListener("click", function () {
      if (sheet) { sheet.remove(); sheet = null; }
    });

    var ob = sheet.querySelector("#mSetOrient");
    if (ob) ob.addEventListener("click", function (e) {
      var b = e.target.closest ? e.target.closest("button[data-v]") : null;
      if (!b) return;
      var v = b.dataset.v;
      fetch("/api/orientation", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ orientation: v })
      }).then(function (r) { return r.json(); }).then(function (res) {
        if (!res.ok) throw new Error(res.message || "存不下来");
        orient = res.orientation;
        ob.querySelectorAll("button").forEach(function (x) {
          x.classList.toggle("on", x.dataset.v === orient);
        });
      }).catch(function (err) {
        var t = document.createElement("div");
        t.className = "m-home-toast";
        t.textContent = err.message || "存不下来";
        document.body.appendChild(t);
        setTimeout(function () { t.remove(); }, 2000);
      });
    });

    // 预览比例：只改上面那块预览框的形状，不改导出结果。
    var rg = sheet.querySelector("#mSetRatio");
    if (rg) {
      var curRatio = "16:9";
      try { curRatio = localStorage.getItem("myonl_preview_ratio") || "16:9"; } catch (e) {}
      if (!RATIO_PAD[curRatio]) curRatio = "16:9";
      rg.querySelectorAll("button").forEach(function (x) {
        x.classList.toggle("on", x.dataset.v === curRatio);
      });
      rg.addEventListener("click", function (e) {
        var b = e.target.closest ? e.target.closest("button[data-v]") : null;
        if (!b) return;
        var v = b.dataset.v;
        try { localStorage.setItem("myonl_preview_ratio", v); } catch (err) {}
        document.documentElement.style.setProperty("--sf-pad", RATIO_PAD[v] || "56.25%");
        rg.querySelectorAll("button").forEach(function (x) { x.classList.toggle("on", x === b); });
      });
    }

    // 主题色：只换强调色（选中态、按钮、作品卡描边），不动背景与文字。
    var ac = sheet.querySelector("#mSetAccent");
    if (ac) {
      var curAccent = "#4f8cff";
      try { curAccent = localStorage.getItem("myonl_accent") || "#4f8cff"; } catch (e) {}
      ac.querySelectorAll("button").forEach(function (x) {
        x.classList.toggle("on", x.dataset.c === curAccent);
      });
      ac.addEventListener("click", function (e) {
        var b = e.target.closest ? e.target.closest("button[data-c]") : null;
        if (!b) return;
        var c = b.dataset.c;
        try { localStorage.setItem("myonl_accent", c); } catch (err) {}
        document.documentElement.style.setProperty("--blue", c);
        // 悬停色用同色相提亮，不引入第二个色
        document.documentElement.style.setProperty("--lavender", c);
        ac.querySelectorAll("button").forEach(function (x) { x.classList.toggle("on", x === b); });
      });
    }
  }

  // ---- 教程：底栏第二格。语法速查 + 建一份可删的练习 ----
  // 不做成纯只读文档：看完立刻能点「建一份练习」，得到一份真能改、能导出、
  // 也能随手删掉的短作品。教程不塞进 games/ 的示例堆里靠代码硬识别，
  // 玩家想自己写就自己建，教程只是起点。
  var tutSheet = null;
  // 教程里一条：图标 + 标题 + 一句人话 + 一行能照抄的写法。
  // 六行纯文字读起来像说明书；一条一块卡，手指知道每块在讲什么。
  function tutItem(ic, title, desc, code) {
    return '<div class="m-tut-item">' +
      '<span class="m-tut-ic2">' + ico(ic) + '</span>' +
      '<span class="m-tut-b"><b>' + title + '</b><span>' + desc + '</span>' +
      (code ? '<code>' + code.replace(/</g, "&lt;") + '</code>' : '') +
      '</span></div>';
  }

  function openTutorialSheet() {
    if (tutSheet) { tutSheet.remove(); tutSheet = null; return; }
    tutSheet = document.createElement("div");
    tutSheet.className = "m-sheet m-set-sheet on";
    tutSheet.innerHTML =
      '<div class="m-sheet-mask"></div>' +
      '<div class="m-sheet-body">' +
        '<div class="m-sheet-grab"></div>' +
        '<div class="m-sheet-title">教程' +
          '<button type="button" class="m-set-done" id="mTutDone">完成</button></div>' +
        // 主操作放在最上面：点开教程的人下一步就是"动手"，不该先滚一屏说明才看到按钮。
        // 练习是普通作品，建在自己列表里，能改也能删。
        '<button type="button" class="m-tut-start" id="mTutStart">' +
          '建一份练习（可删）' +
          '<span>21 句话的短作品，改两句就懂</span></button>' +
        '<div class="m-tut-doc">' +
          tutItem("M3.6 3.4h8.8M3.6 6.4h8.8M3.6 9.4h5.2", "一行一句话",
            "剧本里一行就是游戏里的一屏，直接写。", "") +
          tutItem("M2.6 3.2h10.8v9.6H2.6zM4.8 1.6v2M11.2 1.6v2", "角色台词",
            "方括号里写说话人，不用先去角色库建人。", "@[小满] 你终于来了。") +
          tutItem("M3.2 2.6h9.6v10.4H3.2z", "旁白",
            "括号里写「旁白」，就是画外音。", "@[旁白] 雨还在下。") +
          tutItem("M3.4 8.2h3.6M9 8.2h3.6M3.4 5.4h9.2M8 2.2v11.6", "分支",
            "@choice 下面每行一个选项，箭头后面是跳到哪一页。", "> 追上去 -> 第一章") +
          tutItem("M2.6 3.4h10.8v9.2H2.6zM5.6 3.4v9.2", "画面",
            "底部「素材」放图，点一下插成背景；音乐、视频同一个入口。", "") +
          tutItem("M8 2.2v7.4M4.9 6.6l3.1 3.1 3.1-3.1M2.6 12.6h10.8", "导出",
            "成品是一个 html，发给谁都能双击玩；也能打成安卓安装包。", "") +
        '</div>' +
        '<div class="m-set-note">练习就是一份普通作品，建在你自己的列表里；不想要就删掉，不影响别的。</div>' +
      '</div>';
    document.documentElement.appendChild(tutSheet);
    tutSheet.querySelector(".m-sheet-mask").addEventListener("click", function () {
      tutSheet.remove(); tutSheet = null;
    });
    tutSheet.querySelector("#mTutDone").addEventListener("click", function () {
      tutSheet.remove(); tutSheet = null;
    });
    tutSheet.querySelector("#mTutStart").addEventListener("click", function () {
      tutSheet.remove(); tutSheet = null;
      openTutorial();
    });
  }

  fetch("/api/home").then(function (r) { return r.json(); }).then(function (res) {
    if (!res.ok) throw new Error("读不到作品列表");
    orient = res.orientation || "any";
    render(res.projects || []);
  }).catch(function (e) {
    var list = $("mHomeList");
    if (list) list.innerHTML = '<div class="m-home-err">' + (e.message || "读不到作品列表") + '</div>' +
      '<button type="button" class="m-home-card" id="mHomeSkip">还是直接进编辑器</button>';
    var sk = $("mHomeSkip");
    if (sk) sk.addEventListener("click", enterEditor);
  });

  // 搜作品：点放大镜展开输入框，打字就把卡片筛掉；「取消」收起并恢复全部。
  // 真过滤，不是摆个假框 —— 作品一多，这是第一个会用到的功能。
  var foldbox = $("mHomeFindBox"), fin = $("mHomeFindInput");
  function setFind(on) {
    if (!foldbox) return;
    foldbox.hidden = !on;
    if (on && fin) fin.focus();
    if (!on) { findQ = ""; if (fin) fin.value = ""; render(allProjects); }
  }
  var findBtn = $("mHomeFind");
  if (findBtn) findBtn.addEventListener("click", function () { setFind(foldbox.hidden); });
  if (fin) fin.addEventListener("input", function () { findQ = fin.value; render(allProjects); });
  var findClr = $("mHomeFindClear");
  if (findClr) findClr.addEventListener("click", function () { setFind(false); });
  // 底部导航复用上面三个真动作，不另写一套逻辑，省得两处行为跑偏
  var navEl = $("mHomeNav");
  if (navEl) {
    navEl.addEventListener("click", function (e) {
      var item = e.target.closest(".m-nav-item");
      if (!item) return;
      var kind = item.getAttribute("data-nav");
      if (kind === "new") newProject();
      else if (kind === "import") importProject();
      else if (kind === "set") openSettings();
      else if (kind === "tut") openTutorialSheet();
      else layer.scrollTo({ top: 0, behavior: "smooth" });
    });
  }
  // 试玩不能整页跳走。
  // 原来的写法是 location.href = "./game.html"：编辑器被导航覆盖掉，游戏里又没有回程，
  // 安卓上只能把应用杀掉重开（用户原话「必须得退出软件」）。
  // 改成全屏内嵌层 + 顶部一条退出栏：编辑器状态原地保留，退出来还是刚才那页。
  // 游戏内部也能退（标题页会 postMessage 过来），两条路都通。
  function closeDemo() {
    var w = $("mDemoLayer");
    if (!w) return;
    var f = $("mDemoFrame");
    // 先把 iframe 换空白再拆：不这么做，里面的 BGM 会继续放，退出去还在响
    if (f) { try { f.src = "about:blank"; } catch (e) { } }
    if (w.parentNode) w.parentNode.removeChild(w);
  }

  // 「试玩示例」那条路整条删了（openDemo / iframe 内嵌层 / 退出试玩的 postMessage）：
  // 它放的是 game.html 里一份和编辑器无关的 demo，点开只看到"别人的游戏"，
  // 新手得不到任何关于"我这东西能做成什么"的信息。新手要看的是能改的东西。

  // 「新手教程」= 建一份真作品，不是播一个内置 demo。
  // 已经在库里就直开（用户可能自己改过它，别覆盖）；没有才建一次。
  var TUT_NAME = "新手教程";
  var TUT_TEXT = [
    "# 这是「新手教程」：一份真能玩、真能改的作品",
    "# 以 # 开头的是注释，不上屏；以 @ 开头的才是游戏里的一句话",
    "",
    "@label start",
    "@[旁白] 这一句是旁白。想改就直接改。",
    "@[小满] 这一句是角色台词，名字在方括号里。",
    "@[小满] 写方括号就不用在角色库里先建人。",
    "@[旁白] 一屏只说一句话，读起来才像游戏。",
    "",
    "@choice:",
    "> 继续看写法 -> 怎么写",
    "> 直接看素材 -> 素材",
    "",
    "@label 怎么写",
    "@[旁白] 一行一句话，想加就加一行。",
    "@[旁白] 想让角色说话，名字放进方括号。",
    "@[旁白] 底部「素材」放图和音乐，点一下就插成背景。",
    "",
    "@choice:",
    "> 下一步 -> 素材",
    "> 回到开头 -> start",
    "",
    "@label 素材",
    "@[旁白] 图片、音乐、视频都放这里。",
    "@[旁白] 选中一个素材，会弹出「拿它做什么」。",
    "@[旁白] 背景、立绘、CG 都在那一步定。",
    "",
    "@choice:",
    "> 下一步 -> 导出",
    "> 回到开头 -> start",
    "",
    "@label 导出",
    "@[旁白] 写完去底部「导出」。",
    "@[旁白] 第一个按钮出一个 html，发给谁都能双击玩。",
    "@[旁白] 也可以出安卓安装包，装到手机上像 App。",
    "",
    "@choice:",
    "> 从头再看一遍 -> start",
    "> 开始写我自己的 -> start",
    ""
  ].join("\n");

  function openTutorial() {
    var lib = {};
    try { lib = JSON.parse(localStorage.getItem("myonl:off:lib:v1") || "{}"); } catch (e) { lib = {}; }
    var has = (lib.projects || []).some(function (p) { return p.name === TUT_NAME; });
    if (has) { openProject(TUT_NAME); return; }
    fetch("/api/new", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: TUT_NAME, text: TUT_TEXT })
    }).then(function (r) { return r.json(); }).then(function (res) {
      if (!res.ok) throw new Error(res.message || "建不了教程");
      openProject(TUT_NAME);
    }).catch(function (e) { toast(e.message || "建不了教程"); });
  }

  // 教程入口在底栏（id=mHomeTut），点击走 nav 委托 → openTutorialSheet，
  // 这里不再单独绑一次，否则同一下点击会既开抽屉又直接建工程。
})();
