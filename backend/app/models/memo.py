"""
Pydantic models for Memo entities
"""

from pydantic import BaseModel, Field, model_validator
from typing import Optional, List, Literal, Any
from datetime import datetime
from uuid import UUID

from app.models.intelligence import IntelligenceV1


# Universal normalization: LLM often returns null or {} instead of []/{}.
# These mappings define how to coerce invalid values per field type.
# HubSpot API expects proper types (lists, dicts, strings) - never null for these.
MEMO_EXTRACTION_LIST_FIELDS = frozenset({
    "painPoints", "nextSteps", "competitors", "objections", "decisionMakers",
})
MEMO_EXTRACTION_DICT_FIELDS = frozenset({
    "confidence", "raw_extraction",
})
MEMO_EXTRACTION_STRING_DEFAULTS = {
    "summary": "",
    "dealCurrency": "EUR",
}


def _normalize_extraction_input(data: Any) -> dict:
    """
    Universal normalizer for MemoExtraction input.
    Accepts null, None, {} from LLM and coerces to HubSpot-safe values.
    """
    if not isinstance(data, dict):
        return {}
    out = dict(data)
    for key in list(out.keys()):
        val = out[key]
        if key in MEMO_EXTRACTION_LIST_FIELDS:
            if val is None:
                out[key] = []
            elif isinstance(val, list):
                out[key] = val
            elif isinstance(val, str) and val.strip():
                out[key] = [val.strip()]
            else:
                out[key] = []
        elif key in MEMO_EXTRACTION_DICT_FIELDS:
            if val is None or not isinstance(val, dict):
                out[key] = {}
            elif key == "confidence":
                fields = val.get("fields")
                if fields is None or not isinstance(fields, dict):
                    out[key] = {**val, "fields": {}}
        elif key in MEMO_EXTRACTION_STRING_DEFAULTS:
            if val is None:
                out[key] = MEMO_EXTRACTION_STRING_DEFAULTS[key]
            elif not isinstance(val, str):
                out[key] = str(val) if val is not None else MEMO_EXTRACTION_STRING_DEFAULTS[key]
    return out


class MemoExtraction(BaseModel):
    """Extracted CRM data from transcript. Accepts null/{} from LLM, coerces to [] or {}."""

    # Deal Information
    companyName: Optional[str] = None
    dealAmount: Optional[float] = None
    dealCurrency: str = "EUR"
    dealStage: Optional[str] = None
    closeDate: Optional[str] = None  # ISO format YYYY-MM-DD

    # Contact Information
    contactName: Optional[str] = None
    contactRole: Optional[str] = None
    contactEmail: Optional[str] = None
    contactPhone: Optional[str] = None

    # Meeting Intelligence
    summary: str = ""
    painPoints: List[str] = Field(default_factory=list)
    nextSteps: List[str] = Field(default_factory=list)
    competitors: List[str] = Field(default_factory=list)
    objections: List[str] = Field(default_factory=list)
    decisionMakers: List[str] = Field(default_factory=list)

    # Confidence
    confidence: dict = Field(default_factory=lambda: {"overall": 0.0, "fields": {}})

    # Raw extraction for dynamic fields
    raw_extraction: Optional[dict] = Field(default_factory=dict)

    # Typed intelligence. Absent on legacy memos. null is unknown, not false.
    intelligence: Optional[IntelligenceV1] = None

    @model_validator(mode="before")
    @classmethod
    def normalize_llm_output(cls, v: Any) -> Any:
        """Accept null/{} from LLM, normalize to HubSpot-safe types."""
        if isinstance(v, dict):
            return _normalize_extraction_input(v)
        return v


class TranscriptionResult(BaseModel):
    """Result from Deepgram transcription"""
    transcript: str
    confidence: float = Field(ge=0.0, le=1.0)
    duration: float  # seconds


class MemoBase(BaseModel):
    """Base memo model"""
    audioUrl: str
    audioDuration: float
    status: str


class MemoCreate(MemoBase):
    """Model for creating a new memo"""
    userId: str


class MemoUpdate(BaseModel):
    """Model for updating memo fields"""
    status: Optional[str] = None
    transcript: Optional[str] = None
    transcriptConfidence: Optional[float] = None
    extraction: Optional[MemoExtraction] = None
    errorMessage: Optional[str] = None
    processedAt: Optional[datetime] = None
    approvedAt: Optional[datetime] = None


