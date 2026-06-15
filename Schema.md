# Schema.md — PF Coach (concept demo)

> PostgreSQL data model for the PF Coach demo (FastAPI on Railway, Postgres on Railway,
> SQLAlchemy + Alembic). The two load-bearing decisions live here: the **measurement-type
> taxonomy** (§7) and the **indexed-progress math** (§8). DDL below is illustrative — map to
> SQLAlchemy models and let Alembic own the real migrations.

---

## 0. Conventions

- **PKs:** `uuid` default `gen_random_uuid()` (Postgres 14+ has it built in).
- **Timestamps:** `timestamptz`, `created_at`/`updated_at` default `now()`.
- **Never hard-delete.** Soft-delete via `status` + `deleted_at`; destructive changes go
  through admin reverse transactions (§12).
- **Units are explicit.** Never store a bare "weight" — always a value + a unit column.
- **Snapshots over joins for hot reads.** `measurement_type` and `session_metric` are
  denormalized onto session rows so progress and logging don't chase joins.
- **Enums:** shown as `CREATE TYPE` for clarity; fine to implement as SQLAlchemy `Enum` or
  `text` + `CHECK`.

## 1. Enums

```sql
CREATE TYPE measurement_type AS ENUM
  ('selectorized','plate_loaded','smith','cardio','circuit','functional','bodyweight');

CREATE TYPE autonomy_mode    AS ENUM ('guided','coached','self_directed');
CREATE TYPE membership_tier  AS ENUM ('classic','black_card');
CREATE TYPE user_role        AS ENUM ('member','admin');
CREATE TYPE record_status    AS ENUM ('active','archived','disabled');

CREATE TYPE equipment_category AS ENUM ('cardio','strength','functional','circuit');
CREATE TYPE stack_unit        AS ENUM ('pin_number','lb','kg');
CREATE TYPE weight_unit       AS ENUM ('lb','kg');
CREATE TYPE distance_unit     AS ENUM ('mi','km','m');
CREATE TYPE difficulty_level  AS ENUM ('beginner','intermediate','advanced');
CREATE TYPE session_type      AS ENUM ('express_circuit','standard');
CREATE TYPE session_status    AS ENUM ('planned','in_progress','completed','skipped');
CREATE TYPE swap_reason       AS ENUM ('unavailable','occupied','preference','other_club');
CREATE TYPE metric_kind       AS ENUM ('est_1rm','volume_load','distance','duration','none');
CREATE TYPE micro_load_kind   AS ENUM ('none','magnet','lever','dial');  -- incremental adders between pins
```

## 2. ER overview (text)

```
users ──< programs ──< program_weeks ──< program_slots
  │           │                                 │ (pattern + chosen exercise)
  │           └── club (home)                    │
  │                                              ▼
  ├──< sessions ──< session_exercises ──< set_entries   (sparse-wide log)
  │        │              │
  │        └── club        └── exercise ── equipment_type ── club_equipment ──> clubs
  │                              │
  │                        movement_pattern
  │
  ├──< body_metrics
  ├──< autonomy_events
  └── home_club ──> clubs

exercise.measurement_type  → drives logging UI + which set_entries fields apply
session_exercise.session_metric_value/kind → feeds indexed progress
```

## 3. Identity & intake

```sql
CREATE TABLE users (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email            citext UNIQUE NOT NULL,
  password_hash    text NOT NULL,                  -- bcrypt
  display_name     text,
  locale           text NOT NULL DEFAULT 'en',     -- 'en' | 'es'
  role             user_role NOT NULL DEFAULT 'member',
  membership_tier  membership_tier NOT NULL DEFAULT 'classic',
  home_club_id     uuid REFERENCES clubs(id),
  -- denormalized current intake snapshot (history lives in intake_responses):
  autonomy_mode    autonomy_mode NOT NULL DEFAULT 'guided',
  goal             text,                            -- e.g. 'general_fitness','weight_loss','strength'
  experience_level difficulty_level NOT NULL DEFAULT 'beginner',
  days_per_week    smallint,
  cardio_pct       smallint CHECK (cardio_pct BETWEEN 0 AND 100),
  strength_pct     smallint CHECK (strength_pct BETWEEN 0 AND 100),
  status           record_status NOT NULL DEFAULT 'active',
  deleted_at       timestamptz,
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now()
);

-- Versioned intake so re-running the interview keeps history and recommendations are auditable.
CREATE TABLE intake_responses (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       uuid NOT NULL REFERENCES users(id),
  answers       jsonb NOT NULL,                    -- raw interview payload
  recommended_mode autonomy_mode NOT NULL,
  rationale     text,                              -- the "here's why" shown on placement screen
  created_at    timestamptz NOT NULL DEFAULT now()
);
```

