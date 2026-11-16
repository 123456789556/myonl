"""P53 对话框皮肤：九宫格 / 渐变蒙版 / 纹理平铺 / 贴图渲染 / 导出成品 PNG。

覆盖点：
1. dialog_skin 纯函数（切边归一、九宫格不变形、渐变 alpha、纹理平铺、合成）
2. config.dialogue() 接受皮肤键（字符串 / 列表），不写配置时行为不变
3. Renderer：没配贴图 → _dialog_skin_surface 返回 None（走旧路径）
4. 编辑器：/api/ui-design/export-textbox 等价助手出 PNG、皮肤预览出 PNG 且不落盘
5. 前端接线：皮肤分页 / 预设库 / 导出按钮
"""

import json
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")  # 无头，须在 import pygame 前
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402
import pytest  # noqa: E402

from engine import dialog_skin as S  # noqa: E402
from engine import editor as E  # noqa: E402
from engine.config import DEFAULTS, Config  # noqa: E402
from engine.renderer import Renderer  # noqa: E402

pytestmark = [pytest.mark.unit]

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(E.__file__)))


def _make_src(w=12, h=12) -> pygame.Surface:
    """造一张带四角可识别色的贴图（左上半红、右上半绿…便于断言角不缩放）。"""
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    for y in range(h):
        for x in range(w):
            surf.set_at((x, y), (x * 20 % 256, y * 20 % 256, (x + y) * 10 % 256, 255))
    return surf


# ============ 1. 纯函数 ============


def test_parse_insets_单值与四边与越界夹取():
    assert S.parse_insets(0, 100, 100) == (0, 0, 0, 0)
    assert S.parse_insets(10, 100, 100) == (10, 10, 10, 10)
    assert S.parse_insets([4, 6, 8, 2], 100, 100) == (4, 6, 8, 2)
    # 单边超过源图一半 → 夹到「留 1px 中段」
    out = S.parse_insets(999, 20, 20)
    assert out[0] + out[2] <= 20 - 1
    assert out[1] + out[3] <= 20 - 1
    # 非法值一律 0
    assert S.parse_insets("abc", 100, 100) == (0, 0, 0, 0)
    assert S.parse_insets(None, 100, 100) == (0, 0, 0, 0)
    assert S.parse_insets([1, 2], 100, 100) == (0, 0, 0, 0)


def test_nine_slice_尺寸正确且四角不拉伸():
    src = _make_src(12, 12)
    out = S.nine_slice(src, 60, 30, [4, 4, 4, 4])
    assert out.get_size() == (60, 30)
    # 四角像素 = 原图四角（不缩放、不位移）
    assert out.get_at((0, 0)) == src.get_at((0, 0))
    assert out.get_at((3, 3)) == src.get_at((3, 3))
    assert out.get_at((59, 29)) == src.get_at((11, 11))
    assert out.get_at((56, 26)) == src.get_at((8, 8))


def test_nine_slice_零切边等于整张缩放():
    src = _make_src(8, 8)
    out = S.nine_slice(src, 40, 24, 0)
    assert out.get_size() == (40, 24)


def test_vertical_fade_顶部透明底部不透明():
    src = pygame.Surface((10, 40), pygame.SRCALPHA)
    src.fill((255, 255, 255, 255))
    out = S.vertical_fade(src, top_px=20)
    assert out.get_size() == (10, 40)
    assert out.get_at((0, 0)).a < 40          # 顶边几乎全透明
    assert out.get_at((0, 39)).a == 255       # 底边不受影响
    # 不改入参
    assert src.get_at((0, 0)).a == 255


def test_tint_乘法染色():
    src = pygame.Surface((6, 6), pygame.SRCALPHA)
    src.fill((200, 100, 50, 255))
    out = S.tint(src, (255, 255, 255))
    assert out.get_at((0, 0))[:3] == (200, 100, 50)
    out2 = S.tint(src, (128, 0, 0))
    assert out2.get_at((0, 0))[0] == pytest.approx(200 * 128 / 255, abs=2)
    assert out2.get_at((0, 0))[1] == 0
    # 非法染色参数 = 原样返回，不抛错
    assert S.tint(src, (1, 2)).get_at((0, 0))[:3] == (200, 100, 50)


