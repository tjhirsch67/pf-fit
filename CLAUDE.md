# CLAUDE.md — PF Coach (concept demo)

> Working context file for Claude Code. This is a **concept/demo** built to pitch an
> intelligent coaching layer for Planet Fitness members. It is not affiliated with,
> endorsed by, or approved by Planet Fitness. See **Guardrails** before generating any
> branding, copy, or assets.

---

## 0. Companion docs (read before relevant work)

This file is auto-loaded every session. The docs below are **not** — consult them when the
work touches their area:

- **`Design.md`** — UI/visual system (PF-evoking palette, typography, components,
  no-logo rules). Read before building or restyling **any frontend**.
- **`Schema.md`** — PostgreSQL data model (measurement-type taxonomy, indexed-progress
  math, clubs/equipment, rotation, logging). Read before **any DB, model, or migration**
  work. It is the source of truth for the data layer.
- **`Seed.md`** — reference data (clubs, equipment, exercises, patterns, nutrition) vs. the
  flagged demo user with sample history. Read before writing **seed scripts** or sample data.

If these conflict with this file, flag it rather than silently picking one.


---

## 1. One-liner

PF already promises "free fitness training" but delivers it as a one-time, group-sized
touch with no ongoing personalization. **PF Coach is the continuous, adaptive version of
that promise** — an AI personal-trainer layer that turns PF's equipment floor into a
guided, rotating, progress-tracked program, sold as a low-cost add-on.

## 2. Status & mode

- Phase: **early concept / demo.** Planning-first. No production commitments yet.
- Default working style: **discuss and plan before coding** (see Conventions).
- Audience for the demo: primarily the **end user** (a brand-new member who has no idea
  where to begin and will otherwise camp on cardio machines for two years). Secondary,
  latent pitch: PF business stakeholders (churn reduction + ancillary revenue).

## 3. The problem & the user

Target user is the intimidated newcomer. PF's own app is a flat content library with no
hand-holding and no sense of progression — nobody uses it. The product's job is to walk
that person onto real machines on day one, then hand over control as they gain confidence.

## 4. Core organizing principle — the autonomy gradient

The app starts maximally prescriptive and **hands over control as the user earns
confidence — by invitation, never by gate** (gating is off-brand for the Judgement Free
Zone).

1. **Guided** — zero decisions. "Go to this machine, here's the video, set the pin here,
   do this, now move on." Anchored on the 30-Minute Express Circuit.
2. **Coached** — app still drives programming + rotation; user can swap and say
   "too easy / too hard"; progressive overload turns on.
3. **Self-directed** — user customizes their own splits; AI shifts to advisory (form,
   plateau-breaking, injury prevention).

The intake places the user on this gradient. Consistency (not raw session count) triggers
a **nudge** to advance; the user can self-promote (or stay guided forever) anytime, with
zero friction or judgment.

## 5. Business model — free vs. paid

**Rule:** never paywall anything PF already gives away for free; fire the paywall only at
the moment of demonstrated engagement (which is the same moment we nudge them to customize).

**Free — "PF Start" (= digitized PE@PF):**
- Intake interview + initial recommendation + autonomy-gradient placement
- Guided first session + full Express Circuit walk-through (videos, pin settings, pacing)
- Equipment orientation / how-to video library (linked out, never rehosted)
- Basic logging + static home-club plan
- Consistency / streak tracking
- Basic unavailable→swap (a substitute, not the progression-preserving one)
- Nutrition partner meals + supplements surface (affiliate/marketing surfaces → want
  maximum eyeballs → free)

