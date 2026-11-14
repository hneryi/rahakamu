#!/usr/bin/env python3
"""Generate the layered master SVGs for the SPankkiBot coaches.

    python3 design/characters/tools/build.py

Writes design/characters/sisu.svg and design/characters/aava.svg.
All art is original. viewBox 0 0 400 480, transparent background.
Left/right in ids are the VIEWER's left/right.

Round 3 (art-direction pass 2):
- one shared head template (face_path) for both, varying jaw and chin only
- Sisu: short neat beard built as a variable-width band offset from the jaw line,
  chevron mustache joined to the chin patch, calm closed smile at rest, bigger irises,
  re-drawn swept hair (3 big clumps + 1 small), stand-up quarter-zip collar,
  rebuilt tablet arm (forearm + cuff + wrist + gripping hand)
- Aava: lower hairline with a swept fringe, rounder chin, shorter neck, lighter hair and
  cardigan, chart on the notebook, re-drawn notebook hand with a wrist
- rim lights: 2 px inner rim at ~65 %, faded at both ends with a gradient, no ear rims
- stronger 3/4: far ear scaled 0.8 and tucked, nose shifted further, glasses seated
  (temple arms under the hair, cheek shadow under the lenses)
"""
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PIVOT = (202, 280)            # neck pivot for head tilt / nod
HEAD_LAYERS = ("hair-back", "ears", "head", "mouth", "eyes", "eyelids", "brows", "hair-front", "glasses")


def f(v):
    return f"{v:.1f}".rstrip("0").rstrip(".")


# ---------------------------------------------------------------- helpers
def group(gid, body, hidden=False, extra=""):
    d = ' display="none"' if hidden else ""
    return f'<g id="{gid}"{d}{extra}>{body}\n  </g>'


def variants(prefix, items, default):
    return "\n  ".join(group(f"{prefix}-{n}", b, hidden=(n != default)) for n, b in items)


def rim(d, clip, pre, op=0.65, w=4.0):
    """Rim light: inner 2 px (stroke clipped to the silhouette), faded at both ends by a gradient."""
    return (f'<path d="{d}" fill="none" stroke="url(#{pre}-grad-rim)" stroke-width="{w}" stroke-linecap="round" '
            f'opacity="{op}" clip-path="url(#{clip})"/>')


def rim_grad(pre, color):
    return (f'<linearGradient id="{pre}-grad-rim" x1="0" y1="0" x2="0" y2="1">'
            f'<stop offset="0" stop-color="{color}" stop-opacity="0"/>'
            f'<stop offset="0.22" stop-color="{color}" stop-opacity="1"/>'
            f'<stop offset="0.72" stop-color="{color}" stop-opacity="1"/>'
            f'<stop offset="1" stop-color="{color}" stop-opacity="0"/></linearGradient>')


def svg_doc(name, defs, layers):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 480" width="400" height="480">
<title>{name}</title>
<!-- SPankkiBot coach "{name}". Original art. Layer ids: see design/characters/NOTES.md -->
<defs>{defs}</defs>
<g id="{name.lower()}">
  {layers}
