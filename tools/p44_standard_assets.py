"""P44-B1 标准模板素材生成：engine/templates/standard/ 的版权干净成品素材。

- 背景 3 张（1280×720）：bg_标题（星空月牙渐变）、bg_教室（暖窗光）、bg_天台（黄昏云）
- 立绘 2 张（512×1024）：林晚_微笑、林晚_生气（扁平剪影）
- BGM 1 段（audio/bgm_night.ogg）：正弦波合成宁静旋律（约 60s 循环）
全部程序生成，无第三方素材，版权干净。
"""
import os, math, struct, wave, sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # 保证 from engine.data 可导入
TPL = ROOT / "engine" / "templates" / "standard"
IMG = TPL / "images"
AUD = TPL / "audio"
IMG.mkdir(parents=True, exist_ok=True)
AUD.mkdir(parents=True, exist_ok=True)


def _vgrad(surf, top, bottom):
    """竖向渐变填充。"""
    w, h = surf.get_size()
    for y in range(h):
        t = y / max(1, h - 1)
        c = (
            int(top[0] * (1 - t) + bottom[0] * t),
            int(top[1] * (1 - t) + bottom[1] * t),
            int(top[2] * (1 - t) + bottom[2] * t),
        )
        surf.fill(c, pygame.Rect(0, y, w, 1))


def _stars(surf, n=90, alpha=170):
    import random
    rnd = random.Random(7)
    for _ in range(n):
        x, y = rnd.randint(0, 1279), rnd.randint(0, 360)
        r = rnd.choice((1, 1, 1, 2))
        c = (235, 235, 250)
        s = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
        pygame.draw.circle(s, (*c, alpha), (r, r), r)
        surf.blit(s, (x - r, y - r))


def _moon(surf, cx=1010, cy=150, r=88, color=(255, 231, 190)):
    pygame.draw.circle(surf, color, (cx, cy), r)
    # 缺口（月牙）
    mask = pygame.Surface((r * 2 + 40, r * 2 + 40), pygame.SRCALPHA)
    pygame.draw.circle(mask, (*color, 255), (r + 40, r + 20), r - 14)
    surf.blit(mask, (cx - r - 20, cy - r - 10), special_flags=pygame.BLEND_RGBA_SUB)


def bg_title():
    surf = pygame.Surface((1280, 720))
    _vgrad(surf, (22, 26, 64), (74, 56, 156))
    _stars(surf)
    _moon(surf)
    pygame.image.save(surf, str(IMG / "bg_标题.png"))


