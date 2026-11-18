# STATUS

> **唯一权威状态页**：现在在哪、下一步做什么、什么被卡住，只看这一页。
> 历史计划与变更说明只保留在 git 历史（原 docs/archive 已于 2026-11-01 删除）。
> 维护规则：人只改上面的四行；自动数字区由 py -3 tools/status.py --write 生成。

- **版本**：v1.0.0-rc19（**手机端为主线**：同一工程 → 竖屏/横屏 H5 网页包 → 安卓 APK；桌面端降为并行出口）。rc11 之后：P69 播放器菜单/6 档存档/设置四项 · P70 选项可调 · P71 UI 设计区整屏参照 · P72 PWA 主屏图标 + 启动遮罩 · P73 `@fg/@anim/@video/@voice/@chapter/@transition` 手机端全实现 · P74 全身立绘与常驻微动 · **P75–P85 手机端存储层两键结构 + 首次引导 + 长按菜单 + 横屏两列设置 + 砍桌宠** · **P86 对话框按台词行数自适应 + 竖屏双立绘内收 + 标题页真封面 + 占位换真插画** · **P87 修发行包漏带前端模块 + 清 80 MB 废料** · **P88 砍「手机连接」** · **P89 砍 AI 助手 + 修手机端 `@else` 分支永不执行的 bug + 第一部完整作品《研修日志》** · **P90 桌面端标题页对齐手机端** · **P91 升级不毁档（玩家数据搬到 %APPDATA%/Moyul/<游戏名>，老档首启复制不删除，发行包不带 saves/）** · **P92 手机端右侧竖列「存/回/设」+ 名牌缩字号** · **P93 手机端存档导出/导入（换文件/换设备不再丢档）+ 面板与格子高度对齐** · **P94 手机端视觉重做：控件统一成 44–96 圆形、竖列垂直居中、菜单改列表行、面板改底部抽屉、名牌去掉描边胶囊** · **P95 横竖两套构图：`images/{名}_p.png` 可选竖版变体 + `config.json` 的 `"focal"` 构图锚点，网页端/桌面端各接一次；《研修日志》补两张真竖版背景**。发行包 `dist/release/MYONL引擎-v1.0.0-rc19.zip` 解压冒烟通过，**未上传 GitHub Release**（本机无 gh CLI / token，用户也说明不需要）。
- **在做**：真机验证仍为零（`adb devices` 只有表头，`adb` 在 `D:\娱乐工作区\_tools\platform-tools`）。**APK 已经能出包了**（P96：自建 WebView 壳 + 固定签名 + 沉浸全屏 + 返回键接管，CI 出 release 包并挂 Release：
`MYONL-apk-3.apk` 3,770,281 B / v2-v3 已签名 / 内含 3.1 MB 单文件 HTML，解出来在 390×844 里跑通标题页→进游戏→返回键三态）。
手机端"升级不丢档"两条腿都补上了：桌面端数据搬到 `%APPDATA%`（P91），手机端加**存档导出/导入**（P93），APK 侧靠**固定签名**（P96）。
**P97 默认 UI 去盒子化**：标题页竖屏不再用卡片（改整宽四段渐隐、字左对齐站在暗处）、面板兜底高从 3.5 行收到 1.9 行（一句台词的框从 19% 屏高降到 14.5%，立绘裙子膝盖完整露出）、菜单行去盒只留分隔线、设置页三个小盒改一条分段控件、存档空档改虚线框、横屏不画面板上缘线、右侧三键去描边并下移到 55%。
剩下：鉴赏页（CG/音乐）无数据链路（`gallery_config.json` 空壳、webpack 不打包 gallery）、立绘分层（眨眼/口型）、桌面端除标题页外的其余页面仍是旧形态。
**P98 补信息表达**（P97 只清了负分）：①发言方亮、非发言方压到 `brightness(0.72)`（120ms 补间；只有"说话人自己在场上"才压别人，旁白不压，避免画面闪；用亮度不用透明度，否则非发言方会透出背景栏杆）②存档格铺当时的背景缩略图（cover 裁切 + 左重右轻压暗，老档无 `bg` 字段退回实底）③`writeSlot` 没有在跑的进度时不再静默返回，页脚写"这局还没在跑，没有可存的进度"，写不进 localStorage 时也明说。
**P102 演出模式进菜单第一层**：①「画面方向」原来在「菜单 → 设置 → 画面方向」三层，手机上换握法不会点三层 —— 现在菜单列表里直接一行 `画面方向 · 自动/竖屏/横屏`，点一次循环一档，`savePrefs()` + `fit()`（`fit` 会把窗口宽高对调，画面自己转、上下补黑边）②菜单从 8 项变 9 项，面板行数 4/8 → 5/9，竖屏行高 2.3 → 2.12（九行 2.3 会顶到屏底，「回到标题」被裁半行）③菜单页背景 0.90 → 0.970（菜单是一列字，0.90 会让台词透上来，字压字像没画完；设置/存档/回顾仍 0.90），菜单页脚注从 footH 收到 0.5 倍字号（最后一项就是「回到标题」，脚注没字可写，按 footH 留就是一块空幕）④`MYONL_DEBUG.panel` 暴露 `menuPanel()` 几何 + `viewH`，验收脚本能量出屏不出屏。实测：`audit/p102-{p,l}-menu.png`、`p102-{p,l}-orient.png`；实点一次 `orient` 后 `myonl:v2:prefs.orient` 由 `auto` → `portrait`（竖横两档都验）；竖屏面板 `y 1049 / h 1256 / viewH 2337`（底 2305 不出屏）。
**P101 对话框不再挡画面**（用户原话"完全的车挡画面确实也不好"）：①对话框贴满左右 + 最底 0.97 → 立绘的鞋和地板全被盖掉；设置里多一组「对话框」三档：**经典**（不透明底板 + 九宫格皮肤）/ **幕**（默认，全宽暗幕，46% 屏高以上一点不压，往下分三级压到 0.86）/ **字幕**（同样无框、最底只压 0.55）。1/2 两档**不画矩形** —— 半透明矩形的病不在透明度，在它有一条边界，亮处露边、暗处消失，同块面板时隐时现 ②面板高度按句子实际行数给（竖屏 `max(1.4, rows)`、横屏 `max(1, rows)`，原来 `rows + 0.9` 会让一句单行台词撑出三行高的板，底下全空）③菜单/存档/设置/回顾的遮罩 0.93 死黑 → 上 0.28 下 0.66 的渐变（打开菜单不再等于关掉画面）④`textLeft(rect)` 统一正文左缘：内缩后正文仍按 `L.textW` 折行（layout 契约不变），左右留白按面板居中算。实测四档 × 三档十二张：`audit/dlg-{p,l,tp,tl}-{0,1,2}.png`。
**P100 手机平板上的视频与存档**：①`@video` 帧缓存原来没有上限 —— 一帧 1080×1920 解出来 8 MB 出头，10 秒 24fps 是 240 帧，循环第一轮就能吃掉 2 GB，手机上表现为白屏；改成只留最近 14 帧（`VIDEO_KEEP`），超出从最旧丢引用 ②`@video` 进入先预热头三帧（否则第一帧还在读、画面黑一下），`@bg` 接管时整片释放，播放时顺手叫下一帧 ③读档续上视频重设 `t0`（存档里那个时间戳会把帧号跳到随机帧） ④存档格台词从 `slice(0, 16)` 改成按 `measureText` 收边 —— 横屏三列卡片窄，16 个中文字会压到隔壁格子（拍 README 图时一眼看到） ⑤README 中英双双重写：APK 下载入口提到最上面、测试数 1155、最近四期换成 P97–P100、界面图换成手机竖横 + 平板竖横 + 视频背景五张真机图、FAQ 写清"玩家侧不限 Windows""平板不用单独打包""升级不毁存档"。实测（24 帧序列四档设备）：缓存恒定 14、切走归 0、`pageerror` 空。

