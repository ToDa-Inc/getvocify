"""Copilot suggest prompt contract (SYSTEM_PROMPT JSON shape)."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-copilot-32-chars")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-copilot-32-chars")

from app.services.copilot.prompts import SYSTEM_PROMPT, build_user_prompt


def test_system_prompt_json_shape_includes_playbook_grounding_fields():
    assert '"evidence_refs": array of strings' in SYSTEM_PROMPT
    assert '"source_id": string or null' in SYSTEM_PROMPT
    assert "evidence_refs to []" in SYSTEM_PROMPT


def test_user_prompt_without_playbook_omits_playbook_suffix():
    prompt = build_user_prompt(
        transcript_window="Them: hola",
        latest_turn="Them: hola",
        product_context=None,
        language="es",
        call_mode="meeting",
    )
    assert "PLAYBOOK (the team's approved answers)" not in prompt


def test_user_prompt_with_playbook_carries_each_approved_answer():
    prompt = build_user_prompt(
        transcript_window="Them: caro",
        latest_turn="Them: caro",
        product_context=None,
        language="es",
        call_mode="meeting",
        playbook_snapshot={
            "entries": [
                {"entry_id": "objection:price", "category": "price", "guidance": "¿Comparado con qué lo estás mirando?"},
                {"entry_id": "objection:timing", "category": "timing", "guidance": ""},
            ],
        },
    )
    assert "PLAYBOOK (the team's approved answers)" in prompt
    assert "- objection:price · price: ¿Comparado con qué lo estás mirando?" in prompt
    # An entry with nothing to say out loud is never offered as an answer.
    assert "objection:timing" not in prompt


def test_user_prompt_with_playbook_but_no_answers_says_so():
    prompt = build_user_prompt(
        transcript_window="Them: caro",
        latest_turn="Them: caro",
        product_context=None,
        language="es",
        call_mode="meeting",
        playbook_snapshot={"entries": []},
    )
    assert "(no approved answers yet)" in prompt


def test_meeting_help_is_said_for_this_conversation_not_copied():
    from app.services.copilot.prompts import MEETING_SYSTEM_PROMPT, PLAYBOOK_USER_SUFFIX

    # A line that would fit any call is wrong: it ties to what this prospect said.
    assert "something specific this prospect said" in MEETING_SYSTEM_PROMPT
    # An objection never comes back with nothing to say (the card would vanish).
    assert "Never return an objection with an empty say_this" in MEETING_SYSTEM_PROMPT
    # The playbook gives the approach, not the words to paste.
    assert "adapted only so it fits" not in PLAYBOOK_USER_SUFFIX
    assert "follows that answer's approach" in PLAYBOOK_USER_SUFFIX


def test_a_meeting_line_a_little_over_the_asked_length_is_kept_not_silenced():
    import json

    from app.services.copilot.suggest import meeting_suggestion

    # Tied to the call, lines run longer than the 90 asked for; silencing them withdrew the card
    # the rep was already looking at (2026-10-03 test: the question and trust cards).
    line = "Entiendo el miedo con vuestros ocho comerciales en clínicas dentales: ¿qué os preocupa que escriba mal en HubSpot?"
    result = meeting_suggestion(json.dumps({"is_objection": True, "objection_type": "trust", "say_this": line}))
    assert result["say_this"] == line
    rambling = "x " * 120
    assert meeting_suggestion(json.dumps({"is_objection": True, "objection_type": "trust", "say_this": rambling}))["is_objection"] is False


def test_live_help_reasoning_follows_the_setting(monkeypatch):
    from app.config import settings
    from app.services.copilot import suggest

    # Gemini Flash-Lite refuses "none"; GPT-6 Luna is ~1 s slower to its first word with "minimal".
    monkeypatch.setattr(settings, "COPILOT_REASONING_EFFORT", None, raising=False)
    assert suggest.live_reasoning() == {"reasoning": {"effort": "minimal"}}
    monkeypatch.setattr(settings, "COPILOT_REASONING_EFFORT", "none", raising=False)
    assert suggest.live_reasoning() == {"reasoning": {"effort": "none"}}


def test_the_live_card_asks_the_model_for_one_line_only():
    from app.services.copilot.prompts import MEETING_SYSTEM_PROMPT

    # Every extra field is time the rep waits and text that pulls their eyes off the call.
    output = MEETING_SYSTEM_PROMPT.split("OUTPUT", 1)[1]
    for field in ("why_it_works", "next_question", "dont_say", "urgency", "evidence_refs"):
        assert field not in output, field
    assert '"say_this"' in output and '"source_id"' in output
    # Calm and predictable: it never argues with the prospect.
    assert "Never argue" in MEETING_SYSTEM_PROMPT


def test_live_answers_are_repeatable():
    from app.services.copilot.suggest import temperature_for

    # The same moment gets the same kind of line; the older phone coach keeps its setting.
    assert temperature_for("meeting") == temperature_for("softphone") == 0.1
    assert temperature_for("speakerphone") == 0.35


def test_finalize_keeps_the_line_on_a_desktop_phone_call():
    from app.services.copilot.grounding import finalize_suggest_result

    line = {"is_objection": True, "objection_type": "price", "say_this": "¿Caro comparado con qué?"}
    result = finalize_suggest_result(call_mode="softphone", suggestion=line, latest_turn="me parece caro")
    assert result["suggestion"]["say_this"] == "¿Caro comparado con qué?"


def test_an_approved_answer_is_never_swapped_for_a_tactic_of_the_models_own():
    from app.services.copilot.prompts import MEETING_SYSTEM_PROMPT

    # 2026-10-05: with "go straight to one sharp question" the price card asked "what would be
    # reasonable?" instead of the team's "it depends on your team; exact price in the demo".
    assert "Keep its idea and its claims" in MEETING_SYSTEM_PROMPT