def test_tile_平铺重复():
    tex = pygame.Surface((4, 4), pygame.SRCALPHA)
    tex.fill((10, 20, 30, 255))
    out = S.tile(tex, 9, 9)
    assert out.get_size() == (9, 9)
    for xy in ((0, 0), (3, 3), (4, 4), (8, 8), (2, 6)):
        assert out.get_at(xy)[:3] == (10, 20, 30)


def test_compose_panel_全参数不崩且尺寸正确():
    src = _make_src(16, 16)
    tex = pygame.Surface((6, 6), pygame.SRCALPHA)
    tex.fill((255, 255, 255, 128))
    out = S.compose_panel(src, 200, 90, [6, 6, 6, 6], (200, 180, 160), 10, 0,
                          tex, 60, 200)
    assert out.get_size() == (200, 90)
    assert 0 < out.get_at((100, 45)).a <= 255
    # 纹理 + 总透明度 0 → 整块透明（但不崩）
    blank = S.compose_panel(src, 40, 20, 0, None, 0, 0, tex, 60, 0)
    assert blank.get_at((10, 10)).a == 0


def test_solid_panel_圆角与像素化兜底():
    surf = S.solid_panel(120, 40, (30, 30, 40), 200, 18, pixelated=True)
    assert surf.get_size() == (120, 40)
    assert surf.get_at((60, 20)).a == 200
    # 圆角外缘透明（说明真的画了圆角，不是整块矩形）
    assert surf.get_at((0, 0)).a == 0


def test_边缘分支_非法值与退化入参不崩():
    # parse_insets：非数值 / bool / 长度不对一律按 0
    assert S.parse_insets("坏值", 100, 100) == (0, 0, 0, 0)
    assert S.parse_insets([True, "x", 3, 4], 100, 100) == (0, 0, 3, 4)
    assert S.parse_insets([1, 2, 3], 100, 100) == (0, 0, 0, 0)
    # 越界被夹：单值 999 不可能吃掉整张图
    l, t, r, b = S.parse_insets(999, 40, 30)
    assert l + r <= 40 and t + b <= 30
    # vertical_fade：0 羽化 = 原样拷贝，不改入参
    src = _make_src(10, 10)
    same = S.vertical_fade(src, 0, 0)
    assert same.get_at((5, 5))[:3] == src.get_at((5, 5))[:3]
    assert same is not src
    # tint：长度不足 / 类型错 → 原样返回
    assert S.tint(src, [1, 2]).get_at((5, 5))[:3] == src.get_at((5, 5))[:3]
    assert S.tint(src, None).get_at((5, 5))[:3] == src.get_at((5, 5))[:3]
    # tile：纹理比面板大 → 等比压到一屏（不只剩一个角）
    big = pygame.Surface((1000, 1000), pygame.SRCALPHA)
    big.fill((255, 255, 255, 255))
    out = S.tile(big, 120, 60)
    assert out.get_size() == (120, 60)
    assert out.get_at((119, 59)).a >= 250   # 没留下没铺到的空角
    # solid_panel：radius=0 走实心矩形分支
    flat = S.solid_panel(20, 10, (1, 200, 3), 255)
    assert flat.get_at((0, 0))[:3] == (1, 200, 3)


def test_surface_for_缓存与合成异常兜底(monkeypatch):
    img = _make_src(16, 16)
    cache = {}
    dlg = {"panel_image": "a", "panel_slice": [4, 4, 4, 4], "panel_alpha": 200}
    a = S.surface_for(dlg, 80, 40, lambda n: img, cache=cache)
    assert a is S.surface_for(dlg, 80, 40, lambda n: img, cache=cache)  # 命中缓存
    assert len(cache) == 1
    # 缓存项持有源图强引用（id 键不会被回收后复用）
    assert next(iter(cache.values()))[1] is img
    # 换参数 → 新对象
    assert S.surface_for({**dlg, "panel_alpha": 120}, 80, 40,
                         lambda n: img, cache=cache) is not a
    # 缓存满了会整体清空（不无限增长）
    for i in range(10):
        S.surface_for(dlg, 80 + i, 40, lambda n: img, cache=cache)
    assert len(cache) <= 8
    # 合成炸了 → 返回 None，让渲染层回退旧路径
    monkeypatch.setattr(S, "compose_panel", _boom)
    assert S.surface_for(dlg, 80, 40, lambda n: img) is None


def _boom(*_a, **_k):
    raise ValueError("坏图")


# ============ 2. config 合并 ============

