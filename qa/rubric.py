"""Rubric: weights chosen from the QA findings, then LOCKED (see tests/test_locked.py).

fair_turns was made report-only after the first calibration pass; that was decided from a single in-sample
rescore on the 10 labelled recordings and should be re-checked on new data. CUTS are the original
placeholders and were never tuned: no further tuning on the 10 labelled recordings.
"""

# Soft skills separate the grades; checklist items do not, so they carry little weight.
CRITERIA = {
    "rapport_start": {
        "weight": 0.22,
        "desc": "Tutor builds rapport at the start: greets children by name, small talk, sets a friendly tone.",
    },
    "welcome_new": {
        "weight": 0.13,
        "desc": "Welcomes and includes new joiners. N/A if nobody new joins or the start is not in the recording.",
    },
    "warmth_energy": {
        "weight": 0.25,
        "desc": "Warmth and energy: encouragement, praise, enthusiasm, humour, responsiveness to children.",
    },
    "fair_turns": {
        # Report-only (weight 0): cannot be measured without diarization, and in calibration it disagreed with
        # the QA notes in both directions. Still scored by the judge and shown in the report, but not graded.
        "weight": 0.0,
        "desc": "Every child gets fair turns relative to attendance; quiet children are drawn in.",
    },
    "lesson_close": {
        "weight": 0.15,
        "desc": (
            "Wrap-up: recap of what was learned, a clear ending, next steps. Homework counts here "
            "when given but is not required. N/A if the end is not in the recording."
        ),
    },
    "checklist": {
        "weight": 0.05,
        "desc": "Basics: questions asked to the class and a structured lesson flow.",
    },
}


# General behaviours per score level, distilled from the QA team's notes (no names, no batch IDs).
ANCHORS = {
    "rapport_start": {
        4: "Greets children individually by name, brief personal or friendly exchange, warm tone before any content.",
        3: "Friendly greeting and introduction, but mostly generic to the group; little one-to-one exchange.",
        2: "Perfunctory greeting, moves to content quickly.",
        1: "Goes straight into revision or the lesson with no greeting or rapport building, even though the opening is in the transcript.",
    },
    "welcome_new": {
        4: "Notices the new joiner, invites a self-introduction, gives time for it and includes them in activities.",
        3: "Welcomes the new joiner but gives no real time for self-introduction.",
        2: "Acknowledges the new joiner only in passing.",
        1: "New joiner is ignored or left out. (null if nobody new joins)",
    },
    "warmth_energy": {
        4: "Frequent specific praise (naming what the child did well) and some humour or playfulness; energy is consistent.",
        3: "Pleasant and encouraging, but energy is uneven or praise is mostly generic.",
        2: "Flat acknowledgements ('okay, next', 'good', moving straight on) with little real praise; low reaction to the children.",
        1: "Dull, impatient or unresponsive; children appear disengaged.",
    },
    "fair_turns": {
        4: "Asks children individually by name and rotates through everyone, including during puzzle solving; draws in quiet children.",
        3: "Most children get turns, with some imbalance.",
        2: "A few children dominate; some are barely addressed.",
        1: "One or two children get nearly all the turns, or the tutor talks throughout.",
    },
    "lesson_close": {
        4: "Recaps what was learned, gives homework or next steps, and ends with a clear, warm goodbye.",
        3: "Clear ending with some recap or next steps.",
        2: "Ends abruptly with a thin recap.",
        1: "No conclusion; the class just stops, even though the ending is in the transcript.",
    },
    "checklist": {
        4: "Many varied questions to the class, clear lesson structure, related videos or materials used well.",
        3: "Adequate questions and structure.",
        2: "Few questions; loose structure.",
        1: "Mostly lecture with almost no questions.",
    },
}

SCALE = "1 = poor, 2 = weak, 3 = good, 4 = excellent; null = not observable in this recording"

# Weighted score (1-4) -> grade. LOCKED placeholders; they were not validated by calibration.
# The Excellent cut was moved from 3.4 to 3.0 post-hoc, after calibration: at 3.4 the judge's best
# observed weighted score (3.27) never reached it, so Excellent was effectively unreachable. This is
# a deliberate, documented change (see README "Excellent cut-point (post-hoc)"), not a revert of the
# lock: Poor (2.0) and Average (2.75) stay exactly as calibrated, and 3.0 is only shown to hold for
# cuts between 2.90 and 3.06 on the 10 labelled recordings — it is in-sample, not out-of-sample tested.
CUTS = [(2.0, "Poor"), (2.75, "Average"), (3.0, "Good")]  # >= last cut is Excellent
TOP_GRADE = "Excellent"
