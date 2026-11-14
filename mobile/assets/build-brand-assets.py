"""Build the app-identity bitmaps for the Expo app from the brand kit in design/.

Reads design/*.svg and design/png/*.png, writes ONLY into mobile/assets/images/ and
mobile/public/. It never writes into design/.

    uv run --no-project --with cairosvg --with pillow python mobile/assets/build-brand-assets.py

Why not a plain copy of design/png/:
- Android adaptive foreground + monochrome: the kit's mark reaches a radius of 324 px on the
  1024 canvas; Android only guarantees the inner 66/108 circle (radius 313 px). They are
  re-rendered at 94 % so the whole mark (sparkle and tail included) is inside the safe zone.
- Splash: the kit's bitmap is 400 px. expo-splash-screen scales it to imageWidth x4 on
  xxxhdpi (640 px at imageWidth 160), so it is re-rendered at 1024 px to stay sharp.
- Web/PWA icons (192, 512, apple-touch 180) are rendered from the full-bleed icon.svg.
"""
from __future__ import annotations

import io
import math
import pathlib
import shutil

import cairosvg
from PIL import Image

ASSETS = pathlib.Path(__file__).resolve().parent
MOBILE = ASSETS.parent
DESIGN = MOBILE.parent / "design"
IMAGES = ASSETS / "images"
PUBLIC = MOBILE / "public"

ADAPTIVE_SCALE = 0.94
SAFE_RADIUS = 1024 * 66 / 108 / 2  # Android adaptive-icon safe circle on a 1024 canvas


def render(svg: str, size: int) -> Image.Image:
    data = cairosvg.svg2png(url=str(DESIGN / svg), output_width=size, output_height=size)
    return Image.open(io.BytesIO(data)).convert("RGBA")


def opaque(im: Image.Image) -> Image.Image:
    """Flatten to RGB: iOS and apple-touch icons must not carry an alpha channel."""
    lo, _hi = im.getchannel("A").getextrema()
    assert lo == 255, "expected a full-bleed opaque icon"
    return im.convert("RGB")


def scaled_on_canvas(svg: str, scale: float, canvas: int = 1024) -> Image.Image:
    inner = round(canvas * scale / 2) * 2
    out = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    off = (canvas - inner) // 2
    out.paste(render(svg, inner), (off, off))
    return out


def content_radius(im: Image.Image) -> float:
    alpha = im.getchannel("A").load()
    c = (im.width - 1) / 2
    return max(
        (math.hypot(x - c, y - c) for y in range(im.height) for x in range(im.width) if alpha[x, y] > 8),
        default=0.0,
    )


def main() -> None:
    IMAGES.mkdir(parents=True, exist_ok=True)
    PUBLIC.mkdir(parents=True, exist_ok=True)

    # Straight from the kit (already the right size and format).
    for name in ("icon.png", "android-icon-background.png", "favicon.png"):
        shutil.copyfile(DESIGN / "png" / name, IMAGES / name)

    # Android adaptive layers, pulled inside the safe zone.
    for svg, name in (
        ("adaptive-foreground.svg", "android-icon-foreground.png"),
        ("adaptive-monochrome.svg", "android-icon-monochrome.png"),
    ):
        im = scaled_on_canvas(svg, ADAPTIVE_SCALE)
        r = content_radius(im)
        assert r <= SAFE_RADIUS, f"{name}: content radius {r:.1f} > safe {SAFE_RADIUS:.1f}"
        im.save(IMAGES / name, optimize=True)
        print(f"{name}: content radius {r:.1f} px (safe {SAFE_RADIUS:.1f})")

    # Splash mark, high resolution, transparent.
    render("splash.svg", 1024).save(IMAGES / "splash-icon.png", optimize=True)

    # Web / PWA icons, opaque full-bleed.
    for size, name in ((192, "icon-192.png"), (512, "icon-512.png"), (180, "apple-touch-icon.png")):
        opaque(render("icon.svg", size)).save(PUBLIC / name, optimize=True)


if __name__ == "__main__":
    main()
