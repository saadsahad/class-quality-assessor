"""VTT -> signals -> judge -> verify -> score."""
from .ingest import Cue, parse_vtt
from .coverage import NA_IF_END_ABSENT, NA_IF_START_ABSENT, check_coverage
from .joiners import late_joiner_candidates
from .judge import run_judge
from .privacy import Masker, names_from_labels
from .rubric import CRITERIA
from .score import compute_rating
from .signals import compute_signals, pseudonymise


PARTIAL_SENSITIVE = ("warmth_energy", "checklist", "fair_turns", "welcome_new")  # need the whole class to judge well


def _secs(ts: str) -> float:
    parts = [int(p) for p in ts.strip().split(":")]
    while len(parts) < 3:
        parts.insert(0, 0)
    return parts[0] * 3600 + parts[1] * 60 + parts[2]


def assess_cues(
    cues: list[Cue],
    n_students: int | None = None,
    camera_issue: bool = False,
    model=None,
    media_duration_s: float | None = None,
    transcript_info: dict | None = None,
):
    """transcript_info is set for audio transcribed here (Whisper): no speaker labels, maybe partial."""
    from .verify import verify_evidence

    anon, label_map = pseudonymise(cues)
    cov = check_coverage(anon, media_duration_s)
    asr = transcript_info is not None
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
        if (cov["start"] == "absent" and c.name in NA_IF_START_ABSENT) or (
            cov["end"] == "absent" and c.name in NA_IF_END_ABSENT
        ):
            score, note = None, "N/A: that part of the class is not in the transcript"
        if score is not None and not kept:  # (c.score may be set while score was forced to N/A above)
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
            "dropped": len(dropped),
            "note": note,
        }
    masker = Masker(names_from_labels(label_map) | set(judgement.names_mentioned))
    result = {
        "rating": compute_rating(scores, camera_issue),
        "criteria": report,
        "signals": {} if asr else compute_signals(anon, media),
        "transcript": {"source": "whisper", "has_speakers": False, **transcript_info}
        if asr
        else {"source": "zoom_vtt", "has_speakers": True, "partial": False},
        "media_segments": [m.model_dump() for m in judgement.media_segments],
        "coverage": cov,
        "model_cross_check": {"rating": judgement.holistic_rating, "reason": judgement.holistic_reason},
        "cost_usd": round(cost, 4),
    }
    return masker.obj(result)  # nothing unmasked leaves this function


def assess_vtt(vtt_text: str, **kw):
    return assess_cues(parse_vtt(vtt_text), **kw)
