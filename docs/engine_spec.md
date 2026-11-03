# MYONL 引擎规格书（engine_spec.md）

> 本文档是引擎的架构定稿 + AI 操作手册。任何人/AI 控制引擎前，先读本文档。
> **版本**：v1.1（2026-10-29；P33 增补：`@bg fadein=`、config `title_music` 标题 BGM、画廊 `require` 解锁门控）
> **技术栈**：Python 3.7+（发行包用 3.13 冻结）+ pygame-ce 2.3–2.5（按 Python 版本自动解析）/ PyInstaller，零第三方依赖除 pygame-ce。
> **平台**：Windows 10/11 唯一目标平台（跨平台支持已砍）。

---

## 0. Windows-only 边界声明

本引擎自 v1.0 起**只支持 Windows 打包与运行**：
- 打包产物：PyInstaller 单 `.exe`（`python -m pack.py games/月光漫步` → 32MB）
- 放弃 Android / iOS / Web / Linux / macOS 打包
- 放弃 SDL_IME 多输入法（Windows IME 通过 SDL_TEXTINPUT 够用）
- 保留游戏手柄映射（SDL 原生支持）和触摸板（SDL_MOUSE）

---

## 1. 架构与模块边界

```
剧本.gal  (UTF-8 可带 BOM，UTF-8-sig 兼容)
   │
   ▼
engine/parser.py（解析）── 24 条 DSL 指令白名单校验 + GalSyntaxError
   │
   ▼ list[dict] 指令列表
engine/runtime.py（解释器 / 状态机，维护 GameState）
   │
   ▼ dict 快照（含持久化展示层状态：fg / camera_zoom / anim_final / pending_wait）
engine/renderer.py（无状态渲染，读 snapshot，展示进度存内部 Timeline 缓存）
   │
   ▼ pygame.Surface 1280×720 画布 → letterbox 等比缩放
engine/ui.py（玩家侧 UI 状态机：title / playing / menu / slots / settings / backlog / gallery）
engine/save.py（GameState ←→ JSON 存档 + 缩略图 + 全局 persistent.json）
engine/data.py（settings.json / gallery_config.json 原子写 + 中文字体自动查找）
engine/timeline.py（统一时间轴调度：镜头 / 转场 / 立绘补间 / 停留，均不进 GameState）
```

**模块依赖单向**：`parser → runtime → demo → renderer / ui`；`save / data / timeline` 依赖 runtime 或 renderer；**禁止反向 import**（renderer/ui 不得 import runtime）。
**数据流铁律**：剧本与引擎代码分离；所有脚本状态存于 GameState；渲染器只读 snapshot，**不反向改状态**；展示层瞬时动画（shake 震动、补间过程）只在 renderer 内部 Timeline，不进存档。

### 1.1 GameState 完整字段（v1.0）

```python
{
    "script": str,                 # 剧本绝对路径
    "stack": [[list_id, index]],   # 栈帧：当前在哪个指令列表的第几条
    "bg": str | None,              # 当前背景图名
    "music": str | None,           # 当前背景音乐名
    "video": {"name": str, "fps": int} | None,  # 帧序列视频背景
    "sprites": [{"char": str, "expr": str, "anim": str, "pos": str | None,
                 "scale": float | None, "z": int | None, "layers": dict | None}],
    "vars": dict,                  # 脚本变量
    "characters": {name: {"color": str}},  # 角色注册表
    "history": [{"char": str | None, "text": str}],  # 已播对话
    "pending_choice": {"options": [{"text": str, "available": bool}], "cursor": int} | None,
    "pending_wait": {"seconds": float} | None,  # @wait 暂停剩余秒数
    "finished": bool,
    "gallery": list[str],          # 已解锁 CG 名（进存档）
    # ---- 持久化展示层状态（读档后 renderer 复原画面）----
    "fg": {"name": str, "x": int, "y": int, "alpha": float} | None,
    "camera_zoom": float,          # zoom 最终缩放（pan 偏移 runtime 算不出，不持久化）
    "anim_final": {char: {param: float}},  # @anim to 值（最终态，非补间过程）
}
```