## 4. Clubs & equipment

The club model is what makes rotation and swap club-aware. Equipment metadata
(`bar_weight_lb`, `stack_unit`, `stack_map`) is where the Smith-bar and pin-vs-pounds
problems get resolved once, centrally.

```sql
CREATE TABLE clubs (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name        text NOT NULL,
  slug        text UNIQUE NOT NULL,
  address     text,
  lat         numeric(9,6),
  lng         numeric(9,6),
  is_demo     boolean NOT NULL DEFAULT false,
  created_at  timestamptz NOT NULL DEFAULT now()
);

-- Canonical catalog of machine/equipment kinds, club-independent.
CREATE TABLE equipment_types (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name          text NOT NULL,                     -- 'Chest Press (selectorized)'
  category      equipment_category NOT NULL,
  measurement_type measurement_type NOT NULL,
  bar_weight_lb numeric(6,2),                      -- Smith/plate: effective (often NOT 45)
  stack_unit    stack_unit,                        -- selectorized: how the stack is labeled
  stack_map     jsonb,                             -- DEFERRED: optional pin_number -> lb mapping
  nominal_plate_lb numeric(5,2),                   -- optional: ~lb per pin step; lets dial/lever
                                                   --   increments convert to a fractional pin step
                                                   --   without the full stack_map (global default ok)
  notes         text,
  created_at    timestamptz NOT NULL DEFAULT now()
);

-- Availability: which equipment exists at which club. Drives rotation + swap filtering.
CREATE TABLE club_equipment (
  club_id           uuid NOT NULL REFERENCES clubs(id),
  equipment_type_id uuid NOT NULL REFERENCES equipment_types(id),
  quantity          smallint NOT NULL DEFAULT 1,
  is_available      boolean NOT NULL DEFAULT true, -- toggle for "broken/out of service"
  PRIMARY KEY (club_id, equipment_type_id)
);
```

## 5. Exercise library & movement patterns

```sql
CREATE TABLE movement_patterns (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  key           text UNIQUE NOT NULL,              -- 'horizontal_push','vertical_pull','hip_hinge',...
  name          text NOT NULL,
  display_order smallint NOT NULL DEFAULT 0
);

CREATE TABLE exercises (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name               text NOT NULL,
  slug               text UNIQUE NOT NULL,
  measurement_type   measurement_type NOT NULL,    -- source of truth for logging UI
  equipment_type_id  uuid REFERENCES equipment_types(id),
  primary_pattern_id uuid REFERENCES movement_patterns(id),
  secondary_pattern_id uuid REFERENCES movement_patterns(id),
  muscle_groups      jsonb,                         -- ['chest','triceps','front_delts']
  difficulty         difficulty_level NOT NULL DEFAULT 'beginner',
  is_anchor          boolean NOT NULL DEFAULT false, -- core compound that does NOT rotate
  video_url          text,                          -- LINKED (YouTube), never rehosted
  instructions       text,
  is_active          boolean NOT NULL DEFAULT true,
  created_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX ix_exercises_pattern ON exercises(primary_pattern_id);
CREATE INDEX ix_exercises_equipment ON exercises(equipment_type_id);
```

## 6. Programs & rotation

A program is a user's plan; each `program_week` is a generated week; each `program_slot` is
a stable pattern slot filled with the exercise chosen for that week. **Anchor slots keep the
same exercise across weeks; variety slots rotate** (filled by the rotation engine from the
pattern's exercise pool, constrained to the program club's `club_equipment`).

