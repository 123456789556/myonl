"""MYONL：自研视觉小说（Galgame）创作引擎。开源 MIT，完全离线。

公共 API：
- 解析：parse_text, parse_file, dump_text, dumps, loads, GalSyntaxError
- 运行时：Runtime, register_command
- 渲染：Renderer
- UI：UI
- 存档：save, load, list_slots, delete_slot, SaveError
- 配置：Config, load_config, keymap
- 表达式：evaluate, validate, ExprError
- 时间轴：Timeline, Track
- 国际化：t (translate)
- 富文本：parse as richtext_parse, FontBook
- 数据：load_settings, save_settings, find_cjk_font, DataError
"""
from .parser import GalSyntaxError, dump_text, dumps, loads, parse_file, parse_text
from .runtime import Runtime, register_command
from .renderer import Renderer
from .ui import UI
from .save import (
    SaveError, save as save_game, load as load_save,
    list_slots, delete_slot, gallery_union, load_persistent
)
from .config import Config, load as load_config, keymap
from .expr import ExprError, evaluate, validate
from .timeline import Timeline, Track
from .i18n import t
from . import richtext
from .data import (
    DataError, load_settings, save_settings, find_cjk_font,
    resolve_image, resolve_audio, data_root, game_root
)

__version__ = "1.0.0rc7"
__all__ = [
    # Parser
    "GalSyntaxError", "parse_text", "parse_file", "dump_text", "dumps", "loads",
    # Runtime
    "Runtime", "register_command",
    # Renderer
    "Renderer",
    # UI
    "UI",
    # Save
    "SaveError", "save_game", "load_save", "list_slots", "delete_slot",
    "gallery_union", "load_persistent",
    # Config
    "Config", "load_config", "keymap",
    # Expression
    "ExprError", "evaluate", "validate",
    # Timeline
    "Timeline", "Track",
    # i18n
    "t",
    # Richtext
    "richtext",
    # Data
    "DataError", "load_settings", "save_settings", "find_cjk_font",
    "resolve_image", "resolve_audio", "data_root", "game_root",
]
