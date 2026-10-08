"""Procedural Sudarshana Chakra brand-logo renderer.

Rebuilds the brand image so the central emblem reads unmistakably as a
SUDARSHANA CHAKRA - a symmetric circular disc with concentric rings, a
central hub with radial spokes, and evenly-spaced sharp serrated chakra
blades - upgraded with photorealistic metal, cyan energy and AI HUD styling.
Gear/turbine geometry is deliberately avoided: blades are wide, sharp,
evenly-spaced triangles separated by visible valleys (not meshing teeth),
and the disc is built from distinct concentric ring layers.

Outputs:
    assets/sudarshana_chakra_ai_logo.png        16:9 cinema banner
    assets/sudarshana_chakra_ai_x_logo.png      1024x1024 X.com card

Run:  .venv\\Scripts\\python.exe tools/build_brand_logo.py
"""
from __future__ import annotations

import math
import os
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

BASE_DIR = Path(__file__).resolve().parent.parent
ASSETS = BASE_DIR / "assets"

MAIN_OUT = ASSETS / "sudarshana_chakra_ai_logo.png"
X_OUT = ASSETS / "sudarshana_chakra_ai_x_logo.png"

BW, BH = 1920, 1080
XW, XH = 1024, 1024

TEAL = (0, 240, 255)
BLUE = (40, 130, 255)
SILVER = (198, 208, 224)
WHITE = (248, 252, 255)
STEEL_D = (56, 64, 82)
STEEL_M = (120, 130, 150)
STEEL_H = (206, 216, 232)

_font_cache = {}


def font(name: str, px: int):
    key = (name, px)
    if key not in _font_cache:
        cand = {
            "bold": ("bahnschrift.ttf", "arialbd.ttf", "segoeuib.ttf"),
            "reg": ("bahnschrift.ttf", "segoeui.ttf", "arial.ttf"),
            "mono": ("consolab.ttf", "consola.ttf"),
        }[name]
        path = next((os.path.join(r"C:\Windows\Fonts", c) for c in cand
                     if os.path.exists(os.path.join(r"C:\Windows\Fonts", c))), None)
        _font_cache[key] = ImageFont.truetype(path, px) if path else ImageFont.load_default(px)
    return _font_cache[key]


def radial_bg(w: int, h: int, cx: float, cy: float, r: float) -> Image.Image:
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    d = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) / r
    d = np.clip(d, 0, 1)
    base = np.zeros((h, w, 4), dtype=np.uint8)
    base[..., 3] = 255
    base[..., 0] = np.clip(4 + 9 * (1 - d) ** 2, 0, 255)
    base[..., 1] = np.clip(7 + 14 * (1 - d) ** 2, 0, 255)
    base[..., 2] = np.clip(17 + 34 * (1 - d) ** 2, 0, 255)
    return Image.fromarray(base, "RGBA")


def glow_layer(img: Image.Image, cx: float, cy: float, r: float, color, a: int) -> None:
    g = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(g)
    for rad, al in ((r, 90), (r * 0.62, 50)):
        d.ellipse([cx - rad, cy - rad, cx + rad, cy + rad], fill=tuple(color) + (al,))
    g = g.filter(ImageFilter.GaussianBlur(max(10, r * 0.22)))
    img.alpha_composite(g)


def poly_mask(w: int, h: int, cx: float, cy: float, pts) -> np.ndarray:
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
    m = np.zeros((h, w), dtype=bool)
    d = ImageDraw.Draw(Image.new("L", (w, h), 0))
    d.polygon([(float(x), float(y)) for x, y in pts], fill=255)
    m[:] = np.asarray(Image.new("L", (w, h), 0)).astype(bool)
    return np.asarray(Image.new("L", (w, h), 0)) > 0


