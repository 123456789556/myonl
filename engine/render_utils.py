"""MYONL 渲染层工具函数（renderer.py 拆分第 1 步）。

纯函数 + UI 键位表，无 Renderer 实例状态依赖，可独立测试。
renderer.py 通过 `from .render_utils import ...` 引入，对外命名空间保持不变
（engine.renderer._ui_key / _format_setting 等引用仍然有效）。
"""
from __future__ import annotations

import pygame

# 非 playing 模式的 pygame 键 → 统一 UI 键名（数字键 1~9/0 → slot1~slot10）
_UI_KEYMAP = {
    pygame.K_UP: "up",
    pygame.K_DOWN: "down",
    pygame.K_LEFT: "left",
    pygame.K_RIGHT: "right",
    pygame.K_RETURN: "confirm",
    pygame.K_KP_ENTER: "confirm",
    pygame.K_SPACE: "confirm",
    pygame.K_ESCAPE: "back",
}
_UI_KEYMAP.update({pygame.K_1 + i: f"slot{i + 1}" for i in range(9)})
_UI_KEYMAP[pygame.K_0] = "slot10"


def _format_setting(value, kind: str) -> str:
    if value is None:
        return "—"
    if kind == "switch":
        try:
            return "开" if float(value) >= 0.5 else "关"
        except (TypeError, ValueError):
            return str(value)
    if kind == "volume":
        try:
            return f"{float(value):.1f}"
        except (TypeError, ValueError):
            return str(value)
    if kind == "offset":
        # U7：对话框位置（像素）——0=项目默认，负=上移，正=下移
        try:
            v = int(round(float(value) / 10.0) * 10)
        except (TypeError, ValueError):
            return str(value)
        if v == 0:
            return "默认"
        return f"上移 {abs(v)}" if v < 0 else f"下移 {v}"
    # P30-S2-1：打字速度档位显示（慢=≤30 / 中=31~60 / 快=≥61），存储仍是数字
    if kind == "speed":
        try:
            v = float(value)
        except (TypeError, ValueError):
            return str(value)
        if v <= 30:
            return "慢"
        if v <= 60:
            return "中"
        return "快"
    try:
        return str(int(value))
    except (TypeError, ValueError):
        return str(value)


def _slot_card_head(row: dict) -> str:
    """⑨ 存档卡片第一行：`位名 · 章节名 · 时间`（章节名缺省「未命名进度」）。"""
    slot = row.get("slot")
    head = row.get("name") or ("快速存档" if slot == "quick" else f"{slot} 号位")
    chapter = row.get("chapter_name") or row.get("label") or "未命名进度"
    stamp = str(row.get("saved_at") or "").replace("T", " ")
    return f"{head} · {chapter} · {stamp}"


def _slot_row_text(row: dict) -> str:
    """存档行文案：`快速存档 / 3 号位 · label · 时间`；空位显示「（空）」。"""
    slot = row.get("slot")
    head = row.get("name") or ("快速存档" if slot == "quick" else f"{slot} 号位")
    if row.get("empty"):
        return f"{head} · （空）"
    label = row.get("label")
    stamp = row.get("saved_at")
    if not label and not stamp:
        return f"{head} · （空）"
    stamp_text = str(stamp or "").replace("T", " ")
    return f"{head} · {label or '未命名进度'} · {stamp_text}"


def _clip_text(text, font, max_width) -> str:
    """单行超宽时截断并加省略号（回看/存档行不折行）。"""
    text = str(text)
    if font.size(text)[0] <= max_width:
        return text
    ell = "…"
    limit = len(text)
    while limit > 0 and font.size(text[:limit] + ell)[0] > max_width:
        limit -= 1
    return text[:limit] + ell


def _ui_key(key, keymap=None) -> str | None:
    """pygame 键 → UI 统一键名（与 engine/ui.py 的键名约定一致；keymap 来自 config.json）。"""
    return (keymap if keymap is not None else _UI_KEYMAP).get(key)


def is_confirm_key(settings, key) -> bool:
    """U10：玩家确认键方案（both / space / enter），设置页可切。"""
    preset = str((settings or {}).get("confirm_key") or "both")
    if preset == "space":
        return key == pygame.K_SPACE
    if preset == "enter":
        return key in (pygame.K_RETURN, pygame.K_KP_ENTER)
    return key in (pygame.K_SPACE, pygame.K_RETURN, pygame.K_KP_ENTER)


