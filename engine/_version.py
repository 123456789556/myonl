"""版本号的唯一真源。

为什么单独一个文件：以前有三处各自写自己的版本 ——
  `engine/__init__.py` 的 `__version__`（桌面状态栏读它）停在 `1.0.0rc24`，
  `tools/build_release_zip.py` 的 `DEFAULT_VERSION` 停在 `v1.0.0-rc19`，
  git tag 才是真正发出去的那个（`v1.2.31`、`v1.2.32`…）。
三个数字互不校验，结果是同一份代码在三个地方自称三个版本，用户报 bug 时
两边说的不是同一版。

现在只有这一行是真源：`VERSION`。其余全部从这里推导：
  - `engine.__version__`（`/api/version` → 桌面状态栏「MYONL v…」）
  - `tools/build_release_zip.py` 的 DEFAULT_VERSION（exe 发行 zip 名）
  - CI 在 tag 推送时拿 tag 与它比对，不一致直接红，不发出一个对不上号的包

发版流程：改这一行 → 提交 → 打同名 tag → 推。**数字必须与 tag 完全一致**，
`tests/test_version_sync.py` 与 `.github/workflows/release-version-gate.yml` 两道都守这一条。

改这里不需要动 `engine/editor.py`（3063 行 = 预算上限，零余量）。
"""
from __future__ import annotations

# 与 git tag 完全一致（tag 去掉前缀 v）。三段的 x.y.z，不许带 rc/beta 后缀：
# Android 的 versionName 与 exe 安装包名都直接拿它，带后缀会导致两台设备显示的
# 版本号对不上，也违背「exe 与 apk 匹配接轨」。
VERSION = "1.2.54"
