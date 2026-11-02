"""P51-T6：剧本 / 配置热重载的「探测层」（八大方向 5.1 / 5.2）。

只回答一个问题：自上次记录以来，这些文件变了没有？
- 按 mtime 轮询，默认 500ms，只 stat 不读内容，开销可忽略；
- 不负责解析/应用：重载失败回退由调用方（demo 主循环）掌握，便于单测；
- 新增文件（例如新加一个 @include）不会自动进监视列表：调用方重载成功后用 set_paths() 重新登记。

用法（demo 主循环）：
    watch = FileWatch(rt.script_files())
    if watch.changed(now_ms):
        top = parse_file(script_path)     # 解析失败 → 保留旧状态，只中文告警
        rt.reload(top)
        watch.set_paths(rt.script_files())
"""
from __future__ import annotations

import os

DEFAULT_INTERVAL_MS = 500


def _mtime(path: str):
    """文件 mtime（纳秒）；不存在 / 不可读返回 None（文件被删也算一次变化）。"""
    try:
        return os.stat(path).st_mtime_ns
    except OSError:
        return None


class FileWatch:
    """一组文件的 mtime 监视器：到点轮询一次，回答「有没有变化」。"""

    def __init__(self, paths=None, interval_ms: int = DEFAULT_INTERVAL_MS):
        self.interval_ms = max(0, int(interval_ms))
        self._paths: list[str] = []
        self._mtimes: dict = {}
        self._next_poll = -1
        self.set_paths(paths or [])

    def set_paths(self, paths) -> None:
        """重新登记监视文件，并立即记录当前 mtime（不会把「刚登记」当成变化）。"""
        uniq: list[str] = []
        for path in paths or []:
            text = os.path.abspath(str(path))
            if text and text not in uniq:
                uniq.append(text)
        self._paths = uniq
        self._mtimes = {p: _mtime(p) for p in uniq}
        self._next_poll = -1

    def paths(self) -> list[str]:
        return list(self._paths)

    def changed(self, now_ms: int) -> bool:
        """到轮询点时检查一次：任一文件 mtime 变化（含被删/新建）返回 True。

        未到轮询点直接返回 False（不动 _mtimes），保证调用方可以每帧调用。
        """
        if not self._paths:
            return False
        if now_ms < self._next_poll:
            return False
        self._next_poll = now_ms + self.interval_ms
        hit = False
        for path in self._paths:
            current = _mtime(path)
            if self._mtimes.get(path) != current:
                self._mtimes[path] = current
                hit = True
        return hit
