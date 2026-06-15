# Seed.md — PF Coach sample & reference data plan

> Two distinct data classes, seeded and managed differently. **Reference data** is real and
> required for the live app to function (you'll use it on the floor). **Demo data** is one
> flagged, fictional user with fabricated history, so the progress screens look alive in a
> pitch. Keep them cleanly separable.

---

## 0. Principles

- **One idempotent seed script** (`seed.py`, SQLAlchemy), run outside Alembic migrations.
- **Reference data always seeds.** Demo user is behind a `--demo` flag so production can
  skip it.
- **Everything demo is flagged** (`users.status` + an `is_demo`-style marker, and
  `clubs.is_demo`) so it's trivial to exclude from real analytics or wipe.
- **Idempotent = upsert by natural key** (club slug, exercise slug, user email) so re-runs
  don't duplicate.
- Real data you enter through the live app is never touched by the seed script.

---

## 1. Reference data (real — required for the app)

### 1.1 Clubs (2)
Enough to demonstrate the home-vs-travel swap. Rename to your real clubs.

| slug | name | role | equipment |
|------|------|------|-----------|
| `home-club` | PF — (your home club) | home | full set |
| `alt-club`  | PF — (a nearby club) | travel | full set **minus 1–2 machines** (to force a swap) |

### 1.2 Movement patterns (6)
`horizontal_push`, `vertical_pull`, `horizontal_pull`, `hip_hinge`,
`knee_dominant` (squat), `core_carry`.

### 1.3 Equipment types (representative PF floor)
With `measurement_type`, and `bar_weight_lb` only where it applies.

- **Cardio** (`cardio`): treadmill, elliptical, Arc/elliptical cross-trainer, upright bike,
  recumbent bike, stair climber.
- **Selectorized strength** (`selectorized`): chest press, shoulder press, lat pulldown,
  seated row, leg press, leg extension, seated leg curl, bicep curl, triceps press,
  abdominal crunch, back extension, hip abductor/adductor.
- **Smith machine** (`smith`, `bar_weight_lb` ≈ effective, e.g. 15–25).
- **Functional** (`functional`): cable tower / functional trainer.
- **Circuit** (`circuit`): the 30-Minute Express Circuit stations (one logical entry).
- **Bodyweight** (`bodyweight`): ab/core mat work.

> Note: leave `stack_map` empty (deferred). Optionally set a global `nominal_plate_lb`
> default so dial/lever increments convert to a fractional pin step; not required to start.

### 1.4 Exercise library (starter set, PF-only)
Each exercise tagged: `measurement_type`, `primary_pattern_id`, `equipment_type_id`,
`muscle_groups`, `difficulty`, `is_anchor`, and a **linked** `video_url` (YouTube, never
rehosted). Suggested starter coverage — at least 2–3 exercises per pattern so the rotation
engine has a pool to rotate through, with the compound lifts flagged `is_anchor = true`:

| pattern | anchor (fixed) | variety pool (rotates) |
|---------|----------------|------------------------|
| horizontal_push | chest press (machine) | Smith bench, cable press, push-up |
| vertical_pull | lat pulldown | assisted pull-up, straight-arm pulldown |
| horizontal_pull | seated row | cable row, reverse pec deck |
| hip_hinge | (Smith RDL or back ext) | hip thrust (machine), cable pull-through |
| knee_dominant | leg press | leg extension, Smith squat, hack-style press |
| core_carry | ab crunch (machine) | cable woodchop, plank (bodyweight), carries |

### 1.5 Nutrition & supplements (placeholders)
- `nutrition_partners`: 2–3 illustrative meal-kit partners (placeholder name + image +
  affiliate URL). **Not** claimed integrations.
- `meal_suggestions`: ~1 per `day_of_week` (7 rows), each linked to a partner.
- `supplements`: 4–6 generic entries (protein, creatine, multivitamin, pre-workout, etc.).

---

## 2. Demo user (fabricated — for showcase only)

One member that makes every progress view populated and believable.

### 2.1 The user
- Name "Alex Rivera (Demo)", email `demo@pfcoach.app`, flagged demo, `locale='en'`.
- Intake: goal general fitness, `experience_level='beginner'`, 3 days/week,
  cardio 40 / strength 60, home club `home-club`, started in `guided`, **promoted to
  `coached`** partway through (so an `autonomy_events` row exists).

### 2.2 Program & sessions
- One active program, **8 weeks**, anchors fixed, variety slots rotating week to week
  (so the pattern-trend stays continuous while individual exercises come and go — the
  whole point).
- **~24 completed sessions** (3/week × 8 weeks), each with realistic `set_entries`:
  - **Week 1–2:** `session_type='express_circuit'` (the guided beginner on-ramp) — circuit
    logging with `tut_seconds`, no pin progression yet.
  - **Week 3 onward:** standard sessions on machines, showing the progression pattern below.
  - **One cardio entry per session** (treadmill or elliptical) so the cardio dashboard has
    distance/duration/HR data.
  - **At least one swap:** a session at `alt-club` where a prescribed machine is missing →
    `was_swapped=true`, `swap_reason='other_club'`, swapped to a same-pattern alternative
    (proves the pattern-trend survives the swap).
  - **One incremental-adder example:** a leg-press set logged with `micro_load_kind='dial'`,
    `added_load_lb=10` (exercises that part of the schema).

### 2.3 The progression curve (so charts look alive)
Seed selectorized exercises with the realistic "reps climb, then pin jumps" pattern we
designed around. Example for **chest press** across the standard weeks:

| week | pin | sets×reps | proxy (effective_step×reps×sets) | indexed (vs wk-3 baseline) | note |
|------|-----|-----------|----------------------------------|----------------------------|------|
| 3 | 5 | 3×8  | 120 | 100 | baseline |
| 4 | 5 | 3×10 | 150 | 125 | rep progress, same pin |
| 5 | 5 | 3×12 | 180 | 150 | rep progress, same pin |
| 6 | 6 | 3×8  | 144 | 120 | **pin jump** → proxy dips, **pin-badge fires** |
| 7 | 6 | 3×10 | 180 | 150 | rebuilding reps |
| 8 | 6 | 3×12 | 216 | 180 | new high |

This single exercise demonstrates the smooth proxy curve, the pin-jump dip, and the
pin-badge milestone all at once. Repeat the same shape (offset/varied) across the other
anchors so the **pattern-trend** lines all rise convincingly with natural wobble.

### 2.4 Body metrics
Weekly weigh-ins over the 8 weeks trending gently down (e.g., 198 → 192 lb) with one or two
flat/up weeks for realism. Optional waist measurement trending down.

### 2.5 What this lights up
Pattern-trend hero (up and to the right, with realistic dips), per-exercise drill-down,
volume distribution, cardio dashboard, PRs / pin-badges, an autonomy promotion event, a
swap that didn't break the trend, and a consistency streak. Nothing in the demo is empty.

---

## 3. Build notes

- `seed.py` structure: `seed_reference()` (always) then `seed_demo()` (only with `--demo`).
- Upserts keyed on slugs/email; safe to re-run.
- Generate demo sessions programmatically from a small curve spec (like §2.3) rather than
  hand-writing 24 sessions — one function that takes (exercise, weekly [pin, reps, sets])
  and emits sessions + session_exercises + set_entries with correct `session_metric`.
- Compute and store `session_metric_value`/`kind` at seed time exactly as the live app
  would on session completion, so seeded and real data are indistinguishable to the
  progress queries.
- A `--wipe-demo` companion (delete where demo-flagged) keeps showcase data disposable.

---

## 4. Open seed decisions

- **Real club names:** plug in your actual home club + one nearby alternate, or keep
  generic for a neutral demo.
- **Exercise count:** starter table above is the minimum for rotation to feel real;
  expand toward the fuller PF floor as you populate via the live app.
- **Demo user count:** one is enough for a pitch; add a second (e.g., an advanced
  self-directed user) only if you want to show the autonomy gradient's far end.
