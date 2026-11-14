"""SPankkiBot brand kit generator.

Generates every SVG in design/ and renders the PNGs in design/png/.
Run from anywhere:
    uv run --with cairosvg --with fonttools python design/build.py
All artwork is original. Text is converted to outlines (Lato, SIL OFL) so the SVGs
render identically everywhere without font dependencies.
"""
from __future__ import annotations

import pathlib

import cairosvg
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

HERE = pathlib.Path(__file__).resolve().parent
PNG = HERE / "png"
PNG.mkdir(exist_ok=True)
FONT_DIR = pathlib.Path("/usr/share/fonts/truetype/lato")

# ---------------------------------------------------------------- palette
BG = "#07140F"
BG2 = "#0B1F17"
GREEN = "#00B26F"
GREEN_HI = "#1ED68C"
GREEN_LO = "#008A56"
MINT = "#3DD9B4"
AMBER = "#F5A524"
AMBER_LO = "#D9860B"
TEXT = "#F2F7F4"
MUTED = "#9FB3A9"
FIXED = "#5B8DEF"
LEAK = "#FF6B8A"

# ---------------------------------------------------------------- mark geometry (512 grid)
BUBBLE = (
    "M168 72H344A112 112 0 0 1 456 184V280A112 112 0 0 1 344 392H222"
    "C204 392 188 398 174 409L118 455C106 465 89 455 92 440L104 384"
    "C76 364 56 326 56 280V184A112 112 0 0 1 168 72Z"
)
# three ascending bars = the three baskets growing into savings
BARS = [(150, 262, 50, 70), (222, 222, 50, 110), (294, 178, 50, 154)]  # x, y, w, h  (bottom = 332)
COIN = (370, 150, 38)  # cx, cy, r
SPARK = "M452 40l7 17 17 7-17 7-7 17-7-17-17-7 17-7z"  # four-point sparkle, outside the bubble


def rrect_path(x, y, w, h, r):
    return (
        f"M{x + r} {y}H{x + w - r}A{r} {r} 0 0 1 {x + w} {y + r}V{y + h - r}"
        f"A{r} {r} 0 0 1 {x + w - r} {y + h}H{x + r}A{r} {r} 0 0 1 {x} {y + h - r}"
        f"V{y + r}A{r} {r} 0 0 1 {x + r} {y}Z"
    )


def circle_path(cx, cy, r, ccw=False):
    s = 0 if ccw else 1
    return f"M{cx - r} {cy}A{r} {r} 0 1 {s} {cx + r} {cy}A{r} {r} 0 1 {s} {cx - r} {cy}Z"


def mark_defs(p: str) -> str:
    return f"""
    <linearGradient id="{p}bub" x1="0.15" y1="0" x2="0.85" y2="1">
      <stop offset="0" stop-color="{GREEN_HI}"/>
      <stop offset="0.55" stop-color="{GREEN}"/>
      <stop offset="1" stop-color="{GREEN_LO}"/>
    </linearGradient>
    <linearGradient id="{p}coin" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#FFC75A"/>
      <stop offset="1" stop-color="{AMBER_LO}"/>
    </linearGradient>
    <linearGradient id="{p}shine" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#FFFFFF" stop-opacity="0.28"/>
      <stop offset="1" stop-color="#FFFFFF" stop-opacity="0"/>
    </linearGradient>
    <clipPath id="{p}clip"><path d="{BUBBLE}"/></clipPath>"""


def mark_body(p: str) -> str:
    bars = []
    opac = [0.62, 0.82, 1.0]
    for (x, y, w, h), o in zip(BARS, opac):
        bars.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="14" fill="{TEXT}" fill-opacity="{o}"/>')
    cx, cy, r = COIN
    return f"""
    <path d="{BUBBLE}" fill="url(#{p}bub)"/>
    <g clip-path="url(#{p}clip)"><path d="M40 40H472V150C380 128 250 126 40 172Z" fill="url(#{p}shine)"/></g>
    {''.join(bars)}
    <circle cx="{cx}" cy="{cy}" r="{r}" fill="url(#{p}coin)"/>
    <circle cx="{cx}" cy="{cy}" r="{r - 9}" fill="none" stroke="#FFE3A6" stroke-opacity="0.75" stroke-width="5"/>
    <path d="M{cx - 11} {cy + 6}L{cx} {cy - 8}L{cx + 11} {cy + 6}" fill="none" stroke="#7A4A00" stroke-opacity="0.55" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/>
    <path d="{SPARK}" fill="{MINT}"/>
    """


