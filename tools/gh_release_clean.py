#!/usr/bin/env python3
"""清理 GitHub Release：只留最近几个安卓包，旧的连 tag 一起删。

为什么要这个脚本：GitHub 插件（github-remote）没有删 Release 的能力，本机也没装 gh CLI，
所以 apk-1 / apk-2 … 这些早期包一直堆在 Releases 页面上，玩家点进去看见一堆不确定能不能
用的旧包。CI 里每次打 tag 会自动清一次（见 .github/workflows/android-apk.yml），
这个脚本是给"手动补一刀"和"排查为什么没删"用的。

用法（只读列举，不需要 token）：
    py -3 tools\\gh_release_clean.py --list

真正删除（需要提交 token，建议 scope 只给 repo）：
    set GITHUB_TOKEN=ghp_xxx
    py -3 tools\\gh_release_clean.py --prune --keep 5 --dry-run     # 先看会删谁
    py -3 tools\\gh_release_clean.py --prune --keep 5 --yes         # 真删

规则：
  * 只处理 tag 形如 apk-<数字> 的 Release，其它 Release 一律不碰；
  * 按数字大小排序（apk-10 排在 apk-9 前面，字符串排序会排错），保留最大的 KEEP 个；
  * 删 Release 时连 tag 一起删（--cleanup），否则 tag 还在，下次又会有人以为是新包；
  * 永远不删"最新那一个"（就算 KEEP 传 0 也至少留 1 个）。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request

REPO = "123456789556/myonl"
API = "https://api.github.com"
# 两类可以有多个历史包的 Release：安卓包 apk-N、Windows 发行候选 v1.0.0-rcN。
# 分组各自保留最近 keep 个 —— 安卓包和桌面包的"最近"不是一回事，不能混着排。
FAMILIES = [
    ("apk", re.compile(r"^apk-(\d+)$"), "安卓包", 3),
    ("rc", re.compile(r"^v1\.0\.0-rc(\d+)$"), "Windows 发行候选", 1),
]


def _req(method: str, path: str, token: str | None) -> tuple[int, object]:
    url = path if path.startswith("http") else API + path
    data = b"" if method in ("DELETE", "POST") else None
    r = urllib.request.Request(url, method=method, data=data)
    r.add_header("Accept", "application/vnd.github+json")
    r.add_header("User-Agent", "myonl-release-clean")
    if token:
        r.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            body = resp.read()
            return resp.status, (json.loads(body) if body else {})
    except urllib.error.HTTPError as e:
        body = e.read()
        try:
            detail = json.loads(body)
        except Exception:
            detail = body.decode("utf-8", "ignore")[:200]
        return e.code, detail


def list_releases(token: str | None, repo: str) -> list[dict]:
    """拿全量 Release（REST 一页 30 条，翻到空为止）。"""
    out: list[dict] = []
    page = 1
    while True:
        code, data = _req("GET", f"/repos/{repo}/releases?per_page=30&page={page}", token)
        if code != 200:
            print(f"取 Release 失败 HTTP {code}: {data}")
            sys.exit(2 if not token else 1)
        if not isinstance(data, list) or not data:
            break
        out.extend(data)
        page += 1
        if page > 20:      # 兜底，别无限翻
            break
    return out


def tag_no(tag: str) -> tuple[str | None, int | None]:
    """把一个 tag 归到某个家族，并取它的编号。"""
    for key, rx, _label, _keep in FAMILIES:
        m = rx.match(tag or "")
        if m:
            return key, int(m.group(1))
    return None, None


def main() -> int:
    ap = argparse.ArgumentParser(description="清理 GitHub Release（每类只留最近几个）")
    ap.add_argument("--repo", default=REPO)
    ap.add_argument("--token", default=None, help="默认读 GITHUB_TOKEN / GH_TOKEN")
    ap.add_argument("--list", action="store_true", help="只列出来看看")
    ap.add_argument("--prune", action="store_true", help="按保留数删掉多余的")
    ap.add_argument("--keep", type=int, default=None,
                    help="两类共用同一个保留数；0 表示这一类全清（默认安卓 3 / Windows 1）")
    ap.add_argument("--keep-apk", type=int, default=None, help="只针对安卓包")
    ap.add_argument("--keep-rc", type=int, default=None, help="只针对 Windows 发行候选")
    ap.add_argument("--dry-run", action="store_true", help="只说会删谁，不动手")
    ap.add_argument("--yes", action="store_true", help="确认真删")
    args = ap.parse_args()

    token = args.token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    rels = list_releases(token, args.repo)

    groups: dict[str, list[tuple[int, dict]]] = {k: [] for k, _, _, _ in FAMILIES}
    others: list[dict] = []
    for r in rels:
        key, n = tag_no(r.get("tag_name", ""))
        if key is None:
            others.append(r)
        else:
            groups[key].append((n, r))
    for key in groups:
        groups[key].sort(key=lambda x: x[0], reverse=True)

    # 每类各自的保留数：--keep-apk / --keep-rc 优先，其次共用的 --keep，最后用默认值。
    # 0 表示"这一类全清"，用来把过时的 Windows 包整批撤掉。
    def _keep(key: str, default_keep: int) -> int:
        v = {"apk": args.keep_apk, "rc": args.keep_rc}[key]
        if v is None:
            v = args.keep
        if v is None:
            v = default_keep
        return max(0, v)

    keep_by = {k: _keep(k, dk) for k, _, _, dk in FAMILIES}

    print(f"仓库 {args.repo}：共 {len(rels)} 个 Release")
    labels = {k: label for k, _, label, _ in FAMILIES}
    for key in groups:
        print(f"\n[{labels[key]}] {len(groups[key])} 个（保留 {keep_by[key]}）")
        for n, r in groups[key]:
            assets = ", ".join(f"{a['name']} {a['size'] / 1048576:.1f}MB" for a in r.get("assets", []))
            print(f"  {r.get('tag_name', ''):<14} {r.get('published_at', '')[:10]}  {assets or '(无附件)'}")
    if others:
        print(f"\n[不清理] {len(others)} 个")
        for r in others:
            print(f"  {r.get('tag_name', '')}")

    if args.list or not args.prune:
        if not args.prune and not args.list:
            print("\n只列举。要清理请加 --prune --yes（建议先 --dry-run）。")
        return 0

    doomed: list[dict] = []
    for key in groups:
        doomed.extend(r for _n, r in groups[key][keep_by[key]:])
    if not doomed:
        print("\n每类都不超过保留数，没有要删的。")
        return 0

    print(f"\n要删 {len(doomed)} 个：")
    for r in doomed:
        print(f"  - {r.get('tag_name', '')}  {r.get('published_at', '')[:10]}")
    if args.dry_run or not args.yes:
        print("\n（dry-run，没有真删。确认没问题再加 --yes）")
        return 0

    if not token:
        print("\n没有 token —— 无法删除。请设置 GITHUB_TOKEN（或 --token），再重跑。")
        return 3

    fails = 0
    for r in doomed:
        tag = r.get("tag_name", "")
        code, detail = _req("DELETE", f"/repos/{args.repo}/releases/{r['id']}", token)
        if code not in (204, 200):
            print(f"  删 Release {tag} 失败 HTTP {code}: {detail}")
            fails += 1
            continue
        code2, detail2 = _req("DELETE", f"/repos/{args.repo}/git/refs/tags/{tag}", token)
        # tag 可能已经被 --cleanup 删掉，404 不算失败
        print(f"  删 {tag}：" + ("好" if code2 in (204, 200) else f"tag HTTP {code2}（可能已随 Release 删掉）"))
    print(f"\n完成：成功 {len(doomed) - fails} 个，失败 {fails} 个。")
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
