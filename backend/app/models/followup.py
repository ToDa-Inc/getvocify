"""Request model for follow-up hand-off actions."""
from typing import Literal

from pydantic import BaseModel, Field


class FollowupActionRequest(BaseModel):
    action: Literal["sent", "copied"]
    channel: Literal["email", "whatsapp"] = "email"
    subject: str = Field("", max_length=300)
    body: str = Field(..., min_length=1, max_length=8000)