---

## 2. DSL 指令表（24 条对外指令，v1.0）

### 2.1 对话与角色（2 条）

| 指令 | 语法 | 示例 | 说明 |
|---|---|---|---|
| `@character` | `@character 名字 #RRGGBB [kind=布局]` | `@character eileen #c8ffc8` / `@character 旁白 #ffffff kind=nvl` | 注册角色 + 对话颜色；可追加 `kind=` 绑定对话框布局（缺省 default，见 config.json `dialogue` 段）；只影响颜色/布局，不写也能用括号台词 |
| 对话 | `@[角色] 文本` / `@ 文本` / `@` 换行 / `@[[…]]` | `@[林晚] 你好。` / `@ hello world!` / `@[[林晚]] 那年夏天……` | **方括号 = 角色台词**（无需登记，括号不显示；`@[林晚]` 后换行写台词也行）；`@[[角色]] 文本` = 整屏独白（NVL），`@[[整段文字]]` = 整屏旁白；`@` 后空格或单独一行 + 下一行 = 旁白；旧的 `@ 已登记角色 文本` 写法继续有效 |

### 2.2 资源加载（4 条）

| 指令 | 语法 | 示例 | 说明 |
|---|---|---|---|
| `@bg` | `@bg 图片名 [fadein=秒]` | `@bg classroom` / `@bg beach fadein=1.5` | 背景切换；`images/<图片名>.png` 或 `.webp`；`fadein=` 本次切换黑场淡入时长（缺省 0.3s，一次性，不进存档） |
| `@music` | `@music 音乐名 [fadein=秒] [fadeout=秒]` | `@music op fadein=2.0` | 背景音乐；`audio/<音乐名>.ogg/.wav/.mp3` |
| `@sfx` | `@sfx 音效名` | `@sfx click` | 一次性音效 |
| `@voice` | `@voice 配音文件名` | `@voice hello_eileen` | 对话附带配音 |

### 2.3 立绘系统（3 条）

| 指令 | 语法 | 示例 | 说明 |
|---|---|---|---|
| `@show` | `@show 角色ID 表情 [anim=呼吸\|walk] [pos=左\|中\|右] [scale=0.5~2.0] [z=整数] [x=像素] [y=像素] [部位:素材]` | `@show 双叶 身体:默认 表情:微笑 pos=中 z=1` | 分层立绘核心语法；`anim` 默认"呼吸"；`pos` 默认中；`x`/`y` 是相对默认位置的像素偏移（场景视图拖拽用）；分层立绘逐个部位查素材 |
| `@hide` | `@hide 角色ID` | `@hide 双叶` | 撤下立绘（同时清掉 anim_final） |
| `@anim` | `@anim 角色ID 参数=起始~结束\|目标 秒数 [ease=linear\|ease_in\|ease_out]` | `@anim 双叶 x=-100~0 0.8 ease=ease_out` | 立绘参数补间：x / y / alpha（0~1） / scale（0.5~2.0） |

### 2.4 视觉演出（6 条）

| 指令 | 语法 | 示例 | 说明 |
|---|---|---|---|
| `@fg` | `@fg 前景名 [x=像素] [y=像素] [alpha=0~1]` / `@fg 无` | `@fg rain alpha=0.6` / `@fg 无` | 前景层贴图（画在立绘之上、UI 之下） |
| `@cg` | `@cg CG名称` | `@cg cg_end1` | 全屏 CG 展示（占满画面、屏蔽对话框，进 gallery 解锁） |
| `@camera` | `@camera pan 左\|右\|上\|下 秒数` / `zoom 起始 结束` / `shake 秒数 幅度` / `reset 秒数` | `@camera zoom 1.0 1.3` | 镜头控制；`zoom` 最终值进存档（持久化） |
| `@transition` | `@transition dissolve 秒数` / `wipe 左\|右\|上\|下 秒数` / `slide 方向 秒数` | `@transition dissolve 0.3` | 下一次背景切换时触发转场 |
| `@wait` | `@wait 秒数\|毫秒数`（无单位默认秒） | `@wait 1.5` / `@wait 500ms` | 暂停推进到倒计时完（读档后续等恢复） |
| `@chapter` | `@chapter 章节标题 [secs=秒]` | `@chapter 第一章 雨夜` / `@chapter 幕间 secs=0.8` | 章节/幕间演出卡：黑场 + 标题渐显渐隐，播完自动恢复（时长缺省取 `pacing.chapter_fade`，同时暂停推进） |

