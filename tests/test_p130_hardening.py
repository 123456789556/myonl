"""P130：把审查报告里"会真伤人"的几条钉住。

这批改动没有新增功能，全是补漏洞。每一条都对应一个具体的、用户会撞上的坏事，
所以测试断言的是"那个坏行为不许回来"，不是"函数长什么样"。

1. 作品库读坏 JSON 时，先把原始串另存一份，再重建 —— 不许就地覆盖。
2. 本地存储写满时，"拿掉最旧的"必须当用户的面说清楚，不许静默。
3. 底部安全区要真的进到 layout 的 bottom 里（全面屏手势条会压住最后一行）。
4. 存档补卡片字段那条路径必须走原子写，不许裸 write_text。
5. 单文件体积告警要能从后端递到编辑器界面，不许算完丢掉。
6. 文档口径：产品说明书不许再说"Windows 唯一目标平台"、手机端文档不许再说"素材装不下"。
"""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _read(*parts):
    return (ROOT.joinpath(*parts)).read_text(encoding="utf-8")


pytestmark = [pytest.mark.unit]


# ---------- 1 & 2：作品库 ----------

def test_坏作品库先备份再重建():
    src = _read("editor", "gal_offline.js")
    assert "function keepBroken(" in src, "少了坏数据备份函数"
    # readLib 的解析失败分支必须调它，且必须在 blankLib 之前
    idx_keep = src.index("keepBroken(raw);")
    idx_blank = src.index("memLib = blankLib();")
    assert idx_keep < idx_blank, "还是先重建空白、后管原数据 —— 那就是原地覆盖丢稿"
    # 备份优先写 localStorage 独立键，满了才落 IndexedDB
    assert "LIB_KEY + \":broken:\"" in src
    assert "lib-broken:" in src


def test_超配额不静默砍():
    src = _read("editor", "gal_offline.js")
    assert "function trimLib(" in src
    # 旧写法：sort 完 slice(0,8)，密钥里一句话都不说
    assert "lib.projects.sort(function (a, b) { return (b.mtime || 0) - (a.mtime || 0); });" not in src
    # 新写法必须把"拿掉了几个"告诉用户
    assert "已把最旧的" in src
    # 且尽量把原文塞进 IndexedDB
    assert "lib-trim:" in src


# ---------- 3：安全区 ----------

def test_安全区真的加进底部留白(tmp_path):
    """layout.js 是 JS，pytest 里用 node 过一遍真值，不靠读字符串猜。"""
    import json
    import shutil
    import subprocess

    node = shutil.which("node")
    if not node:
        pytest.skip("本机没有 node，跳过 JS 布局实测")
    script = tmp_path / "probe.js"
    script.write_text(
        "const {layoutFor} = require(" + json.dumps(str(ROOT / "web" / "myonl-layout.js")) + ");\n"
        "const plain = layoutFor(390, 844);\n"
        "const safe = layoutFor(390, 844, {safeBottom: 34});\n"
        "const land = layoutFor(844, 390, {safeBottom: 34});\n"
        "console.log(JSON.stringify({plain: plain.bottom, safe: safe.bottom, land: land.bottom}));\n",
        encoding="utf-8",
    )
    out = subprocess.run([node, str(script)], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    got = json.loads(out.stdout.strip().splitlines()[-1])
    assert got["safe"] > got["plain"], "传了 safeBottom，bottom 却没变 —— 等于没接上"
    delta = got["safe"] - got["plain"]
    # 逻辑值按"短边恒 1080"换算：34 CSS 在 390 宽屏上约 94 逻辑
    assert 80 <= delta <= 100, f"换算比例不对，实际差 {delta}"
    assert got["land"] >= 0


def test_播放器把安全区传下去了():
    src = _read("web", "myonl-player.js")
    assert "function safeBottomCss()" in src
    assert "env(safe-area-inset-bottom" in src
    assert "layoutFor(lw, lh, {safeBottom:" in src
    # 横屏时手柄条在侧边，不留底部
    assert "lh >= lw ? safeBottomCss() : 0" in src


# ---------- 4：存档原子写 ----------

def test_补存档字段走原子写():
    src = _read("engine", "demo.py")
    assert "save_api._atomic_write_text(save_path" in src
    bad = 'save_path.write_text(_json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")'
    assert bad not in src, "又退回裸 write_text 了 —— 断电会留下半截档"


# ---------- 5：体积告警要递到脸前 ----------

def test_导出接口透传体积告警():
    src = _read("engine", "editor.py")
    assert '"file_warning": stat.get("file_warning", "")' in src
    assert '"file_mb": stat.get("file_mb", 0)' in src
    ui = _read("editor", "editor_uidesign.js")
    assert "resp.file_warning" in ui, "后端给了告警，前端没显示，等于白算"


# ---------- 6：文档口径 ----------

def test_产品说明书不再说放弃安卓():
    src = _read("docs", "产品说明书.md")
    assert "Windows 唯一目标平台" not in src
    assert "放弃 Android" not in src


def test_手机端文档不再说素材装不下():
    src = _read("docs", "手机端编游戏.md")
    assert "装不下素材" not in src
    assert "IndexedDB" in src


def test_README不再说成品只能电脑出():
    src = _read("README.md")
    assert "依旧在电脑上跑一次" not in src
    # 不许再把固定测试数写死在命令注释里（每加一批就过期一次）
    assert "全量 1200 passed" not in src


def test_开工须知指向的文件真实存在():
    """指向不存在的文档比不写更糟 —— 接手的人会以为自己在读一份没有的文件。"""
    # 2026-11-19 仓库迁到 myonl\MYONL引擎，纲领仍留在 娱乐工作区\玩具项目\ 下：
    # 只认上一级会变成"永远 skip"，本机这份校验就白丢了。按已知位置逐个试。
    candidates = [
        ROOT.parent / "AI开工须知.md",
        ROOT.parent.parent / "AI开工须知.md",
        ROOT.parent.parent / "玩具项目" / "AI开工须知.md",
    ]
    guide = next((c for c in candidates if c.is_file()), None)
    if guide is None:
        pytest.skip("AI开工须知.md 在仓库外，别人机器上本来就没有")
    src = guide.read_text(encoding="utf-8")
    assert "MYONL引擎\\docs\\发布纪律.md" not in src
    assert "MYONL引擎\\docs\\STATUS.md" not in src
