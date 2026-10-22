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
    # Poor (2.0) and Average (2.75) are the original locked cuts, untouched. The Excellent cut was
    # deliberately moved from 3.4 to 3.0 post-hoc, after calibration showed 3.4 made Excellent
    # unreachable (best observed weighted score was 3.27) — see README "Excellent cut-point (post-hoc)".
    assert CUTS == [(2.0, "Poor"), (2.75, "Average"), (3.0, "Good")]
