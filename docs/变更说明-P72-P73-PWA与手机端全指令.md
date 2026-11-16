# P72 + P73：手机端装得上（PWA 主屏图标），演得全（@fg / @anim / @video / @voice / @chapter / @transition）

## 为什么做

用户要求「全部做好自己去规划直到完全完成」。翻了一遍手机端还剩什么，两件事最扎眼：

1. **导出去的网页包只能"在浏览器里打开"，装不成一个 App。** 每次玩都要输地址、顶上有地址栏、桌面上没有图标 —— 这对"发出去让人玩"是硬伤。
2. **桌面端有 6 条演出指令手机端直接不支持**：`@fg`（前景贴图，雨雪/光效）、`@anim`（立绘参数补间）、`@video`（帧序列背景）、`@voice`（语音）、`@chapter`（章节卡）、`@transition`（转场）。作者在桌面端调好的效果，导到手机上一半没了。

## 做了什么

### P72：PWA（添加到主屏幕 = 全屏 App）

- **`engine/pwa.py`（新文件）**：纯几何图标（不依赖字体/外部素材）。深底 `#14161f` + 品牌蓝 `#4f8cff` 的对话框 + 两条文字线 + 上方淡白人形 + 下方两枚胶囊选项 —— 512 缩到 48 也还认得出是"对话 × 选项"。
  - 4 倍超采样再 LANCZOS 缩，边缘不糊。
  - **踩坑**：`Image.new("RGBA")` + `ImageDraw.Draw(img, "RGBA")` 时 PIL 是**直接替换像素、不做 alpha 混合**，半透明元素会变成纯白实心块。改成 `Image.new("RGB", ..., 底色)` + `Draw(img, "RGBA")` 才是真的叠色。这一条踩了两次。
- **`manifest_dict` / `write_bundle` / `inline_manifest`**：`display:standalone`、`start_url:"./"`、`display_override`、`theme_color`、192/512/512-maskable 三档图标 + `apple-touch-icon.png(180)`。
  单文件版没法带外部文件，所以 manifest 走 `data:application/manifest+json;base64,...`，两个图标也内联进去。
- **`engine/webpack.py`**：两套模板的 `<head>` 都补 `manifest` + `apple-touch-icon` + `apple-mobile-web-app-capable` / `status-bar-style:black-translucent` / `title` / `format-detection`；`<body>` 首行加启动遮罩 `#boot`（黑底 + 一颗脉动蓝点 + 作品名）。
- **`web/myonl-player.js`**：`dismissBoot()` —— 素材加载完淡出撤掉；**出错也撤**（否则黑屏会把错误文字挡住）。

### P73：把 6 条"手机端不支持"补齐

以桌面端实现为语义基准（`render_sprites.py` 的 `_apply_sprite_anim`、`render_scene.py` 的 `_draw_fg`）：

| 指令 | 手机端做法 |
|---|---|
| `@fg` 名 x= y= alpha= | 压在 CG 之上、对话框之下的整屏贴图层。竖屏不能用 1280×720 原样贴（那样只剩顶上一小条），改 `cover` 铺满居中裁；x/y 按 1280 基准当偏移 |
| `@anim 角色 参数=起~终 秒` | `state.anim[角色][参数] = {from,to,secs,t0}`，绘制时按 `performance.now()` 线性取当前值；`scale` 以**底部中心**为锚再平移 x/y（和桌面一致）；`alpha` 走 `globalAlpha` |
| `@video 名 fps=` | 帧序列 `images/videos/名_001.png` 起连续编号，网页包/单文件都拷进去（`pack["videos"]`），播放器按 fps 循环，帧图懒加载、没加载完先贴上一帧不留黑 |
| `@voice 名` | 独立语音通道：换句掐掉上一条，音量比 BGM 略高。（parser 要求 `@voice` 紧跟在台词后，执行顺序就是 say → voice） |
| `@chapter 标题 秒` | 黑场 + 居中大标题 + 蓝色短线，淡入淡出；期间 `waitUntil` 挡点击，播完自动继续。`next()` 遇到 chapter 必须 break，否则台词会抢在章节卡前面出来 |
| `@transition dissolve/wipe/slide` | 记到 `state.trans`，作用于**下一张**背景：dissolve = 淡入秒数，wipe/slide = 按方向 `clip` 推进来 |