def test_config_默认皮肤键为空且行为不变():
    dlg = Config().dialogue("default")
    assert dlg["panel_image"] == ""
    assert dlg["panel_slice"] == 0
    assert dlg["panel_tint"] is None
    assert dlg["panel_fade"] == 0
    assert dlg["panel_alpha"] == 255
    assert dlg["pad_x"] == 0 and dlg["pad_y"] == 0


def test_config_接受皮肤字符串与列表覆盖():
    dlg = Config({"dialogue": {"default": {
        "panel_image": "textbox", "panel_slice": [10, 8, 10, 8],
        "panel_texture": "paper", "panel_texture_alpha": 90,
        "panel_tint": [255, 200, 180], "panel_fade": 24,
    }}}).dialogue("default")
    assert dlg["panel_image"] == "textbox"
    assert dlg["panel_slice"] == [10, 8, 10, 8]
    assert dlg["panel_texture"] == "paper"
    assert dlg["panel_texture_alpha"] == 90
    assert dlg["panel_tint"] == [255, 200, 180]
    assert dlg["panel_fade"] == 24


def test_config_脏皮肤覆盖被忽略不崩():
    dlg = Config({"dialogue": {"default": {
        "panel_image": 123, "panel_slice": "x", "panel_fade": [1, 2],
        "panel_tint": "red",
    }}}).dialogue("default")
    assert dlg["panel_image"] == ""            # 非字符串 → 回落默认
    assert dlg["panel_slice"] == 0
    assert dlg["panel_fade"] == 0
    assert dlg["panel_tint"] is None


def test_config_nvl继承皮肤键():
    # 未配置：nvl 也有皮肤键，但值为空 → 仍走原有整屏渐变
    assert Config().dialogue("nvl")["panel_image"] == ""
    assert Config().dialogue("nvl")["panel_alpha"] == 255
    # 显式配到 nvl 段：生效（这是"整屏旁白也能贴图"的入口）
    dlg = Config({"dialogue": {"nvl": {
        "panel_image": "textbox", "panel_slice": [0, 0, 0, 0], "panel_fade": 40,
    }}}).dialogue("nvl")
    assert dlg["panel_image"] == "textbox"
    assert dlg["panel_fade"] == 40


def test_renderer_nvl整屏也能贴皮肤(tmp_path):
    root = _project(tmp_path, {"dialogue": {"nvl": {"panel_image": "textbox"}}})
    ren = Renderer((1280, 720), root)
    try:
        surf = ren._dialog_skin_surface(ren.config.dialogue("nvl"),
                                        pygame.Rect(0, 0, 1280, 720))
        assert surf is not None
        assert surf.get_size() == (1280, 720)
    finally:
        ren.close()


# ============ 3. 渲染层 ============


