"""Tests for the core-criteria rule-based override in qa/score.py (adopted in-sample; see README)."""
from qa.score import compute_rating

FULL = {"rapport_start": 3, "welcome_new": 3, "warmth_energy": 3, "fair_turns": 3, "lesson_close": 3, "checklist": 3}


def test_one_core_criterion_at_1_overrides_to_poor():
    s = {**FULL, "rapport_start": 1}  # weighted alone (2.45) would read as Average
    r = compute_rating(s)
    assert r["grade"] == "Poor"
    assert r["borderline"] == ("Poor", "Average")
    assert "Rated Poor by the core-criteria rule" in r["override_reason"]
    assert "rapport 1" in r["override_reason"]
    assert "no strengths at 4" in r["override_reason"]
    assert "suggests Average" in r["override_reason"]


def test_two_core_at_or_below_2_with_none_at_4_overrides_to_poor():
    s = {**FULL, "rapport_start": 2, "warmth_energy": 2}
    r = compute_rating(s)
    assert r["grade"] == "Poor"
    assert r["override_reason"].startswith("Rated Poor by the core-criteria rule: rapport 2, warmth 2")


def test_two_low_core_but_a_4_elsewhere_in_core_blocks_the_override():
    s = {**FULL, "rapport_start": 2, "warmth_energy": 2, "welcome_new": 4}
    r = compute_rating(s)
    assert r["grade"] != "Poor" and r["override_reason"] is None


def test_two_core_at_4_with_none_low_overrides_to_excellent():
    # lesson_close/checklist pulled down so the weighted score (3.34) alone would read as Good
    s = {**FULL, "rapport_start": 4, "warmth_energy": 4, "lesson_close": 2, "checklist": 2}
    r = compute_rating(s)
    assert r["grade"] == "Excellent"
    assert r["borderline"] == ("Good", "Excellent")
    assert "no weaknesses at 2 or below" in r["override_reason"]
    assert "suggests Good" in r["override_reason"]


def test_na_core_criterion_excluded_from_the_rule_not_counted_as_weak():
    # only rapport and warmth are observable; both low is still 2-of-2, so Poor fires
    s = {**FULL, "rapport_start": 2, "warmth_energy": 2, "welcome_new": None}
    r = compute_rating(s)
    assert r["grade"] == "Poor"
    assert "welcoming" not in r["override_reason"]


def test_no_override_when_rule_agrees_with_weighted_grade():
    s = dict(FULL)  # all 3s: weighted = Good-ish middle, no core trigger either way
    r = compute_rating(s)
    assert r["override_reason"] is None


def test_override_applies_before_camera_penalty_on_the_label_but_penalty_still_affects_weighted():
    s = {**FULL, "rapport_start": 1}
    r = compute_rating(s, camera_issue=True)
    assert r["grade"] == "Poor"  # rule fires on raw criterion scores regardless of the penalty
    assert r["penalty"] == 0.5