def draw_blades(img: Image.Image, cx: float, cy: float, r0: float, r1: float, n: int,
                axis_highlight: bool = True) -> None:
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    arr = np.array(layer)
    STEEL_D_A = np.array(STEEL_D, dtype=np.float64)
    STEEL_H_A = np.array(STEEL_H, dtype=np.float64)
    h, w = img.height, img.width
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
    dx = xx - cx
    dy = yy - cy
    rr = np.sqrt(dx ** 2 + dy ** 2)
    angle = np.arctan2(-dy, dx)
    step = 2 * math.pi / n
    half = step * 0.30
    for k in range(n):
        a = k * step
        t = (angle - a + math.pi) % (2 * math.pi) - math.pi
        inb = np.abs(t) <= half
        radial = (rr >= r0) & (rr <= r1)
        blade = inb & radial
        f = np.clip((rr - r0) / max(1e-6, (r1 - r0)), 0, 1)
        side = 1 - np.abs(t) / half
        bright = 0.34 + 0.72 * (f ** 1.15) + 0.22 * (side ** 3)
        if axis_highlight:
            bright += 0.14 * np.exp(-((t * 3.0) ** 2))
        vs = np.clip(bright, 0, 1)[..., None]
        rgb = STEEL_D_A + (STEEL_H_A - STEEL_D_A) * vs
        mb = blade
        arr[mb, 0] = rgb[mb, 0]
        arr[mb, 1] = rgb[mb, 1]
        arr[mb, 2] = rgb[mb, 2]
        arr[mb, 3] = 255
    img.alpha_composite(Image.fromarray(arr, "RGBA"))
    d = ImageDraw.Draw(img)
    for k in range(n):
        a = k * step
        x1 = cx + r1 * math.cos(a)
        y1 = cy - r1 * math.sin(a)
        d.line([x1 - 1.5, y1, x1 + 1.5, y1], fill=TEAL + (150,), width=2)
    for k in range(n):
        a = k * step
        x0 = cx + r0 * math.cos(a - half)
        y0 = cy - r0 * math.sin(a - half)
        d.line([x0, y0, x0, y0 + 1], fill=TEAL + (90,), width=1)
    img.alpha_composite(Image.new("RGBA", img.size, (0, 0, 0, 0)))


def res_abs(angle: np.ndarray, n: int) -> np.ndarray:
    step = 2 * math.pi / n
    return np.round(angle / step).astype(int) % 3


def annulus(img: Image.Image, cx: float, cy: float, r_outer: float, r_inner: float,
            light: tuple = (BLUE, STEEL_M, STEEL_H), spec: bool = True) -> None:
    h, w = img.height, img.width
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
    dx = xx - cx
    dy = yy - cy
    rr = np.sqrt(dx ** 2 + dy ** 2)
    mask = (rr >= r_inner) & (rr <= r_outer)
    lx = cx - r_outer * 0.4
    ly = cy - r_outer * 0.4
    v = np.clip(((xx - lx) + (yy - ly)) / (2.2 * r_outer) + 0.35, 0, 1)
    arr = np.array(img).copy()
    for c in range(3):
        arr[mask, c] = light[0][c] * (1 - v[mask]) + light[2][c] * v[mask]
    if spec:
        sd = np.abs(np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) - (r_outer + r_inner) / 2)
        ang = np.arctan2(-(yy - cy), (xx - cx))
        lu = np.exp(-((ang + 2.4) ** 2) * 8) * np.exp(-(sd**2) / 40)
        for c in range(3):
            arr[mask, c] = np.clip(arr[mask, c] + lu[mask] * 90, 0, 255)
    img.paste(Image.fromarray(arr, "RGBA"), (0, 0))


def disc_metal(img: Image.Image, cx: float, cy: float, r0: float, r1: float,
               shade: tuple = (STEEL_D, STEEL_M, SILVER)) -> None:
    h, w = img.height, img.width
    ya, xa = np.mgrid[0:h, 0:w].astype(np.float64)
    dx = xa - cx
    dy = ya - cy
    rr = np.sqrt(dx ** 2 + dy ** 2)
    mask = (rr >= r0) & (rr <= r1)
    v = np.clip((rr - r0) / max(1e-6, r1 - r0), 0, 1)
    arr = np.array(img).copy()
    for c in range(3):
        arr[mask, c] = np.clip(
            shade[0][c] * (1 - v[mask]) + shade[2][c] * v[mask], 0, 255)
    img.paste(Image.fromarray(arr, "RGBA"), (0, 0))


def ring_line(img: Image.Image, cx: float, cy: float, r: float, color, wd: int, a: int = 255) -> None:
    d = ImageDraw.Draw(img)
    b = wd / 2
    d.ellipse([cx - r - b, cy - r - b, cx + r + b, cy + r + b],
              outline=tuple(color) + (a,), width=wd)


