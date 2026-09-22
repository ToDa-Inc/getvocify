"""Build C04 once per revision. A repeat reuses the stored intelligence."""

from __future__ import annotations

from typing import Any, Callable, Optional

from app.models.intelligence import EvidenceRef, IntelligenceV1, MeetingFact, quote_is_in_source
from app.services.intelligence.worker import revision_for_memo

Classify = Callable[[dict], dict]


def _tri_state(value: Any, *, yes: str, no: str) -> Optional[bool]:
    if value == yes:
        return True
    if value == no:
        return False
    return None


def interpret_memo(
    memo: dict,
    classify: Classify,
    sources: dict[str, str],
) -> tuple[IntelligenceV1, bool]:
    """Return intelligence and whether a new classification was required."""
    revision = revision_for_memo(memo)
    existing = memo.get("intelligence")
    if isinstance(existing, dict) and existing.get("input_revision") == revision and existing.get("version") == 1:
        return IntelligenceV1.model_validate(existing), False

    result = classify(memo)
    answers = result.get("answers") or {}
    evidence: list[EvidenceRef] = []
    for raw in memo.get("candidate_evidence") or []:
        item = raw if isinstance(raw, EvidenceRef) else EvidenceRef.model_validate(raw)
        if quote_is_in_source(item, sources):
            evidence.append(item)
    agreed = _tri_state(answers.get("meeting_agreed"), yes="agreed", no="not_agreed")
    pain = _tri_state(answers.get("pain_confirmed"), yes="confirmed", no="not_confirmed")
    if result.get("status") == "unavailable":
        status = "unavailable"
    elif agreed is None or pain is None:
        status = "partial"
    else:
        status = "ready"
    intelligence = IntelligenceV1(
        version=1,
        input_revision=revision,
        status=status,
        pain_confirmed=pain,
        meeting=MeetingFact(agreed=agreed, precision="unknown", evidence_refs=[item.id for item in evidence]),
        evidence=evidence,
    )
    return intelligence, True
