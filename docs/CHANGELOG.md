# CHANGELOG

> 只记 release 级变化，一句话 + 证据链接。单项细节见 git 历史（原 archive/ 已删除）。

## 2026-11-16（P72 + P73：手机端装得上、演得全）

**两件事**：① 导出的网页包/单文件现在带 PWA —— manifest + 192/512/maskable 图标 + iOS 全屏 meta + 启动遮罩，「添加到主屏幕」就是没有地址栏的 App。② 桌面端有、手机端一直不支持的 6 条演出指令全补上：`@fg` 前景贴图（cover 铺满）、`@anim` 立绘补间（x/y 1280 基准 + scale 底部中心锚 + alpha）、`@video` 帧序列背景（帧图一起打进包、fps 循环、懒加载）、`@voice` 独立语音通道（换句掐上一条）、`@chapter` 黑场章节卡（期间挡点击）、`@transition` dissolve 淡入 / wipe·slide 按方向 clip 推进。

**顺带修**：`@fg 无` 从来没真清过前景 —— parser 归一成 `name="无"`，`runtime.py` 只认 `reset` 字段，于是桌面端一直"设了一张叫『无』的图"再静默跳过；四处（runtime / webpack 收集 / 前端 VM / demo 预检）统一认 `无`。`webpack` 的 unsupported 清单里还塞着 parser 根本不产出的 `play`/`stop`/`shake`，删掉后清单如实为空。`_collect_image_names` 之前不收 `@fg` 的图。

**编辑器的指令入口也跟着补齐**（不然指令做出来了、作者在手机上打不出来）：手机键盘快捷条从 5 个键加到 15 个（`@bg` / `@show` / `@chapter` / `@voice` / `@choice:` / `@if` / `@set` / `@label` / `@transition` / `@fg` / `→` / 缩进 / 换行 / 撤销），输入 `@` 后的补全表补 `fg / anim / camera / transition / plug / wait / nvl`，`@fg` 和 `@cg` 打完空格也会列图片名，卡片总览能认出 `fg / anim / chapter / transition / camera`。顺带：手机上没有 Home/End 键，点 `@bg` 若光标停在一句台词中间会把整行撕开 —— 指令键改为「这一行已有内容就先换一行再插」。

**踩坑留档**：PIL `Image.new("RGBA") + Draw(img,"RGBA")` 是直接替换像素、不混 alpha，半透明会变纯白实心 —— 必须 `Image.new("RGB", 底色) + Draw(...,"RGBA")`。`next()` 遇到 `chapter` 必须 break，否则台词抢在章节卡前面出来。`@voice` 只能紧跟在台词之后，播放顺序是 say → voice。

**证据**：`pwa-boot.png` / `pwa-play.png`（遮罩淡出、`#boot` 已移除、三处 PWA 头全 True、无 console error）、`p73-anim-early.png`（立绘偏左滑入）、`p73-fg.png`（斜雨铺满且不盖对话框）、`p73-video-a/b.png`（两帧换色）、`p73b-01.png`（章节卡）、`p73b-06.png`（wipe 半屏分界）、`p74land-choice.png` + `p74choice-portrait.png`（横/竖屏选项页，按钮上方有「在答什么」那一行）；单文件 774823 B；`pytest -m "not slow"` 1091 passed + 1 skipped。详见 `docs/变更说明-P72-P73-PWA与手机端全指令.md`。

## 2026-11-16（P71：UI 设计区有整屏缩略图了——调参数能看见手机上变成什么样）

**症状**：P70 让选项七项参数真能调了，但调的时候只有右边的数字在变，没有任何参照物。要知道 620 和 800 在手机上差多少，得先导出、再跑、再看一眼。

**修法**：UI 设计区加一块 300×649 的整屏缩略图，按当前作品背景 + 当前参数 + 当前分组实时画（背景 / 暗角 / 立绘占位 / 对话框 + 名字牌 + 假台词 / 两个选项按钮 / 快捷栏 / 右上圆钮），当前 tab 那一组描蓝框，参数变化走 170ms 补间。手机竖屏吸顶 158×342、横屏右上浮窗 88×190、桌面 300×649；点一下铺满整屏看细节。

**顺带修**：`_get_asset` 取单个素材用的是 `app.data_root`（仓库根），而列表是按作品目录扫的 → 列表有、点开 404。新增 `_resolve_asset()` 先作品根再 `data_root`，两处调用全换。

**踩坑留档**：`.uid-stage` 这名字已被 P58 画布容器占用（`display:none`），第一版整屏预览撞名被隐藏；CSS 补丁按 `\n}` 找块尾切错，把整个文件复制了一份（已截断，括号数校验 1201/1201）。

**证据**：`stage-p-default.png` / `stage-p-tuned.png`（800 / gap70 / #33224a / radius30 的对比）、`stage-l-tuned.png`、`stage-p-big.png`；`pytest -m "not slow"` 1085 passed + 1 skipped。详见 `docs/变更说明-P71-整屏参照预览.md`。

## 2026-11-16（P70：选项按钮真正可调——三条断链一起修）

**症状**：编辑器「外观 → 选项按钮」怎么调，手机端播放器都不变。查下来是三处同时断：① `_ui_design_get/set/preview` 用 `app.project_root`（`--script` 启动时是仓库根），读的是空配置、写的也是根目录；② 播放器 `drawChoices` 完全不读 `ui.choices`，宽高间距走布局、圆角写死 14；③ `webpack.CONFIG_KEYS` 没有 `ui` / `dialogue`，单文件导出把这两段整个裁掉。

**修法**：三处改用 `_current_project_root()`；播放器新增 `choiceGeom()` 接上 7 个键（width / row_height / gap / dialog_gap / radius / bg / fg，默认值等于原行为）；`CONFIG_KEYS` 补 `ui`、`dialogue`。语义按 pygame 端对齐：`dialog_gap` = 选项组离对话区多远，`gap` = 选项之间的缝。

**编辑器**：「选项按钮」组 4 滑块 → 7 控件（+ 底色 / 文字色，空=跟随主题，后端只收 `#rrggbb`），并加一块 300×132 实时预览（按手机竖屏 1080 宽等比缩放，改参数即重画）。控件全 JS 注入，`index.html` 仍 599 行。

**证据**：`choice-play-tuned-p.png`（800/80/30/gap60/紫底绿字，全部来自编辑器参数）→ 恢复默认后 `play-p-choice.png`；`pytest -m "not slow"` 1084 passed + 1 skipped。详见 `docs/变更说明-P70-选项可调.md`。

## 2026-11-16（P68：手机编辑器去 IDE 化 + 播放器换皮）

**编辑器**：P65 只是把桌面三列"藏"起来，露出来的仍是 VS Code 的壳 —— 这一期换掉。文件标签条 `display:none`（手机只开一个文件）；状态栏从八段挤一行收成 `已保存 / 第 N 行`，窄屏文案改成 `通过 · N 条`；顶栏四个控件统一 34×34 圆角 10 浅底胶囊并左对齐；正文 15px / 行高 28px（绝对值）/ 行号槽 34px。左侧那条 13px 灰竖带定位到 `.file-pane`（`left:46px + translateX(-110%)` 右边缘停在 13px），改 `left:0 + translateX(-102%)` 后消失。