def circuit_ring(img: Image.Image, cx: float, cy: float, r: float, n: int) -> None:
    d = ImageDraw.Draw(img)
    for k in range(n):
        a0 = k * (2 * math.pi / n)
        a1 = a0 + (2 * math.pi / n) * 0.42
        x0 = cx + r * math.cos(a0)
        y0 = cy - r * math.sin(a0)
        x1 = cx + r * math.cos(a1)
        y1 = cy - r * math.sin(a1)
        d.line([x0, y0, x1, y1], fill=TEAL + (200,), width=2)
    for k in range(n):
        a0 = k * (2 * math.pi / n) + math.pi / n
        rr_ = r + 6
        x0 = cx + rr_ * math.cos(a0)
        y0 = cy - rr_ * math.sin(a0)
        x1 = cx + (r + 14) * math.cos(a0)
        y1 = cy - (r + 14) * math.sin(a0)
        d.line([x0, y0, x1, y1], fill=SILVER + (160,), width=1)


def spokes(img: Image.Image, cx: float, cy: float, r_in: float, r_out: float, n: int) -> None:
    d = ImageDraw.Draw(img)
    for k in range(n):
        a = k * (2 * math.pi / n)
        sw = math.pi / n * 0.30
        p1 = (cx + r_in * math.cos(a - sw), cy - r_in * math.sin(a - sw))
        p2 = (cx + r_in * math.cos(a + sw), cy - r_in * math.sin(a + sw))
        p3 = (cx + r_out * math.cos(a + sw), cy - r_out * math.sin(a + sw))
        p4 = (cx + r_out * math.cos(a - sw), cy - r_out * math.sin(a - sw))
        d.polygon([p1, p2, p3, p4], fill=STEEL_M + (255,))
    for k in range(n):
        a = k * (2 * math.pi / n)
        rm = (r_in + r_out) / 2
        d.line([cx + rm * math.cos(a), cy - rm * math.sin(a),
                cx + rm * 1.02 * math.cos(a), cy - rm * 1.02 * math.sin(a)],
               fill=TEAL + (120,), width=1)


def ai_core(img: Image.Image, cx: float, cy: float, r: float) -> None:
    g = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(g)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(0, 180, 255, 255))
    g = g.filter(ImageFilter.GaussianBlur(6))
    img.alpha_composite(g)
    h, w = img.height, img.width
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
    dx = xx - cx
    dy = yy - cy
    rr = np.sqrt(dx ** 2 + dy ** 2)
    mask = rr <= r
    v = np.clip(1 - rr / r, 0, 1) ** 1.4
    arr = np.array(img).copy()
    fb = mask & (v > 0.02)
    arr[fb, 0] = np.clip(40 + 180 * v[fb], 0, 255)
    arr[fb, 1] = np.clip(140 + 112 * v[fb], 0, 255)
    arr[fb, 2] = np.clip(225 + 28 * v[fb], 0, 255)
    img.paste(Image.fromarray(arr, "RGBA"), (0, 0))
    d = ImageDraw.Draw(img)
    s = r * 0.7
    for k in range(3):
        a = k * (2 * math.pi / 3) - math.pi / 2
        x0 = cx + s * math.cos(a)
        y0 = cy + s * math.sin(a)
        x1 = cx + s * math.cos(a + 2 * math.pi / 3)
        y1 = cy + s * math.sin(a + 2 * math.pi / 3)
        d.line([x0, y0, x1, y1], fill=SILVER + (220,), width=3)
    d.ellipse([cx - r * 0.30, cy - r * 0.30, cx + r * 0.30, cy + r * 0.30],
              outline=WHITE + (255,), width=3)