def _project(tmp_path, cfg=None, with_image=True) -> str:
    root = str(tmp_path)
    os.makedirs(os.path.join(root, "images"), exist_ok=True)
    if with_image:
        img = _make_src(32, 32)
        pygame.image.save(img, os.path.join(root, "images", "textbox.png"))
        tex = pygame.Surface((8, 8), pygame.SRCALPHA)
        tex.fill((255, 255, 255, 40))
        pygame.image.save(tex, os.path.join(root, "images", "paper.png"))
    if cfg:
        with open(os.path.join(root, "config.json"), "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    return root


def test_renderer_没配贴图时走旧路径(tmp_path):
    root = _project(tmp_path)
    ren = Renderer((1280, 720), root)
    try:
        rect = pygame.Rect(18, 500, 1244, 172)
        assert ren._dialog_skin_surface(ren.config.dialogue("default"), rect) is None
    finally:
        ren.close()


def test_renderer_配了贴图返回合成面板(tmp_path):
    root = _project(tmp_path, {"dialogue": {"default": {
        "panel_image": "textbox", "panel_slice": [8, 8, 8, 8],
        "panel_texture": "paper", "panel_texture_alpha": 40, "panel_alpha": 230,
    }}})
    ren = Renderer((1280, 720), root)
    try:
        dlg = ren.config.dialogue("default")
        rect = pygame.Rect(18, 500, 1244, 172)
        surf = ren._dialog_skin_surface(dlg, rect)
        assert surf is not None
        assert surf.get_size() == (1244, 172)
        # 二次取用命中缓存（同一对象）
        assert ren._dialog_skin_surface(dlg, rect) is surf
    finally:
        ren.close()


def test_renderer_贴图缺失时回落旧路径(tmp_path):
    root = _project(tmp_path, {"dialogue": {"default": {"panel_image": "nope"}}},
                    with_image=False)
    ren = Renderer((1280, 720), root)
    try:
        assert ren._dialog_skin_surface(ren.config.dialogue("default"),
                                        pygame.Rect(0, 0, 100, 50)) is None
    finally:
        ren.close()


def test_渲染一帧带皮肤对话框不报错(tmp_path):
    root = _project(tmp_path, {"dialogue": {"default": {
        "panel_image": "textbox", "panel_slice": [8, 8, 8, 8], "pad_x": 12, "pad_y": 6,
    }}})
    ren = Renderer((1280, 720), root)
    try:
        ren._screen.fill((30, 32, 44))
        hist = [{"char": "林晚", "text": "带贴图的对话框：九宫格自适应宽高。"}]
        ren._tw_text = hist[0]["text"]
        ren._tw_shown = float(len(hist[0]["text"]))
        ren._draw_dialog(hist, {"林晚": {"color": (255, 196, 120)}}, pending=False)
        # pad_y 生效：正文起始 y 比无 pad 时更靠下
        layout = ren._dialog_layout(hist, {"林晚": {"color": (255, 196, 120)}}, False)
        assert layout["margin"] == 24 + 12
    finally:
        ren.close()


# ============ 4. 编辑器：写回清洗 / 导出 / 预览 ============


def test_clean_dialogue_value_挡住脏值():
    ok, val = E._clean_dialogue_value("panel_image", " textbox ")
    assert ok and val == "textbox"
    assert E._clean_dialogue_value("panel_image", "../secret")[0] is False
    assert E._clean_dialogue_value("panel_image", 123)[0] is False
    assert E._clean_dialogue_value("panel_slice", [4, 4, 4, 4]) == (True, [4, 4, 4, 4])
    assert E._clean_dialogue_value("panel_slice", 6) == (True, 6)
    assert E._clean_dialogue_value("panel_slice", [1, 2])[0] is False
    assert E._clean_dialogue_value("panel_tint", None) == (True, None)
    assert E._clean_dialogue_value("panel_tint", [1, 2, 3]) == (True, [1, 2, 3])
    assert E._clean_dialogue_value("panel_tint", [1, 2, 300])[0] is False
    assert E._clean_dialogue_value("panel_fade", 12) == (True, 12)
    assert E._clean_dialogue_value("panel_fade", "12")[0] is False


def test_textbox_png_导出尺寸与画布一致(tmp_path):
    root = _project(tmp_path, {"canvas_size": [1920, 1080], "dialogue": {"default": {
        "panel_image": "textbox", "panel_slice": [10, 10, 10, 10],
        "panel_texture": "paper", "panel_texture_alpha": 50,
    }}})
    png = E._textbox_png(root, {"panel_image": "textbox", "panel_slice": [10, 10, 10, 10]},
                         {"pixelated": True, "pixel_scale": 4}, 1920, None)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    # 1080p 下 height 180 会按 ui_scale 1.5 放大到 270
    import struct
    w, h = struct.unpack(">II", png[16:24])
    assert w == 1920
    assert h == 270


def test_textbox_png_没贴图也有兜底底图(tmp_path):
    root = _project(tmp_path, with_image=False)
    png = E._textbox_png(root, {}, {}, 1280, 180)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(png) > 500


def test_ui_design_预览支持皮肤补丁且不写盘(tmp_path):
    root = _project(tmp_path)
    before = E._load_project_config(root)
    png = E._ui_design_png(root, {}, {"panel_image": "textbox",
                                      "panel_slice": [8, 8, 8, 8],
                                      "panel_fade": 20, "pad_x": 10})
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(png) > 1000
    assert E._load_project_config(root) == before


def test_ui_design_get_返回皮肤键(tmp_path):
    root = _project(tmp_path, {"dialogue": {"default": {"panel_image": "textbox"}}})
    cfg = E._load_project_config(root)
    assert cfg["dialogue"]["default"]["panel_image"] == "textbox"
    # 白名单包含全部皮肤键（GET 会按这个列表补齐返回）
    for k in ("panel_image", "panel_slice", "panel_tint", "panel_fade",
              "panel_fade_bottom", "panel_texture", "panel_texture_alpha",
              "panel_alpha", "pad_x", "pad_y"):
        assert k in E._EditorHandler._UI_DESIGN_DLG_KEYS
        assert k in DEFAULTS["dialogue"]["default"]


# ============ 5. 前端接线 ============


def test_前端皮肤分页与预设库接线():
    html = open(os.path.join(_ROOT, "editor", "index.html"), encoding="utf-8").read()
    js = open(os.path.join(_ROOT, "editor", "editor_uidesign.js"), encoding="utf-8").read()
    css = open(os.path.join(_ROOT, "editor", "editor.css"), encoding="utf-8").read()
    # 入口 HTML 只留挂载点（皮肤控件与画布结构由 JS 注入，守住入口行数门禁）
    for token in ('id="uidPanelSkin"', 'id="uidExport"', 'id="uidPreviewHint"'):
        assert token in html, f"index.html 缺 {token}"
    for token in ("uidBuildSkinControls", "UID_PRESETS", "uidApplyPreset",
                  "uidExportTextbox", "export-textbox", "uidPositionStage",
                  "uidLoadImageNames", "uidSliceL", "uidPanelImage",
                  "uidDragBody", "uidDragTop", "uidDragLeft"):
        assert token in js, f"editor_uidesign.js 缺 {token}"
    assert ".uid-drag-body" in css and ".uid-preset" in css
    # 导出路由已注册
    assert ("POST", "/api/ui-design/export-textbox") in E._EditorHandler._ROUTES


# ============ 6. 端到端：白名单写回 + 导出落盘 ============


def _http_server(root):
    import http.client  # noqa: F401 - 只在集成用例里用
    import socket
    import threading

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    app = E.EditorApp(root)
    srv = E.ThreadingHTTPServer(("127.0.0.1", port), app.make_handler())
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return port, srv


def _req(port, method, path, body=None):
    import http.client
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=15)
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    conn.request(method, path, data, {"Content-Type": "application/json"})
    resp = conn.getresponse()
    raw = resp.read()
    conn.close()
    return resp.status, raw