</g>
</svg>
'''


def blush_grad(pre, color):
    return (f'<radialGradient id="{pre}-grad-blush">'
            f'<stop offset="0" stop-color="{color}" stop-opacity="0.5"/>'
            f'<stop offset="0.6" stop-color="{color}" stop-opacity="0.22"/>'
            f'<stop offset="1" stop-color="{color}" stop-opacity="0"/></radialGradient>')


def top_grad(pre, a, b):
    return (f'<linearGradient id="{pre}-grad-top" x1="0" y1="0" x2="0" y2="1">'
            f'<stop offset="0" stop-color="{a}"/><stop offset="1" stop-color="{b}"/></linearGradient>')


# ---------------------------------------------------------------- shared head template
def face_path(hw, top, jaw_hw, jaw_y, chin_y, chin_k, cx=202, temple_y=168):
    """One base head for both characters. Returns (d, segments) where segments are the
    cubic pieces (p0, p1, p2, p3) from the viewer-right temple round the chin to the
    viewer-left temple (used to build the beard band)."""
    L, R = cx - hw, cx + hw
    segs = [
        ((R, temple_y), (R, temple_y + 38), (cx + jaw_hw + 9, jaw_y - 22), (cx + jaw_hw, jaw_y)),
        ((cx + jaw_hw, jaw_y), (cx + jaw_hw - 11, chin_y - 9), (cx + chin_k, chin_y), (cx, chin_y)),
        ((cx, chin_y), (cx - chin_k, chin_y), (cx - jaw_hw + 11, chin_y - 9), (cx - jaw_hw, jaw_y)),
        ((cx - jaw_hw, jaw_y), (cx - jaw_hw - 9, jaw_y - 22), (L, temple_y + 38), (L, temple_y)),
    ]
    d = (f"M{f(L)} {temple_y} C{f(L)} {top + 30} {f(cx - hw * 0.56)} {top} {cx} {top} "
         f"C{f(cx + hw * 0.56)} {top} {f(R)} {top + 30} {f(R)} {temple_y} ")
    for _, p1, p2, p3 in segs:
        d += f"C{f(p1[0])} {f(p1[1])} {f(p2[0])} {f(p2[1])} {f(p3[0])} {f(p3[1])} "
    return d + "Z", segs


def cubic_pts(seg, n=28):
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = seg
    out = []
    for i in range(n + 1):
        t = i / n
        u = 1 - t
        out.append((u ** 3 * x0 + 3 * u * u * t * x1 + 3 * u * t * t * x2 + t ** 3 * x3,
                    u ** 3 * y0 + 3 * u * u * t * y1 + 3 * u * t * t * y2 + t ** 3 * y3))
    return out


def contour(segs, y_min):
    pts = []
    for s in segs:
        for p in cubic_pts(s):
            if p[1] >= y_min and (not pts or math.dist(p, pts[-1]) > 0.5):
                pts.append(p)
    return pts


def band(pts, out_fn, in_fn, center=(202, 190), wobble=0.0):
    """Closed shape between the contour offset outward by out_fn(p) and inward by in_fn(p)."""
    outer, inner = [], []
    n = len(pts)
    for i, p in enumerate(pts):
        a, b = pts[max(i - 1, 0)], pts[min(i + 1, n - 1)]
        tx, ty = b[0] - a[0], b[1] - a[1]
        ln = math.hypot(tx, ty) or 1
        nx, ny = -ty / ln, tx / ln
        if (center[0] - p[0]) * nx + (center[1] - p[1]) * ny < 0:
            nx, ny = -nx, -ny
        o = out_fn(p)
        w = in_fn(p) + wobble * math.sin(i * 1.7)
        outer.append((p[0] - nx * o, p[1] - ny * o))
        inner.append((p[0] + nx * w, p[1] + ny * w))
    ring = outer + inner[::-1]
    return "M" + " L".join(f"{f(x)} {f(y)}" for x, y in ring) + " Z"


def smooth(e0, e1, x):
    t = max(0.0, min(1.0, (x - e0) / (e1 - e0)))
    return t * t * (3 - 2 * t)


def taper(seg, w0, w1, n=16):
    """Filled tapered stroke along one cubic (width w0 at the start, w1 at the end)."""
    pts = cubic_pts(seg, n)
    left, right = [], []
    for i, p in enumerate(pts):
        a, b = pts[max(i - 1, 0)], pts[min(i + 1, n)]
        tx, ty = b[0] - a[0], b[1] - a[1]
        ln = math.hypot(tx, ty) or 1
        nx, ny = -ty / ln, tx / ln
        h = (w0 + (w1 - w0) * i / n) / 2
        left.append((p[0] + nx * h, p[1] + ny * h))
        right.append((p[0] - nx * h, p[1] - ny * h))
    ring = left + right[::-1]
    return "M" + " L".join(f"{f(x)} {f(y)}" for x, y in ring) + " Z"


# ---------------------------------------------------------------- eyes
def almond(cx, cy, w, h, grow=0.0):
    hw = w / 2 + grow
    t = h * 0.66 + grow * 1.3
    b = h * 0.60 + grow * 1.3
    return (f"M{f(cx-hw)} {f(cy+2)} C{f(cx-hw+2)} {f(cy-t)} {f(cx+hw-2)} {f(cy-t-1)} {f(cx+hw)} {f(cy+1)} "
            f"C{f(cx+hw-3)} {f(cy+b)} {f(cx-hw+4)} {f(cy+b+1)} {f(cx-hw)} {f(cy+2)} Z")


def top_curve(cx, cy, w, h):
    hw = w / 2
    t = h * 0.66
    return f"M{f(cx-hw)} {f(cy+2)} C{f(cx-hw+2)} {f(cy-t)} {f(cx+hw-2)} {f(cy-t-1)} {f(cx+hw)} {f(cy+1)}"


def eye_defs(pre, side, cx, cy, w, h):
    return (f'<clipPath id="{pre}-clip-eye-{side}"><path d="{almond(cx, cy, w, h)}"/></clipPath>'
            f'<clipPath id="{pre}-clip-lid-{side}"><path d="{almond(cx, cy, w, h, 4)}"/></clipPath>')


def eye(pre, side, cx, cy, w, h, P, lashes):
    hw = w / 2
    ir = P["iris_r"]
    ix, iy = cx + 1, cy + 1.5
    outer = -1 if side == "left" else 1
    ox = cx + outer * hw
    flick = f"M{f(ox)} {f(cy+1.5)} Q{f(ox+outer*4)} {f(cy-1)} {f(ox+outer*7)} {f(cy-5)}"
    lash_extra = ""
    if lashes:
        lash_extra = (f'<path d="M{f(ox-outer*4)} {f(cy-8)} Q{f(ox+outer*1)} {f(cy-12)} {f(ox+outer*3)} {f(cy-14)}" '
                      f'fill="none" stroke="{P["lid"]}" stroke-width="2.2" stroke-linecap="round"/>')
    return f'''
    <g id="eye-{side}">
      <path id="eye-{side}-white" d="{almond(cx, cy, w, h)}" fill="#FFFDF8"/>
      <g clip-path="url(#{pre}-clip-eye-{side})">
        <g id="pupil-{side}">
          <circle cx="{f(ix)}" cy="{f(iy)}" r="{f(ir)}" fill="{P['iris_dk']}"/>
          <circle cx="{f(ix)}" cy="{f(iy+1.2)}" r="{f(ir-2)}" fill="{P['iris']}"/>
          <circle cx="{f(ix)}" cy="{f(iy+0.5)}" r="{f(ir*0.48)}" fill="#160E0B"/>
          <circle cx="{f(ix+ir*0.38)}" cy="{f(iy-ir*0.36)}" r="{f(ir*0.30)}" fill="#FFFFFF"/>
          <circle cx="{f(ix-ir*0.36)}" cy="{f(iy+ir*0.42)}" r="{f(ir*0.13)}" fill="#FFFFFF" opacity="0.85"/>
        </g>
        <path d="M{f(cx-hw-2)} {f(cy-h*0.2)} C{f(cx-hw/2)} {f(cy-h*0.48)} {f(cx+hw/2)} {f(cy-h*0.48)} {f(cx+hw+2)} {f(cy-h*0.2)} L{f(cx+hw+2)} {f(cy-h)} L{f(cx-hw-2)} {f(cy-h)} Z" fill="{P['skin_sh']}" opacity="0.35"/>
      </g>
      <path d="{top_curve(cx, cy, w, h)}" fill="none" stroke="{P['lid']}" stroke-width="{P['lid_w']}" stroke-linecap="round"/>
      <path d="{flick}" fill="none" stroke="{P['lid']}" stroke-width="{P['lid_w']*0.85:.1f}" stroke-linecap="round"/>
      {lash_extra}
    </g>'''


def eyelids(pre, side, cx, cy, w, h, P):
    hw = w / 2
    sk, lid, lw = P["skin"], P["lid"], P["lid_w"]
    cover = almond(cx, cy, w, h, 4)
    half = (f"M{f(cx-hw-6)} {f(cy+1)} C{f(cx-hw/2)} {f(cy-4)} {f(cx+hw/2)} {f(cy-4)} {f(cx+hw+6)} {f(cy)} "
            f"L{f(cx+hw+6)} {f(cy-h)} L{f(cx-hw-6)} {f(cy-h)} Z")
    half_line = f"M{f(cx-hw)} {f(cy+1)} C{f(cx-hw/2)} {f(cy-3.5)} {f(cx+hw/2)} {f(cy-3.5)} {f(cx+hw)} {f(cy)}"
    closed = f"M{f(cx-hw+1)} {f(cy+1)} Q{f(cx)} {f(cy+9)} {f(cx+hw-1)} {f(cy)}"
    happy = f"M{f(cx-hw+2)} {f(cy+6)} Q{f(cx)} {f(cy-12)} {f(cx+hw-2)} {f(cy+5)}"
    cheek = f"M{f(cx-hw+3)} {f(cy+17)} Q{f(cx)} {f(cy+10)} {f(cx+hw-3)} {f(cy+17)}"
    clip = f'clip-path="url(#{pre}-clip-lid-{side})"'
    return f'''
    <g id="eyelid-{side}-half" display="none">
      <path d="{half}" fill="{sk}" {clip}/>
      <path d="{half_line}" fill="none" stroke="{lid}" stroke-width="{lw}" stroke-linecap="round"/>
    </g>
    <g id="eyelid-{side}-closed" display="none">
      <path d="{cover}" fill="{sk}"/>
      <path d="{closed}" fill="none" stroke="{lid}" stroke-width="{lw}" stroke-linecap="round"/>
    </g>
    <g id="eyelid-{side}-happy" display="none">
      <path d="{cover}" fill="{sk}"/>
      <path d="{happy}" fill="none" stroke="{lid}" stroke-width="{lw+1.2:.1f}" stroke-linecap="round"/>
      <path d="{cheek}" fill="none" stroke="{P['skin_dk']}" stroke-width="2.2" stroke-linecap="round" opacity="0.7"/>
    </g>'''


def smile_lids(cx_l, cx_r, cy, wl, wr, color):
    """Soft lower-lid 'smile' arcs: what makes the eyes read kind instead of staring."""
    out = []
    for cx, w in ((cx_l, wl), (cx_r, wr)):
        hw = w / 2 - 4
        out.append(f'<path d="M{f(cx-hw)} {f(cy+16)} Q{f(cx)} {f(cy+21.5)} {f(cx+hw)} {f(cy+16)}" fill="none" '
                   f'stroke="{color}" stroke-width="2" stroke-linecap="round" opacity="0.5"/>')
    return "".join(out)


# ---------------------------------------------------------------- mouths
def mouth_open(pre, P, d, teeth_y, tcx, tcy, trx, try_, cid, line):
    return f'''
      <clipPath id="{pre}-clip-{cid}"><path d="{d}"/></clipPath>
      <path d="{d}" fill="{P['mouth']}"/>
      <g clip-path="url(#{pre}-clip-{cid})">
        <rect x="160" y="{teeth_y-24}" width="100" height="24" rx="4" fill="{P['teeth']}"/>
        <ellipse cx="{tcx}" cy="{tcy}" rx="{trx}" ry="{try_}" fill="{P['tongue']}"/>
      </g>
      <path d="{d}" fill="none" stroke="{line}" stroke-width="2.2" stroke-linejoin="round"/>'''


# ---------------------------------------------------------------- hands (local coords: origin = wrist top centre, up = -y)
HAND_SCALE = 1.3


def hand_thumbs_up(P):
    sk, sh, dk = P["skin"], P["skin_sh"], P["skin_dk"]
    sil = ("M-19 -5 C-24 -14 -24 -29 -18 -37 C-15 -41 -11 -42 -7 -41 "
           "C-9 -51 -7 -62 -2 -69 C2 -75 11 -73 11 -65 C11 -57 9 -49 10 -42 "
           "C17 -39 22 -31 22 -20 C22 -8 16 0 4 0 L-11 0 C-15 0 -18 -2 -19 -5 Z")
    back = "M10 -42 C17 -39 22 -31 22 -20 C22 -8 16 0 4 0 L1 0 C11 -6 15 -20 10 -42 Z"
    return f'''
      <path d="{sil}" fill="{sk}"/>
      <path d="{back}" fill="{sh}"/>
      <path d="M-22 -28 Q-15 -27 -9 -29 M-22 -18 Q-15 -17 -9 -19 M-20 -9 Q-14 -8 -9 -10" fill="none" stroke="{dk}" stroke-width="1.4" stroke-linecap="round"/>
      <path d="M-7 -41 C-3 -37 -4 -32 -9 -30" fill="none" stroke="{dk}" stroke-width="1.4" stroke-linecap="round"/>
      <path d="M1 -66 C1 -70 8 -70 8 -66 L8 -62 C6 -60 3 -60 1 -62 Z" fill="#FFFFFF" opacity="0.35"/>
      <path d="M-18 -36 C-16 -39 -12 -40 -9 -40" fill="none" stroke="#FFFFFF" stroke-width="1.4" stroke-linecap="round" opacity="0.4"/>'''


def hand_idea(P):
    sk, sh, dk = P["skin"], P["skin_sh"], P["skin_dk"]
    sil = ("M-20 -4 C-23 -14 -22 -28 -18 -38 C-18 -52 -17 -66 -14 -75 C-12 -82 -3 -82 -1 -75 "
           "C1 -66 1 -52 0 -41 C4 -45 10 -45 13 -41 C16 -43 21 -39 22 -33 "
           "C24 -22 22 -8 14 -2 C10 0 6 1 2 1 L-12 1 C-16 1 -19 -1 -20 -4 Z")
    side = "M13 -41 C16 -43 21 -39 22 -33 C24 -22 22 -8 14 -2 C10 0 6 1 2 1 C12 -6 16 -22 13 -41 Z"
    thumb = "M-19 -12 C-14 -24 2 -28 13 -26 C19 -25 20 -18 14 -17 C4 -16 -6 -12 -12 -5 Z"
    return f'''
      <path d="{sil}" fill="{sk}"/>
      <path d="{side}" fill="{sh}"/>
      <path d="M6 -42 L6 -33 M13 -40 L13 -31" fill="none" stroke="{dk}" stroke-width="1.4" stroke-linecap="round"/>
      <path d="{thumb}" fill="{sk}"/>
      <path d="M-12 -5 C-6 -12 4 -16 14 -17" fill="none" stroke="{dk}" stroke-width="1.4" stroke-linecap="round"/>
      <path d="M-17 -40 Q-9 -37 -1 -40" fill="none" stroke="{dk}" stroke-width="1.2" stroke-linecap="round" opacity="0.7"/>
      <path d="M-13 -72 C-12 -77 -9 -78 -6 -77" fill="none" stroke="#FFFFFF" stroke-width="1.4" stroke-linecap="round" opacity="0.45"/>'''


ARM_UP = ("M276 350 C300 352 312 356 318 362 L366 424 C376 440 368 462 350 464 "
          "C340 465 332 460 326 452 L282 392 C276 380 274 364 276 350 Z")
ARM_FORE = ("M330 446 C322 410 312 372 302 338 L338 330 C348 366 358 400 367 434 "
            "C372 452 360 466 346 466 C338 466 332 458 330 446 Z")


def gesture_arm(P, clip, pre, cuff_extra=""):
    """Two-segment raised arm: shoulder -> elbow out at (348,440) -> wrist (320,334). Pre-lift coords."""
    fore_sh = ("M338 330 C348 366 358 400 367 434 C372 452 360 466 346 466 "
               "C356 454 358 440 352 420 C346 396 336 362 326 332 Z")
    return f'''
    <path d="{ARM_UP}" fill="{P['top_sh']}"/>
    <path d="M296 378 Q306 382 312 392 M314 400 Q322 404 328 414" fill="none" stroke="{P['top_dk']}" stroke-width="2" stroke-linecap="round" opacity="0.4"/>
    {rim("M276 350 C300 352 312 356 318 362 L366 424 C376 440 368 462 350 464", clip + "-up", pre)}
    <path d="{ARM_FORE}" fill="{P['top']}"/>
    <path d="{fore_sh}" fill="{P['top_sh']}" opacity="0.6"/>
    <path d="M330 446 C322 410 312 372 302 338" fill="none" stroke="{P['top_hi']}" stroke-width="3" stroke-linecap="round" opacity="0.5"/>
    <path d="M318 392 Q328 396 336 390 M326 420 Q336 424 346 418" fill="none" stroke="{P['top_dk']}" stroke-width="2" stroke-linecap="round" opacity="0.35"/>
    {rim("M338 330 C348 366 358 400 367 434 C372 452 360 466 346 466", clip + "-fore", pre)}
    {cuff_extra}'''


def gesture_clips(pre):
    return (f'<clipPath id="{pre}-clip-arm-up"><path d="{ARM_UP}"/></clipPath>'
            f'<clipPath id="{pre}-clip-arm-fore"><path d="{ARM_FORE}"/></clipPath>')


def far_ear(body, ax, ay, dx):
    """3/4 view: the far ear is smaller and tucked behind the face edge."""
    return f'<g transform="translate({dx} 0) translate({ax} {ay}) scale(0.8) translate({-ax} {-ay})">{body}</g>'


# ================================================================ SISU
def sisu():
    P = dict(
        skin="#F2C3A0", skin_sh="#DE9F7E", skin_dk="#C4806A", blush="#F08A78",
        hair="#B8854F", hair_sh="#94663A", hair_hi="#D9AA6E", hair_dk="#6E4A2A",
        beard="#B08352", beard_sh="#8E6440",
        iris="#4F86A8", iris_dk="#2D5873", iris_r=12.2, lid="#2E1C12", lid_w=3.2,
        top="#F5A524", top_sh="#DC8C1F", top_dk="#B56A10", top_hi="#FFC765", top_low="#D98A1E",
        green="#00B26F", green_dk="#008A56", mint="#3DD9B4", rim="#FFD892",
        mouth="#4A1F1A", tongue="#E2766C", teeth="#FFFDF7", lip="#C9705F",
        frame="#2F3B36",
    )
    pre = "sisu"
    LIFT = 24
    TILT = 4                    # head leans toward viewer-right
    TX = 5                      # fake 3/4 turn: mouth / mustache shift toward viewer-right
    NX = 9                      # nose shifts a bit further
    MY = -4                     # mouth group lift
    EL, ER, EY, EH = 172, 240, 190, 24
    EWL, EWR = 31, 28.6         # far (viewer-right) eye narrower

    FACE, FSEGS = face_path(hw=78, top=84, jaw_hw=58, jaw_y=252, chin_y=280, chin_k=20)
    HAIR_FRONT = ("M126 186 C118 160 116 130 126 110 C132 94 140 84 150 78 "
                  "C156 64 170 56 186 58 C196 48 210 44 222 48 C230 42 240 40 248 43 "
                  "C251 39 254 37 258 37 C258 43 261 48 266 52 "
                  "C282 62 294 84 292 108 C298 138 292 166 280 186 "
                  "C277 168 271 150 262 132 "
                  "C258 142 250 150 238 148 C236 140 237 131 235 123 "
                  "C227 138 215 150 200 151 C201 141 202 131 198 123 "
                  "C190 132 180 138 168 139 C170 133 170 128 166 124 "
                  "C161 129 155 133 148 134 C142 140 136 156 132 170 C130 177 128 182 126 186 Z")
    TORSO = ("M28 520 C28 432 40 392 78 372 C100 360 134 350 154 342 C162 338 168 334 172 330 "
             "L232 330 C236 334 242 338 250 342 C270 350 304 360 326 372 C364 392 376 432 376 520 Z")

    defs = (f'<clipPath id="{pre}-clip-face"><path d="{FACE}"/></clipPath>'
            f'<clipPath id="{pre}-clip-hair"><path d="{HAIR_FRONT}"/></clipPath>'
            f'<clipPath id="{pre}-clip-torso"><path d="{TORSO}"/></clipPath>'
            + gesture_clips(pre)
            + blush_grad(pre, P["blush"]) + rim_grad(pre, P["rim"])
            + top_grad(pre, P["top"], P["top_low"])
            + eye_defs(pre, "left", EL, EY, EWL, EH) + eye_defs(pre, "right", ER, EY, EWR, EH))

    hair_back = f'''
    <path d="M128 196 C116 124 150 66 204 66 C258 66 290 124 278 196 Z" fill="{P['hair_sh']}"/>'''

    # ---- body (pre-lift coords; whole group translated up by LIFT)
    body = f'''
    <path d="M164 316 C176 302 228 302 240 316 L240 330 L164 330 Z" fill="{P['top_dk']}"/>
    <path id="neck" d="M178 262 C178 290 176 312 172 334 L232 334 C228 312 226 290 226 262 Z" fill="{P['skin']}"/>
    <path d="M172 268 L232 268 L232 314 C216 328 190 328 172 312 Z" fill="{P['skin_sh']}"/>
    <path id="torso" d="{TORSO}" fill="url(#{pre}-grad-top)"/>
    <path d="M250 342 C270 350 304 360 326 372 C364 392 376 432 376 520 L262 520 C266 450 262 390 250 342 Z" fill="{P['top_sh']}" opacity="0.35"/>
    <path d="M150 350 C172 366 232 366 254 350 L252 368 C230 380 174 380 152 368 Z" fill="{P['top_sh']}" opacity="0.4"/>
    <path d="M190 336 L214 336 L202 362 Z" fill="#F4F1EA"/>
    <path d="M204 336 L214 336 L202 362 Z" fill="#E2DED4"/>
    <path d="M192 336 Q202 344 212 336" fill="none" stroke="#D8D2C6" stroke-width="2.2" stroke-linecap="round"/>
    <g id="collar">
      <path d="M164 314 C170 316 180 320 189 322 C192 336 196 350 202 364 C190 356 174 348 158 342 C156 332 158 322 164 314 Z" fill="{P['top']}"/>
      <path d="M240 314 C234 316 224 320 215 322 C212 336 208 350 202 364 C214 356 230 348 246 342 C248 332 246 322 240 314 Z" fill="{P['top_sh']}"/>
      <path d="M161 327 C170 331 180 335 191 337 M243 327 C234 331 224 335 213 337" fill="none" stroke="{P['top_dk']}" stroke-width="1.6" stroke-linecap="round" opacity="0.6"/>
      <path d="M164 314 C170 316 180 320 189 322" fill="none" stroke="{P['top_hi']}" stroke-width="2.4" stroke-linecap="round" opacity="0.85"/>
      <path d="M189 322 C192 336 196 350 202 364 L215 322" fill="none" stroke="{P['top_dk']}" stroke-width="2" stroke-linejoin="round"/>
    </g>
    <path d="M202 364 L202 520" stroke="{P['top_dk']}" stroke-width="2.2"/>
    <g id="zip-pull"><rect x="198" y="362" width="8" height="15" rx="3" fill="{P['green']}"/><rect x="200" y="366" width="4" height="7" rx="1.5" fill="{P['green_dk']}"/></g>
    <path d="M216 382 C236 386 258 386 284 380" fill="none" stroke="{P['top_dk']}" stroke-width="1.6" stroke-linecap="round" opacity="0.45"/>
    <g id="chest-tab"><rect x="252" y="381" width="10" height="4" rx="2" fill="{P['green']}"/></g>'''

    sleeve_l = ("M124 350 C100 358 86 364 78 372 C40 392 28 432 28 520 L98 520 "
                "C98 470 100 430 104 406 C108 384 114 366 124 350 Z")
    sleeve_r = ("M280 350 C304 358 318 364 326 372 C364 392 376 432 376 520 L306 520 "
                "C306 470 304 430 300 406 C296 384 290 366 280 350 Z")

    # viewer-left arm: upper arm down the side to an elbow just below the frame, forearm rising
    # diagonally to a ribbed cuff, short wrist (smartwatch) and a hand gripping the tablet's left edge.
    E, CC = (40, 534), (96, 436)                 # elbow (out of frame), cuff centre
    ln = math.dist(E, CC)
    dx, dy = (CC[0] - E[0]) / ln, (CC[1] - E[1]) / ln     # along the forearm (toward the hand)
    ax, ay = -dy, dx                                       # across (toward lower right)
    ang = math.degrees(math.atan2(ay, ax))

    def at(base, a, c):                                     # base + a*along + c*across
        return (base[0] + dx * a + ax * c, base[1] + dy * a + ay * c)

    def pt(p):
        return f"{f(p[0])} {f(p[1])}"

    el, er, cl, cr = at(E, 0, -20), at(E, 0, 20), at(CC, 0, -15.5), at(CC, 0, 15.5)
    forearm = (f"M{pt(el)} C{pt(at(E, 30, -22))} {pt(at(CC, -30, -18))} {pt(cl)} L{pt(cr)} "
               f"C{pt(at(CC, -30, 17))} {pt(at(E, 30, 21))} {pt(er)} Z")
    fore_sh = (f"M{pt(cr)} C{pt(at(CC, -30, 17))} {pt(at(E, 30, 21))} {pt(er)} L{pt(at(E, 0, 10))} "
               f"C{pt(at(E, 30, 11))} {pt(at(CC, -30, 8))} {pt(at(CC, 0, 7))} Z")
    fore_hi = f"M{pt(at(E, 6, -18))} C{pt(at(E, 34, -19))} {pt(at(CC, -30, -15))} {pt(at(CC, -6, -13))}"
    wrist = f"M{pt(at(CC, 4, -10.5))} L{pt(at(CC, 18, -10))} L{pt(at(CC, 18, 10))} L{pt(at(CC, 4, 10.5))} Z"
    wrist_sh = f"M{pt(at(CC, 4, 5))} L{pt(at(CC, 18, 5))} L{pt(at(CC, 18, 10))} L{pt(at(CC, 4, 10.5))} Z"
    W = at(CC, 11, 0)
    strap = f"M{pt(at(W, 0, -10))} L{pt(at(W, 0, 10))}"
    T_ROT = "rotate(-3 147 406)"
    tablet = f'''
    <g id="prop" transform="{T_ROT}">
      <rect x="110" y="380" width="74" height="52" rx="7" fill="#1A2220"/>
      <rect x="110" y="380" width="74" height="52" rx="7" fill="none" stroke="#56635E" stroke-width="1.6"/>
      <rect x="116" y="385" width="63" height="42" rx="3.5" fill="#0B2A1E"/>
      <path d="M123 421 L174 421" stroke="#1F4A38" stroke-width="1.4"/>
      <rect x="125" y="411" width="7" height="10" rx="1.5" fill="{P['green']}" opacity="0.75"/>
      <rect x="136" y="405" width="7" height="16" rx="1.5" fill="{P['green']}" opacity="0.85"/>
      <rect x="147" y="400" width="7" height="21" rx="1.5" fill="{P['green']}"/>
      <rect x="158" y="394" width="7" height="27" rx="1.5" fill="{P['mint']}"/>
      <path d="M126 404 L139 398 L150 393 L167 387" fill="none" stroke="{P['mint']}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
      <circle cx="167" cy="387" r="2.6" fill="#FFFFFF"/>
      <path d="M118 387 L132 387" stroke="#FFFFFF" stroke-width="2" stroke-linecap="round" opacity="0.25"/>
    </g>'''
    fingers = [(392, 9.5), (402, 10.5), (412.5, 10.5), (422, 9)]
    knuckles = "".join(
        f'<path d="M{f(93.5 + abs(i - 1.4))} {f(y)} L118 {f(y - 3)}" stroke="{P["skin"] if i < 3 else P["skin_sh"]}" stroke-width="{w}" stroke-linecap="round"/>'
        for i, (y, w) in enumerate(fingers))
    gaps = "".join(f'<path d="M{f(89.5 + abs(i - 1) * 1.2)} {f(y + 0.5)} L108 {f(y - 2.5)}" stroke="{P["skin_dk"]}" stroke-width="1.5" stroke-linecap="round"/>'
                   for i, y in enumerate((397, 407.2, 417.5)))
    arm_left_rest = f'''
    <path d="{sleeve_l}" fill="{P['top']}"/>
    <path d="M124 350 C114 366 108 384 104 406 C100 430 98 470 98 520 L86 520 C88 470 92 428 98 404 C104 382 112 364 124 350 Z" fill="{P['top_sh']}" opacity="0.55"/>
    <path d="M124 350 C114 366 108 384 104 406 C100 430 98 470 98 520" fill="none" stroke="{P['top_dk']}" stroke-width="2" stroke-linecap="round" opacity="0.5"/>
    <path d="M110 362 C98 366 88 372 80 382" fill="none" stroke="{P['top_hi']}" stroke-width="3" stroke-linecap="round" opacity="0.6"/>
    <path d="M44 410 C38 430 34 456 33 480" fill="none" stroke="{P['top_hi']}" stroke-width="4" stroke-linecap="round" opacity="0.35"/>
    <rect x="110" y="380" width="74" height="52" rx="7" fill="{P['top_dk']}" opacity="0.3" transform="translate(3 3) {T_ROT}"/>
    <path d="{forearm}" fill="{P['top_dk']}" opacity="0.3" transform="translate(4 3)"/>
    <path d="{forearm}" fill="{P['top']}"/>
    <path d="{fore_sh}" fill="{P['top_sh']}"/>
    <path d="{fore_hi}" fill="none" stroke="{P['top_hi']}" stroke-width="3" stroke-linecap="round" opacity="0.6"/>
    <path d="M{pt(at(E, 40, -12))} Q{pt(at(E, 44, 0))} {pt(at(E, 40, 12))}" fill="none" stroke="{P['top_dk']}" stroke-width="1.8" stroke-linecap="round" opacity="0.35"/>
    <path d="{wrist}" fill="{P['skin']}"/>
    <path d="{wrist_sh}" fill="{P['skin_sh']}"/>
    <g transform="rotate({f(ang)} {pt(CC)})">
      <rect x="{f(CC[0]-18)}" y="{f(CC[1]-6.5)}" width="36" height="13" rx="6.5" fill="{P['top_sh']}"/>
      <path d="{' '.join(f'M{f(CC[0]+k)} {f(CC[1]-5.5)} L{f(CC[0]+k)} {f(CC[1]+5.5)}' for k in (-12, -6, 0, 6, 12))}" stroke="{P['top_dk']}" stroke-width="1.4" stroke-linecap="round" opacity="0.5"/>
    </g>
    <g id="smartwatch">
      <path d="{strap}" stroke="#1D2422" stroke-width="8" stroke-linecap="round"/>
      <g transform="rotate({f(ang)} {pt(W)})">
        <rect x="{f(W[0]-8.5)}" y="{f(W[1]-7.5)}" width="17" height="15" rx="5" fill="#111715"/>
        <rect x="{f(W[0]-6)}" y="{f(W[1]-5)}" width="12" height="10" rx="3" fill="{P['green']}"/>
        <path d="M{f(W[0]-4)} {f(W[1]+1)} L{f(W[0]-2)} {f(W[1]-1.5)} L{f(W[0])} {f(W[1]+0.5)} L{f(W[0]+3.5)} {f(W[1]-3)}" fill="none" stroke="#E9FFF6" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/>
      </g>
    </g>
    <g id="hand-tablet-back">
      <path d="M98 426 C95 416 95 400 99 390 C102 385 107 383 112 384 L114 430 C108 433 101 432 98 426 Z" fill="{P['skin']}"/>
      <path d="M98 426 C101 432 108 433 114 430 L114 424 C108 426 102 425 99 420 Z" fill="{P['skin_sh']}"/>
      {knuckles}
      {gaps}
      <path d="M90 391.5 Q91 388 94 387.5 M89 401.5 Q90 398 93 397.5 M89 412 Q90 408.5 93 408" fill="none" stroke="#FFFFFF" stroke-width="1.3" stroke-linecap="round" opacity="0.45"/>
    </g>
    {tablet}
    <g id="hand-tablet">
      <path d="M100 420 C102 411 108 403 114 399 C118 396 122 399 120 403 C118 408 113 415 108 422 Z" fill="{P['skin']}"/>
      <path d="M108 422 C113 415 118 408 120 403" fill="none" stroke="{P['skin_dk']}" stroke-width="1.4" stroke-linecap="round"/>
      <path d="M114 400 C116 398.5 118.5 398.5 119.5 400" fill="none" stroke="#FFFFFF" stroke-width="1.3" stroke-linecap="round" opacity="0.55"/>
    </g>'''
    arm_right_rest = f'''
    <path d="{sleeve_r}" fill="{P['top_sh']}"/>
    <path d="M280 350 C290 366 296 384 300 406 C304 430 306 470 306 520" fill="none" stroke="{P['top_dk']}" stroke-width="2.4" stroke-linecap="round" opacity="0.7"/>
    <path d="M342 430 Q332 434 324 444 M352 460 Q342 464 334 474" fill="none" stroke="{P['top_dk']}" stroke-width="2" stroke-linecap="round" opacity="0.4"/>
    {rim("M280 350 C304 358 318 364 326 372 C364 392 376 432 376 520", pre + "-clip-torso", pre)}'''

    cuff = f'''
    <path d="M306 338 L334 334 L336 310 L308 312 Z" fill="{P['skin']}"/>
    <path d="M327 335 L334 334 L336 310 L329 311 Z" fill="{P['skin_sh']}"/>
    <rect x="296" y="326" width="48" height="17" rx="8" fill="{P['top_sh']}" transform="rotate(-8 320 334)"/>
    <path d="M305 329 L306 340 M313 328 L314 339 M321 327 L322 338 M329 326 L330 337 M337 325 L338 336" stroke="{P['top_dk']}" stroke-width="1.4" stroke-linecap="round" opacity="0.5" transform="rotate(-8 320 334)"/>
    <g id="hand-thumbs-up" transform="translate(320 320) rotate(-8) scale({HAND_SCALE})">{hand_thumbs_up(P)}
    </g>'''
    arm_right_gesture = (f'<path d="{sleeve_r}" fill="{P["top_sh"]}"/>'
                         + rim("M280 350 C304 358 318 364 326 372", pre + "-clip-torso", pre)
                         + gesture_arm(P, pre + "-clip-arm", pre, cuff))

    ear_r = f'''<path d="M274 176 C288 168 298 180 296 196 C294 214 284 224 270 220 Z" fill="{P['skin_sh']}"/>
    <path d="M280 186 C287 186 289 195 287 203 C285 210 280 212 275 209" fill="none" stroke="{P['skin_dk']}" stroke-width="2.6" stroke-linecap="round"/>'''
    ears = f'''
    <path d="M130 176 C116 168 106 180 108 196 C110 214 120 224 134 220 Z" fill="{P['skin']}"/>
    <path d="M124 186 C117 186 115 195 117 203 C119 210 124 212 129 209" fill="none" stroke="{P['skin_dk']}" stroke-width="2.6" stroke-linecap="round"/>
    {far_ear(ear_r, 276, 198, -6)}'''

    # ---- beard: variable-width band offset from the jaw line
    jaw = contour(FSEGS, 172)
    PCX = 207                                    # chin patch centre (under the shifted mouth)

    def chin(p):
        return math.exp(-((p[0] - PCX) / 23) ** 2) * smooth(262, 276, p[1])

    def b_in(p):
        return 8 + 4 * smooth(200, 236, p[1]) + 6 * chin(p)

    def b_out(p):
        return 2.5 * smooth(190, 220, p[1]) + 3.5 * chin(p)

    def sh_in(p):
        side = 4 if p[0] < 202 else 6           # light from the upper left; 4-6 px along the jaw edge
        return side * smooth(224, 248, p[1]) - b_out(p)

    beard_d = band(jaw, b_out, b_in)
    beard_sh_d = band([p for p in jaw if p[1] > 220], b_out, sh_in)
    head = f'''
    <path id="face" d="{FACE}" fill="{P['skin']}"/>
    <g clip-path="url(#{pre}-clip-face)">
      <path d="M248 92 C272 134 274 204 254 244 C242 266 224 280 202 290 L330 330 L330 80 Z" fill="{P['skin_sh']}"/>
      <path d="{HAIR_FRONT}" transform="translate(3 8)" fill="{P['skin_sh']}" opacity="0.85"/>
      <ellipse cx="150" cy="150" rx="12" ry="7" fill="#FFFFFF" opacity="0.16"/>
    </g>
    <ellipse id="blush-left" cx="156" cy="220" rx="18" ry="10" fill="url(#{pre}-grad-blush)"/>
    <ellipse id="blush-right" cx="254" cy="220" rx="14" ry="10" fill="url(#{pre}-grad-blush)"/>
    {smile_lids(EL, ER, EY, EWL, EWR, P['skin_dk'])}
    <g transform="translate({NX} 0)">
      <path id="nose" d="M206 199 C204 210 198 218 200 225 C203 230 211 230 215 226" fill="none" stroke="{P['skin_dk']}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
      <path d="M209 226 C214 222 214 214 209 206" fill="none" stroke="{P['skin_sh']}" stroke-width="3" stroke-linecap="round" opacity="0.7"/>
    </g>
    <g id="beard">
      <path d="{beard_d}" fill="{P['beard']}"/>
      <path d="{beard_sh_d}" fill="{P['beard_sh']}"/>
      <path d="M150 252 Q156 260 164 266 M154 246 Q159 252 165 257" fill="none" stroke="{P['hair_hi']}" stroke-width="1.6" stroke-linecap="round" opacity="0.6"/>
      <g id="mustache" transform="translate({TX} {MY})">
        <path d="M184 242 C190 236 200 233 206 236 C212 233 222 236 228 242 C221 240 214 240 206 243 C198 240 191 240 184 242 Z" fill="{P['beard']}"/>
        <path d="M206 243 C214 240 221 240 228 242 C222 241.5 214 242 206 244.5 Z" fill="{P['beard_sh']}" opacity="0.8"/>
        <path d="{taper(((185, 241), (180, 248), (180, 258), (186, 266)), 4.5, 2.6)}" fill="{P['beard']}"/>
        <path d="{taper(((227, 241), (232, 248), (232, 258), (226, 266)), 4.5, 2.6)}" fill="{P['beard']}"/>
      </g>
    </g>'''

    mouths = variants("mouth", [
        ("smile", f'''
      <path d="M186 249 Q207 267 229 248 Q207 258 186 249 Z" fill="{P['mouth']}" stroke="{P['mouth']}" stroke-width="2" stroke-linejoin="round"/>
      <path d="M199 263 Q207 266 215 262" fill="none" stroke="{P['lip']}" stroke-width="2.4" stroke-linecap="round" opacity="0.8"/>
      <path d="M183 245 Q183 249 186 250 M232 244 Q232 248 229 249" fill="none" stroke="{P['skin_dk']}" stroke-width="2" stroke-linecap="round"/>'''),
        ("calm", f'''
      <path d="M190 251 Q207 262 225 250" fill="none" stroke="{P['mouth']}" stroke-width="3.2" stroke-linecap="round"/>
      <path d="M200 260 Q207 263 214 259" fill="none" stroke="{P['lip']}" stroke-width="2.4" stroke-linecap="round" opacity="0.8"/>'''),
        ("talk-a", mouth_open(pre, P, "M186 249 Q207 255 228 248 Q225 275 207 277 Q189 275 186 249 Z", 257, 207, 277, 12, 6, "talk-a", P['mouth'])
            + f'<path d="M191 247 Q207 251 223 246" fill="none" stroke="{P["lip"]}" stroke-width="1.6" stroke-linecap="round" opacity="0.6"/>'),
        ("talk-o", mouth_open(pre, P, "M207 252 C212 252 213.5 257 213.5 260.5 C213.5 265.5 211 268.5 207 268.5 C203 268.5 200.5 265.5 200.5 260.5 C200.5 257 202 252 207 252 Z", 256, 207, 268.5, 5, 3, "talk-o", P['mouth'])),
        ("grin", mouth_open(pre, P, "M182 247 Q207 257 232 246 Q228 277 207 279 Q186 277 182 247 Z", 257, 207, 279, 14, 7, "grin", P['mouth'])
            + f'<path d="M178 243 Q178 248 182 250 M236 242 Q236 247 232 249" fill="none" stroke="{P["skin_dk"]}" stroke-width="2" stroke-linecap="round"/>'),
        ("concerned", f'''
      <path d="M195 258 Q206 254 219 257" fill="none" stroke="{P['mouth']}" stroke-width="3.2" stroke-linecap="round"/>
      <path d="M201 264 Q207 266 214 264" fill="none" stroke="{P['lip']}" stroke-width="2.2" stroke-linecap="round" opacity="0.7"/>'''),
        ("hmm", f'''
      <path d="M204 258 Q214 261 225 255" fill="none" stroke="{P['mouth']}" stroke-width="3.2" stroke-linecap="round"/>'''),
    ], "smile")

    eyes = eye(pre, "left", EL, EY, EWL, EH, P, False) + eye(pre, "right", ER, EY, EWR, EH, P, False)
    lids = eyelids(pre, "left", EL, EY, EWL, EH, P) + eyelids(pre, "right", ER, EY, EWR, EH, P)

    def brows_pair(l, r):
        st = f'fill="none" stroke="{P["hair_dk"]}" stroke-width="6" stroke-linecap="round"'
        return f'<path d="{l}" {st}/><path d="{r}" {st}/>'

    brows = variants("brows", [
        ("neutral", brows_pair("M152 160 Q168 151 189 156", "M222 156 Q240 151 255 159")),
        ("raised", brows_pair("M152 150 Q168 139 189 145", "M222 145 Q240 139 255 149")),
        ("concerned", brows_pair("M153 160 Q172 157 189 143", "M222 143 Q238 157 254 160")),
        ("thinking", brows_pair("M153 161 Q169 157 189 159", "M222 148 Q240 137 255 149")),
    ], "neutral")

    hair_front = f'''
    <path d="{HAIR_FRONT}" fill="{P['hair']}"/>
    <g clip-path="url(#{pre}-clip-hair)">
      <path d="M256 36 C284 58 298 98 292 140 L300 190 L310 30 Z" fill="{P['hair_sh']}"/>
      <path d="M262 132 C266 110 274 92 288 78 C282 96 276 112 274 140 Z" fill="{P['hair_sh']}"/>
      <path d="M235 123 C238 104 246 86 262 70 C252 88 246 104 245 128 Z" fill="{P['hair_sh']}"/>
      <path d="M198 123 C202 102 214 82 234 64 C220 86 212 104 209 130 Z" fill="{P['hair_sh']}"/>
      <path d="M166 124 C170 108 180 92 198 78 C186 96 179 110 176 130 Z" fill="{P['hair_sh']}"/>
      <path d="M238 148 C246 146 254 140 262 132 L262 140 C254 148 246 152 238 150 Z" fill="{P['hair_sh']}" opacity="0.7"/>
      <path d="M200 151 C214 150 226 138 235 123 L236 132 C228 146 214 154 200 153 Z" fill="{P['hair_sh']}" opacity="0.7"/>
      <path d="M146 84 C164 68 190 60 214 62 C196 68 176 76 160 96 Z" fill="{P['hair_hi']}" opacity="0.85"/>
      <path d="M268 72 C260 90 252 110 248 136 C256 112 264 94 273 76 Z" fill="{P['hair_hi']}" opacity="0.9"/>
      <path d="M242 60 C228 80 216 104 210 140 C220 108 230 86 247 63 Z" fill="{P['hair_hi']}" opacity="0.9"/>
      <path d="M196 72 C184 88 176 106 173 130 C181 108 189 92 201 76 Z" fill="{P['hair_hi']}" opacity="0.8"/>
      <path d="M134 120 C136 106 142 96 150 90 C146 102 142 112 140 126 Z" fill="{P['hair_hi']}" opacity="0.5"/>
    </g>
    {rim("M248 43 C251 39 254 37 258 37 C258 43 261 48 266 52 C282 62 294 84 292 108 C298 138 292 166 280 186", pre + "-clip-hair", pre, 0.7)}'''

    gl = P["frame"]
    LY0, LY1 = EY - 16, EY + 18

    def lens(cx, w):
        x0, x1 = cx - w / 2, cx + w / 2
        return (f'<path d="M{f(x0+7)} {LY1+2.5} Q{f(cx)} {LY1+5} {f(x1-7)} {LY1+2.5}" fill="none" stroke="{P["skin_dk"]}" stroke-width="3" stroke-linecap="round" opacity="0.22"/>'
                f'<rect x="{f(x0)}" y="{LY0}" width="{f(w)}" height="{LY1-LY0}" rx="11" fill="#FFFFFF" fill-opacity="0.08"/>'
                f'<rect x="{f(x0)}" y="{LY0}" width="{f(w)}" height="{LY1-LY0}" rx="11" fill="none" stroke="{gl}" stroke-width="1.8" opacity="0.8"/>'
                f'<path d="M{f(x0)} {LY0+12} C{f(x0)} {LY0+3} {f(x0+4)} {LY0} {f(x0+12)} {LY0} L{f(x1-12)} {LY0} C{f(x1-4)} {LY0} {f(x1)} {LY0+3} {f(x1)} {LY0+12}" '
                f'fill="none" stroke="{gl}" stroke-width="3.8" stroke-linecap="round"/>'
                f'<path d="M{f(cx+w*0.17)} {EY-10} L{f(cx+w*0.33)} {EY+1}" stroke="#FFFFFF" stroke-width="3" stroke-linecap="round" opacity="0.4"/>')

    WL, WR, LCR = 50, 44, ER - 2
    glasses = f'''
    {lens(EL, WL)}{lens(LCR, WR)}
    <path d="M{f(EL+WL/2)} {EY-9} Q{f((EL+WL/2+LCR-WR/2)/2)} {EY-14} {f(LCR-WR/2)} {EY-9}" fill="none" stroke="{gl}" stroke-width="3.2" stroke-linecap="round"/>
    <path d="M{f(LCR+WR/2-8)} {EY-15.5} Q{f(LCR+WR/2)} {EY-15} {f(LCR+WR/2)} {EY-6}" fill="none" stroke="{P['rim']}" stroke-width="1.2" stroke-linecap="round" opacity="0.8"/>'''
    # temple arms sit under the hair (end of the head layer), running to the top third of each ear
    temples = f'''
    <g id="glasses-temples" stroke="{gl}" stroke-width="3" stroke-linecap="round" fill="none">
      <path d="M{f(EL-WL/2)} {EY-8} L127 {EY-11}"/>
      <path d="M{f(LCR+WR/2)} {EY-8} L274 {EY-11}"/>
    </g>'''
    head += temples

    tilt = f' transform="rotate({TILT} {PIVOT[0]} {PIVOT[1]})"'
    tilt_m = f' transform="rotate({TILT} {PIVOT[0]} {PIVOT[1]}) translate({TX} {MY})"'
    lift = f' transform="translate(0 -{LIFT})"'

    layers = "\n  ".join([
        group("hair-back", hair_back, extra=tilt),
        group("body", body, extra=lift),
        group("arms-rest", group("arm-left-rest", arm_left_rest) + group("arm-right-rest", arm_right_rest), extra=lift),
        group("ears", ears, extra=tilt),
        group("head", head, extra=tilt),
        group("mouth", mouths, extra=tilt_m),
        group("eyes", eyes, extra=tilt),
        group("eyelids", lids, extra=tilt),
        group("brows", brows, extra=tilt),
        group("hair-front", hair_front, extra=tilt),
        group("glasses", glasses, extra=tilt),
        group("arms-gesture", group("arm-right-gesture", arm_right_gesture), hidden=True, extra=lift),
    ])
    return svg_doc("Sisu", defs, layers)


# ================================================================ AAVA
def aava():
    P = dict(
        skin="#DBA67E", skin_sh="#C08962", skin_dk="#9E6748", blush="#EA7C70",
        hair="#6A4030", hair_sh="#45291C", hair_hi="#8E5A40", hair_dk="#2A1610",
        iris="#7A5230", iris_dk="#4A2C18", iris_r=11, lid="#24140E", lid_w=3.4,
        top="#1F9C86", top_sh="#14705F", top_dk="#0C4D43", top_hi="#3DD9B4", top_low="#188270",
        blouse="#F5ECDC", blouse_sh="#DCCFB8",
        green="#00B26F", green_dk="#008A56", amber="#F5A524", rim="#3DD9B4",
        mouth="#5A2229", tongue="#E07A78", teeth="#FFFDF7", lip="#C0605F",
        frame="#6B3E22", frame_dk="#3B1F12", frame_hi="#A86A3A",
    )
    pre = "aava"
    LIFT = 36                   # shorter visible neck
    TILT = -4                   # head leans toward viewer-left (toward Sisu in the duo)
    TX = -4                     # 3/4 turn toward viewer-left
    NX = -8                     # nose shifts a bit further
    MY = -4                     # mouth sits a little higher
    EL, ER, EY, EH = 170, 234, 192, 26
    EWL, EWR = 30.4, 33         # far (viewer-left) eye narrower

    FACE, _ = face_path(hw=72, top=88, jaw_hw=53, jaw_y=250, chin_y=284, chin_k=24)
    HAIR_FRONT = ("M132 200 C121 156 127 112 155 91 C173 79 197 73 220 77 C252 83 277 107 283 145 "
                  "C286 168 283 188 277 206 C275 190 271 178 266 168 "
                  "C246 150 218 136 190 129 "
                  "C174 131 158 138 150 150 C143 161 140 174 138 188 C136 193 134 197 132 200 Z")
    BUN = "M182 60 C178 38 196 22 218 24 C242 26 254 46 250 66 C246 86 224 96 204 90 C190 86 184 74 182 60 Z"
    TORSO = ("M40 520 C40 432 52 394 88 374 C110 362 140 352 160 344 C168 340 174 336 178 332 "
             "L226 332 C230 336 236 340 244 344 C264 352 294 362 316 374 C352 394 364 432 364 520 Z")

    defs = (f'<clipPath id="{pre}-clip-face"><path d="{FACE}"/></clipPath>'
            f'<clipPath id="{pre}-clip-hair"><path d="{HAIR_FRONT}"/></clipPath>'
            f'<clipPath id="{pre}-clip-bun"><path d="{BUN}"/></clipPath>'
            f'<clipPath id="{pre}-clip-torso"><path d="{TORSO}"/></clipPath>'
            + gesture_clips(pre)
            + blush_grad(pre, P["blush"]) + rim_grad(pre, P["rim"])
            + top_grad(pre, P["top"], P["top_low"])
            + eye_defs(pre, "left", EL, EY, EWL, EH) + eye_defs(pre, "right", ER, EY, EWR, EH))

    hair_back = f'''
    <g id="pencil" transform="translate(166 26) rotate(27)">
      <rect x="14" y="0" width="74" height="11" fill="#F2C14E"/>
      <rect x="14" y="0" width="74" height="3.5" fill="#FFD978"/>
      <rect x="14" y="7.5" width="74" height="3.5" fill="#D9A23A"/>
      <path d="M14 0 L0 5.5 L14 11 Z" fill="#EBC9A0"/>
      <path d="M5 3.5 L0 5.5 L5 7.5 Z" fill="#3A3A3A"/>
      <rect x="88" y="-0.5" width="8" height="12" fill="#C7CDCA"/>
      <rect x="96" y="-0.5" width="10" height="12" rx="3.5" fill="#F08FA0"/>
    </g>
    <path id="bun" d="{BUN}" fill="{P['hair']}"/>
    <g clip-path="url(#{pre}-clip-bun)">
      <path d="M250 66 C246 86 224 96 204 90 C222 84 240 72 244 48 C250 54 252 60 250 66 Z" fill="{P['hair_sh']}"/>
      <path d="M190 62 C192 44 208 34 226 36 C214 40 204 50 202 66 Z" fill="{P['hair_sh']}" opacity="0.8"/>
      <path d="M206 80 C220 80 234 70 240 56 C238 72 226 86 210 88 Z" fill="{P['hair_sh']}" opacity="0.8"/>
      <path d="M194 40 C202 30 216 27 228 30 C216 33 206 38 199 47 Z" fill="{P['hair_hi']}"/>
    </g>
    {rim("M222 24 C240 27 252 42 251 60", pre + "-clip-bun", pre)}
    <path d="M126 204 C114 132 150 80 202 80 C256 80 292 132 280 204 C270 192 136 192 126 204 Z" fill="{P['hair_sh']}"/>'''

    body = f'''
    <path id="neck" d="M175 262 C175 290 173 310 169 334 L235 334 C231 310 229 290 229 262 Z" fill="{P['skin']}"/>
    <path d="M172 270 L232 270 L232 318 C216 332 190 332 172 316 Z" fill="{P['skin_sh']}"/>
    <path id="torso" d="{TORSO}" fill="url(#{pre}-grad-top)"/>
    <path d="M244 344 C264 352 294 362 316 374 C352 394 364 432 364 520 L262 520 C264 440 258 384 244 344 Z" fill="{P['top_sh']}" opacity="0.6"/>
    <path id="blouse" d="M166 336 C180 342 224 342 238 336 C232 386 218 450 210 520 L194 520 C186 450 172 386 166 336 Z" fill="{P['blouse']}"/>
    <path d="M228 338 L238 336 C232 386 218 450 210 520 L204 520 C212 440 222 384 228 338 Z" fill="{P['blouse_sh']}"/>
    <path d="M184 332 L202 356 L220 332 Z" fill="{P['skin']}"/>
    <path d="M188 332 L202 350 L216 332 Z" fill="{P['skin_sh']}" opacity="0.6"/>
    <path id="collar-left" d="M176 328 L202 356 L184 372 C176 360 170 346 170 334 Z" fill="#FFF8EC"/>
    <path id="collar-right" d="M228 328 L202 356 L220 372 C228 360 234 346 234 334 Z" fill="{P['blouse_sh']}"/>
    <path d="M194 354 Q202 361 210 354" fill="none" stroke="#D9B65A" stroke-width="1.4"/>
    <circle cx="202" cy="362" r="3.2" fill="{P['top_hi']}"/>
    <path d="M166 336 C172 386 186 450 194 520" fill="none" stroke="{P['top_dk']}" stroke-width="9"/>
    <path d="M238 336 C232 386 218 450 210 520" fill="none" stroke="{P['top_dk']}" stroke-width="9"/>
    <path d="M169 338 C175 386 189 450 197 520" fill="none" stroke="{P['top_hi']}" stroke-width="1.6" opacity="0.6"/>'''

    sleeve_l = ("M128 352 C106 360 94 366 88 374 C52 394 40 432 40 520 L104 520 "
                "C104 470 106 430 110 406 C114 384 120 366 128 352 Z")
    sleeve_r = ("M276 352 C298 360 310 366 316 374 C352 394 364 432 364 520 L300 520 "
                "C300 470 298 430 294 406 C290 384 284 366 276 352 Z")
    C = 56.5                    # donut circumference (r 9)
    notebook = f'''
    <g transform="rotate(-6 131 424)">
      <rect x="94" y="374" width="80" height="102" rx="5" fill="#E0D4BC"/>
      <rect x="96" y="372" width="80" height="102" rx="5" fill="#FFFFFF"/>
      <path d="M100 377 L172 377 M100 381 L172 381" stroke="#E6DDCB" stroke-width="1.2"/>
      <rect x="90" y="376" width="80" height="102" rx="5" fill="#F3EBDB"/>
      <rect x="90" y="376" width="14" height="102" rx="5" fill="{P['green']}"/>
      <rect x="100" y="376" width="4" height="102" fill="{P['green_dk']}"/>
      <rect x="154" y="376" width="6" height="102" fill="{P['green']}"/>
      <g id="notebook-chart">
        <circle cx="121" cy="402" r="9" fill="none" stroke="{P['green']}" stroke-width="6" stroke-dasharray="{C*0.5:.1f} {C}" transform="rotate(-90 121 402)"/>
        <circle cx="121" cy="402" r="9" fill="none" stroke="{P['top_hi']}" stroke-width="6" stroke-dasharray="{C*0.3:.1f} {C}" stroke-dashoffset="{-C*0.5:.1f}" transform="rotate(-90 121 402)"/>
        <circle cx="121" cy="402" r="9" fill="none" stroke="{P['amber']}" stroke-width="6" stroke-dasharray="{C*0.2:.1f} {C}" stroke-dashoffset="{-C*0.8:.1f}" transform="rotate(-90 121 402)"/>
        <path d="M134 410 L140 404 L145 406 L151 396" fill="none" stroke="{P['top']}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>
        <path d="M112 422 L148 422 M112 429 L138 429" stroke="#D6C9AE" stroke-width="2" stroke-linecap="round"/>
      </g>
      <path d="M104 378 L168 378" stroke="#FFFFFF" stroke-width="2" opacity="0.8"/>
      <path d="M134 476 L134 490 L138 486 L142 490 L142 476 Z" fill="{P['top_hi']}"/>
    </g>'''
    sk, ssh, sdk = P["skin"], P["skin_sh"], P["skin_dk"]
    # fingers wrap over the notebook's right edge, angled up-left, varied lengths
    fingers = [((174, 421), (152, 409)), ((176, 431), (149.5, 418)), ((177, 441), (153, 430)), ((178, 451), (160, 442))]
    finger_paths = "".join(
        f'<path d="M{a[0]} {a[1]} L{b[0]} {b[1]}" stroke="{sk}" stroke-width="{w}" stroke-linecap="round"/>'
        for (a, b), w in zip(fingers, (9.5, 10, 9.5, 8.5)))
    creases = (f'<path d="M172 426 L156 417 M174 436 L156 427 M175 446 L161 438" fill="none" stroke="{sdk}" '
               f'stroke-width="1.4" stroke-linecap="round" opacity="0.75"/>')
    nails = "".join(
        f'<path d="M{b[0]+1.5} {b[1]-2.6} Q{b[0]-1} {b[1]-1.2} {b[0]-1} {b[1]+1.6}" fill="none" stroke="#FFFFFF" stroke-width="1.3" stroke-linecap="round" opacity="0.5"/>'
        for _, b in fingers[:3])
    arm_left_rest = f'''
    <path d="{sleeve_l}" fill="{P['top']}"/>
    <path d="M128 352 C120 366 114 384 110 406 C106 430 104 470 104 520" fill="none" stroke="{P['top_sh']}" stroke-width="3" stroke-linecap="round"/>
    <path d="M66 396 C56 418 50 446 48 480" fill="none" stroke="{P['top_hi']}" stroke-width="5" stroke-linecap="round" opacity="0.35"/>
    <path d="M110 362 C98 366 88 372 80 382" fill="none" stroke="{P['top_hi']}" stroke-width="3" stroke-linecap="round" opacity="0.5"/>
    <g id="prop">{notebook}</g>
    <path d="M156 446 L160 474 C134 480 104 490 82 500 C60 510 40 500 42 482 C44 466 56 458 72 456 C100 452 130 448 156 446 Z" fill="{P['top']}"/>
    <path d="M160 474 C134 480 104 490 82 500 C68 506 56 502 48 494 C70 494 102 482 158 464 Z" fill="{P['top_sh']}"/>
    <path d="M156 446 C130 448 100 452 72 456 C56 458 44 466 42 482" fill="none" stroke="{P['top_hi']}" stroke-width="3" stroke-linecap="round" opacity="0.5"/>
    <path d="M90 462 Q96 470 98 482 M120 456 Q126 464 128 476" fill="none" stroke="{P['top_dk']}" stroke-width="2" stroke-linecap="round" opacity="0.4"/>
    <path d="M150 445 L163 443 L167 473 L154 476 Z" fill="{P['blouse']}"/>
    <path d="M159 443.5 L163 443 L167 473 L163 473.5 Z" fill="{P['blouse_sh']}"/>
    <g id="hand-notebook">
      <path d="M162 446 L176 444 L182 470 L166 474 Z" fill="{sk}"/>
      <path d="M176 444 L182 470 L177 471 L171 445 Z" fill="{ssh}"/>
      <path d="M168 468 C166 452 166 434 170 422 C173 414 182 412 187 418 C192 430 193 450 188 464 C184 474 172 476 168 468 Z" fill="{sk}"/>
      <path d="M187 418 C192 430 193 450 188 464 C185 471 179 474 173 474 C183 464 187 446 183 420 Z" fill="{ssh}"/>
      <path d="M181 424 C179 417 178 411 179 406 C180 402 185 402 186 406 C187 411 188 417 188 424 Z" fill="{sk}"/>
      <path d="M188 424 C188 417 187 411 186 406" fill="none" stroke="{sdk}" stroke-width="1.3" stroke-linecap="round" opacity="0.7"/>
      <path d="M180 407 Q182 403.5 185 405" fill="none" stroke="#FFFFFF" stroke-width="1.2" stroke-linecap="round" opacity="0.5"/>
      {finger_paths}
      {creases}
      {nails}
    </g>'''
    arm_right_rest = f'''
    <path d="{sleeve_r}" fill="{P['top_sh']}"/>
    <path d="M276 352 C286 366 290 384 294 406 C298 430 300 470 300 520" fill="none" stroke="{P['top_dk']}" stroke-width="3" stroke-linecap="round"/>
    <path d="M334 428 Q324 432 316 442 M344 458 Q334 462 326 472" fill="none" stroke="{P['top_dk']}" stroke-width="2" stroke-linecap="round" opacity="0.4"/>
    {rim("M276 352 C298 360 310 366 316 374 C352 394 364 432 364 520", pre + "-clip-torso", pre)}'''

    cuff = f'''
    <path d="M305 338 L333 334 L335 312 L307 314 Z" fill="{P['skin']}"/>
    <path d="M326 335 L333 334 L335 312 L328 313 Z" fill="{P['skin_sh']}"/>
    <path d="M298 330 L342 323 L344 340 L300 347 Z" fill="{P['blouse']}"/>
    <path d="M298 334 L342 327" stroke="{P['blouse_sh']}" stroke-width="2"/>
    <g id="hand-idea" transform="translate(320 320) rotate(-6) scale({HAND_SCALE})">{hand_idea(P)}
    </g>
    <g id="idea-sparkle" fill="{P['top_hi']}">
      <path d="M352 206 L355 216 L365 219 L355 222 L352 232 L349 222 L339 219 L349 216 Z"/>
      <circle cx="368" cy="198" r="3"/>
    </g>'''
    arm_right_gesture = (f'<path d="{sleeve_r}" fill="{P["top_sh"]}"/>'
                         + rim("M276 352 C298 360 310 366 316 374", pre + "-clip-torso", pre)
                         + gesture_arm(P, pre + "-clip-arm", pre, cuff))

    ear_l = f'''<path d="M136 178 C122 170 112 182 114 198 C116 214 125 222 138 218 Z" fill="{P['skin']}"/>
    <path d="M130 188 C123 188 121 196 123 203 C125 209 129 211 134 208" fill="none" stroke="{P['skin_dk']}" stroke-width="2.4" stroke-linecap="round"/>
    <circle cx="124" cy="220" r="3.4" fill="{P['top_hi']}"/>'''
    ears = f'''
    {far_ear(ear_l, 132, 200, 6)}
    <path d="M268 178 C282 170 292 182 290 198 C288 214 279 222 266 218 Z" fill="{P['skin_sh']}"/>
    <path d="M274 188 C281 188 283 196 281 203 C279 209 275 211 270 208" fill="none" stroke="{P['skin_dk']}" stroke-width="2.4" stroke-linecap="round"/>
    <circle cx="280" cy="220" r="3.4" fill="{P['top_hi']}"/>'''

    head = f'''
    <path id="face" d="{FACE}" fill="{P['skin']}"/>
    <g clip-path="url(#{pre}-clip-face)">
      <path d="M250 96 C272 136 274 202 254 244 C242 266 226 280 206 290 L330 330 L330 80 Z" fill="{P['skin_sh']}"/>
      <path d="{HAIR_FRONT}" transform="translate(3 8)" fill="{P['skin_sh']}" opacity="0.85"/>
      <path d="M128 184 C130 218 140 246 160 268 L167 264 C150 244 141 220 138 186 Z" fill="{P['skin_sh']}" opacity="0.45"/>
    </g>
    <ellipse id="blush-left" cx="158" cy="224" rx="14" ry="10" fill="url(#{pre}-grad-blush)"/>
    <ellipse id="blush-right" cx="248" cy="224" rx="17" ry="10" fill="url(#{pre}-grad-blush)"/>
    {smile_lids(EL, ER, EY, EWL, EWR, P['skin_dk'])}
    <path id="nose" transform="translate({NX} 0)" d="M208 208 C206 216 202 222 204 227 C207 230 212 230 215 227" fill="none" stroke="{P['skin_dk']}" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round"/>'''

    mouths = variants("mouth", [
        ("smile", f'''
      <path d="M186 246 Q206 266 226 245" fill="none" stroke="{P['mouth']}" stroke-width="3.2" stroke-linecap="round"/>
      <path d="M196 258 Q206 266 216 258 Q206 261 196 258 Z" fill="{P['lip']}" stroke="{P['lip']}" stroke-width="2" stroke-linejoin="round"/>
      <path d="M182 243 Q182 247 186 248 M230 242 Q230 246 226 247" fill="none" stroke="{P['skin_dk']}" stroke-width="2" stroke-linecap="round"/>'''),
        ("calm", f'''
      <path d="M192 249 Q206 259 220 248" fill="none" stroke="{P['mouth']}" stroke-width="3.2" stroke-linecap="round"/>
      <path d="M199 256 Q206 260 213 256" fill="none" stroke="{P['lip']}" stroke-width="2.2" stroke-linecap="round" opacity="0.8"/>'''),
        ("talk-a", mouth_open(pre, P, "M187 246 Q206 252 225 245 Q222 272 206 274 Q190 272 187 246 Z", 253, 207, 273, 11, 6, "talk-a", P['lip'])
            + f'<path d="M192 244 Q206 247 220 243" fill="none" stroke="{P["lip"]}" stroke-width="1.6" stroke-linecap="round" opacity="0.6"/>'),
        ("talk-o", mouth_open(pre, P, "M206 249 C211.5 249 213 254 213 258.5 C213 263.5 210.5 266.5 206 266.5 C201.5 266.5 199 263.5 199 258.5 C199 254 200.5 249 206 249 Z", 252, 206, 266.5, 5, 3, "talk-o", P['lip'])),
        ("grin", mouth_open(pre, P, "M185 244 Q206 252 227 243 Q224 275 206 277 Q188 275 185 244 Z", 253, 206, 276, 12, 7, "grin", P['lip'])
            + f'<path d="M181 241 Q181 245 185 246 M231 240 Q231 244 227 245" fill="none" stroke="{P["skin_dk"]}" stroke-width="2" stroke-linecap="round"/>'),
        ("concerned", f'''
      <path d="M195 255 Q206 251 218 254" fill="none" stroke="{P['mouth']}" stroke-width="3.2" stroke-linecap="round"/>
      <path d="M201 261 Q207 263 213 261" fill="none" stroke="{P['lip']}" stroke-width="2.2" stroke-linecap="round" opacity="0.7"/>'''),
        ("hmm", f'''
      <path d="M190 255 Q200 258 211 253" fill="none" stroke="{P['mouth']}" stroke-width="3.2" stroke-linecap="round"/>'''),
    ], "smile")

    eyes = eye(pre, "left", EL, EY, EWL, EH, P, True) + eye(pre, "right", ER, EY, EWR, EH, P, True)
    lids = eyelids(pre, "left", EL, EY, EWL, EH, P) + eyelids(pre, "right", ER, EY, EWR, EH, P)

    def brows_pair(l, r):
        st = f'fill="none" stroke="{P["hair_dk"]}" stroke-width="5" stroke-linecap="round"'
        return f'<path d="{l}" {st}/><path d="{r}" {st}/>'

    brows = variants("brows", [
        ("neutral", brows_pair("M154 162 Q169 153 187 157", "M216 157 Q236 151 254 162")),
        ("raised", brows_pair("M154 154 Q169 142 187 148", "M216 148 Q236 141 254 154")),
        ("concerned", brows_pair("M155 162 Q171 158 187 145", "M216 145 Q234 158 253 162")),
        ("thinking", brows_pair("M155 162 Q170 157 187 160", "M216 150 Q236 139 254 152")),
    ], "neutral")

    hair_front = f'''
    <path d="{HAIR_FRONT}" fill="{P['hair']}"/>
    <g clip-path="url(#{pre}-clip-hair)">
      <path d="M248 80 C276 100 290 140 284 190 L300 200 L300 60 Z" fill="{P['hair_sh']}"/>
      <path d="M190 129 C218 136 246 150 266 168 L268 163 C248 146 220 133 192 126 Z" fill="{P['hair_sh']}" opacity="0.8"/>
      <path d="{taper(((194, 110), (224, 114), (252, 132), (272, 160)), 1, 5)}" fill="{P['hair_sh']}" opacity="0.85"/>
      <path d="{taper(((206, 123), (230, 128), (250, 140), (264, 158)), 1, 4)}" fill="{P['hair_hi']}" opacity="0.8"/>
      <path d="{taper(((190, 129), (188, 116), (190, 102), (197, 88)), 4, 0.6)}" fill="{P['hair_sh']}"/>
      <path d="M184 128 C168 134 156 146 150 160 C150 146 160 132 178 124 Z" fill="{P['hair_sh']}" opacity="0.8"/>
      <path d="{taper(((160, 108), (176, 94), (192, 88), (210, 86)), 1, 9)}" fill="{P['hair_hi']}"/>
      <path d="{taper(((210, 86), (228, 84), (244, 88), (258, 98)), 9, 1)}" fill="{P['hair_hi']}"/>
      <path d="M140 160 C142 138 148 120 158 108 C152 126 148 142 146 164 Z" fill="{P['hair_hi']}" opacity="0.6"/>
    </g>
    {rim("M220 77 C252 83 277 107 283 145 C286 168 283 188 277 206", pre + "-clip-hair", pre, 0.7)}
    <path id="wisp-left" d="M132 182 C124 206 126 232 140 252 C134 230 134 206 140 188 Z" fill="{P['hair']}"/>
    <path id="wisp-right" d="M272 182 C280 206 278 232 264 252 C270 230 270 206 264 188 Z" fill="{P['hair']}"/>'''

    fr, fd, fh = P["frame"], P["frame_dk"], P["frame_hi"]

    def ring(side, cx, rx, ry):
        cy = EY + 1
        cid = f"{pre}-clip-rim-{side}"
        ann = (f"M{f(cx-rx-2.5)} {cy} a{f(rx+2.5)} {f(ry+2.5)} 0 1 0 {f(2*rx+5)} 0 a{f(rx+2.5)} {f(ry+2.5)} 0 1 0 {f(-2*rx-5)} 0 Z "
               f"M{f(cx-rx+2.5)} {cy} a{f(rx-2.5)} {f(ry-2.5)} 0 1 0 {f(2*rx-5)} 0 a{f(rx-2.5)} {f(ry-2.5)} 0 1 0 {f(-2*rx+5)} 0 Z")
        blot = [(-0.75, -0.6, 5, 2.6, -40), (0.2, -1.0, 4.5, 2.4, 0), (0.95, 0.15, 3, 4.6, 0),
                (0.35, 0.95, 5, 2.4, 20), (-0.95, 0.4, 3, 4.4, 0)]
        blots = "".join(
            f'<ellipse cx="{f(cx+dx*rx)}" cy="{f(cy+dy*ry)}" rx="{a}" ry="{b}" fill="{fh}" transform="rotate({r} {f(cx+dx*rx)} {f(cy+dy*ry)})"/>'
            for dx, dy, a, b, r in blot)
        return (f'<path d="M{f(cx-rx*0.7)} {cy+ry+2} Q{cx} {cy+ry+6} {f(cx+rx*0.7)} {cy+ry+2}" fill="none" stroke="{P["skin_dk"]}" stroke-width="3" stroke-linecap="round" opacity="0.22"/>'
                f'<clipPath id="{cid}"><path d="{ann}" clip-rule="evenodd" fill-rule="evenodd"/></clipPath>'
                f'<ellipse cx="{cx}" cy="{cy}" rx="{f(rx)}" ry="{ry}" fill="#FFFFFF" fill-opacity="0.08" stroke="{fr}" stroke-width="4.4"/>'
                f'<g clip-path="url(#{cid})">{blots}</g>'
                f'<ellipse cx="{cx}" cy="{cy}" rx="{f(rx-2.4)}" ry="{ry-2.4}" fill="none" stroke="{fd}" stroke-width="0.8"/>'
                f'<path d="M{f(cx+rx*0.33)} {EY-13} L{f(cx+rx*0.66)} {EY-4}" stroke="#FFFFFF" stroke-width="3" stroke-linecap="round" opacity="0.4"/>')

    RL, RR = 22, 24
    glasses = f'''
    {ring("left", EL, RL, 24)}{ring("right", ER, RR, 24)}
    <path d="M{EL+RL} {EY-4} Q{(EL+ER)//2} {EY-11} {ER-RR} {EY-4}" fill="none" stroke="{fr}" stroke-width="3.4" stroke-linecap="round"/>'''
    temples = f'''
    <g id="glasses-temples" stroke="{fr}" stroke-width="3.4" stroke-linecap="round" fill="none">
      <path d="M{EL-RL} {EY-3} L134 {EY-7}"/>
      <path d="M{ER+RR} {EY-3} L270 {EY-7}"/>
    </g>'''
    head += temples

    tilt = f' transform="rotate({TILT} {PIVOT[0]} {PIVOT[1]})"'
    tilt_m = f' transform="rotate({TILT} {PIVOT[0]} {PIVOT[1]}) translate({TX} {MY})"'
    lift = f' transform="translate(0 -{LIFT})"'

    layers = "\n  ".join([
        group("hair-back", hair_back, extra=tilt),
        group("body", body, extra=lift),
        group("arms-rest", group("arm-left-rest", arm_left_rest) + group("arm-right-rest", arm_right_rest), extra=lift),
        group("ears", ears, extra=tilt),
        group("head", head, extra=tilt),
        group("mouth", mouths, extra=tilt_m),
        group("eyes", eyes, extra=tilt),
        group("eyelids", lids, extra=tilt),
        group("brows", brows, extra=tilt),
        group("hair-front", hair_front, extra=tilt),
        group("glasses", glasses, extra=tilt),
        group("arms-gesture", group("arm-right-gesture", arm_right_gesture), hidden=True, extra=lift),
    ])
    return svg_doc("Aava", defs, layers)


if __name__ == "__main__":
    (ROOT / "sisu.svg").write_text(sisu())
    (ROOT / "aava.svg").write_text(aava())
    print("wrote", ROOT / "sisu.svg", ROOT / "aava.svg")
