"""Draws KaiDrop's icon: an arrow dropping a pink note into a tray, on the dark
background KaiPlayer's and KaiRadio's icons use, in KaiDrop's mint.

Writes assets/icon.png (256x256), assets/kaidrop.ico (16 to 256) for the
.exe, and kaidrop/appicon.py for the window.

Usage: python tools/make_icon.py
"""
import base64
import io
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

SIZE = 256
SCALE = 4  # Drawn larger, then shrunk, for smooth edges.
MINT = (94, 224, 168)
PINK = (255, 107, 157)
BG_CENTER = (40, 42, 58)
BG_EDGE = (16, 17, 24)
ASSETS = Path(__file__).resolve().parent.parent / "assets"
PACKAGE = ASSETS.parent / "kaidrop"


def background(size):
    img = Image.new("RGB", (size, size))
    px = img.load()
    c = size / 2
    for y in range(size):
        for x in range(size):
            t = min(1.0, math.hypot(x - c, y - c * 0.9) / (size * 0.72))
            px[x, y] = tuple(int(a + (b - a) * t) for a, b in zip(BG_CENTER, BG_EDGE))
    return img


def draw():
    s = SIZE * SCALE
    img = background(s).convert("RGBA")
    layer = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    u = s / 256  # One icon pixel.

    # The tray: an open box the files drop into.
    w = int(14 * u)
    d.line((44 * u, 150 * u, 44 * u, 206 * u), fill=MINT, width=w)
    d.line((212 * u, 150 * u, 212 * u, 206 * u), fill=MINT, width=w)
    d.rounded_rectangle((37 * u, 192 * u, 219 * u, 213 * u), radius=10 * u, fill=MINT)
    for x in (44, 212):
        d.ellipse(((x - 7) * u, 143 * u, (x + 7) * u, 157 * u), fill=MINT)

    # The arrow, dropping into it.
    d.rounded_rectangle((106 * u, 34 * u, 150 * u, 128 * u), radius=10 * u, fill=MINT)
    d.polygon([(70 * u, 112 * u), (186 * u, 112 * u), (128 * u, 176 * u)], fill=MINT)

    # A pink note riding the arrow: it's music being sent.
    nx, ny = 121 * u, 138 * u  # The note's head, in the arrowhead.
    top = ny - 46 * u
    d.ellipse((nx - 15 * u, ny - 11 * u, nx + 11 * u, ny + 11 * u), fill=PINK)
    d.rectangle((nx + 5 * u, top, nx + 11 * u, ny), fill=PINK)
    d.polygon([(nx + 5 * u, top), (nx + 22 * u, top + 9 * u), (nx + 22 * u, top + 19 * u),
               (nx + 11 * u, top + 13 * u)], fill=PINK)

    # A soft glow under the shapes.
    glow = layer.filter(ImageFilter.GaussianBlur(10 * u))
    glow.putalpha(glow.getchannel("A").point(lambda a: a * 0.35))
    img = Image.alpha_composite(img, glow)
    img = Image.alpha_composite(img, layer)
    return img.convert("RGB").resize((SIZE, SIZE), Image.LANCZOS)


def main():
    img = draw()
    img.save(ASSETS / "icon.png")
    img.save(ASSETS / "kaidrop.ico", sizes=[(n, n) for n in (16, 24, 32, 48, 64, 128, 256)])
    # The window's own icon, inside the package so the .exe needs no data files.
    sizes = {}
    for n in (64, 32, 16):
        buf = io.BytesIO()
        img.resize((n, n), Image.LANCZOS).save(buf, "PNG", optimize=True)
        sizes[n] = base64.b64encode(buf.getvalue()).decode()
    lines = ['"""KaiDrop\'s icon for its window, as base64 PNGs (made by tools/make_icon.py)."""', "",
             "APP_ICONS = ("] + [f'    "{data}",  # {n}x{n}' for n, data in sizes.items()] + [")", ""]
    (PACKAGE / "appicon.py").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