**踩坑**：编辑器不是 CodeMirror，是 `textarea#source` + `.hl-layer` 叠层，按 `.cm-*` 写样式全是 no-op；行号必须用 px 行高，否则与正文错位。

**播放器**：对话框死黑底 → 深色渐变 + 1px 高光线；名字牌改为跟角色色（同色底 + 描边 + 白字）；选项按钮去掉 3px 蓝框改成细边 + 左侧 accent 竖条；继续提示三角 → 呼吸圆点；面板最少 3 行 → 2 行。

**示例素材**：`bg_教室` / `bg_天台` 两块土黄纯色块换成抽象氛围图（夜色渐变 + 柔光斑 + 暗角），任何比例 cover 都不出抽象方块。

**验证**：`p68-portrait-dark/light.png`、`p68-landscape-dark.png`、`play-portrait-*.png`；全量 `1085 passed + 1 skipped`（76.96s）。

## 2026-11-16（P67：横屏也算手机 + 设置里定画面方向）

**横屏**：窄屏判定从 `max-width:860px` 改成一个条件组 `(max-width:860px), (max-height:520px)`——手机横过来 844×390 以前会跌回桌面三列，现在仍是"一行顶栏 + 底部五 tab"；横屏工作台卡片排两列。

**方向设置**：设置弹层加「游戏画面：跟随 / 竖屏 / 横屏」，写进工程 `config.json` 的 `orientation`（`GET/POST /api/orientation`）。导出网页带 `<meta name="myonl-orientation">`，播放器方向不符时底部浮一句"把手机横/竖过来"，转对即消失（不硬锁，锁方向要全屏权限且各浏览器不一致）。

**踩坑**：`--script` 启动时 `app.project_root` 还是仓库根，第一版把 `config.json` 写到了仓库根目录；新增 `_current_project_root()`（= 剧本所在目录）修正，误生成的文件已删。

**验证**：`p67-home-landscape.png`（两列 + tab 贴底）、`p67-set-orient.png`、`p67-orient-hint.png`；全量 `1084 passed + 1 skipped`。

## 2026-11-16（P66：手机端工作台——先给"我的作品"，再进编辑器）

**问题**：P65 之后打开手机端仍然直接是编辑器源码，新人第一眼是行号和语法色；而且进了编辑器没有出口（没按钮回项目列表）。

**改法**：窄屏先进一层工作台——`我的作品` 大标题 + 工程卡片（名字 / `49 条指令 · 21 个素材 · 11 天前` / `›`）+ 虚线「＋ 新建作品」+ 页脚"本地作品 · 不上传云端"。点一张卡才进编辑器；编辑器顶栏最左加「‹ 作品」退回。后端两个口：`GET /api/home`（遍历 `games/` 下带 `script.gal` 的目录，数 `@` 行、数 `images/audio/fonts/video` 文件、按 mtime 倒序）、`POST /api/project`（`{folder}` 切工程，只认直接子目录名，`..`/`.`/含斜杠/空一律 400）。

**设置**：右上齿轮开底部弹层（不是全屏弹窗）——深色/浅色分段切换、返回作品列表、隐私说明一行。

**踩坑**：编辑器全局 `button { height: 28px; background: var(--blue) }` 会把工作台卡片压成 28px，名字与副标题叠成一坨；需给卡片写回 `height:auto; min-height:62px`。

**验证**：`p65-home-dark.png` / `p65-home-light.png` / `p65-set.png` / `p65-enter.png`；`/api/home` 实测 5 个工程；新测试 `test_工作台_列出工程并拒绝越界切换`；全量 `1084 passed + 1 skipped`。

**未做**：横竖屏用户设置（跟随/锁竖/锁横）、编辑器横屏布局、本机账号档案、真机复验。

## 2026-11-16（P65：手机端分层——顶栏收成一行，底部纯文字 tab，能全屏）

**问题**：真机打开编辑器，菜单栏 + 活动栏 + 工具条 + 标签页 + 面包屑 + 格式条一共吃掉 1/3 屏幕才轮到正文。这是把桌面三列 IDE 硬塞进 390 宽的必然结果，调 padding 救不了。

**改法**：手机端默认只留一行——`文件` + `⛶` + `⋯`；编辑/视图/运行/帮助、活动栏、搜索框、面包屑全部隐藏（功能都在 `⋯` 和 tab 里）。底部一条**纯文字 tab**：剧本 / 素材 / 外观 / 预览 / 导出，选中态蓝色文字 + 顶部 2px 蓝线；不放 emoji（风格不统一反而像随手拼的）。原来右侧 4 个浮圆按钮退役。

**全屏**：顶栏 `⛶` 调 `requestFullscreen()`；另加 PWA（`manifest.webmanifest` + 两个图标，`display: fullscreen`），添加到主屏幕后启动没有地址栏。服务端补了三条静态路由。播放器那边点「开始」时顺带进全屏，失败静默跳过。

**引导**：原来手机上也讲"左边/中间/右边"，对不上界面。换成手机三步：底部五个 tab、写第一行、看效果/发出去。

**浅深两套**：`data-theme="light"` 本来就有全套变量覆盖，只是手机上看不到入口；顶栏 `⋯` 里可切，tab 与顶栏全部改用 `var(--xxx)` 跟着换肤。

**诊断口**：`?diag=1` 在左上角实时显示 inner / visualViewport / dpr / body 高度 / tab 实际位置——手机定位问题靠数字判，不靠猜。

**验证**：390×844 深/浅两版截图（`p65-web-dark.png` / `p65-web-light.png`）；真机 `android-p65-2.png` tab 已贴底；`/manifest.webmanifest`、`/icon-192.png` 均 200；全量 `1083 passed + 1 skipped`。

**未做**：`config.orientation`（跟随/锁竖/锁横）与编辑器横屏布局；工程卡片工作台首页。

## 2026-11-16（P64：@camera 上手机 + 背景交叉淡入 + 真机首验）

**镜头**：`@camera` 四个子命令（zoom / pan / shake / reset）在手机端一直是空白。现在按桌面 `runtime.py` 的语义补齐：zoom 终值进存档，pan 位移 = 短边 14% 并按秒数缓入缓出，shake 带尾部衰减，reset 一起回原位。连续 zoom 不跳变（补间起点用当前实际缩放）；镜头只作用于背景/立绘/CG，对话框不动；底图按偏移量动态多铺，不露黑边。

**淡入**：`@bg` 原来瞬间换图，像幻灯片翻页。现在默认 280ms 交叉淡入，CG 切进切出同一条管线，作者不用写任何指令。

**真机首验**：vivo V2323A（Android 16 / WebView 151 / 1080×2400）。`file://` 单文件能打开、标题页正常、点开始进正文。发现浏览器自带搜索栏 + 工具栏吃掉约 250px（裸 html 不是全屏，APK 的存在理由）。新增 `tools/android_probe.py`。

**验证**：vm-smoke 新增 camera 一组断言；画面 zoom/pan/shake/reset 逐项截图对比；淡入实测红 → `[132,107,60]` → 绿；全量 `1083 passed + 1 skipped`。

## 2026-11-16（P63：CG 全屏、存档不串、缺图当面说）

