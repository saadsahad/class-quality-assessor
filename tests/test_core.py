from qa.ingest import parse_vtt
from qa.score import compute_rating
from qa.verify import verify_evidence

VTT = """WEBVTT

1
00:00:05.000 --> 00:00:09.000
Tutor A: Good evening everyone, welcome to class

2
00:00:09.500 --> 00:00:12.000
Tutor A: so happy to see you all today

3
00:00:40.000 --> 00:00:44.000
Device 2: can I play next please

4
01:00:00.000 --> 01:00:03.000
Tutor A: Let us look at this video now
"""


def cues():
    return parse_vtt(VTT)


def test_parse_vtt_speakers_and_times():
    c = cues()
    assert len(c) == 4
    assert c[0].speaker == "Tutor A" and c[0].start == 5.0
    assert c[2].speaker == "Device 2" and c[2].text == "can I play next please"
    assert c[3].start == 3600.0


def test_verify_paraphrase_split_cue_and_fabrication():
    ev = [
        {"quote": "welcome to class so happy to see you all", "ts": 8},  # spans two cues
        {"quote": "Good evening everyone, welcome to class!", "ts": 6},  # punctuation differs
        {"quote": "you are all champions of the world", "ts": 8},  # invented
        {"quote": "can I play next please", "ts": 300},  # real quote, wrong time
    ]
    kept, dropped = verify_evidence(ev, cues())
    assert len(kept) == 2
    assert {d["reason"] for d in dropped} == {"not found near timestamp"}


def test_verify_rejects_media_and_short_quotes():
    ev = [
        {"quote": "Let us look at this video now", "ts": 3601},
        {"quote": "good evening", "ts": 6},
    ]
    kept, dropped = verify_evidence(ev, cues(), media_segments=[(3590, 3700)])
    assert not kept
    assert [d["reason"] for d in dropped] == ["inside media playback", "quote too short or missing timestamp"]


def test_score_renormalises_na():
    s = {"rapport_start": 4, "welcome_new": None, "warmth_energy": 4, "fair_turns": 4, "lesson_close": 4, "checklist": 4}
    r = compute_rating(s)
    assert r["weighted"] == 4.0 and r["grade"] == "Excellent" and r["na"] == ["welcome_new"]


def test_score_insufficient():
    assert compute_rating({"checklist": 3})["grade"] is None


def test_camera_penalty_drops_a_grade_near_boundary():
    s = {"rapport_start": 3, "welcome_new": 3, "warmth_energy": 3, "fair_turns": 3, "lesson_close": 3, "checklist": 3}
    assert compute_rating(s)["grade"] == "Good"
    r = compute_rating(s, camera_issue=True)
    assert r["grade"] == "Average" and r["penalty"] == 0.5


def test_pseudonymise_and_signals():
    from qa.signals import compute_signals, pseudonymise

    anon, mapping = pseudonymise(cues())
    assert mapping["Tutor A"] == "S1" and all(c.speaker in {"S1", "S2"} for c in anon)
    sig = compute_signals(anon, media=[(3590, 3700)])
    assert sig["most_talkative_label"] == "S1" and sig["distinct_speaker_labels"] == 2


def test_cost_guard_refuses(monkeypatch):
    import pytest

    from qa import judge

    class FakeClient:
        class messages:
            @staticmethod
            def count_tokens(**kw):
                class R:
                    input_tokens = 5_000_000

                return R

    monkeypatch.setattr(judge, "Anthropic", lambda: FakeClient)
    with pytest.raises(judge.CostGuardError):
        judge.run_judge(cues(), {}, model="claude-sonnet-5-5")


def test_masker_names_and_labels():
    from qa.privacy import Masker, names_from_labels

    from_labels = names_from_labels(["Aarav's iPad", "Tutor Meera", "iPhone 12"])
    assert from_labels == {"aarav", "meera"}
    m = Masker(from_labels | {"Zoya"})
    out = m.text("Well done Aarav! Zoya, and aarav's turn, thanks Meera")
    assert "arav" not in out.lower() and "zoya" not in out.lower() and "meera" not in out.lower()
    assert out.count("[Name A]") == 2  # same name, same tag
    assert "Zoya" not in str(m.obj({"q": ["Zoya"]}))


