# MYONL 引擎规格（engine_spec.md）

> 这份是**剧本语法与格式层面**的权威参考：指令全集、参数、存档结构、Python/JS API。
> 平台、打包产物、运行环境以 [README](../README.md)、[打包使用指南](desktop/打包使用指南.md)、
> [手机端编游戏](mobile/手机端编游戏.md) 为准；代码怎么组织见 [架构说明](架构说明.md)。
>
> 剧本是纯文本 `.gal`（UTF-8，兼容记事本另存的 BOM），每行一条指令，`@` 开头。
> 手机端解析器（`engine/parser.js`）与电脑端（`engine/parser.py`）逐字段一致，
> 由 `tools/pack_diff.py` 拿 `games/` 下全部工程对拍。

## 1. 架构与模块边界

```
剧本.gal
   │
   ▼
engine/parser.py（解析）── 指令白名单校验 + GalSyntaxError
   │
   ▼ list[dict] 指令列表
engine/runtime.py（解释器 / GameState）
   │
   ▼ dict 快照（含持久化展示层状态）
engine/renderer.py（无状态渲染，读 snapshot）
   │
   ▼ pygame.Surface 逻辑画布 1280×720，letterbox 等比缩放
engine/ui.py（玩家侧 UI 状态机）
engine/save.py（GameState ↔ JSON 存档 + 缩略图 + 全局 persistent）
engine/data.py（settings.json / 素材定位 / 中文字体查找）
engine/timeline.py（镜头 / 转场 / 立绘补间 / 停留调度，不进 GameState）
```

**模块依赖单向**：`parser → runtime → demo → renderer / ui`；`save / data / timeline`
依赖 runtime 或 renderer；禁止反向 import（renderer/ui 不得 import runtime）。
**数据流铁律**：剧本与引擎代码分离；脚本状态存于 GameState；渲染器只读 snapshot，
不反向改状态；展示层瞬时动画（震动、补间过程）只在 renderer 内部 Timeline，不进存档。

### 1.1 GameState 主要字段

```python
{
    "script": str,                 # 剧本路径
    "stack": [[list_id, index]],   # 栈帧：当前在哪个指令列表的第几条
    "bg": str | None,              # 当前背景图名
    "music": str | None,           # 当前背景音乐名
    "video": {"name": str, "fps": int, "movie_file": bool,
              "loop": bool, "mute": bool} | None,
    "sprites": [{"char", "expr", "anim", "pos", "scale", "z", "layers"}],
    "vars": dict,                  # 脚本变量
    "characters": {name: {"color": str}},
    "history": [{"char": str | None, "text": str}],
    "pending_choice": {"options": [...], "cursor": int} | None,
    "pending_wait": {"seconds": float} | None,
    "finished": bool,
    "gallery": list[str],           # 已解锁 CG 名（进存档）
    # ---- 持久化展示层状态（读档后 renderer 复原画面）----
    "fg": {"name", "x", "y", "alpha"} | None,
    "camera_zoom": float,
    "anim_final": {char: {param: float}},
}
```

---

## 2. 指令表

> 计数口径：下表按**指令种类**列。`@[角色]` / `@` / `@[[…]]` 是台词的三种写法，
> 不算独立指令；`@plug:` 是插件前缀。手机端未实现的指令在第 2.9 节单独列出。

### 2.1 对话与角色

| 指令 | 语法 | 示例 | 说明 |
|---|---|---|---|
| `@character` | `@character 名字 #RRGGBB [kind=布局]` | `@character 林晚 #c8ffc8` / `@character 旁白 #ffffff kind=nvl` | 注册角色 + 对话颜色；`kind=` 绑定对话框布局（缺省 default）；不登记也能用方括号台词 |
| 台词 | `@[角色] 文本` / `@ 文本` / `@` 换行 / `@[[…]]` | `@[林晚] 你好。` / `@ hello world!` / `@[[林晚]] 那年夏天……` | 方括号 = 角色台词（无需登记，括号不显示；`@[林晚]` 后换行写台词也行）；`@[[角色]] 文本` = 整屏独白（NVL）；`@[[整段文字]]` = 整屏旁白；`@` 后空格或单独一行 + 下一行 = 旁白；旧的 `@ 已登记角色 文本` 写法继续有效 |

### 2.2 资源加载

| 指令 | 语法 | 示例 | 说明 |
|---|---|---|---|
| `@bg` | `@bg 图片名 [fadein=秒]` | `@bg classroom` / `@bg beach fadein=1.5` | 背景切换；`images/<名>.png/.jpg/.jpeg/.webp`；`fadein=` 本次黑场淡入时长（缺省 0.3s，一次性，不进存档） |
| `@music` | `@music 音乐名 [fadein=秒] [fadeout=秒]` | `@music op fadein=2.0` | 背景音乐；`audio/<名>.ogg/.mp3/.wav` |
| `@sfx` | `@sfx 音效名` | `@sfx click` | 一次性音效 |
| `@voice` | `@voice 配音文件名` | `@voice hello_eileen` | 给上一句台词配配音；`audio/<名>.ogg/.mp3/.wav` |