class Memo(MemoBase):
    """Full memo model returned by API"""
    id: UUID
    userId: str
    authorName: Optional[str] = None
    authorEmail: Optional[str] = None
    transcript: Optional[str] = None
    transcriptConfidence: Optional[float] = None
    extraction: Optional[MemoExtraction] = None
    errorMessage: Optional[str] = None
    createdAt: datetime
    processedAt: Optional[datetime] = None
    approvedAt: Optional[datetime] = None
    pipelineMeta: Optional[dict] = None
    source: Optional[str] = None
    hubspotEngagementId: Optional[str] = None
    hubspotContactId: Optional[str] = None
    hubspotDealId: Optional[str] = None
    screeningOutcome: Optional[str] = None
    interactionKind: Optional[str] = None
    salesMotionKey: Optional[str] = None
    # Lista 4 T4: what the after-call outcome did (stored date, handoff hint). Approve only.
    after_call: Optional[dict] = None
    
    class Config:
        from_attributes = True


class UploadResponse(BaseModel):
    """Response from upload endpoint"""
    id: str
    status: str
    statusUrl: str


class ApproveMemoRequest(BaseModel):
    """Request body for approving a memo"""
    deal_id: Optional[str] = Field(None, description="Deal ID to update (None = create new)")
    is_new_deal: bool = Field(default=False, description="Whether to create a new deal")
    contact_id: Optional[str] = Field(
        None,
        description="Resolved HubSpot contact to update (contact-first identity)",
    )
    company_id: Optional[str] = Field(
        None,
        description="Optional HubSpot company linked to the resolved contact",
    )
    skip_deal: bool = Field(
        default=False,
        description="Update contact/company only; do not create or update a deal",
    )
    extraction: Optional[MemoExtraction] = None
    create_note: bool = Field(default=True, description="Create CRM note when a deal is synced")
    create_company: Optional[bool] = Field(
        default=None,
        description=(
            "Manual Confirm can create a company when the contact has none. "
            "False never creates (auto-approve). None uses workspace auto_create_companies."
        ),
    )
    call_outcome: Optional[Literal["converted", "on_hold", "lost"]] = Field(
        None,
        description=(
            "Result of the call as marked by the rep on the confirmation screen. "
            "None means the rep didn't mark an outcome (unchanged legacy behavior) - "
            "this is optional, not a forced choice on every memo."
        ),
    )
    lost_reason: Optional[str] = Field(
        None,
        description=(
            "Required when call_outcome='lost' (see validator below). One of "
            "crm_configurations.lost_reasons, or free text when the rep picked "
            "'Other' in the UI - the backend does not restrict it to the "
            "configured list, since the account's list can change independently."
        ),
    )

    # Lista 4 T4 (E10, AFTER_CALL_FLOW_ENABLED): the outcome the rep picks in Hoy's panel after
    # the call. With the flag on it replaces call_outcome (see services/after_call.py); with it
    # off these are ignored and approval behaves exactly as before.
    rep_outcome: Optional[Literal["meeting_booked", "follow_up", "not_interested", "disqualified"]] = None
    followup_at: Optional[datetime] = Field(
        None, description="follow_up only: when to call back. None = the cadence's suggested date."
    )
    disqualify_reason: Optional[str] = Field(
        None, description="Required for not_interested/disqualified; written as the lost reason."
    )
    lead_status: Optional[str] = Field(
        None,
        description=(
            "The contact lead status the rep chose instead of the proposed one - honoured only "
            "when it is one of the account's mapped On hold / Lost values."
        ),
    )

    @model_validator(mode="after")
    def _lost_requires_reason(self) -> "ApproveMemoRequest":
        """
        Enforced here, not just in the extension UI: a rep marking a call
        Lost must always record why. A UI can be bypassed (direct API call,
        a future integration); this validator cannot - FastAPI turns this
        into a 422 before any handler code runs, for every caller.
        """
        if self.call_outcome == "lost" and not (self.lost_reason or "").strip():
            raise ValueError("lost_reason is required when call_outcome is 'lost'")
        _require_outcome_reason(self.rep_outcome, self.disqualify_reason or self.lost_reason)
        return self


def _require_outcome_reason(rep_outcome: Optional[str], reason: Optional[str]) -> None:
    """Same rule as a Lost call_outcome: closing a contact out always records why."""
    if rep_outcome in ("not_interested", "disqualified") and not (reason or "").strip():
        raise ValueError(f"disqualify_reason is required when rep_outcome is '{rep_outcome}'")


class RecordOutcomeRequest(BaseModel):
    """POST /memos/{id}/outcome (Lista 4 T4): the after-call outcome for a memo that is already
    approved (auto-approve wrote it before the rep got to the panel). Same semantics as the
    rep_outcome fields of ApproveMemoRequest."""
    rep_outcome: Literal["meeting_booked", "follow_up", "not_interested", "disqualified"]
    followup_at: Optional[datetime] = None
    disqualify_reason: Optional[str] = None
    lead_status: Optional[str] = None

    @model_validator(mode="after")
    def _closing_requires_reason(self) -> "RecordOutcomeRequest":
        _require_outcome_reason(self.rep_outcome, self.disqualify_reason)
        return self

