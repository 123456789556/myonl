"""作品体积体检。

为什么单独一层：作品要能长大。现在导出是"所有素材 base64 内联进单个 HTML"，
小作品没问题，一旦语音、高清 CG、视频进来，这条路会在某个体积上直接崩掉
（浏览器加载几 GB 的 HTML 没有商量余地）。

所以先把"这个作品现在有多大、还能不能单文件发"算清楚，
让导出流程按档位说话，而不是闷头生成一个打不开的文件。

分层依据（阈值来自实际渠道约束，不是拍脑袋）：
- 单文件 HTML：30 MB 以内，超过后打开就已经明显变慢，手机低端机更差
- APK 内嵌：300 MB 以内，国内渠道普遍卡 100-200 MB 上传，但直接装不受限；
  Google Play 的 AAB 基础包 200 MB、资源包另算，这里取 300 MB 当上限
- 外置资源包：2 GB 以内，靠首次启动解压到应用私有目录
- 再往上就是商业游戏的体量（原神 15 GB 级），需要下载器 + 热更，不是这一层能解决的
"""

import os

# (上限字节数, 档位名, 给作者的话)
BANDS = [
    (30 << 20, "single", "单个 .html，微信或 QQ 直接发出去"),
    (300 << 20, "apk", "打成 APK 装到手机上"),
    (2 << 30, "external", "APK + 外置资源包，首次启动解压"),
    (None, "download", "要下载器和资源热更了，手机上这套跑不动"),
]

# 剧本本体永远很小，单独统计，不参与"能不能单文件发"的判断
SCRIPT_NAMES = {"script.gal", "config.json"}

ASSET_DIRS = {
    "images": "图片",
    "audio": "音频",
    "video": "视频",
}


def human_size(n: int) -> str:
    if n < 1024:
        return "%d B" % n
    if n < 1024 * 1024:
        return "%.1f KB" % (n / 1024)
    if n < 1024 * 1024 * 1024:
        return "%.1f MB" % (n / (1024 * 1024))
    return "%.2f GB" % (n / (1024 * 1024 * 1024))


def band_for(total: int):
    for limit, name, advice in BANDS:
        if limit is None or total <= limit:
            return name, advice
    return BANDS[-1][1], BANDS[-1][2]


def scan(root: str) -> dict:
    """扫一遍作品目录。

    返回的 bytes 只算素材（图片/音频/视频/其它），不含剧本与配置——
    因为剧本再长也就几百 KB，把它算进"能不能单文件发"的判断只会误导人。
    """
    counts = {}
    bytes_by_kind = {}
    total_assets = 0
    script_bytes = 0
    largest = {"path": "", "bytes": 0}

    for dirpath, dirnames, filenames in os.walk(root):
        # 跳过编辑器和导出产物，它们不是作品内容
        dirnames[:] = [d for d in dirnames if d not in (
            ".git", "dist", "node_modules", "__pycache__",
        )]
        for name in filenames:
            path = os.path.join(dirpath, name)
            try:
                size = os.path.getsize(path)
            except OSError:
                continue
            rel = os.path.relpath(path, root).replace(os.sep, "/")
            if name in SCRIPT_NAMES or rel.startswith("docs/"):
                script_bytes += size
                continue

            kind = "其它"
            for d, label in ASSET_DIRS.items():
                if ("/" + d + "/") in ("/" + rel) or rel.startswith(d + "/"):
                    kind = label
                    break
            counts[kind] = counts.get(kind, 0) + 1
            bytes_by_kind[kind] = bytes_by_kind.get(kind, 0) + size
            total_assets += size
            if size > largest["bytes"]:
                largest = {"path": rel, "bytes": size}

    band, advice = band_for(total_assets)
    return {
        "root": root,
        "asset_bytes": total_assets,
        "asset_human": human_size(total_assets),
        "script_bytes": script_bytes,
        "script_human": human_size(script_bytes),
        "counts": counts,
        "bytes_by_kind": bytes_by_kind,
        "largest": largest,
        "largest_human": human_size(largest["bytes"]) if largest["path"] else "",
        "band": band,
        "advice": advice,
    }