```sql
CREATE TABLE programs (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       uuid NOT NULL REFERENCES users(id),
  name          text,
  club_id       uuid REFERENCES clubs(id),         -- home club the plan is generated against
  autonomy_mode_at_creation autonomy_mode NOT NULL,
  start_date    date,
  status        record_status NOT NULL DEFAULT 'active',
  deleted_at    timestamptz,
  created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE program_weeks (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  program_id   uuid NOT NULL REFERENCES programs(id),
  week_number  smallint NOT NULL,
  start_date   date,
  is_current   boolean NOT NULL DEFAULT false,
  generated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (program_id, week_number)
);

CREATE TABLE program_slots (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  program_week_id uuid NOT NULL REFERENCES program_weeks(id),
  slot_index      smallint NOT NULL,
  pattern_id      uuid NOT NULL REFERENCES movement_patterns(id), -- the STABLE part
  exercise_id     uuid NOT NULL REFERENCES exercises(id),         -- the rotated-in choice
  is_anchor       boolean NOT NULL DEFAULT false,
  prescribed_sets smallint,
  prescribed_reps smallint,
  prescribed_target jsonb,                          -- cardio/circuit targets (duration, level...)
  notes           text,
  UNIQUE (program_week_id, slot_index)
);
```

## 7. Sessions & logging  ← the measurement-type taxonomy

`session_exercises` is one performed exercise in a session (snapshotting its
`measurement_type` and the computed `session_metric`). `set_entries` is **sparse-wide**:
every logged dimension is a nullable column; which ones are required is enforced per
`measurement_type` in Pydantic, not the DB.

```sql
CREATE TABLE sessions (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         uuid NOT NULL REFERENCES users(id),
  program_week_id uuid REFERENCES program_weeks(id),   -- null for ad-hoc
  club_id         uuid NOT NULL REFERENCES clubs(id),  -- current_club (defaults home, overridable)
  session_type    session_type NOT NULL DEFAULT 'standard',
  status          session_status NOT NULL DEFAULT 'planned',
  scheduled_date  date,
  started_at      timestamptz,
  completed_at    timestamptz,
  created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE session_exercises (
  id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id            uuid NOT NULL REFERENCES sessions(id),
  exercise_id           uuid NOT NULL REFERENCES exercises(id),
  source_slot_id        uuid REFERENCES program_slots(id),  -- which slot it came from
  order_index           smallint NOT NULL,
  measurement_type      measurement_type NOT NULL,           -- snapshot
  prescribed            jsonb,                               -- targets carried from the slot
  -- swap tracking (folded in; no separate table needed for the demo):
  was_swapped           boolean NOT NULL DEFAULT false,
  swapped_from_exercise_id uuid REFERENCES exercises(id),
  swap_reason           swap_reason,
  -- denormalized progress metric (computed on completion, §8):
  session_metric_kind   metric_kind NOT NULL DEFAULT 'none',
  session_metric_value  numeric(10,3),
  notes                 text,
  created_at            timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX ix_sx_session  ON session_exercises(session_id);
CREATE INDEX ix_sx_exercise ON session_exercises(exercise_id);

CREATE TABLE set_entries (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  session_exercise_id  uuid NOT NULL REFERENCES session_exercises(id),
  set_number           smallint NOT NULL,
  -- strength dimensions:
  reps                 smallint,
  weight_value         numeric(7,2),
  weight_unit          weight_unit,
  pin_position         smallint,        -- selectorized: track the pin, not fake lbs
  -- incremental adders between pins (magnet / push-in lever / +5/+10 dial):
  micro_load_kind      micro_load_kind NOT NULL DEFAULT 'none',
  added_load_lb        numeric(6,2),    -- when the adder is labeled in lb (e.g. leg-press dial +5/+10)
  micro_load_notches   smallint,        -- when it's an unlabeled stepped adder (lever/magnet count)
  -- cardio dimensions:
  distance_value       numeric(8,3),
  distance_unit        distance_unit,
  duration_seconds     integer,
  level                smallint,
  incline              numeric(4,1),
  speed                numeric(5,2),
  avg_hr               smallint,
  calories             integer,
  -- circuit / time-under-tension:
  tut_seconds          integer,
  -- shared:
  rpe                  numeric(3,1),
  extra                jsonb,           -- overflow for anything not columnized
  created_at           timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX ix_set_entries_parent ON set_entries(session_exercise_id);
```

### 7.1 Which fields apply per `measurement_type`

App-layer (Pydantic) validation matrix — required (R), optional (o), unused (·):

| field            | selectorized | plate_loaded | smith | cardio | circuit | functional | bodyweight |
|------------------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| reps             | R | R | R | · | o | R | R |
| weight_value/unit| · | R | R | · | · | o | · |
| pin_position     | R | · | · | · | · | o | · |
| micro_load_kind / added_load_lb / micro_load_notches | o | · | · | · | · | · | · |
| duration_seconds | · | · | · | R | o | o | o |
| distance/level/incline/speed/avg_hr/calories | · | · | · | R(any) | · | · | · |
| tut_seconds      | · | · | · | · | R | · | · |
| rpe              | o | o | o | o | o | o | o |

