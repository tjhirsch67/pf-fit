"""Unit tests for the indexed-progress engine (progress.py).

Pure logic — needs only ``pydantic-settings`` (via config) + stdlib. Runs under pytest, or
standalone: ``python tests/test_progress.py`` prints a summary and exits non-zero on failure.

The selectorized case reproduces Seed.md §2.3's chest-press curve exactly, which is the
canonical proof that the proxy + indexing + pin-badge mechanics behave as designed.
"""

import os
import sys
from datetime import datetime, timedelta
from types import SimpleNamespace

# Allow `python tests/test_progress.py` from the backend dir.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from enums import MeasurementType, MetricKind, WeightUnit, DistanceUnit  # noqa: E402
import progress  # noqa: E402


def _set(**kw):
    """A stand-in for a set_entries row (compute_session_metric uses getattr)."""
    base = dict(
        reps=None, weight_value=None, weight_unit=None, pin_position=None,
        added_load_lb=None, micro_load_notches=None, distance_value=None,
        distance_unit=None, duration_seconds=None, tut_seconds=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


# ─── selectorized: the Seed.md §2.3 chest-press curve ───────────────────────────

def test_selectorized_curve_matches_seed_doc():
    # (pin, reps) per week, 3 sets each — straight from Seed.md §2.3.
    weeks = [(5, 8), (5, 10), (5, 12), (6, 8), (6, 10), (6, 12)]
    expected_proxy = [120, 150, 180, 144, 180, 216]
    expected_indexed = [100, 125, 150, 120, 150, 180]

    base = datetime(2026, 3, 1)
    points = []
    for i, (pin, reps) in enumerate(weeks):
        sets = [_set(reps=reps, pin_position=pin) for _ in range(3)]
        kind, value = progress.compute_session_metric(MeasurementType.selectorized, sets)
        assert kind == MetricKind.volume_load, kind
        assert value == expected_proxy[i], (i, value, expected_proxy[i])
        points.append(progress.MetricPoint(recorded_at=base + timedelta(weeks=i), value=value, pin_position=pin))

    indexed = [round(p.indexed) for p in progress.index_points(points)]
    assert indexed == expected_indexed, indexed

    badges = progress.detect_pin_badges(points)
    assert len(badges) == 1, badges
    assert (badges[0].from_pin, badges[0].to_pin) == (5, 6), badges[0]


def test_selectorized_microload_folds_into_step():
    # A +10 lb dial on a machine whose nominal step is 10 lb adds exactly one pin's worth.
    eq = SimpleNamespace(nominal_plate_lb=10.0, bar_weight_lb=None)
    plain = [_set(reps=10, pin_position=5)]
    dialed = [_set(reps=10, pin_position=5, added_load_lb=10.0)]
    _, v_plain = progress.compute_session_metric(MeasurementType.selectorized, plain, eq)
    _, v_dial = progress.compute_session_metric(MeasurementType.selectorized, dialed, eq)
    assert v_plain == 50.0, v_plain          # 5 * 10
    assert v_dial == 60.0, v_dial            # (5 + 10/10) * 10 = 6 * 10


# ─── plate_loaded / smith: Epley est-1RM ────────────────────────────────────────

def test_plate_loaded_epley_best_set():
    sets = [_set(reps=10, weight_value=100, weight_unit=WeightUnit.lb),
            _set(reps=5, weight_value=120, weight_unit=WeightUnit.lb)]
    kind, value = progress.compute_session_metric(MeasurementType.plate_loaded, sets)
    assert kind == MetricKind.est_1rm
    # best of 100*(1+10/30)=133.333 and 120*(1+5/30)=140.0 -> 140.0
    assert value == 140.0, value


def test_smith_adds_effective_bar_weight():
    eq = SimpleNamespace(bar_weight_lb=20.0, nominal_plate_lb=None)
    sets = [_set(reps=10, weight_value=100, weight_unit=WeightUnit.lb)]
    kind, value = progress.compute_session_metric(MeasurementType.smith, sets, eq)
    assert kind == MetricKind.est_1rm
    assert value == round(120 * (1 + 10 / 30), 3), value  # (100 + 20 bar) -> 160.0


def test_kg_converts_to_lb():
    sets = [_set(reps=1, weight_value=100, weight_unit=WeightUnit.kg)]
    _, value = progress.compute_session_metric(MeasurementType.plate_loaded, sets)
    # 100 kg -> 220.462 lb, then Epley at 1 rep -> load * (1 + 1/30).
    expected = 100 * progress.KG_TO_LB * (1 + 1 / 30)
    assert abs(value - expected) < 0.05, value


# ─── cardio: distance preferred, summed across sets ─────────────────────────────

def test_cardio_sums_distance_in_meters():
    sets = [_set(distance_value=1, distance_unit=DistanceUnit.mi),
            _set(distance_value=500, distance_unit=DistanceUnit.m)]
    kind, value = progress.compute_session_metric(MeasurementType.cardio, sets)
    assert kind == MetricKind.distance
    assert abs(value - (1609.344 + 500)) < 0.01, value


# ─── pattern-trend roll-up survives rotation ────────────────────────────────────

def test_pattern_trend_continuous_across_rotation():
    base = datetime(2026, 3, 1)
    # Exercise A performed weeks 0-2 then rotated out; B rotated in weeks 3-5. Both rising.
    a = [progress.MetricPoint(recorded_at=base + timedelta(weeks=i), value=v, exercise_id="A")
         for i, v in enumerate([100, 110, 120])]
    b = [progress.MetricPoint(recorded_at=base + timedelta(weeks=i), value=v, exercise_id="B")
         for i, v in zip(range(3, 6), [200, 220, 240])]
    series = progress.pattern_trend_series({"A": a, "B": b})
    assert len(series) == 6, len(series)
    values = [pt["value"] for pt in series]
    # Monotonic-ish rise, and no gap/crash when A drops out and B takes over.
    assert values[0] == 100.0, values
    assert values[-1] >= values[0], values


# ─── standalone runner ──────────────────────────────────────────────────────────

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
