# -*- coding: utf-8 -*-
"""MYONL 多语言（i18n）模块。

只覆盖引擎 UI 层文案（标题菜单/快捷栏/设置/回看/提示），剧本 DSL 与对话文本不做翻译。

设计：
  - locale/<lang>.json 存「原文 → 译文」映射；zh-CN 是恒等映射（key=value）
  - t(text, lang) 返回译文；缺键回落原文；缺 locale 文件回落原文
  - lang 来自 settings.json 的 lang 键（默认 zh-CN，老配置零影响）
  - 全标准库，零第三方依赖
"""
from __future__ import annotations

import json
import os

# locale 目录：engine/i18n.py 同级的 ../locale
_LOCALE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "locale")

# 支持的语言代码（与 locale/*.json 文件名对应）
SUPPORTED_LANGS = ("zh-CN", "en-US")
DEFAULT_LANG = "zh-CN"

# 进程内缓存：{lang: dict}；首次访问加载，后续直接用
_cache: dict[str, dict[str, str]] = {}


def _load(lang: str) -> dict[str, str]:
    """加载 locale/<lang>.json；失败返回空 dict（回落原文）。"""
    if lang in _cache:
        return _cache[lang]
    path = os.path.join(_LOCALE_DIR, f"{lang}.json")
    table: dict[str, str] = {}
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, dict):
                table = {str(k): str(v) for k, v in raw.items()}
        except (OSError, ValueError):
            table = {}
    _cache[lang] = table
    return table


def t(text: str, lang: str = DEFAULT_LANG) -> str:
    """翻译 text 到 lang；缺键/缺文件返回原文。

    空串直接返回空串，避免查表开销。
    """
    if not text:
        return text
    if lang == DEFAULT_LANG:
        return text  # zh-CN 恒等，跳过查表
    table = _load(lang)
    return table.get(text, text)


def reset_cache() -> None:
    """清空翻译缓存（locale 文件热更新时调用）。"""
    _cache.clear()
