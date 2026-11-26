"""P273：@voice / @cg / @fg / @camera / @transition 在逐句页有参数表单。

用户原话：「改 x= alpha= 这这些我希望你搞好」。之前这 5 条只能整行改，
卡片视图只给中文名和一句摘要，等于写错一个数字就得切去源码。

钉住（node 直接跑 editor/editor_perf.js，不靠人眼）：
    1. scan 认得出 5 条指令的全部写法，认不出的行返回 null（不许吃掉别人的行）；
    2. scan → line 对规范写法是等价的（缺省参数不写进命令）；
    3. @fg 只写非缺省参数：x=0 不写、alpha=1 不写、alpha 夹在 0~1；
    4. fixVoices 把「前面不是台词」的配音搬到上一个台词后面；前面根本没有台词就丢掉并计数；
    5. editor_scene.js 五处钩子都在（parse / render / read / save / fix），漏一处就等于表单白做。
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

ROOT = Path(__file__).resolve().parents[1]
PERF = ROOT / "editor" / "editor_perf.js"
SCENE = (ROOT / "editor" / "editor_scene.js").read_text(encoding="utf-8")


def _node(expr: str):
    node = shutil.which("node")
    if not node:
        pytest.skip("本机没有 node")
    js = PERF.read_text(encoding="utf-8")
    code = (
        "const fs=require('fs');"
        "const src=fs.readFileSync(process.argv[1],'utf8');"
        "const window={};"
        "new Function('window', src)(window);"
        "const P=window.MYONLPerf;"
        "const out=(()=>{" + expr + "})();"
        "process.stdout.write(JSON.stringify(out));"
    )
    r = subprocess.run([node, "-e", code, str(PERF)], capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


SCAN_CASES = [
    ("@voice 林小雨_01.wav", {"op": "voice", "sound": "林小雨_01.wav"}),
    ("@cg 结局A", {"op": "cg", "name": "结局A"}),
    ("@fg 雨帘 alpha=0.6 x=-40 y=12", {"op": "fg", "name": "雨帘", "x": -40, "y": 12, "alpha": 0.6}),
    ("@fg 无", {"op": "fg", "name": "无", "x": 0, "y": 0, "alpha": 1}),
    ("@camera pan 左 2", {"op": "camera", "kind": "pan", "dir": "左", "secs": 2}),
    ("@camera zoom 1 1.4", {"op": "camera", "kind": "zoom", "from": 1, "to": 1.4}),
    ("@camera shake 0.4 12", {"op": "camera", "kind": "shake", "secs": 0.4, "amp": 12}),
    ("@camera reset 0.6", {"op": "camera", "kind": "reset", "secs": 0.6}),
    ("@transition dissolve 0.8", {"op": "transition", "kind": "dissolve", "secs": 0.8}),
    ("@transition wipe 右 0.5", {"op": "transition", "kind": "wipe", "dir": "右", "secs": 0.5}),
    ("@transition slide up 0.3", {"op": "transition", "kind": "slide", "dir": "上", "secs": 0.3}),
]


def test_scan_covers_five_ops():
    got = _node("return " + json.dumps([c[0] for c in SCAN_CASES]) + ".map(s=>P.scan(s))")
    for (src, want), have in zip(SCAN_CASES, got):
        for k, v in want.items():
            assert have and have.get(k) == v, (src, k, have)


def test_scan_ignores_unknown_lines():
    lines = ["@bg 教室.png", "@ 旁白 今天下雨。", "@show 林小雨 微笑", "# 注释", "@camera roll 2", "@voice"]
    got = _node("return " + json.dumps(lines) + ".map(s=>P.scan(s))")
    assert got == [None, None, None, None, None, None]


def test_line_round_trip():
    # 语义等价即可：参数顺序按「先位置后透明度」重排，不强求逐字相同
    for src, want in SCAN_CASES:
        got = _node("return " + json.dumps(src) + ".split('\\n').map(s=>P.scan(P.line(P.scan(s))))")
        for k, v in want.items():
            assert got[0] and got[0].get(k) == v, (src, k, got[0])
    # 规范写法（新建一条时落进文本里的样子）
    canon = _node("return P.line({op:'fg',name:'雨帘',x:-40,y:12,alpha:0.6})")
    assert canon == "@fg 雨帘 x=-40 y=12 alpha=0.6"


def test_fg_writes_only_non_default_params():
    got = _node(
        "return ["
        "P.line({op:'fg',name:'雨帘',x:0,y:0,alpha:1}),"
        "P.line({op:'fg',name:'雨帘',x:30,y:0,alpha:1}),"
        "P.line({op:'fg',name:'雨帘',x:0,y:0,alpha:1.7}),"
        "P.line({op:'fg',name:'雨帘',x:0,y:0,alpha:-0.3})]"
    )
    # 1.7 被夹到 1（等于缺省，不写参数）；-0.3 夹到 0（写出来）
    assert got == ["@fg 雨帘", "@fg 雨帘 x=30", "@fg 雨帘", "@fg 雨帘 alpha=0"]


def test_fix_voices_puts_voice_after_say():
    lines = ["@label start", "@bg 教室.png", "@voice a.wav", "@[林小雨] 你来了。", "@end"]
    got = _node("return P.fixVoices(" + json.dumps(lines) + ")")
    assert got["lines"] == ["@label start", "@bg 教室.png", "@[林小雨] 你来了。", "@voice a.wav", "@end"]
    assert got["moved"] == 1 and got["dropped"] == 0


def test_fix_voices_drops_voice_without_say():
    lines = ["@label start", "@bg 教室.png", "@voice a.wav", "@end"]
    got = _node("return P.fixVoices(" + json.dumps(lines) + ")")
    assert "@voice a.wav" not in got["lines"] and got["dropped"] == 1


def test_scene_hooks_present():
    assert "window.MYONLPerf.scan(t)" in SCENE
    assert "window.MYONLPerf.render(model" in SCENE
    assert "model.newPerf = window.MYONLPerf.read(formEl, model)" in SCENE
    assert "var pl = window.MYONLPerf.line(p)" in SCENE
    assert "window.MYONLPerf.fixVoices(outSeg)" in SCENE
    # 旧行必须真的被清掉，否则同一场里会出现两条同名演出
    assert r'/^@(voice|cg|fg|camera|transition|anim)\b/.test(seg[pz])) seg[pz] = null' in SCENE


def test_perf_file_is_shipped():
    html = (ROOT / "editor" / "index.html").read_text(encoding="utf-8")
    assert "/editor_perf.js" in html
    budget = (ROOT / "tests" / "test_p173_file_budget.py").read_text(encoding="utf-8")
    assert '"editor/editor_perf.js"' in budget



def test_render_makes_a_real_form_for_each_op():
    model = {"perf": [
        {"op": "voice", "sound": "a.wav"},
        {"op": "cg", "name": "结局A"},
        {"op": "fg", "name": "雨帘", "x": -40, "y": 12, "alpha": 0.6},
        {"op": "camera", "kind": "zoom", "from": 1, "to": 1.4},
        {"op": "transition", "kind": "wipe", "dir": "右", "secs": 0.5},
    ]}
    html = _node("return P.render(" + json.dumps(model) + ", {images:['教室.png'],audios:['a.wav'],videos:[]})")
    # 五条各一张卡，控件齐全
    assert html.count('class="sf-perf"') == 5
    for cls in ["sf-p-sound", "sf-p-name", "sf-p-x", "sf-p-y", "sf-p-alpha", "sf-p-from", "sf-p-to", "sf-p-dir", "sf-p-secs", "sf-p-kind"]:
        assert cls in html, cls
    assert html.count("sf-p-add") == 6   # P274 加第 6 条：补间
    assert 'data-op="transition"' in html and "@transition wipe 右 0.5" in html
    # 默认折叠：不占台词的位置；加过东西后靠 model.perfOpen 保持展开
    assert '<details class="sf-fold sf-perf-box">' in html
    opened = _node("return P.render({perf:[],perfOpen:true}, {})")
    assert '<details class="sf-fold sf-perf-box" open>' in opened


def test_perf_css_keeps_44px_targets():
    css = (ROOT / "editor" / "perf.css").read_text(encoding="utf-8")
    assert "#sceneForm .sf-prow input, #sceneForm .sf-prow select" in css   # 权重压过全局输入框
    assert "height: 44px" in css
    assert ".sf-padd .sf-p-add { min-height: 44px; }" in css
    assert ".sf-perf .sf-del, .sf-perf .sf-p-clear { flex: 0 0 auto; min-width: 44px; height: 44px; padding: 0 10px; }" in css
