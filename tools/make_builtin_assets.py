# -*- coding: utf-8 -*-
"""自带素材扩充：给模板/示例工程补足背景、立绘、音效、BGM（全部程序生成，版权干净）。

背景 6 张（1280×720）：走廊 / 夜街 / 公园黄昏 / 卧室 / 咖啡店 / 雨天
立绘 5 张（512×1024）：林晚（微笑/生气/惊讶）+ 苏晴（微笑/默认）
音效 4 个（ogg）：click / page / door / rain
BGM 1 首（60s ogg）：bgm_day（明亮大调）

只写入 engine/templates/standard/，再同步到示例与"新游戏"工程。
用法：py -3 tools/make_builtin_assets.py [--sync-only]
"""
from __future__ import annotations

import math
import os
import random
import shutil
import struct
import sys
import wave
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TPL = ROOT / "engine" / "templates" / "standard"
IMG = TPL / "images"
AUD = TPL / "audio"
W, H = 1280, 720
TARGETS = [
    ROOT / "games" / "标准示例",
    ROOT / "games" / "新游戏",
    ROOT / "games" / "新游戏模板",
]


# ---------------- 背景：统一风格（柔和渐变 + 几何剪影） ----------------

def _vgrad(surf, top, bottom):
    w, h = surf.get_size()
    for y in range(h):
        t = y / max(1, h - 1)
        surf.fill(tuple(int(top[i] * (1 - t) + bottom[i] * t) for i in range(3)),
                  pygame.Rect(0, y, w, 1))


def _soft_light(surf, cx, cy, r, color, alpha=70):
    layer = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
    for i in range(r, 0, -4):
        a = int(alpha * (1 - i / r))
        pygame.draw.circle(layer, (*color, a), (r, r), i)
    surf.blit(layer, (cx - r, cy - r))


def _floor(surf, y, color, line=None):
    pygame.draw.rect(surf, color, (0, y, W, H - y))
    if line:
        pygame.draw.line(surf, line, (0, y), (W, y), 3)