### 2.3 立绘系统

| 指令 | 语法 | 示例 | 说明 |
|---|---|---|---|
| `@show` | `@show 角色ID 表情 [anim=呼吸\|walk] [pos=左\|中\|右] [scale=0.5~2.0] [z=整数] [x=像素] [y=像素] [部位:素材]` | `@show 双叶 身体:默认 表情:微笑 pos=中 z=1` | 分层立绘；`anim` 默认呼吸；`pos` 默认中，也可 `left/center/right`；`x`/`y` 是相对默认位置的像素偏移；分层立绘逐个部位查素材 |
| `@hide` | `@hide 角色ID` | `@hide 双叶` | 撤下立绘（同时清掉 anim_final） |
| `@anim` | `@anim 角色ID 参数=起始~结束\|目标 秒数 [ease=曲线]` | `@anim 双叶 x=-100~0 0.8 ease=ease_out` | 立绘参数补间：x / y / alpha（0~1）/ scale（0.5~2.0）；曲线名取自 `timeline.EASINGS` |

### 2.4 视觉演出

| 指令 | 语法 | 示例 | 说明 |
|---|---|---|---|
| `@fg` | `@fg 前景名 [x=像素] [y=像素] [alpha=0~1]` / `@fg 无` | `@fg rain alpha=0.6` / `@fg 无` | 前景层贴图（画在立绘之上、UI 之下）；`无` 清除 |
| `@cg` | `@cg CG名称` | `@cg cg_end1` | 全屏 CG 展示（占满画面、屏蔽对话框，进 gallery 解锁） |
| `@camera` | `@camera pan 方向 秒数` / `zoom 起始 结束` / `shake 秒数 幅度` / `reset 秒数` | `@camera zoom 1.0 1.3` | 镜头控制；`zoom` 最终值进存档 |
| `@transition` | `@transition dissolve 秒数` / `wipe 方向 秒数` / `slide 方向 秒数` | `@transition dissolve 0.3` | 下一次背景切换时触发转场；方向 左/右/上/下（也可 left/right/up/down） |
| `@wait` | `@wait 秒数\|毫秒数`（无单位默认秒） | `@wait 1.5` / `@wait 500ms` | 暂停推进到倒计时完（读档后续等恢复） |
| `@chapter` | `@chapter 章节标题 [secs=秒]` | `@chapter 第一章 雨夜` / `@chapter 幕间 secs=0.8` | 章节/幕间演出卡：黑场 + 标题渐显渐隐，播完自动恢复（时长缺省取 `pacing.chapter_fade`，同时暂停推进） |

### 2.5 流程控制

| 指令 | 语法 | 示例 | 说明 |
|---|---|---|---|
| `@label` | `@label 标签名` | `@label scene1_start` | 跳转目标标签 |
| `@jump` | `@jump 标签名` | `@jump scene1_start` | 跳到标签位置继续执行 |
| `@end` | `@end` | `@end` | 结束剧本播放，`state["finished"] = True` |
| `@set` | `@set 变量 += 数值` / `-=` / `=` / `@set 变量 = 表达式` / `@set 变量 = "字符串"` | `@set 好感 += 1` / `@set 名字 = "双叶"` | 变量操作；表达式支持变量、整数/小数、字符串字面量与 + 拼接、四则 +-*/、括号、比较、and/or/not |
| `@if` | `@if 条件:` + 缩进块；`@elif 条件:`；`@else:` | `@if 好感 > 50:` | 条件分支；支持 `and`/`or`/`not`/比较 |
| `@choice:` | `@choice:` + 缩进选项列表 | 见 2.6 | 暂停推进等待玩家选择 |
| `@video` | `@video 视频名 [file] [fps=N] [loop=0\|1] [mute]` | `@video rain fps=24` / `@video op file loop=1 mute` | 视频背景，两条通道见 2.8 |
| `@plug:` | `@plug:插件指令名 [参数...]` | `@plug:shake 1.0` | 插件入口，见 [插件开发指南](desktop/插件开发指南.md) |
| `@include` | `@include 相对路径.gal` | `@include 章节/第一章.gal` | 顶层内联展开另一个剧本；路径相对当前文件目录，禁止循环引用 |

### 2.6 `@choice:` 缩进格式

```
@choice:
  > 你走向便利店。 -> 结局A
  > 你转身回家。 -> 结局B
  > 打招呼: 好感 >= 3 -> 结局C

@label 结局A
@ 你推开了便利店的门。
@end
```

