from app.services.extraction_confidence import (
    FIELD_CONFIDENCE_HIGH,
    FIELD_CONFIDENCE_UNCERTAIN,
    field_extraction_confidence,
    jev_score_to_field_confidence,
    merge_field_confidences,
)
from app.models.memo import MemoExtraction


def test_jev_score_to_field_confidence():
    assert jev_score_to_field_confidence(0.9) == FIELD_CONFIDENCE_HIGH
    assert jev_score_to_field_confidence(0.6) == FIELD_CONFIDENCE_UNCERTAIN


def test_field_extraction_confidence_defaults_high():
    extraction = MemoExtraction(confidence={"overall": 0.5, "fields": {}})
    assert field_extraction_confidence(extraction, "amount") == FIELD_CONFIDENCE_HIGH


def test_field_extraction_confidence_reads_stored_score():
    extraction = MemoExtraction(confidence={"overall": 0.5, "fields": {"amount": 0.65}})
    assert field_extraction_confidence(extraction, "amount") == 0.65


def test_merge_field_confidences():
    extracted = {"confidence": {"overall": 0.5, "fields": {"a": 0.9}}}
    merge_field_confidences(extracted, {"b": 0.65})
    assert extracted["confidence"]["fields"]["a"] == 0.9
    assert extracted["confidence"]["fields"]["b"] == 0.65
