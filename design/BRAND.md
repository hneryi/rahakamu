# Rahakamu brand kit

**Talk with your money.** Rahakamu is a personal economic trainer. The brand should feel premium, calm and dark-first, with the warmth of two coach characters. All artwork here is original. It does not use any S-Bank / S-Pankki logo, wordmark or trademark. "S-green" means only that we use a similar colour family.

## The mark
A **chat bubble** (you talk with your money) holding **three rising bars** (the three baskets: fixed, irregular, leaks, getting healthier over time), plus an **amber coin with an up-chevron** (growth and savings) and a **mint sparkle** (the AI). The coin is Sisu's amber and the sparkle is Aava's mint, so both coaches show up in the mark itself.

- Minimum size: 24 px for the full mark. Below that, use `favicon.svg` (the simplified version without shine, sparkle or coin ring).
- Clear space: 25 % of the mark's width on every side.
- Never recolour the bubble outside the green gradient. Never rotate it, stretch it, add an outline or put it on a busy photo.

## Palette
| Token | Hex | Use |
|---|---|---|
| bg | `#07140F` | App background, splash background, adaptive-icon base |
| bg-2 | `#0B1F17` | Gradient end, raised areas |
| surface | `rgba(255,255,255,0.06)` + 1 px `rgba(255,255,255,0.08)` border | Glass cards |
| primary (S-green) | `#00B26F` | Primary actions, positive money |
| green-hi / green-lo | `#1ED68C` / `#008A56` | Mark gradient stops, pressed states |
| mint (Aava) | `#3DD9B4` | Accent, Aava, tagline, AI sparkle |
| amber (Sisu) | `#F5A524` | Sisu, coin, streaks and achievements, irregular basket |
| warn | `#FF6B5A` | Overspend, critical safe-to-spend |
| text / muted | `#F2F7F4` / `#9FB3A9` | Primary and secondary text |
| basket: fixed / irregular / leak | `#5B8DEF` / `#F5A524` / `#FF6B8A` | Basket meter, charts, chips |

Contrast: text `#F2F7F4` on `#07140F` is about 17:1, muted is about 8:1, and primary green on bg is about 6.5:1 (AA for body text). Do not put green text on green surfaces.

## Typography
- **App UI:** the system font (SF Pro on iOS, Roboto on Android, system-ui on web), as SPEC §5.4 sets out. Type scale 34 / 22 / 17 / 15 / 13. Show money in **tabular numbers** (`fontVariant: ['tabular-nums']`), bold, and keep the € sign smaller than the figure.
- **Brand / marketing:** **Lato** (SIL OFL). Black for the wordmark, Bold for taglines, Regular for body text. Every brand SVG already has its text turned into outlines, so no font file is needed to show them.
- **Current wordmark:** "Rahakamu", one word, capital R. The coming-soon page renders it as system-font SVG text beside the unchanged mark.
- **Legacy wordmarks:** `wordmark.svg` and `wordmark-on-light.svg` still contain the old outlined name. Do not use them for new Rahakamu material; regenerating those assets is a separate task.

## Characters
| | **Sisu** (bear) | **Aava** (owl) |
|---|---|---|
| Role | The Trainer | The Mentor |
| Colour | Amber `#F5A524` | Mint `#3DD9B4` |
| Look | Round amber bear, green sweatband, whistle | Soft teal owl, big round glasses, tiny book |
| Teaching style | Challenges, streaks, reps, quick wins | Explains *why*, uses analogies, asks one reflective question |
| Voice (TTS) | pitch 0.9, rate 1.05 | pitch 1.1, rate 0.95 |

Usage:
- Show **one** active coach at a time in the app: the dock, the chat header and their speech bubbles. Show both together only in onboarding (the coach picker) and in marketing such as the social card.
- Tint the coach's speech bubble or accent ring with their colour at about 15 % opacity. Keep the money UI in neutral or basket colours, so a persona colour never reads as "good" or "bad".
- The coaches' mood (happy, concerned, celebrate) follows the data. Do not show celebrate on a critical safe-to-spend status.

## Tone of voice
Both coaches use only numbers from tools and never invent figures. They stay mobile-short (120 words or fewer), tie spending to the three baskets, and may end with one "💡" concept. Investing gets general education only, with a note about risk and a pointer to S-Bank advisors. They reply in the user's language (fi/en/sv).

