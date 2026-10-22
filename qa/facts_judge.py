"""Experimental: a judge that reports only observable facts (counts, timestamps, yes/no), not 1-4
opinions. Facts are mapped to the existing criteria in qa/facts_mapping.py by fixed code rules, not
by the model. This module is not wired into the shipped app (qa/pipeline.py, app.py) - it is reached
only from calibrate_facts.py on the facts-judge branch. See README "Facts judge (experimental)".

Hypothesis under test: 1-4 opinion scores compress and invert Poor/Average; countable facts, scored
by code, may separate better.
"""
import sys
from typing import Literal, Optional

from anthropic import Anthropic
from pydantic import BaseModel

from .config import JUDGE_EFFORT, JUDGE_MAX_TOKENS, JUDGE_MODEL, MAX_RUN_USD
from .ingest import Cue
from .judge import CostGuardError, Evidence, MediaSegment, _pricing, asr_note, estimate_cost, joiner_hint, render_transcript


class FactsJudgement(BaseModel):
    media_segments: list[MediaSegment]
    estimated_students: int
    names_mentioned: list[str]

    first_lesson_content: Evidence  # the first quote where the tutor moves from greetings/chat into the lesson itself
    greeted_by_name: list[Evidence]  # one entry per DISTINCT child the tutor greets by name, anywhere near the start
    check_in_questions: list[Evidence]  # personal check-in questions ("how was your day", "did you finish your puzzle")

    late_joiner_present: bool
    late_joiner_welcome: Optional[Literal["introduced", "welcomed_by_name", "acknowledged", "ignored"]]
    late_joiner_evidence: list[Evidence]  # 0-2 quotes supporting late_joiner_welcome; empty list if no late joiner

    addressed_by_name: list[Evidence]  # one entry per DISTINCT child addressed by name anywhere in the whole class
    named_child_questions: list[Evidence]  # one entry per question put to a specifically named child

    specific_praise: list[Evidence]  # praise naming what the child did ("good, you spotted the fork")
    generic_praise: list[Evidence]  # praise with no specifics ("good job", "nice")
    flat_acknowledgements: list[Evidence]  # "okay, next", "alright", moving on with no praise at all

    recap: bool
    recap_evidence: list[Evidence]
    homework_set: bool
    homework_evidence: list[Evidence]
    goodbye: bool
    goodbye_evidence: list[Evidence]


SYSTEM_FACTS = """You review recordings of 8x8 online chess classes for children (tutor plus 2-8 students on Zoom) and extract OBSERVABLE FACTS - not opinions or 1-4 scores. Every fact that isn't a single-document timestamp must carry a verbatim quote (5-25 words) and the timestamp where it starts; quotes that cannot be confirmed in the transcript are discarded before anything is scored.

The transcript is Zoom's. Speaker labels are devices, pseudonymised S1, S2... in order of talk time. A label is not a person: siblings and parents may share a device, and one child may appear under several labels. Zoom may attribute played media (YouTube videos) to the tutor - never report these as facts about the tutor; instead list the time range in media_segments.

Report these facts, each as a count (give one Evidence item per instance, do not just give a number) or yes/no with its own evidence:
- first_lesson_content: the single quote where the tutor stops greeting/chatting and starts the lesson itself (the first chess content, instruction, or revision). If the class never has a distinct greeting phase, pick the first substantive tutor line.
- greeted_by_name: one quote per DISTINCT child the tutor greets by name (anywhere the tutor does so, not just before first_lesson_content - timing is decided in code from the timestamps).
- check_in_questions: personal questions about the child, not chess ("how are you", "did you have a good day"), as opposed to a chess question.
- late_joiner_present (bool) and late_joiner_welcome: "introduced" if the joiner is invited to introduce themselves and does, "welcomed_by_name" if greeted by name but not invited to introduce themselves, "acknowledged" if only noticed in passing (e.g. "oh someone joined"), "ignored" if a join is evident but not acknowledged at all. null/false if nobody joins late.
- addressed_by_name: one quote per DISTINCT child addressed by name anywhere in the class (for information; a label may be a device, not a person, so under-count rather than guess).
- named_child_questions: one quote per question asked to a specifically named child (not the group).
- specific_praise: praise naming what the child did or got right.
- generic_praise: praise with no specifics ("good job", "nice", "well done" with nothing attached).
- flat_acknowledgements: "okay, next", "alright", moving on with no praise or reaction at all.
- recap/homework_set/goodbye (bool, each with its own evidence): recap of what was learned; homework given; a goodbye/sign-off at the end.

Do not infer or round up: if you cannot quote it, it did not happen. estimated_students and names_mentioned (every personal first name AND every spelling variant/misspelling you see, for local masking) are still needed."""


def run_facts_judge(
    cues: list[Cue],
    signals: dict,
    n_students: int | None = None,
    model: str = JUDGE_MODEL,
    coverage: dict | None = None,
    late_speakers: list[dict] | None = None,
    asr: dict | None = None,
):
    """cues must already be pseudonymised. Returns (FactsJudgement, cost_usd). Mirrors qa.judge.run_judge."""
    client = Anthropic()
    hint = f"Teacher-supplied class size: {n_students}.\n" if n_students else ""
    cov = (
        f"Coverage computed from timestamps: opening of the class {coverage['start']}, closing {coverage['end']}.\n"
        if coverage
        else ""
    )
    joiners = joiner_hint(late_speakers) if late_speakers is not None else ""
    asr_txt = asr_note(asr) if asr else ""
    sig = f"Approximate signals (include played media, so treat as rough): {signals}\n\n" if signals else ""
    user = f"{hint}{cov}{joiners}{asr_txt}{sig}TRANSCRIPT:\n{render_transcript(cues)}"
    messages = [{"role": "user", "content": user}]

    n_in, est = estimate_cost(client, model, messages, SYSTEM_FACTS)
    print(f"[facts-judge] {model}: {n_in} input tokens, worst-case ${est:.3f}", file=sys.stderr)
    if est > MAX_RUN_USD:
        raise CostGuardError(f"Estimated worst-case ${est:.2f} exceeds the ${MAX_RUN_USD:.2f} limit; run refused.")

    resp = client.messages.parse(
        model=model,
        max_tokens=JUDGE_MAX_TOKENS,
        system=SYSTEM_FACTS,
        messages=messages,
        output_config={"effort": JUDGE_EFFORT},
        output_format=FactsJudgement,
    )
    p_in, p_out = _pricing(model)
    cost = (resp.usage.input_tokens * p_in + resp.usage.output_tokens * p_out) / 1e6
    print(f"[facts-judge] actual: {resp.usage.input_tokens} in / {resp.usage.output_tokens} out = ${cost:.3f}", file=sys.stderr)
    if resp.stop_reason in ("refusal", "max_tokens") or resp.parsed_output is None:
        raise RuntimeError(f"Facts judge returned no usable result (stop_reason={resp.stop_reason})")
    return resp.parsed_output, cost