### 2.5 流程控制（9 条）

| 指令 | 语法 | 示例 | 说明 |
|---|---|---|---|
| `@label` | `@label 标签名` | `@label scene1_start` | 跳转目标标签 |
| `@jump` | `@jump 标签名` | `@jump scene1_start` | 跳到标签位置继续执行 |
| `@end` | `@end` | `@end` | 结束剧本播放，`state["finished"] = True` |
| `@set` | `@set 变量 += 数值` / `-=` / `=` / `@set 变量 = 表达式` / `@set 变量 = "字符串"` | `@set 好感 += 1` / `@set 好感 = 好感 + 2` / `@set 名字 = "双叶"` | 脚本变量操作；表达式支持变量、整数/小数、字符串字面量与 + 拼接、四则 +-*/、括号、比较、and/or/not |
| `@if` | `@if 条件: <缩进块>` / `@elif 条件:` / `@else:` | `@if 好感 > 50:` | 条件分支；支持 `and`/`or`/`not`/比较 |
| `@choice:` | `@choice:` + 缩进选项列表 | 见下方 | 暂停推进等待玩家选择 |
| `@video` | `@video 视频名 [fps=整数]` | `@video op fps=24` | 帧序列视频背景 |
| `@plug:` | `@plug:插件指令名 [参数...]` | `@plug:shake 1.0` | 插件入口（engine/action.py 注册的 action 走这里） |
| `@include` | `@include 相对路径.gal` | `@include 章节/第一章.gal` | 顶层内联展开另一个剧本；路径相对当前文件目录，禁止循环引用 |

### 2.6 @choice: 缩进格式

```
@choice:
  > 你走向便利店。 -> 结局A
  > 你转身回家。 -> 结局B

@label 结局A
@ 你推开了便利店的门。
@end
```

`@choice:` 单独一行；下一行起每条选项写成 `> 文本 -> 标签`，条件可写在文本后（`> 文本: 好感 >= 3 -> 标签`）。下一行不是 `>` 开头即表示选项结束。

### 2.7 台词三种写法（重要）

| 写法 | 效果 | 示例 |
|---|---|---|
| `@[角色] 文本` | 普通对话框台词，**不需要** `@character` 登记 | `@[林晚] 你好。` |
| `@[角色]` + 换行 | 下一行整行作为台词 | `@[林晚]` / 下一行 `你好。` |
| `@[[角色]] 文本` | 整屏独白（NVL 布局） | `@[[林晚]] 那年夏天，风很长。` |
| `@[[整段文字]]` | 整屏旁白（无名字） | `@[[我忽然想起那年夏天。]]` |
| `@ 文本` | 旁白 | `@ 注意：请勿靠近。` |
| `@` + 换行 | 下一行整行作为旁白 | `@` / 下一行 `hello world!` |

边界规则：
- 方括号里允许**配平嵌套**：`@[林晚[老师]] 你好。` → 角色名「林晚[老师]」；单括号后跟换行也表示台词。
- 双括号 `[[...]]` 里不能再出现 `[` 或 `]`。
- **冒号没有特殊含义**：`@ 注意：请勿靠近` 是旁白，不会把「注意」当人名。
- 旧写法 `@ 已登记角色 文本` 继续有效；名字未登记时整行按旁白处理。
- 台词插值：`${变量}` 替换为变量当前值（未定义时打印中文警告并置空）。旧写法 `{变量}` 仍兼容，但只在变量**已定义**且名字不是 `b` / `i` / `color` / `size` 时替换——富文本标记（`{b}…{/b}` 等）不会被插值层吃掉；未定义的 `{…}` 原样保留。

