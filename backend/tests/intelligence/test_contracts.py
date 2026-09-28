"""F0: legacy memos stay valid, and a quote must exist in its source."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-intelligence-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-intelligence-32")

from app.models.intelligence import EvidenceRef, IntelligenceV1, quote_is_in_source
from app.models.memo import MemoExtraction

PARTIAL = {
    "version": 1,
    "input_revision": "rev-1",
    "status": "partial",
    "sales_motion_key": None,
    "pain_confirmed": None,
    "commitments": [],
    "objections": [],
    "meeting": {
        "agreed": None,
        "starts_at": None,
        "timezone": None,
        "precision": "unknown",
        "evidence_refs": [],
    },
    "playbook_observations": [],
    "evidence": [],
}


def test_legacy_extraction_without_intelligence_validates_as_before():
    memo = MemoExtraction.model_validate({"summary": "Hola", "contactName": "Marina"})
    assert memo.summary == "Hola"
    assert memo.contactName == "Marina"
    assert memo.intelligence is None


def test_unknown_is_not_false():
    intel = IntelligenceV1.model_validate(PARTIAL)
    assert intel.pain_confirmed is None
    assert intel.meeting.agreed is None
    assert intel.pain_confirmed is not False
    assert intel.meeting.agreed is not False


def test_quote_missing_from_the_source_is_not_evidence():
    evidence = EvidenceRef(
        id="ev-1",
        source_type="transcript",
        source_id="memo-1",
        quote="El seguimiento nos ocupa tres horas",
        speaker_role="prospect",
    )
    assert quote_is_in_source(evidence, {"memo-1": "Hablamos del precio."}) is False
    assert quote_is_in_source(evidence, {"memo-1": "El seguimiento nos ocupa tres horas al día."}) is True


def test_unavailable_intelligence_does_not_strip_existing_extraction_fields():
    memo = MemoExtraction.model_validate(
        {
            "summary": "Quiere propuesta",
            "nextSteps": ["Enviar deck"],
            "objections": ["Está caro"],
            "intelligence": {**PARTIAL, "status": "unavailable"},
        }
    )
    assert memo.summary == "Quiere propuesta"
    assert memo.nextSteps == ["Enviar deck"]
    assert memo.objections == ["Está caro"]
    assert memo.intelligence.status == "unavailable"


def test_identical_words_keep_human_note_and_prospect_apart():
    quote = "Ahora conduzco"
    prospect = EvidenceRef(
        id="ev-t",
        source_type="transcript",
        source_id="memo-1",
        quote=quote,
        speaker_role="prospect",
    )
    note = EvidenceRef(
        id="ev-n",
        source_type="human_note",
        source_id="ann-1",
        quote=quote,
        speaker_role=None,
    )
    assert prospect.quote == note.quote
    assert prospect.source_type != note.source_type
    assert prospect.source_id != note.source_id
