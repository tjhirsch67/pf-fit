# Design.md — PF Coach (concept demo)

> Visual + UX guidance for the PF Coach demo. The goal is for the UI to **feel like it
> belongs in the Planet Fitness world** — same energy, warmth, and color language — while
> using **none of PF's logos, emblems, registered phrases, or custom typeface.** We evoke,
> we do not copy. Read §1 and §9 before building anything.

---

## 1. Brand intent & the no-logo rule

**Evoke, don't infringe.** We borrow PF's *feeling* — friendly, inclusive,
non-intimidating, energetic, bold, approachable — through color, layout, and voice. We do
**not** use:

- the PF logo or the gear / thumbs-up emblem (or any approximation of it)
- PF's custom wordmark typeface
- registered phrases as product chrome ("Judgement Free Zone®", "PF Black Card®",
  "You Belong®", "High School Summer Pass®", etc.)
- official PF photography or marketing imagery

For the demo, use a **neutral placeholder wordmark**: lowercase text `pf coach` with a
small `concept` tag, set in our display font. No icon mark. (This is a pitch artifact;
real branding would require PF approval.)

## 2. Voice & tone

PF's copy is warm, encouraging, plainspoken, lightly playful, and **always
non-intimidating**. Mirror that:

- Speak *to* the beginner, never down to them. "Let's keep it simple." "No experience
  needed." "Nice work."
- Lowercase, friendly headlines are on-brand. Sentence case everywhere; never ALL CAPS,
  never Title Case.
- Encourage, never gate or shame. The nudge to advance is an **invitation**:
  "Build a streak and we'll invite you to start customizing" — never "you haven't
  unlocked this."
- Short sentences. Active voice. Real verbs.

## 3. Color system

Anchored on PF's **confirmed** brand colors (purple `#A4278D` / PMS 248, yellow `#F9F72E`,
black, white). Tints and shades below are **derived** for UI use (surfaces, text, states).

```css
:root {
  /* --- Brand (confirmed) --- */
  --pf-purple:        #A4278D;  /* primary brand purple (PMS 248) */
  --pf-yellow:        #F9F72E;  /* accent / energy pop */
  --pf-black:         #111111;  /* off-black for text */
  --pf-white:         #FFFFFF;

  /* --- Purple scale (derived) --- */
  --purple-900:       #4A1240;  /* deepest — large surfaces, headers in dark contexts */
  --purple-800:       #6E1A5E;  /* deep — primary text on light, strong fills */
  --purple-600:       #A4278D;  /* = brand */
  --purple-300:       #D98FCB;  /* hover tints, chart fills */
  --purple-100:       #F3E0EF;  /* light fills, selected pills */
  --purple-050:       #FBF1F8;  /* faint surface wash */

  /* --- Yellow scale (derived) --- */
  --yellow-600:       #D6D400;  /* hover / darker accent */
  --yellow-500:       #F9F72E;  /* = brand accent */
  --yellow-100:       #FCFBC2;  /* light highlight fill */
  /* Text ON yellow must be deep purple or near-black — never white. */

  /* --- Neutrals --- */
  --ink:              #111111;  /* primary text */
  --ink-muted:        #5F5E5A;  /* secondary text */
  --ink-faint:        #8E8D87;  /* tertiary / hints */
  --surface:          #FFFFFF;  /* cards */
  --surface-2:        #F6F5F1;  /* page / muted surfaces */
  --border:           rgba(17,17,17,0.12);
  --border-strong:    rgba(17,17,17,0.22);

  /* --- Semantic --- */
  --go:               #1D9E75;  /* "go" / success / PR (Express Circuit green light) */
  --go-ink:           #0F6E56;
  --rest:             #E24B4A;  /* "rest/switch" / error (Express Circuit red light) */
  --rest-ink:         #A32D2D;
  --info:             #378ADD;
  --warn:             #BA7517;
}
```

**Usage rules**
- **Purple = primary identity** (nav accents, primary buttons, headers, selected states,
  the active autonomy-mode pill). Use `--purple-600` for fills, `--purple-800` for text on
  light purple, `--purple-900` for large dark surfaces.
- **Yellow = sparingly, for energy and CTAs that must pop.** It's a spotlight, not a
  background. Text on yellow is always `--purple-800` or `--ink` — never white (fails
  contrast).
- **Traffic-light timer** uses `--go` (work interval) and `--rest` (transition) — this maps
  directly to the real Express Circuit green/red system.
- **Dark mode:** invert surfaces to near-black, lift text to white/`--purple-100`, keep
  purple identity but use lighter purple (`--purple-300`) for accents so it reads on dark.
  Every token must be legible on both light and near-black backgrounds.

## 4. Typography

We can't use PF's custom face, so we evoke its bold, friendly, geometric character.