---

## 3. 错误处理

| 错误类型 | 抛异常 | 含中文提示 + 1 起始行号 |
|---|---|---|
| 指令不存在 | `GalSyntaxError` | ✅ |
| 参数缺失 / 类型错 | `GalSyntaxError` | ✅ |
| 标签重复 / 未定义 | `GalSyntaxError` | ✅ |
| 角色重复定义 | `GalSyntaxError` | ✅ |
| 表达式非法（注入风险） | `GalSyntaxError` 包 `ExprError` | ✅（禁止 `__import__` / `open` / `subprocess` / 属性访问） |
| @if / @choice 缩进错误 | `GalSyntaxError` | ✅ |
| 视频不存在 / 音频不存在 | `RuntimeError` + `stderr` 警告 | ✅（降级静音 / 占位） |
| 存档 JSON 损坏 | `SaveError` | ✅（不崩溃） |
| 非法槽位（0 / 11 / -1 / 路径穿越） | `SaveError` | ✅ |
| 死循环（@jump 超 5000 次） | `RuntimeError` + 中文说明 | ✅ |

---

## 4. 存档 schema

存档文件：`<assets_root>/saves/slot_N.json`（N = "quick" 或 1~10）。缩略图：`<assets_root>/saves/thumb_N.png`。卡片信息：JSON 顶层 `thumbnail_path`（只存文件名）、`chapter_name`、`last_text`、`label`（锚点最近 label 名）。全局解锁：`<assets_root>/saves/persistent.json`（跨存档持久）。

**线程安全**：settings.json 用 `os.replace` 原子替换；存档 JSON 先写临时文件再 replace。

---

## 5. 与主流 gal 引擎对标（2026-10-29 实拍）

| 维度 | MYONL v1.0 | Ren'Py 8.x | Unity+Fungus | 备注 |
|---|---|---|---|---|
| **核心架构** | 24 条 @指令 DSL（纯 Python 336KB） | Python + 200+ statement DSL（3MB + 40 Cython） | C# + Inspector 节点 | MYONL DSL 比 Ren'Py 更窄、更像 gal 引擎 |
| **立绘分层** | ✅ 部位:素材 z 序补间 | ✅ LayeredImage + 动画 | ⚠️ 原生无 | **MYONL 的 @anim 秒/毫秒/ease 三语法是独有的** |
| **镜头/转场** | ✅ 统一 Timeline（zoom 持久化） | ✅ 40+ 种 + shader | ⚠️ 插件 | MYONL 架构更干净（事件不四散） |
| **对话框自定义** | ⚠️ config.json `dialogue` 布局（default 底部条 / nvl 整屏）+ `@character kind=` 绑定 | ✅ 完整样式系统 + Character kind | ✅ Inspector | 已从"纯硬编码"起步：几何/底色/边宽可配；气泡/侧图等布局后续扩展 |
| **输入变量** | ❌ | ✅ `$ renpy.input()` | ✅ 节点 | 即将 P1-3 |
| **Python 嵌入** | ❌ | ✅ `$ Python` 任意执行 + exec hook | ✅ C# | 即将 P1-2 |
| **action 扩展** | ❌（有 @plug: 入口无注册框架） | ✅ renpy.register_action | ✅ C# 接口 | 即将 P1-1 |
| **画廊系统** | ✅ 固定格 + 解锁条件（gallery_config.json，`require` 支持多结局收集门控，P33） | ✅ 完整（DSL 定义） | ✅ 插件 | |
| **翻译系统** | ❌ | ✅ 30+ 语言框架 | ⚠️ 插件 | 即将 P1-5 |
| **跨平台** | ❌ Windows-only | ✅ 全平台 | ✅ 全平台 | MYONL 已砍跨平台 |
| **打包体积** | 🆕 **32MB** | ~100MB+ | 500MB+ | **MYONL 护城河** |
| **零底层依赖** | 🆕 是 | 否（Cython/SDL 定制） | 否 | **第二个护城河** |
| **测试覆盖** | 486 pytest passed | 估计 2000+（未见公开数据） | — | |
| **编辑器 / Launcher** | ❌（python -m engine.cli 命令行） | ✅ 完整（项目创建/打包/主题） | ✅ Unity Editor | 即将 P0-2 |

