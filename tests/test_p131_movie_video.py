# -*- coding: utf-8 -*-
"""P131 真视频进「幕」：静态守住冻结契约里的字面标识符。

这批断言咬的是契约（p131-movie-contract.md）里写死的函数名 / 字段名 /
文案片段，不做行为推断。另外三条线（解析器、打包器、播放器、素材库）
落地之前，对应断言会红 —— 这是预期的，不许为了变绿放宽断言。

不许起浏览器、不许联网、不许依赖真视频文件；node 不在就跳过 JS 语法门禁。
"""
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _read(*parts):
    return (ROOT.joinpath(*parts)).read_text(encoding="utf-8")


PARSER_JS = _read("engine", "parser.js")
PARSER_PY = _read("engine", "parser.py")
PACK_JS = _read("engine", "pack.js")
WEBPACK_PY = _read("engine", "webpack.py")
PLAYER = _read("web", "myonl-player.js")
OFFLINE = _read("editor", "gal_offline.js")
MANIFEST = _read("editor", "manifest.webmanifest")
SW = _read("editor", "sw.js") if (ROOT / "editor" / "sw.js").exists() else ""
INDEX_HTML = _read("editor", "index.html")
DOC_MOBILE = _read("docs", "手机端编游戏.md")
DOC_CHANGELOG = _read("docs", "CHANGELOG.md")
DOC_IMPORT = _read("docs", "素材导入指南.md")

NODE = shutil.which("node")

pytestmark = [pytest.mark.unit]


# ---------- 1. 语法：两套解析器 ----------

def test_parser_js认_video分支():
    assert 'head === "video"' in PARSER_JS or '"video"' in PARSER_JS


def test_parser_js错误文案不再把_video列进电脑端打包名单():
    # 「请到电脑端打包」那条 throw 里，拒收名单是「；」之后那一段。
    # 「手机端解析器支持：…」前面列 @video 是应该的（它现在真的支持了），所以只看拒收段。
    idx = PARSER_JS.find("请到电脑端打包")
    assert idx >= 0, "找不到「请到电脑端打包」报错文案"
    reject_list = PARSER_JS[max(0, idx - 400):idx].rsplit("；", 1)[-1]
    assert "@video" not in reject_list, "@video 还挂在手机端解析器的拒收名单里"


def test_parser_js视频IR带_file_loop_mute():
    assert "parseVideoArgs" in PARSER_JS
    assert 'op: "video"' in PARSER_JS
    assert "file: file" in PARSER_JS
    assert "loop: loop" in PARSER_JS
    assert "mute: mute" in PARSER_JS


def test_parser_py视频IR带_movie_file_loop_mute():
    start = PARSER_PY.find('if head == "video":')
    assert start >= 0, "parser.py 没有 video 分支"
    nxt = PARSER_PY.find('if head ==', start + 10)
    seg = PARSER_PY[start:nxt if nxt > 0 else start + 800]
    assert '"op": "video"' in seg
    # 注意：py 侧因 file 是公共源文件字段，真视频开关落位为 movie_file（契约字面是 file，
    # 此处按引擎线落地后的实际键名锁；两侧对齐情况回报 Organizer 核对）
    assert '"movie_file"' in seg
    assert '"loop"' in seg
    assert '"mute"' in seg


# ---------- 2. pack 数据形状 ----------

def test_pack_js带_movies与字节数():
    assert "movies" in PACK_JS
    assert "opts.movies" in PACK_JS
    assert "mime" in PACK_JS
    # 总体积要把 movies 字节算进去，返回值带 bytes 与 fileMb
    assert "bytes" in PACK_JS
    assert "fileMb" in PACK_JS


def test_webpack_py收真视频进_movies():
    assert "_collect_movie_names" in WEBPACK_PY
    assert "movies" in WEBPACK_PY
    assert "assets/movies" in WEBPACK_PY


# ---------- 3. 播放器 ----------

def test_播放器有_movie四件套():
    assert "function movieEl()" in PLAYER
    assert "function releaseMovie()" in PLAYER
    assert "function drawMovie()" in PLAYER
    assert "function warmMovie()" in PLAYER
    assert "function drawMovieFallback(" in PLAYER
    assert "movieFallback" in PLAYER


def test_MYONL_DEBUG_video读数带_movie状态():
    # 调试口对象名是 window.MYONL_DEBUG（不是 MYONL），视频读数在其 video getter 里
    assert "window.MYONL_DEBUG" in PLAYER
    start = PLAYER.find("get video()")
    assert start >= 0, "播放器没有 video 读数"
    seg = PLAYER[start:start + 900]
    assert "movie" in seg
    assert "count" in seg
    assert "readyState" in seg
    assert "paused" in seg


