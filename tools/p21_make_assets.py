"""P21 占位素材生成：bg_03/bg_04/她_sad/bgm_02.wav（简单命名，不绑 IP）
色块 + 中央中文文字标识，与 P18 素材风格一致。
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(r"D:\娱乐工作区\自研项目\Moyul引擎\games\示例故事")
IMG = ROOT / "images"
AUD = ROOT / "audio"
IMG.mkdir(exist_ok=True)
AUD.mkdir(exist_ok=True)

W, H = 1280, 720

def block(name: str, color: tuple, text: str) -> None:
    img = Image.new("RGB", (W, H), color)
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype(str(ROOT / "fonts" / "simhei.ttf"), 56)
    except Exception:
        font = ImageFont.load_default()
    tw, th = d.textbbox((0, 0), text, font=font)[2:4]
    d.text(((W - tw) // 2, (H - th) // 2), text, fill=(255, 255, 255), font=font)
    img.save(IMG / f"{name}.png")
    print(f"  images/{name}.png {color}")

# bg_03 车站前（黄昏前，蓝灰+暖底） / bg_04 黄昏街道（橙紫）
block("bg_03", (120, 130, 150), "车站前")
block("bg_04", (190, 120, 90), "黄昏街道")
# 她_sad（灰蓝立绘块）
block("她_sad", (90, 100, 120), "她-sad")

# bgm_02.wav 静音占位（3 秒，与 bgm_01 同制式）
import wave, struct
with wave.open(str(AUD / "bgm_02.wav"), "w") as w:
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(22050)
    silence = b"\x00\x00" * (22050 * 3)
    w.writeframes(silence)
print("  audio/bgm_02.wav 静音 3s")

# 校验旧素材齐备
need = ["bg_01", "bg_02", "bg_03", "bg_04", "cg_01", "cg_02",
        "她_normal", "她_smile", "她_sad"]
for n in need:
    p = IMG / f"{n}.png"
    print(("OK  " if p.exists() else "MISS") + f" {n}.png")
for n in ["bgm_01", "bgm_02", "voice_01", "voice_02"]:
    p = AUD / f"{n}.wav"
    print(("OK  " if p.exists() else "MISS") + f" {n}.wav")