- **Display / headings:** a friendly geometric sans — `Poppins` or `Montserrat`
  (Google Fonts), weight 600 for headlines, 500 for sub-heads. Lowercase headline styling
  is on-brand and welcome.
- **Body / UI:** `Inter` or system sans (`-apple-system, "Segoe UI", Roboto, sans-serif`),
  weights 400 / 500.
- **Two weights per face, max.** No 700+ except an occasional display headline.

```css
--font-display: "Poppins", "Montserrat", system-ui, sans-serif;
--font-body:    "Inter", -apple-system, "Segoe UI", Roboto, sans-serif;
```

**Scale (mobile-first):** h1 28 / h2 22 / h3 18 / body 16 / small 13 / micro 11 (floor).
Line-height 1.5–1.7 for body. Never below 11px.

## 5. Layout & spacing

- **Mobile-first PWA.** Design at ~390px width first; scale up gracefully.
- **Bottom tab nav** on mobile (Today · Plan · Progress · More). Thumb-reachable.
- **Card-based content blocks** echo the PF site: image/illustration + bold headline +
  short blurb + single clear CTA.
- **Hero pattern:** big friendly headline, supportive line, one primary action. Low
  cognitive load — one decision per screen for the Guided beginner.
- **Spacing rhythm:** 4 / 8 / 12 / 16 / 24 / 32. Generous whitespace; uncluttered =
  non-intimidating.
- **Radius:** 12px for cards, 8px for inputs/buttons, full-pill (999px) for badges/timers.
- **Borders:** 1px `--border`; bump to `--border-strong` on hover/emphasis. No heavy
  shadows — flat, clean surfaces.

## 6. Components

- **Primary button:** filled `--pf-purple`, white text, radius 8, comfortable tap target
  (min 44px height). Hover → `--purple-800`.
- **Accent CTA (use rarely):** filled `--pf-yellow`, text `--purple-800`. For one
  high-energy action per screen at most.
- **Secondary button:** transparent, 1px `--border-strong`, `--ink` text.
- **Autonomy-mode pills:** three pills — Guided / Coached / Self-directed. Active = filled
  `--purple-100` with `--purple-800` text; inactive = `--surface-2` with `--ink-faint`
  text. Always show all three so the user sees the path ahead.
- **Station card (the demo's money shot):** video thumbnail (linked YouTube, play icon
  overlay) → exercise name → "set the pin to ~N" chip → traffic-light timer pill
  (`--go` work / `--rest` transition) → `Done` + `Swap` actions side by side.
- **Timer pill:** full-pill, `--go` background tint with `--go-ink` text in the work
  interval; flips to `--rest` tint / `--rest-ink` during transition.
- **Streak / consistency:** thin progress bar in `--go`, with an encouraging caption.
- **Progress charts:** line charts in `--purple-600` (pattern-trend hero) with per-exercise
  sparklines beneath in `--purple-300`; PRs marked in `--go`. Indexed to 100 baseline
  (label the axis "% of starting point" for the pattern view). Cardio dashboards use
  `--info`. Keep charts flat, gridlines faint, no 3D, no gradients.
- **Badges/tags:** full-pill, light fill + same-family dark text (e.g., `--purple-100` /
  `--purple-800`). Never plain black text on a colored fill.

## 7. Iconography

- Use a clean **outline** icon set (e.g., Tabler, Lucide, or Heroicons outline). One set
  throughout.
- **No PF emblem, gear, or thumbs-up icon.** Don't hand-draw anything resembling it.
- Icons inherit text color; decorative icons get `aria-hidden`, icon-only buttons get an
  `aria-label`.

## 8. Imagery

- Prefer simple illustrations or neutral, generic gym/equipment photography (licensed or
  placeholder) — **not** PF's marketing photos.
- The vibe is clean, bright, spacious, welcoming — matching PF's "clean and spacious
  environment" without lifting their assets.

## 9. Accessibility

- WCAG AA contrast minimum. **Yellow text on white fails** — never do it; yellow is a fill,
  text on it is dark. Purple `--pf-purple` on white passes for large/bold text; use
  `--purple-800` for body-size purple text.
- Touch targets ≥ 44×44px. Forms large and simple (the beginner is intimidated already).
- Respect `prefers-reduced-motion`; the traffic-light timer must not rely on color alone —
  pair it with a "Go" / "Switch" label.
- All content must work in light and dark mode.

## 10. Quick do / don't

**Do:** purple-led identity, yellow as a spark, friendly lowercase headlines, one decision
per beginner screen, flat clean cards, link out to videos, label everything in plain words.

**Don't:** the PF logo/emblem, registered phrases as our chrome, PF's exact typeface, white
text on yellow, ALL CAPS, cluttered screens, gating language, rehosted videos.
