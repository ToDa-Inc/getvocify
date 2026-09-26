"""Request models for follow-up hand-off actions and the rep's pasted writing samples."""
from typing import Literal

from pydantic import BaseModel, Field


class FollowupActionRequest(BaseModel):
    action: Literal["sent", "copied"]
    channel: Literal["email", "whatsapp"] = "email"
    subject: str = Field("", max_length=300)
    body: str = Field(..., min_length=1, max_length=8000)


class WritingSamplesRequest(BaseModel):
    """Limits per sample live in followup_logic.clean_pasted; this only bounds the payload."""

    samples: list[str] = Field(default_factory=list, max_length=10)