顺带修掉三处隐性 bug：

- **`@fg 无` 从来没真的清过前景**。parser 把它归一成 `name="无"`，但 `runtime.py` 只认 `ins.get("reset")` —— 于是桌面端一直走"设了一张叫『无』的图"，绘制时找不到素材就静默跳过，看着像清了、其实是素材缺失。现在 runtime / webpack 收集 / 前端 VM / `demo.py` 的资源预检四处统一认 `无`/`none`。
- **`webpack` 的 unsupported 清单里塞了 `play`/`stop`/`shake`** —— parser 根本不产出这三个 op（`@shake` 已归一成 `camera kind=shake`）。删掉，清单现在如实为空。
- **`_collect_image_names` 不收 `@fg` 的贴图** —— 加了 fg 收集，但 `@fg 无` 不当素材报缺失。

## 顺带补的一块：横屏选项页「在答什么」

补验收截图时才发现横屏 844×390 下选项页几乎是一整屏黑 + 两个按钮：选项出现会藏起对话框（
否则上一句面板会压住按钮，横屏只 390 高时尤其明显），但代价是**玩家不知道自己在回答什么**。

改法：选项组上方补一行提问文字 —— 取当前台词的最后一行、居中、`bw*0.94` 折行最多两行、带阴影。
不画面板（面板才是压按钮的那个），只留一行字在按钮上方 `bh*0.55` 处。同时把压暗层从 `0.66` 降到 `0.56`，
背景不再被压成一整片黑。

证据：`p74land-choice.png`（横屏，提问行在按钮上方）、`p74choice-portrait.png`（竖屏同场景 +
底部「这个作品是横屏的·把手机横过来 ↔」提示）。

## 验证

- `tests/test_p72_pwa.py`：6 条（方向映射与 short_name 截断 / 落盘含 PNG 头 / manifest base64 往返 / 两套模板的 head / 真编单文件里搜得到 PWA 字样）。
- `web/test/vm-smoke.js` 追加第 9 段：`@fg` 设置与 reset、`@anim` 起点缺省接上一次终点、存档只存终值、`@video` 被 `@bg` 清掉、读档复原 fg/anim。
- 真机式验收（playwright，390×844 `has_touch`，`file://` 直开单文件）：
  - `pwa-boot.png` 抓到遮罩淡出中（蓝点 + 作品名 + 下面标题页已就位）；
  - 加载后 `#boot` 已从 DOM 移除，`manifest` / `apple-touch-icon` / `capable` 三项全 True，console 无 error；
  - `p73-anim-early.png` 立绘偏左滑入 → `p73-anim-late.png` 到位（`@anim x`）；
  - `p73-fg.png` 斜雨铺满全屏且不盖对话框（`@fg`）；
  - `p73-video-a/b.png` 两帧换色循环（`@video`）；
  - `p73b-01.png` 章节卡黑场标题（`@chapter`）；
  - `p73b-06.png` 半屏分界的擦除（`@transition wipe`）。
- 门禁：`pytest -m "not slow"` **1091 passed / 1 skipped / 32 deselected**；`vm-smoke`、`layout-smoke`、`node --check` 全过。
- 体积：单文件 `774824 B`（P71 时 718978，+55 KB 主要是内联 manifest + 两个图标 ≈ 42 KB 和变大的播放器）。

## 已知边界

- 单文件内联 manifest 的意义有限（`file://` 下 Android 不会给装 PWA，`apple-touch-icon` 才是 iOS 真正用得上的那个）。留着是因为"发一个文件给别人"这条路要尽量完整；嫌大可以砍。
- `@transition` 的 wipe/slide 方向语义按"新画面从该方向推入"实现，没去逐个核对桌面端的像素级方向。
- `@plug`（插件调用）仍然不支持 —— 插件本身是桌面端 Python 侧的扩展点，手机端没有对应实现。现在会记进 `warnings`，不静默吞掉。
- PWA 要真正"装得上"，网页包必须放在 https 或 localhost 静态服务下；直接双击 `index.html` 只能当网页看。
