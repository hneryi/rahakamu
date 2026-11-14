#!/usr/bin/env python3
"""Compose expression states by toggling layer display attrs, then render PNGs.

    uv run --with resvg-py --with pillow python design/characters/tools/render.py

Outputs into design/characters/renders/:
  sisu.png, aava.png (800 px wide, bg #07140F), duo.png,
  sisu-expressions.png, aava-expressions.png
  (--all) states/<name>-<state>.png for every STATES entry
The STATES table below is also the reference mapping for the app's Character
component (state -> which layer variants are visible).
"""
import io
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import resvg_py
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "renders"
BG = "#07140F"
NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", NS)

# state -> layer selection.
# tilt = extra head tilt in degrees on top of the built-in lean, in the persona's lean
# direction (+ = lean further toward the partner, - = straighten / lean back).
STATES = {
    "idle":      dict(mouth="smile",     brows="neutral",   eyelids=None,     pupils=(0, 0),    gesture=False, tilt=0),
    "listening": dict(mouth="calm",      brows="raised",    eyelids=None,     pupils=(0, -1.5), gesture=False, tilt=7),
    "talking":   dict(mouth="talk-a",    brows="neutral",   eyelids=None,     pupils=(0, 0),    gesture=False, tilt=0),
    "thinking":  dict(mouth="hmm",       brows="thinking",  eyelids=None,     pupils=(5, -5),   gesture=False, tilt=-5),
    "happy":     dict(mouth="grin",      brows="raised",    eyelids="happy",  pupils=(0, 0),    gesture=False, tilt=2),
    "concerned": dict(mouth="concerned", brows="concerned", eyelids=None,     pupils=(0, 1.5),  gesture=False, tilt=3),
    "celebrate": dict(mouth="grin",      brows="raised",    eyelids=None,     pupils=(0, 0),    gesture=True,  tilt=0),
    "blink":     dict(mouth="smile",     brows="neutral",   eyelids="closed", pupils=(0, 0),    gesture=False, tilt=0),
    "talk-o":    dict(mouth="talk-o",    brows="neutral",   eyelids=None,     pupils=(0, 0),    gesture=False, tilt=0),
}
# per-persona tweaks on top of STATES
OVERRIDES = {
    "aava": {"celebrate": dict(eyelids="happy")},   # soft closed-eye smile so the idea pose reads as joy
}
SHEET = ["idle", "talking", "thinking", "happy", "concerned", "celebrate"]
DOCK = ["idle", "listening", "talking", "talk-o", "thinking", "happy", "concerned", "celebrate", "blink"]
HEAD_LAYERS = ("hair-back", "ears", "head", "mouth", "eyes", "eyelids", "brows", "hair-front", "glasses")
PIVOT = "202 280"
# Avatar (head + collar) crop for sizes <= 110 px; the full bust works from ~160 px up.
AVATAR_VIEWBOX = {"sisu": "62 22 280 300", "aava": "58 4 280 300"}


def compose(svg_text: str, state: str, viewbox: str | None = None) -> str:
    root = ET.fromstring(svg_text)
    title = root.find(f"{{{NS}}}title")
    persona = (title.text or "").lower() if title is not None else ""
    s = {**STATES[state], **OVERRIDES.get(persona, {}).get(state, {})}
    by_id = {el.get("id"): el for el in root.iter() if el.get("id")}

    def show(eid, on):
        el = by_id.get(eid)
        if el is None:
            return
        if on:
            el.attrib.pop("display", None)
        else:
            el.set("display", "none")

    for eid in by_id:
        if eid.startswith("mouth-"):
            show(eid, eid == f"mouth-{s['mouth']}")
        elif eid.startswith("brows-"):
            show(eid, eid == f"brows-{s['brows']}")
        elif eid.startswith("eyelid-"):
            show(eid, s["eyelids"] is not None and eid.endswith(f"-{s['eyelids']}"))
    tilt = s.get("tilt", 0)
    if tilt:
        for lid in HEAD_LAYERS:
            el = by_id.get(lid)
            if el is None:
                continue
            base = el.get("transform", "")
            m = re.search(r"rotate\((-?[\d.]+)", base)
            sign = -1 if (m and float(m.group(1)) < 0) else 1
            el.set("transform", f"rotate({tilt * sign} {PIVOT}) {base}".strip())
    show("arms-gesture", s["gesture"])
    show("arm-right-rest", not s["gesture"])
    dx, dy = s["pupils"]
    for side in ("left", "right"):
        el = by_id.get(f"pupil-{side}")
        if el is not None:
            if dx or dy:
                el.set("transform", f"translate({dx} {dy})")
            else:
                el.attrib.pop("transform", None)
    if viewbox:
        x, y, w, h = viewbox.split()
        root.set("viewBox", viewbox)
        root.set("width", w)
        root.set("height", h)
    return ET.tostring(root, encoding="unicode")