def bg_corridor():
    surf = pygame.Surface((W, H))
    _vgrad(surf, (206, 200, 186), (150, 142, 130))
    # 透视走廊：两侧门框逐渐缩小
    for i in range(6):
        k = i / 6
        x1 = int(60 + k * 430)
        x2 = int(1220 - k * 430)
        y1 = int(80 + k * 120)
        y2 = int(660 - k * 120)
        pygame.draw.rect(surf, (176, 168, 154), (x1, y1, x2 - x1, y2 - y1), 4)
        pygame.draw.rect(surf, (120, 110, 100), (x1 + 18, y1 + 70, 90 - i * 12, 220), 3)
        pygame.draw.rect(surf, (120, 110, 100), (x2 - 108 + i * 12, y1 + 70, 90 - i * 12, 220), 3)
    _soft_light(surf, W // 2, 260, 320, (255, 245, 220), 90)
    _floor(surf, 600, (128, 118, 106), (96, 88, 78))
    pygame.image.save(surf, str(IMG / "bg_走廊.png"))


def bg_street_night():
    surf = pygame.Surface((W, H))
    _vgrad(surf, (18, 22, 44), (52, 46, 84))
    rnd = random.Random(11)
    for _ in range(120):
        x, y = rnd.randint(0, W - 1), rnd.randint(0, 300)
        r = rnd.choice((1, 1, 2))
        pygame.draw.circle(surf, (220, 226, 255), (x, y), r)
    # 楼群
    x = 0
    while x < W:
        bw = rnd.randint(110, 220)
        bh = rnd.randint(200, 380)
        pygame.draw.rect(surf, (34, 38, 66), (x, H - 140 - bh, bw, bh))
        for wy in range(H - 140 - bh + 24, H - 160, 42):
            for wx in range(x + 18, x + bw - 24, 38):
                if rnd.random() < 0.55:
                    pygame.draw.rect(surf, (255, 226, 150), (wx, wy, 16, 22))
        x += bw + rnd.randint(8, 26)
    _floor(surf, H - 140, (26, 28, 44), (60, 62, 88))
    _soft_light(surf, 240, H - 140, 220, (255, 210, 140), 80)
    # 路灯
    pygame.draw.line(surf, (90, 92, 116), (240, H - 140), (240, 380), 6)
    pygame.draw.circle(surf, (255, 232, 180), (240, 372), 22)
    pygame.image.save(surf, str(IMG / "bg_街道夜.png"))


def bg_park():
    surf = pygame.Surface((W, H))
    _vgrad(surf, (255, 214, 170), (176, 150, 186))
    _soft_light(surf, 320, 180, 260, (255, 240, 200), 100)
    # 树
    rnd = random.Random(5)
    for bx in (160, 420, 900, 1130):
        pygame.draw.rect(surf, (96, 74, 58), (bx - 12, 420, 24, 200))
        for _ in range(9):
            pygame.draw.circle(surf, (74, 108, 78),
                               (bx + rnd.randint(-90, 90), 360 + rnd.randint(-60, 40)),
                               rnd.randint(40, 70))
    _floor(surf, 600, (108, 122, 84), (84, 96, 66))
    # 长椅
    pygame.draw.rect(surf, (120, 90, 66), (560, 560, 200, 16))
    pygame.draw.rect(surf, (120, 90, 66), (560, 530, 200, 12))
    pygame.draw.rect(surf, (92, 68, 52), (572, 576, 12, 44))
    pygame.draw.rect(surf, (92, 68, 52), (736, 576, 12, 44))
    pygame.image.save(surf, str(IMG / "bg_公园.png"))


def bg_room():
    surf = pygame.Surface((W, H))
    _vgrad(surf, (232, 216, 200), (196, 178, 168))
    # 窗
    pygame.draw.rect(surf, (140, 170, 200), (820, 90, 360, 300))
    pygame.draw.rect(surf, (250, 246, 236), (820, 90, 360, 300), 10)
    pygame.draw.line(surf, (250, 246, 236), (1000, 90), (1000, 390), 8)
    pygame.draw.line(surf, (250, 246, 236), (820, 240), (1180, 240), 8)
    _soft_light(surf, 1000, 240, 260, (255, 250, 230), 80)
    # 床
    pygame.draw.rect(surf, (176, 142, 120), (80, 420, 420, 200), border_radius=12)
    pygame.draw.rect(surf, (246, 240, 232), (100, 400, 180, 70), border_radius=10)
    pygame.draw.rect(surf, (196, 168, 148), (80, 600, 420, 40))
    # 桌
    pygame.draw.rect(surf, (150, 118, 96), (600, 470, 220, 16))
    pygame.draw.rect(surf, (120, 94, 78), (612, 486, 14, 120))
    pygame.draw.rect(surf, (120, 94, 78), (794, 486, 14, 120))
    _floor(surf, 620, (168, 146, 132), (140, 120, 108))
    pygame.image.save(surf, str(IMG / "bg_房间.png"))


def bg_cafe():
    surf = pygame.Surface((W, H))
    _vgrad(surf, (238, 222, 198), (186, 160, 138))
    # 吧台
    pygame.draw.rect(surf, (118, 84, 62), (0, 470, W, 34))
    pygame.draw.rect(surf, (92, 64, 46), (0, 504, W, 216))
    # 吊灯
    for cx in (260, 640, 1020):
        pygame.draw.line(surf, (90, 80, 70), (cx, 0), (cx, 96), 4)
        pygame.draw.circle(surf, (255, 232, 180), (cx, 108), 26)
        _soft_light(surf, cx, 120, 150, (255, 236, 190), 80)
    # 杯子
    for cx in (300, 700, 980):
        pygame.draw.rect(surf, (250, 246, 238), (cx, 430, 34, 40), border_radius=6)
        pygame.draw.circle(surf, (250, 246, 238), (cx + 42, 448), 10, 4)
    # 菜单板
    pygame.draw.rect(surf, (70, 54, 44), (520, 120, 240, 160))
    for i in range(4):
        pygame.draw.line(surf, (210, 196, 178), (546, 156 + i * 30), (734, 156 + i * 30), 3)
    pygame.image.save(surf, str(IMG / "bg_咖啡店.png"))


def bg_rain():
    surf = pygame.Surface((W, H))
    _vgrad(surf, (96, 112, 132), (62, 74, 92))
    # 远处建筑
    for i, (bx, bw, bh) in enumerate([(80, 260, 220), (380, 200, 300), (640, 300, 180), (980, 220, 260)]):
        pygame.draw.rect(surf, (54, 64, 82), (bx, 520 - bh, bw, bh))
        for wy in range(520 - bh + 26, 500, 46):
            for wx in range(bx + 20, bx + bw - 26, 44):
                if (wx + wy) % 3:
                    pygame.draw.rect(surf, (120, 142, 160), (wx, wy, 18, 24))
    _floor(surf, 520, (46, 54, 68), (70, 82, 98))
    # 雨丝
    rnd = random.Random(3)
    rain = pygame.Surface((W, H), pygame.SRCALPHA)
    for _ in range(420):
        x, y = rnd.randint(0, W), rnd.randint(0, H)
        ln = rnd.randint(14, 34)
        pygame.draw.line(rain, (190, 210, 230, rnd.randint(60, 130)), (x, y), (x - 6, y + ln), 1)
    surf.blit(rain, (0, 0))
    pygame.image.save(surf, str(IMG / "bg_雨天.png"))


# ---------------- 立绘：扁平剪影（两个角色 × 表情） ----------------

def _hair(surf, color):
    pygame.draw.circle(surf, color, (256, 180), 96)
    pygame.draw.ellipse(surf, color, (180, 150, 152, 110))
    pygame.draw.ellipse(surf, color, (180, 300, 152, 140))


def _sprite(hair, dress, eye: str) -> pygame.Surface:
    surf = pygame.Surface((512, 1024), pygame.SRCALPHA)
    pygame.draw.circle(surf, (246, 218, 200), (256, 210), 92)   # 脸
    _hair(surf, hair)
    eye_y = 220
    if eye == "smile":
        pygame.draw.arc(surf, (60, 50, 70), (196, eye_y - 18, 46, 34), 0, math.pi, 4)
        pygame.draw.arc(surf, (60, 50, 70), (272, eye_y - 18, 46, 34), 0, math.pi, 4)
        pygame.draw.arc(surf, (150, 90, 110), (218, 300, 76, 46), 0, math.pi, 4)
    elif eye == "angry":
        pygame.draw.circle(surf, (60, 50, 70), (219, eye_y), 10)
        pygame.draw.circle(surf, (60, 50, 70), (295, eye_y), 10)
        pygame.draw.arc(surf, (150, 90, 110), (218, 306, 76, 46), math.pi, 2 * math.pi, 4)
    elif eye == "surprise":
        pygame.draw.circle(surf, (60, 50, 70), (219, eye_y), 13)
        pygame.draw.circle(surf, (60, 50, 70), (295, eye_y), 13)
        pygame.draw.circle(surf, (250, 240, 245), (219, eye_y - 4), 4)
        pygame.draw.circle(surf, (250, 240, 245), (295, eye_y - 4), 4)
        pygame.draw.ellipse(surf, (150, 90, 110), (232, 302, 48, 40), 4)
    else:  # normal
        pygame.draw.ellipse(surf, (60, 50, 70), (204, eye_y - 12, 30, 24))
        pygame.draw.ellipse(surf, (60, 50, 70), (280, eye_y - 12, 30, 24))
        pygame.draw.line(surf, (150, 90, 110), (232, 316), (280, 316), 4)
    pygame.draw.polygon(surf, dress, [(256, 320), (196, 560), (316, 560)])
    pygame.draw.ellipse(surf, (250, 236, 226), (196, 540, 120, 90))
    pygame.draw.circle(surf, (255, 231, 190), (256, 352), 14)
    return surf


# ---------------- 音频：音效 + BGM（wav → ogg） ----------------

def _write_wav(path: Path, frames: bytes, sr=44100):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(frames)


def _to_ogg(wav: Path, ogg: Path):
    import threading

    import soundfile as sf

    def _run():
        data, sr = sf.read(str(wav), dtype="int16")
        sf.write(str(ogg), data, sr, format="OGG", subtype="VORBIS")

    threading.stack_size(32 * 1024 * 1024)
    t = threading.Thread(target=_run)
    t.start()
    t.join()


def sfx(path: Path, kind: str):
    sr = 44100
    frames = bytearray()
    if kind == "click":
        n = int(sr * 0.045)
        for i in range(n):
            t = i / sr
            env = math.exp(-t * 90)
            v = math.sin(2 * math.pi * 1200 * t) * 0.6 + math.sin(2 * math.pi * 2400 * t) * 0.2
            frames += struct.pack("<h", int(10000 * env * v))
    elif kind == "page":
        n = int(sr * 0.22)
        rnd = random.Random(9)
        for i in range(n):
            t = i / sr
            env = math.exp(-t * 14) * (1 - t / 0.22)
            v = (rnd.random() * 2 - 1) * 0.7 + math.sin(2 * math.pi * (600 + 2200 * t) * t) * 0.3
            frames += struct.pack("<h", int(9000 * env * v))
    elif kind == "door":
        n = int(sr * 0.35)
        rnd = random.Random(4)
        for i in range(n):
            t = i / sr
            env = math.exp(-t * 8)
            v = math.sin(2 * math.pi * 90 * t) * 0.8 + (rnd.random() * 2 - 1) * 0.25
            frames += struct.pack("<h", int(12000 * env * v))
    else:  # rain：3 秒雨声（可循环）
        n = int(sr * 3.0)
        rnd = random.Random(2)
        low = 0.0
        for i in range(n):
            t = i / sr
            noise = rnd.random() * 2 - 1
            low = low * 0.92 + noise * 0.08
            env = min(1.0, t / 0.15) * min(1.0, (3.0 - t) / 0.15)
            frames += struct.pack("<h", int(7000 * env * (noise * 0.45 + low * 0.55)))
    wav = path.with_suffix(".wav")
    _write_wav(wav, bytes(frames), sr)
    _to_ogg(wav, path)
    wav.unlink(missing_ok=True)
    print("sfx:", path.name, path.stat().st_size, "bytes")


def bgm_day(path: Path, seconds=60):
    """明亮大调：C - G - Am - F，带轻微琶音。"""
    sr = 44100
    chords = [(261.6, 329.6, 392.0), (196.0, 246.9, 392.0),
              (220.0, 261.6, 329.6), (174.6, 220.0, 349.2)]
    frames = bytearray()
    for i in range(sr * seconds):
        t = i / sr
        bar = int(t // 4) % 4
        seg = t % 4
        env = 0.55 + 0.45 * math.exp(-seg * 0.55)
        chord = chords[bar]
        v = sum(math.sin(2 * math.pi * f * t) for f in chord) / 3
        v += 0.18 * math.sin(2 * math.pi * chord[0] * 2 * t) * (0.5 + 0.5 * math.sin(2 * math.pi * 2 * t))
        v *= 0.97 + 0.03 * math.sin(2 * math.pi * 4 * t)
        frames += struct.pack("<h", max(-32767, min(32767, int(11000 * env * v))))
    wav = path.with_suffix(".wav")
    _write_wav(wav, bytes(frames), sr)
    _to_ogg(wav, path)
    wav.unlink(missing_ok=True)
    print("bgm:", path.name, path.stat().st_size, "bytes")


def _characters_doc() -> dict:
    """自带角色库：与上面的立绘素材一一对应（新建工程/示例工程直接可用）。"""
    return {
        "schema": 1,
        "characters": [
            {"id": "林晚", "name": "林晚", "color": "#ffb3c8", "kind": "default",
             "avatars": {"微笑": "林晚_微笑", "生气": "林晚_生气", "惊讶": "林晚_惊讶"},
             "layers": {}, "voice": "林晚_",
             "notes": "示例主角：温柔、嘴硬心软"},
            {"id": "苏晴", "name": "苏晴", "color": "#8ecae6", "kind": "default",
             "avatars": {"微笑": "苏晴_微笑", "默认": "苏晴_默认"},
             "layers": {}, "voice": "苏晴_",
             "notes": "示例配角：开朗、爱吐槽"},
        ],
    }


def sync_to_games():
    """把模板素材同步进示例/新游戏工程（只补缺，不覆盖用户修改）。"""
    import json

    sources = sorted(IMG.glob("*.png")) + sorted(AUD.glob("*.ogg"))
    # 模板自身的角色库（新建工程时随模板一起复制）
    (TPL / "characters.json").write_text(
        json.dumps(_characters_doc(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for game in TARGETS:
        if not game.is_dir():
            continue
        added = 0
        for src in sources:
            sub = "images" if src.suffix == ".png" else "audio"
            dst = game / sub / src.name
            if not dst.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                added += 1
        char_json = game / "characters.json"
        if not char_json.exists():   # 已有角色库不覆盖（用户可能改过）
            char_json.write_text(
                json.dumps(_characters_doc(), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8")
            added += 1
        print(f"同步 {game.name}: +{added} 个素材/配置")


def main(argv=None) -> int:
    if "--sync-only" not in (argv or sys.argv):
        pygame.init()
        pygame.font.init()
        bg_corridor()
        bg_street_night()
        bg_park()
        bg_room()
        bg_cafe()
        bg_rain()
        for name, hair, dress, eye in [
            ("林晚_微笑", (120, 96, 150), (238, 176, 190), "smile"),
            ("林晚_生气", (110, 88, 140), (214, 108, 118), "angry"),
            ("林晚_惊讶", (120, 96, 150), (238, 176, 190), "surprise"),
            ("苏晴_微笑", (96, 78, 64), (150, 196, 214), "smile"),
            ("苏晴_默认", (96, 78, 64), (150, 196, 214), "normal"),
        ]:
            pygame.image.save(_sprite(hair, dress, eye), str(IMG / f"{name}.png"))
            print("sprite:", name)
        for kind in ("click", "page", "door", "rain"):
            sfx(AUD / f"{kind}.ogg", kind)
        bgm_day(AUD / "bgm_day.ogg")
    sync_to_games()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
