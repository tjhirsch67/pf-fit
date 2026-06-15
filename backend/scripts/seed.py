"""Idempotent seed script (Seed.md).

Two data classes, cleanly separable:
  - Reference data (real, required) — always seeds. Upserts by natural key, safe to re-run.
  - Demo data (fabricated) — only with ``--demo``. One flagged user with 8 weeks of history
    so every progress view looks alive. ``--wipe-demo`` removes it.

Usage (from backend/):
    python scripts/seed.py            # reference only
    python scripts/seed.py --demo     # + demo user
    python scripts/seed.py --wipe-demo

Seeded sessions store ``session_metric_kind``/``value`` computed with the *same* progress
engine the live app uses, so seeded and real data are indistinguishable to progress queries.
The demo chest-press curve reproduces Seed.md §2.3 exactly.
"""

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import auth  # noqa: E402
import models  # noqa: E402
import progress  # noqa: E402
from database import SessionLocal  # noqa: E402
from routers.programs import create_program_for_user  # noqa: E402

DEMO_EMAIL = "demo@pfcoach.app"


# ─── upsert helper ──────────────────────────────────────────────────────────

def get_or_create(db, model, defaults=None, **key):
    obj = db.query(model).filter_by(**key).first()
    if obj:
        return obj, False
    params = dict(key)
    params.update(defaults or {})
    obj = model(**params)
    db.add(obj)
    db.flush()
    return obj, True


# ─── reference data ─────────────────────────────────────────────────────────

PATTERNS = [
    ("horizontal_push", "Horizontal Push", 1),
    ("vertical_pull", "Vertical Pull", 2),
    ("horizontal_pull", "Horizontal Pull", 3),
    ("hip_hinge", "Hip Hinge", 4),
    ("knee_dominant", "Knee-Dominant", 5),
    ("core_carry", "Core / Carry", 6),
]

# name, category, measurement_type, bar_weight_lb, stack_unit, nominal_plate_lb
EQUIPMENT = [
    ("Treadmill", "cardio", "cardio", None, None, None),
    ("Elliptical", "cardio", "cardio", None, None, None),
    ("Upright Bike", "cardio", "cardio", None, None, None),
    ("Stair Climber", "cardio", "cardio", None, None, None),
    ("Chest Press", "strength", "selectorized", None, "pin_number", 10),
    ("Shoulder Press", "strength", "selectorized", None, "pin_number", 10),
    ("Lat Pulldown", "strength", "selectorized", None, "pin_number", 10),
    ("Seated Row", "strength", "selectorized", None, "pin_number", 10),
    ("Leg Press", "strength", "selectorized", None, "pin_number", 12),
    ("Leg Extension", "strength", "selectorized", None, "pin_number", 10),
    ("Seated Leg Curl", "strength", "selectorized", None, "pin_number", 10),
    ("Assisted Pull-up", "strength", "selectorized", None, "pin_number", 10),
    ("Pec Deck", "strength", "selectorized", None, "pin_number", 10),
    ("Abdominal Crunch", "strength", "selectorized", None, "pin_number", 10),
    ("Back Extension", "strength", "selectorized", None, "pin_number", 10),
    ("Smith Machine", "strength", "smith", 15, None, None),
    ("Cable Tower", "functional", "functional", None, None, None),
    ("Express Circuit", "circuit", "circuit", None, None, None),
]