def chakra(img: Image.Image, cx: float, cy: float, R: float) -> None:
    glow_layer(img, cx, cy, R * 1.30, BLUE, 85)
    glow_layer(img, cx, cy, R * 1.12, TEAL, 60)
    disc_metal(img, cx, cy, 0.19 * R, 0.40 * R, (STEEL_D, STEEL_M, STEEL_H))
    draw_blades(img, cx, cy, 0.985 * R, 1.15 * R, 24)
    disc_metal(img, cx, cy, 0.455 * R, 0.50 * R, (STEEL_D, STEEL_M, STEEL_H))
    annulus(img, cx, cy, 0.80 * R, 0.985 * R)
    ring_line(img, cx, cy, 0.80 * R, TEAL, 2, 190)
    ring_line(img, cx, cy, 0.985 * R, TEAL, 2, 150)
    spokes(img, cx, cy, 0.42 * R, 0.80 * R, 16)
    disc_metal(img, cx, cy, 0.20 * R, 0.42 * R, (STEEL_D, STEEL_M, SILVER))
    circuit_ring(img, cx, cy, 0.30 * R, 12)
    ring_line(img, cx, cy, 0.42 * R, BLUE, 2, 200)
    ring_line(img, cx, cy, 0.20 * R, SILVER, 2, 220)
    ai_core(img, cx, cy, 0.20 * R)
    for k in range(12):
        a = k * (2 * math.pi / 12)
        rx = 0.61 * R
        d = ImageDraw.Draw(img)
        d.ellipse([cx + rx * math.cos(a) - 3, cy - rx * math.sin(a) - 3,
                   cx + rx * math.cos(a) + 3, cy - rx * math.sin(a) + 3],
                  fill=TEAL + (200,))
    ring_line(img, cx, cy, 1.16 * R, TEAL, 2, 65)
    _hud_ticks(img, cx, cy, 1.16 * R, 48)


def _hud_ticks(img: Image.Image, cx: float, cy: float, r: float, n: int) -> None:
    d = ImageDraw.Draw(img)
    for k in range(n):
        a = k * (2 * math.pi / n)
        r1 = r - 6 if k % 2 else r - 12
        x0 = cx + r1 * math.cos(a)
        y0 = cy - r1 * math.sin(a)
        x1 = cx + r * math.cos(a)
        y1 = cy - r * math.sin(a)
        d.line([x0, y0, x1, y1], fill=TEAL + (120,), width=2)