def _scale_to_fit(img, max_w, max_h):
    """等比缩放到不超过 (max_w, max_h)（不拉伸变形）。"""
    w, h = img.get_size()
    if w <= 0 or h <= 0 or max_w <= 0 or max_h <= 0:
        return img
    s = min(max_w / w, max_h / h)
    if s <= 0:
        return img
    return pygame.transform.smoothscale(img, (max(1, int(w * s)), max(1, int(h * s))))


def _wrap_text(text, font, max_width, measure=None):
    """按宽度折行（字符级，不做词级断行），保留显式换行。

    measure：可选的量宽函数 text -> 像素宽；缺省用 font.size(text)[0]（无缓存）。
    T8 起渲染层传入带缓存的 TextMixin._font_width，这里是折行算法的唯一实现，
    避免缓存版与直出版各写一份、日后改一处漏一处。
    """
    width_of = measure if measure is not None else (lambda s: font.size(s)[0])
    lines = []
    for para in str(text).split("\n"):
        cur = ""
        for ch in para:
            if not cur or width_of(cur + ch) <= max_width:
                cur += ch
            else:
                lines.append(cur)
                cur = ch
        lines.append(cur)
    return lines


# ---- 常量（原 renderer.py 画面/资源/镜头/UI 常量）----

# 画面常量（T10：逻辑画布尺寸可由 config.json canvas_size 覆盖，此处为兜底默认值）
DEFAULT_SIZE = (1280, 720)
DIALOG_HEIGHT = 180                 # 对话框高度（默认；P0-1 起由 config dialogue.default 可配）
DIALOG_TOP = DEFAULT_SIZE[1] - DIALOG_HEIGHT  # 默认顶 y（默认布局，供测试/常量引用）
CHOICE_ROW_HEIGHT = 40              # 选项每行高度
FADE_SECONDS = 0.3                  # 背景淡入时长
FONT_SIZE = 28                      # 正文字号
MISSING_COLOR = (51, 51, 51)        # 占位色块 #333
TITLE_FONT_SIZE = 72                # 标题画面引擎名字号
UI_HIGHLIGHT = (255, 255, 200)      # UI 光标高亮描边色（与选项菜单一致）
UI_DISABLED = (136, 136, 136)       # UI 灰置文字色（与选项菜单一致）
# P30-S1-2：选中项高对比配色（深蓝实底 + 白字，夜景画面上也能读清；
# 与未选中的半透明黑底明显区分，避免"看不出哪行被选中"）
UI_SELECTED_BG = (40, 54, 96)       # 选中行底色
UI_SELECTED_BG_ALPHA = 235
UI_SELECTED_FG = (255, 255, 255)    # 选中行文字色
UI_SELECTED_BORDER = (140, 180, 255)  # 选中行描边色
UI_IDLE_BG = (0, 0, 0)              # 未选中行底色
UI_IDLE_BG_ALPHA = 180
# P30-S1-1：对话框正文色 / 出选项时上一句的压暗色
DIALOG_FG = (255, 255, 255)
DIALOG_FG_DIM = (150, 150, 150)
SPRITE_MARGIN = 20                  # @show pos=左/右 时立绘贴边留白（像素）
# ---- 资源管理（20GB 级项目：运行时内存与素材总量解耦）----
IMG_CACHE_MAX = 256                 # 图片 LRU 上限（张数）
IMG_CACHE_MAX_BYTES = 512 * 1024 * 1024  # 图片 LRU 上限（估算字节，w*h*4）
FRAME_WINDOW = 5                    # 帧序列滑动窗口：只驻留当前帧 ±5
ANIM_FPS = 6                        # 立绘动画（呼吸/说话）帧率
SFX_CACHE_MAX = 64                  # 音效/配音 LRU 上限（条数）
_FRAME_EXTS = (".png", ".webp")     # 帧序列允许的后缀（查找顺序即优先级）
# 镜头 / 转场常量
CAM_PAN_RATIO = 0.15                # 平移最大幅度 = 屏幕宽/高的 15%
CAM_ZOOM_SECONDS = 1.0              # @camera zoom 默认时长（参数只给起止缩放）
CAM_SHAKE_PX = 30                   # 震动基础像素幅度（再乘 args[1] 幅度系数）
TRANS_DEFAULT_SECONDS = 0.3         # 默认淡入时长（与原 FADE_SECONDS 一致）
# P30-C-c：@anim 可补间的立绘参数及缺省显示值
SPRITE_ANIM_DEFAULTS = {"x": 0.0, "y": 0.0, "alpha": 1.0, "scale": 1.0}
# P30-C-d：分层立绘的固定叠放顺序（身体在下、皮肤/服装居中、表情在上）；未列出的部位接在后面
LAYER_ORDER = ("身体", "皮肤", "表情")
