"""Request models for follow-up hand-off actions and the rep's pasted writing samples."""
from typing import Annotated, Literal

from pydantic import BaseModel, EmailStr, Field

# Raw, before trimming: clean_pasted enforces 40-1500 on the trimmed text, so this only
# stops an oversized body from reaching it.
RAW_SAMPLE_MAX = 5000


class FollowupActionRequest(BaseModel):
    action: Literal["sent", "copied"]
    channel: Literal["email", "whatsapp"] = "email"
    subject: str = Field("", max_length=300)
    body: str = Field(..., min_length=1, max_length=8000)


class FollowupSendRequest(BaseModel):
    """D9: sent from Vocify via Resend. subject/body are the rep's final, reviewed text -
    the same ones the ready draft or a hand edit produced."""
    to: EmailStr
    subject: str = Field("", max_length=300)
    body: str = Field(..., min_length=1, max_length=8000)


class WritingSamplesRequest(BaseModel):
    samples: list[Annotated[str, Field(max_length=RAW_SAMPLE_MAX)]] = Field(default_factory=list, max_length=10)


class FollowupSkipRequest(BaseModel):
    """The rep doesn't want to send this draft; undo puts it back while they still can."""
    undo: bool = False


class FollowupPreference(BaseModel):
    """Whether Vocify drafts follow-up emails for this rep at all."""
    suggest: bool
