"""Transcript ingestion. Transcript text is held in memory only and never logged."""
import re
from dataclasses import dataclass

_TS = r"(?:(\d+):)?(\d{2}):(\d{2})[.,](\d{3})"
_CUE = re.compile(rf"{_TS}\s*-->\s*{_TS}")
_SPEAKER = re.compile(r"^([^:\n]{1,60}):\s+(.*)$")


@dataclass
class Cue:
    start: float
    end: float
    speaker: str | None
    text: str


def _secs(h, m, s, ms) -> float:
    return int(h or 0) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def parse_vtt(text: str) -> list[Cue]:
    """Parse a Zoom WebVTT file. Zoom writes `Speaker Name: text` inside each cue."""
    cues: list[Cue] = []
    lines = text.replace("\r\n", "\n").split("\n")
    i = 0
    while i < len(lines):
        m = _CUE.search(lines[i])
        if not m:
            i += 1
            continue
        g = m.groups()
        start, end = _secs(*g[:4]), _secs(*g[4:])
        i += 1
        body = []
        while i < len(lines) and lines[i].strip():
            body.append(lines[i].strip())
            i += 1
        joined = " ".join(body)
        sm = _SPEAKER.match(joined)
        speaker, utter = (sm.group(1).strip(), sm.group(2).strip()) if sm else (None, joined)
        if utter:
            cues.append(Cue(start, end, speaker, utter))
    return cues


def fmt_ts(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"
