"""
Pydantic models for conversation context.
"""

from datetime import datetime
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel


ConversationStateEnum = Literal[
    "idle",
    "waiting_approval",
    "waiting_add_fields",
    "waiting_crm_instruction",
    "waiting_deal_choice",
]

MessageDirection = Literal["inbound", "outbound"]
MessageContentType = Literal["text", "extraction_summary", "system"]


class Conversation(BaseModel):
    """Conversation (one per chat)."""

    id: UUID
    chat_id: str
    account_id: str
    user_id: UUID
    channel: str = "whatsapp"
    created_at: datetime
    updated_at: datetime


class ConversationMessage(BaseModel):
    """Single message in a conversation."""

    id: UUID
    conversation_id: UUID
    direction: MessageDirection
    content_type: MessageContentType = "text"
    content: Optional[str] = None
    metadata: dict[str, Any] = {}
    created_at: datetime


class ConversationState(BaseModel):
    """Explicit state for intent resolution."""

    conversation_id: UUID
    state: ConversationStateEnum = "idle"
    pending_memo_id: Optional[UUID] = None
    pending_artifact_ids: Optional[dict[str, Any]] = None
    state_expires_at: Optional[datetime] = None
    updated_at: datetime
