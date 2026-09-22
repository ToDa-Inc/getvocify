"""C04 IntelligenceV1. Unknown stays null; it is not false."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class EvidenceRef(BaseModel):
    id: str
    source_type: Literal["transcript", "human_note"]
    source_id: str
    turn_id: Optional[str] = None
    quote: str
    start_ms: Optional[int] = None
    end_ms: Optional[int] = None
    speaker_role: Optional[str] = None


class MeetingFact(BaseModel):
    agreed: Optional[bool] = None
    starts_at: Optional[str] = None
    timezone: Optional[str] = None
    precision: Literal["unknown", "date", "time"] = "unknown"
    evidence_refs: list[str] = Field(default_factory=list)


class IntelligenceV1(BaseModel):
    version: Literal[1] = 1
    input_revision: str
    status: Literal["ready", "partial", "unavailable"]
    sales_motion_key: Optional[str] = None
    interest: Optional[str] = None
    pain_confirmed: Optional[bool] = None
    commitments: list = Field(default_factory=list)
    objections: list = Field(default_factory=list)
    meeting: MeetingFact = Field(default_factory=MeetingFact)
    competitor_mentions: list = Field(default_factory=list)
    playbook_observations: list = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(default_factory=list)


def quote_is_in_source(evidence: EvidenceRef, sources: dict[str, str]) -> bool:
    """A quote counts only when it appears in the named source. Missing text is unknown, not a fact."""
    text = sources.get(evidence.source_id)
    if text is None:
        return False
    quote = (evidence.quote or "").strip()
    if not quote:
        return False
    return quote in text
