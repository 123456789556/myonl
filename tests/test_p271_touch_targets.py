"""P271：剧本页里按不到的小钮补命中区，并修「× 被拖拽把手盖住」的真 bug。

量出来的（Playwright，844×390，elementFromPoint 打点）：
    ×（预览角上）30×30，位置 right:6，正好压在预览右边界那条 22px 把手上 —— 中心点 elementFromPoint
      落到 mPrevGrip，等于看得见点不动
    ▶ 36×44、⋯ 38×44、＋加一句 67×38、真实渲染预览 91×26

修法：不改视觉尺寸，只给这些钮加一层透明命中区（44 的方框），× 往内挪到 right:34 让开把手。
"""

from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "editor" / "editor.css").read_text(encoding="utf-8")

TINY = ("#mStageBtn", "#mTopPreview", ".menubar .scn-more", "#sfAddSay", "#sfAddChar", "#sfAddOpt", ".sf-real-btn", ".m-codehelp")


def test_hit_area_overlay_covers_all_tiny_buttons():
    # 命中区只加透明 ::after，width/height 取 max(44, 自身)，视觉尺寸不变
    idx = CSS.index("/* P271 触控命中区")
    seg = CSS[idx:]
    assert "width: max(44px, 100%); height: max(44px, 100%);" in seg
    for sel in TINY:
        assert sel in seg, sel


def test_absolute_buttons_keep_their_position():
    # 最大那条坑：不分青红皂白给 ::after 的宿主加 position:relative，会把绝对定位的 × 挪进流里
    idx = CSS.index("/* P271 触控命中区")
    seg = CSS[idx:]
    static_line = [l for l in seg.splitlines() if "position: relative" in l][0]
    assert "#mStageBtn" not in static_line
    assert ".sf-real-btn" not in static_line


def test_stage_close_button_moved_off_the_grip():
    assert ".m-stage-btn { position: absolute; right: 34px; top: 6px;" in CSS
    # 原来 right:6 的写法必须消失，否则又压回把手上
    assert ".m-stage-btn { position: absolute; right: 6px;" not in CSS
    # × 只有一个字，不许折行（溢出审计报过「折行」）
    line = [l for l in CSS.splitlines() if l.strip().startswith(".m-stage-btn {")][0]
    assert "white-space: nowrap" in line
