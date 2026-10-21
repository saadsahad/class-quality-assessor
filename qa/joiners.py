"""Candidate late joiners from the transcript: labels whose first utterance comes well after class start.

Zoom VTTs record speech only, not join events, so this is a hint: a quiet child who finally speaks,
or one child rejoining on another device, looks the same as a new joiner.
"""
from collections import defaultdict

from .ingest import Cue

LATE_AFTER_S = 300


def speaker_first_seen(cues: list[Cue]) -> list[dict]:
    """Per label: first utterance (seconds after the first cue), utterance and word counts. Labels should be pseudonymised."""
    t0 = min(c.start for c in cues)
    info = defaultdict(lambda: {"first_s": None, "utterances": 0, "words": 0})
    for c in cues:
        d = info[c.speaker]
        d["first_s"] = c.start - t0 if d["first_s"] is None else min(d["first_s"], c.start - t0)
        d["utterances"] += 1
        d["words"] += len(c.text.split())
    return [
        {"label": k, **{**v, "first_s": round(v["first_s"])}, "late": v["first_s"] > LATE_AFTER_S}
        for k, v in sorted(info.items(), key=lambda kv: kv[1]["first_s"])
    ]


def late_joiner_candidates(cues: list[Cue]) -> list[dict]:
    return [s for s in speaker_first_seen(cues) if s["late"]]
