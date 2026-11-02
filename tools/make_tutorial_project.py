# -*- coding: utf-8 -*-
"""生成「教程示例」工程（M1：引擎可被使用）。

产物：games/教程示例/ —— 一个带注释的最小工程，陌生人打开就能改：
- script.gal：11 种指令 / 分支 / 变量条件 / 一小段双结局，注释写给完全不懂引擎的人
- images：程序生成的占位背景与立绘（可换成自己的）
- config/settings/gallery/pack_config：与标准示例同构，打包即可出 exe

为什么用脚本生成而不是手搓提交：保证可复现，且素材是程序占位、无版权问题。

用法：py -3 tools/make_tutorial_project.py [--force]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "games" / "教程示例"

SCRIPT = '''# 教程示例 · 3 分钟改出你的第一幕
#
# 怎么用：把下面的台词改成你的 → 保存 → 右侧预览立即可见 → 满意后点打包。
# 这个工程故意只演示最常用的 11 种指令，全部列在这里：
#   @character 登记角色名/颜色   @bg 换背景        @show 显示立绘
#   @ 台词（角色名 + 内容）       @choice 分支选项   @set 改变量
#   @if 条件                     @jump 跳转        @label 标签（跳转目标）
#   @wait 等待几秒                @end 结束
#
# 想换成自己的素材：把 images/ 里的 png 换成同名图片即可（尺寸 1280x720 / 512x1024 最佳）。

@character 林晚 #ffb3c8
@character 我 #8ecae6

@bg bg_教室
@set 好感 = 1

@label start
@ 旁白 放学后的教室只剩两个人。
@show 林晚 微笑
@ 林晚 你还不走？
@ 我 在等一个人。
@ 林晚 ……谁啊？
@choice:
    > 说实话 -> 坦白
    > 岔开话题 -> 岔开

@label 坦白
@set 好感 += 2
@ 林晚 那……一起走吧。
@jump 结局

@label 岔开
@ 我 在等雨停。
@ 林晚 今天没下雨哦。
@jump 结局

@label 结局
@bg bg_天台
@if 好感 >= 3:
    @ 旁白 晚风很轻，谁也没有先开口。
@wait 1.0
@ 旁白 有些话今天没说，明天还会说。
@end
'''


def _dump(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="生成教程示例工程")
    ap.add_argument("--force", action="store_true", help="已存在时覆盖脚本与配置")
    args = ap.parse_args(argv)

    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    sys.path.insert(0, str(ROOT))

    print(f"目标：{PROJECT}")
    PROJECT.mkdir(parents=True, exist_ok=True)
    (PROJECT / "images").mkdir(exist_ok=True)

    # 1) 剧本
    script_path = PROJECT / "script.gal"
    if script_path.exists() and not args.force:
        print("  跳过 script.gal（已存在，--force 覆盖）")
    else:
        script_path.write_text(SCRIPT, encoding="utf-8")
        print("  写入 script.gal")

    # 2) 配置（沿用标准示例的观感，只换标题）
    ref = ROOT / "games" / "标准示例" / "config.json"
    cfg = json.loads(ref.read_text(encoding="utf-8"))
    cfg["window_title"] = "教程示例"
    _dump(PROJECT / "config.json", cfg)
    print("  写入 config.json")

    _dump(PROJECT / "settings.json", {
        "_说明": "玩家偏好（引擎可写）。title 显示在标题画面；splash=true 时若有开场.gal 会先播序幕。",
        "title": "教程示例",
        "splash": False,
    })
    _dump(PROJECT / "gallery_config.json", {
        "_说明": "画廊配置：键=画廊格名，值=点开后轮播的高清场景序列。空对象表示暂无画廊。",
    })
    _dump(PROJECT / "pack_config.json", {
        "_说明": "打包档案（python pack.py <游戏目录> 自动读取）：上线前把游戏名、图标、运营号改成你自己的。",
        "schema": 1,
        "game_name": "教程示例",
        "version": "1.0.0",
        "icon": "icon.png",
        "publisher": {"name": "个人开发者", "account_id": "MYONL-DEMO",
                      "channel": "本地发行", "contact": ""},
        "description": "用 MYONL 引擎做的第一个游戏（教程示例）。",
        "release_notes": "首个版本",
    })
    print("  写入 settings/gallery/pack_config")

    # 3) 占位素材（程序生成，无版权）
    from engine.newgame import make_default_icon, make_placeholder_assets

    made = make_placeholder_assets(PROJECT, overwrite=True)
    make_default_icon(PROJECT, overwrite=True)
    print(f"  生成占位素材 {len(made)} 张 + icon.png")

    # 4) 自检：预检零缺素材
    from engine.demo import _precheck_resources

    _precheck_resources(str(script_path), str(PROJECT))
    print("完成：python -m engine.editor --project games/教程示例 即可打开")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
