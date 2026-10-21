"""Guards against accidental tuning: the rubric and cut-points are locked after calibration on the 10 labelled recordings."""
from qa.rubric import CRITERIA, CUTS


def test_weights_locked():
    assert {k: v["weight"] for k, v in CRITERIA.items()} == {
        "rapport_start": 0.22,
        "welcome_new": 0.13,
        "warmth_energy": 0.25,
        "fair_turns": 0.0,  # report-only
        "lesson_close": 0.15,
        "checklist": 0.05,
    }


def test_cuts_locked():
    assert CUTS == [(2.0, "Poor"), (2.75, "Average"), (3.4, "Good")]
