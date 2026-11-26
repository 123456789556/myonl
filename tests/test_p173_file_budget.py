# -*- coding: utf-8 -*-
"""P173：单文件体积预算 —— 只许降，不许涨。

为什么有这一条：引擎已经长到 `editor_main.js` 3394 行、`editor.py` 2992 行、
`editor.css` 3322 行。这类文件继续膨胀的代价不是「看着烦」：

- 改一处要通读全篇，改错的风险随行数线性涨；
- 测试失败时定位不到是哪块逻辑，只能 grep；
- 新人（包括以后的我自己）不敢动，于是所有新功能继续往同一个文件里塞，越滚越大。

所以把**今天每个大文件的行数**记成天花板。任何一次提交让某个文件比记录更高，
这条就红 —— 逼着要么拆，要么把新东西放到新文件里。

怎么降：拆出去之后把数字跟着往下调。**不许往上调**，
涨了说明又往老文件里塞东西了，那不是"这次特殊"，那是没守规矩。

参考线（不是硬指标，是提醒）：
    800 行   —— 一个模块还看得完
    1500 行  —— 开始需要目录/分节注释才能导航
    3000 行  —— 已经到了该拆的地步
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

ROOT = Path(__file__).resolve().parents[1]

# 上限 = 记账当天的实际行数 + 一点注释余量。降了要跟着降。
#
# 唯一允许的例外：新增确实是修复所必需（比如版面错位非加几行 CSS 不可）。
# 那时候调高上限可以，但必须做到两件事：
#   1) 提交信息里写清为什么涨、涨了几行；
#   2) 先找过"能不能顺手删掉等价行数"——找不到才涨。
# 不许做的：为了让自己这次的提交变绿，把上限一把抬高几十行。那这条测试就白设了。
FILE_BUDGET: dict[str, int] = {
    "editor/editor_main.js": 3395,   # P184b 素材列表改用缩略图 +2
    "editor/editor_pro.js": 2160,
    "editor/editor_uidesign.js": 1520,
    "editor/gal_offline.js": 1770,   # P197d 两条写正文的路都拍快照并等快照提交（+18，1745→1763）；P184b 入库不缩、另存缩略图 +24；P188 +40 补 POST /api/import；P190 +3 /api/new 收 text 种子
    "editor/editor_scene.js": 1282,  # P274 场景页「底板」条 +8（背景/视频/音乐搬出折叠 + 补间默认值，1266→1274）；P273 演出面板钩子 +59
    "editor/editor_perf.js": 334,    # P274 第 6 条指令 @anim 的整套（scan/line/card/read + 22 条缓动中文标签 + 角色候选，+70，262→332）；P273 新文件（5 条指令）
    "editor/editor_strip.js": 60,    # P183 分镜带（一句一张卡），新文件
    "editor/strip.css": 100,         # P183 分镜带样式，新文件
    "editor/asset_thumb.js": 50,     # P184b 缩略图生成（240 边，只给列表看，不动原图），新文件
    "editor/editor_draft.js": 420,   # P198 静默草稿 + 恢复 + 保存状态窄条（含窄条只在自己那屏显示）；P198.1 加 orphan 挤槽（+40，303→408），新文件
    "editor/editor_lint.js": 260,    # P199a 剧本体检（5 条规则）+ 查找替换（默认只动台词）+ 过滤，纯函数，新文件
    "editor/editor_find.js": 490,    # P199a 查找替换界面层：浮钮 + 浮层 + chips + 结果列表 + 替换后即时体检 + 一次撤销 + 中英切换，新文件
    "editor/i18n.js": 130,           # 界面词典：按键按业界术语（Find/Replace All/Problems/Cast/Lines），一处收口，新文件
    "editor/editor_tryplay.js": 172, # P201 编辑器内整篇试玩：把导出的成品 HTML 塞进全屏 iframe（与导出共用一条构建），新文件
    "editor/editor_shell.js": 900,   # P197b 底栏「导出」收成导出页 + 素材先关覆盖层 +9（874→883）；P258 say() 加兜底提示条 +10（887→897）——单文件版没有 window.toast，菜单里的导出提示原本全部静默
    "editor/mobile/ui_polish.js": 548,   # P188 主链路收口 + P189 结构两层（模式槽/预览浮条/空态合成/外观入口）+ P190 场景页时序兜底（场景列表重扫 + 空态恢复 + 空舞台占位 + 重扫不弹 toast）；P194 移进 mobile/，路径随搬迁改
    "editor/ui-fix.css": 330,   # P276 空态预览整块砍掉 -8（占位块/灰字/比例三行一起删，336→328）；     # P274 底板条样式 +9（.sf-base / .sf-base-cell / 44 高 select，327→336）；P186 手机外壳 + P188 主链路样式 + P189 结构两层（浮条/场景 order/外观预览置顶）+ P190 空舞台占位（宽度显式给，否则 padding 撑高的舞台会塌成 0），新文件；P268 空舞台改成跟真舞台同比例（+3 行：height:0/min-height:0/padding-bottom 一行落点 + 两行注释）
    "editor/perf.css": 21,        # P273 演出面板样式（新文件，不收进 3471 的 editor.css）
    "editor/editor.css": 3468,   # P276 删掉 .m-gzoom 死规则 -3（3471→3468）；   # P267 小总览 / 竖横排开关 / 正文行距 +8；P265 流程图样式 / 预览顶边齐平 / 场景页头并进顶栏 +41；P264 横屏把预览挪到左、左栏宽度走 --m-rail、预览收起条 +12   # P179 首页去大卡后布局收口 +5；P185 顶部安全带（挖孔/侧边 cutout）+18；P190 +25 手机场景两态真正分开（#sceneForm 的 id 级 display 压过 class 级 none）+ 横屏列表不再被表单挤成 29px + 横屏右侧不留缝
    "engine/editor.py": 3063,   # P199a 加 /editor_lint.js /editor_find.js /i18n.js 三条路由与 serve 方法（+15，3043→3058）；P201 加 /editor_tryplay.js 路由与 _serve_tryplay_js（+5，3058→3063）；P198 新增 /editor_draft.js 路由与 _serve_draft_js（+5，3038→3043）；P184b asset_thumb.js 静态路由 +1；P188 ui_polish.js 路由 +1
    "engine/parser.py": 1080,
}


def _lines(p: Path) -> int:
    return len(p.read_text(encoding="utf-8").splitlines())


def test_大文件不超预算():
    """超预算 = 又往老文件里堆了东西。要加功能就加在新文件里。"""
    over: list[str] = []
    for rel, cap in FILE_BUDGET.items():
        f = ROOT / rel
        assert f.is_file(), f"预算表里的文件不存在了：{rel}（改名或删了要同步这张表）"
        n = _lines(f)
        if n > cap:
            over.append(f"{rel} {n} 行 > 预算 {cap}（超 {n - cap} 行）")
    assert not over, (
        "文件超预算，只许降不许涨：\n  " + "\n  ".join(over)
        + "\n正确做法：把新增逻辑放进新文件；或者先把这块拆出去再降预算数字。"
    )


def test_预算表里的路都真实存在():
    """防呆：预算表写错路径会静默放过（上面那条已经断言，这里再单拎出来说明后果）。"""
    missing = [rel for rel in FILE_BUDGET if not (ROOT / rel).is_file()]
    assert not missing, f"预算表指向了不存在的文件：{missing}"
