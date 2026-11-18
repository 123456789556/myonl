"""P100：手机/平板上的两件"只有在真机上才会炸"的事。

一是 @video 帧池 —— 一帧 1080×1920 解出来 8 MB 出头，10 秒 24fps 就是 240 帧，
无限缓存能在循环第一轮吃掉 2 GB，手机上表现是白屏。所以必须：有上限、进入预热、切走释放。
二是存档格里的台词 — 横屏三列比竖屏两列窄，原来按"截 16 个字"写死，中文字会横着压到隔壁格子。

这两条都是纯 JS 行为，pytest 只能在源码层钉住"机制还在"（真跑靠 web/test 与真机验收）。
"""
from pathlib import Path
import re

import pytest

pytestmark = [pytest.mark.unit]

ROOT = Path(__file__).resolve().parents[1]
PLAYER = ROOT / "web" / "myonl-player.js"


def _src() -> str:
    return PLAYER.read_text(encoding="utf-8")


def _case(src: str, name: str, next_name: str) -> str:
    """抠出 switch 里某个 case 到下一个 case 之间的代码，避免全文件瞎撞。"""
    start = src.index(f'case "{name}"')
    end = src.index(f'case "{next_name}"', start)
    return src[start:end]


def test_video_cache_is_bounded_not_unbounded():
    """帧缓存必须是"留最近 N 帧"，不能是普通对象无限塞。"""
    src = _src()
    assert "const VIDEO_KEEP" in src
    # 淘汰真的在跑：超上限就从最旧的开始删
    assert "while (videoKeys.length > VIDEO_KEEP)" in src


def test_video_cache_also_capped_by_bytes():
    """帧数上限拦不住 1080p：14 帧 × 8 MB ≈ 110 MB，手机上照样被杀。

    所以帧数之外还要有字节上限。同时必须至少留 2 帧 ——
    正在播的那一帧被踢掉，画面就黑一下。
    """
    src = _src()
    assert "const VIDEO_KEEP_BYTES" in src, "只有帧数上限，没有字节上限"
    assert "while (bytes > VIDEO_KEEP_BYTES" in src, "字节上限没接进淘汰"
    assert "videoKeys.length > 2" in src, "字节上限必须保住正在播的两帧"


def test_video_warms_on_entry_and_releases_on_bg():
    """进 @video 预热头几帧（否则黑一下），@bg 接管时整片释放。"""
    src = _src()
    video_case = _case(src, "video", "camera")
    assert "warmVideo()" in video_case
    bg_case = _case(src, "bg", "cg")
    assert "dropVideoCache()" in bg_case
    assert "function warmVideo" in src
    assert "function dropVideoCache" in src


def test_video_clock_restarts_after_load():
    """读档续上视频必须重设 t0 —— 存档里那个时间戳会把帧号跳到一个随机帧上。"""
    src = _src()
    # 两个入口（next 里补画面、读档按钮）都要重设
    assert src.count("state.video.t0 = performance.now()") >= 2
    assert "state.video = vm.state.video ? Object.assign({}, vm.state.video) : null" in src


def test_slot_text_is_measured_not_char_counted():
    """存档格台词按真实内宽收，不再 hard slice(0, 16)。"""
    src = _src()
    assert "function ellipsisTo" in src
    assert "slice(0, 16)" not in src


def test_missing_video_sequence_does_not_black_screen():
    """工程里没这个视频名时，返回 null 让静态背景顶上，而不是把背景画黑。"""
    src = _src()
    assert "function videoSeq" in src
    seq = src[src.index("function videoSeq"):src.index("function videoLoad")]
    assert "return (seq && seq.length) ? seq : null;" in seq


def test_readme_matches_what_ships():
    """README 是门面，别让它挂着旧的发布号 / 旧的测试数，也别让它自相矛盾。

    注意：这里**不写死某个 apk 编号**——写死的话每发一版都得改测试，
    等于自己给自己上锁。真正要守的是「徽章和下载链指向同一个包」。
    """
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    # v1 起 tag 就是版本号，旧的 apk-N 也认 —— 守的始终是「徽章和下载链同一个包」
    dl = re.search(r"releases/download/((?:apk-\d+)|(?:v\d+\.\d+\.\d+))/MYONL-\1\.apk", readme)
    assert dl, "README 没给安卓包的下载入口"
    badge = re.search(r"release-((?:apk--\d+)|(?:v\d+\.\d+\.\d+))", readme)
    assert badge, "README 缺 Release 徽章"
    assert badge.group(1) == dl.group(1), "徽章和下载链指向的不是同一个包"
    nums = [int(n) for n in re.findall(r"(\d{4})\s*passed", readme)]
    assert nums and max(nums) >= 1100, "README 里的测试数还停在几年前那个数"
    assert "v1.0.0--rc15" not in readme, "release 徽章还是 rc15"
    assert "docs/images/m-game.jpg" in readme, "界面还是桌面截图"
    # 图确实在仓库里（README 挂空图比挂旧图更糟）
    for name in ("m-game.jpg", "m-video.jpg", "t-game.jpg", "t-game-l.jpg"):
        assert (ROOT / "docs" / "images" / name).is_file(), f"缺图 {name}"