def _glass_panel(img: Image.Image, x, y, w, h, title, rows) -> None:
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([x, y, x + w, y + h], radius=16,
                        fill=(6, 12, 26, 205), outline=TEAL + (140,), width=2)
    d.line([x + 20, y + 44, x + w - 20, y + 44], fill=TEAL + (90,), width=1)
    d.text((x + w // 2, y + 24), title, font=font("mono", 19), fill=TEAL + (255,), anchor="mm")
    yy = y + 62
    for kind, text in rows:
        if kind == "head":
            d.text((x + 22, yy), text, font=font("bold", 22), fill=WHITE + (255,), anchor="lm")
        elif kind == "sub":
            d.text((x + 22, yy), text, font=font("mono", 16), fill=SILVER + (220,), anchor="lm")
        elif kind == "ok":
            d.text((x + 22, yy), text, font=font("mono", 17), fill=TEAL + (255,), anchor="lm")
            d.ellipse([x + w - 30, yy - 5, x + w - 18, yy + 7], fill=(0, 255, 170, 255))
        else:
            d.text((x + 22, yy), text, font=font("mono", 17), fill=WHITE + (220,), anchor="lm")
        yy += 30


def _telemetry(img: Image.Image) -> None:
    d = ImageDraw.Draw(img)
    y0 = BH - 66
    d.line([60, y0, BW - 60, y0], fill=TEAL + (70,), width=1)
    for i, lab in enumerate(("SYSTEM INTEGRITY", "BOOT CHAIN", "BIOMETRIC GATE", "API LINK")):
        x = 90 + i * 460
        seg = 150
        nbars = 9
        bw = seg / nbars
        for b in range(nbars):
            bh = 10 + ((b * 7 + i * 3) % 22)
            col = TEAL if b < 5 + (i % 3) else SILVER
            d.rounded_rectangle([x + b * bw, y0 + 14, x + b * bw + bw * 0.6, y0 + 14 + bh],
                                radius=2, fill=col + (160,))
        d.text((x, y0 + 44), lab, font=font("mono", 16), fill=SILVER + (200,), anchor="lm")


def _metallic_text(img, cx, y, text, px, anchor="mm", glow=TEAL):
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    ld.text((cx, y), text, font=font("bold", px), fill=(255, 255, 255, 255), anchor=anchor)
    g = layer.filter(ImageFilter.GaussianBlur(16))
    img.alpha_composite(g)
    text_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    td = ImageDraw.Draw(text_layer)
    td.text((cx, y), text, font=font("bold", px), fill=(255, 255, 255, 255), anchor=anchor,
            stroke_width=2, stroke_fill=(8, 12, 24, 255))
    mask = np.asarray(text_layer.split()[0]) > 0
    bbox = layer.getbbox()
    if not bbox:
        return
    arr = np.array(img)
    h, w = img.height, img.width
    ymin, ymax = bbox[1] - 12, bbox[3] + 12
    for yy in range(max(0, ymin), min(h, ymax)):
        f = (yy - ymin) / max(1, (ymax - ymin))
        top_c = np.array([220, 232, 248])
        bot_c = np.array([150, 168, 200])
        col = (top_c * (1 - f) + bot_c * f)
        mrow = mask[yy]
        if not mrow.any():
            continue
        arr[yy, mrow, 0] = col[0]
        arr[yy, mrow, 1] = col[1]
        arr[yy, mrow, 2] = col[2]
    spec_row = (ymin + ymax) // 2
    for yy in range(max(0, spec_row - 3), min(h, spec_row + 4)):
        mrow = mask[yy]
        if mrow.any():
            arr[yy, mrow, 0] = np.clip(arr[yy, mrow, 0] + 40, 0, 255)
            arr[yy, mrow, 1] = np.clip(arr[yy, mrow, 1] + 40, 0, 255)
            arr[yy, mrow, 2] = np.clip(arr[yy, mrow, 2] + 40, 0, 255)
    d = ImageDraw.Draw(img)
    img.paste(Image.fromarray(arr, "RGBA"), (0, 0))


def render_main() -> Image.Image:
    img = radial_bg(BW, BH, 960, 470, 900)
    glow_layer(img, 960, 220, 500, BLUE, 40)
    chakra(img, 960, 505, 300)
    _metallic_text(img, 960, 128, "SUDARSHANA CHAKRA", 92)
    _metallic_text(img, 960, 235, "AI", 54)
    _glass_panel(img, 70, 300, 360, 250, "DUAL AI POWER",
                 [("head", "GEMINI + NVIDIA"), ("sub", "parallel LLM routing"), ("ok", "linked")])
    _glass_panel(img, 70, 580, 360, 225, "VOICE BIOMETRIC",
                 [("head", "AUTHENTICATION"), ("ok", "VERIFIED"), ("sub", "pass-phrase gate")])
    _glass_panel(img, 70, 835, 360, 130, "SECURITY",
                 [("head", "5-TIER VIBE"), ("sub", "prompt-injection shield")])
    _glass_panel(img, BW - 430, 300, 360, 250, "AUTONOMOUS AGENT",
                 [("head", "ANALYZE - PLAN"), ("head", "EXECUTE - LEARN"), ("sub", "self-healing loop")])
    _glass_panel(img, BW - 430, 580, 360, 225, "LOCKED COMPANION",
                 [("head", "@chaturvedishivam179"), ("ok", "guardian active"), ("sub", "identity immutable")])
    _glass_panel(img, BW - 430, 835, 360, 130, "MCP NETWORK",
                 [("head", "SPOTIFY - HOME - OS"), ("sub", "tool bus online")])
    _telemetry(img)
    return img


def render_x() -> Image.Image:
    img = radial_bg(XW, XH, 512, 480, 620)
    chakra(img, 512, 470, 270)
    _metallic_text(img, 512, 820, "SUDARSHANA CHAKRA", 62)
    _metallic_text(img, 512, 900, "AI", 40)
    d = ImageDraw.Draw(img)
    d.text((512, 960), "AUTONOMOUS DESKTOP COMPANION", font=font("mono", 22), fill=SILVER + (220,), anchor="mm")
    return img


def main() -> None:
    import hashlib

    ASSETS.mkdir(parents=True, exist_ok=True)
    img = render_main()
    img.save(MAIN_OUT, "PNG")
    ximg = render_x()
    ximg.save(X_OUT, "PNG")
    square = ASSETS / "sudarshana_chakra_ai_logo_square.png"
    ximg.save(square, "PNG")
    for p in (MAIN_OUT, X_OUT, square):
        print("wrote", p.name, p.stat().st_size,
              "SHA", hashlib.sha256(p.read_bytes()).hexdigest()[:16])


if __name__ == "__main__":
    main()