`@choice:` 单独一行；下一行起每条选项写成 `> 文本 -> 标签`，条件写在文本后
（`> 文本: 条件 -> 标签`，条件可省略）。同一组选项缩进必须一致；下一行不是 `>` 开头即选项结束。

### 2.7 台词写法与内联标记

| 写法 | 效果 | 示例 |
|---|---|---|
| `@[角色] 文本` | 普通对话框台词，**不需要** `@character` 登记 | `@[林晚] 你好。` |
| `@[角色]` + 换行 | 下一行整行作为台词 | `@[林晚]` / 下一行 `你好。` |
| `@[[角色]] 文本` | 整屏独白（NVL 布局） | `@[[林晚]] 那年夏天，风很长。` |
| `@[[整段文字]]` | 整屏旁白（无名字） | `@[[我忽然想起那年夏天。]]` |
| `@ 文本` | 旁白 | `@ 注意：请勿靠近。` |
| `@` + 换行 | 下一行整行作为旁白 | `@` / 下一行 `hello world!` |

边界规则：

- 单括号允许配平嵌套：`@[林晚[老师]] 你好。` → 角色名「林晚[老师]」；双括号 `[[...]]` 里不能再出现 `[` 或 `]`。
- **冒号没有特殊含义**：`@ 注意：请勿靠近` 是旁白，不会把「注意」当人名。
- 台词插值：`${变量}` 替换为变量当前值（未定义时打印中文警告并置空）。旧写法 `{变量}` 仍兼容，但只在变量**已定义**且名字不是 `b` / `i` / `color` / `size` 时替换。
- 富文本标记（只影响被包住的字，折行/分页仍按纯文本算）：`{b}…{/b}` 粗体、`{i}…{/i}` 斜体、`{color=#rrggbb}…{/color}` 变色、`{size=N}…{/size}` 字号（8~128px）；可嵌套，未闭合自动补到行尾，不认识的标签原样显示；字面花括号写 `{{` `}}`。

### 2.8 `@video` 两条通道

| 写法 | 通道 | 素材位置 |
|---|---|---|
| `@video 名 fps=24`（不写 `file`） | 帧序列 | `images/videos/名_001.png` 起连续编号（`.png` / `.webp`） |
| `@video 名 file` | 真视频文件 | `videos/名.mp4` / `.webm` / `.mov`；可追加 `loop=0\|1`（0 播完停最后一帧，1 循环，缺省 1）、`mute`（静音） |

`fps=` 只对帧序列有意义；`file` 形式接受但忽略 `fps=`。播放器同时只解一个视频，
切幕 / 切背景 / 读档 / 退出立刻释放。

### 2.9 手机端未实现的指令

手机端解析器遇到下列指令会抛清楚的中文错误并指出第几行，不静默走偏：
`@plug` `@include`。
手机端已覆盖：`@character` `@bg` `@music` `@sfx` `@show` `@hide` `@wait` `@chapter`
`@label` `@jump` `@end` `@set` `@if` `@video` `@voice` `@cg` `@fg` `@camera` `@transition` `@anim`
+ `@choice:` + 台词行。完整边界见 [手机端编游戏](mobile/手机端编游戏.md)。

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

存档文件：`<assets_root>/saves/slot_N.json`（N = `"quick"` 或 1~10）。缩略图：
`<assets_root>/saves/thumb_N.png`。卡片信息：JSON 顶层 `thumbnail_path`（只存文件名）、
`chapter_name`、`last_text`、`label`（锚点最近 label 名）。全局解锁：
`<assets_root>/saves/persistent.json`（跨存档持久）。

**线程安全**：settings.json 用 `os.replace` 原子替换；存档 JSON 先写临时文件再 replace。
存档锚点是「标签 + 偏移」，不是行号：剧本小改、加新章节，旧存档依然能读。

---