def test_pipeline_caps_unverified_high_scores_and_masks(monkeypatch):
    from qa import pipeline
    from qa.judge import Criterion, Evidence, Judgement

    def crit(name, score, quotes):
        return Criterion(name=name, score=score, rationale="Aarav did well", evidence=quotes)

    good = Evidence(quote="welcome to class so happy to see you all", ts="00:00:08", speaker="S1")
    fake = Evidence(quote="you are all champions of the world", ts="00:00:08", speaker="S1")
    j = Judgement(
        media_segments=[], estimated_students=3, names_mentioned=["Aarav"],
        criteria=[
            crit("rapport_start", 4, [good]),      # verified: stays 4
            crit("warmth_energy", 4, [fake]),      # unverified high: capped to 2
            crit("fair_turns", 1, []),             # low, no quote: kept, based on absence
        ],
        holistic_rating="Good", holistic_reason="Aarav was great",
    )
    monkeypatch.setattr(pipeline, "run_judge", lambda *a, **k: (j, 0.01))
    r = pipeline.assess_vtt(VTT)
    c = r["criteria"]
    assert c["rapport_start"]["score"] == 4
    assert c["warmth_energy"]["score"] == 2 and c["warmth_energy"]["note"].startswith("capped")
    assert c["fair_turns"]["score"] == 1 and c["fair_turns"]["note"] == "based on absence"
    assert "Aarav" not in str(r)


def test_coverage_from_data():
    from qa.coverage import check_coverage
    from qa.ingest import Cue

    def cue(t, text):
        return Cue(t, t + 3, "S1", text)

    full = [cue(10, "Hello everyone"), cue(14, "Hi, welcome back"), cue(1500, "ok"), cue(3200, "Bye everyone, see you next week")]
    c = check_coverage(full, media_duration_s=3210)
    assert (c["start"], c["end"]) == ("present", "present")

    # tutor skips the greeting but speech starts at 0: that is poor rapport, not missing data
    no_greet = [cue(0, "Let us revise the last class"), cue(50, "now the pawn"), cue(3000, "that is it")]
    c = check_coverage(no_greet, media_duration_s=3003)
    assert (c["start"], c["end"]) == ("unclear", "unclear")

    # speech starts 15 min in with no greeting; transcript stops 10 min before media ends
    partial = [cue(900, "so the knight moves"), cue(950, "like this"), cue(2000, "good move")]
    c = check_coverage(partial, media_duration_s=2700)
    assert (c["start"], c["end"]) == ("absent", "absent")
    assert check_coverage(partial)["end"] == "unclear"  # no media length -> cannot call it absent


def test_pipeline_forces_na_when_part_absent(monkeypatch):
    from qa import pipeline
    from qa.judge import Criterion, Judgement

    j = Judgement(
        media_segments=[], estimated_students=3, names_mentioned=[],
        criteria=[Criterion(name="rapport_start", score=3, rationale="x", evidence=[]),
                  Criterion(name="fair_turns", score=1, rationale="x", evidence=[])],
        holistic_rating="Average", holistic_reason="x",
    )
    monkeypatch.setattr(pipeline, "run_judge", lambda *a, **k: (j, 0.0))
    late = "WEBVTT\n\n1\n00:15:00.000 --> 00:15:04.000\nS: so the knight moves like this\n\n2\n00:16:00.000 --> 00:16:04.000\nS: and the bishop too\n"
    r = pipeline.assess_vtt(late)
    assert r["criteria"]["rapport_start"]["score"] is None and r["criteria"]["rapport_start"]["note"].startswith("N/A")
    assert r["criteria"]["fair_turns"]["score"] == 1


def test_late_joiner_candidates():
    from qa.ingest import Cue
    from qa.joiners import late_joiner_candidates

    cues = [Cue(0, 3, "S1", "hello"), Cue(10, 12, "S2", "hi"), Cue(400, 403, "S3", "hello everyone"), Cue(500, 502, "S3", "ok")]
    late = late_joiner_candidates(cues)
    assert [s["label"] for s in late] == ["S3"] and late[0]["utterances"] == 2


def test_joiner_hint_labels_and_times_only():
    from qa.judge import joiner_hint

    h = joiner_hint([{"label": "S4", "first_s": 2523, "utterances": 9, "words": 36, "late": True}])
    assert "S4 at +00:42:03" in h and "utterances" not in h and "36" not in h
    assert "none" in joiner_hint([])


def test_borderline_band():
    # Cuts are [(2.0, Poor), (2.75, Average), (3.0, Good)] (Excellent cut moved to 3.0 post-hoc).
    from qa.score import borderline

    assert borderline(2.85) == ("Average", "Good")  # 0.10 above the 2.75 cut
    assert borderline(2.55) == ("Average", "Good")  # 0.20 below it
    assert borderline(2.95) == ("Good", "Excellent")  # 0.05 below the 3.0 cut
    assert borderline(3.0) == ("Good", "Excellent")  # exactly at the 3.0 cut counts as borderline
    assert borderline(2.49) is None  # 0.26 and 0.49 from the nearest cuts


