"""Transcript-derived signals. Speaker labels are devices, so they are pseudonymised to S1, S2...
(S1 talks most) before anything leaves the process."""
from collections import Counter

from .ingest import Cue, fmt_ts

DEAD_AIR_S = 20


def pseudonymise(cues: list[Cue]) -> tuple[list[Cue], dict[str, str]]:
    words = Counter()
    for c in cues:
        words[c.speaker or "?"] += len(c.text.split())
    mapping = {name: f"S{i + 1}" for i, (name, _) in enumerate(words.most_common())}
    return [Cue(c.start, c.end, mapping[c.speaker or "?"], c.text) for c in cues], mapping


def _outside(c: Cue, media) -> bool:
    return not any(a <= c.start <= b for a, b in media)


def compute_signals(cues: list[Cue], media=()) -> dict:
    """Approximate signals; pass the judge's media segments to exclude played videos."""
    live = [c for c in cues if _outside(c, media)]
    if not live:
        return {}
    duration = max(c.end for c in cues) - min(c.start for c in cues)
    words = Counter()
    for c in live:
        words[c.speaker] += len(c.text.split())
    total = sum(words.values()) or 1
    top = words.most_common(1)[0][0]
    gaps = sum(
        max(0.0, b.start - a.end) for a, b in zip(live, live[1:]) if b.start - a.end > DEAD_AIR_S
    )
    mins = max(duration / 60, 1)
    return {
        "duration_min": round(duration / 60, 1),
        "distinct_speaker_labels": len(words),
        "most_talkative_label": top,
        "most_talkative_share": round(words[top] / total, 2),
        "talk_share_by_label": {k: round(v / total, 2) for k, v in words.most_common()},
        "words_per_min": round(total / mins, 1),
        "questions_per_10min": round(sum(c.text.count("?") for c in live) / mins * 10, 1),
        "dead_air_pct": round(100 * gaps / max(duration, 1), 1),
        "first_cue_at": fmt_ts(min(c.start for c in cues)),
    }