**Ren'Py 值得直接抄/改的模块**（纯 Python，MIT 许可，可以引入）：
- `renpy/common/00action_*.rpy` — action 注册框架（最容易迁移，全纯 Python）
- `renpy/common/00translation.rpy` — 翻译系统框架
- `renpy/common/00gallery.rpy` — 画廊 DSL
- `renpy/common/00nvl_mode.rpy` — 旁白整屏模式
- `renpy/common/00inputvalues.rpy` — 输入变量（参考语法）

**不值得抄**（MYONL 用 pygame-ce 包 SDL 层）：
- 所有 `.pyx` Cython 渲染代码
- Launcher、打包器、移动平台支持
- 跨平台兼容层

---

## 6. Python API 参考

### `engine.parser`

```python
parse_text(text: str, source: str = "<string>") -> list[dict]
parse_file(path) -> list[dict]
dump_text(instructions: list[dict]) -> str
dumps(instructions) -> str
loads(json_str) -> list[dict]
# 异常：GalSyntaxError（.line / .message / .source）
```

### `engine.runtime`

```python
Runtime()
rt.load(script_path)                          # 加载剧本
rt.snapshot() -> dict                         # 当前 GameState（只读快照）
rt.step() -> dict                             # 执行下一条指令 → 事件 dict
rt.choose(index)                              # 选择当前 pending_choice 的第 index 项
rt.save(slot) -> str                          # 存档（slot: "quick" | 1~10）
rt.load_save(slot) -> dict                    # 读档 → GameState
rt.pending_wait_seconds() -> float            # @wait 剩余秒数（无等待返回 0.0）
rt.advance_wait(dt_seconds)                   # 倒计时推进（demo 主循环每帧调）
rt.set_var(key, value)                        # 脚本变量 API（给 action 用）
rt.seen_sprites() -> list[str]                # 已见过立绘（画廊解锁）
```

### `engine.renderer`

```python
Renderer(size=(1280, 720), assets_root=".")
ren.render(state: dict, ui_view: dict | None)  # 画一帧；自动从 state 恢复持久化状态
ren.handle_input() -> dict                     # 返回 {"action": "...", "hit": {...} | None}
ren.play_anim(char, param, from_value, to_value, secs, easing="linear")
ren.play_fg(name, x=0, y=0, alpha=1.0)
ren.play_camera(kind, *args)                  # pan/zoom/shake/reset
ren.set_splash(bool)                          # 序幕模式
ren.trigger_ending_fade()                     # 结尾淡出
ren.reveal_all()                              # 打字机立即完成
ren.save_thumbnail(path)                      # 存档缩略图
ren._last_dt_ms -> int                        # 上一帧 dt（ms），主循环用来倒计时 @wait
ren.close()                                   # 释放资源
```

### `engine.save`

```python
save(state, slot, anchor_stack=None, *, label=None, last_text=None)
load(slot) -> dict                            # 存档 JSON 顶层字典（state + thumbnail_path 等）
list_slots() -> list[dict]                    # [{slot, label, chapter_name, last_text, size, modified}]
delete_slot(slot)
gallery_union(list_a) -> list[str]            # 全局解锁 ∪ 当前档解锁
load_persistent() -> dict                     # {"gallery": [...]}
saves_dir() -> Path
set_saves_dir(path) -> Path                   # demo 启动时指向 assets_root/saves
reset_saves_dir()                             # 恢复默认 "saves"
slot_path(slot) -> Path                       # 存档文件路径（会校验槽位）
# 异常：SaveError
```

