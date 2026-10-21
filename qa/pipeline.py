"""VTT -> signals -> judge -> verify -> score."""
import statistics

from .ingest import Cue, parse_vtt
from .coverage import NA_IF_END_ABSENT, NA_IF_START_ABSENT, check_coverage
from .joiners import late_joiner_candidates
from .judge import run_judge
from .privacy import Masker, names_from_labels
from .rubric import CRITERIA, CUTS
from .score import borderline, compute_rating
from .signals import compute_signals, pseudonymise
from .config import ADAPTIVE_MEDIAN_BAND


PARTIAL_SENSITIVE = ("warmth_energy", "checklist", "fair_turns", "welcome_new")  # need the whole class to judge well
# These two must get a concrete 1-4 score whenever the matching part of the class is actually in the
# transcript (coverage != "absent"); only a genuinely missing opening/closing excuses a null score.
COVERAGE_GATED = {"rapport_start": "start", "lesson_close": "end"}


def _secs(ts: str) -> float:
    parts = [int(p) for p in ts.strip().split(":")]
    while len(parts) < 3:
        parts.insert(0, 0)
    return parts[0] * 3600 + parts[1] * 60 + parts[2]


def _one_pass(anon, cov, n_students, asr, transcript_info, model):
    """One judge call plus verification. Returns (scores, report, cost, judgement, media, names)."""
    from .verify import verify_evidence

    judgement, cost = run_judge(
        anon,
        {} if asr else compute_signals(anon),  # talk share and joiners mean nothing without speaker labels
        n_students,
        coverage=cov,
        late_speakers=None if asr else late_joiner_candidates(anon),
        asr=transcript_info,
        **({"model": model} if model else {}),
    )
    media = [(_secs(m.start), _secs(m.end)) for m in judgement.media_segments]

    scores, report = {}, {}
    for c in judgement.criteria:
        ev = [{"quote": e.quote, "ts": _secs(e.ts), "speaker": e.speaker} for e in c.evidence]
        kept, dropped = verify_evidence(ev, anon, media)
        score, note = c.score, "ok"
        absent_forced = (cov["start"] == "absent" and c.name in NA_IF_START_ABSENT) or (
            cov["end"] == "absent" and c.name in NA_IF_END_ABSENT
        )
        if absent_forced:
            score, note = None, "N/A: that part of the class is not in the transcript"
        elif c.name in COVERAGE_GATED and c.score is None:
            # The judge chose null even though coverage says this part IS in the transcript (not "absent").
            # Null is only a legitimate escape when the transcript itself is partial (Whisper sampling).
            if asr and transcript_info and transcript_info.get("partial"):
                score, note = None, "N/A: partial transcript, low confidence"
            else:
                score, note = 1, "coverage shows this part is present; scored 1 (not shown) rather than N/A"
        if note == "ok" and score is not None and not kept:
            if score >= 3:  # a high score needs at least one verified quote
                score, note = 2, f"capped from {c.score}: no verified quote"
            else:
                note = "based on absence"
        if note == "ok" and asr and transcript_info.get("partial") and c.name in PARTIAL_SENSITIVE:
            note = "judged from a partial transcript (sampled parts of the class)"
        scores[c.name] = score
        report[c.name] = {
            "score": score,
            "in_grade": CRITERIA[c.name]["weight"] > 0,
            "judge_score": c.score,
            "rationale": c.rationale,
            "evidence": kept,
            "verified_count": len(kept),
            "dropped": len(dropped),
            "thin_evidence": score is not None and len(kept) < 2,
            "note": note,
        }
    return scores, report, cost, judgement, media


def assess_cues(
    cues: list[Cue],
    n_students: int | None = None,
    camera_issue: bool = False,
    model=None,
    media_duration_s: float | None = None,
    transcript_info: dict | None = None,
):
    """transcript_info is set for audio transcribed here (Whisper): no speaker labels, maybe partial."""
    anon, label_map = pseudonymise(cues)
    cov = check_coverage(anon, media_duration_s)
    asr = transcript_info is not None

    scores, report, cost, judgement, media = _one_pass(anon, cov, n_students, asr, transcript_info, model)
    rating = compute_rating(scores, camera_issue)
    total_cost, runs = cost, 1

    # A score this close to a grade boundary is sensitive to the model's own run-to-run noise: run it
    # twice more and take the per-criterion median instead of trusting a single borderline call.
    if rating["weighted"] is not None and borderline(rating["weighted"], CUTS, ADAPTIVE_MEDIAN_BAND):
        passes = [(scores, report, judgement, media)]
        for _ in range(2):
            s2, r2, c2, j2, m2 = _one_pass(anon, cov, n_students, asr, transcript_info, model)
            total_cost += c2
            passes.append((s2, r2, j2, m2))
        runs = 3
        combined = {}
        for name in CRITERIA:
            vals = [p[0][name] for p in passes if p[0].get(name) is not None]
            combined[name] = round(statistics.median(vals)) if len(vals) >= 2 else None
        rating = compute_rating(combined, camera_issue)
        # Use the pass closest to the combined weighted score for the displayed rationale/evidence.
        rep = min(
            range(3),
            key=lambda i: abs((compute_rating(passes[i][0], camera_issue)["weighted"] or 1e9) - (rating["weighted"] or 0)),
        )
        scores, report, judgement, media = passes[rep][0], passes[rep][1], passes[rep][2], passes[rep][3]
        for name, v in combined.items():
            if name in report:
                report[name]["score"] = v
                if v != report[name]["judge_score"]:
                    report[name]["note"] = (report[name]["note"] + "; " if report[name]["note"] != "ok" else "") + "median of 3 runs"

    masker = Masker(names_from_labels(label_map) | set(judgement.names_mentioned))
    result = {
        "rating": rating,
        "criteria": report,
        "signals": {} if asr else compute_signals(anon, media),
        "transcript": {"source": "whisper", "has_speakers": False, **transcript_info}
        if asr
        else {"source": "zoom_vtt", "has_speakers": True, "partial": False},
        "media_segments": [m.model_dump() for m in judgement.media_segments],
        "coverage": cov,
        "model_cross_check": {"rating": judgement.holistic_rating, "reason": judgement.holistic_reason},
        "median_of_3": runs == 3,
        "cost_usd": round(total_cost, 4),
    }
    return masker.obj(result)  # nothing unmasked leaves this function


def assess_vtt(vtt_text: str, **kw):
    return assess_cues(parse_vtt(vtt_text), **kw)