def mark_group(p: str, tx=0, ty=0, scale=1.0) -> str:
    return f'<g transform="translate({tx} {ty}) scale({scale})">{mark_body(p)}</g>'


def mono_path() -> str:
    """Single-colour silhouette: bubble with bars + coin knocked out (even-odd)."""
    parts = [BUBBLE]
    parts += [rrect_path(x, y, w, h, 14) for x, y, w, h in BARS]
    cx, cy, r = COIN
    parts.append(circle_path(cx, cy, r))
    parts.append(circle_path(cx, cy, r - 15))  # solid coin centre -> reads as a coin ring
    return " ".join(parts)


def svg(w, h, body, defs="", extra=""):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}"{extra}>'
        f"<defs>{defs}</defs>{body}</svg>\n"
    )


# ---------------------------------------------------------------- text to outlines
_fonts: dict[str, TTFont] = {}


def text_path(text: str, font: str, size: float, x: float, y: float, tracking: float = 0.0):
    """Return (svg path d, advance width) for text with baseline at (x, y)."""
    f = _fonts.setdefault(font, TTFont(FONT_DIR / font))
    gs = f.getGlyphSet()
    cmap = f.getBestCmap()
    upm = f["head"].unitsPerEm
    s = size / upm
    pen = SVGPathPen(gs)
    cur = 0.0
    for ch in text:
        g = cmap[ord(ch)]
        tp = TransformPen(pen, (s, 0, 0, -s, x + cur, y))
        gs[g].draw(tp)
        cur += gs[g].width * s + tracking
    return pen.getCommands(), cur - tracking


def wordmark_paths(x, y, size):
    """'SPankki' light + 'Bot' green. Returns (body, width)."""
    d1, w1 = text_path("SPankki", "Lato-Black.ttf", size, x, y, tracking=-size * 0.01)
    d2, w2 = text_path("Bot", "Lato-Black.ttf", size, x + w1 - size * 0.005, y, tracking=-size * 0.01)
    return d1, d2, w1 - size * 0.005 + w2


# ---------------------------------------------------------------- characters (tiny, for social card)
def sisu_head(cx, cy, s):
    return f"""<g transform="translate({cx} {cy}) scale({s})">
      <circle cx="-34" cy="-34" r="18" fill="{AMBER_LO}"/><circle cx="34" cy="-34" r="18" fill="{AMBER_LO}"/>
      <circle cx="-34" cy="-34" r="9" fill="#FFD9A0"/><circle cx="34" cy="-34" r="9" fill="#FFD9A0"/>
      <circle cx="0" cy="0" r="50" fill="{AMBER}"/>
      <rect x="-50" y="-30" width="100" height="14" rx="7" fill="{GREEN}"/>
      <ellipse cx="0" cy="18" rx="24" ry="18" fill="#FFE1B3"/>
      <ellipse cx="0" cy="10" rx="8" ry="6" fill="#3A2410"/>
      <path d="M-8 24Q0 31 8 24" stroke="#3A2410" stroke-width="3.5" fill="none" stroke-linecap="round"/>
      <circle cx="-18" cy="-4" r="5.5" fill="#1C140C"/><circle cx="18" cy="-4" r="5.5" fill="#1C140C"/>
      <circle cx="-16" cy="-6" r="1.8" fill="#fff"/><circle cx="20" cy="-6" r="1.8" fill="#fff"/>
    </g>"""


def aava_head(cx, cy, s):
    return f"""<g transform="translate({cx} {cy}) scale({s})">
      <path d="M-46 -20L-40 -58L-16 -40Z" fill="#26A98A"/><path d="M46 -20L40 -58L16 -40Z" fill="#26A98A"/>
      <ellipse cx="0" cy="2" rx="50" ry="50" fill="{MINT}"/>
      <ellipse cx="0" cy="22" rx="30" ry="26" fill="#BFF5E6"/>
      <circle cx="-19" cy="-6" r="17" fill="#F2FFFB" stroke="#0B3A30" stroke-width="5"/>
      <circle cx="19" cy="-6" r="17" fill="#F2FFFB" stroke="#0B3A30" stroke-width="5"/>
      <path d="M-2 -6H2" stroke="#0B3A30" stroke-width="5"/>
      <circle cx="-19" cy="-5" r="6.5" fill="#0B1F17"/><circle cx="19" cy="-5" r="6.5" fill="#0B1F17"/>
      <circle cx="-17" cy="-7" r="2" fill="#fff"/><circle cx="21" cy="-7" r="2" fill="#fff"/>
      <path d="M-7 12L0 22L7 12Z" fill="{AMBER}"/>
    </g>"""


