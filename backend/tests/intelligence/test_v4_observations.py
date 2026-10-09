"""C04 v4 (PLAYBOOK_OBSERVATIONS_ENABLED): named competitors and one observation per
playbook step. Before this, both were hardcoded [] - no adherence, missed steps,
checklist or named competitors could ever come from a real conversation."""

from __future__ import annotations

import asyncio
import json
import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-intelligence-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-intelligence-32")

from app.services.coaching.score_assembly import coaching_lines
from app.services.intelligence.extract import (
    OBSERVATIONS_PROMPT_VERSION,
    PROMPT_VERSION,
    build_messages,
    extract_intelligence,
    is_current,
    shape_intelligence,
)

TRANSCRIPT = (
    "You: Hola Marina, soy Lucía de Vocify, ¿tienes dos minutos? "
    "Them: Sí, dime. You: ¿Cómo gestionáis hoy los leads que no contestan? "
    "Them: Fatal, ya usamos Ringover pero se nos quedan leads sin llamar. "
    "You: Vale, te mando información. Them: Perfecto, gracias."
)
STEPS = [
    {"step_id": "opening", "label": "Apertura", "criterion": "Se presenta y pide permiso"},
    {"step_id": "pain", "label": "Descubrir el dolor", "criterion": "Consigue que nombre un problema"},
    {"step_id": "meeting", "label": "Agendar la reunión", "criterion": "Propone día y hora y el prospecto acepta"},
    {"step_id": "qualify", "label": "Cualificar", "criterion": "Confirma quién decide"},
]
MEMO = {"id": "memo-1", "transcript": TRANSCRIPT, "extraction": {"summary": "s"}}


def _raw(**extra):
    return {"interest": "medium", "objections": [], "commitments": [], **extra}


def test_observations_keep_only_what_the_transcript_backs():
    shaped = shape_intelligence(
        MEMO,
        _raw(playbook_observations=[
            {"step_id": "opening", "status": "met", "quote": "soy Lucía de Vocify, ¿tienes dos minutos?"},
            {"step_id": "pain", "status": "met", "quote": "se nos quedan leads sin llamar"},  # prospect's words
            {"step_id": "meeting", "status": "missed", "quote": "Vale, te mando información."},
            {"step_id": "ghost", "status": "met", "quote": "Hola"},  # not a playbook step
        ]),
        prompt_version=OBSERVATIONS_PROMPT_VERSION,
        playbook_steps=STEPS,
    )
    by_step = {obs["step_id"]: obs for obs in shaped["playbook_observations"]}
    assert list(by_step) == ["opening", "pain", "meeting", "qualify"]
    assert by_step["opening"]["status"] == "met" and by_step["opening"]["evidence_refs"]
    # "met" needs the rep's own words: a prospect quote is not evidence the rep did it.
    assert by_step["pain"]["status"] == "unknown" and by_step["pain"]["evidence_refs"] == []
    assert by_step["meeting"]["status"] == "missed" and by_step["meeting"]["quote"] == "Vale, te mando información."
    # A step the model skipped is unknown, so coverage stays honest.
    assert by_step["qualify"]["status"] == "unknown"
    evidence_ids = {item["id"] for item in shaped["evidence"]}
    assert set(by_step["opening"]["evidence_refs"]) <= evidence_ids


def test_a_fabricated_quote_downgrades_to_unknown():
    shaped = shape_intelligence(
        MEMO,
        _raw(playbook_observations=[{"step_id": "meeting", "status": "missed", "quote": "nunca dijo esto"}]),
        prompt_version=OBSERVATIONS_PROMPT_VERSION,
        playbook_steps=STEPS[2:3],
    )
    assert shaped["playbook_observations"][0]["status"] == "unknown"


def test_named_competitors_need_their_quote_and_are_deduplicated():
    shaped = shape_intelligence(
        MEMO,
        _raw(competitor_mentions=[
            {"name": "Ringover", "quote": "ya usamos Ringover"},
            {"name": "ringover", "quote": "ya usamos Ringover"},
            {"name": "Aircall", "quote": "usamos Aircall"},  # not said
        ]),
        prompt_version=OBSERVATIONS_PROMPT_VERSION,
    )
    assert [item["name"] for item in shaped["competitor_mentions"]] == ["Ringover"]
    assert shaped["competitor_mentions"][0]["evidence_refs"]