# name, slug, measurement_type, equipment_name|None, pattern_key|None, muscle_groups,
# difficulty, is_anchor, video_query
EXERCISES = [
    ("Chest Press (Machine)", "chest-press-machine", "selectorized", "Chest Press", "horizontal_push",
     ["chest", "triceps", "front_delts"], "beginner", True),
    ("Smith Bench Press", "smith-bench-press", "smith", "Smith Machine", "horizontal_push",
     ["chest", "triceps"], "intermediate", False),
    ("Cable Chest Press", "cable-chest-press", "functional", "Cable Tower", "horizontal_push",
     ["chest", "triceps"], "beginner", False),
    ("Push-up", "push-up", "bodyweight", None, "horizontal_push", ["chest", "triceps", "core"], "beginner", False),

    ("Lat Pulldown", "lat-pulldown", "selectorized", "Lat Pulldown", "vertical_pull",
     ["lats", "biceps"], "beginner", True),
    ("Assisted Pull-up", "assisted-pull-up", "selectorized", "Assisted Pull-up", "vertical_pull",
     ["lats", "biceps"], "intermediate", False),
    ("Straight-Arm Pulldown", "straight-arm-pulldown", "functional", "Cable Tower", "vertical_pull",
     ["lats"], "beginner", False),

    ("Seated Row", "seated-row", "selectorized", "Seated Row", "horizontal_pull",
     ["mid_back", "biceps"], "beginner", True),
    ("Cable Row", "cable-row", "functional", "Cable Tower", "horizontal_pull",
     ["mid_back", "biceps"], "beginner", False),
    ("Reverse Pec Deck", "reverse-pec-deck", "selectorized", "Pec Deck", "horizontal_pull",
     ["rear_delts", "mid_back"], "beginner", False),

    ("Back Extension", "back-extension", "selectorized", "Back Extension", "hip_hinge",
     ["glutes", "lower_back", "hamstrings"], "beginner", True),
    ("Smith RDL", "smith-rdl", "smith", "Smith Machine", "hip_hinge",
     ["hamstrings", "glutes"], "intermediate", False),
    ("Cable Pull-through", "cable-pull-through", "functional", "Cable Tower", "hip_hinge",
     ["glutes", "hamstrings"], "beginner", False),

    ("Leg Press", "leg-press", "selectorized", "Leg Press", "knee_dominant",
     ["quads", "glutes"], "beginner", True),
    ("Leg Extension", "leg-extension", "selectorized", "Leg Extension", "knee_dominant",
     ["quads"], "beginner", False),
    ("Smith Squat", "smith-squat", "smith", "Smith Machine", "knee_dominant",
     ["quads", "glutes"], "intermediate", False),

    ("Abdominal Crunch (Machine)", "ab-crunch-machine", "selectorized", "Abdominal Crunch", "core_carry",
     ["abs"], "beginner", True),
    ("Cable Woodchop", "cable-woodchop", "functional", "Cable Tower", "core_carry",
     ["obliques", "core"], "beginner", False),
    ("Plank", "plank", "bodyweight", None, "core_carry", ["core"], "beginner", False),

    # Cardio (no pattern — fuels the cardio dashboard, not the strength trend).
    ("Treadmill Walk/Run", "treadmill", "cardio", "Treadmill", None, ["cardio"], "beginner", False),
    ("Elliptical", "elliptical", "cardio", "Elliptical", None, ["cardio"], "beginner", False),

    # Express Circuit stations (circuit — the Guided on-ramp).
    ("Circuit — Chest Press", "circuit-chest", "circuit", "Express Circuit", None, ["chest"], "beginner", False),
    ("Circuit — Leg Press", "circuit-legs", "circuit", "Express Circuit", None, ["quads"], "beginner", False),
    ("Circuit — Lat Pulldown", "circuit-back", "circuit", "Express Circuit", None, ["lats"], "beginner", False),
    ("Circuit — Shoulder Press", "circuit-shoulders", "circuit", "Express Circuit", None, ["delts"], "beginner", False),
    ("Circuit — Ab Crunch", "circuit-core", "circuit", "Express Circuit", None, ["abs"], "beginner", False),
]

NUTRITION_PARTNERS = [
    ("FreshFuel Kits", "https://example.com/freshfuel"),
    ("GreenCrate Meals", "https://example.com/greencrate"),
]

MEALS = [
    (0, "Overnight oats with berries", "Quick high-fiber breakfast to start the week."),
    (1, "Grilled chicken power bowl", "Lean protein, brown rice, and roasted veg."),
    (2, "Salmon & sweet potato", "Omega-3s and slow carbs for recovery."),
    (3, "Turkey chili", "Batch-friendly, protein-dense comfort food."),
    (4, "Greek yogurt & nut parfait", "Protein-forward snack or light dinner."),
    (5, "Veggie stir-fry with tofu", "Plant-based, colorful, and filling."),
    (6, "Egg-white veggie scramble", "Light, protein-rich weekend brunch."),
]

SUPPLEMENTS = [
    ("Whey Protein", "protein", "Convenient post-workout protein. ~25g per scoop."),
    ("Creatine Monohydrate", "performance", "5g daily; one of the most well-studied supplements."),
    ("Multivitamin", "general", "Daily micronutrient insurance."),
    ("Pre-Workout", "performance", "Caffeine + beta-alanine for training energy."),
    ("Omega-3 Fish Oil", "general", "EPA/DHA for recovery and general health."),
    ("Vitamin D3", "general", "Supports bone health; useful in low-sun months."),
]


def _yt(name):
    return "https://www.youtube.com/results?search_query=" + name.replace(" ", "+") + "+how+to"


