"""Decide from data whether the opening / closing of the class is present in the transcript.

The transcript alone cannot tell "recording starts mid-class" from "tutor skipped the greeting";
QA notes show the latter is a real failure, so a missing greeting is scored, not N/A. A part is
"absent" (-> N/A) only on objective evidence: speech starts, or the transcript stops, far from the
media's own start/end, with no greeting/goodbye talk near that edge.
"""
import re

from .ingest import Cue

WINDOW_S = 300
ABSENT_GAP_S = 600  # first cue this late with no greeting -> opening not in the transcript
ABSENT_TAIL_S = 300  # transcript stops this early with no goodbye -> ending not in the transcript

GREET = re.compile(
    r"\b(hello|hi|hey|good (morning|evening|afternoon)|welcome|how are you|how is everyone|nice to see)\b", re.I
)
BYE = re.compile(
    r"\b(bye|goodbye|see you|take care|that'?s (all )?for today|next class|next week|great job today|thank you (all|everyone|guys))\b",
    re.I,
)


def check_coverage(cues: list[Cue], media_duration_s: float | None = None) -> dict:
    first, last = cues[0].start, cues[-1].end
    greet = sum(1 for c in cues if c.start < first + WINDOW_S and GREET.search(c.text))
    bye = sum(1 for c in cues if c.end > last - WINDOW_S and BYE.search(c.text))
    tail_gap = (media_duration_s - last) if media_duration_s else None

    if greet >= 2:
        start = "present"
    elif greet == 0 and first > ABSENT_GAP_S:
        start = "absent"
    else:
        start = "unclear"

    if bye >= 1:
        end = "present"
    elif tail_gap is not None and tail_gap > ABSENT_TAIL_S:
        end = "absent"
    else:
        end = "unclear"

    return {
        "start": start,
        "end": end,
        "first_cue_s": round(first),
        "last_cue_s": round(last),
        "media_s": round(media_duration_s) if media_duration_s else None,
        "greeting_cues_in_opening": greet,
        "goodbye_cues_in_closing": bye,
    }


# criteria that cannot be judged when the matching part of the class is absent
NA_IF_START_ABSENT = ("rapport_start", "welcome_new")
NA_IF_END_ABSENT = ("lesson_close",)