### `engine.ui`

```python
UI()
ui.settings_path -> str
ui.mode -> str                                # title / playing / menu / slots / settings / backlog / gallery
ui.refresh()                                  # 刷新存档列表 + settings
ui.set_history(list[dict])                    # 注入 GameState.history
ui.set_gallery(list[str], list[str])          # 注入已解锁 CG + 已见过立绘
ui.set_gallery_config(list[dict])             # gallery_config.json 解析结果
ui.set_settings(dict)                         # demo 落盘后回写
ui.handle(key: str) -> dict | None            # 消费一个统一键名
ui.click(hit: dict) -> dict | None            # 鼠标点击分派（kind=key/item/gallery_tab）
ui.view(now_ms: int | None) -> dict           # 导出绘制数据
next_value(key, current) -> int | float       # 设置项取下一档（text_speed 三档循环）
# 设置页分组（按 SETTINGS_ITEMS 出现顺序）：基础 / 音频 / 语音 / 高级 / 键位 / 界面
# 「界面」组（玩家侧，追加在末尾不影响既有项位置）：
#   quickbar_enabled  1 显示快捷栏 / 0 隐藏（快捷键仍可用）
#   pet_enabled       1 游戏运行时拉起桌宠 / 0 关闭（默认 0；仅源码模式生效，
#                     桌宠不进游戏包，见 engine/pet_host.py）
```

### `engine.pet_host`

```python
start() -> (bool, str)                        # 拉起桌宠子进程；失败给中文说明
stop() -> None                                # 关闭并回收；游戏退出时必调
sync(enabled) -> None                         # 按开关启停；失败只 stderr 告警
is_running() -> bool
# 安全阀：MYONL_NO_PET=1 或 SDL_VIDEODRIVER=dummy 时不启动（测试/无头环境）
```

### `engine.data`

```python
load_settings(path) -> dict                   # settings.json（UTF-8-sig 兼容 BOM）
save_settings(settings, path=None)           # 原子写 tmp + os.replace，未知键保留
load_gallery_config(assets_root) -> list[dict]  # 值可为列表（幻灯片）或对象 {"images": [...], "require": [CG 名...]}
find_cjk_font() -> str                        # 自动查找系统中文字体路径
resolve_image(name, assets_root) -> str | None
resolve_audio(name, assets_root) -> str | None
```

### `engine.expr`

```python
validate(text: str) -> None                   # 校验表达式（只看语法白名单，不求值）
evaluate(text: str, variables: dict)          # 按变量表求值；未定义变量按 0
# 异常：ExprError（中文原因）
# 安全：禁止属性访问、下标、函数调用、字符串字面量、lambda、__ 开头名字
```

### `engine.timeline`

```python
Timeline()
tl.play(name, dur_ms, fn=None, t0=0, easing="linear", loop=False, meta=None) -> Track
tl.hold(name, dur_ms, t0=0, meta=None) -> Track  # 只计时不取值（序幕/CG 停留）
tl.cancel(name)                               # 丢掉一条轨
tl.clear()                                    # 清空全部轨
tl.tick(now: int) -> dict                     # 推进到 now，返回 {轨名: 值}
tl.has(name) -> bool
tl.track(name) -> Track | None
tl.value(name, default=None)
tl.done(name, now=None) -> bool
tl.progress(name, now=None) -> float          # 0~1
tl.elapsed(name, now: int) -> int             # 时钟起点到 now 的毫秒
tl.reset_clock(name)
# Track: __slots__ = (name, t0, dur, fn, easing, loop, meta)
# 缓动：linear / ease_in / ease_out / none（直达）
```

### `engine.config`