# ---------------------------------------------------------------- build
def write(name, content):
    (HERE / name).write_text(content)
    return HERE / name


def render(src: pathlib.Path, out: str, w: int, h: int | None = None):
    cairosvg.svg2png(url=str(src), write_to=str(PNG / out), output_width=w, output_height=h or w)


def bg_defs(p="bg"):
    return f"""
    <linearGradient id="{p}lin" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#0F3A29"/>
      <stop offset="0.55" stop-color="{BG2}"/>
      <stop offset="1" stop-color="{BG}"/>
    </linearGradient>
    <radialGradient id="{p}glow" cx="0.5" cy="0.46" r="0.5">
      <stop offset="0" stop-color="{GREEN}" stop-opacity="0.42"/>
      <stop offset="0.6" stop-color="{GREEN}" stop-opacity="0.08"/>
      <stop offset="1" stop-color="{GREEN}" stop-opacity="0"/>
    </radialGradient>"""


def main():
    # logo (mark) ----------------------------------------------------------
    logo = write("logo.svg", svg(512, 512, mark_body("m"), mark_defs("m")))

    # wordmark -------------------------------------------------------------
    size = 120
    d1, d2, tw = wordmark_paths(0, 0, size)
    mark_h = 150
    gap = 26
    W = int(mark_h + gap + tw + 14)
    H = 160
    base = 118
    d1, d2, _ = wordmark_paths(mark_h + gap, base, size)
    body = (
        mark_group("w", 0, 5, mark_h / 512)
        + f'<path d="{d1}" fill="{TEXT}"/><path d="{d2}" fill="{GREEN}"/>'
    )
    write("wordmark.svg", svg(W, H, body, mark_defs("w")))
    # light-background variant
    body_l = mark_group("w", 0, 5, mark_h / 512) + f'<path d="{d1}" fill="{BG}"/><path d="{d2}" fill="{GREEN_LO}"/>'
    write("wordmark-on-light.svg", svg(W, H, body_l, mark_defs("w")))

    # app icon 1024 (full bleed) -----------------------------------------
    ms = 640 / 512
    icon_body = f"""
      <rect width="1024" height="1024" fill="url(#bglin)"/>
      <rect width="1024" height="1024" fill="url(#bgglow)"/>
      <ellipse cx="512" cy="828" rx="250" ry="22" fill="#000" fill-opacity="0.2"/>
      {mark_group("i", 512 - 256 * ms, 512 - 262 * ms, ms)}
    """
    icon = write("icon.svg", svg(1024, 1024, icon_body, bg_defs() + mark_defs("i")))

    # android adaptive ----------------------------------------------------
    # 108dp canvas, 72dp visible, 66dp safe circle => keep mark inside ~600 px of 1024
    fs = 560 / 512
    fg = write(
        "adaptive-foreground.svg",
        svg(1024, 1024, mark_group("a", 512 - 256 * fs, 512 - 262 * fs, fs), mark_defs("a")),
    )
    bgsvg = write(
        "adaptive-background.svg",
        svg(1024, 1024, '<rect width="1024" height="1024" fill="url(#bglin)"/><rect width="1024" height="1024" fill="url(#bgglow)"/>', bg_defs()),
    )
    mono = write(
        "adaptive-monochrome.svg",
        svg(
            1024,
            1024,
            f'<g transform="translate({512 - 256 * fs} {512 - 262 * fs}) scale({fs})">'
            f'<path d="{mono_path()}" fill="#FFFFFF" fill-rule="evenodd"/>'
            f'<path d="{SPARK}" fill="#FFFFFF"/></g>',
        ),
    )

    # splash (transparent) -----------------------------------------------
    splash = write("splash.svg", svg(512, 512, mark_body("s"), mark_defs("s")))

    # favicon: simplified mark (no shine/sparkle/coin detail), fills the 64 box,
    # transparent so it works on light and dark browser chrome
    fsc = 64 / 420
    cx, cy, r = COIN
    fav_bars = "".join(
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="16" fill="{TEXT}"/>' for x, y, w, h in BARS
    )
    fav_body = (
        f'<g transform="translate({-46 * fsc} {-60 * fsc}) scale({fsc})">'
        f'<path d="{BUBBLE}" fill="url(#fbub)"/>{fav_bars}'
        f'<circle cx="{cx}" cy="{cy}" r="{r + 4}" fill="{AMBER}"/></g>'
    )
    fav = write("favicon.svg", svg(64, 64, fav_body, mark_defs("f")))

    # social card 1200x630 ------------------------------------------------
    wsize = 104
    wx = 330
    d1, d2, tw = wordmark_paths(wx, 300, wsize)
    tag, tgw = text_path("Talk with your money.", "Lato-Bold.ttf", 46, wx + 4, 372)
    sub, _ = text_path("Your personal economic trainer, powered by your own bank data.", "Lato-Regular.ttf", 24, wx + 4, 418)

    chips = []
    cx0 = wx + 4
    for label, col in (("Fixed", FIXED), ("Irregular", AMBER), ("Leaks", LEAK)):
        lp, lw = text_path(label, "Lato-Bold.ttf", 20, cx0 + 34, 486)
        cwid = lw + 52
        chips.append(
            f'<rect x="{cx0}" y="460" width="{cwid}" height="38" rx="19" fill="#FFFFFF" fill-opacity="0.06" stroke="#FFFFFF" stroke-opacity="0.1"/>'
            f'<circle cx="{cx0 + 19}" cy="479" r="7" fill="{col}"/><path d="{lp}" fill="{TEXT}"/>'
        )
        cx0 += cwid + 12
    sisu_lbl, sw = text_path("Sisu", "Lato-Bold.ttf", 22, 0, 0)
    aava_lbl, aw = text_path("Aava", "Lato-Bold.ttf", 22, 0, 0)
    s_lbl, _ = text_path("Sisu", "Lato-Bold.ttf", 22, 1000 - sw / 2, 590)
    a_lbl, _ = text_path("Aava", "Lato-Bold.ttf", 22, 1110 - aw / 2, 590)
    social_body = f"""
      <rect width="1200" height="630" fill="url(#soclin)"/>
      <circle cx="170" cy="300" r="300" fill="url(#socglow)"/>
      <circle cx="1120" cy="80" r="260" fill="url(#socglow2)"/>
      <path d="M0 630L1200 470V630Z" fill="#FFFFFF" fill-opacity="0.02"/>
      {mark_group("c", 60, 168, 240 / 512)}
      <path d="{d1}" fill="{TEXT}"/><path d="{d2}" fill="{GREEN}"/>
      <path d="{tag}" fill="{MINT}"/>
      <path d="{sub}" fill="{MUTED}"/>
      {''.join(chips)}
      <rect x="944" y="476" width="222" height="134" rx="28" fill="#FFFFFF" fill-opacity="0.05" stroke="#FFFFFF" stroke-opacity="0.08"/>
      {sisu_head(1000, 530, 0.62)}
      {aava_head(1110, 530, 0.62)}
      <path d="{s_lbl}" fill="{AMBER}"/><path d="{a_lbl}" fill="{MINT}"/>
    """
    soc_defs = (
        mark_defs("c")
        + f"""
    <linearGradient id="soclin" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#0D3324"/><stop offset="0.5" stop-color="{BG2}"/><stop offset="1" stop-color="{BG}"/>
    </linearGradient>
    <radialGradient id="socglow"><stop offset="0" stop-color="{GREEN}" stop-opacity="0.35"/><stop offset="1" stop-color="{GREEN}" stop-opacity="0"/></radialGradient>
    <radialGradient id="socglow2"><stop offset="0" stop-color="{MINT}" stop-opacity="0.14"/><stop offset="1" stop-color="{MINT}" stop-opacity="0"/></radialGradient>"""
    )
    social = write("social-card.svg", svg(1200, 630, social_body, soc_defs))

    # PNGs ---------------------------------------------------------------
    render(icon, "icon.png", 1024)
    render(fg, "android-icon-foreground.png", 1024)
    render(bgsvg, "android-icon-background.png", 1024)
    render(mono, "android-icon-monochrome.png", 1024)
    render(splash, "splash-icon.png", 400)
    render(fav, "favicon.png", 48)
    render(social, "social-card.png", 1200, 630)
    render(logo, "logo-512.png", 512)
    cairosvg.svg2png(url=str(HERE / "wordmark.svg"), write_to=str(PNG / "wordmark.png"), output_width=W * 2)
    print("built:", sorted(p.name for p in PNG.iterdir()))


if __name__ == "__main__":
    main()
