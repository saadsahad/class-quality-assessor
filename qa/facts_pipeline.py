"""Experimental: VTT -> facts judge -> verify every fact's evidence -> fixed code rules -> same
compute_rating (weights, cuts, override) as the shipped pipeline. Not wired into app.py/qa/pipeline.py.
"""
from .coverage import check_coverage
from .facts_judge import run_facts_judge
from .facts_mapping import VerifiedFacts, map_facts
from .ingest import Cue, parse_vtt
from .joiners import late_joiner_candidates
from .pipeline import _secs
from .privacy import Masker, names_from_labels
from .score import compute_rating
from .signals import compute_signals, pseudonymise
from .verify import verify_evidence


def _verify(evidence_list, anon, media):
    ev = [{"quote": e.quote, "ts": _secs(e.ts), "speaker": e.speaker} for e in evidence_list]
    kept, dropped = verify_evidence(ev, anon, media)
    return kept, len(dropped)


def assess_facts_cues(
    cues: list[Cue],
    n_students: int | None = None,
    camera_issue: bool = False,
    model=None,
    media_duration_s: float | None = None,
    transcript_info: dict | None = None,
):
    anon, label_map = pseudonymise(cues)
    cov = check_coverage(anon, media_duration_s)
    asr = transcript_info is not None
    judgement, cost = run_facts_judge(
        anon,
        {} if asr else compute_signals(anon),
        n_students,
        coverage=cov,
        late_speakers=None if asr else late_joiner_candidates(anon),
        asr=transcript_info,
        **({"model": model} if model else {}),
    )
    media = [(_secs(m.start), _secs(m.end)) for m in judgement.media_segments]
    media_minutes = sum(e - s for s, e in media) / 60.0

    first_cue_t = min(c.start for c in anon)
    content_kept, content_dropped = _verify([judgement.first_lesson_content], anon, media)
    # if the judge's own first-content quote can't be confirmed, fall back to the class start (minutes_to_content=0)
    content_ts = content_kept[0]["ts"] if content_kept else first_cue_t

    greeted_kept, greeted_dropped = _verify(judgement.greeted_by_name, anon, media)
    greeted_before = [e for e in greeted_kept if e["ts"] < content_ts]
    checkin_kept, checkin_dropped = _verify(judgement.check_in_questions, anon, media)
    checkin_before = [e for e in checkin_kept if e["ts"] < content_ts]

    addressed_kept, addressed_dropped = _verify(judgement.addressed_by_name, anon, media)
    named_q_kept, named_q_dropped = _verify(judgement.named_child_questions, anon, media)
    specific_kept, specific_dropped = _verify(judgement.specific_praise, anon, media)
    generic_kept, generic_dropped = _verify(judgement.generic_praise, anon, media)
    flat_kept, flat_dropped = _verify(judgement.flat_acknowledgements, anon, media)
    recap_kept, recap_dropped = _verify(judgement.recap_evidence, anon, media)
    homework_kept, homework_dropped = _verify(judgement.homework_evidence, anon, media)
    goodbye_kept, goodbye_dropped = _verify(judgement.goodbye_evidence, anon, media)
    late_kept, late_dropped = _verify(judgement.late_joiner_evidence, anon, media)

    # a bool fact is true only if the judge said so AND at least one supporting quote survived verification
    late_present = bool(judgement.late_joiner_present and late_kept)
    late_welcome = judgement.late_joiner_welcome if late_present else None
    recap = bool(judgement.recap and recap_kept)
    homework_set = bool(judgement.homework_set and homework_kept)
    goodbye = bool(judgement.goodbye and goodbye_kept)

    sig = {} if asr else compute_signals(anon, media)
    duration_min = (max(c.end for c in anon) - min(c.start for c in anon)) / 60.0 if anon else 0.0
    # Without speaker labels (ASR) there's no "tutor share"; fall back to the whole class length.
    tutor_talk_minutes = duration_min * sig["most_talkative_share"] if sig.get("most_talkative_share") else duration_min

    vf = VerifiedFacts(
        minutes_to_content=max(0.0, (content_ts - first_cue_t) / 60.0),
        greeted_by_name=len(greeted_before),
        check_in_questions=len(checkin_before),
        late_joiner_present=late_present,
        late_joiner_welcome=late_welcome,
        addressed_by_name=len(addressed_kept),
        named_child_questions=len(named_q_kept),
        specific_praise=len(specific_kept),
        generic_praise=len(generic_kept),
        flat_acknowledgements=len(flat_kept),
        recap=recap,
        homework_set=homework_set,
        goodbye=goodbye,
        tutor_talk_minutes=round(tutor_talk_minutes, 2),
        media_minutes=round(media_minutes, 2),
        notes={
            "dropped": {
                "first_lesson_content": content_dropped, "greeted_by_name": greeted_dropped,
                "check_in_questions": checkin_dropped, "addressed_by_name": addressed_dropped,
                "named_child_questions": named_q_dropped, "specific_praise": specific_dropped,
                "generic_praise": generic_dropped, "flat_acknowledgements": flat_dropped,
                "recap": recap_dropped, "homework_set": homework_dropped, "goodbye": goodbye_dropped,
                "late_joiner": late_dropped,
            },
            "judge_claimed": {
                "late_joiner_present": judgement.late_joiner_present, "recap": judgement.recap,
                "homework_set": judgement.homework_set, "goodbye": judgement.goodbye,
            },
            "content_quote_verified": bool(content_kept),
        },
    )
    scores = map_facts(vf)
    rating = compute_rating(scores, camera_issue)
    masker = Masker(names_from_labels(label_map) | set(judgement.names_mentioned))
    result = {
        "rating": rating,
        "scores": scores,
        "facts": vf,
        "signals": sig,
        "coverage": cov,
        "cost_usd": round(cost, 4),
    }
    return masker.obj(result)


def assess_facts_vtt(vtt_text: str, **kw):
    return assess_facts_cues(parse_vtt(vtt_text), **kw)