@pytest.mark.integration
def test_接口端到端_皮肤写回与导出落盘(tmp_path):
    root = _project(tmp_path)
    port, srv = _http_server(root)
    try:
        # 写回：皮肤键过白名单 + 类型清洗落进 config.json
        status, raw = _req(port, "POST", "/api/ui-design", {
            "dialogue": {"panel_image": "textbox", "panel_slice": [10, 8, 10, 8],
                         "panel_texture": "paper", "panel_texture_alpha": 50,
                         "pad_x": 14},
        })
        assert status == 200 and json.loads(raw)["ok"] is True
        cfg = E._load_project_config(root)
        dlg = cfg["dialogue"]["default"]
        assert dlg["panel_image"] == "textbox"
        assert dlg["panel_slice"] == [10, 8, 10, 8]
        assert dlg["panel_texture"] == "paper"

        # 读回：GET 带上皮肤键
        status, raw = _req(port, "GET", "/api/ui-design")
        assert status == 200
        data = json.loads(raw)
        assert data["dialogue"]["panel_image"] == "textbox"
        assert data["dialogue"]["pad_x"] == 14

        # 导出：成品 PNG 真的落到 images/
        status, raw = _req(port, "POST", "/api/ui-design/export-textbox",
                           {"dialogue": {"panel_image": "textbox",
                                         "panel_slice": [10, 8, 10, 8]},
                            "name": "exported"})
        assert status == 200 and json.loads(raw)["ok"] is True
        out = os.path.join(root, "images", "exported.png")
        assert os.path.exists(out)
        with open(out, "rb") as f:
            assert f.read(8) == b"\x89PNG\r\n\x1a\n"
        # 脏导出名被拒
        status, raw = _req(port, "POST", "/api/ui-design/export-textbox",
                           {"name": "../evil"})
        assert status == 400
        # 同名图已存在：默认拒（409），不静默覆盖用户的素材
        status, raw = _req(port, "POST", "/api/ui-design/export-textbox",
                           {"dialogue": {"panel_image": "textbox"}, "name": "exported"})
        assert status == 409
        assert json.loads(raw)["exists"] is True
        # 明确带 overwrite 才覆盖
        status, raw = _req(port, "POST", "/api/ui-design/export-textbox",
                           {"dialogue": {"panel_image": "textbox"},
                            "name": "exported", "overwrite": True})
        assert status == 200 and json.loads(raw)["ok"] is True
        assert not os.path.exists(os.path.join(root, "images", "exported.png.tmp"))
    finally:
        srv.shutdown()
        srv.server_close()
