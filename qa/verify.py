"""Check every piece of evidence against the transcript; drop anything unconfirmed."""
import re

from rapidfuzz import fuzz

from .config import VERIFY_MIN_RATIO, VERIFY_MIN_WORDS, VERIFY_WINDOW_S
from .ingest import Cue


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", s.lower())).strip()


def _in_media(ts: float, media: list[tuple[float, float]]) -> bool:
    return any(a <= ts <= b for a, b in media)


def verify_evidence(evidence, cues: list[Cue], media_segments=(), window=VERIFY_WINDOW_S):
    """Return (kept, dropped). Each item is {quote, ts (seconds), ...}; dropped items gain `reason`.

    A quote is confirmed when it fuzzy-matches the joined cue text within +/-window seconds of
    its claimed timestamp. Joining cues handles quotes that Zoom split across cue boundaries.
    Quotes inside media (e.g. a YouTube video attributed to the tutor) are rejected.
    """
    kept, dropped = [], []
    media = list(media_segments)
    for ev in evidence:
        quote, ts = _norm(ev.get("quote", "")), ev.get("ts")
        reason = None
        if ts is None or len(quote.split()) < VERIFY_MIN_WORDS:
            reason = "quote too short or missing timestamp"
        elif _in_media(ts, media):
            reason = "inside media playback"
        else:
            near = [c for c in cues if c.end >= ts - window and c.start <= ts + window]
            joined = _norm(" ".join(c.text for c in near))
            if not joined or fuzz.partial_ratio(quote, joined) < VERIFY_MIN_RATIO:
                reason = "not found near timestamp"
        (dropped if reason else kept).append({**ev, **({"reason": reason} if reason else {})})
    return kept, dropped