def bg_classroom():
    surf = pygame.Surface((1280, 720))
    _vgrad(surf, (196, 172, 132), (140, 110, 86))
    # 窗户光
    light = pygame.Surface((1280, 720), pygame.SRCALPHA)
    for i, (wx, ww) in enumerate([(150, 220), (420, 220), (690, 220), (960, 220)]):
        pygame.draw.rect(light, (255, 236, 200, 60), (wx, 80, ww, 520))
        pygame.draw.rect(light, (255, 236, 200, 120), (wx + 10, 90, ww - 20, 500))
    surf.blit(light)
    # 窗框
    for wx, ww in [(150, 220), (420, 220), (690, 220), (960, 220)]:
        pygame.draw.rect(surf, (96, 78, 62), (wx, 80, ww, 520), 6)
        pygame.draw.line(surf, (96, 78, 62), (wx + ww // 2, 80), (wx + ww // 2, 600), 6)
        pygame.draw.line(surf, (96, 78, 62), (wx, 300), (wx + ww, 300), 6)
    # 地面
    pygame.draw.rect(surf, (122, 96, 76), (0, 600, 1280, 120))
    pygame.draw.line(surf, (90, 70, 58), (0, 600), (1280, 600), 4)
    pygame.image.save(surf, str(IMG / "bg_教室.png"))


def bg_rooftop():
    surf = pygame.Surface((1280, 720))
    _vgrad(surf, (250, 200, 160), (180, 120, 160))  # 黄昏
    _stars(surf, n=40, alpha=90)
    # 云
    for cx, cy, r in [(300, 180, 90), (760, 140, 110), (1050, 260, 80)]:
        cloud = pygame.Surface((r * 4, r * 3), pygame.SRCALPHA)
        for dx, dy, rr in [(r, r, r), (r * 1.8, r * 1.2, r * 0.8), (r * 0.4, r * 1.3, r * 0.7), (r * 2.5, r * 1.4, r * 0.7)]:
            pygame.draw.circle(cloud, (255, 240, 230, 190), (int(dx), int(dy)), int(rr))
        surf.blit(cloud, (cx - r * 2, cy - r * 1.5))
    # 楼顶围栏
    pygame.draw.rect(surf, (90, 80, 100), (0, 560, 1280, 160))
    pygame.draw.rect(surf, (120, 108, 130), (0, 560, 1280, 26))
    pygame.image.save(surf, str(IMG / "bg_天台.png"))


def _blit_name(surf, name, root, size=64):
    import pygame as pg
    pg.font.init()
    from engine.data import find_cjk_font
    try:
        path = find_cjk_font(str(root))
        font = pg.font.Font(path, size)
    except Exception:
        font = pg.font.Font(None, size)
    label = font.render(name, True, (255, 255, 255))
    surf.blit(label, (surf.get_width() // 2 - label.get_width() // 2,
                      surf.get_height() - label.get_height() - 40))


def _sprite(emoji_style="smile"):
    """扁平剪影立绘：柔和色渐变 + 简洁人形。"""
    surf = pygame.Surface((512, 1024), pygame.SRCALPHA)
    # 头发/衣服色
    if emoji_style == "smile":
        hair, dress = (120, 96, 150), (238, 176, 190)
    else:
        hair, dress = (110, 88, 140), (214, 108, 118)
    # 头
    pygame.draw.circle(surf, (246, 218, 200), (256, 210), 92)
    # 头发
    pygame.draw.circle(surf, hair, (256, 180), 96)
    pygame.draw.ellipse(surf, hair, (180, 150, 152, 110))
    pygame.draw.ellipse(surf, hair, (180, 300, 152, 140))
    # 眼（微笑 vs 生气）
    eye_y = 220
    if emoji_style == "smile":
        pygame.draw.arc(surf, (60, 50, 70), (196, eye_y - 18, 46, 34), 0, math.pi, 4)
        pygame.draw.arc(surf, (60, 50, 70), (272, eye_y - 18, 46, 34), 0, math.pi, 4)
        pygame.draw.arc(surf, (150, 90, 110), (218, 300, 76, 46), 0, math.pi, 4)
    else:
        pygame.draw.circle(surf, (60, 50, 70), (219, eye_y), 10)
        pygame.draw.circle(surf, (60, 50, 70), (295, eye_y), 10)
        pygame.draw.arc(surf, (150, 90, 110), (218, 306, 76, 46), math.pi, 2 * math.pi, 4)
    # 身体（连衣裙）
    pygame.draw.polygon(surf, dress, [(256, 320), (196, 560), (316, 560)])
    pygame.draw.ellipse(surf, (250, 236, 226), (196, 540, 120, 90))
    # 领结
    pygame.draw.circle(surf, (255, 231, 190), (256, 352), 14)
    return surf


def make_bgm(path, seconds=60):
    """正弦波合成 BGM：柔和和弦循环，44100Hz 16bit 单声道 OGG 由 WAV 转换。"""
    sr = 44100
    n = sr * seconds
    # 和弦进行：Am - F - C - G（舒缓）
    chords = [(220.0, 261.6, 329.6), (174.6, 220.0, 261.6),
              (196.0, 246.9, 293.7), (196.0, 246.9, 293.7)]
    frames = bytearray()
    for i in range(n):
        t = i / sr
        chord = chords[(i // (sr * 4)) % 4]
        seg = i % (sr * 4) / sr
        # 衰减包络
        env = 0.5 + 0.5 * math.exp(-seg * 0.7)
        v = 0
        for f in chord:
            v += math.sin(2 * math.pi * f * t)
        # 轻微颤音
        v *= (0.96 + 0.04 * math.sin(2 * math.pi * 5 * t))
        sample = int(12000 * env * v / len(chord))
        frames += struct.pack("<h", max(-32767, min(32767, sample)))
    wav = path.with_suffix(".wav")
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(bytes(frames))
    # 转 OGG（引擎优先读 ogg，体积约为 wav 的 1/40）
    _wav_to_ogg(wav, path)
    wav.unlink()
    print("bgm:", path.name, path.stat().st_size, "bytes")


def _wav_to_ogg(wav, ogg):
    """libsndfile 的 Vorbis 编码需要较大线程栈，故放到大栈线程里跑。"""
    import threading

    import soundfile as sf

    def _run():
        data, sr = sf.read(str(wav), dtype="int16")
        sf.write(str(ogg), data, sr, format="OGG", subtype="VORBIS")

    threading.stack_size(32 * 1024 * 1024)
    t = threading.Thread(target=_run)
    t.start()
    t.join()


if __name__ == "__main__":
    bg_title()
    bg_classroom()
    bg_rooftop()
    for style in ("smile", "angry"):
        s = _sprite(style)
        name = "林晚_微笑" if style == "smile" else "林晚_生气"
        _blit_name(s, name, ROOT)
        pygame.image.save(s, str(IMG / f"{name}.png"))
    make_bgm(AUD / "bgm_night.ogg")
    for f in sorted(IMG.iterdir()):
        print("img:", f.name, f.stat().st_size)
