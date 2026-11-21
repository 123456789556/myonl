# -*- coding: utf-8 -*-
"""P0-B：editor_lint.js 的行为测试（node VM 实跑，不是正则扫源码）。

为什么能这么测：editor_lint.js 是纯函数，不碰 DOM、不读 localStorage，
所以把它丢进 node 的 vm 上下文、只注入一个空 window 就能跑。
这条路项目里早就有（test_p114_js_kernel / test_p115_value_aliases / test_p130_hardening
都是 shutil.which("node") + subprocess），这里沿用同一口径：没有 node 就 skip，不假装通过。

守两件事：
1. 原 5 条规则行为不变（回归）；
2. 新增第 6 条 asset-missing：缺素材要报、存在不报、不传清单不报、@fg 无 不报、
   写 `教室.png` 也认、行尾注释不参与判断。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

ROOT = Path(__file__).resolve().parents[1]
LINT = ROOT / "editor" / "editor_lint.js"

# 一次 node 进程跑完所有用例：读 stdin 的 JSON，回 stdout 的 JSON。
RUNNER = r"""
const fs = require('fs'), vm = require('vm');
const code = fs.readFileSync(process.env.MYONL_LINT_PATH, 'utf8');
const ctx = { window: {}, console };
vm.createContext(ctx);
vm.runInContext(code, ctx, { filename: 'editor_lint.js' });
const L = ctx.window.MYONLLint;
let raw = '';
process.stdin.on('data', d => raw += d);
process.stdin.on('end', () => {
  const cases = JSON.parse(raw);
  const out = cases.map(c => {
    const r = L.run(c.text, c.opts || undefined);
    return { issues: r.issues, counts: r.counts,
             repl: c.repl ? L.replace(c.text, c.repl[0], c.repl[1], c.repl[2] || {}) : null };
  });
  process.stdout.write(JSON.stringify(out));
});
"""


def _run(cases: list[dict]) -> list[dict]:
    node = shutil.which("node")
    if not node:
        pytest.skip("这台机器没有 node，跳过 lint 行为实测")
    p = subprocess.run(
        [node, "-e", RUNNER],
        input=json.dumps(cases, ensure_ascii=False),
        capture_output=True, text=True, encoding="utf-8", timeout=60, cwd=str(ROOT),
        env={**os.environ, "MYONL_LINT_PATH": str(LINT), "PYTHONIOENCODING": "utf-8"},
    )
    assert p.returncode == 0, p.stderr[:800]
    return json.loads(p.stdout.strip())


def _codes(res: dict) -> list[str]:
    return [i["code"] for i in res["issues"]]


FIVE = """@character 小满 #ffcc00
@character 阿零 #99ccff
@label start
@ 小满 我们去教室。
@ 未登记的人 这句会被当旁白。
@[没登记的名字] 这句渲染正常但角色库里没有。
@jump 不存在的地方
@label 没人跳的幕
@ 小满 到这儿了。
@end"""


def test_原五条规则都还在():
    res = _run([{"text": FIVE}])[0]
    got = set(_codes(res))
    assert {"unregistered", "bracket-stray", "char-unused", "jump-broken", "label-orphan"} <= got, got
    assert res["counts"]["error"] >= 1


def test_不传素材清单时新规则静默():
    """纯文本分析场景（replace 内部也走 scan）不该因为没有素材库而报缺素材。"""
    res = _run([{"text": "@bg 教室\n@music 主题曲\n@ 旁白 走。\n@end"}])[0]
    assert "asset-missing" not in _codes(res)


def test_缺素材要报且带行号():
    text = "@label start\n@bg 教室\n@music 主题曲\n@ 旁白 走。\n@end"
    res = _run([{"text": text, "opts": {"assets": ["主题曲"]}}])[0]
    miss = [i for i in res["issues"] if i["code"] == "asset-missing"]
    assert len(miss) == 1, res["issues"]
    assert miss[0]["name"] == "教室"
    assert miss[0]["line"] == 2, miss[0]
    assert miss[0]["level"] == "warn"
    assert miss[0]["scene"] == "start"


def test_存在的不报_没有假阳性():
    text = ("@label start\n@bg 教室\n@cg 回忆\n@fg 雨\n@music 主题曲\n"
            "@sfx 开门\n@voice 第一句\n@video 片头\n@ 旁白 走。\n@end")
    assets = ["教室", "回忆", "雨", "主题曲", "开门", "第一句", "片头"]
    res = _run([{"text": text, "opts": {"assets": assets}}])[0]
    assert "asset-missing" not in _codes(res), res["issues"]


def test_清除关键字与扩展名与行尾注释():
    text = ("@label start\n@fg 无\n@fg none\n@bg 教室.png\n"
            "@music 主题曲 # 这里是注释\n@ 旁白 走。\n@end")
    res = _run([{"text": text, "opts": {"assets": ["教室", "主题曲"]}}])[0]
    assert "asset-missing" not in _codes(res), res["issues"]


def test_角色指令不算素材引用():
    """@show / @hide 的首 token 是角色名，不能拿素材清单去判它。"""
    text = "@character 小满 #ffcc00\n@label start\n@show 小满\n@hide 小满\n@ 小满 在。\n@end"
    res = _run([{"text": text, "opts": {"assets": ["教室"]}}])[0]
    assert "asset-missing" not in _codes(res), res["issues"]


def test_替换行为不受影响():
    """replace 内部 scan 不传 assets：加了第 6 条规则也不能改替换结果。"""
    text = "@label 教室\n@bg 教室\n@ 小满 我去教室。\n@end"
    res = _run([{"text": text, "repl": ["教室", "天台"]}])[0]
    assert res["repl"]["count"] == 1, res["repl"]
    assert "@label 教室" in res["repl"]["text"]
    assert "@bg 教室" in res["repl"]["text"]
    assert "我去天台。" in res["repl"]["text"]