## 8. Progress — the indexed model

Two-level progress that survives rotation. On session completion, compute one
`session_metric` per `session_exercise`, then **index every metric to that exercise's own
first session = 100**, making units irrelevant so rotated exercises still roll up.

### 8.1 Per-exercise metric (what `session_metric_kind` records)

| measurement_type | metric_kind   | formula |
|------------------|---------------|---------|
| plate_loaded, smith | `est_1rm`  | Epley: `load * (1 + reps/30)` — `load` resolves true lb incl. `bar_weight_lb` |
| selectorized     | `volume_load` | `effective_step * reps * sets` (honest proxy — `effective_step` isn't lbs; indexing cancels the unit) |
| functional, bodyweight | `volume_load` | `(load or 1) * reps * sets` |
| cardio           | `distance` or `duration` | best of distance / duration / level — feeds the cardio dashboard, **not** the strength trend |
| circuit          | `duration`    | total TUT / completion — consistency-oriented, light progress |

**`effective_step`** folds the incremental adder into the pin so progress made *without*
moving the pin still registers:

```
effective_step = pin_position
               + (added_load_lb / nominal_plate_lb)      -- labeled +5/+10 dial, if both known
               + (micro_load_notches * NOTCH_FRACTION)   -- unlabeled lever/magnet; NOTCH_FRACTION ~0.5
```

Calibration is intentionally loose — because every value is indexed to the exercise's own
baseline, only *consistency* matters (same machine + same adder → same number), not real
pounds. Defaults (`nominal_plate_lb` global fallback, `NOTCH_FRACTION`) live in app config
and can be tuned after real-world use.

**Pin-badge milestone:** the proxy can dip the session a pin jump lands (more pin, fewer
reps), so surface the pin increase as a celebrated milestone ("now on pin 6, up from 5")
alongside the smooth proxy line. The proxy draws the granular curve; the badge turns the
discrete jump into a win instead of a confusing dip.

### 8.2 Indexing

```
indexed_value(exercise, session) = session_metric_value
                                 / first_session_metric_value(exercise, user)
                                 * 100
```

- **Per-exercise chart:** that exercise's `indexed_value` over time (drill-down level).
- **Pattern-trend (hero):** recency-weighted average of `indexed_value` across all
  exercises whose `primary_pattern_id = pattern`, for the user. Continuous across rotation
  because each input is normalized to its own baseline.

### 8.3 Optional materialization

For the demo, compute on read from `session_exercises`. If pattern-trend queries get heavy,
precompute:

```sql
CREATE TABLE exercise_progress_points (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       uuid NOT NULL REFERENCES users(id),
  exercise_id   uuid NOT NULL REFERENCES exercises(id),
  session_id    uuid NOT NULL REFERENCES sessions(id),
  metric_kind   metric_kind NOT NULL,
  metric_value  numeric(10,3) NOT NULL,
  indexed_value numeric(7,2) NOT NULL,           -- vs. this user+exercise first value
  recorded_at   timestamptz NOT NULL,
  UNIQUE (user_id, exercise_id, session_id)
);
CREATE INDEX ix_epp_user_exercise ON exercise_progress_points(user_id, exercise_id, recorded_at);
```

Pattern-trend then aggregates `exercise_progress_points` joined to `exercises.primary_pattern_id`.

## 9. Body metrics

```sql
CREATE TABLE body_metrics (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id      uuid NOT NULL REFERENCES users(id),
  recorded_at  timestamptz NOT NULL DEFAULT now(),
  weight_value numeric(6,2),
  weight_unit  weight_unit,
  body_fat_pct numeric(4,1),
  measurements jsonb,                              -- {'waist_in': 34, 'chest_in': 42, ...}
  notes        text
);
CREATE INDEX ix_body_metrics_user ON body_metrics(user_id, recorded_at);
```

## 10. Nutrition & supplements (marketing surfaces — placeholders)

```sql
CREATE TABLE nutrition_partners (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name         text NOT NULL,
  image_url    text,
  affiliate_url text,
  is_active    boolean NOT NULL DEFAULT true
);

CREATE TABLE meal_suggestions (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  partner_id   uuid REFERENCES nutrition_partners(id),
  day_of_week  smallint CHECK (day_of_week BETWEEN 0 AND 6),  -- ~1 per day
  title        text NOT NULL,
  description  text,
  image_url    text,
  link_url     text,
  tags         jsonb,
  is_active    boolean NOT NULL DEFAULT true
);

CREATE TABLE supplements (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name         text NOT NULL,
  category     text,
  description  text,
  image_url    text,
  link_url     text,
  is_active    boolean NOT NULL DEFAULT true
);
```

> Reminder: nutrition partners are illustrative, not claimed integrations; affiliate links
> need FTC disclosure. No prescriptive calorie targets in this surface.

## 11. Autonomy events & consistency

Consistency is derived from `sessions` (completed count, current streak); cache only if
needed. `autonomy_events` records each invitation/transition for the nudge mechanic.

```sql
CREATE TABLE autonomy_events (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     uuid NOT NULL REFERENCES users(id),
  from_mode   autonomy_mode,
  to_mode     autonomy_mode NOT NULL,
  trigger     text NOT NULL,                       -- 'nudge_consistency' | 'self_declared' | 'admin'
  occurred_at timestamptz NOT NULL DEFAULT now()
);
```

Example consistency read (sessions completed this calendar month):

```sql
SELECT count(*) FROM sessions
WHERE user_id = $1 AND status = 'completed'
  AND completed_at >= date_trunc('month', now());
```

## 12. Soft-delete & admin reversal (house principle: never hard-delete)

- User-facing "delete" sets `status='archived'` / `deleted_at = now()`; rows stay.
- Reversible business actions (e.g., undo a logged session) are performed by an admin and
  recorded so they can be replayed/audited:

```sql
CREATE TABLE admin_transactions (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  admin_id     uuid NOT NULL REFERENCES users(id),
  action       text NOT NULL,                      -- 'archive_session','restore_program',...
  target_table text NOT NULL,
  target_id    uuid NOT NULL,
  before_state jsonb,
  after_state  jsonb,
  created_at   timestamptz NOT NULL DEFAULT now()
);
```

## 13. Indexing summary

- `users(email)` unique; `users(home_club_id)`.
- `club_equipment(club_id, equipment_type_id)` PK already covers club lookups; add
  `(equipment_type_id)` for reverse lookups during swap.
- `exercises(primary_pattern_id)`, `exercises(equipment_type_id)`.
- `session_exercises(session_id)`, `(exercise_id)`.
- `set_entries(session_exercise_id)`.
- `exercise_progress_points(user_id, exercise_id, recorded_at)` if materialized.
- `body_metrics(user_id, recorded_at)`.

## 14. Alembic / migration notes

- One initial migration for enums + core tables; keep `exercise_progress_points` in a
  later migration so you can ship compute-on-read first and add materialization only if
  needed.
- Create `CREATE TYPE` enums in their own upgrade step before tables that reference them;
  Alembic won't auto-detect enum value changes — handle those manually.
- Seed data (clubs, equipment_types, movement_patterns, a starter exercise set, demo
  meal/supplement rows) belongs in a seed script, not migrations.

## 15. Schema decisions

**Resolved (approved):**
- **Selectorized progress unit:** `volume_load` proxy via `effective_step × reps × sets`
  (captures rep progress between pin jumps), **plus** the top-pin increase surfaced as a
  milestone badge. Not top-pin alone.
- **Pin→lb mapping (`stack_map`):** deferred. The app lives on pin numbers; `stack_map` is
  an additive polish layer only if real users ask to see pounds. Increment math uses the
  lighter `nominal_plate_lb` (or a global default) instead.
- **Incremental adders:** captured per set (`micro_load_kind` + `added_load_lb` /
  `micro_load_notches`) and folded into `effective_step`; calibration loose since indexing
  cancels absolute scale.

**Still open:**
- **set_entries sparse-wide vs. JSONB payload:** going sparse-wide for queryability; the
  `extra` JSONB column is the escape hatch. Reconsider only if the column count balloons.
- **Cardio in pattern-trend:** intentionally excluded (own dashboard). Confirm that's the
  desired UX before wiring charts.
- **`NOTCH_FRACTION` / `nominal_plate_lb` defaults:** placeholder values; tune after
  real-world logging.