**`@cg` 上手机**：之前编译器不收 CG 图、内核 OPS 里没有 `cg`、`unsupported` 里还老实列着它——不是坏，是没做。现在 `_walk` 收 `name`、`OPS` 加 `cg`、`case "cg"` 吐事件并写 `state.cg`（进存档）、播放器 `drawCg()` cover 铺满（画在立绘上、对话框下），语义同桌面端：`@cg` 上图一直盖着，下一条 `@bg` 退场。缺图时画"CG 素材缺失：xxx"。

**存档 key**：原来只有标题，两个同名工程会互抢进度。改成 标题 + 剧本名 + 指令条数。

**缺素材提示**：导出接口一直返回 `missing` 但前端没显示，作者以为没问题、别人看到空白。现在弹窗红字 + 菜单 toast 都报。

**验证**：CG 进 `assets`、单文件 59 KB、点一次后 `cg=cg_拥抱` 且左上角取色是 CG 颜色、`@bg` 后清空、读档还在。全量 `1083 passed + 1 skipped`。

## 2026-11-16（P62：让声音真的响，让包别太大）

**音频**：`@music` / `@sfx` 之前在手机端是哑的（编译器不收 `audio/`，内核把这两个 op 丢进"暂不支持"）。现在 `_collect_audio_names()` 收 `music/track` 与 `sfx/sound` → `pack["audio"]`，单文件转 `data:audio/...`；内核吐 `music`/`sfx` 事件并把曲名进存档；播放器用 `Audio` 播、支持 `fadein/fadeout`、右上角静音键、读档续上音乐。`unsupported` 里去掉 music/sfx。

**体积**：单文件里超过 300 KB 的图缩到 1600 边内转 WebP（quality 82），压不下 10% 就不换，没 Pillow 就跳过。实测 16 MB 噪声 PNG → 单文件 2 MB，省 15 MB。

**验证**：临时工程带 `@music`+`@sfx` → `MYONL_DEBUG.audio` 显示在播、点喇叭 `muted=true`；小图 `saved==0` 仍走 PNG；缺音频进 `missing` 不抛异常。新增 5 条 pytest + vm-smoke 的 music/sfx/存档断言，全量 `1082 passed + 1 skipped`。教程示例单文件 83 KB，`unsupported` 空。版本升 rc9，PyInstaller 打进 157 个 PIL 模块（exe 里压缩也可用）。

## 2026-11-16（P61：做出来的东西能交出去了——单文件导出）

**为什么**：之前的「导出手机版」是一堆文件（index.html + pack.json + 3 个 js + assets/），手机上打不开、微信发不了人。链路断在最后一步。

**做法**：`engine/webpack.build_single()` 把图片转 base64 塞进素材表、三个播放器内联进 `<script>`、剧本 IR 内联成 `window.__MYONL_PACK__`（播放器优先用它，没有才 fetch pack.json），`</script` 序列统一转义成 `<\/script`。产物是**一个 .html**，零外部请求。

**三个入口**：菜单「文件 → 导出一个 HTML」、UI 设计弹窗底部「单文件」、CLI `--single`。产物 `<发行根>/dist/single/<工程名>.html`，编辑器经 `/single-file/` 取回（带 `_safe_within` 越界防护）。

**验证**：教程示例 78 KB 单文件、0 外部请求、`file://` 双击能玩（标题/画布/点进正文/无报错）；编辑器按钮提示 `78 KB · 25 条 / 5 张`；菜单入口请求 1 次、新页能玩。新增 `tests/test_single_html.py` 8 条，全量 `1077 passed + 1 skipped`。

**边界**：base64 让图片体积涨约 37%；音频没内嵌（带 `@music` 的工程单文件里没声音，会进 unsupported）；iOS 需在「文件」App 里点开，微信里不一定能直接跑。

## 2026-11-16（P60：手机上少点手打，少点滑动）

**工具条/菜单**：窄屏隐藏工具条文字标签只留图标（6 个按钮 31–35px，390 一行放得下）；菜单的「场景/角色/素材/设置」四个显式入口隐藏（抽屉和菜单里都有）；搜索框收成 34px 圆图标，点一下展开到 131px、失焦自动收回。

**Dock 面板**：固定 180px → 窄屏 `38dvh`（实测 321px），打开问题/输出/运行日志时编辑区还剩一半。

**手机键盘快捷条**（`.m-keybar`，高 49px，贴状态栏）：`@` · `@choice:` · `@if` · `@set` · `@label` · `@show` · `→` · `缩进` · `换行` · `撤销`。只在窄屏且剧本框聚焦时出现，出现时浮动按钮让位；每个按钮 `pointerdown` 都 `preventDefault`，点快捷键时输入框不失焦（实测插入后焦点仍是 `#source`）；`setRangeText` 插入并补发 input/keyup，语法检查与预览照常刷新；`@choice:` 连缩进一起写，`缩进` 插 4 空格，`撤销` 走原生 `execCommand("undo")`；用 `visualViewport` 算键盘占位，iOS 也能顶到键盘上方。

**语音转文字不做**：手机输入法自带的语音键就够，浏览器 Web Speech 在 iOS 残缺、安卓要联网，与「离线可跑」冲突。

**验证**：`@choice:` 长度 729→742、尾部正确、焦点不丢；缩进 +4；dock 321/844；无 JS 报错。`1069 passed + 1 skipped`、pyright 基线、node 两 smoke 全绿。截图 `screenshots/p60-phone-keybar.png`、`p60-phone-dock.png`。说明 `docs/变更说明-P60-手机输入与工具条.md`。

## 2026-11-16（P59：手机上的编辑器真能用了）

**为什么**：P58 只铺满了 UI 设计页，主界面在 390px 宽下仍三栏（活动栏 46 + 工程文件 220 + 预览 520），编辑区只剩 100 出头，写不了剧本。

**做法**：窄屏只留编辑区 + 底部 4 个悬浮圆按钮——📁 文件/大纲抽屉（左，`min(80vw,330px)`）、🗂 素材抽屉（右，`min(84vw,330px)`）、👁 预览抽屉（下，`62dvh`）、▶ 转发 `#btnRun`。点遮罩或 Esc 关闭，同时只开一个；状态栏钉底、按钮抬到它上面；编辑区留 96px 让位。触屏会误触发的素材晾衣绳在窄屏隐藏。桌面（>860px）一行没动。

**踩的坑**：改完页面宽 390 被撑到 651——素材面板 `.asset-pane` 靠 `absolute+transform` 藏在屏外，隐形撑宽整个页面，`fixed` 的遮罩/dock 跟着错位（dock 跑到 x=461、点按钮被 `.main` 拦）。收口是窄屏给 `html,body` 加 `overflow-x:hidden; max-width:100vw`。另修 `.ob-card` 固定 420 宽溢出（`max-width:calc(100vw-24px)`）、`.file-pane` 抽屉只有 152 宽（`@media (max-width:900px)` 里 `width:auto !important` 压过新规则）。

**验证**：页面宽 651→390、编辑区 390、侧栏 -297→46 开/遮罩关闭、素材抽屉 328、预览抽屉 y=321、手机里敲字 46 行无报错、横屏 844 正常、桌面 1360 三栏原样。`1069 passed + 1 skipped`、pyright 112 基线、node 两 smoke 全绿。截图 `screenshots/p59-phone-editor.png` 等 5 张。说明 `docs/变更说明-P59-手机主界面.md`。

**边界**：顶部工具条仍是要横滑的文字按钮；底部 Dock 面板在手机上仍占半屏；没做手机键盘快捷工具条（`@`/`@choice:`/缩进）。

