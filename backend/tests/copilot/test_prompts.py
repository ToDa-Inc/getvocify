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
