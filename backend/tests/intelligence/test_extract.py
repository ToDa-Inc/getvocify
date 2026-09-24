import asyncio
import os

os.environ.setdefault("SUPABASE_URL", "http://localhost:54321")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-secret")

from app.services.intelligence.extract import extract_intelligence, shape_intelligence  # noqa: E402

TRANSCRIPT = (
    "Them: El seguimiento nos ocupa tres horas al día. "
    "Them: Ahora mismo el precio se nos va de presupuesto. "
    "You: Te envío el caso de logística el jueves."
)
MEMO = {
    "id": "memo-1",
    "company_id": "co-1",
    "user_id": "u-1",
    "transcript": TRANSCRIPT,
    "capture_started_at": "2026-09-22T10:00:00+02:00",
    "extraction": {"summary": "Llamada de descubrimiento"},
}


def test_keeps_only_quotes_that_are_in_the_transcript():
    raw = {
        "interest": "high",
        "pain_confirmed": True,
        "objections": [
            {"category": "price", "resolution": "open", "quote": "el precio se nos va de presupuesto"},
            {"category": "timing", "resolution": "open", "quote": "no tenemos tiempo este año"},
        ],
        "commitments": [],
    }
    shaped = shape_intelligence(MEMO, raw)
    assert shaped["interest"] == "high"
    assert shaped["pain_confirmed"] is True
    assert [item["category"] for item in shaped["objections"]] == ["price"]
    assert shaped["objections"][0]["evidence_refs"]


def test_a_commitment_without_a_real_date_is_dropped_and_unknown_interest_stays_null():
    raw = {
        "interest": "maybe",
        "commitments": [
            {"kind": "send", "origin": "rep_promise", "text": "enviar el caso de logística", "due_at": "2026-09-24T09:00:00+02:00", "quote": "Te envío el caso de logística el jueves"},
            {"kind": "call", "origin": "prospect_request", "text": "llamar", "due_at": "pronto", "quote": "Te envío"},
        ],
    }
    shaped = shape_intelligence(MEMO, raw)
    assert shaped["interest"] is None
    assert len(shaped["commitments"]) == 1
    assert shaped["commitments"][0]["text"] == "enviar el caso de logística"
    assert shaped["commitments"][0]["due_at"].startswith("2026-09-24")


def test_an_unknown_category_becomes_other_and_a_long_text_is_cut():
    raw = {
        "objections": [{"category": "vibes", "resolution": "open", "quote": "El seguimiento nos ocupa tres horas"}],
        "commitments": [{
            "kind": "send",
            "origin": "rep_promise",
            "text": "enviar " + "x" * 200,
            "due_at": "2026-09-24T09:00:00+02:00",
            "quote": "Te envío el caso de logística el jueves",
        }],
    }
    shaped = shape_intelligence(MEMO, raw)
    assert shaped["objections"][0]["category"] == "other"
    assert len(shaped["commitments"][0]["text"]) <= 80


def test_extract_calls_the_model_once_and_returns_cost_metadata():
    class FakeLLM:
        calls = 0
        last_call_meta = {"model": "m", "prompt_tokens": 900, "completion_tokens": 120}

        async def chat_json(self, messages, **kwargs):
            FakeLLM.calls += 1
            assert "Te envío el caso de logística" in messages[-1]["content"]
            return {"interest": "medium", "objections": [], "commitments": []}

    shaped, meta = asyncio.run(extract_intelligence(MEMO, FakeLLM()))
    assert FakeLLM.calls == 1
    assert shaped["interest"] == "medium"
    assert shaped["version"] == 1
    assert meta["prompt_tokens"] == 900


def test_no_transcript_means_no_call():
    class NeverCalled:
        async def chat_json(self, *_args, **_kwargs):
            raise AssertionError("no call")

    shaped, meta = asyncio.run(extract_intelligence({**MEMO, "transcript": ""}, NeverCalled()))
    assert shaped is None
    assert meta == {}