## 2026-11-16（P58：手机上手能拖能放大，少误触）

**为什么**：P57 的画布编辑是按桌面鼠标尺寸做的——390px 宽屏下编辑区三栏各剩 100px，画布被压成 200×113，面板只占 30px 高，12px 手柄手指抓不住；播放器 pointerdown 就推进，一滑就翻页。

**编辑器**：窄屏（≤860px）UI 设计页全屏覆盖；画布 1.0x–3.0x 缩放（按钮 / Ctrl+滚轮 / 双指捏合，1x=容器宽，放大后容器可触摸滚动，转屏自动重算）；命中判定按 `pointerType` 分档（触摸 22px、鼠标 14px）；触摸下 8 手柄放大 1.6 倍、绿点 1.7 倍；事件从 mouse 全家换成 pointer 全家（手指和鼠标同一条路径）。

**播放器**：点击改成「按下→抬起」判定（位移 >12px 或按住 >1.2s 不算点击，滑动不翻页，连点跳过保留）；选项按钮最小高 120 逻辑 px（≈43 CSS px）；正文号短边 1/26 → 1/22（390 宽屏约 15 → 17.7 CSS px）。

**验证**：竖屏画布 200×113 → 360×203、放大到 1.5x 后 540、触摸拖右边缘 panel_width 0→1000、桌面 1.25x 拖右边缘 1056 + offset_x -94、播放器滑动 120px 不推进。截图 `screenshots/p58-portrait-canvas.png`、`p58-phone-choice.png`。

**边界**：只有 UI 设计页做了窄屏全屏，编辑器主界面在手机上仍挤（P59）；没做双指平移；播放器没做刘海/手势条安全区。说明 `docs/变更说明-P58-触控与画布手感.md`。

## 2026-11-16（P57：对话框 UI 可视化编辑——画布上手柄拖，不再填数字）

**为什么**：调圆角/位置/宽高只能拖滑杆，数字和画面分离，改一次要来回对照。改成虚幻 / PPT 的做法：预览图上叠选择框，直接抓角、抓边、抓绿点。

**做了什么**：8 个手柄（四角 + 四边中点）+ 左上角绿点管圆角；命中判定挂在 `document` 捕获阶段、纯坐标算（边角 14px 命中带、绿点 34px 内、框内=整体移动、框外放行给点图放大），不依赖 DOM 叠层顺序；`move/e/w/n/s/四角/radius` 各自改对应键，改宽高时反算 `offset_x/offset_y` 让对边钉住；选择框改屏幕 px 定位（百分比在图未加载时会算歪）。布局上把预览列 `order:-1` 顶到最上、`flex-wrap` 允许换行——原中心页面只有 ~525px，预览列被裁成 100px 根本没法拖。

**验证**：真实 Chromium 实拖四种——本体（offset 0→-104/-78）、右边缘（panel_width 0→920 + offset_x -200）、绿点（radius 18→40）、上边缘（height 200→364）；截图 `screenshots/p57-canvas-handles.png`。pytest 1069 passed + 1 skipped、pyright 112 基线不变。

**边界**：只有「对话框」页签可拖；名字框/选项/快捷栏/菜单/设置页仍走滑杆（缺各分组的画布矩形）。说明 `docs/变更说明-P57-可视化UI编辑.md`。

## 2026-11-16（全面转手机端 + 可迁移导出：Ren'Py 工程 / 通用 JSON）

**方向**：手机端 = 主线，桌面端 = 并行出口。README 首段、编辑器文案、导出按钮位置一起改口径，不只是写一句标语。

**新增 `engine/portable.py`**：一个工程三种去处——`dist/web/`（H5，P54）、`dist/portable/<工程>/renpy/`（Ren'Py 工程：`game/script.rpy` + `game/images/`，解压丢进 SDK 即可跑）、`dist/portable/<工程>/json/`（`game.json` + `assets/` + 格式说明，任何引擎照表读 IR）。CLI `py -3 -m engine.portable <工程> --engine renpy|json|both`。

**转换规则（重点是"不假装"）**：中文图名/label/角色统一换成 `bg1/s1/label_1/c1` ASCII 短名，原名进注释；剧本在首个 label 之前的散指令收进合成 `label start`（原 start → `start_orig` + jump）；桌面专属指令（music/video/camera/anim/transition/plug…）只进 `unsupported`，不在 .rpy 里造假效果；对话框皮肤不投影（Ren'Py 有自己的 textbox）。

**编辑器**：弹窗底部两排按钮——「导出手机版」+「导出 Ren'Py + JSON」；`POST /api/export-portable`、`GET /portable-file/<名>.zip`（realpath 校验，`../` 400、非 zip 404、中文文件名走 RFC 5987）。

**验证**：`tests/test_portable.py` 8 条（label 不重复 / image 都指向真图 / ASCII 化 / `@music` 不进 rpy / 缺素材进告警 / JSON 带格式说明 / 双目标 / 路由+下载+越界）；真实 Chromium 里两个按钮都点通。**未验**：Ren'Py 侧没真跑（本机无 SDK）、APK 真机安装。说明 `docs/变更说明-P56-手机化与可迁移导出.md`。

## 2026-11-16（安卓打包：Capacitor 壳 + GitHub Actions 出 APK）

**为什么**：H5 包只能"用浏览器打开"，装不上桌面。安卓这层做成**壳**——网页包一行不改，塞进 Capacitor，APK 交给 GitHub Actions 的机器编（本机没有 JDK/Android SDK，也就不用装）。

**新增**：`tools/build_android.py`（生成 Capacitor 工程：`capacitor.config.json` / `package.json` / `www/`，可选 `--install` 跑 `npm i` + `cap add android` + `cap sync`，`--build` 出 debug APK；appId 与网页包完整性都有校验）；`.github/workflows/android-apk.yml`（手动触发填工程路径/应用名/包名，或推 `v*` tag 自动跑；上传 `myonl-debug-apk` artifact）。

**横竖屏的真开关**：`AndroidManifest.xml` 打补丁 —— `android:screenOrientation="fullSensor"`（四向都跟传感器，不锁 portrait/landscape）、`android:configChanges` 补 `orientation|screenSize`（转屏不重建 Activity，WebView 不重载，剧本不会被打回标题）。补丁幂等。

**验证到哪**：脚手架 + `npm install` + `cap add android` + `cap sync` 在本机实跑通过（`android/app/src/main/assets/public/` 里三个 js 与 pack.json 都在，Manifest 补丁已验证）；`tests/test_android_pack.py` 12 条；`gradlew assembleDebug` 与真机安装**没验**（本机无 JDK/SDK），Actions 工作流**没跑过**。说明 `docs/变更说明-P55-安卓打包.md`。

**未做（如实记）**：返回键回标题页（需 Capacitor App 插件 JS 侧）、沉浸式全屏/启动图、release 签名包、iOS、微信/抖音小游戏封装。

## 2026-11-16（手机版：同一个工程编成 H5，竖屏横屏都能跑）

**为什么**：Ren'Py 的出口是桌面，出不了竖屏 H5、上不了 itch.io 网页区和微信/抖音小游戏。所以把「手机播放器」做成正式出口，而不是给 Ren'Py 老用户做桌面平替。