def test_v3_output_is_unchanged():
    shaped = shape_intelligence(
        MEMO,
        _raw(competitor_mentions=[{"name": "Ringover", "quote": "ya usamos Ringover"}],
             playbook_observations=[{"step_id": "opening", "status": "met", "quote": "soy Lucía de Vocify"}]),
        playbook_steps=STEPS,
    )
    assert shaped["prompt_version"] == PROMPT_VERSION
    assert shaped["competitor_mentions"] == []
    assert shaped["playbook_observations"] == []


def test_v4_sends_the_steps_and_v3_does_not():
    v4 = json.loads(build_messages(MEMO, prompt_version=OBSERVATIONS_PROMPT_VERSION, playbook_steps=STEPS)[1]["content"])
    assert [step["step_id"] for step in v4["playbook_steps"]] == ["opening", "pain", "meeting", "qualify"]
    v3 = json.loads(build_messages(MEMO)[1]["content"])
    assert "playbook_steps" not in v3
    assert "playbook_observations" in build_messages(MEMO, prompt_version=OBSERVATIONS_PROMPT_VERSION)[0]["content"]


def test_both_versions_count_as_current(monkeypatch):
    from app.services.intelligence import extract

    monkeypatch.setattr(extract, "revision_for_memo", lambda _memo: "rev-1")
    for version in (PROMPT_VERSION, OBSERVATIONS_PROMPT_VERSION):
        memo = {"extraction": {"intelligence": {"prompt_version": version, "input_revision": "rev-1"}}}
        assert is_current(memo)
    assert not is_current({"extraction": {"intelligence": {"prompt_version": "intelligence_v2", "input_revision": "rev-1"}}})


def test_extract_intelligence_uses_the_requested_version():
    class LLM:
        last_call_meta = {}

        async def chat_json(self, messages, **_kwargs):
            assert "playbook_steps" in messages[1]["content"]
            return _raw(playbook_observations=[{"step_id": "opening", "status": "met", "quote": "soy Lucía de Vocify"}])

    shaped, _meta = asyncio.run(extract_intelligence(
        MEMO, LLM(), prompt_version=OBSERVATIONS_PROMPT_VERSION, playbook_steps=STEPS[:1],
    ))
    assert shaped["prompt_version"] == OBSERVATIONS_PROMPT_VERSION
    assert shaped["playbook_observations"][0]["status"] == "met"


def test_coaching_lines_come_from_cited_observations_only():
    shaped = shape_intelligence(
        MEMO,
        _raw(playbook_observations=[
            {"step_id": "opening", "status": "met", "quote": "soy Lucía de Vocify, ¿tienes dos minutos?"},
            {"step_id": "meeting", "status": "missed", "quote": "Vale, te mando información."},
        ]),
        prompt_version=OBSERVATIONS_PROMPT_VERSION,
        playbook_steps=STEPS,
    )
    ids = [item["id"] for item in shaped["evidence"]]
    strengths, improvements = coaching_lines(shaped, evidence_ids=ids)
    assert strengths == ["Apertura: «soy Lucía de Vocify, ¿tienes dos minutos?»"]
    assert improvements == ["Agendar la reunión: Propone día y hora y el prospecto acepta"]
    assert coaching_lines({"playbook_observations": []}, evidence_ids=ids) == ([], [])


def test_v3_is_upgraded_only_when_the_company_is_on_v4():
    from app.services.intelligence.extract import _needs_upgrade

    v3 = {"extraction": {"intelligence": {"prompt_version": PROMPT_VERSION}}}
    v4 = {"extraction": {"intelligence": {"prompt_version": OBSERVATIONS_PROMPT_VERSION}}}
    assert _needs_upgrade(v3, OBSERVATIONS_PROMPT_VERSION) is True
    assert _needs_upgrade(v3, PROMPT_VERSION) is False
    assert _needs_upgrade(v4, PROMPT_VERSION) is False  # never downgraded
    assert _needs_upgrade(v4, OBSERVATIONS_PROMPT_VERSION) is False
