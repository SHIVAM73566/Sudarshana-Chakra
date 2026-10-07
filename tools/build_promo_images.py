"""Cinematic promo-image generator for Sudarshana Chakra AI.

Composes 1920x1080 (16:9) storefront visuals from the real brand assets
(logo + locked avatar) using Pillow + numpy. Outputs go to /promos/.
Run:  .venv\\Scripts\\python.exe tools/build_promo_images.py
"""
from __future__ import annotations

import math
import os
import random
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

BASE_DIR = Path(__file__).resolve().parent.parent
LOGO_PATH = BASE_DIR / "assets" / "sudarshana_chakra_logo_core.png"
AVATAR_PATH = BASE_DIR / "assets" / "sudarshana_avatar_core.png"
OUT_DIR = BASE_DIR / "promos"

W, H = 1920, 1080

TEAL = (0, 240, 255)
BLUE = (30, 144, 255)
VIOLET = (124, 92, 232)
SILVER = (198, 208, 224)
WHITE = (246, 250, 255)
GREEN = (0, 255, 170)

_FONT_BOLD = None
_FONT_REG = None
_FONT_MONO = None


def _load(path: str) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, 40)


def fonts():
    global _FONT_BOLD, _FONT_REG, _FONT_MONO
    if _FONT_BOLD is not None:
        return _FONT_BOLD, _FONT_REG, _FONT_MONO
    fdir = r"C:\Windows\Fonts"
    _FONT_BOLD = _FONT_REG = _FONT_MONO = None
    for cand in ("segoeuib.ttf", "arialbd.ttf", "bahnschrift.ttf"):
        p = os.path.join(fdir, cand)
        if os.path.exists(p):
            try:
                _FONT_BOLD = ImageFont.truetype(p, 40)
                break
            except Exception:
                pass
    for cand in ("segoeui.ttf", "arial.ttf", "bahnschrift.ttf"):
        p = os.path.join(fdir, cand)
        if os.path.exists(p):
            try:
                _FONT_REG = ImageFont.truetype(p, 40)
                break
            except Exception:
                pass
    for cand in ("consolab.ttf", "consola.ttf", "courbd.ttf", "cour.ttf"):
        p = os.path.join(fdir, cand)
        if os.path.exists(p):
            try:
                _FONT_MONO = ImageFont.truetype(p, 40)
                break
            except Exception:
                pass
    if _FONT_BOLD is None:
        _FONT_BOLD = ImageFont.load_default(40)
    if _FONT_REG is None:
        _FONT_REG = ImageFont.load_default(40)
    if _FONT_MONO is None:
        _FONT_MONO = ImageFont.load_default(40)
    return _FONT_BOLD, _FONT_REG, _FONT_MONO


def font(kind: str, px: int):
    fb, fr, fm = fonts()
    src = {"bold": fb, "reg": fr, "mono": fm}[kind]
    if isinstance(src, ImageFont.FreeTypeFont):
        try:
            return src.font_variant(size=px)
        except Exception:
            return ImageFont.truetype(os.path.join(r"C:\Windows\Fonts",
                {"bold": "arialbd.ttf", "reg": "arial.ttf", "mono": "consola.ttf"}[kind]), px)
    return ImageFont.load_default(px)


def draw_text_glow(img, xy, text, font, fill, glow, anchor="mm", blur=10, galpha=110):
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.text(xy, text, font=font, fill=tuple(glow) + (galpha,), anchor=anchor, stroke_width=2, stroke_fill=(0, 0, 0, 160))
    layer = layer.filter(ImageFilter.GaussianBlur(blur))
    img.alpha_composite(layer, (0, 0))
    d = ImageDraw.Draw(img)
    d.text(xy, text, font=font, fill=tuple(fill) + (255,), anchor=anchor, stroke_width=1, stroke_fill=(0, 0, 0, 200))