def test_allowlisted_words_never_masked_even_if_reported_as_names():
    from qa.privacy import Masker

    m = Masker({"video", "rook", "queen", "check"})
    out = m.text("The video was choppy today, let's check the rook and protect the queen")
    assert out == "The video was choppy today, let's check the rook and protect the queen"


def test_real_names_still_masked_alongside_allowlist():
    from qa.privacy import Masker

    m = Masker({"video", "Aarav"})
    out = m.text("The video was choppy while Aarav was speaking")
    assert "video" in out and "Aarav" not in out and "[Name A]" in out


def test_names_from_labels_excludes_allowlisted_tokens():
    from qa.privacy import names_from_labels

    assert names_from_labels(["Video's iPad", "Rook Device"]) == {"device"}


def test_coverage_gated_null_forced_to_one_when_part_is_present():
    from qa import pipeline
    from qa.judge import Criterion, Judgement

    j = Judgement(
        media_segments=[], estimated_students=2, names_mentioned=[],
        criteria=[
            Criterion(name="rapport_start", score=None, rationale="no greeting shown", evidence=[]),
            Criterion(name="lesson_close", score=None, rationale="abrupt stop", evidence=[]),
        ],
        holistic_rating="Average", holistic_reason="x",
    )
    import qa.pipeline as pl

    pl.run_judge = lambda *a, **k: (j, 0.0)
    r = pl.assess_vtt(VTT)  # VTT fixture covers start and end (greet + goodbye present)
    assert r["criteria"]["rapport_start"]["score"] == 1
    assert "scored 1" in r["criteria"]["rapport_start"]["note"]
    assert r["criteria"]["lesson_close"]["score"] == 1


def test_coverage_gated_null_stays_na_when_asr_partial():
    from qa import pipeline
    from qa.judge import Criterion, Judgement

    j = Judgement(
        media_segments=[], estimated_students=2, names_mentioned=[],
        criteria=[Criterion(name="rapport_start", score=None, rationale="x", evidence=[])],
        holistic_rating="Average", holistic_reason="x",
    )
    pipeline.run_judge = lambda *a, **k: (j, 0.0)
    r = pipeline.assess_vtt(VTT, transcript_info={"partial": True, "covered_pct": 40, "mode": "sampled"})
    assert r["criteria"]["rapport_start"]["score"] is None
    assert "low confidence" in r["criteria"]["rapport_start"]["note"]


def test_adaptive_median_of_3_triggers_on_borderline_and_not_otherwise(monkeypatch):
    from qa import pipeline
    from qa.judge import Criterion, Evidence, Judgement
    from qa.rubric import CRITERIA

    # a verified quote on every criterion so the "no verified quote" cap never interferes with the median
    ev = [Evidence(quote="so happy to see you all today", ts="00:00:09", speaker="S1")]

    def judgement_with(rapport, base=2):
        return Judgement(
            media_segments=[], estimated_students=2, names_mentioned=[],
            criteria=[
                Criterion(name=k, score=rapport if k == "rapport_start" else base, rationale="x", evidence=ev)
                for k in CRITERIA
            ],
            holistic_rating="Good", holistic_reason="x",
        )

    calls = {"n": 0}

    def fake_judge(*a, **k):
        calls["n"] += 1
        # alternate 1 and 2 on rapport_start across the 3 runs so the median (2) differs from run 1 (1)
        return judgement_with([1, 2, 1][(calls["n"] - 1) % 3]), 0.01

    monkeypatch.setattr(pipeline, "run_judge", fake_judge)
    calls["n"] = 0
    r = pipeline.assess_vtt(VTT)
    assert r["median_of_3"] is True and calls["n"] == 3
    assert r["criteria"]["rapport_start"]["score"] == 1  # median of [1, 2, 1]

    def fake_judge_far(*a, **k):
        calls["n"] += 1
        return judgement_with(4, base=4), 0.01  # every criterion 4 -> weighted (4.0) far from any cut, no retry needed

    monkeypatch.setattr(pipeline, "run_judge", fake_judge_far)
    calls["n"] = 0
    r2 = pipeline.assess_vtt(VTT)
    assert r2["median_of_3"] is False and calls["n"] == 1