**分工是硬约束**：Python 端只当**编译器**（剧本语法只有 `engine/parser.py` 一份）→ 出 `pack.json`；JS 端只当**播放器**（执行同一套 IR，不实现语法）。以后包微信/抖音小游戏只是给播放器加壳。

**新增**：`engine/webpack.py`（`build_web()` + `py -3 -m engine.webpack`，只拷剧本真正引用到的图，缺素材记 `missing` 不硬失败）；`web/myonl-core.js`（IR 执行器 + 变量插值/比较/存档/未知指令不崩）；`web/myonl-layout.js`（布局纯函数：短边 1080、长宽按真实窗口比例、字号按短边、极端比例夹 0.42~2.2）；`web/myonl-player.js`（canvas 背景/立绘/面板/打字机/选项/标题/结局，面板高度随台词行数，皮肤沿用 P53 九宫格语义）。

**编辑器**：「界面设计」弹窗新增**导出手机版**按钮 → `POST /api/export-web` 编到 `<发行根>/dist/web/<工程名>/`，并把产物挂到 `GET /web-preview/...` 供浏览器直接跑（路径 realpath 前缀校验，`../` 被拒）。

**转屏**：监听 `resize`/`orientationchange` 重算画布并重排台词，已显示字数按比例续上（不重播、不跳字）；横竖屏字号差 ≤4px。

**证据**：`web/test/vm-smoke.js`、`web/test/layout-smoke.js` node 全通过；`tools/web_shot.py` 在真实 Chromium 里竖屏 390×844 与横屏 844×390 各跑一遍剧情并断言首句/立绘/选项/分支/转屏/自动存档；`tests/test_webpack.py` 11 条（编译器 + node 冒烟 + 编辑器导出与越界防护）；`pytest -q -m "not slow"` **1047 passed + 1 skipped**；pyright **112 = 基线**；说明 `docs/变更说明-P54-手机版.md`。

**未做（如实记）**：音频（`@music/@play/@stop` 归 unsupported）、多存档槽、历史回看/快进、立绘位移参数、微信/抖音小游戏封装。

## 2026-11-15（对话框皮肤：一张图自适应 + 画布可视化 + 反导出成品）

**为什么不是「贴一张 textbox.png」**：主流教程（Ren'Py + Photopea）的做法是固定尺寸 PNG 整张替换，面板尺寸或分辨率一变就变形。MYONL 改为「一张 PNG 按九宫格切片自适应」：四角不缩放、边与中段拉伸，渐变蒙版与图案填充由引擎计算（不用回 PS 重做），编辑器里可直接在画布上拖位置/高度，最后还能把当前设计**导出成成品 `textbox.png`**（可当 `panel_image`，也能给别的引擎用）。

**引擎**：新增 `engine/dialog_skin.py`（纯函数：切边归一 / 九宫格 / 垂直渐变 / 乘法染色 / 纹理平铺 / 合成 / 缓存 / 纯色兜底）；`config.dialogue.default` 新增 10 个皮肤键（`panel_image / panel_slice / panel_tint / panel_fade / panel_fade_bottom / panel_texture / panel_texture_alpha / panel_alpha / pad_x / pad_y`），**全部留空 = 与旧版逐像素一致**，老工程零变化；1080p 边距等比缩放对列表值同样生效。

**编辑器**：新增「对话框皮肤」页签（5 套预设、九宫格四边、顶部/底部羽化、纹理强度、内边距、素材下拉）、预览画布拖拽（拖本体改横纵偏移、拖上边缘改高度、拖左边缘改面板宽度）、`POST /api/ui-design/export-textbox` 落盘 `images/<名>.png`（导出名清洗，`../evil` 返回 400）。**NVL 整屏旁白同样支持皮肤**（整屏矩形走同一套合成，未配图仍是原渐变底）。

**示例素材**：`tools/p53_sample_skins.py` 生成 `games/教程示例/images/textbox.png`（640×170 玻璃面板）与 `paper.png`（64×64 可平铺纸纹），九宫格拉伸对照图 `screenshots/p53-dialog-skin.png`。**教程示例默认启用**这层皮肤（贴图 + 纸纹 28 + `pad_y:10`），打开即可见；新建模板工程保持原样。

**安全细节**：导出的同名图默认**不覆盖**（409 + 前端确认后才带 `overwrite` 重发，文件写入走临时文件 + `os.replace`，失败不留 `.tmp`）；面板缓存的键是图片对象 `id()`，命中时再核对对象身份并持有强引用，避免 id 复用后拿到上一张图的合成结果。

**证据**：`tests/test_p53_dialog_skin.py` 24 条（纯函数 / 配置合并 / 渲染 / 白名单清洗 / 导出尺寸 / 端到端 HTTP 写回与落盘 / 前端接线）；全量 `pytest -q -m "not slow"` 1033 passed + 1 skipped；pyright 112 = 基线；engine 覆盖率 80%+ 通过；说明文档 `docs/变更说明-P53-对话框皮肤.md`。

## 2026-11-10（发行与门面收口 / P0：英文区域 Windows 打包被打断）

**P0 修复：英文区域 Windows 上「打包」直接失败**。GitHub `windows-latest` runner 是英文区域，控制台编码 cp1252；`engine/packaging.py` 打包第一步 `print("开始打包：…")` 抛 `UnicodeEncodeError: 'charmap' codec can't encode characters`，流程在产物写出之前就中断，用户看到的是「打包失败」。修复：新增 `packaging.ensure_tolerant_console()`（只把 stdout/stderr 的编码错误处理降级为 `replace`，不改编码、不碰产物、不碰已写入的 UTF-8 文件），在 `pack_project()` 入口与 `pack.py main()` 各调用一次。证据：`PYTHONIOENCODING=cp1252` 复现——修复前 exit 1（栈顶 `packaging.py:427`），修复后 exit 0、产物 22.77 MB；CI 侧同源证据 = run `42353120797` 第 5 步 `FAIL 'charmap' codec`，前 4 步（解压 / 开编辑器 / 改一句 / 运行预览）全绿。新增 `tests/test_console_encoding.py` 4 条守护（含「不加保护确实会崩」的前提用例、中文控制台原样输出、stdout 为 `None` 的冻结窗口场景）。

**英文入口上线**：`README.en.md`（英文主入口，明确写出「指令关键字与编辑器界面为中文，这是设计选择」，不夸大英文覆盖）+ `docs/en/quick-start.md`；`README.md` 顶部加语言切换，并修复第 3 行 badge 多一个右括号导致的断链。

**rc7 转为 Latest**：`prerelease` 由 `true` 改 `false`，`/releases/latest` 实测返回 `v1.0.0-rc7`；Release 正文追加中英双语说明（原文未删）。**连带发现**：`release-smoke` 按 latest 取包，此前一直下到 rc6 的包、不是 rc7，根因在此。

**展示物料**：`docs/展示_60秒分镜与投稿包.md`（7 镜 60 秒分镜、逐镜素材来源与取证要求、旁白逐字稿、B 站 / itch.io 投稿包）+ `docs/images/cover-60s.jpg`（2730×1536，由 `editor.jpg` 与 `title.jpg` 两张真截图合成，未重绘界面内容）。

**遗留（未做，如实记）**：发行包 `MYONL-v1.0.0-rc7-windows.zip` 里的 `editor.exe` 仍是修复前构建，**该 P0 尚未进入已发布的 zip**；需重打发行包、替换附件、复跑 `release-smoke` 才能转绿。

