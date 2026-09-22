"""Same revision is not interpreted twice, and unknown stays null."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-intelligence-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-intelligence-32")

from app.services.intelligence.interpret import interpret_memo

MEMO = {
    "id": "memo-1",
    "user_id": "user-1",
    "company_id": "company-1",
    "extraction": {"summary": "Quiere el caso"},
    "candidate_evidence": [
        {
            "id": "ev-1",
            "source_type": "transcript",
            "source_id": "memo-1",
            "quote": "El seguimiento nos ocupa tres horas",
            "speaker_role": "prospect",
        },
        {
            "id": "ev-missing",
            "source_type": "transcript",
            "source_id": "memo-1",
            "quote": "frase que no se dijo",
            "speaker_role": "prospect",
        },
    ],
}
SOURCES = {"memo-1": "El seguimiento nos ocupa tres horas al día."}


def test_missing_classification_does_not_become_false_and_drops_unknown_quotes():
    calls = {"n": 0}

    def classify(_memo):
        calls["n"] += 1
        return {"status": "unavailable", "answers": {}}

    intelligence, created = interpret_memo(MEMO, classify, SOURCES)
    assert created is True
    assert intelligence.meeting.agreed is None
    assert intelligence.pain_confirmed is None
    assert intelligence.status == "unavailable"
    assert [item.id for item in intelligence.evidence] == ["ev-1"]
    assert calls["n"] == 1


def test_identical_retry_reuses_intelligence_without_classifying_again():
    calls = {"n": 0}

    def classify(_memo):
        calls["n"] += 1
        return {
            "status": "ready",
            "answers": {"meeting_agreed": "agreed", "pain_confirmed": "confirmed"},
        }

    first, created = interpret_memo(MEMO, classify, SOURCES)
    assert created is True
    stored = {**MEMO, "intelligence": first.model_dump()}
    second, again = interpret_memo(stored, classify, SOURCES)
    assert again is False
    assert second.input_revision == first.input_revision
    assert second.meeting.agreed is True
    assert calls["n"] == 1