def seed_reference(db):
    print("Seeding reference data...")

    home, _ = get_or_create(db, models.Club, {"name": "PF — Home Club", "is_demo": False}, slug="home-club")
    alt, _ = get_or_create(db, models.Club, {"name": "PF — Travel Club", "is_demo": False}, slug="alt-club")

    patterns = {}
    for key, name, order in PATTERNS:
        p, _ = get_or_create(db, models.MovementPattern, {"name": name, "display_order": order}, key=key)
        patterns[key] = p

    equipment = {}
    for name, cat, mt, bar, su, nom in EQUIPMENT:
        e, _ = get_or_create(
            db, models.EquipmentType,
            {"category": cat, "measurement_type": mt, "bar_weight_lb": bar,
             "stack_unit": su, "nominal_plate_lb": nom},
            name=name,
        )
        equipment[name] = e

    exercises = {}
    for name, slug, mt, eq_name, pat_key, muscles, diff, anchor in EXERCISES:
        ex, _ = get_or_create(
            db, models.Exercise,
            {
                "name": name,
                "measurement_type": mt,
                "equipment_type_id": equipment[eq_name].id if eq_name else None,
                "primary_pattern_id": patterns[pat_key].id if pat_key else None,
                "muscle_groups": muscles,
                "difficulty": diff,
                "is_anchor": anchor,
                "video_url": _yt(name),
                "instructions": f"Set up on the {eq_name or 'floor'}, move through a full range of motion, and control the weight.",
            },
            slug=slug,
        )
        exercises[slug] = ex

    # Club equipment: home has everything; travel club is missing the Smith + Leg Extension
    # (forces a swap to demonstrate the same-pattern affordance).
    alt_missing = {"Smith Machine", "Leg Extension"}
    for name, e in equipment.items():
        get_or_create(db, models.ClubEquipment, {"quantity": 1, "is_available": True},
                      club_id=home.id, equipment_type_id=e.id)
        get_or_create(db, models.ClubEquipment,
                      {"quantity": 1, "is_available": name not in alt_missing},
                      club_id=alt.id, equipment_type_id=e.id)

    # Nutrition surfaces.
    partners = {}
    for name, url in NUTRITION_PARTNERS:
        p, _ = get_or_create(db, models.NutritionPartner, {"affiliate_url": url}, name=name)
        partners[name] = p
    default_partner = partners["FreshFuel Kits"]
    for dow, title, desc in MEALS:
        get_or_create(db, models.MealSuggestion,
                      {"description": desc, "partner_id": default_partner.id,
                       "link_url": "https://example.com/recipe", "is_active": True},
                      title=title)
    for name, cat, desc in SUPPLEMENTS:
        get_or_create(db, models.Supplement,
                      {"category": cat, "description": desc,
                       "link_url": "https://www.amazon.com/s?k=" + name.replace(" ", "+"),
                       "is_active": True},
                      name=name)

    db.commit()
    print(f"  clubs: home={home.slug}, alt={alt.slug}")
    print(f"  patterns: {len(patterns)}  equipment: {len(equipment)}  exercises: {len(exercises)}")
    return home, alt


# ─── demo data ─────────────────────────────────────────────────────────────

def wipe_demo(db):
    user = db.query(models.User).filter(models.User.email == DEMO_EMAIL).first()
    if not user:
        return False

    session_ids = [s.id for s in db.query(models.Session).filter(models.Session.user_id == user.id).all()]
    if session_ids:
        sx_ids = [
            sx.id for sx in db.query(models.SessionExercise)
            .filter(models.SessionExercise.session_id.in_(session_ids)).all()
        ]
        if sx_ids:
            db.query(models.SetEntry).filter(models.SetEntry.session_exercise_id.in_(sx_ids)).delete(synchronize_session=False)
            db.query(models.SessionExercise).filter(models.SessionExercise.id.in_(sx_ids)).delete(synchronize_session=False)
        db.query(models.Session).filter(models.Session.id.in_(session_ids)).delete(synchronize_session=False)

    program_ids = [p.id for p in db.query(models.Program).filter(models.Program.user_id == user.id).all()]
    if program_ids:
        week_ids = [
            w.id for w in db.query(models.ProgramWeek)
            .filter(models.ProgramWeek.program_id.in_(program_ids)).all()
        ]
        if week_ids:
            db.query(models.ProgramSlot).filter(models.ProgramSlot.program_week_id.in_(week_ids)).delete(synchronize_session=False)
            db.query(models.ProgramWeek).filter(models.ProgramWeek.id.in_(week_ids)).delete(synchronize_session=False)
        db.query(models.Program).filter(models.Program.id.in_(program_ids)).delete(synchronize_session=False)

    db.query(models.IntakeResponse).filter(models.IntakeResponse.user_id == user.id).delete(synchronize_session=False)
    db.query(models.AutonomyEvent).filter(models.AutonomyEvent.user_id == user.id).delete(synchronize_session=False)
    db.query(models.BodyMetric).filter(models.BodyMetric.user_id == user.id).delete(synchronize_session=False)
    db.query(models.User).filter(models.User.id == user.id).delete(synchronize_session=False)
    db.commit()
    return True