**Paid — "PF Coach" add-on (the thing PF can't staff):**
- Adaptive, weekly-rotating program across the equipment floor
- Progressive overload (auto-adjusting loads/reps from logged performance)
- Deep progress analytics (pattern-trend + per-exercise drill-down, volume, est-1RM, PRs)
- Intelligent, progression-preserving substitutions (swap / travel club)
- Injury assessment + AI rehab programs
- Periodization, deload weeks, plateau-breaking; coached + self-directed modes

**Price framing:** PF Classic ≈ $15/mo, Black Card ≈ $24.99/mo. The add-on should feel
like "a little more for a trainer" — roughly +$5–10/mo, or a new "Black Card+" coaching
tier.

## 6. Domain model (the concepts the code must get right)

### 6.1 Measurement-type taxonomy
PF's floor is heterogeneous; a single reps×weight model produces garbage. Every exercise
carries a `measurement_type` that determines its logging UI and progress math:

| type | unit(s) logged | notes |
|------|----------------|-------|
| `selectorized` | pin position + reps + sets | Stack often labeled 1–15, **not lbs** — track the pin number; optional per-machine lbs map later |
| `plate_loaded` | lbs + reps + sets | Hammer Strength etc. |
| `smith` | lbs + reps + sets | Bar is counterbalanced, **not 45 lb** — store effective bar weight |
| `cardio` | time / distance / level / incline / pace / HR | Separate schema; not sets |
| `circuit` | time-under-tension intervals (1:00 on / 0:30 transition) | No reps; Express Circuit mode |
| `functional` | reps or time + load | Cables, TRX, kettlebells, ropes |
| `bodyweight` | reps or time | Core / ab work |

### 6.2 Movement patterns & slots
Programs are built from stable **pattern slots**: horizontal push, vertical pull,
horizontal pull, hip hinge, knee-dominant/squat, carry/core. Each slot has a **pool** of
PF-available exercises tagged to that pattern. "Anchor" slots (core compounds) stay fixed;
"variety" slots rotate.

### 6.3 Rotation engine
Fills variety slots weekly to expose the user to different machines, holding anchors
constant, **constrained by the user's current club's available equipment.** Rotation
intentionally breaks per-exercise progression continuity — which is why progress is
tracked at two levels (below).

### 6.4 Progress normalization (load-bearing decision)
You cannot average a leg press (pin 12) against a hack squat (135 lb). For each exercise,
compute a per-session metric (estimated 1RM for load-based via Epley/Brzycki, or
volume-load = sets×reps×load), then **index it to that exercise's own first session = 100.**
Everything becomes percent-change-from-its-own-baseline, units-agnostic.

- **Pattern-trend** = recency-weighted average of indexed values across all exercises in a
  pattern. Stays continuous across rotation. *This is the hero metric.*
- **Per-exercise** = the drill-down beneath each pattern.
- Est-1RM is gated by measurement type (valid for plate/smith; rough on selectorized;
  N/A for circuit/cardio). Cardio gets its own dashboards.

UI: pattern-trend is the **container**, per-exercise is the **drill-down**, single exercise
history is the deepest level. One screen, three depths.

### 6.5 Club & equipment model + swap
A club = a set of available equipment (clubs genuinely differ). A session has a
`current_club` (defaults to home, one-tap override). Every prescribed exercise carries a
persistent **unavailable / swap** affordance (broken machine, occupied, or different club).
Swaps return **same-pattern** alternatives filtered to the current club, so a swap never
punches a hole in the pattern-trend.

### 6.6 PF anchors (grounding, not invention)
- Free tier mirrors **PE@PF** (PF's free, included small-group training + "Design Your Own
  Program" trainer intake — our intake *is* that intake, digitized).
- Beginner front door is the **30-Minute Express Circuit** (already on the floor, signposted,
  beginner-engineered, green/red traffic-light pacing).

### 6.7 Nutrition & supplements
- Nutrition: ~1 partner meal/day (e.g., meal-kit partners) as **illustrative placeholders
  with affiliate-style links** — not a claimed live integration. Suggested meals only, no
  prescriptive calorie targets.
- Supplements: marketing surface as-is; future state is a PF-branded line. FTC
  affiliate-disclosure hygiene on any real links.

## 7. Tech stack (house standard)

- **Backend:** FastAPI on Railway
- **Database:** PostgreSQL on Railway
- **Frontend:** vanilla HTML/CSS/JS, mobile-first PWA, deployed on Netlify
- **AI:** Anthropic API (program generation, intake reasoning, advisory)
- **Auth:** JWT + bcrypt
- **Email:** Mailtrap (if notifications are added)
- **Principle:** never hard-delete; admin-only reverse transactions

## 8. Reuse vs. net-new (relative to MARLON)

**Carries over cleanly:** intake/interview engine, exercise-library CRUD backend, AI
program generation, PDF export + email delivery, English/Spanish i18n, medical disclaimer
pattern, injury assessment + AI rehab.

**Net-new for PF Coach:** measurement-type taxonomy, movement-pattern/slot model, rotation
engine, indexed-progress analytics, club→equipment model + swap.

## 9. Demo scope (MVP slice — resist building everything)

The cold-open vertical slice that tells the whole story in one sitting:
1. Intake → recommendation with rationale (autonomy placement)
2. **Guided first session** on the Express Circuit at the home club (the money shot)
3. A generated rotating week
4. The unavailable→swap moment (model two clubs: a full "home" club and a "travel" club
   missing a machine or two)
5. Progress screen: pattern-trend hero + exercise drill-down, **seeded with a few weeks of
   data so charts look alive**
6. Nutrition showcase (placeholder partners)

Everything else is roadmap.

## 10. Guardrails (read before generating anything)

- **No Planet Fitness logo or emblem.** Do not use, recreate, or approximate the PF logo,
  the gear/thumbs-up mark, or any official iconography — now or in generated assets.
- **No registered phrases as our own branding** — avoid "Judgement Free Zone®",
  "PF Black Card®", "You Belong®", etc. as product chrome. Reference PF factually where
  needed, not as our identity.
- **No exact PF typeface.** Evoke, don't copy (see Design.md).
- **Demo labeling.** The app should read as a concept/prototype, using a neutral
  placeholder wordmark (e.g., "PF Coach — concept"). Before any public/commercial use,
  trademark and brand approval from PF would be required.
- **Videos are linked out** (YouTube), never downloaded or rehosted.
- **Nutrition partners are placeholders**, not claimed integrations.
- **Medical/financial:** reuse the medical disclaimer; the app is not medical or financial
  advice. Keep nutrition non-prescriptive.

## 11. Working conventions (collaboration prefs)

- **Plan first.** Discuss design/architecture before writing code.
- **Full file contents**, not partial diffs, when delivering code.
- **Test against production URLs.**
- Environment: Windows + PowerShell + VS Code; GitHub for version control; Claude Code for
  local sessions.
- Local project root: `C:\Projects\PF`.

## 12. Open decisions (pending)

- Promotion nudge trigger: consistency window vs. self-declared "I've got this" (current
  lean: consistency triggers the *nudge*, user always controls the *switch*).
- Demo equipment: one canonical "standard PF" set vs. modeling real club variability
  (current lean: two clubs, to showcase swap).
- Progress hero: confirmed **pattern-trend as container, per-exercise as drill-down.**
