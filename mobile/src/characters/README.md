# Characters: Sisu & Aava

The two AI coaches are the face of Rahakamu (SPEC §6 / §6b). They are original, human
cartoon characters: half-body busts in a flat style with soft cel-shading. One component
powers the home-screen dock (~96–110 px, mostly idle) and the large chat hero (190–240 px,
driven by the chat stream). Everything is vector (`react-native-svg`) animated with
Reanimated 4, so there are no image assets.

| | Sisu, "The Trainer" | Aava, "The Mentor" |
|---|---|---|
| Pedagogy | Direct and energetic: small reps, streaks, wins | Calm and thoughtful: explains the *why* |
| Look | Late 20s, tousled sandy hair, short beard, thin glasses, amber quarter-zip, smartwatch, tablet with a rising chart | Mid 30s, dark bun with a pencil, round tortoiseshell glasses, teal cardigan over a cream blouse, notebook with a donut chart |
| Colour | `#F5A524` (accent `#B56A10`) | `#3DD9B4` (accent `#12665A`) |
| Motion | Quick 260 ms blends, bouncier hops, thumbs-up pump | Slow 520 ms blends, gentle breathing, raised "idea" finger + sparkle |
| Voice (expo-speech) | pitch 0.95, rate 1.05 | pitch 1.1, rate 0.95 |

## Usage

```tsx
import { Character, PERSONAS, moodToState, type CharacterState } from '@/characters';

<Character persona="sisu" state="idle" />                         // 120 px default
<Character persona={persona} state={chatState} size={220} locale="sv" haptics />
```

Props: `persona: 'sisu' | 'aava'`, `state: CharacterState`, `size?` (px, default 120; the
character is drawn in a size × size square), `locale?: 'en' | 'fi' | 'sv'` (accessibility
label language), `haptics?` (success haptic when celebrate starts, native only),
`accessibilityLabel?`, `style?`, `testID?`.

`PERSONAS[id]` returns `{ id, name, title, tagline, role, color, accent, tint, emoji, voice{pitch,rate} }`;
`title`, `tagline` and `role` are `Localized` (`en`, `fi`, `sv`).

### Driving the state from the chat stream (SPEC §4.2)

| Situation / SSE event | `state` |
|---|---|
| Mic held, or the composer is focused | `listening` |
| `status` thinking / tool | `thinking` |
| `token` events streaming, or TTS speaking | `talking` |
| `done.mood` | `moodToState(mood)` → `happy` / `concerned` / `celebrate` / `idle` |

State changes blend over the persona's `blendMs`, so it is fine to switch states as often as
events arrive.

## What each state does

| State | Face | Body / effects |
|---|---|---|
| idle | Closed smile, random blinks every 2.5–5 s, pupils glance around | Breathing, slight head sway |
| listening | Calm smile, raised brows, eyes to the user | Head tilts in, pulsing halo ring in the persona colour |
| thinking | Off-centre "hmm" mouth, one brow up, pupils up to the side | Head straightens, three-dot bubble |
| talking | Irregular closed / A / O mouth loop | Head bob |
| happy | Grin, ^ ^ eyes with raised cheeks | Small bounce |
| concerned | Small soft mouth, inner brows lifted | Sisu: sweat drop. Aava: glasses slip and are pushed back up |
| celebrate | Grin | Gesture arm springs in (Sisu thumbs-up, Aava "idea" finger), hop, sparkles |

## Architecture

```
Character.tsx         public component: memo, unique SVG id prefix, a11y label, haptics
 └─ HumanCharacter.tsx  layer stack: floor glow, halo, figure { head-back, body + arms,
                        head-front (face, mouths, eyes, lids, brows, hair, glasses), gesture arm },
                        think bubble, sparkles
art/sisu.tsx, aava.tsx  AUTO-GENERATED from design/characters/{sisu,aava}.svg by tools/svg2rn.py
art/types.ts            the PersonaArt contract the generator fills
rig.ts                  one shared clock, state weights, blink scheduler
pose.ts                 derives the per-frame pose (tilt, bob, gaze, brows, mouth weights …)
motion.ts               MOTION profiles and the state → pose table (from design tools/render.py)
layout.ts               art units → px; avatar crop up to 140 px, full bust above
Effects.tsx             halo rings, think bubble, sparkles
personas.ts, types.ts   metadata, labels, moodToState, public types
```

- Moving parts are full-size `Animated.View` layers transformed around pivots in art units
  (same on iOS, Android and web). Inside the SVG only opacity, circle `cx/cy` (pupils) and
  path `d` (brows, sweat drop) are animated. No filters or blur.
- Optional layers (halo, bubble, sweat, gesture arm, sparkles) mount only while their state is
  active, plus a short linger to fade out. Static art is memoized.
- To change the art, edit `design/characters/tools/build.py`, rebuild the SVGs, then run
  `python3 mobile/src/characters/tools/svg2rn.py`.

## Accessibility

- The root is `accessibilityRole="image"` with a localized label, e.g. "Sisu, your trainer —
  thinking", "Aava, mentorisi — puhuu", "Sisu, din tränare — glad".
- With the OS Reduce Motion setting on, hops, sparkles and halo pulses are off; expressions
  still change.

## Testing

`/characters-lab` (dev route) shows both characters in every state at 64, 120 and 240 px
("all sizes"), with auto-cycle, an EN/FI/SV label switch and a "simulate chat flow" button.
