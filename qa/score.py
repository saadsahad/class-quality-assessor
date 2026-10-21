"""Rating computed in code from criterion scores, never taken from the model's own verdict."""
from .config import BORDERLINE_BAND, CAMERA_PENALTY
from .rubric import CRITERIA, CUTS, TOP_GRADE

MIN_WEIGHT_OBSERVED = 0.4


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


def compute_rating(scores: dict, camera_issue: bool = False, cuts=CUTS) -> dict:
    """scores: criterion -> 1..4 or None (N/A). Weights are renormalised over observed criteria."""
    observed = {k: v for k, v in scores.items() if v is not None and k in CRITERIA}
    total_w = sum(CRITERIA[k]["weight"] for k in observed)
    if total_w < MIN_WEIGHT_OBSERVED:
        return {"grade": None, "weighted": None, "note": "insufficient observable criteria", "penalty": 0.0}
    weighted = sum(CRITERIA[k]["weight"] * v for k, v in observed.items()) / total_w
    penalty = CAMERA_PENALTY if camera_issue else 0.0
    final = max(1.0, weighted - penalty)
    return {
        "grade": grade_for(final, cuts),
        "weighted": round(final, 2),
        "before_penalty": round(weighted, 2),
        "penalty": penalty,
        "borderline": borderline(final, cuts),
        "observed": sorted(observed),
        "na": sorted(k for k in CRITERIA if k not in observed),
    }
