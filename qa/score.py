"""Rating computed in code from criterion scores, never taken from the model's own verdict.

Grading is two explicit steps, both over the locked weights and cut-points (neither is retuned here):
  1. The weighted average of observed criteria, cut into a grade as before.
  2. A core-criteria rule-based override (see CORE_CRITERIA below) that can replace that grade with
     Poor or Excellent when the tutor's rapport, warmth and welcome of new joiners are uniformly weak
     or uniformly strong. It was adopted in-sample on 10 labelled recordings because the weighted
     average alone never predicted Poor or Excellent at all; the rule trades some Average accuracy
     for Poor accuracy, which matters more for a QA tool meant to catch weak classes.
"""
from .config import BORDERLINE_BAND, CAMERA_PENALTY
from .rubric import CRITERIA, CUTS, TOP_GRADE

MIN_WEIGHT_OBSERVED = 0.4

# The three criteria the override rule looks at, and how they're named in its one-line explanation.
CORE_CRITERIA = ("rapport_start", "warmth_energy", "welcome_new")
CORE_LABELS = {"rapport_start": "rapport", "warmth_energy": "warmth", "welcome_new": "welcoming"}
GRADES = [name for _, name in CUTS] + [TOP_GRADE]


def grade_for(score: float, cuts=CUTS) -> str:
    for cut, name in cuts:
        if score < cut:
            return name
    return TOP_GRADE


def borderline(score: float, cuts=CUTS, band: float = BORDERLINE_BAND):
    """If score is within `band` of its nearest cut, return (lower_grade, upper_grade), else None."""
    names = [n for _, n in cuts] + [TOP_GRADE]
    cut, i = min(((c, i) for i, (c, _) in enumerate(cuts)), key=lambda ci: abs(score - ci[0]))
    return (names[i], names[i + 1]) if abs(score - cut) <= band else None


def _core_rule(scores: dict):
    """Poor if any core criterion is 1, or two or more are 2-or-below with none at 4.
    Excellent if most core criteria (2 of the 3) are 4 and none are 2-or-below. Else no override.
    N/A core criteria are left out of the counts, not treated as either weak or strong."""
    present = {k: scores[k] for k in CORE_CRITERIA if scores.get(k) is not None}
    ones = [k for k, v in present.items() if v == 1]
    low = [k for k, v in present.items() if v <= 2]
    fours = [k for k, v in present.items() if v == 4]
    if ones or (len(low) >= 2 and not fours):
        grade = "Poor"
    elif len(fours) >= 2 and not low:
        grade = "Excellent"
    else:
        grade = None
    return grade, present, low, fours


def _override_reason(rule_grade: str, present: dict, fours: list, low: list, weighted: float, weighted_grade: str) -> str:
    parts = ", ".join(f"{CORE_LABELS[k]} {v}" for k, v in present.items())
    tail = ", no strengths at 4" if rule_grade == "Poor" and not fours else ""
    tail = tail or (", no weaknesses at 2 or below" if rule_grade == "Excellent" and not low else "")
    return (
        f"Rated {rule_grade} by the core-criteria rule: {parts}{tail}. "
        f"Weighted score {weighted:.2f} suggests {weighted_grade}."
    )


def compute_rating(scores: dict, camera_issue: bool = False, cuts=CUTS) -> dict:
    """scores: criterion -> 1..4 or None (N/A). Weights are renormalised over observed criteria."""
    observed = {k: v for k, v in scores.items() if v is not None and k in CRITERIA}
    total_w = sum(CRITERIA[k]["weight"] for k in observed)
    if total_w < MIN_WEIGHT_OBSERVED:
        return {"grade": None, "weighted": None, "note": "insufficient observable criteria", "penalty": 0.0}
    weighted = sum(CRITERIA[k]["weight"] * v for k, v in observed.items()) / total_w
    penalty = CAMERA_PENALTY if camera_issue else 0.0
    final = max(1.0, weighted - penalty)

    weighted_grade = grade_for(final, cuts)
    bl = borderline(final, cuts)
    grade, override_reason = weighted_grade, None

    rule_grade, present, low, fours = _core_rule(scores)
    if rule_grade and rule_grade != weighted_grade:
        grade = rule_grade
        i, j = sorted((GRADES.index(rule_grade), GRADES.index(weighted_grade)))
        bl = (GRADES[i], GRADES[j])
        override_reason = _override_reason(rule_grade, present, fours, low, final, weighted_grade)

    return {
        "grade": grade,
        "weighted": round(final, 2),
        "before_penalty": round(weighted, 2),
        "penalty": penalty,
        "borderline": bl,
        "override_reason": override_reason,
        "observed": sorted(observed),
        "na": sorted(k for k in CRITERIA if k not in observed),
    }
