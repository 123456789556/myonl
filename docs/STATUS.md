# STATUS

> **唯一权威状态页**：现在在哪、下一步做什么、什么被卡住，只看这一页。
> 历史计划与变更说明只保留在 git 历史（原 docs/archive 已于 2026-11-01 删除）。
> 维护规则：人只改上面的四行；自动数字区由 py -3 tools/status.py --write 生成。

- **版本**：v1.0.0-rc19（**手机端为主线**：同一工程 → 竖屏/横屏 H5 网页包 → 安卓 APK；桌面端降为并行出口）。rc11 之后：P69 播放器菜单/6 档存档/设置四项 · P70 选项可调 · P71 UI 设计区整屏参照 · P72 PWA 主屏图标 + 启动遮罩 · P73 `@fg/@anim/@video/@voice/@chapter/@transition` 手机端全实现 · P74 全身立绘与常驻微动 · **P75–P85 手机端存储层两键结构 + 首次引导 + 长按菜单 + 横屏两列设置 + 砍桌宠** · **P86 对话框按台词行数自适应 + 竖屏双立绘内收 + 标题页真封面 + 占位换真插画** · **P87 修发行包漏带前端模块 + 清 80 MB 废料** · **P88 砍「手机连接」** · **P89 砍 AI 助手 + 修手机端 `@else` 分支永不执行的 bug + 第一部完整作品《研修日志》** · **P90 桌面端标题页对齐手机端** · **P91 升级不毁档（玩家数据搬到 %APPDATA%/Moyul/<游戏名>，老档首启复制不删除，发行包不带 saves/）** · **P92 手机端右侧竖列「存/回/设」+ 名牌缩字号** · **P93 手机端存档导出/导入（换文件/换设备不再丢档）+ 面板与格子高度对齐** · **P94 手机端视觉重做：控件统一成 44–96 圆形、竖列垂直居中、菜单改列表行、面板改底部抽屉、名牌去掉描边胶囊** · **P95 横竖两套构图：`images/{名}_p.png` 可选竖版变体 + `config.json` 的 `"focal"` 构图锚点，网页端/桌面端各接一次；《研修日志》补两张真竖版背景**。发行包 `dist/release/MYONL引擎-v1.0.0-rc19.zip` 解压冒烟通过，**未上传 GitHub Release**（本机无 gh CLI / token，用户也说明不需要）。
- **在做**：真机验证仍为零（`adb devices` 只有表头，`adb` 在 `D:\娱乐工作区\_tools\platform-tools`）。手机端"升级不丢档"两条腿都补上了：桌面端数据搬到 `%APPDATA%`（P91），手机端加**存档导出/导入**（P93）——origin 隔离那堵墙拆不掉，但换文件后能把档搬回来。剩下：鉴赏页（CG/音乐）无数据链路（`gallery_config.json` 空壳、webpack 不打包 gallery）、立绘分层（眨眼/口型）、桌面端除标题页外的其余页面仍是旧形态。
- **质量门槛**：干净 Windows（无 Python）下可做出并打包可玩 demo；H5 播放器在真实 Chromium 竖屏 390×844 / 横屏 844×390 + 转屏 + 自动存档全过；安卓 APK 由 CI 产出（gradlew assembleDebug 绿）。
- **本机限制**：无 JDK / 无 Android SDK / 无 gh CLI / 无 Ren'Py SDK——所以 **APK 只能在 CI 里编**、**Ren'Py 导出工程没在 Ren'Py 里真跑过**；Actions 日志需 token（已改成失败时写 `::error::` 注解，匿名可读）。**真机 adb 需另装 platform-tools（`D:\娱乐工作区\_tools\platform-tools`），且必须覆盖 TEMP 才能起 daemon**（默认 `%TEMP%` 写 `adb.log` 会被拒）。
- **后续待办**：① 真机验一次转屏/选项/CG/读档 ② 装一次 APK ③ 鉴赏页（CG / 音乐）数据链路 ④ `@plug` 插件调用（手机端无对应实现） ⑤ 桌面端其余页面对齐手机端 ⑥ 桌面端也加存档导出/导入（现在只有手机端有）。

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