```python
Config(overrides: dict | None = None)
cfg.window_title -> str
cfg.font(name="body") -> int                  # 字号（8~128）
cfg.font_file() -> str                        # 自定义字体（相对游戏根目录；空=自动查找 fonts/ → 系统）
cfg.color(name) -> tuple                      # (r, g, b) 或 (r, g, b, a)
cfg.alpha(name) -> int                        # 0~255
cfg.theme_color(name) -> tuple                # 语义主题色（primary/accent/surface/...）
cfg.line_height(name="body") -> float         # 行高倍数（0.8~4.0）
cfg.ui_section(name) -> dict                  # UI 布局段
cfg.dialogue(name="default") -> dict          # 对话框几何
cfg.keymap_table() -> dict
cfg.to_dict() -> dict                         # 完整生效配置
cfg.warnings: list[str]                       # 加载时的警告信息
load(assets_root=".") -> Config               # 读 config.json；缺失/损坏 → 全默认
keymap(cfg: Config) -> dict                   # {pygame 键码: 动作名}
# 类型防护：_deep_merge 阻止非 dict 覆盖 dict 默认值（防 config.json 写错类型崩溃）
```

### `engine.i18n`

```python
t(text: str, lang: str = "zh-CN") -> str      # UI 字符串翻译；缺翻译返原文
# 翻译文件：locale/<lang>.json（zh-CN / en-US）
# 注意：只翻译 UI 文本，不翻译剧本内容
```

### `engine.richtext`

```python
parse(text: str) -> list[dict]                # 解析内联样式标记
# 支持：{b}粗体{/b}、{i}斜体{/i}、{color=#rrggbb}...{/color}、{size=N}...{/size}
# 嵌套支持；未闭合标签自动闭合；\{ 转义
FontBook(font_path, default_size)
fb.get(size, bold=False, italic=False) -> pygame.font.Font
# 按 (size, bold, italic) 缓存字体实例
```

### `engine.newgame`

```python
create_game(name: str, template: str = "default", dest: str = ".") -> Path
# 模板：default（教程骨架）、moonlight（完整素材复制）、standard（抛光 demo）
# 生成项目目录：script.gal + images/ + audio/ + fonts/ + config.json

# 自定义字体：config.json 里 "font_file": "fonts/我的字体.ttf"（相对游戏根目录，
# 支持绝对路径）；文件不存在时打印中文警告并回退自动查找，不崩。
# 快捷栏图标：config.json 的
#   "ui": {"quickbar": {"icons": {"SAVE": "ui_save", "LOAD": "ui_load"}}}
# 值为 images/ 下的图片名（不带扩展名）；缺项/缺图自动回退为原来的文字按钮。
```

### `engine.packaging`

```python
PackProfile(game_dir: str)
profile.game_name -> str
profile.version -> str                        # 语义化版本（major.minor.patch）
profile.bump(kind: str)                       # kind: major/minor/patch
profile.icon_path -> str | None               # 自定义图标
profile.to_dict() -> dict
profile.save()                                # 写回 pack_config.json
load_pack_profile(game_dir) -> PackProfile
# 异常：PackProfileError
```

---

## 7. 测试与验证

- **全量 pytest**：`py -m pytest -q` —— 必须全绿（当前 500+ passed）
- **无头通关**：`python -m engine.demo games/月光漫步/script.gal --assets games/月光漫步 --auto --max-frames 60000` —— 0 异常、stderr 空
- **打包验证**：`py pack.py games/月光漫步` → `dist/月光漫步/月光漫步.exe` 无头启动 22s 不崩
- **每一步新功能**：每个新 action / 指令 / 持久状态均带独立 pytest

---

## 8. 构建命令速查

```bash
# 语法检查
python -m engine.cli --check script.gal

# 无头自动通关
python -m engine.demo games/月光漫步/script.gal --assets games/月光漫步 --auto

# 打包
python pack.py games/月光漫步

# 运行测试
pytest -q
```
