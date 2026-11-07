# STATUS

> **唯一权威状态页**：现在在哪、下一步做什么、什么被卡住，只看这一页。
> 历史计划与变更说明只保留在 git 历史（原 docs/archive 已于 2026-11-01 删除）。
> 维护规则：人只改上面的四行；自动数字区由 py -3 tools/status.py --write 生成。

- **版本**：v1.0.0-rc7（Windows 离线引擎；rc6 后交互与失败态收口：原子保存、启动/热重载错误可定位、编辑器对齐与 Dock 缩放、存档/读档/打包失败态）——**已发布**（GitHub Release prerelease，附件 `MYONL-v1.0.0-rc7-windows.zip` 46.43MB）
- **在做**：**rc7 已上线，只剩唯一门槛**——tag `v1.0.0-rc7` 已推送 GitHub（tag 对象 `1079b1e` → 提交 `30bd8b6`），Release 已发布（prerelease，附件 `MYONL-v1.0.0-rc7-windows.zip` 46.43MB，创建于 2026-11-05 07:58 CST）；CI `tests` / `ui-walkthrough` 在 HEAD `8fc3e53` 全绿（2026-11-06 最近一次 ui-walkthrough success）。后续 = 干净 Windows 人工抽测（2026-11-07 发行包链路复验再次 PASS）。
- **质量门槛**：干净 Windows（无 Python 环境）下可做出并打包一个可玩 demo；自动化等价验证（改→存→跑→打包→成品）已通过，人工抽测待补。
- **本机限制（2026-11-07 实测）**：本机为 Windows 10 家庭版，无 Windows Sandbox（需专业版）；且 `py.exe` 位于 `C:\WINDOWS`，对所有本地用户可见——**新建本地用户也无法等价"无 Python"环境**。该格必须在外部机器 / 云桌面完成，或由用户拍板以自动化等价验证替代。
- **后续待办**：① 干净 Windows 环境人工抽测 ② 收集早期使用者反馈（CI 已接入 GitHub Actions · windows-latest） ③ 已知限制：4000 行级文档单键约 42ms（textarea 整篇重排，微优化收益 <1%，需换编辑器架构）。

<!-- auto:begin -->
<!-- 自动数字区：由 tools/status.py 写入，勿手改 -->
- 测试：pytest 无头套件（unit / ui / integration；`-m "not slow"` 日常快跑）
- 覆盖率门禁：`engine/` ≥ 80%
- 类型检查：pyright 棘轮（只拦新增错误，不新增类型债）
- 打包质量门禁：`tools/verify_release_flow.py` 验证改→存→跑→打包→成品链路
<!-- auto:end -->

## 冻结令

M1 期间，engine/ 只接受「阻塞陌生人上手」的 P0 修复；功能与重构一律进 BACKLOG。示例游戏只作可改样板，不做完整作品。

## 最近验证

| 日期 | 命令 | 结果 |
|---|---|---|
| 2026-11-07 | py -3 tools/verify_release_flow.py --zip dist/release/MYONL引擎-v1.0.0-rc7.zip | **PASS / exit 0**：解压 408 文件 → 无 Python + 空 AppData 启动编辑器窗口 `[MYONL 编辑器]` · API 53449 → 改一句 → 语法检查 → 运行（`[教程示例]` 窗口）→ 打包（22.9MB，3.1s，走内置玩家模板）→ 成品窗口 `[教程示例]` |
| 2026-11-07 | py -3 -m pytest -q -m "not slow" | **1005 passed + 1 skipped**（新增 `tests/test_release_zip_manifest.py` 守护发行包清单） |
| 2026-11-07 | py -3 tools/build_release_zip.py --version v1.0.0-rc7 --out dist/release/_candidate/… --verify | **409 文件 / 46.43MB**，冒烟两项 exit 0；与旧包diff 只多 `tools/win_env_check.bat`（SHA256 `AAAEF00B…9CEA2`）。**GitHub Release 附件仍是旧包（408 文件，缺该脚本），替换待用户拍板** |
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