# Per-standard-week shape (Seed.md §2.3), applied to selectorized exercises relative to a
# per-exercise base pin: reps climb, then a pin jump (proxy dips, pin-badge fires), rebuild.
SELECTORIZED_PLAN = [(0, 8), (0, 10), (0, 12), (1, 8), (1, 10), (1, 12)]  # (pin_delta, reps)


def _sets_for(exercise, equipment, week_i):
    """Generate set_entries dicts for one exercise in standard week index 0..5."""
    mt = exercise.measurement_type.value if hasattr(exercise.measurement_type, "value") else exercise.measurement_type
    if mt == "selectorized":
        base = {"chest-press-machine": 5, "lat-pulldown": 6, "seated-row": 7, "leg-press": 8,
                "back-extension": 4, "ab-crunch-machine": 5, "leg-extension": 6,
                "assisted-pull-up": 5, "reverse-pec-deck": 5}.get(exercise.slug, 5)
        delta, reps = SELECTORIZED_PLAN[week_i]
        pin = base + delta
        sets = [{"reps": reps, "pin_position": pin} for _ in range(3)]
        if exercise.slug == "leg-press" and week_i >= 3:  # incremental-adder example
            sets[0]["micro_load_kind"] = "dial"
            sets[0]["added_load_lb"] = 10.0
        return sets
    if mt in ("smith", "plate_loaded"):
        wt = 65 + week_i * 5
        reps = [8, 10, 12, 8, 10, 12][week_i]
        return [{"reps": reps, "weight_value": float(wt), "weight_unit": "lb"} for _ in range(3)]
    if mt == "functional":
        return [{"reps": 10 + week_i, "weight_value": 30.0 + week_i * 5, "weight_unit": "lb"} for _ in range(3)]
    if mt == "bodyweight":
        return [{"reps": 10 + week_i * 2} for _ in range(3)]
    return [{"reps": 10}]


def _make_session(db, user, club_id, session_type, completed_at, exercise_set_specs, swap_index=None):
    """Create a completed session with set_entries and computed per-exercise metrics."""
    s = models.Session(
        user_id=user.id, club_id=club_id, session_type=session_type,
        status=models.SessionStatus.completed.value,
        started_at=completed_at - timedelta(minutes=40), completed_at=completed_at,
        scheduled_date=completed_at.date(),
    )
    db.add(s)
    db.flush()
    for order, (exercise, equipment, sets) in enumerate(exercise_set_specs):
        sx = models.SessionExercise(
            session_id=s.id, exercise_id=exercise.id, order_index=order,
            measurement_type=(exercise.measurement_type.value if hasattr(exercise.measurement_type, "value") else exercise.measurement_type),
        )
        if swap_index is not None and order == swap_index:
            sx.was_swapped = True
            sx.swapped_from_exercise_id = exercise.id
            sx.swap_reason = models.SwapReason.other_club.value
        db.add(sx)
        db.flush()
        for i, sd in enumerate(sets, start=1):
            db.add(models.SetEntry(session_exercise_id=sx.id, set_number=i, **sd))
        db.flush()
        kind, value = progress.compute_session_metric(sx.measurement_type, sx.set_entries, equipment)
        sx.session_metric_kind = kind.value
        sx.session_metric_value = value
    return s