# ---------------------------------------------------------------- background
def gradient_base(seed: int):
    rng = random.Random(seed)
    top = np.array([4, 6, 16], dtype=np.float32)
    mid = np.array([8, 20, 46], dtype=np.float32)
    bot = np.array([11, 34, 66], dtype=np.float32)
    f = np.linspace(0, 1, H, dtype=np.float32)
    col = np.stack([np.interp(f, [0.0, 0.55, 1.0], [top[c], mid[c], bot[c]]) for c in range(3)], axis=1)
    base = np.zeros((H, W, 4), dtype=np.uint8)
    base[..., 3] = 255
    for c in range(3):
        base[..., c] = np.tile(col[:, c], (W, 1)).T  # (H,W)
    img = Image.fromarray(base, "RGBA")

    def glow(cx, cy, rx, ry, color, alpha):
        g = np.zeros((H, W, 4), dtype=np.float32)
        g[..., 3] = 255
        yy2, xx2 = np.mgrid[0:H, 0:W].astype(np.float32)
        d2 = ((xx2 - cx) / rx) ** 2 + ((yy2 - cy) / ry) ** 2
        m = np.clip(1.0 - np.sqrt(np.maximum(d2, 0.0)), 0, 1) ** 1.6
        for c, v in enumerate(color):
            g[..., c] = v
        g[..., 3] = m * alpha
        layer = Image.fromarray(np.clip(g, 0, 255).astype(np.uint8), "RGBA")
        img.alpha_composite(layer)

    glow(W * 0.8, H * 0.25, W * 0.55, H * 0.5, TEAL, 70)
    glow(W * 0.18, H * 0.72, W * 0.6, H * 0.55, BLUE, 60)
    glow(W * 0.5, H * 1.05, W * 0.85, H * 0.45, VIOLET, 55)

    # starfield
    draw = ImageDraw.Draw(img)
    for i in range(260):
        x = rng.randint(0, W - 1)
        y = rng.randint(0, H - 1)
        r = rng.choice((1, 1, 1, 2))
        a = rng.randint(60, 200)
        tint = rng.choice([WHITE, TEAL, SILVER, BLUE, WHITE, SILVER])
        draw.ellipse([x, y, x + r * 2, y + r * 2], fill=tint + (a,))
    for i in range(18):
        x = rng.randint(0, W - 1)
        y = rng.randint(0, H - 1)
        lg = rng.randint(3, 6)
        draw.line([x, y, x + lg * 3, y + lg], fill=TEAL + (60,))

    # perspective grid floor
    gd = ImageDraw.Draw(img)
    horizon = H * 0.78
    cx = W * 0.5
    for k in range(-18, 19):
        x = cx + k * 62
        gd.line([x, horizon, cx + k * 14, H + 60], fill=(0, 240, 255, 26), width=1)
    for row in range(1, 16):
        y = horizon + (row ** 1.7) * 4
        if y > H:
            break
        gd.line([0, y, W, y], fill=(0, 220, 255, 20), width=1)

    # scanlines
    for y in range(0, H, 4):
        ImageDraw.Draw(img).line([0, y, W, y], fill=(255, 255, 255, 7))

    # vignette
    yy2, xx2 = np.mgrid[0:H, 0:W].astype(np.float32)
    d = np.sqrt(((xx2 - W / 2) / (W / 2)) ** 2 + ((yy2 - H / 2) / (H / 2)) ** 2)
    v = np.clip((d - 0.62) / 0.55, 0, 1) * 0.55
    vim = Image.new("RGBA", (W, H))
    pd = np.zeros((H, W, 4), dtype=np.uint8)
    pd[..., 3] = (v * 255).astype(np.uint8)
    img.alpha_composite(Image.fromarray(pd, "RGBA"))
    return img


def load_logo():
    return Image.open(LOGO_PATH).convert("RGBA")


def load_avatar(dpx: int):
    av = Image.open(AVATAR_PATH).convert("RGB")
    s = min(av.size)
    l = (av.width - s) // 2
    t = (av.height - s) // 3
    av = av.crop((l, t, l + s, t + s)).resize((dpx, dpx), Image.LANCZOS)
    mask = Image.new("L", (dpx, dpx), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, dpx, dpx], fill=255)
    out = Image.new("RGBA", (dpx, dpx), (0, 0, 0, 0))
    out.paste(av, (0, 0), mask)
    return out


def place_logo(img, height: int, x: int, y: int, glow=True, alpha=255):
    lg = load_logo()
    w = int(round(lg.width * height / lg.height))
    lg = lg.resize((w, height), Image.LANCZOS)
    if glow:
        layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
        layer.alpha_composite(lg, (x, y))
        layer = layer.filter(ImageFilter.GaussianBlur(22))
        img.alpha_composite(layer, (0, 0))
    if alpha < 255:
        lg.putalpha(lg.getchannel("A").point(lambda a: int(a * alpha / 255)))
    img.alpha_composite(lg, (x, y))
    return w


