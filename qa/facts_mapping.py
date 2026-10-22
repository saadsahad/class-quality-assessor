"""Fixed rules mapping verified facts to the 5 scored criteria. Written BEFORE any facts-judge run on
real recordings (see README "Facts judge (experimental)"); one revision is allowed after seeing the
results, and is disclosed there if used. These are the only mapping rules; nothing here is tuned per
recording.

Input is a VerifiedFacts dataclass of already-verified counts/booleans (see facts_pipeline.py) - a
count is the number of evidence quotes that survived qa/verify.py, not the judge's own claimed number.
"""
from dataclasses import dataclass, field


@dataclass
class VerifiedFacts:
    minutes_to_content: float  # minutes from the first cue to first_lesson_content's timestamp
    greeted_by_name: int  # distinct children greeted by name, verified, with ts before first_lesson_content
    check_in_questions: int  # verified, with ts before first_lesson_content

    late_joiner_present: bool
    late_joiner_welcome: str | None  # "introduced" | "welcomed_by_name" | "acknowledged" | "ignored" | None

    addressed_by_name: int  # report-only; no mapping rule uses this
    named_child_questions: int  # verified count, whole class

    specific_praise: int
    generic_praise: int
    flat_acknowledgements: int

    recap: bool
    homework_set: bool
    goodbye: bool

    tutor_talk_minutes: float  # class duration if no speaker labels (e.g. ASR without a VTT)
    media_minutes: float  # computed from media_segments, not judged

    # the raw, unverified claims, kept only for the calibration report's audit trail (never scored)
    notes: dict = field(default_factory=dict)


def _per_10(count: int, minutes: float) -> float:
    return (count / minutes) * 10 if minutes > 0 else 0.0


# The fact list has no direct "was there any greeting at all" boolean, only "greeted BY NAME" (a
# count) and minutes-to-content. So "no greeting" vs "greeting without names" is told apart by whether
# any time passes before lesson content starts at all: if content starts essentially at cue zero, no
# greeting of any kind happened; if it starts later but no child was named, that's a name-less greeting.
# This is a code-level interpretation, not a fact the judge reports directly - flagged in the README.
NO_GREETING_THRESHOLD_MIN = 0.1


def rapport_start(f: VerifiedFacts) -> int:
    if f.greeted_by_name >= 2 and f.check_in_questions >= 1 and f.minutes_to_content >= 2:
        return 4
    if f.greeted_by_name >= 1 and (f.check_in_questions >= 1 or f.minutes_to_content >= 2):
        return 3
    if f.greeted_by_name == 0 and f.minutes_to_content < NO_GREETING_THRESHOLD_MIN:
        return 1
    return 2  # a greeting happened (time passed, or a name was used) but not enough for 3 or 4


def welcome_new(f: VerifiedFacts) -> int | None:
    if not f.late_joiner_present:
        return None
    return {"introduced": 4, "welcomed_by_name": 3, "acknowledged": 2, "ignored": 1}.get(f.late_joiner_welcome, 1)


def warmth_energy(f: VerifiedFacts) -> int:
    praise = _per_10(f.specific_praise, f.tutor_talk_minutes)
    flat = _per_10(f.flat_acknowledgements, f.tutor_talk_minutes)
    generic = _per_10(f.generic_praise, f.tutor_talk_minutes)
    if praise >= 3 and praise > flat:
        return 4
    if praise >= 1:
        return 3
    if generic > praise or flat > praise:
        return 2
    return 1


def lesson_close(f: VerifiedFacts) -> int:
    if f.recap and f.homework_set and f.goodbye:
        return 4
    if f.recap and f.goodbye:
        return 3
    if f.goodbye or f.homework_set:
        return 2
    return 1


def checklist(f: VerifiedFacts) -> int:
    per10 = _per_10(f.named_child_questions, f.tutor_talk_minutes)
    if per10 >= 8:
        score = 4
    elif per10 >= 4:
        score = 3
    elif per10 >= 1:
        score = 2
    else:
        score = 1
    media_share = f.media_minutes / max(f.tutor_talk_minutes, 1e-6)
    if media_share > 0.25:
        score = max(1, score - 1)
    return score


def map_facts(f: VerifiedFacts) -> dict:
    """criterion name -> score (1-4 or None); fair_turns is left out, same as the shipped rubric (report-only)."""
    return {
        "rapport_start": rapport_start(f),
        "welcome_new": welcome_new(f),
        "warmth_energy": warmth_energy(f),
        "lesson_close": lesson_close(f),
        "checklist": checklist(f),
    }
