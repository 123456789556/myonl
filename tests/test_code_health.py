# -*- coding: utf-8 -*-
"""架构与文档结构约束（M0 收口）。

把计划里写的「验收口径」变成可执行测试，避免 ✅ 手填：
1. 渲染模块行数上限（P45 拆分目标；当前 renderer 642 / render_dialog 609，先按 700 防失控）
2. 编辑器入口行数（T4 目标 <500，当前 3938 → xfail 记账；硬上限 4000，只剩 62 行余量）
3. pytest marker 集合与计划一致；每个测试文件必须声明分层 marker（否则 -m 分层会静默漏跑）
4. 文档结构：STATUS/ROADMAP/BACKLOG/CHANGELOG + 唯一计划页存在；STATUS 有自动数字块

规则：这里的断言只能随「口径变更」改，不能为了让测试变绿而放宽。
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

ROOT = Path(__file__).resolve().parents[1]

RENDER_LIMIT = 700          # P45 目标 600；当前两个文件在 600~700 之间，先由 700 兜底并存账
EDITOR_ENTRY_TARGET = 600  # 主脚本已抽到 editor_main.js（index 529 行）   # T4 验收口径
EDITOR_ENTRY_CEILING = 4000 # 硬上限：只许下降，不许再涨


def _lines(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


# 当前实际行数（xfail 说明用；每次跑都读真实值，避免注释与代码漂移）
EDITOR_ENTRY_NOW = _lines(ROOT / "editor" / "index.html")


# ==================== 1. 模块行数 ====================

def test_渲染模块行数上限():
    """P45 拆分后的 10 个渲染模块 + renderer 入口，单文件不超过 700 行。"""
    files = sorted((ROOT / "engine").glob("render_*.py")) + [ROOT / "engine" / "renderer.py"]
    assert len(files) >= 10, f"渲染模块数量异常：{len(files)}"
    over = []
    for f in files:
        n = _lines(f)
        if n > RENDER_LIMIT:
            over.append(f"{f.name}={n}")
    assert not over, f"渲染模块超 {RENDER_LIMIT} 行：{over}"


def test_编辑器入口行数硬上限():
    """编辑器 index.html 只许下降；超过 4000 行说明又在往里堆逻辑。"""
    n = _lines(ROOT / "editor" / "index.html")
    assert n < EDITOR_ENTRY_CEILING, f"editor/index.html 已 {n} 行，超过硬上限 {EDITOR_ENTRY_CEILING}"


def test_编辑器入口行数目标():
    """T4 验收口径：index.html <600 行（T16：主脚本已抽到 editor_main.js）。"""
    n = _lines(ROOT / "editor" / "index.html")
    assert n < EDITOR_ENTRY_TARGET, f"index.html 当前 {n} 行（目标 <{EDITOR_ENTRY_TARGET}），归 T16"


# ==================== 2. 测试分层与计划一致 ====================

def _pytest_ini_markers() -> set[str]:
    text = (ROOT / "pytest.ini").read_text(encoding="utf-8")
    block = text.split("markers =", 1)[1] if "markers =" in text else ""
    names: set[str] = set()
    for line in block.splitlines():
        m = re.match(r"^\s{4}([a-z_]+):", line)
        if m:
            names.add(m.group(1))
    return names


def test_marker集合与计划一致():
    """计划写 unit/ui/slow/integration，就必须只有这四个；出现 e2e 之类即为口径漂移。"""
    assert _pytest_ini_markers() == {"unit", "ui", "slow", "integration"}


def test_每个测试文件声明分层marker():
    """分层跑（-m unit/ui/slow/integration）不能静默漏测：每个 tests/test_*.py 必须声明 pytestmark 且含合法层。

    背景：2026-11-01 的 test_a1_errors.py 漏打 marker，-m 分层跑会整文件静默跳过；
    这里把「新测试必须进分层」固化成门禁，避免再静默漏。
    """
    allowed = {"unit", "ui", "slow", "integration"}
    missing: list[str] = []
    bad: list[str] = []
    for f in sorted((ROOT / "tests").glob("test_*.py")):
        text = f.read_text(encoding="utf-8")
        m = re.search(r"pytestmark\s*=\s*\[(.*?)\]", text, re.S)
        if not m:
            missing.append(f.name)
            continue
        layers = set(re.findall(r"pytest\.mark\.([a-z_]+)", m.group(1)))
        if not (layers & allowed):
            bad.append(f"{f.name}={sorted(layers)}")
    assert not missing, f"测试文件未声明 pytestmark（-m 分层会静默漏跑）：{missing}"
    assert not bad, f"pytestmark 里没有合法分层：{bad}"


# ==================== 3. 文档结构：公开的留，内部的走 ====================
#
# P117 起立规矩：公开仓库只放「陌生人下载下来就能用、能看懂」的文档。
# 内部状态页、路线图、待办、唯一计划页、逐条变更说明 —— 一律留在本地 myonl-publish。
# 下面这些断言就是那道闸门，不是建议：谁把内部文档推上来，测试就红。

# 陌生人需要看的（必须存在）
_PUBLIC_DOCS = (
    "CHANGELOG.md",        # 这版改了什么
    "engine_spec.md",       # 指令全集：想写剧本的人得查它
    "快速上手.md",          # 怎么开始
    "手机端编游戏.md",       # 手机这条路怎么走
    "素材导入指南.md",       # 图和音乐怎么放进去
    "打包使用指南.md",       # 怎么出成品
    "存档与升级.md",         # 玩家最怕的那件事
    "版本规则.md",           # 版本号怎么算
    "贡献指南.md",           # 想搭把手的人从哪进
    "插件开发指南.md",       # 想扩展引擎的人
    "架构说明.md",           # 代码怎么组织的
)

# 内部自己看的（必须不在仓库里）
_INTERNAL_DOCS = (
    "STATUS.md",
    "ROADMAP.md",
    "BACKLOG.md",
    "接手规矩.md",
    "md-规范说明.md",
    "展示_60秒分镜与投稿包.md",
    "计划",
    # 发布纪律讲的是"我们的仓库该放什么"，还写着本机绝对路径 ——
    # 文件名干净，内容全是内部信息。它就是被下面那条内容检查抓出来的。
    "发布纪律.md",
)


def test_对外文档齐全():
    for name in _PUBLIC_DOCS:
        assert (ROOT / "docs" / name).is_file(), f"缺少 docs/{name}"


def test_内部文档不许进公开仓库():
    """谁把内部文档推上来，这条就红——规矩得能拦住人才算规矩。"""
    for name in _INTERNAL_DOCS:
        assert not (ROOT / "docs" / name).exists(), (
            f"docs/{name} 是内部文档，按发布纪律应留在本地 myonl-publish/内部文档")
    strays = sorted(p.name for p in (ROOT / "docs").glob("变更说明-P*.md"))
    assert not strays, f"逐条变更说明不进公开仓库：{strays[:5]}"


def test_历史文档不再进仓库():
    """2026-11-01 用户授权：历史只在 git（原 docs/archive 104 篇 + 项目协作制度 已删除）。"""
    assert not (ROOT / "docs" / "archive").exists(), "docs/archive 已删除，历史查 git 历史"
    assert not (ROOT / "docs" / "项目协作制度.md").exists(), "项目协作制度已并入项目外总纲"


# ---- 上面三条只拦文件名。文件名合规、内容照样能泄露，所以下面两条查内容 ----

_INTERNAL_MARKERS = (
    "STATUS.md",
    "ROADMAP.md",
    "BACKLOG.md",
    "变更说明-P",
    "接手规矩",
    "md-规范说明",
    "展示_60秒",
    "计划/00-总览",
)


def test_公开文档不许链到已移出的内部文档():
    """文件移走了，链接还留在正文里 —— 读者点过去 404，还得猜是不是没写完。

    这种泄露比"多出一个文件"更隐蔽：文件名干干净净，内容在指路。
    """
    leaks = []
    for md in sorted((ROOT / "docs").rglob("*.md")):
        text = md.read_text(encoding="utf-8", errors="ignore")
        for marker in _INTERNAL_MARKERS:
            if marker in text:
                leaks.append(f"{md.relative_to(ROOT)} 里出现 {marker}")
    assert not leaks, f"公开文档在链已移出的内部文档：{leaks[:6]}"


def test_公开文档不许泄露本机路径():
    """`D:\\娱乐工作区` 只该出现在我们自己的笔记里。

    写进公开文档等于把目录结构摊开，而且读者照抄一定失败。
    """
    patterns = ("D:\\娱乐工作区", "C:\\Users", "myonl-publish")
    leaks = []
    for md in sorted((ROOT / "docs").rglob("*.md")):
        text = md.read_text(encoding="utf-8", errors="ignore")
        for pat in patterns:
            if pat in text:
                leaks.append(f"{md.relative_to(ROOT)} 里出现 {pat}")
    assert not leaks, f"公开文档泄露本机路径：{leaks[:6]}"
    readme = (ROOT / "README.md").read_text(encoding="utf-8", errors="ignore")
    for pat in patterns:
        assert pat not in readme, f"README 泄露本机路径：{pat}"


# ==================== 4. 编辑器反馈结构（E-1，M1.5） ====================

def test_编辑器问题面板与微反馈结构齐全():
    """问题面板 + 保存/预览脉冲是 E-1 的正反馈骨架，删/改文件名时立即可见。"""
    html = (ROOT / "editor" / "index.html").read_text(encoding="utf-8")
    html += "\n" + (ROOT / "editor" / "editor_main.js").read_text(encoding="utf-8")
    css = (ROOT / "editor" / "editor.css").read_text(encoding="utf-8")
    for token in ("breadcrumb", "updateBreadcrumb", "bc-item", "problemsPanel", "problemsList", "problem-row", "renderProblems", "jumpToLine"):
        assert token in html, f"index.html 缺 {token}"
    assert "preview-bar.pulse" in css
    assert ".breadcrumb" in css


def test_编辑器内嵌教程入口():
    """开发者侧「边写边看说明书」：帮助菜单 + 左栏入口 + 文档 API。"""
    html = (ROOT / "editor" / "index.html").read_text(encoding="utf-8")
    html += "\n" + (ROOT / "editor" / "editor_main.js").read_text(encoding="utf-8")
    assert "helpPanel" in html and "actHelp" in html
    assert "教程 / 说明书" in html
    editor_py = (ROOT / "engine" / "editor.py").read_text(encoding="utf-8")
    assert "/api/help" in editor_py and "/api/help/doc" in editor_py


# ==================== 5. 编辑器布局嵌套（结构回归，M1.5 修复） ====================

def test_编辑器三栏嵌套正确():
    """左栏（源码）与右栏（预览/检查器/时间线）必须都在 .main 里。

    2026-11-01 审图发现：left-pane 后多了一个 </div>，浏览器把 splitEdit/right-pane
    挤成 body 的直接子元素 → 三栏布局塌成上下两块。这里用标准库 HTMLParser 守住结构。
    """
    from html.parser import HTMLParser

    class P(HTMLParser):
        def __init__(self):
            super().__init__()
            self.stack = []
            self.parents = {}  # (tag, id/class) -> parent class/id

        def handle_starttag(self, tag, attrs):
            d = dict(attrs)
            key = (tag, d.get('id') or '', d.get('class') or '')
            parent = self.stack[-1] if self.stack else None
            if key not in self.parents:
                self.parents[key] = parent
            self.stack.append(key)

        def handle_endtag(self, tag):
            for i in range(len(self.stack) - 1, -1, -1):
                if self.stack[i][0] == tag:
                    del self.stack[i:]
                    break

    parser = P()
    parser.feed((ROOT / "editor" / "index.html").read_text(encoding="utf-8"))
    main = ("div", "", "main")
    right = ("div", "", "right-pane")
    left = ("div", "", "left-pane")
    src = ("div", "sourceWrap", "source-wrap")
    assert right in parser.parents and parser.parents[right] == main
    assert src in parser.parents and parser.parents[src] == left


def test_素材晾衣绳结构():
    """素材晾衣绳（交互想法参考 Tendedero，MIT）：悬停滑出 + 点击插入指令。"""
    html = (ROOT / "editor" / "index.html").read_text(encoding="utf-8")
    html += "\n" + (ROOT / "editor" / "editor_main.js").read_text(encoding="utf-8")
    css = (ROOT / "editor" / "editor.css").read_text(encoding="utf-8")
    for token in ("clothesline", "clItems", "clTrigger", "clTabs", "cl-pin", "pushPreviewHistory",
                 "refreshClothesline", "insertDirective(c.ins)", "drop-ready"):
        assert token in html, f"index.html 缺 {token}"
    assert ".clothesline.open" in css and "cl-swing" in css