**P99 安卓平板适配**（玩家侧定稿为「手机 + 安卓平板」，桌面端播放器代码保留但不再演进）：①字号从"逻辑比例 `短边/22`"改成按物理 CSS 反推 `18.5×1080/短边CSS` —— 原来平板 800 CSS 宽时同样的 49 逻辑会变成 34.8 CSS px，等于把手机内容整体放大一倍；现在手机 51 / 平板 25，落到眼睛里一样大 ②正文宽度上限 720 CSS px（约 39 字一行），管住安卓平板横屏 1280×800 那种宽画布 ③立绘高度改用「当前」面板高度现算（`min(0.86屏高, panelTopY-6)`），平板竖屏立绘从 53% 涨到 71% 屏高、长句再连续收回 ④`layoutFor` 返回 `tablet`，smoke 契约改成「物理字号 17.5~19.5 CSS」「一行 ≤41 字」并加了 800×1280 / 1280×800 / 1024×600 三档。
- **质量门槛**：干净 Windows（无 Python）下可做出并打包可玩 demo；H5 播放器在真实 Chromium 竖屏 390×844 / 横屏 844×390 + 转屏 + 自动存档全过；安卓 APK 由 CI 产出（`gradle assembleRelease` 绿，固定签名，Release 可匿名下载）。
- **本机限制**：无 JDK / 无 Android SDK / 无 gh CLI / 无 Ren'Py SDK——所以 **APK 只能在 CI 里编**、**Ren'Py 导出工程没在 Ren'Py 里真跑过**；Actions 日志需 token（已改成失败时写 `::error::` 注解，匿名可读）。**真机 adb 需另装 platform-tools（`D:\娱乐工作区\_tools\platform-tools`），且必须覆盖 TEMP 才能起 daemon**（默认 `%TEMP%` 写 `adb.log` 会被拒）。
- **后续待办**：① 真机装一次 APK、验转屏/选项/CG/读档 ② 鉴赏页（CG / 音乐）数据链路 ③ `@plug` 插件调用（手机端无对应实现） ④ 桌面端其余页面对齐手机端 ⑤ 桌面端也加存档导出/导入（现在只有手机端有）。