def avatar_hud(img, center, dpx):
    av = load_avatar(dpx)
    av.putalpha(av.getchannel("A").point(lambda a: min(255, int(a * 0.98))))
    # glow under avatar
    glow = Image.new("RGBA", av.size, (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([0, 0, dpx, dpx], fill=TEAL + (120,))
    glow = glow.filter(ImageFilter.GaussianBlur(28))
    img.alpha_composite(glow, (center[0] - dpx // 2, center[1] - dpx // 2))
    img.alpha_composite(av, (center[0] - dpx // 2, center[1] - dpx // 2))

    d = ImageDraw.Draw(img)
    rings = [(dpx // 2 + 26, 2), (dpx // 2 + 44, 1), (dpx // 2 + 72, 3)]
    for rr, wd in rings:
        d.ellipse([center[0] - rr, center[1] - rr, center[0] + rr, center[1] + rr],
                  outline=TEAL + ((190 if wd > 1 else 120),), width=wd)
    # tick marks orbiting
    for k in range(36):
        ang = math.radians(k * 10)
        r1 = dpx // 2 + 20
        r2 = dpx // 2 + 34
        c = math.cos(ang), math.sin(ang)
        d.line([center[0] + c[0] * r1, center[1] + c[1] * r1,
                center[0] + c[0] * r2, center[1] + c[1] * r2], fill=TEAL + ((150 if k % 3 else 230),), width=2)
    # corner reticle brackets
    R = dpx // 2 + 74
    for sgn in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
        bx, by = center[0] + sgn[0] * (R + 10), center[1] + sgn[1] * (R + 10)
        d.line([bx - sgn[0] * 46, by, bx, by], fill=TEAL + (255,), width=3)
        d.line([bx, by - sgn[1] * 46, bx, by], fill=TEAL + (255,), width=3)
    return R + 14


def pill(img, x, y, text, color=TEAL, px=30, border=True):
    d = ImageDraw.Draw(img)
    f = font("bold", px)
    tw = d.textlength(text, font=f)
    w = int(tw) + 72
    h = px + 34
    d.rounded_rectangle([x, y, x + w, y + h], radius=h // 2, fill=color + (28,), outline=color + (215,) if border else None, width=2)
    d.text((x + 26, y + h // 2), ">", font=font("bold", px - 6), fill=color + (255,), anchor="lm")
    tt = (x + 34, y + h // 2)
    d.text(tt, text, font=f, fill=tuple(WHITE) + (255,), anchor="lm")
    return w, h


def badge(img, cx, y, text, color=GREEN):
    d = ImageDraw.Draw(img)
    f = font("mono", 26)
    tw = d.textlength(text, font=f)
    w = int(tw) + 56
    h = 48
    x = int(cx - w / 2)
    d.rounded_rectangle([x, y, x + w, y + h], radius=h // 2, fill=(0, 0, 0, 150), outline=color + (230,), width=2)
    d.text((x + w // 2, y + h // 2), text, font=f, fill=color + (255,), anchor="mm")
    d.ellipse([x + 14, y + h // 2 - 5, x + 24, y + h // 2 + 5], fill=color + (255,))
    return w


# ------------------------------------------------------------------ variants
def cover():
    img = gradient_base(1)
    place_logo(img, 300, 150, 300)
    # avatar HUD right
    cx, cy = 1400, 470
    avatar_hud(img, (cx, cy), 300)
    fb, fr, fm = fonts()
    # HUD label
    d = ImageDraw.Draw(img)
    d.text((cx, cy + 250), "GUARDIAN - PERMANENT COMPANION", font=font("mono", 30), fill=TEAL + (255,), anchor="mm")
    d.text((cx, cy + 292), "* locked avatar * immutable identity", font=font("mono", 22), fill=SILVER + (200,), anchor="mm")

    # tagline
    draw_text_glow(img, (150, 760), "SUPER-INTELLIGENT SYSTEM", font("bold", 92), WHITE, TEAL, anchor="lm")
    d.text((150, 830), "Autonomous Desktop Operating Intelligence  -  Built to secure. Built to evolve.", font=font("reg", 36), fill=SILVER + (255,), anchor="lm")

    # callouts
    y = 920
    for t in ("BIOMETRIC VOICE AUTH", "GEMINI & NVIDIA DUAL LLM", "5-TIER VIBE SECURITY", "AUTONOMOUS SELF-HEALING"):
        pill(img, 150, y, t, px=28)
        y += 78
    draw_text_glow(img, (W - 150, H - 46), "SUDARSHANA CHAKRA AI", font("bold", 30), TEAL, TEAL, anchor="rm")
    d.text((W - 150, H - 10), "v1.0.0", font=font("mono", 22), fill=SILVER + (170,), anchor="rm")
    return img


def dashboard_view():
    img = gradient_base(2)
    place_logo(img, 170, 90, 90)
    fb, fr, fm = fonts()
    d = ImageDraw.Draw(img)

    # central holographic portal
    cx, cy = 720, 520
    r = avatar_hud(img, (cx, cy), 380)
    d.arc([cx - r - 60, cy - r - 60, cx + r + 60, cy + r + 60], start=0, end=150, fill=TEAL + (90,), width=12)
    d.arc([cx - r - 60, cy - r - 60, cx + r + 60, cy + r + 60], start=200, end=330, fill=BLUE + (90,), width=12)
    d.text((cx, cy + 330), "ACTIVE VOICE AUTH", font=font("bold", 42), fill=TEAL + (255,), anchor="mm")
    d.text((cx, cy + 382), "Voice biometric gate engaged  -  pass-phrase required", font=font("reg", 26), fill=SILVER + (220,), anchor="mm")
    badge(img, cx, cy + 434, "LOCK STATE: SECURE", GREEN)

    # FFT waveform strip bottom-left
    wave_x, wave_y, wave_w, wave_h = 52, 830, 720, 150
    d.rounded_rectangle([wave_x, wave_y, wave_x + wave_w, wave_y + wave_h], radius=18, fill=(0, 0, 0, 120), outline=TEAL + (90,), width=2)
    rng = random.Random(9)
    bars = 48
    bw = (wave_w - 40) / bars
    for i in range(bars):
        hb = rng.randint(14, wave_h - 40)
        hb = int(hb * (0.5 + 0.5 * abs(math.sin(i * 0.55))))
        x0 = wave_x + 20 + i * bw
        y0 = wave_y + wave_h - 20
        col = TEAL if hb > wave_h * 0.55 else BLUE
        d.rounded_rectangle([x0, y0 - hb, x0 + bw * 0.7, y0], radius=3, fill=col + (180,))
    d.text((wave_x + wave_w // 2, wave_y + 24), "LIVE FFT WAVEFORM   *  SUDARSHANA LISTENING", font=font("mono", 22), fill=TEAL + (230,), anchor="mm")

    # right callout panel
    y = 260
    for t in ("MODALITY: VOICE + VISION", "PROVIDER: GEMINI", "THREAT: NEUTRALIZED", "MEMORY: SYNCED"):
        pill(img, 1180, y, t, px=27)
        y += 82
    draw_text_glow(img, (W - 60, H - 50), "SUDARSHANA CHAKRA AI  -  DASHBOARD", font("bold", 26), TEAL, TEAL, anchor="rm")
    return img


def zip_proof():
    img = gradient_base(3)
    place_logo(img, 170, 90, 70)
    fb, fr, fm = fonts()
    d = ImageDraw.Draw(img)

    # file-tree panel
    px0, py0, pww, phh = 120, 280, 720, 560
    d.rounded_rectangle([px0, py0, px0 + pww, py0 + phh], radius=20, fill=(0, 0, 0, 150), outline=SILVER + (120,), width=2)
    d.text((px0 + 40, py0 + 44), "OPENCODE  -  RELEASE TREE", font=font("mono", 24), fill=TEAL + (255,), anchor="lm")
    mono = font("mono", 24)
    rows = [
        ("/", "Sudarshana_Chakra_AI_v1.0.0", TEAL),
        ("", ".env.example", SILVER),
        ("", "README.md", SILVER),
        ("", "LICENSE", SILVER),
        ("", "main.py", SILVER),
        ("", "ui.py", SILVER),
        ("", "requirements.txt", SILVER),
        ("", "core/", BLUE),
        ("", "actions/", BLUE),
        ("", "assets/", BLUE),
        ("", "start_sudarshana.bat", SILVER),
        ("", "bootstrap.ps1", SILVER),
        ("", "dist/sudarshana_chakra_ai_v1.0.0.zip", GREEN),
    ]
    ry = py0 + 96
    for ind, txt, col in rows:
        pre = "  " if ind else "     "
        d.text((px0 + 40 + 8, ry), pre + txt, font=mono, fill=col + (255,), anchor="lm")
        ry += 36
    d.text((px0 + pww - 40, py0 + phh - 34), "no secrets  *  no tests  *  no git", font=font("mono", 18), fill=SILVER + (150,), anchor="rm")

    # zip box
    zx, zy, zw, zh = 980, 300, 760, 300
    d.rounded_rectangle([zx, zy, zx + zw, zy + zh], radius=24, fill=(6, 14, 34, 235), outline=TEAL + (200,), width=3)
    ImageDraw.Draw(img).rounded_rectangle([zx, zy, zx + zw, zy + zh], radius=24, outline=TEAL + (80,), width=10)
    # zipper
    zzc = zx + zw - 70
    for yy2 in range(zy + 26, zy + zh - 26, 12):
        d.line([zzc - 26, yy2, zzc + 26, yy2], fill=SILVER + (200,), width=1)
    d.ellipse([zzc - 10, zy + 20, zzc + 10, zy + 40], fill=SILVER + (255,))
    d.text((zx + zw // 2 - 60, zy + zh // 2), "Sudarshana_Chakra_AI_v1.0.0.zip", font=font("bold", 38), fill=WHITE + (255,), anchor="mm")
    d.text((zx + zw // 2 - 60, zy + zh // 2 + 52), "270 files  *  12.92 MB  *  SHA-256 verified", font=font("mono", 22), fill=SILVER + (200,), anchor="mm")

    # READY TO SELL ribbon
    rbx, rby, rbw, rbh = zx + 40, zy - 46, 220, 60
    d.rounded_rectangle([rbx, rby, rbx + rbw, rby + rbh], radius=rbh // 2, fill=GREEN + (235,), outline=None, width=0)
    d.text((rbx + rbw // 2, rby + rbh // 2), "READY TO SELL", font=font("bold", 30), fill=(3, 20, 12, 255), anchor="mm")

    platforms = "Codester     Code Robotics     SellAnyCode.com     Payhip"
    draw_text_glow(img, (W // 2, 700), platforms, font("bold", 44), WHITE, TEAL, anchor="mm")
    d.text((W // 2, 772), "Full source  *  commercial EULA  *  .env.example  *  launchers  *  promo kit", font=font("reg", 28), fill=SILVER + (230,), anchor="mm")
    return img


def dual_llm():
    img = gradient_base(4)
    place_logo(img, 150, 90, 80)
    fb, fr, fm = fonts()
    d = ImageDraw.Draw(img)
    cx, cy = W // 2, 540
    # beam between orbs
    beam = Image.new("RGBA", img.size, (0, 0, 0, 0))
    bd = ImageDraw.Draw(beam)
    for kk in range(5):
        o = (0, 240, 255, 26 + kk * 20)

        bd.line([cx - 380, cy, cx + 380, cy], fill=o, width=18 + kk * 6)
    beam = beam.filter(ImageFilter.GaussianBlur(12))
    img.alpha_composite(beam)
    d.line([cx - 380, cy, cx + 380, cy], fill=WHITE + (220,), width=3)

    for sgn, name, rgb in ((-1, "GEMINI", BLUE), (1, "NVIDIA NIM", GREEN)):
        ox, oy = cx + sgn * 380, cy
        d.ellipse([ox - 30, oy - 30, ox + 30, oy + 30], fill=rgb + (255,))
        d.ellipse([ox - 46, oy - 46, ox + 46, oy + 46], outline=rgb + (160,), width=3)
        d.text((ox, oy + 96), name, font=font("bold", 40), fill=rgb + (255,), anchor="mm")
        d.text((ox, oy + 138), "DUAL-LLM ROUTING", font=font("mono", 24), fill=SILVER + (220,), anchor="mm")

    d.text((cx, cy - 250), "TWO ENGINES. ONE COMMAND CORE.", font=font("bold", 66), fill=WHITE + (255,), anchor="mm")
    d.text((cx, cy - 190), "Gemini drives live voice & vision; NVIDIA NIM powers deep planning.", font=font("reg", 30), fill=SILVER + (230,), anchor="mm")

    y = 780
    for t in ("FAILOVER SAFE", "PROMPT-INJECTION SHIELD", "CONTEXT ROUTING"):
        pill(img, 210 + (t == "CONTEXT ROUTING") * 560, y, t, px=26)
        y += 74
    return img


def self_healing():
    img = gradient_base(5)
    place_logo(img, 150, 90, 80)
    fb, fr, fm = fonts()
    d = ImageDraw.Draw(img)
    # EKG heartbeat across center
    yy0 = 520
    d.rounded_rectangle([110, yy0 - 60, W - 110, yy0 + 60], radius=20, fill=(0, 0, 0, 130), outline=GREEN + (120,), width=2)
    pts = []
    n = 340
    for i in range(n):
        t = i / n
        basev = yy0 + 18 * math.sin(t * math.pi * 6)
        if 0.42 < t < 0.46:
            seg = (t - 0.42) / 0.04
            basev = yy0 - 120 * math.sin(seg * math.pi) + 16
        pts.append((110 + 40 + t * (W - 300), basev))
    for k in range(1, len(pts)):
        d.line([pts[k - 1], pts[k]], fill=GREEN + (255,), width=4)
    d.ellipse([pts[int(n * 0.44)][0] - 8, pts[int(n * 0.44)][1] - 8, pts[int(n * 0.44)][0] + 8, pts[int(n * 0.44)][1] + 8], fill=GREEN + (255,))

    draw_text_glow(img, (W // 2, 300), "AUTONOMOUS SELF-HEALING SYSTEM", font("bold", 66), WHITE, GREEN, anchor="mm")
    d.text((W // 2, 362), "Runtime exceptions are caught, root-caused, patched and verified - without crashing.", font=font("reg", 30), fill=SILVER + (230,), anchor="mm")

    y = 700
    for t in ("TRACEBACK ANALYSIS", "LLM CODE PATCHER", "ISOLATED CRUCIBLE TEST", "HUD TELEMETRY"):
        pill(img, 150, y, t, px=26)
        y += 80
    # status chips right
    d.text((W - 150, 715), "[HEAL] 2 patches applied today", font=font("mono", 26), fill=GREEN + (255,), anchor="rm")
    d.text((W - 150, 760), "[GUARD] integrity verified", font=font("mono", 26), fill=GREEN + (255,), anchor="rm")
    d.text((W - 150, 805), "[CORE] boot chain stable", font=font("mono", 26), fill=SILVER + (220,), anchor="rm")
    return img


def save(img, name):
    img = img.convert("RGB")
    path = OUT_DIR / name
    img.save(path, "PNG", optimize=True)
    print("saved", name, img.size, f"{os.path.getsize(path)/1024:.0f} KB")


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    core = {
        "chakra_ai_cover_16x9.png": cover,
        "chakra_dashboard_voice_auth_16x9.png": dashboard_view,
        "chakra_marketplace_zip_proof_16x9.png": zip_proof,
        "chakra_dual_llm_16x9.png": dual_llm,
        "chakra_self_healing_16x9.png": self_healing,
    }
    aliases = {
        "codester_banner_chakra_ai.png": "chakra_ai_cover_16x9.png",
        "sellanycode_banner_chakra_ai.png": "chakra_dashboard_voice_auth_16x9.png",
        "payhip_preview_chakra_ai.png": "chakra_marketplace_zip_proof_16x9.png",
        "code_robotics_preview_chakra_ai.png": "chakra_dual_llm_16x9.png",
    }
    rendered = {}
    for name, fn in core.items():
        save(fn(), name)
        rendered[name] = OUT_DIR / name
    for alias, src in aliases.items():
        d = rendered[src]
        out = OUT_DIR / alias
        out.write_bytes(d.read_bytes())
        print("aliased", alias)
    print("DONE ->", OUT_DIR)


if __name__ == "__main__":
    main()