## v1.0.0-rc7（2026-11-05，交互与失败态收口 / 定版）

**失败态可定位（发行版无控制台）**：点「开始游戏」遇到剧本语法错误时，原来只写 stderr、玩家看起来像点了没反应；现在回标题并弹「剧本加载失败：第 N 行：原因」。热重载失败也把行号与原因压成单行 toast，不再提示「见控制台」。超长原因按 56 字截断，不会画出屏幕。

**失败不留半成品**：剧本保存、`config.json`、`.editor_config.json` 改为「同目录临时文件写完 → `os.replace`」，写盘中途失败（磁盘满/权限变化/杀软锁文件）时原文件保持上一版，临时文件清理干净；新增 3 条测试（原子写失败保留旧内容、不留 `.tmp`、接口返回中文错误）。模板打包沿用暂存目录方案，失败保留上一版产物。

**交互与错误提示补齐**：设置音量/改键真正写回 `settings.json`，写盘失败弹中文 toast；`/api/check` 网络失败不再让预览栏卡在「检查中…」；存档/读档失败弹中文 toast，读档失败退回存档列表重选；桌面窗口关闭前提示未保存改动；补 F5 / Ctrl+R / Ctrl+P / Ctrl+N / Ctrl+, 快捷键。

**编辑器对齐与窗口缩放**：高亮层宽度改为跟随 `textarea.clientWidth`——WebView2 竖向滚动条占 10px，原来铺到 `right:0` 会比内容区宽出一截，软换行断点不同会让行号/当前行/错误浮层越往下偏越多（末尾表现为多一行 22px）。Dock 高度在窗口变矮时重新夹紧，并给编辑区保留 300px：420px 高窗口下正文由 20px 恢复到 112px。

**性能实测（4000 行文档，CDP 采样 20 键）**：单键约 42.5ms，其中 `syncScroll` 读 `clientWidth` 触发的 textarea 整篇重排占 41.05ms；`updateLineNumbers` 0.17ms、`incSignature` 0.08ms、`updateBreadcrumb` 0.08ms。对比实验证实该重排在绘制前必然发生，推迟读取不减少总耗时；逐行正则与面包屑合计 <1%。因此本轮不做微优化（收益低于噪声），大文档输入性能作为已知限制记录，后续若需要只能换编辑器架构（contenteditable / 虚拟滚动）。

**验证**：`pytest -q -m "not slow"` **1004 passed + 1 skipped**；`-m slow` **32 passed**；pyright **112 = 基线**；`verify_editor_trae_ui.py` **41/41**（教程示例 + 多文件工程各一轮）；`smoke_editor_exe.py` 两项 exit 0。

## v1.0.0-rc6（2026-11-02，发行版发布阻断修复 / 标准示例 Demo）

**P0 修复：发行版「一键打包」实际不可用**。冻结后的 `editor.exe` 没有 Python/PyInstaller，打包 API 最终调用 `pack.py` → `editor.exe -m PyInstaller` 必然退出码 2。修复：随包内置**玩家运行库模板**（`engine/templates/player/MYONLPlayer.exe + _internal`，22.8MB），打包 = 复制模板 + 游戏资源，1 秒完成；新增 `engine/player_app.py` 作为模板与源码头（`pack.py` 复用同一入口）、`tools/build_player_template.py`（`build_editor.bat` 缺失时自动构建）、`engine/packaging.py` 的模板打包分支（冻结模式优先模板，缺模板给中文提示）。`tools/build_release_zip.py --verify` 新增「玩家模板必须在包里」检查。

**P0 修复：编辑器预览污染运行窗口**。`_preview_png` / `_ui_design_png` / `newgame` 用 `os.environ.setdefault("SDL_VIDEODRIVER","dummy")` 永久改进程环境，之后「▶ 运行」spawn 的子进程继承 dummy → 游戏窗口永远不出现（看起来像按钮没反应）。新增 `engine/sdl_env.py` 的 `dummy_video` 装饰器：只在本函数内设 dummy，退出恢复原值（`tests/test_sdl_env.py`）。

**验证工具**：新增 `tools/verify_release_flow.py`——解压发行包 → 空 AppData/无 Python 启动编辑器 → 改一句 → 保存 → 语法检查 → 运行（确认真实游戏窗口）→ 一键打包 → 启动成品窗口；rc6 全流程 **PASS**。

**Demo**：`games/标准示例` 展示名改为《晚风与约定》（窗口标题/标题页/打包名），模板打包产物 23.3MB；窗口图标改为读取工程 `icon.png`（模板 exe 无法改文件图标）。

**桌宠 Mooki 核验**：**默认关闭**（`/api/pet status` 初始 `running=false`，编辑器启动不拉起）；在「设置 → 桌宠」或「视图 → 桌宠（实验）」打开后启动独立进程（源码 `python -m engine.pet` / 发行版 `editor.exe --pet`）。修复冻结版右键「打开 MYONL 引擎」误拼 `-m engine.editor_app` 的问题；`editor.spec` 补 `brand/mooki_layers`，发行版与源码版使用同一套分层素材。新增 3 条测试（默认关闭 / 启停命令 / 右键命令）。

**测试**：全量 **1007 passed + 1 skipped**（本机内存紧张，分两批跑：994+13；新增 4 条玩家模板复制用例 + 2 条 SDL 环境隔离用例 + 3 条桌宠用例）。

**发行**：editor.exe 重打（8.1MB，含玩家模板与桌宠分层素材）；`MYONL引擎-v1.0.0-rc6.zip` 46.4MB / 407 文件，SHA256 `4510CBCD242666B3112ED963061B7205E14DCC7B24E8098ECB36527AAADF408D`；解压冒烟 exit 0；净环境（空 AppData + 剥离 Python）真实编辑器窗口 PASS；`verify_release_flow.py` 全流程 PASS（打包 1.0s / 22.8MB，成品窗口打开）。

**文档**：`快速上手` / `打包使用指南` 区分「发行版一键打包（无需 Python）」与「源码版 pack.py」；发行版 README 补「打包约 1 秒、不需要 Python」。

## v1.0.0-rc5（2026-11-02，全交互走查 / 5 个交互缺陷修复）

**全交互走查**：新增 `tools/ui_walkthrough.py`——用真实 `KEYDOWN` / `MOUSEBUTTONDOWN` / `MOUSEMOTION` 事件驱动 `Renderer.handle_input → UI → 业务`，按玩家顺序走 43 步并逐屏断言（标题 → 设置分组/滑条拖动/改键 → 空读档 → 新游戏 → 回看/隐藏 UI → 快捷栏 AUTO/F5 → 10 格存档/读档 → 选项锁 → CG → 画廊 → 菜单 → 继续 → 终幕淡出）。产物 `screenshots/walkthrough/`（43 张 PNG + `walkthrough.gif` + `report.html`）。

**修掉的 5 个交互缺陷**：
1. 点「开始新游戏」先出现空画面，要再按一次空格才出第一句 → 加载后立即推进到首句（`engine/demo.py`）。
2. 标题 → 画廊 → Esc 钻进游戏内菜单 → 记住来路，返回标题（`engine/ui.py`）。
3. playing 态快捷栏 / ◀ 回看 / ▼ 推进看得见却点不动（鼠标只被当成推进剧情）→ 命中控件后按语义分派（`engine/render_window.py`）。
4. 存档页 10 格只画出 3 格（`divmod` 行列写反 + 越界 `break`）→ 5×2 全部可见、可点并垂直居中（`engine/render_ui_pages.py`）。
5. 方向键左右在真实主循环被丢弃 → 存档九宫格、画廊页签/轮播左右可操作（`engine/demo.py`）。

