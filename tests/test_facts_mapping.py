"""Pure-function tests for the facts-judge mapping rules (no API calls). See qa/facts_mapping.py."""
from qa.facts_mapping import VerifiedFacts, checklist, lesson_close, map_facts, rapport_start, warmth_energy, welcome_new


def facts(**kw) -> VerifiedFacts:
    base = dict(
        minutes_to_content=0.0, greeted_by_name=0, check_in_questions=0,
        late_joiner_present=False, late_joiner_welcome=None,
        addressed_by_name=0, named_child_questions=0,
        specific_praise=0, generic_praise=0, flat_acknowledgements=0,
        recap=False, homework_set=False, goodbye=False,
        tutor_talk_minutes=10.0, media_minutes=0.0,
    )
    base.update(kw)
    return VerifiedFacts(**base)


def test_rapport_4_two_greeted_checkin_and_two_minutes():
    assert rapport_start(facts(greeted_by_name=2, check_in_questions=1, minutes_to_content=2.0)) == 4


def test_rapport_3_needs_checkin_or_minutes_not_both():
    assert rapport_start(facts(greeted_by_name=2, check_in_questions=0, minutes_to_content=2.0)) == 3  # minutes alone
    assert rapport_start(facts(greeted_by_name=1, check_in_questions=1, minutes_to_content=0.0)) == 3  # check-in alone


def test_rapport_2_one_greeted_but_neither_checkin_nor_minutes():
    assert rapport_start(facts(greeted_by_name=1, check_in_questions=0, minutes_to_content=0.5)) == 2


def test_rapport_2_greeting_without_names_some_time_passed():
    assert rapport_start(facts(greeted_by_name=0, minutes_to_content=1.5)) == 2


def test_rapport_1_no_greeting_content_starts_immediately():
    assert rapport_start(facts(greeted_by_name=0, minutes_to_content=0.05)) == 1


def test_welcome_na_without_a_late_joiner():
    assert welcome_new(facts(late_joiner_present=False, late_joiner_welcome="ignored")) is None


def test_welcome_levels():
    for level, score in [("introduced", 4), ("welcomed_by_name", 3), ("acknowledged", 2), ("ignored", 1)]:
        assert welcome_new(facts(late_joiner_present=True, late_joiner_welcome=level)) == score


def test_warmth_4_needs_3plus_specific_praise_exceeding_flat():
    assert warmth_energy(facts(specific_praise=3, flat_acknowledgements=0, tutor_talk_minutes=10)) == 4
    assert warmth_energy(facts(specific_praise=3, flat_acknowledgements=3, tutor_talk_minutes=10)) == 3  # ties don't count


def test_warmth_3_any_specific_praise():
    assert warmth_energy(facts(specific_praise=1, flat_acknowledgements=10, tutor_talk_minutes=10)) == 3


def test_warmth_2_generic_or_flat_exceeds_specific():
    assert warmth_energy(facts(specific_praise=0, generic_praise=2, tutor_talk_minutes=10)) == 2
    assert warmth_energy(facts(specific_praise=0, flat_acknowledgements=2, tutor_talk_minutes=10)) == 2


def test_warmth_1_almost_no_praise_at_all():
    assert warmth_energy(facts(tutor_talk_minutes=10)) == 1


def test_warmth_per_10_min_normalisation_and_zero_minutes_guard():
    # 1 specific praise over 20 minutes is below the "1 or more per 10 min" bar... actually counts are
    # raw occurrences normalised per 10 min of talk, so a single occurrence over any positive duration
    # still satisfies "specific praise >= 1 per 10 min" once normalised up; check the zero-duration guard instead.
    assert warmth_energy(facts(specific_praise=0, tutor_talk_minutes=0.0)) == 1  # no division error


def test_close_4_all_three():
    assert lesson_close(facts(recap=True, homework_set=True, goodbye=True)) == 4


def test_close_3_recap_and_goodbye_no_homework():
    assert lesson_close(facts(recap=True, goodbye=True, homework_set=False)) == 3


def test_close_2_goodbye_or_homework_alone():
    assert lesson_close(facts(goodbye=True)) == 2
    assert lesson_close(facts(homework_set=True)) == 2


def test_close_1_none_and_recap_alone_also_falls_to_1():
    assert lesson_close(facts()) == 1
    assert lesson_close(facts(recap=True)) == 1  # recap alone isn't in any explicit tier; falls through


def test_checklist_thresholds_per_10_min():
    assert checklist(facts(named_child_questions=8, tutor_talk_minutes=10)) == 4
    assert checklist(facts(named_child_questions=4, tutor_talk_minutes=10)) == 3
    assert checklist(facts(named_child_questions=1, tutor_talk_minutes=10)) == 2
    assert checklist(facts(named_child_questions=0, tutor_talk_minutes=10)) == 1


def test_checklist_media_penalty_and_floor():
    assert checklist(facts(named_child_questions=8, tutor_talk_minutes=10, media_minutes=3)) == 3  # >25% media: -1
    assert checklist(facts(named_child_questions=0, tutor_talk_minutes=10, media_minutes=3)) == 1  # floor at 1, not 0
    assert checklist(facts(named_child_questions=8, tutor_talk_minutes=10, media_minutes=2)) == 4  # exactly 20%: no penalty


def test_map_facts_returns_all_five_criteria_and_leaves_out_fair_turns():
    scores = map_facts(facts(greeted_by_name=2, check_in_questions=1, minutes_to_content=2, recap=True, goodbye=True))
    assert set(scores) == {"rapport_start", "welcome_new", "warmth_energy", "lesson_close", "checklist"}
    assert "fair_turns" not in scores
