# MYONL 引擎

> 用几行 `.gal` 脚本写出一部能玩的视觉小说：分支、存档、配音、CG、打包，全部开箱即用。
> **这是一个引擎工具（给创作者用），不是游戏作品**；仓库里的示例游戏只是可改的小样板。
> Windows · Python 3.13 · pygame-ce · MIT

**当前版本：`v1.0.0-rc6`** · 完全离线运行 · Windows 桌面 · MIT 开源；运行时仅依赖 Python 与 pygame-ce。

## 我该看哪一节？

- **只想做游戏**：使用随引擎发布的 Windows 发行包（无需安装 Python）；发行包内自带「五步上手」说明。
- **读源码 / 改引擎 / 参与开发**：见下面的「源码开发」一节（需要 Python 3.13）。

---

## 是什么

MYONL 是一个自研的 Galgame / 视觉小说引擎。作者写 `script.gal`，引擎负责解析、执行、渲染、存档，
并打包成玩家双击就能玩的独立应用（不装 Python、不做任何配置）。

```gal
@bg bg_天台
@music bgm_night

@label start
@show 林晚 微笑
@[林晚] 你又迟到了两分钟。      # 方括号 = 角色台词（不登记也能用）
@ 晚风把她的发梢吹起。          # @ + 空格 = 旁白
@choice:
  > 一起看日落 -> 结局_看日落
  > 说出那个约定 -> 结局_约定

@label 结局_看日落
@[[林晚]] 那年夏天，风很长。    # 双括号 = 整屏独白（NVL）
@end
```

## 特性

- **DSL**：24 条指令（含 `@bg/@music/@show/@anim/@fg/@cg/@camera/@transition/@chapter/@choice/@set/@if/@jump/@voice/@video/@include` 等），中文直写
- **演出**：打字机、22 条缓动曲线、镜头 pan/zoom/shake、三种转场、动画立绘、帧序列视频背景、配音
- **玩家外壳**：标题/菜单/存档 10 位/回看/设置/画廊/快捷栏，标准版主题（`config.json` 可换肤）+ 像素化 UI
- **开发体验**：Web 编辑器（三视图 + 实时预览）、语法检查、一键打包、**剧本/配置热重载**（`--hot-reload`）
- **平台**：逻辑画布可配（1280×720 / 1920×1080 等比缩放）、素材按需加载 + LRU 缓存（大素材库不会一次性占满内存）

### 快速开始（Windows）

```powershell
pip install -r requirements.txt

# 1) 跑自带示例（三幕小故事：走廊 → 天台 → 房间）
py -3 -m engine.demo games/标准示例/script.gal --assets games/标准示例

# 2) 新建一个自己的游戏（默认教学骨架；编辑器里新建则是极简 hello world）
py -3 -m engine.cli new 我的第一个游戏

# 3) 打开 Web 编辑器（浏览器 http://127.0.0.1:8000）
py -3 -m engine.editor --project games/我的第一个游戏

# 4) 打包成玩家双击即玩的目录（dist/<游戏名>/）
py -3 pack.py games/我的第一个游戏
```

写剧本时建议开热重载：

```powershell
py -3 -m engine.demo games/我的第一个游戏/script.gal --assets games/我的第一个游戏 --hot-reload
```

改 `.gal` → 500ms 内从当前场景重播；改 `config.json` → 字号/颜色/对话框即时生效。

## 开发

```powershell
py -3 -m pytest -q                    # 全量测试（约 90s）
py -3 -m pytest -q -m "not slow"      # 日常快跑（约 50s）
powershell -File tools/preflight.ps1 -Fast   # 一键门禁：pytest + pyright 等检查
```

- 测试分层：`unit` / `ui` / `slow` / `integration`；覆盖率门禁 80%（`tools/check_coverage.ps1`）
- 类型检查棘轮：`tools/check_types.ps1`（只拦新增，不许新增类型债）

## 目录

| 目录 | 内容 |
|---|---|
| `engine/` | 引擎核心：解析、运行时、渲染（10 个 render 模块）、存档、编辑器后端、打包 |
| `editor/` | Web 编辑器前端（HTML/CSS/JS，无构建） |
| `games/` | 示例工程（标准示例 / 教程示例 / 新游戏 / 新游戏模板） |
| `tests/` | pytest 无头测试套件（unit / ui / integration；`-m "not slow"` 日常快跑） |
| `tools/` | 门禁与工具脚本（coverage / pyright / 打包验证等） |
| `docs/` | 上手 / 产品说明 / 引擎规格 / 开发者与打包指南 / 贡献说明 |

## 文档

- 快速上手：[docs/快速上手.md](docs/快速上手.md)
- 产品说明：[docs/产品说明书.md](docs/产品说明书.md)
- 引擎规格（指令全集）：[docs/engine_spec.md](docs/engine_spec.md)
- 开发者指南：[docs/开发者使用指南.md](docs/开发者使用指南.md)
- 打包指南：[docs/打包使用指南.md](docs/打包使用指南.md)
- 素材导入指南：[docs/素材导入指南.md](docs/素材导入指南.md)
- 贡献说明：[docs/贡献指南.md](docs/贡献指南.md)

## 许可

MIT（见 [LICENSE](LICENSE)）。第三方组件与素材许可见 [NOTICE](NOTICE)。

> 本产品完全离线运行，不依赖任何在线服务。
