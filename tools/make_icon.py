"""KaiDrop's icon is no longer drawn here: all the Kai apps' icons come from one
script, switch2homebrew-submit/tools/make_app_icons.py, which writes
switch2homebrew-submit/icons/kaidrop.jpg (with Mizuiro's seal) and
mizuiroame/assets/icons/kaidrop-256.png (without it). This makes KaiDrop's
icon files from those two:

- assets/icon.png (256x256, with the seal);
- assets/kaidrop.ico for the .exe and Explorer: 16 to 256, the seal only from
  48 up (smaller, it would be a smudge in the corner);
- kaidrop/appicon.py, the window's own icon (64, 32 and 16, without the seal).

Usage: python tools/make_icon.py
       (run make_app_icons.py first after changing the symbol or its colors)
"""
import base64
import io
import sys
from pathlib import Path

from PIL import Image

HOME = Path(__file__).resolve().parents[2]
SEALED = HOME / "switch2homebrew-submit" / "icons" / "kaidrop.jpg"
PLAIN = HOME / "mizuiroame" / "assets" / "icons" / "kaidrop-256.png"
ASSETS = Path(__file__).resolve().parent.parent / "assets"
PACKAGE = ASSETS.parent / "kaidrop"
SMALL = (16, 24, 32)          # Without the seal.
LARGE = (48, 64, 128, 256)    # With it.
WINDOW = (64, 32, 16)


def main() -> int:
    for source in (SEALED, PLAIN):
        if not source.is_file():
            print(f"{source} not found: run python {HOME / 'switch2homebrew-submit' / 'tools' / 'make_app_icons.py'}")
            return 1
    sealed = Image.open(SEALED).convert("RGBA")
    plain = Image.open(PLAIN).convert("RGBA")
    sealed.convert("RGB").save(ASSETS / "icon.png", optimize=True)

    def at(n: int) -> Image.Image:
        return (plain if n in SMALL else sealed).resize((n, n), Image.LANCZOS)

    # Each size from its own picture (Pillow would shrink the first one for all of them).
    sizes = SMALL + LARGE
    at(256).save(ASSETS / "kaidrop.ico", sizes=[(n, n) for n in sizes], append_images=[at(n) for n in sizes[:-1]])
    lines = ['"""KaiDrop\'s icon for its window, as base64 PNGs (made by tools/make_icon.py)."""', "",
             "APP_ICONS = ("]
    for n in WINDOW:
        buf = io.BytesIO()
        plain.resize((n, n), Image.LANCZOS).convert("RGB").save(buf, "PNG", optimize=True)
        lines.append(f'    "{base64.b64encode(buf.getvalue()).decode()}",  # {n}x{n}')
    (PACKAGE / "appicon.py").write_text("\n".join(lines + [")", ""]), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