**验证**：全量 **998 passed + 1 skipped**；新增回归用例（首句立即出现、画廊返回层级、快捷栏可点、10 格全画出、5 列键盘导航）。设置卡片改为垂直居中。

**发行**：editor.exe 重打（8.1MB）；`MYONL引擎-v1.0.0-rc5.zip` 35.2MB / 283 文件，SHA256 `78A9013F283575AC0BAB6CEF6E5ECF4E78ACEE198CBD560128B4D1DB63BD52DD`；`build_release_zip.py --verify` 冒烟通过；`verify_release_clean.ps1` 净环境（剥离 Python + 空 AppData）`editor.exe -h` / `--demo-worker` exit 0，真实窗口 `[MYONL 编辑器]` 成功打开。

## v1.0.0-rc4（2026-11-02，空包 / 台词语法 / 编辑器交互）

**台词语法**：`@[角色] 文本`（普通对话框，无需登记）、`@[角色]` + 换行、`@[[角色]] 文本` / `@[[整段文字]]`（整屏独白 NVL）、`@ 文本` 与 `@` + 换行（旁白）；**冒号不再有特殊含义**，`@ 注意：请勿靠近` 是旁白；旧 `@ 已登记角色 文本` 继续有效（`tests/test_parser.py`）。

**数据与流程修复（2026-11-02）**：卡片视图补齐 `@wait` / `kind=` / `@show x/y`，角色台词统一方括号回写（不再降级成旁白）；场景视图保存原位改写并保留 `anim=`、分层立绘、`fadein`；UI 设计修复像素化布尔/快捷栏字符串类型、空配置 GET 缺省值；改键后确认键统一走 keymap（自定义键生效）；选项全不可选时自动推进并告警；跳到 `@if` 内 `@label` 会补齐父帧。玩家侧：存档补齐第 10 格 + F5 快存独立 quick 槽、SKIP 默认开启、标题/设置/回看提示走 i18n、教程与模板改用 `@[角色]` 写法、标准示例标题页补作品名、`data_dir` 真正作用于存档读写（`tests/test_runtime.py` / `test_parser.py` / `test_ui.py` / `test_data_dir.py`）。

**语法修复（同日）**：台词插值规范写法改为 `${变量}`，修 `{b}` 富文本被插值吞掉的回归（旧 `{变量}` 仅在变量已定义时仍生效）；缩进支持行首 Tab（按 4 空格，`tests/test_parser.py`）；场景视图台词解析改为按方括号深度匹配（修 `@[林晚[老师]]` 名字截断，与引擎语法对齐，`tests/test_u_interactions.py` 用 Node 实跑校验）。

**空包与素材**：编辑器「新建游戏」= 极简 hello world（一行可改可删的旁白，不带素材）；`engine/templates` 随 editor.exe 进包；打包时缺失背景自动补白底占位图并写文件名；素材全删仍可进标题开局（`tests/test_builtin_assets.py`）。

**UI 配色**：编辑器「UI 设计」新增「配色」分组——10 个语义主题色（primary / primary_soft / accent / surface / surface_alt / text / text_dim / border / danger / success）取色器直改、实时预览；保存只改 `theme` 白名单键，「恢复引擎默认」用 `null` 清掉覆盖回落到 `THEME_FALLBACK`（`tests/test_editor.py` / `tests/test_p51_editor_ui_design.py`）。

**编辑器**：场景视图新增「图层顺序」面板（UI > 前景 > 立绘 z > 背景，拖拽或 ↑↓ 改 z，舞台同步遮挡）；场景列表与源码区右键菜单（查看属性 / 复制粘贴一幕 / 复制剪切粘贴文字，剪贴板存 localStorage）；修带 BOM 剧本误报「没有场景」；场景表单识别三种台词写法并保留原写法（`tests/test_u_interactions.py`）。

**发行**：editor.exe 重打（8.1MB，含内置素材模板与全部前端模块）；`MYONL引擎-v1.0.0-rc4.zip` 35.2MB/283 文件，解压冒烟通过（`editor.exe -h` 与 demo worker 均 exit 0）；`build_release_zip.py --verify` 增加「内置模板必须在包里 + 快速上手链接必须可达」检查；教程示例游戏端到端打包 22.76MB（`dist/教程示例`）。编辑器启动前检测 WebView2，缺失时弹中文安装提示（不再静默无窗口）；新增 `tools/verify_release_clean.ps1` 净环境冒烟（剥离 Python 环境变量后直接跑冻结 exe）。

**文档**：README / 快速上手 / 开发者使用指南 / 产品说明书 / engine_spec 同步到 24 条指令与括号台词写法；新增《架构说明》（模块职责/数据流/扩展点）与《贡献指南》（环境/门禁/同步规则/提交格式）。

## v1.0.0-rc3-dev（2026-11-01，可视化创作层：场景/角色/视频/编辑器拆分）

**场景视图（对标 LetsGal Studio，双入口同一 .gal）**：左场景列表 + 右属性面板（背景/音乐/视频/角色/台词/选项/跳转）；保存只改对应行，未知指令保留；首个 @label 前的「开场设置」可编辑；舞台 16:9 预览（背景/沿用背景/角色可拖动）。

**画面级（B）**：角色位置预设（左/中/右）、舞台拖拽写回 `@show … x= y=`（引擎新增 x/y 像素偏移，向后兼容）、双击复位；z/scale 控件（引擎原语）。

**视频/纯画面场景（C2）**：解析 `@video`（保留 fps=），属性面板视频下拉，舞台「点击播放」，列表「视频/纯画面」徽标，无台词场景可保存。

**角色库（引擎级 characters.json）**：角色=一等资产（颜色/布局/表情→素材映射），Runtime 启动播种、`@character` 仍可覆盖；编辑器角色库面板 + 从素材导入（角色_表情）+ 场景视图头像/表情候选；批量改名同步 `@character/@show/@hide/@anim/台词`。

**场景管理**：＋新场景/复制/删除（先扫 @jump/选项引用）、类型筛选；未做拖拽重排（文件顺序=叙事顺序）。

**第二批（同日）**：素材面板内嵌「角色」分类；舞台接入引擎真实渲染（预览帧作底图）；场景列表搜索 + 分段渲染（大项目）；清理并行 WIP、覆盖率刷新、过期文档加 `无用-` 前缀。

**工程**：`index.html` 3996→529 行（主脚本抽到 `editor_main.js` + 路由，token 断言迁移）；pyright 159/165；测试 900 passed + 1 skipped（1 failed 为并行会话 WIP）；验收脚本 22/22。