<!-- auto:begin -->
<!-- 自动数字区：由 tools/status.py 写入，勿手改 -->
- 测试收集：1124 项（通过数见下方「最近验证」）
- 覆盖率：80.49%（门禁实测，但为旧提交 4941913，需重跑）
- pyright：115 个错误 / 基线 112（超出基线，需修）
- git：113 个提交 · 最新 tag v1.0.0-rc11 · HEAD 54da0f1 feat: P71 UI 设计区整屏参照预览（300x649 缩略手机，参数实时补间）+ 修 _get_asset 用 data_root 取素 · 工作区有未提交改动
<!-- auto:end -->

## 冻结令

M1 期间，engine/ 只接受「阻塞陌生人上手」的 P0 修复；功能与重构一律进 BACKLOG。示例游戏只作可改样板，不做完整作品。

## 最近验证

| 日期 | 命令 | 结果 |
|---|---|---|
| 2026-11-16 | `py -3 -m pytest -q -m "not slow"` / `tools/preflight.ps1` | **1035 passed + 1 skipped**；pyright **112 = 基线**；全量 1067 passed + 1 skipped；覆盖率 **80.49%**（门禁 80% 通过，基线 81.09——新增模块的防御分支拉低，非回归） |
| 2026-11-16 | `py -3 -m PyInstaller --noconfirm --clean editor.spec` + `tools/build_release_zip.py --verify` | 重打 `dist/editor/editor.exe`（8.1MB）与 `MYONL引擎-v1.0.0-rc7.zip`（46.5MB / 411 文件）；冒烟：`editor.exe -h` exit 0、`--demo-worker` exit 0，「解压即可用」通过 |
| 2026-11-16 | 发布副本 `MYONL-publish`：`py -3 -m pytest -q -m "not slow"` | **1031 passed + 1 skipped**（镜像 15 个 P53 文件后复跑，提交 `5fff154`） |
| 2026-11-10 | `$env:PYTHONIOENCODING="cp1252"; py -3 pack.py "games\教程示例"` | **修复前 exit 1**：`UnicodeEncodeError: 'charmap' codec can't encode characters`，栈顶 `engine/packaging.py:427`（与 CI run `42353120797` 同源）；**修复后 exit 0**，中文日志按预期降级成 `?`，产物 **22.77MB** 正常生成 |
| 2026-11-10 | py -3 -m pytest -q -m "not slow" | **1009 passed + 1 skipped**（新增 `tests/test_console_encoding.py` 4 条；架构门禁 `test_每个测试文件声明分层marker` 通过） |
| 2026-11-10 | GitHub API 复核 | `release-smoke` 在 `72bf5fe` **failure**（run `42353120797`，第 6 步失败）；`tests` 在 `3bdeb62` 与 `9cc005a` 均 success；`/releases/latest` 返回 `v1.0.0-rc7` |
| 2026-11-07 | py -3 tools/verify_release_flow.py --zip dist/release/MYONL引擎-v1.0.0-rc7.zip | **PASS / exit 0**：解压 408 文件 → 无 Python + 空 AppData 启动编辑器窗口 `[MYONL 编辑器]` · API 53449 → 改一句 → 语法检查 → 运行（`[教程示例]` 窗口）→ 打包（22.9MB，3.1s，走内置玩家模板）→ 成品窗口 `[教程示例]` |
| 2026-11-07 | py -3 -m pytest -q -m "not slow" | **1005 passed + 1 skipped**（新增 `tests/test_release_zip_manifest.py` 守护发行包清单） |
| 2026-11-07 | py -3 tools/build_release_zip.py --version v1.0.0-rc7 --out dist/release/_candidate/… --verify | **409 文件 / 46.43MB**，冒烟两项 exit 0；与旧包diff 只多 `tools/win_env_check.bat`（SHA256 `AAAEF00B…9CEA2`）。**附件已于同日替换**：asset `MYONL-v1.0.0-rc7-windows.zip` 46.43MB / SHA256 `AAAEF00B…9CEA2`（下载数归零），Release 正文补「2026-11-07 附件更新」段 |
| 2026-11-05 | py -3 -m pytest -q -m "not slow" / -m slow / tools/check_types.ps1 | **1004 passed + 1 skipped；slow 32 passed；pyright 112 = 基线（不新增）** |
| 2026-11-05 | py -3 tools/verify_editor_trae_ui.py（教程示例 + 多文件工程） | **41/41 × 2**：含 900/1024/800 窄窗口、滚动到底正文可见、光标/行号/错误对齐 |
| 2026-11-05 | PyInstaller --clean editor.spec + tools/smoke_editor_exe.py | **exit 0**：`-h` / `--demo-worker` 两项冒烟通过 |
| 2026-11-02 | py -3 tools/verify_release_flow.py | **PASS**：发行包解压 → 空 AppData/无 Python 开编辑器 → 改一句 → 保存 → 运行（真实游戏窗口）→ 一键打包（1.0s / 22.8MB）→ 成品窗口；发布阻断全部修复 |
| 2026-11-02 | py -3 tools/build_release_zip.py --version v1.0.0-rc6 --verify + tools/verify_release_clean.ps1 | **46.4MB / 407 文件**（SHA256 `4510CB…F408D`），含玩家模板与桌宠分层素材；解压冒烟 exit 0；净环境真实窗口 `[MYONL 编辑器]` PASS |
| 2026-11-02 | py -3 -m pytest -q（分两批） | **1007 passed + 1 skipped**（玩家模板 4 例 + SDL 环境隔离 2 例 + 桌宠 3 例；第一批 994+1 跳过，第二批 13） |
| 2026-11-02 | py -3 -m pytest tests/test_u_interactions.py -k 桌宠 + 冻结版手动 | **5 passed**；编辑器启动 `status=关闭`；start 后子进程 `editor.exe --pet`、stop 后退出；右键菜单冻结版直接起编辑器 |
| 2026-11-02 | py -3 tools/ui_walkthrough.py | **43/43 步通过，0 失败断言**：真实键鼠事件走完标题→设置→存档→剧情→选项→CG→画廊→菜单→终幕；产物 `screenshots/walkthrough/report.html` + `walkthrough.gif` |
| 2026-11-02 | py -3 tools/build_release_zip.py --version v1.0.0-rc5 --verify + tools/verify_release_clean.ps1 | **35.2MB / 283 文件**（SHA256 `78A9013F…BD52DD`），editor.exe 8.1MB；解压冒烟 exit 0；净环境空 AppData 真实窗口 `[MYONL 编辑器]` PASS |
| 2026-11-02 | py -3 -m pytest -q | **998 passed + 1 skipped**（全交互走查修复：首句立即出现、画廊返回、快捷栏可点、10 格存档、左右键） |
| 2026-11-02 | powershell -File tools/verify_release_clean.ps1 | **PASS**：剥离 Python 环境 + 空 AppData 后，`editor.exe -h` / `--demo-worker` exit 0，真实窗口成功打开 `[MYONL 编辑器]`；WebView2 present |
| 2026-11-02 | py -3 tools/build_release_zip.py --version v1.0.0-rc4 --verify | **35.2MB / 283 文件**；editor.exe 8.1MB，解压后 `-h` 与 demo worker 冒烟均 exit 0 |
| 2026-11-02 | py -3 pack.py games/教程示例 | **22.76MB**，产物 `dist/教程示例/教程示例.exe`，可执行文件+资源+存档位齐全 |
| 2026-11-02 | py -3 -m pytest -q | **992 passed + 1 skipped**（三批修复：dump/场景保存、UI 设计类型、改键/选项卡死/jump、10 槽+F5 快存、SKIP/i18n/教程/标题页/data_dir） |
| 2026-11-02 | py -3 -m pytest -q | **970 passed + 1 skipped**（括号台词/NVL、极简空包、打包补白底、场景图层面板、右键菜单、BOM 修复） |
| 2026-11-02 | py -3 tools/status.py --write | 收集 971 / 覆盖率 81.95% / pyright 157（基线 165） |
| 2026-11-01 | py -3 tools/build_release_zip.py --version v1.0.0-rc4 --verify | **35.2MB / 283 文件**；校验内置素材模板随包 + 解压 editor.exe 冒烟通过 |
| 2026-11-01 | py -3 -m pytest -q | **962 passed + 1 skipped**（内置素材进引擎/空包、删素材可开局、标题不重叠、旁白前缀） |
| 2026-11-01 | powershell -File tools/check_types.ps1 | 棘轮通过：无新增类型错误（editor.py 若干项存量下降） |
| 2026-11-01 | py -3 -m pytest -q | **948 passed + 1 skipped**（U10 键位/V3 章节分组/V4 角色库/E4 任务进度/1080p 预设/桌宠记忆/素材热重载） |
| 2026-11-01 | py -3 tools/build_release_zip.py --verify | 34.8MB / **260 文件**；解压 editor.exe 冒烟通过 |
| 2026-11-01 | py -3 -m pytest -q | **931 passed + 1 skipped**（U7/U9/U10/U12 + V1 新增 20 条守护） |
| 2026-11-01 | powershell -File tools/preflight.ps1 -Fast | exit 0（148.4s；899 passed / pyright 159 / STATUS 刷新） |
| 2026-11-01 | py -3 -m pytest -q | **910 passed + 1 skipped**（含 E9 档位 5 条守护） |
| 2026-11-01 | powershell -File tools/check_types.ps1 | 通过：159 错误 / 基线 165 |
| 2026-11-01 | py -3 tools/verify_editor_trae_ui.py | 通过 22/22（新增档位下拉无回归） |
| 2026-11-01 | Playwright 档位实测 | L1 隐藏检查器/富文本/语言下拉、菜单无 JSON；L3 出视图页签与 JSON 菜单；刷新后记住选择 |
| 2026-11-01 | py -3 -m pytest -q | 797 passed + 1 skipped + 1 xfailed（799 收集） |
| 2026-11-01 | powershell -File tools/preflight.ps1 -Fast | exit 0（61.8s） |
| 2026-11-01 | py -3 tools/build_release_zip.py --verify | **34.7MB / 254 文件**（重打入内嵌教程后）；解压后 editor.exe 冒烟通过 |
| 2026-11-01 | py -3 -m pytest -q | 837 收集 / 835 passed + 1 skipped + 1 xfailed |
| 2026-11-01 | py -3 -m engine.capability | 本机 high：15.3GB / 16 核 / RTX 4060 / 磁盘 37GB |
| 2026-11-01 | py -3 -m pytest -q | **881 收集 / 879 passed + 1 skipped + 1 xfailed**（A1~A3 + C1/C2 集成后） |
| 2026-11-01 | py -3 tools/build_release_zip.py --version v1.0.0-rc3 --verify | **34.7MB / 254 文件**；解压 editor.exe -h → exit 0；--demo-worker → exit 0 |
| 2026-11-01 | py -3 -m pytest tests -q | **900 passed + 1 skipped**（1 failed 为另一会话 WIP 的 test_trae_phase3_frontend_structure，不在本批提交内） |
| 2026-11-01 | powershell -File tools/check_types.ps1 | 通过：159 错误 / 基线 165 |
| 2026-11-01 | py -3 tools/verify_editor_trae_ui.py | 通过 22/22 |
| 2026-11-01 | PyInstaller + build_release_zip --verify | editor.exe 重打 + 冒烟 exit 0；zip 34.7MB/254 文件，解压冒烟通过（含 A2 问题面板/ Dock / 教程） |
| 2026-10-31 | powershell -File tools/check_types.ps1 | 棘轮通过（623 = 基线 623） |
| 2026-11-01 | py -3 -m pytest -q | **887 passed + 1 skipped + 1 xfailed**（D2/D3 + B2-UI + 渲染层类型声明后） |
| 2026-11-01 | powershell -File tools/preflight.ps1 -Fast | exit 0（73.0s；pyright 159 / 基线 165） |
| 2026-11-01 | PyInstaller + smoke_editor_exe | editor.exe 重打 8.4MB；两检查 exit 0 |
| 2026-11-01 | py -3 tools/build_release_zip.py --verify | **MYONL引擎-v1.0.0-rc2.zip 34.7MB / 254 文件**，解压后 editor.exe 冒烟 exit 0 |
| 2026-11-01 | powershell -File tools/check_coverage.ps1 | exit 0（engine **83.03%**，阈值 80%，基线 81.09%） |
| 2026-10-31 | powershell -File tools/check_coverage.ps1 | exit 0（engine 82.64%，阈值 80%） |