def test_bg分支释放视频():
    start = PLAYER.find('case "bg":')
    assert start >= 0, "播放器没有 bg 分支"
    nxt = PLAYER.find('case "cg":', start)
    seg = PLAYER[start:nxt if nxt > 0 else start + 600]
    # 帧池缓存与真视频解码句柄两件事都要放
    assert "dropVideoCache" in seg, "@bg 分支没放帧池缓存"
    assert "releaseMovie()" in seg, "@bg 分支没调 releaseMovie() 释放视频"


def test_video分支接_warmMovie():
    start = PLAYER.find('case "video":')
    assert start >= 0, "播放器没有 video 事件分支"
    seg = PLAYER[start:start + 500]
    assert "warmMovie" in seg
    assert "ev.file" in seg


def test_播放器降级与兜底文案在():
    assert "deviceMemory" in PLAYER
    assert "hardwareConcurrency" in PLAYER
    assert "720" in PLAYER
    assert "本机解不了这段视频" in PLAYER
    assert "playsinline" in PLAYER
    # 属性两种写法都认：字面属性或 setAttribute 都行，metadata 不能丢
    assert ("preload=\"metadata\"" in PLAYER or
            'setAttribute("preload", "metadata")' in PLAYER)


# ---------- 4. 手机素材库 ----------

def test_kindOf能返回_video():
    start = OFFLINE.find("function kindOf")
    assert start >= 0, "素材库没有 kindOf"
    seg = OFFLINE[start:start + 200]
    assert '"video"' in seg


def test_importShared搬收件箱素材():
    assert "importShared" in OFFLINE
    # 挂在 MYONLAssets 出口上，页面才能调到
    assert "importShared: importShared" in OFFLINE or "importShared:" in OFFLINE
    assert "inbox:" in OFFLINE


def test_素材库不再拒收真视频():
    assert "视频暂不收" not in OFFLINE
    assert "videoDataUrl" in OFFLINE
    assert '"video"' in OFFLINE
    assert "out.movies" in OFFLINE
    # 视频类型识别走 /^video\// 正则（accept 串在 index.html，属组织者那条线）
    assert "/^video\\//" in OFFLINE
    assert "这段视频超过 24 MB" in OFFLINE


# ---------- 5. 分享进来（PWA share target） ----------

def test_manifest有_share_target():
    assert "share_target" in MANIFEST
    assert "/share-target" in MANIFEST
    assert "multipart/form-data" in MANIFEST
    assert '"media"' in MANIFEST
    assert "video/*" in MANIFEST
    assert "image/*" in MANIFEST


def test_sw拦截_share_target写收件箱():
    assert "inbox:" in SW
    assert "myonl-assets" in SW
    assert '"files"' in SW
    assert "/index.html?shared=1" in SW
    assert "303" in SW
    assert "formData" in SW
    assert '"media"' in SW


def test_offline脚本注册sw并调_importShared():
    """接线落在 gal_offline.js：入口页有 <600 行硬上限，分享链路又是素材落库的一部分。"""
    assert 'register("/sw.js")' in OFFLINE
    assert "importShared" in OFFLINE
    assert "shared=" in OFFLINE
    # 入口页只留一行改动：文件选择框要能选到视频
    assert "video/*" in INDEX_HTML
    # 顺手守住入口页的行数预算（tests/test_code_health.py 也查，这里防一手堆逻辑）
    assert len(INDEX_HTML.splitlines()) < 600


# ---------- 7. 文档 ----------

def test_手机端文档写清真视频边界():
    assert "视频（真文件）" in DOC_MOBILE
    assert "24 MB" in DOC_MOBILE
    # 同时只解一个视频、切幕立刻释放、低端机自动降级
    assert "一个" in DOC_MOBILE
    assert "释放" in DOC_MOBILE
    assert "降级" in DOC_MOBILE


def test_CHANGELOG有真视频记录():
    # 这条守的是「这次视频改动在公开 CHANGELOG 有记录」，不是「必须写内部编号」。
    # 版本规则规定 P 号不进公开 CHANGELOG，所以断言改为认内容标题；写成 P131 反而会被规则判违规。
    assert "真视频进「幕」" in DOC_CHANGELOG
    assert "@video" in DOC_CHANGELOG


def test_素材指南补手机端真视频写法():
    assert "@video" in DOC_IMPORT
    assert "file" in DOC_IMPORT


# ---------- JS 语法门禁（node 不在就 skip） ----------

@pytest.mark.skipif(not NODE, reason="本机没有 node")
@pytest.mark.parametrize("path", [
    "engine/parser.js",
    "engine/pack.js",
    "web/myonl-player.js",
    "editor/gal_offline.js",
    "editor/sw.js",
])
def test_JS语法检查(path):
    r = subprocess.run([NODE, "--check", str(ROOT / path)],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, f"{path} 语法有问题：{r.stderr}"