**编辑器三档模式（E9，同日）**：新增 `editor/editor_level.js` + 菜单栏「L1 新手 / L2 默认 / L3 专业」下拉，选择记 localStorage：
L1 隐藏属性检查器 / 时间线 / 素材晾衣绳 / 富文本工具条 / 语言下拉 / 问题详细切换，视图菜单隐藏 JSON/卡片/UI 设计区/桌宠；
L2 = 现有完整布局；L3 额外开放「源码 / JSON / 卡片」视图页签。命令面板（Ctrl+Shift+P）同步按档位过滤。
**打包修复**：`editor.spec` 漏带 `editor_main.js` / `editor_scene.js` / `editor_characters.js`（发行包打开编辑器会 500），已补全全部前端模块清单并加测试守护。
**工程**：测试 910 passed + 1 skipped；pyright 159/165（顺手修 `renderer._options` 声明，清掉 5033428 遗留的 1 个新增报错）。
**发行**：editor.exe 重打 8.0MB（确认含 `editor_level.js` 等全部前端模块）；`MYONL引擎-v1.0.0-rc3.zip` 34.8MB/258 文件，解压后 editor.exe 冒烟 exit 0。

**文档清理（同日）**：第二批删 12 篇（真人测试 2、已交付设计 8、评估 2）；第三批把计划书-M1.6 / 真机测试 / 测试任务 / 协作分工 / 两篇交付记录共 6 篇**合并进 `docs/计划/00-总览`**（已交付只留汇总表，计划只写未完成）；第四批删 `docs/archive/` 全部 104 篇 + `项目协作制度.md`（历史只在 git，`git log --all -- docs/archive` 可找回）。测试改为 **Windows Sandbox 零帮助自测**，不再依赖真人陌生人；产品说明书测试数同步为 910。

## v1.0.0-rc2（2026-11-01，M1.5-C 收口 / 首个可发测试包）

**报错体验（A）**：结构化错误对象（summary/detail/hint/line/file，旧字段兼容）；问题面板「简单/详细」双视图（详细含指令原文/建议/复制，localStorage 记忆）；常见错误 10 类「你是不是想写…」提示；底部 Dock（问题/输出/运行日志）。

**排版与字号（B）**：玩家字号三档（0.85/1.0/1.2，行距自动跟，切档实时重建字体）；编辑器「UI 设计区」新增**正文字号 / 正文行距**滑杆（写回 `font.body`/`line_height.body`，实时预览，非白名单字号键保持不变）。

**游戏 UI 打磨（C）**：设置页内容卡片 + 分组标题 + 上下文提示；选项与对话框间距参数化（`ui.choices.dialog_gap` 默认 40）；标题排版配置收口（`_title_layout`：对齐/字距/菜单几何/作品名坐标全走 config，左列不再写死 96/70）。

**编辑器层次（D）**：底部 Dock；活动栏徽标（问题数红徽标 / 未保存黄点 / 素材导入转圈）；侧栏分组折叠（工程文件 / 章节大纲，chevron + 记忆）。

**标准版 UI**：模板只保留唯一 `black` 主题，冻结「标准版 UI v1」+ config 全量外观键速查；开发者按需改 config，不做风格包/预设。

**工程**：pyright 棘轮基线 **555 → 165**（渲染四 Mixin 补宿主属性 TYPE_CHECKING 声明，+ B2-UI 写回处 None 收窄）；全量 **887 passed + 1 skipped + 1 xfailed**；preflight -Fast exit 0。

**发行**：editor.exe 重打 8.4MB + 冒烟 exit 0；发行包 **MYONL引擎-v1.0.0-rc2.zip（34.7MB / 254 文件）**，解压冒烟通过（含 M1.5-C 全部 UI/报错/编辑器改动）。

**后续待办**：干净 Windows 环境人工抽测、接入 CI 流水线；路线见 `docs/计划/00-总览.md`。

## v1.0.0-rc1（2026-10-31，引擎候选版）

**引擎**：792 项测试 / 791 passed + 1 skipped；engine 覆盖率 82.64%；pyright 棘轮 623 通过；
T6 剧本/配置热重载（--hot-reload）、T8 字体缓存（对话绘制 -76%）、T10 分辨率可配 + 1080p 视觉比例、
22 条缓动曲线、测试分层 markers + 覆盖率门禁。

**内容**：standard 模板由《雨夜车站》回退《晚风与约定》；雨夜素材管线与示例残留删除（5 个提交）。

**游戏 UI（玩家侧，M1.5-B）**：标题排版配置收口（对齐/字距/菜单几何/作品名坐标全走 config）；设置页视觉升级（内容卡片、分组标题、提示按页变化）；选项与对话框间距参数化（`ui.choices.dialog_gap` 默认 40，不再贴边）；设置页扩到 11 项——显示模式（窗口/无边框全屏/全屏）、AUTO 速度三档（叠在 pacing 上）、静音与配音音量、**字号三档（0.85/1.0/1.2，行距自动跟）**、默认打字速度 45；新工程首次窗口按设备档位；低配自动跳震动/缩缓存；快捷栏首次提示一次。

**报错体验（M1.5-C）**：结构化错误对象（summary/detail/hint/line/file，旧字段兼容）；问题面板「简单/详细」双视图（指令原文/建议/复制）；常见错误 10 类「你是不是想写…」提示；底部 Dock（问题/输出/运行日志）。

**编辑器**：素材晾衣绳（交互想法参考 Tendedero/MIT，独立实现：悬停滑出最近素材、点卡片插入、置顶常用、拖拽到代码区、最近 6 条预览历史）；内嵌教程/说明书侧栏（帮助→教程，F1 开关）；问题面板（语法错误列表 + 点击跳行）；保存/预览成功微反馈（reduced-motion 关闭）；**Trae/VSCode 式分层感**——面包屑（工程›文件›@label）、分区标题层级、状态栏问题徽标/编码、检查器/时间线折叠。开发者边写边看，玩家侧不出现新手任务清单与教程弹窗。

**素材**：批量素材导入工具（`tools/import_assets.py`）——照片 cover 裁切/清洗/去重/清单、短视频抽帧为 `@video` 帧序列、生成可粘贴的 .gal 片段。

**体验（M1.5）**：演出节奏商业向默认值（换景 0.35s / 转场 0.45s / 大幕 0.9s / 幕间 0.25s / AUTO 0.9s，config.pacing 可调）；
设备评估详细版（内存/CPU/显卡/屏幕/磁盘逐项评分 + 依据 + 建议值，`py -3 -m engine.capability`）；竖屏（抖音）素材模糊填充导入。

**发行**：编辑器可打包（editor.exe 8.0MB，冻结形态跑 demo 冒烟通过）；引擎发行 zip **34.7MB/254 文件**（含内嵌教程，解压冒烟通过）；教程示例工程 + 快速上手文档。

**工程**：文档体系切 release 里程碑制（STATUS/ROADMAP/BACKLOG/CHANGELOG + archive）；
架构约束测试化；`tools/preflight.ps1` 一键门禁 + `tools/status.py` 状态数字自动生成；补根 README。

**后续待办**：早期使用者反馈收集、CI 接入；编辑器徽标与侧栏折叠、字号行距控件、标题配置等改进见 BACKLOG。

> 定位：MYONL 是**引擎工具**，示例游戏（标准模板《晚风与约定》）只作可改样板，不作为产品交付。

历史：git 提交记录（原 `docs/archive/` 104 篇已于 2026-11-01 删除，可用 `git log --all -- docs/archive` 找回）

**P67 补**：工作台卡片加缩略图（`GET /api/thumb`，优先 `icon.png`，退到 `images/` 第一张），卡片变「左图右文」；全量 `1085 passed + 1 skipped`。