**Sisu: energetic, tough love, never shaming.** Short, punchy sentences and fitness metaphors.
- ✅ "Strong week! Leaks down 18 € vs last week. That's a PR. Next rep: 7 days with no takeaway. In?"
- ✅ "Taxis took 64 € this month. Two rides fewer is 30 € back in your pocket. Easy win."
- ❌ "You wasted money again." (shaming) ❌ "Buy index funds now." (personalised investment advice)

**Aava: calm, warm, Socratic.** Plain language, one analogy, one question.
- ✅ "Think of your fixed basket as the foundation of a house. It's 52 % of your spending, which is sturdy. What would you like the leftover 'rooms' to be for?"
- ✅ "Small café visits are like a dripping tap: 3 € a time, but 41 € this month. Is that a drip you enjoy, or one you'd like to fix?"
- ❌ Long lectures, jargon without an explanation, more than one question.

## Do and don't
- **Do:** stay dark-first, use plenty of space, round shapes (radius 24), one accent colour per screen and big friendly numbers.
- **Do:** use the basket colours the same way everywhere: the meter, charts, chips and lessons.
- **Do:** call the product "Rahakamu" (one word, capital R).
- **Don't:** copy S-Bank / S-Group logos, the "S" symbol, typefaces or brand art. Don't say Rahakamu is an official S-Bank product. It is a Junction 2026 concept.
- **Don't:** use real merchant brand names in any visuals, mock-ups or screenshots.
- **Don't:** put the mark on a light-green background, add drop shadows to the wordmark, or use the coin without the bubble.

## Files
The marketing wordmarks, social cards, their PNG derivatives and `build.py` are legacy
SPankkiBot assets. The [legacy pitch slides](../pitch/slides.html) also retain that name;
use Rahakamu for new material. No design regeneration is required to run the app.

The legacy generator can recreate the SVGs and PNGs (including the old name):
```
uv run --with cairosvg --with fonttools python design/build.py
```
| File | What it is |
|---|---|
| `design/logo.svg` | Mark, 512 grid, transparent |
| `design/wordmark.svg` / `design/wordmark-on-light.svg` | Legacy mark + "SPankkiBot" (outlined text; not the current Rahakamu display name) for dark / light backgrounds |
| `design/icon.svg` | 1024 full-bleed app icon (dark green gradient + glow + mark) |
| `design/adaptive-foreground.svg` | Android adaptive foreground: mark kept inside the 66 % safe circle, transparent |
| `design/adaptive-background.svg` | Android adaptive background: gradient |
| `design/adaptive-monochrome.svg` | Android 13+ themed icon: white silhouette with bars and coin cut out |
| `design/splash.svg` | Mark centred, transparent background |
| `design/favicon.svg` | Simplified mark for 16 to 48 px, transparent |
| `design/social-card.svg` | 1200×630 README / pitch / OG card |
| `design/png/logo-512.png`, `design/png/wordmark.png` | Bitmaps for the README and slides |
| `design/png/social-card.png` | 1200×630 social card (wordmark + "Talk with your money." + baskets + Sisu & Aava) |

### Copy into the Expo app (`mobile/assets/images/`, filenames match `mobile/app.json`)
| Source | Target | Size |
|---|---|---|
| `design/png/icon.png` | `mobile/assets/images/icon.png` | 1024×1024, opaque |
| `design/png/android-icon-foreground.png` | `mobile/assets/images/android-icon-foreground.png` | 1024×1024, transparent |
| `design/png/android-icon-background.png` | `mobile/assets/images/android-icon-background.png` | 1024×1024, opaque gradient |
| `design/png/android-icon-monochrome.png` | `mobile/assets/images/android-icon-monochrome.png` | 1024×1024, white on transparent |
| `design/png/splash-icon.png` | `mobile/assets/images/splash-icon.png` | 400×400, transparent |
| `design/png/favicon.png` | `mobile/assets/images/favicon.png` | 48×48, transparent |

```
cp design/png/{icon,android-icon-foreground,android-icon-background,android-icon-monochrome,splash-icon,favicon}.png mobile/assets/images/
```

Recommended `mobile/app.json` changes (the mobile builder or the orchestrator should make these):
- `expo.name`: `"Rahakamu"`, and `expo.userInterfaceStyle`: `"dark"` (or keep `"automatic"` if the light theme is ready).
- `android.adaptiveIcon.backgroundColor`: `"#07140F"` (currently Expo's default `#E6F4FE`).
- `expo-splash-screen` plugin: `backgroundColor` `"#07140F"`, `imageWidth` `160`.
- `ios.icon` currently points at the template's `./assets/expo.icon`. Either set it to `"./assets/images/icon.png"` or remove it so iOS falls back to `expo.icon`.
