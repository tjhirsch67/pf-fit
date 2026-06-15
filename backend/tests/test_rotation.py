"""Unit tests for the rotation + swap engine (rotation.py). Pure stdlib — no deps."""

import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import rotation  # noqa: E402


def ex(id, equipment_type_id=None, is_anchor=False, slug=None):
    return SimpleNamespace(id=id, equipment_type_id=equipment_type_id, is_anchor=is_anchor, slug=slug or id)


def ce(equipment_type_id, is_available=True):
    return SimpleNamespace(equipment_type_id=equipment_type_id, is_available=is_available)


# ─── availability / club filtering ──────────────────────────────────────────────

def test_available_equipment_ids_excludes_out_of_service():
    rows = [ce("chest"), ce("row"), ce("legpress", is_available=False)]
    assert rotation.available_equipment_ids(rows) == {"chest", "row"}


def test_bodyweight_always_available():
    plank = ex("plank", equipment_type_id=None)
    assert rotation.exercise_available(plank, set()) is True


def test_machine_filtered_when_club_lacks_it():
    legpress = ex("legpress", equipment_type_id="legpress_eq")
    assert rotation.exercise_available(legpress, {"chest_eq"}) is False
    assert rotation.exercise_available(legpress, {"legpress_eq"}) is True


# ─── LRU variety selection ──────────────────────────────────────────────────────

def test_variety_prefers_least_recently_used():
    pool = [ex("a", "eq"), ex("b", "eq"), ex("c", "eq")]
    avail = {"eq"}
    # 'a' and 'b' used recently (a most recent); 'c' never used -> should be chosen.
    choice = rotation.choose_variety_exercise(pool, avail, history=["a", "b"])
    assert choice.id == "c", choice.id


def test_variety_excludes_anchor_and_respects_availability():
    pool = [ex("anchor", "eq1", is_anchor=True), ex("v1", "eq2"), ex("v2", "eq3")]
    # Club only has eq1 + eq2; anchor excluded -> only v1 qualifies.
    choice = rotation.choose_variety_exercise(pool, {"eq1", "eq2"}, history=[], anchor_id="anchor")
    assert choice.id == "v1", choice.id


def test_variety_returns_none_when_nothing_available():
    pool = [ex("v1", "eq_missing")]
    assert rotation.choose_variety_exercise(pool, {"other"}, history=[]) is None


# ─── same-pattern swap ──────────────────────────────────────────────────────────

def test_swap_offers_same_pattern_alternatives_at_club():
    pool = [ex("chest_press", "chest_eq"), ex("smith_bench", "smith_eq"), ex("cable_press", "cable_eq")]
    # Travel club lacks the smith; swapping away from chest_press should offer only cable_press.
    alts = rotation.same_pattern_alternatives("chest_press", pool, {"chest_eq", "cable_eq"})
    assert [a.id for a in alts] == ["cable_press"], [a.id for a in alts]


# ─── whole-week build: anchors fixed, variety rotates, club-constrained ──────────

def test_build_week_anchor_fixed_variety_rotates():
    pools = {
        "push": [ex("chest_press", "chest_eq", is_anchor=True), ex("smith_bench", "smith_eq"), ex("cable_press", "cable_eq")],
        "pull": [ex("lat_pulldown", "lat_eq", is_anchor=True), ex("assisted_pullup", "pullup_eq")],
    }
    specs = [
        {"slot_index": 0, "pattern_id": "push", "is_anchor": True, "anchor_exercise_id": "chest_press"},
        {"slot_index": 1, "pattern_id": "push", "is_anchor": False},
        {"slot_index": 2, "pattern_id": "pull", "is_anchor": True, "anchor_exercise_id": "lat_pulldown"},
    ]
    avail = {"chest_eq", "smith_eq", "cable_eq", "lat_eq", "pullup_eq"}

    wk1 = rotation.build_program_week(specs, pools, avail, history_by_pattern={})
    by_slot = {r["slot_index"]: r for r in wk1}
    assert by_slot[0]["exercise_id"] == "chest_press"   # anchor fixed
    assert by_slot[2]["exercise_id"] == "lat_pulldown"  # anchor fixed
    assert by_slot[1]["exercise_id"] in ("smith_bench", "cable_press")  # variety chosen

    # Next week: feed history; variety slot should pick the *other* variety exercise.
    wk1_variety = by_slot[1]["exercise_id"]
    wk2 = rotation.build_program_week(specs, pools, avail, history_by_pattern={"push": [wk1_variety, "chest_press"]})
    wk2_variety = {r["slot_index"]: r for r in wk2}[1]["exercise_id"]
    assert wk2_variety != wk1_variety, (wk1_variety, wk2_variety)


def test_build_week_anchor_falls_back_when_club_missing_it():
    pools = {"push": [ex("chest_press", "chest_eq", is_anchor=True), ex("cable_press", "cable_eq")]}
    specs = [{"slot_index": 0, "pattern_id": "push", "is_anchor": True, "anchor_exercise_id": "chest_press"}]
    # Travel club lacks the anchor's machine -> falls back to the same-pattern alternative.
    wk = rotation.build_program_week(specs, pools, {"cable_eq"}, history_by_pattern={})
    assert wk[0]["exercise_id"] == "cable_press", wk[0]
    assert wk[0]["unfilled"] is False


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failures = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"  FAIL  {t.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            failures += 1
            print(f"  ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
