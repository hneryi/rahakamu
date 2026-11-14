# Rahakamu coaches: human cartoon characters

Sisu ("The Trainer") and Aava ("The Mentor"). These are original designs that replace the bear and owl from SPEC §6 (see §6b). The art is half-body busts drawn in a flat style with soft cel-shading. It is layered and every animatable part has an id.

```
design/characters/
  sisu.svg, aava.svg        layered master art, viewBox 0 0 400 480, transparent bg
  tools/build.py            generator: the single source of truth for the SVGs (edit here, not the .svg files)
  tools/render.py           state composer (toggles display attrs) and PNG renderer
  renders/                  sisu.png, aava.png (800 px), duo.png, *-expressions.png,
                            avatars-small.png (every state at 110 px and 64 px with the avatar crop)
  renders/states/           one 400 px PNG per state (with --all)
```

To rebuild:
```bash
python3 design/characters/tools/build.py
uv run --with resvg-py --with pillow python design/characters/tools/render.py --all
```

## Characters
| | Sisu | Aava |
|---|---|---|
| Role | The Trainer: energetic, encouraging | The Mentor: calm, wise, warm |
| Look | late 20s, tousled sandy-brown hair: 3 big S-curved clumps + 1 small one swept to viewer-left, uneven tips, one soft crown tuft, lighter strands; short neat beard (8 px sideburn → 12 px jaw band → ~24 px chin patch, cheeks bare), chevron mustache joined to the chin patch by thin tapered lines past the mouth corners; thin half-rim glasses, blue eyes, calm closed smile at rest | mid 30s, dark-brown loose bun with a pencil through it, side part at x≈190 with a soft fringe swept to viewer-right over the brow corner, crown sheen arc, round tortoiseshell glasses (solid ring + blotches), brown eyes, mint stud earrings |
| Outfit | amber quarter-zip with a stand-up collar (fold line, back band visible behind the neck), zip open to a small V of white tee, S-green zip pull, tiny 10×4 S-green tab on a chest seam (`#chest-tab`) | teal cardigan with a darker band, cream blouse with collar, tiny gold chain with a mint pendant |
| Prop | tablet (tilt −3°, tight 3 px contact shadow) with an S-green rising bar/line chart. Viewer-left arm: upper arm down the side, forearm rising diagonally from an elbow just below the frame, ribbed cuff, short wrist with the S-green `#smartwatch`; `#hand-tablet-back` (back of hand + 4 curled knuckles at the tablet's left edge) is under `#prop`, the thumb `#hand-tablet` lies on the front bezel | cream notebook with S-green spine, band and mint ribbon, plus a finance cue on the cover (`#notebook-chart`: green/mint/amber donut + rising line), hugged on the viewer-left forearm; `#hand-notebook`: blouse cuff → 10 px wrist → palm with one shadow tone, four fingers of different lengths angled up-left over the cover, thumb tip along the edge |
| Gesture | thumbs-up (`#arm-right-gesture` > `#hand-thumbs-up`) | raised index finger, thumb folded over the curled fingers, mint sparkle (`#hand-idea`, `#idea-sparkle`) |
| Rim light | warm `#FFD892` | mint `#3DD9B4` (same rule for both, see construction notes) |
| Head lean | `rotate(4 202 280)`, toward viewer-right; mouth/mustache shifted 5 px right, nose 9 px; viewer-right (far) eye/lens narrower; far ear 0.8× and tucked 6 px | `rotate(-4 202 280)`, toward viewer-left; mouth shifted 4 px left, nose 8 px; viewer-left (far) eye narrower; far ear 0.8× and tucked 6 px; thin far-cheek shadow |

## Layer stack and part ids (back to front)
**Left/right in ids are the VIEWER's left/right.**

| id | notes |
|---|---|
| `hair-back` | back hair silhouette. Aava: also `#bun` and `#pencil` |
| `body` | `#neck`, `#torso`, `#collar`, `#zip-pull`, `#chest-tab` (Sisu) / `#blouse`, `#collar-left`, `#collar-right` (Aava). Has `transform="translate(0 -24)"` (Sisu) or `translate(0 -36)` (Aava, short neck) |
| `arms-rest` | `#arm-left-rest` (holds the prop: sleeve, forearm, `#prop`, hands; Sisu also `#smartwatch`, `#hand-tablet-back`, `#hand-tablet`; Aava `#notebook-chart` inside `#prop`, `#hand-notebook`), `#arm-right-rest`. Hide `#arm-right-rest` when the gesture is shown. Same lift as `body` |
| `ears` | both ears (Aava: earrings). The far ear is wrapped in a `scale(0.8)` group tucked behind the face edge. No rim light on ears |
| `head` | `#face`, face shading (clipped to the face, including a cast shadow of the fringe), `#blush-left`, `#blush-right`, lower-lid smile arcs, `#nose`, and last `#glasses-temples` (temple arms, so they pass under `hair-front` to the top third of the ear). Sisu also has `#beard` > `#mustache` (the mustache group carries the same `translate(5 -4)` as the mouth) |
| `mouth` | variants `mouth-smile` (default, closed: Sisu a filled crescent, Aava a line + lip), `mouth-calm` (smaller closed smile), `mouth-talk-a`, `mouth-talk-o` (narrow O), `mouth-grin` (teeth; only happy and celebrate), `mouth-concerned`, `mouth-hmm` (pushed ~6 px toward one corner). Group transform also carries the 3/4 shift and lift (`… translate(TX MY)`, Sisu `5 -4`, Aava `-4 -4`) |
| `eyes` | `#eye-left`, `#eye-right`. Each has `#eye-*-white` plus `#pupil-*` (iris, pupil and highlights, clipped to the eye white). Translate `#pupil-*` by up to about ±4 px to set the look direction |
| `eyelids` | `eyelid-{left,right}-{half,closed,happy}`, all hidden by default. `closed` = blink (∪ line), `happy` = thick ^ arch plus a raised-cheek arc under each eye (so it never reads as a blink at 64 px), `half` = skeptical / sleepy (unused) |
| `brows` | variants `brows-neutral` (default), `brows-raised` (about 10 px above neutral), `brows-concerned`, `brows-thinking` (one brow up) |
| `hair-front` | fringe and tufts with clump shading. Aava: `#wisp-left`, `#wisp-right` (good for a gentle sway) |
| `glasses` | lens soft cheek shadow (skin-dark 22 %, 2–3 px below the lower rim), frames, lenses (8 % white), bridge (upper-middle of the lens), glare streaks. They stay in place while the eyes animate underneath |
| `arms-gesture` | hidden by default. Holds `#arm-right-gesture`: shoulder sleeve, upper arm (darker) out to the elbow at (348, 440), forearm up to the wrist at (320, 334), cuff, hand at `scale(1.3)` (Sisu: `#hand-thumbs-up`; Aava: `#hand-idea`, `#idea-sparkle`). Same lift as `body` |

Head layers (`hair-back`, `ears`, `head`, `mouth`, `eyes`, `eyelids`, `brows`, `hair-front`, `glasses`) each carry the persona lean `rotate(±4 202 280)`. To animate a nod or a state tilt, prepend another `rotate(a 202 280)` to all of them (that is what `render.py` does for `tilt`), or wrap them.

Variant families are sibling `<g>` elements. Show exactly one per family (`display="none"` on the others). Defs ids carry a prefix (`sisu-clip-*`, `aava-clip-*`), so both SVGs can be inlined on the same page. Open mouths keep their own clipPath inside the variant group.

## State to layer mapping (`tools/render.py` STATES + OVERRIDES)
`tilt` = extra degrees in the persona's lean direction (negative = straighten / lean back).

| state | mouth | brows | eyelids | pupils | tilt | gesture |
|---|---|---|---|---|---|---|
| idle | smile (closed) | neutral | none | 0,0 | 0 | no |
| listening | calm | raised | none | 0,-1.5 | +7 | no |
| talking | loop talk-a / talk-o / calm | neutral | none | 0,0 | 0 | no |
| thinking | hmm (off-centre) | thinking | none | +5,-5 (up and to the side) | -5 | no |
| happy | grin | raised | happy (^ + raised cheeks) | 0,0 | +2 | no |
| concerned | concerned (small soft closed mouth) | concerned (inner ends lifted) | none (eyes open and soft) | 0,+1.5 | +3 | no |
| celebrate | grin | raised | none (Aava override: happy, so the idea pose reads as joy) | 0,0 | 0 | yes |
| blink (overlay) | – | – | closed for about 120 ms every 3–5 s | – | – | – |

Teeth are reserved for happy and celebrate (and the talk frames); idle and listening are always closed-mouth so the dock never looks over-eager.

Suggested motion in react-native-svg + Reanimated: breathe by scaling the whole group on Y by about 1.5 % with the origin at the bottom; nod by rotating all head layers (including `hair-back`) together by ±2° around (202, 280); pop the gesture arm in by translating it up from y+60; spin or pulse `#idea-sparkle`.

## Palette
| | Sisu | Aava |
|---|---|---|
| skin / shadow / line | `#F2C3A0` / `#DE9F7E` / `#C4806A` (fair, pink) | `#DBA67E` / `#C08962` / `#9E6748` (warmer, slightly olive) |
| blush | `#F08A78` | `#EA7C70` |
| hair / shadow / highlight / brows | `#B8854F` / `#94663A` / `#D9AA6E` (also the light strands) / `#6E4A2A` | `#6A4030` / `#45291C` / `#8E5A40` (crown sheen arc) / `#2A1610` |
| beard / shadow (4–6 px inner band along the jaw edge only) | `#B08352` / `#8E6440` | – |
| iris / iris dark (radius) | `#4F86A8` / `#2D5873` (12.2) | `#7A5230` / `#4A2C18` (11) |
| lid line | `#2E1C12` 3.2 px | `#24140E` 3.4 px plus lashes |
| clothing | amber `#F5A524` → `#D98A1E` gradient, shadow `#DC8C1F` (body plane at 35 %), deep `#B56A10`, highlight `#FFC765` | teal `#1F9C86` → `#188270` gradient, shadow `#14705F`, deep `#0C4D43` (folds / bands only), mint `#3DD9B4`; blouse `#F5ECDC` / `#DCCFB8` |
| brand details | S-green `#00B26F` / `#008A56` (zip pull, chest tab, watch screen, tablet chart) | S-green notebook spine and band, donut chart (S-green / mint / amber), mint ribbon, earrings and pendant |
| frames | half-rim `#2F3B36` (3.8 px top bar, 1.8 px lower rim) plus a `#FFD892` outer-temple glint | solid `#6B3E22` 4.4 px ring, `#A86A3A` blotches clipped to the ring, `#3B1F12` 0.8 px inner line |
| mouth / tongue / teeth | `#4A1F1A` / `#E2766C` / `#FFFDF7` | `#5A2229` / `#E07A78` / `#FFFDF7`, lip `#C0605F` |

## Construction notes
- One head template: `face_path(hw, top, jaw_hw, jaw_y, chin_y, chin_k)` in `build.py` builds both faces; only jaw width and chin differ. Sisu `78/84/58/252/280/20` (broader jaw, chin at y 280), Aava `72/88/53/250/284/24` (narrower, rounder chin).
- Proportions: the eyes sit at y≈190; Aava's hairline is at y≈130 (fringe covers the brow corner), Sisu's fringe tips reach y 133–151. Heads are deliberately large, about 1:2.5 if you imagine the full figure.
- Sisu's beard is generated, not hand-drawn: `band()` offsets the sampled jaw contour outward (2.5 px, more at the chin) and inward by a width function (8 px sideburn → 12 px jaw band → +6 px gaussian chin patch centred under the shifted mouth). The beard shadow is the same band with a 4 px (lit side) / 6 px (shadow side) inner width. The mustache is a 44×7 chevron, joined to the chin patch by tapered 4.5 → 2.6 px lines (`taper()`).
- 3/4 view: each head leans 4° toward the partner (so they face each other in the duo); the mouth shifts 4–5 px and the nose 8–9 px the same way; the far eye/lens is narrower; the far ear is 0.8× and tucked behind the face edge.
- Light comes from the upper left. Every skin, hair and cloth area has one shadow tone on the right, plus a fringe cast shadow on the forehead (the hair path offset by (3, 8), clipped to the face), a neck shadow under the jaw and tight contact shadows under props.
- Rim lights, one rule for both: a 4 px stroke clipped to the silhouette (2 px visible), opacity 0.65–0.7, stroked with `#<pre>-grad-rim` (fades in over the first 22 % and out over the last 28 % of the path's height). Only on viewer-right edges of hair, the top-right of the bun, shoulders and the gesture arm. No rims on ears, the bun underside or sleeve ends.
- Hair language: 3–5 shaped clumps per character with one shadow tone and one highlight; thin light strands are tapered fills, never strokes.
- No outlines on silhouettes, only interior detail lines. Weights: lids 3.2–3.4, features and mouths 3.0–3.2, glasses 3.4–3.8, detail creases 1.3–1.6.
- Hands: one silhouette per hand with 1.3–1.6 px crease strokes, never outlined capsules. Gesture hands are drawn at `scale(1.3)` so the gesture reads at 110 px.
- Small sizes (≤ 110 px): use the avatar crop, `viewBox="62 22 280 300"` (Sisu) or `viewBox="58 4 280 300"` (Aava). It keeps the head at ~60 % of the tile height and still fits the celebrate hand. See `renders/avatars-small.png`. The full bust works from about 160 px up.
- Mouth center x≈206–207 (before the 3/4 shift), y≈246–256 after the −4 lift. The talk loop is calm → talk-a → talk-o → talk-a. Every open mouth uses the same teeth band and tongue construction, so the frames match.
