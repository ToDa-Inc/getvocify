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
        "pain_quote": "El seguimiento nos ocupa tres horas al día",
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


def test_pain_without_a_quote_from_the_transcript_is_unknown():
    assert shape_intelligence(MEMO, {"pain_confirmed": True})["pain_confirmed"] is None
    invented = shape_intelligence(MEMO, {"pain_confirmed": True, "pain_quote": "perdemos clientes"})
    assert invented["pain_confirmed"] is None


def test_pain_keeps_its_evidence():
    shaped = shape_intelligence(
        MEMO, {"pain_confirmed": True, "pain_quote": "El seguimiento nos ocupa tres horas al día"},
    )
    [ref] = shaped["evidence"]
    assert ref["quote"] == "El seguimiento nos ocupa tres horas al día"


MEETING_MEMO = {
    **MEMO,
    "transcript": "You: ¿Te va bien el martes a las diez para la demo? Them: Perfecto, el martes a las diez.",
}


def test_an_agreed_meeting_with_a_time_is_kept():
    shaped = shape_intelligence(MEETING_MEMO, {"meeting": {
        "agreed": True, "starts_at": "2026-09-29T10:00:00+02:00", "quote": "Perfecto, el martes a las diez",
    }})
    meeting = shaped["meeting"]
    assert meeting["agreed"] is True
    assert meeting["starts_at"] == "2026-09-29T10:00:00+02:00"
    assert meeting["precision"] == "time"
    assert meeting["evidence_refs"]


def test_an_agreed_meeting_with_only_a_day_keeps_the_day():
    shaped = shape_intelligence(MEETING_MEMO, {"meeting": {
        "agreed": True, "starts_at": "2026-09-29", "quote": "Perfecto, el martes a las diez",
    }})
    assert shaped["meeting"]["starts_at"] == "2026-09-29"
    assert shaped["meeting"]["precision"] == "date"


def test_a_meeting_without_a_quote_or_with_a_vague_date_is_not_invented():
    assert shape_intelligence(MEETING_MEMO, {"meeting": {"agreed": True}})["meeting"]["agreed"] is None
    vague = shape_intelligence(MEETING_MEMO, {"meeting": {
        "agreed": True, "starts_at": "la semana que viene", "quote": "Perfecto, el martes a las diez",
    }})
    assert vague["meeting"]["agreed"] is True
    assert vague["meeting"]["starts_at"] is None
    assert vague["meeting"]["precision"] == "unknown"


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


def _commitment(due_at):
    return {"commitments": [{
        "kind": "send", "origin": "rep_promise", "text": "enviar el caso de logística",
        "due_at": due_at, "quote": "Te envío el caso de logística el jueves",
    }]}


def test_a_commitment_with_a_time_has_time_precision():
    [item] = shape_intelligence(MEMO, _commitment("2026-09-24T11:00:00+02:00"))["commitments"]
    assert item["due_at"] == "2026-09-24T11:00:00+02:00"
    assert item["temporal_precision"] == "time"


def test_a_commitment_with_only_a_day_starts_that_day_in_the_memo_timezone():
    [item] = shape_intelligence(MEMO, _commitment("2026-09-24"))["commitments"]
    assert item["due_at"] == "2026-09-24T00:00:00+02:00"
    assert item["temporal_precision"] == "date"
    winter = shape_intelligence({**MEMO, "timezone": "Europe/Madrid"}, _commitment("2026-12-03"))
    assert winter["commitments"][0]["due_at"] == "2026-12-03T00:00:00+01:00"
    other = shape_intelligence({**MEMO, "timezone": "America/Mexico_City"}, _commitment("2026-09-24"))
    assert other["commitments"][0]["due_at"] == "2026-09-24T00:00:00-06:00"


def test_a_day_only_commitment_is_due_on_that_day_in_hoy():
    from datetime import datetime

    from app.services.hoy.materialize import day_end
    from app.services.hoy.signals import signals_for_contact, touch_from_intelligence

    shaped = shape_intelligence(MEMO, _commitment("2026-09-24"))
    touch = touch_from_intelligence(
        memo_id="memo-1", contact_id="c-1", deal_id=None,
        at=datetime.fromisoformat("2026-09-22T10:00:00+02:00"), intelligence=shaped,
    )
    wednesday = datetime.fromisoformat("2026-09-23T09:00:00+02:00")
    thursday = datetime.fromisoformat("2026-09-24T09:00:00+02:00")
    assert not signals_for_contact([touch], now=wednesday, day_end=day_end(wednesday, "Europe/Madrid"))
    [signal] = signals_for_contact([touch], now=thursday, day_end=day_end(thursday, "Europe/Madrid"))
    assert signal.type == "commitment_due"


def test_a_commitment_without_an_offset_or_a_real_day_is_dropped():
    assert shape_intelligence(MEMO, _commitment("2026-09-24T11:00:00"))["commitments"] == []
    assert shape_intelligence(MEMO, _commitment("2026-02-30"))["commitments"] == []


def test_a_commitment_where_no_day_was_said_is_kept_without_a_date():
    [item] = shape_intelligence(MEMO, _commitment(None))["commitments"]
    assert item["text"] == "enviar el caso de logística"
    assert item["due_at"] is None
    assert item["temporal_precision"] == "unknown"


def test_an_undated_commitment_never_reaches_hoy():
    from datetime import datetime

    from app.services.hoy.materialize import day_end
    from app.services.hoy.signals import signals_for_contact, touch_from_intelligence

    shaped = shape_intelligence(MEMO, _commitment(None))
    touch = touch_from_intelligence(
        memo_id="memo-1", contact_id="c-1", deal_id=None,
        at=datetime.fromisoformat("2026-09-22T10:00:00+02:00"), intelligence=shaped,
    )
    later = datetime.fromisoformat("2026-12-01T09:00:00+01:00")
    assert not signals_for_contact([touch], now=later, day_end=day_end(later, "Europe/Madrid"))


def test_an_unknown_timezone_falls_back_to_madrid():
    kept = shape_intelligence({**MEMO, "timezone": "Mars/Base"}, _commitment("2026-09-24"))
    assert kept["commitments"][0]["due_at"] == "2026-09-24T00:00:00+02:00"


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


def test_the_prompt_version_names_its_own_prompt_file():
    from app.services.intelligence.extract import PROMPT_PATH, PROMPT_VERSION

    assert PROMPT_VERSION == "intelligence_v3"
    assert PROMPT_PATH.name == f"{PROMPT_VERSION}.md"
    stored = shape_intelligence({**MEMO, "timezone": "Europe/Madrid"}, {"commitments": []})
    assert stored["prompt_version"] == "intelligence_v3"


def test_a_released_prompt_file_is_never_edited_in_place():
    from app.services.intelligence.extract import PROMPT_PATH

    v2 = (PROMPT_PATH.parent / "intelligence_v2.md").read_text(encoding="utf-8")
    assert "SPEAKER: S1" not in v2
    assert "en dos semanas" not in v2
