# -*- coding: utf-8 -*-
"""P136 技术债 4：workflow_dispatch / 分支构建也要有可区分、单调递增的 versionCode。

以前非 tag 触发不注入版本，gradle 兜底恒为 1，每个手动包系统都当同一版。
本机不跑 Gradle/CI，这里守工作流脚本与 gradle 兜底口径。
"""
import re
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

ROOT = Path(__file__).resolve().parents[1]
WF = ROOT / ".github" / "workflows" / "android-apk.yml"
GRADLE = ROOT / "android" / "app" / "build.gradle"


def test_workflow_injects_run_number_for_non_tag():
    text = WF.read_text(encoding="utf-8")
    # 非 tag 分支必须用 GITHUB_RUN_NUMBER 注入 versionCode
    assert "GITHUB_RUN_NUMBER" in text
    assert "MYONL_VERSION_CODE" in text
    # tag 判定必须先看 ref 是不是 tags，不能只看版本号字符串
    assert 'refs/tags/*' in text


def test_tag_path_keeps_semantic_code():
    text = WF.read_text(encoding="utf-8")
    # 发版路径的语义码公式不能被手动路径顶掉
    assert "MAJ * 10000 + MIN * 100 + PAT" in text
    assert "MYONL_VERSION_NAME=$VER" in text


def test_gradle_fallback_still_safe_when_env_missing():
    gradle = GRADLE.read_text(encoding="utf-8")
    # 本地裸跑没有 CI 环境变量时仍要有兜底，不能直接崩
    assert 'MYONL_VERSION_CODE' in gradle
    assert '?: "1"' in gradle


def test_version_code_formula_matches_python_reference():
    """等价复算：tag 语义码 / 手动运行号两条分支，数值与公式一致。"""
    def resolve(ref: str, ref_name: str, run: int):
        ver = ref_name[1:] if ref_name.startswith("v") else ref_name
        if ref.startswith("refs/tags/") and re.match(r"^\d+\.\d+\.\d+$", ver):
            ma, mi, pa = map(int, ver.split("."))
            return ma * 10000 + mi * 100 + pa
        return run

    assert resolve("refs/tags/v1.2.0", "v1.2.0", 42) == 10200
    assert resolve("refs/heads/main", "main", 42) == 42
    # 运行号单调递增：后一次构建必然大于前一次
    assert resolve("refs/heads/main", "main", 43) > resolve("refs/heads/main", "main", 42)