def seed_demo(db, home, alt):
    print("Seeding demo user...")
    wipe_demo(db)

    user = models.User(
        email=DEMO_EMAIL,
        password_hash=auth.hash_password("demo1234"),
        display_name="Alex Rivera (Demo)",
        locale="en",
        home_club_id=home.id,
        autonomy_mode=models.AutonomyMode.coached.value,  # promoted partway (event below)
        goal="general_fitness",
        experience_level=models.DifficultyLevel.beginner.value,
        days_per_week=3,
        cardio_pct=40,
        strength_pct=60,
    )
    db.add(user)
    db.flush()

    db.add(models.IntakeResponse(
        user_id=user.id,
        answers={"goal": "general fitness", "experience": "beginner", "days_per_week": 3,
                 "confidence": "nervous", "cardio_vs_strength": "balanced"},
        recommended_mode=models.AutonomyMode.guided.value,
        rationale="You're brand new and a little nervous — let's keep it simple. We'll start "
                  "you on the 30-minute Express Circuit so every step is laid out, then hand "
                  "you more control as your confidence grows.",
    ))

    base = datetime.now(timezone.utc).replace(hour=18, minute=0, second=0, microsecond=0) - timedelta(weeks=8)

    # Program (8 weeks) generated against the home club.
    program = create_program_for_user(db, user, home.id, weeks=8, name="Alex's Program")

    # Look up exercises/equipment for hand-built sessions.
    ex = {e.slug: e for e in db.query(models.Exercise).all()}
    eq_by_id = {e.id: e for e in db.query(models.EquipmentType).all()}
    treadmill = ex["treadmill"]
    circuit_stations = [e for e in ex.values() if (e.measurement_type.value if hasattr(e.measurement_type, "value") else e.measurement_type) == "circuit"]

    def eq_for(exercise):
        return eq_by_id.get(exercise.equipment_type_id) if exercise.equipment_type_id else None

    # Weeks 1–2: Express Circuit (Guided on-ramp), 3 sessions each.
    for wk in range(2):
        for d, day_off in enumerate((0, 2, 4)):
            when = base + timedelta(weeks=wk, days=day_off)
            specs = [(st, None, [{"tut_seconds": 60}]) for st in circuit_stations]
            specs.append((treadmill, eq_for(treadmill), [{"distance_value": 1.0, "distance_unit": "mi",
                                                          "duration_seconds": 1200, "avg_hr": 138}]))
            _make_session(db, user, home.id, models.SessionType.express_circuit.value, when, specs)

    # Autonomy promotion guided -> coached at the start of week 3.
    db.add(models.AutonomyEvent(
        user_id=user.id, from_mode=models.AutonomyMode.guided.value,
        to_mode=models.AutonomyMode.coached.value, trigger="nudge_consistency",
        occurred_at=base + timedelta(weeks=2),
    ))

    # Weeks 3–8: standard sessions from the generated program weeks, 3 sessions/week.
    weeks_sorted = sorted(program.weeks, key=lambda w: w.week_number)
    for week_i in range(6):  # program weeks 3..8
        pw = weeks_sorted[week_i + 2]
        slot_exercises = [ex_by_id for ex_by_id in
                          [db.query(models.Exercise).get(slot.exercise_id) for slot in pw.slots] if ex_by_id]
        for d, day_off in enumerate((0, 2, 4)):
            when = base + timedelta(weeks=week_i + 2, days=day_off)
            specs = []
            for exercise in slot_exercises:
                specs.append((exercise, eq_for(exercise), _sets_for(exercise, eq_for(exercise), week_i)))
            # One cardio entry per session.
            dist = 1.0 + 0.1 * week_i
            specs.append((treadmill, eq_for(treadmill),
                          [{"distance_value": round(dist, 2), "distance_unit": "mi",
                            "duration_seconds": 1200, "avg_hr": 142}]))
            # Week 6, first session: at the travel club with one same-pattern swap.
            club_id = alt.id if (week_i == 3 and d == 0) else home.id
            swap_index = 1 if (week_i == 3 and d == 0 and len(specs) > 1) else None
            _make_session(db, user, club_id, models.SessionType.standard.value, when, specs, swap_index=swap_index)

    # Body metrics: weekly weigh-ins trending gently down with realistic wobble.
    weights = [198, 197, 197, 195, 194, 194, 193, 192]
    waists = [36.0, 35.8, 35.8, 35.5, 35.2, 35.2, 35.0, 34.8]
    for wk in range(8):
        db.add(models.BodyMetric(
            user_id=user.id,
            recorded_at=base + timedelta(weeks=wk),
            weight_value=float(weights[wk]), weight_unit="lb",
            measurements={"waist_in": waists[wk]},
        ))

    db.commit()
    n_sessions = db.query(models.Session).filter(models.Session.user_id == user.id).count()
    print(f"  demo user: {DEMO_EMAIL} (password: demo1234)")
    print(f"  program weeks: {len(program.weeks)}  completed sessions: {n_sessions}")


def main():
    parser = argparse.ArgumentParser(description="PF Coach seed script")
    parser.add_argument("--demo", action="store_true", help="also seed the fabricated demo user")
    parser.add_argument("--wipe-demo", action="store_true", help="remove demo data and exit")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.wipe_demo:
            removed = wipe_demo(db)
            print("Demo data removed." if removed else "No demo user found.")
            return
        home, alt = seed_reference(db)
        if args.demo:
            seed_demo(db, home, alt)
        print("Seed complete.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
