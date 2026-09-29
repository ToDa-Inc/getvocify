"""Shared extraction confidence scores for CRM preview UI."""

from __future__ import annotations

from typing import Any, Optional

FIELD_CONFIDENCE_HIGH = 0.92
FIELD_CONFIDENCE_UNCERTAIN = 0.65
FIELD_JEV_HIGH_THRESHOLD = 0.75
CONFIDENCE_HIGH_UI = 0.9
CONFIDENCE_LOW_UI = 0.5


def jev_score_to_field_confidence(jev_conf: float) -> float:
    try:
        conf = float(jev_conf)
    except (TypeError, ValueError):
        return FIELD_CONFIDENCE_UNCERTAIN
    if conf >= FIELD_JEV_HIGH_THRESHOLD:
        return FIELD_CONFIDENCE_HIGH
    return FIELD_CONFIDENCE_UNCERTAIN


def field_extraction_confidence(extraction: Any, field_name: str) -> float:
    """Resolve per-field confidence for approval preview rows."""
    conf = getattr(extraction, "confidence", None) or {}
    fields = conf.get("fields") if isinstance(conf, dict) else {}
    if not isinstance(fields, dict):
        return FIELD_CONFIDENCE_HIGH
    raw = fields.get(field_name)
    if raw is None:
        return FIELD_CONFIDENCE_HIGH
    try:
        score = float(raw)
    except (TypeError, ValueError):
        return FIELD_CONFIDENCE_HIGH
    return max(0.0, min(1.0, score))


def merge_field_confidences(extracted: dict, confidences: Optional[dict[str, float]]) -> None:
    if not confidences:
        return
    conf = extracted.setdefault("confidence", {"overall": 0.5, "fields": {}})
    if not isinstance(conf, dict):
        return
    fields = conf.setdefault("fields", {})
    if not isinstance(fields, dict):
        return
    for name, score in confidences.items():
        if not name or score is None:
            continue
        try:
            fields[name] = max(0.0, min(1.0, float(score)))
        except (TypeError, ValueError):
            continue
