"""One judge call: structured output, cost guard before and after. Nothing is logged but token counts and cost."""
import sys
from typing import Literal, Optional

from anthropic import Anthropic
from dotenv import load_dotenv
from pydantic import BaseModel

from .config import JUDGE_EFFORT, JUDGE_MAX_TOKENS, JUDGE_MODEL, MAX_RUN_USD, PRICES
from .ingest import Cue, fmt_ts
from .rubric import ANCHORS, CRITERIA, SCALE

load_dotenv()

CriterionName = Literal[tuple(CRITERIA)]  # type: ignore[valid-type]


class CostGuardError(RuntimeError):
    pass


class MediaSegment(BaseModel):
    start: str  # HH:MM:SS
    end: str
    note: str


class Evidence(BaseModel):
    quote: str  # verbatim from the transcript
    ts: str  # HH:MM:SS where the quote starts
    speaker: str  # pseudonym, e.g. S1


class Criterion(BaseModel):
    name: CriterionName
    score: Optional[int]  # 1-4, null if not observable
    rationale: str
    evidence: list[Evidence]


class Judgement(BaseModel):
    media_segments: list[MediaSegment]
    estimated_students: int
    names_mentioned: list[str]  # first names of anyone in the class (children, tutor, parents), for local masking
    criteria: list[Criterion]
    holistic_rating: Literal["Poor", "Average", "Good", "Excellent"]
    holistic_reason: str


SYSTEM = f"""You review recordings of 8x8 online chess classes for children (tutor plus 2-8 students on Zoom) and judge teaching quality.

The transcript is Zoom's. Speaker labels are devices, pseudonymised S1, S2... in order of talk time. A label is not a person: siblings and parents may share a device, and one child may appear under several labels. Zoom may attribute played media (YouTube videos) to the tutor.

Work in this order:
1. media_segments: time ranges where played media or a video seems to be speaking (polished narration, long unbroken monologue unlike the tutor's usual style). Never use such text as evidence about the tutor.
2. estimated_students and names_mentioned: every personal first name that appears in the transcript or labels (used only to mask names locally).
3. Score each criterion {SCALE}. Judge fair turns relative to the number of students, mainly from who the tutor addresses by name and calls on, not from label counts alone.
4. holistic_rating: your own overall view, shown only as a cross-check.

Criteria, with what each score looks like (use 4 only when the behaviour is shown consistently and you can quote it):
""" + "\n".join(
    f"- {k}: {v['desc']}\n" + "\n".join(f"    {n}: {ANCHORS[k][n]}" for n in (4, 3, 2, 1)) for k, v in CRITERIA.items()
) + """

Rules:
- Every evidence quote must be copied verbatim from the transcript (5-25 words) with the timestamp where it starts. Give 1-3 quotes per scored criterion; quotes that cannot be found are discarded.
- Refer to children as Student A, B, C in rationales; do not repeat their names.
- Use the full 1-4 scale. Do not default to the middle: a clearly weak or clearly strong class should get a 1 or a 4, not a cautious 2 or 3.
- For rapport_start and lesson_close only, use null ONLY when the coverage line above says that part is absent from the transcript. If the opening or closing is present (or its coverage is unclear) and the tutor simply did not build rapport or did not close the lesson, that is a real teaching gap: score it 1, do not use null to avoid judging it.
- For every other criterion, set it to null rather than guess when the recording does not show it (e.g. welcome_new when nobody new joins)."""


def _pricing(model: str) -> tuple[float, float]:
    if model not in PRICES:
        raise CostGuardError(f"No price configured for {model}; add it to qa/config.py")
    return PRICES[model]


def render_transcript(cues: list[Cue]) -> str:
    return "\n".join(f"[{fmt_ts(c.start)}] {c.speaker}: {c.text}" for c in cues)


def estimate_cost(client: Anthropic, model: str, messages, system: str) -> tuple[int, float]:
    """Worst case: counted input tokens plus the full max_tokens ceiling billed as output."""
    n_in = client.messages.count_tokens(model=model, system=system, messages=messages).input_tokens
    p_in, p_out = _pricing(model)
    return n_in, (n_in * p_in + JUDGE_MAX_TOKENS * p_out) / 1e6


def joiner_hint(late: list[dict]) -> str:
    """Labels and first-speech times only; a hint for welcome_new, not evidence of a new joiner."""
    if not late:
        return "Speakers first heard late (>5 min after class speech began): none.\n"
    items = ", ".join(f"{s['label']} at +{fmt_ts(s['first_s'])}" for s in late)
    return (
        f"Speakers first heard late (>5 min after class speech began): {items}. This is only a hint for "
        "welcome_new: a label may be a child who stayed quiet, or a rejoin on another device. Score "
        "welcome_new only if the transcript shows someone new being welcomed or ignored.\n"
    )


def asr_note(info: dict) -> str:
    note = (
        "This transcript is automatic speech recognition of the audio, not Zoom's: there are no speaker labels "
        "(every line is S1), and names and chess terms may be misheard. Work out who is speaking from context.\n"
    )
    if info.get("partial"):
        note += (
            f"It covers only about {info['covered_pct']}% of the class: the opening, the closing and some windows in between. "
            "Do not judge what you cannot see; use null where a criterion cannot be judged from this sample.\n"
        )
    if info.get("language") and info["language"] != "en":
        note += f"The detected language is '{info['language']}'; quote it verbatim.\n"
    return note


def run_judge(
    cues: list[Cue],
    signals: dict,
    n_students: int | None = None,
    model: str = JUDGE_MODEL,
    coverage: dict | None = None,
    late_speakers: list[dict] | None = None,
    asr: dict | None = None,
):
    """cues must already be pseudonymised. Returns (Judgement, cost_usd)."""
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

    n_in, est = estimate_cost(client, model, messages, SYSTEM)
    print(f"[judge] {model}: {n_in} input tokens, worst-case ${est:.3f}", file=sys.stderr)
    if est > MAX_RUN_USD:
        raise CostGuardError(f"Estimated worst-case ${est:.2f} exceeds the ${MAX_RUN_USD:.2f} limit; run refused.")

    resp = client.messages.parse(
        model=model,
        max_tokens=JUDGE_MAX_TOKENS,
        system=SYSTEM,
        messages=messages,
        output_config={"effort": JUDGE_EFFORT},
        output_format=Judgement,
    )
    p_in, p_out = _pricing(model)
    cost = (resp.usage.input_tokens * p_in + resp.usage.output_tokens * p_out) / 1e6
    print(f"[judge] actual: {resp.usage.input_tokens} in / {resp.usage.output_tokens} out = ${cost:.3f}", file=sys.stderr)
    if resp.stop_reason in ("refusal", "max_tokens") or resp.parsed_output is None:
        raise RuntimeError(f"Judge returned no usable result (stop_reason={resp.stop_reason})")
    return resp.parsed_output, cost
