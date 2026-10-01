import json

from app.services.copilot.prompts import MEETING_SYSTEM_PROMPT, SYSTEM_PROMPT, system_prompt_for
from app.services.copilot.suggest import _suggestion_for_mode, meeting_suggestion


def _raw(**overrides):
    base = {
        "is_objection": True,
        "objection_type": "price",
        "urgency": "high",
        "say_this": "¿Caro comparado con qué?",
        "why_it_works": "Ancla el valor.",
        "next_question": "¿Cuánto os cuesta hoy hacerlo a mano?",
        "dont_say": "No bajes precio.",
    }
    base.update(overrides)
    return json.dumps(base)


def test_clear_objection_with_one_short_line_is_shown():
    result = meeting_suggestion(_raw())
    assert result["is_objection"] is True
    assert result["say_this"] == "¿Caro comparado con qué?"


def test_everything_else_stays_silent():
    for raw in (
        _raw(is_objection=False),
        _raw(objection_type="none"),
        _raw(say_this="   "),
        _raw(say_this="x" * 91),
        "not json",
        "",
    ):
        result = meeting_suggestion(raw)
        assert result["is_objection"] is False and result["say_this"] == "", raw


def test_long_follow_up_is_dropped_but_the_line_stays():
    result = meeting_suggestion(_raw(next_question="y" * 120))
    assert result["is_objection"] is True and result["next_question"] == ""


def test_phone_calls_keep_the_existing_coach():
    assert system_prompt_for("speakerphone") is SYSTEM_PROMPT
    assert system_prompt_for("meeting") is MEETING_SYSTEM_PROMPT
    # Phone mode still fills a nudge when parsing fails; meetings never do.
    assert _suggestion_for_mode("not json", "speakerphone")["say_this"]
    assert _suggestion_for_mode("not json", "meeting")["say_this"] == ""


def test_product_questions_are_a_case_of_their_own():
    result = meeting_suggestion(_raw(objection_type="question", say_this="Sí, se conecta con HubSpot y Pipedrive."))
    assert result["is_objection"] is True and result["objection_type"] == "question"


def test_the_meeting_prompt_limits_questions_to_the_offer_context():
    assert '"question"' in MEETING_SYSTEM_PROMPT
    assert "If neither answers it" in MEETING_SYSTEM_PROMPT
