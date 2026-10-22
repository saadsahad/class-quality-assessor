"""Facts pipeline: evidence verification, before-content filtering, and the verified-bool rule
(judge's claim is required but on its own isn't enough - at least one quote must survive verification)."""
from qa.facts_judge import Evidence, FactsJudgement
from qa.facts_pipeline import assess_facts_vtt

VTT = """WEBVTT

1
00:00:05.000 --> 00:00:09.000
S1: Good evening everyone, welcome to class

2
00:00:12.000 --> 00:00:16.000
S1: Ria how was your day today

3
00:00:20.000 --> 00:00:24.000
S2: it was good thank you

4
00:02:30.000 --> 00:02:35.000
S1: okay let's begin with the knight move today

5
00:05:00.000 --> 00:05:05.000
S1: great job Ria you found the fork

6
00:40:00.000 --> 00:40:05.000
S1: that is all for today, bye everyone
"""


def ev(quote, ts, speaker="S1"):
    return Evidence(quote=quote, ts=ts, speaker=speaker)


def base_judgement(**overrides):
    kw = dict(
        media_segments=[], estimated_students=1, names_mentioned=["Ria"],
        first_lesson_content=ev("okay let's begin with the knight move today", "00:02:30"),
        greeted_by_name=[ev("Ria how was your day today", "00:00:12")],
        check_in_questions=[ev("Ria how was your day today", "00:00:12")],
        late_joiner_present=False, late_joiner_welcome=None, late_joiner_evidence=[],
        addressed_by_name=[ev("great job Ria you found the fork", "00:05:00")],
        named_child_questions=[],
        specific_praise=[ev("great job Ria you found the fork", "00:05:00")],
        generic_praise=[], flat_acknowledgements=[],
        recap=False, recap_evidence=[],
        homework_set=False, homework_evidence=[],
        goodbye=True, goodbye_evidence=[ev("that is all for today, bye everyone", "00:40:00")],
    )
    kw.update(overrides)
    return FactsJudgement(**kw)


def run(monkeypatch, judgement, **kw):
    import qa.facts_pipeline as fp

    monkeypatch.setattr(fp, "run_facts_judge", lambda *a, **k: (judgement, 0.02))
    return assess_facts_vtt(VTT, **kw)


def test_evidence_before_content_is_counted_evidence_after_is_not(monkeypatch):
    # greeted_by_name's quote (00:00:12) is before first_lesson_content (00:02:30): counted.
    r = run(monkeypatch, base_judgement())
    assert r["facts"].greeted_by_name == 1 and r["facts"].check_in_questions == 1
    # move the same greeting to AFTER content starts: it should no longer count toward rapport
    late_greet = base_judgement(greeted_by_name=[ev("Ria how was your day today", "00:05:30")])
    r2 = run(monkeypatch, late_greet)
    assert r2["facts"].greeted_by_name == 0


def test_unconfirmed_quote_is_dropped_and_not_counted(monkeypatch):
    fabricated = base_judgement(specific_praise=[ev("you are a chess grandmaster already", "00:05:00")])
    r = run(monkeypatch, fabricated)
    assert r["facts"].specific_praise == 0
    assert r["facts"].notes["dropped"]["specific_praise"] == 1


def test_bool_fact_requires_a_verified_quote_not_just_the_judges_claim(monkeypatch):
    # recap=True claimed, but the supporting quote is fabricated -> recap must end up False
    claimed_not_verified = base_judgement(recap=True, recap_evidence=[ev("we covered everything perfectly today", "00:40:00")])
    r = run(monkeypatch, claimed_not_verified)
    assert r["facts"].recap is False
    # goodbye=True with a real quote stays True
    assert r["facts"].goodbye is True


def test_late_joiner_requires_verified_evidence_too(monkeypatch):
    claimed = base_judgement(
        late_joiner_present=True, late_joiner_welcome="introduced",
        late_joiner_evidence=[ev("completely made up late joiner line", "00:10:00")],
    )
    r = run(monkeypatch, claimed)
    assert r["facts"].late_joiner_present is False and r["facts"].late_joiner_welcome is None


def test_media_minutes_computed_from_media_segments(monkeypatch):
    from qa.facts_judge import MediaSegment

    j = base_judgement(media_segments=[MediaSegment(start="00:10:00", end="00:13:00", note="video")])
    r = run(monkeypatch, j)
    assert r["facts"].media_minutes == 3.0


def test_names_are_masked_in_the_result(monkeypatch):
    r = run(monkeypatch, base_judgement())
    assert "Ria" not in str(r)


def test_first_lesson_content_falls_back_to_class_start_if_unverified(monkeypatch):
    j = base_judgement(first_lesson_content=ev("this exact sentence is nowhere in the transcript", "00:02:30"))
    r = run(monkeypatch, j)
    assert r["facts"].notes["content_quote_verified"] is False
    assert r["facts"].minutes_to_content == 0.0
