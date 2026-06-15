"""Club-aware rotation + swap engine (CLAUDE.md §6.2/§6.3/§6.5, Schema.md §6).

Programs are built from stable **pattern slots**. *Anchor* slots (core compounds) hold the
same exercise every week; *variety* slots rotate weekly to expose the member to different
machines — but always **constrained to the equipment their current club actually has**.

Rotation deliberately breaks per-exercise continuity (that's why progress is tracked at the
pattern level — see progress.py). The **swap** affordance handles the in-the-moment cases
(broken machine, occupied, or a different club on this visit) by offering *same-pattern*
alternatives filtered to the current club, so a swap never punches a hole in the trend.

Pure logic, stdlib only: callers gather exercises / club equipment from the DB and hand
lightweight rows (anything exposing the duck-typed attributes below) to these functions.
Exercise-like inputs expose: ``id``, ``equipment_type_id``, ``is_anchor``, and a stable
ordering key via ``slug`` (falls back to ``name`` then ``id``).
"""

from typing import Dict, Iterable, List, Optional, Sequence, Set


# ─── Availability ───────────────────────────────────────────────────────────────

def available_equipment_ids(club_equipment_rows: Iterable) -> Set:
    """Set of equipment_type_ids that exist *and* are in service at a club."""
    return {
        r.equipment_type_id
        for r in club_equipment_rows
        if getattr(r, "is_available", True) and getattr(r, "equipment_type_id", None) is not None
    }


def exercise_available(exercise, available_ids: Set) -> bool:
    """An exercise is doable at a club if its equipment is available — or if it needs no
    equipment (bodyweight / some functional work has a null ``equipment_type_id``)."""
    eq = getattr(exercise, "equipment_type_id", None)
    return eq is None or eq in available_ids


def _sort_key(exercise):
    return getattr(exercise, "slug", None) or getattr(exercise, "name", None) or str(getattr(exercise, "id", ""))


def _ex_id(exercise):
    return getattr(exercise, "id", exercise)


# ─── Pools ────────────────────────────────────────────────────────────────────

def candidates_for_pattern(
    pool: Sequence,
    available_ids: Set,
    *,
    include_anchors: bool = False,
    exclude_ids: Iterable = (),
) -> List:
    """Club-available exercises for a pattern, stably ordered. Variety selection excludes
    anchors by default (they own their own slots)."""
    excluded = set(exclude_ids)
    out = [
        ex for ex in pool
        if exercise_available(ex, available_ids)
        and _ex_id(ex) not in excluded
        and (include_anchors or not getattr(ex, "is_anchor", False))
    ]
    return sorted(out, key=_sort_key)


# ─── Variety selection (least-recently-used) ────────────────────────────────────

def choose_variety_exercise(
    pool: Sequence,
    available_ids: Set,
    history: Sequence = (),
    *,
    anchor_id=None,
    exclude_ids: Iterable = (),
):
    """Pick the variety exercise for a slot: the club-available candidate used least recently
    (longest since last appearance in ``history``, which is most-recent-first), breaking ties
    by stable order. This maximizes variety while staying deterministic.

    Returns an exercise from ``pool`` or ``None`` if nothing is available.
    """
    exclude = set(exclude_ids)
    if anchor_id is not None:
        exclude.add(anchor_id)
    candidates = candidates_for_pattern(pool, available_ids, exclude_ids=exclude)
    if not candidates:
        return None

    # Recency rank: index in history (0 = most recent). Not in history -> never used -> best.
    recency = {ex_id: i for i, ex_id in enumerate(history)}
    NEVER = len(history) + 1

    def lru_key(ex):
        # Higher "staleness" first, then stable order.
        return (-recency.get(_ex_id(ex), NEVER), _sort_key(ex))

    return sorted(candidates, key=lru_key)[0]


# ─── Same-pattern swap ──────────────────────────────────────────────────────────

def same_pattern_alternatives(
    current_exercise_id,
    pool: Sequence,
    available_ids: Set,
    *,
    exclude_ids: Iterable = (),
    include_anchors: bool = True,
) -> List:
    """Same-pattern, club-available alternatives for the unavailable/swap affordance,
    excluding the current exercise (and anything else already in the session)."""
    exclude = set(exclude_ids)
    exclude.add(current_exercise_id)
    return candidates_for_pattern(
        pool, available_ids, include_anchors=include_anchors, exclude_ids=exclude
    )


# ─── Whole-week generation ──────────────────────────────────────────────────────

def build_program_week(
    slot_specs: Sequence[dict],
    pools_by_pattern: Dict,
    available_ids: Set,
    history_by_pattern: Optional[Dict[object, List]] = None,
) -> List[dict]:
    """Fill a week's slots: anchors keep their fixed exercise; variety slots rotate (LRU)
    from their pattern pool, constrained to the club's equipment.

    ``slot_specs`` items: ``{slot_index, pattern_id, is_anchor, anchor_exercise_id,
    prescribed_sets, prescribed_reps, prescribed_target, notes}``.
    Returns one resolved dict per slot, carrying the chosen ``exercise_id`` (or ``None`` with
    ``unfilled=True`` if the club genuinely has nothing for that pattern).
    """
    history_by_pattern = history_by_pattern or {}
    chosen_this_week: Set = set()  # avoid duplicating an exercise across two slots in one week
    out: List[dict] = []

    for spec in sorted(slot_specs, key=lambda s: s.get("slot_index", 0)):
        pattern_id = spec.get("pattern_id")
        pool = pools_by_pattern.get(pattern_id, [])
        is_anchor = spec.get("is_anchor", False)
        resolved = {
            "slot_index": spec.get("slot_index"),
            "pattern_id": pattern_id,
            "is_anchor": is_anchor,
            "prescribed_sets": spec.get("prescribed_sets"),
            "prescribed_reps": spec.get("prescribed_reps"),
            "prescribed_target": spec.get("prescribed_target"),
            "notes": spec.get("notes"),
            "exercise_id": None,
            "unfilled": False,
        }

        if is_anchor and spec.get("anchor_exercise_id") is not None:
            anchor_id = spec["anchor_exercise_id"]
            anchor_ex = next((ex for ex in pool if _ex_id(ex) == anchor_id), None)
            if anchor_ex is not None and exercise_available(anchor_ex, available_ids):
                resolved["exercise_id"] = anchor_id
                chosen_this_week.add(anchor_id)
                out.append(resolved)
                continue
            # Anchor machine missing at this club — fall back to a same-pattern alternative.
            alt = choose_variety_exercise(
                pool, available_ids, history_by_pattern.get(pattern_id, []),
                exclude_ids=chosen_this_week,
            )
            resolved["exercise_id"] = _ex_id(alt) if alt is not None else None
            resolved["unfilled"] = alt is None
            if alt is not None:
                chosen_this_week.add(_ex_id(alt))
            out.append(resolved)
            continue

        # Variety slot.
        choice = choose_variety_exercise(
            pool, available_ids, history_by_pattern.get(pattern_id, []),
            exclude_ids=chosen_this_week,
        )
        resolved["exercise_id"] = _ex_id(choice) if choice is not None else None
        resolved["unfilled"] = choice is None
        if choice is not None:
            chosen_this_week.add(_ex_id(choice))
        out.append(resolved)

    return out
