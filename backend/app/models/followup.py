"""Request models for follow-up hand-off actions and the rep's pasted writing samples."""
from typing import Annotated, Literal

from pydantic import BaseModel, Field

# Raw, before trimming: clean_pasted enforces 40-1500 on the trimmed text, so this only
# stops an oversized body from reaching it.
RAW_SAMPLE_MAX = 5000


class FollowupActionRequest(BaseModel):
    action: Literal["sent", "copied"]
    channel: Literal["email", "whatsapp"] = "email"
    subject: str = Field("", max_length=300)
    body: str = Field(..., min_length=1, max_length=8000)


class WritingSamplesRequest(BaseModel):
    samples: list[Annotated[str, Field(max_length=RAW_SAMPLE_MAX)]] = Field(default_factory=list, max_length=10)