def render(svg_text: str, width: int, bg=BG) -> Image.Image:
    png = resvg_py.svg_to_bytes(svg_string=svg_text, width=width, background=bg)
    return Image.open(io.BytesIO(bytes(png))).convert("RGB")


def font(size, bold=False):
    name = "Lato-Bold.ttf" if bold else "Lato-Regular.ttf"
    try:
        return ImageFont.truetype(f"/usr/share/fonts/truetype/lato/{name}", size)
    except OSError:
        return ImageFont.load_default()


def sheet(name: str, svg_text: str, cell_w=400):
    cols, rows = 3, 2
    cell_h = int(cell_w * 1.2)
    label_h = 44
    pad = 16
    W = cols * cell_w + (cols + 1) * pad
    H = rows * (cell_h + label_h) + (rows + 1) * pad + 60
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.text((pad, 18), f"{name} - expressions", fill="#F2F7F4", font=font(28, True))
    for i, st in enumerate(SHEET):
        c, r = i % cols, i // cols
        x = pad + c * (cell_w + pad)
        y = 60 + pad + r * (cell_h + label_h + pad)
        d.rounded_rectangle([x, y, x + cell_w, y + cell_h + label_h], 18, fill="#0E2219", outline="#1B3328")
        im = render(compose(svg_text, st), cell_w, bg="#0E2219")
        img.paste(im, (x, y))
        d.text((x + 16, y + cell_h + 8), st, fill="#9FB3A9", font=font(22))
    return img


def avatars(svgs):
    """Dock-size check: every state at 110 px and 64 px tall using the avatar crop."""
    sizes = (110, 64)
    pad, label_w = 14, 70
    cell = {h: int(h * 280 / 300) for h in sizes}
    W = label_w + len(DOCK) * (cell[110] + pad) + pad
    H = pad + 30 + 2 * (110 + 64 + 3 * pad) + 40
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    y = pad
    for i, st in enumerate(DOCK):
        d.text((label_w + i * (cell[110] + pad), y), st, fill="#9FB3A9", font=font(14))
    y += 26
    for n, t in svgs.items():
        d.text((pad, y + 40), n, fill="#F2F7F4", font=font(18, True))
        for h in sizes:
            for i, st in enumerate(DOCK):
                im = render(compose(t, st, AVATAR_VIEWBOX[n]), cell[h])
                img.paste(im, (label_w + i * (cell[110] + pad), y))
            y += h + pad
        y += pad
    return img


def main():
    OUT.mkdir(exist_ok=True)
    svgs = {n: (ROOT / f"{n}.svg").read_text() for n in ("sisu", "aava")}
    for n, t in svgs.items():
        render(compose(t, "idle"), 800).save(OUT / f"{n}.png")
        sheet(n.capitalize(), t).save(OUT / f"{n}-expressions.png")
    a = render(compose(svgs["sisu"], "idle"), 600)
    b = render(compose(svgs["aava"], "idle"), 600)
    duo = Image.new("RGB", (1240, 760), BG)
    duo.paste(a, (10, 20))
    duo.paste(b, (630, 20))
    duo.save(OUT / "duo.png")
    avatars(svgs).save(OUT / "avatars-small.png")
    # extra states for review (and app reference)
    if "--all" in sys.argv:
        (OUT / "states").mkdir(exist_ok=True)
        for n, t in svgs.items():
            for st in STATES:
                render(compose(t, st), 400).save(OUT / "states" / f"{n}-{st}.png")
    print("rendered into", OUT)


if __name__ == "__main__":
    main()
