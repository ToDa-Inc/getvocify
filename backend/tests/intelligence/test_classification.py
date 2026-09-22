"""F0: Jev answers that are missing or invalid stay unknown."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-intelligence-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-intelligence-32")
os.environ.setdefault("OPENROUTER_API_KEY", "test-key")

import pytest

from app.services.llm.jev import JevClient
from app.services.llm.jev_schemas import OBJECTION_KIND, evidence_state


class StubJev(JevClient):
    def __init__(self, answers):
        super().__init__(api_key="test-key")
        self.answers = answers
        self.seen_state = None

    async def _post_systemone(self, state, questions):
        self.seen_state = state
        return self.answers


@pytest.mark.asyncio
async def test_provider_silence_is_unknown_not_false():
    client = StubJev(None)
    result = await client.classify_questions(
        {"transcript": "Hola"},
        [{"question": "meeting_agreed", "allowed": ["agreed", "not_agreed", "unknown"], "on_missing": "unknown"}],
    )
    assert result["status"] == "unavailable"
    assert result["answers"]["meeting_agreed"] == "unknown"
    assert result["answers"]["meeting_agreed"] is not False


@pytest.mark.asyncio
async def test_low_confidence_or_invalid_choice_stays_unknown():
    client = StubJev({"meeting_agreed": {"choice": "maybe", "confidence": 0.99}})
    result = await client.classify_questions(
        {"transcript": "Hola"},
        [{"question": "meeting_agreed", "allowed": ["agreed", "not_agreed", "unknown"], "on_missing": "unknown"}],
    )
    assert result["status"] == "partial"
    assert result["answers"]["meeting_agreed"] == "unknown"


@pytest.mark.asyncio
async def test_driving_now_is_not_classified_as_price_by_default():
    client = StubJev(None)
    result = await client.classify_questions({"transcript": "Ahora conduzco"}, [OBJECTION_KIND])
    assert result["answers"]["objection_kind"] == "unknown"
    assert result["answers"]["objection_kind"] != "price"


@pytest.mark.asyncio
async def test_late_resolution_is_kept_when_the_transcript_is_long():
    late = "La objeción de precio quedó resuelta al aceptar el caso."
    transcript = ("inicio " * 4000) + late
    assert len(transcript) > 16000
    state = evidence_state(transcript, [late])
    assert late in state["transcript"]
    client = StubJev({"objection_resolution": {"choice": "resolved", "confidence": 0.91}})
    result = await client.classify_questions(
        state,
        [{"question": "objection_resolution", "allowed": ["resolved", "open", "unknown"], "on_missing": "unknown"}],
    )
    assert result["answers"]["objection_resolution"] == "resolved"
    assert late in client.seen_state["transcript"]


@pytest.mark.asyncio
async def test_memo_classifier_keeps_silence_unknown_and_a_late_quote():
    from app.services.intelligence.interpret import classify_memo

    late = "El seguimiento nos ocupa tres horas al día."
    transcript = ("inicio " * 4000) + late
    memo = {"transcript": transcript, "candidate_evidence": [{"quote": late}]}
    client = StubJev(None)
    result = await classify_memo(memo, client)
    assert result["status"] == "unavailable"
    assert result["answers"]["meeting_agreed"] == "unknown"
    assert result["answers"]["pain_confirmed"] == "unknown"
    assert result["answers"]["meeting_agreed"] is not False
    assert late in client.seen_state["transcript"]
