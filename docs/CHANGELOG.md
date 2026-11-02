# CHANGELOG

> 只记 release 级变化，一句话 + 证据链接。单项细节见 git 历史（原 archive/ 已删除）。

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
