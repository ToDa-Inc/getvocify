"""Meeting proposal accept payload."""

from typing import Literal

from pydantic import BaseModel, Field


class MeetingProposalAcceptRequest(BaseModel):
    decision: Literal["accept", "omit", "corrected"]
    proposal_id: str = Field(..., min_length=1, max_length=200)
    starts_at: str | None = None