## 5. Python API 参考

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
rt.load(script_path)
rt.snapshot() -> dict
rt.step() -> dict
rt.choose(index)
rt.save(slot) -> str
rt.load_save(slot) -> dict
rt.pending_wait_seconds() -> float
rt.advance_wait(dt_seconds)
rt.set_var(key, value)
rt.seen_sprites() -> list[str]
```

### `engine.renderer`

```python
Renderer(size=(1280, 720), assets_root=".")
ren.render(state: dict, ui_view: dict | None)
ren.handle_input() -> dict
ren.play_anim(char, param, from_value, to_value, secs, easing="linear")
ren.play_fg(name, x=0, y=0, alpha=1.0)
ren.play_camera(kind, *args)
ren.set_splash(bool)
ren.trigger_ending_fade()
ren.reveal_all()
ren.save_thumbnail(path)
ren._last_dt_ms -> int
ren.close()
```

### `engine.save`

```python
save(state, slot, anchor_stack=None, *, label=None, last_text=None)
load(slot) -> dict
list_slots() -> list[dict]
delete_slot(slot)
gallery_union(list_a) -> list[str]
load_persistent() -> dict
saves_dir() -> Path
set_saves_dir(path) -> Path
reset_saves_dir()
slot_path(slot) -> Path
# 异常：SaveError
```

### `engine.ui`

```python
UI()
ui.settings_path -> str
ui.mode -> str
ui.refresh()
ui.set_history(list[dict])
ui.set_gallery(list[str], list[str])
ui.set_gallery_config(list[dict])
ui.set_settings(dict)
ui.handle(key: str) -> dict | None
ui.click(hit: dict) -> dict | None
ui.view(now_ms: int | None) -> dict
next_value(key, current) -> int | float
```

### `engine.data`

```python
load_settings(path) -> dict
save_settings(settings, path=None)
load_gallery_config(assets_root) -> list[dict]
find_cjk_font() -> str
resolve_image(name, assets_root) -> str | None
resolve_audio(name, assets_root) -> str | None
```

### `engine.expr`

```python
validate(text: str) -> None
evaluate(text: str, variables: dict)
# 异常：ExprError（中文原因）
# 安全：禁止属性访问、下标、函数调用、字符串字面量、lambda、__ 开头名字
```

### `engine.timeline`

```python
Timeline()
tl.play(name, dur_ms, fn=None, t0=0, easing="linear", loop=False, meta=None) -> Track
tl.hold(name, dur_ms, t0=0, meta=None) -> Track
tl.cancel(name)
tl.clear()
tl.tick(now: int) -> dict
tl.has(name)
tl.track(name) -> Track | None
tl.value(name, default=None)
tl.done(name, now=None) -> bool
tl.progress(name, now=None) -> float
tl.elapsed(name, now: int) -> int
tl.reset_clock(name)
# 缓动名集合见 timeline.EASINGS（linear / none / ease_in / ease_out 及
# ease_in/out/in_out_quad|cubic|quart|sine|expo|back）
```

### `engine.config`

```python
Config(overrides: dict | None = None)
cfg.window_title -> str
cfg.font(name="body") -> int
cfg.font_file() -> str
cfg.color(name) -> tuple
cfg.alpha(name) -> int
cfg.theme_color(name) -> tuple
cfg.line_height(name="body") -> float
cfg.ui_section(name) -> dict
cfg.dialogue(name="default") -> dict
cfg.keymap_table() -> dict
cfg.to_dict() -> dict
cfg.warnings: list[str]
load(assets_root=".") -> Config
keymap(cfg: Config) -> dict
# 类型防护：_deep_merge 阻止非 dict 覆盖 dict 默认值
```

### `engine.i18n`

```python
t(text: str, lang: str = "zh-CN") -> str
# 翻译文件：locale/<lang>.json（zh-CN / en-US）；只翻译 UI 文本，不翻译剧本内容
```

### `engine.richtext`

```python
parse(text: str) -> list[dict]
# 支持：{b}粗体{/b}、{i}斜体{/i}、{color=#rrggbb}...{/color}、{size=N}...{/size}
FontBook(font_path, default_size)
fb.get(size, bold=False, italic=False) -> pygame.font.Font
```

### `engine.newgame`

```python
create_game(name: str, template: str = "default", dest: str = ".") -> Path
# 模板：hello（极简空包）、default（教学骨架）、standard（内置素材成品模板）
# 自定义字体：config.json "font_file": "fonts/我的字体.ttf"（相对游戏根目录，支持绝对路径）
# 竖版构图：images/{名}_p.png，播放器按当前方向挑；config.json "focal": {"名": [x, y]} 定裁切窗口
```

### `engine.packaging`

```python
PackProfile(game_dir: str)
profile.game_name -> str
profile.version -> str
profile.bump(kind: str)
profile.icon_path -> str | None
profile.to_dict() -> dict
profile.save()
load_pack_profile(game_dir) -> PackProfile
# 异常：PackProfileError
```

---

## 6. 测试与验证

- **全量 pytest**：`py -3 -m pytest -q`，必须全绿。通过数以最新 [CHANGELOG](CHANGELOG.md) 为准；
  本文不手写会过期的测试计数。
- **无头通关**：`py -3 -m engine.demo games/标准示例/script.gal --assets games/标准示例 --auto --max-frames 60000`，0 异常、stderr 空。
- **打包验证**：`py pack.py games/标准示例`，产物无头启动不崩。
- 每条新指令 / 持久状态均带独立 pytest。

## 7. 构建命令速查

```bash
# 语法检查
py -3 -m engine.cli --check script.gal

# 无头自动通关
py -3 -m engine.demo games/标准示例/script.gal --assets games/标准示例 --auto

# 打包桌面目录
py -3 pack.py games/标准示例

# 运行测试
py -3 -m pytest -q
```
