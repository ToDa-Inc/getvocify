"""
Conversation context service: CRUD for conversations, messages, and state.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from supabase import Client

from app.deps import get_supabase
from app.models.conversation import (
    Conversation,
    ConversationMessage,
    ConversationState,
    ConversationStateEnum,
    MessageContentType,
    MessageDirection,
)

logger = logging.getLogger(__name__)

STATE_TTL_HOURS = 2


class ConversationService:
    """Create/lookup conversations, persist messages, manage state."""

    def __init__(self, supabase: Client | None = None) -> None:
        self.supabase = supabase or get_supabase()

    def get_or_create_conversation(
        self,
        chat_id: str,
        account_id: str,
        user_id: str,
        channel: str = "whatsapp",
    ) -> Optional[Conversation]:
        """
        Lookup conversation by chat_id, or create if not exists.
        Returns None if creation fails.
        """
        if not chat_id or not account_id or not user_id:
            return None

        try:
            r = (
                self.supabase.table("conversations")
                .select("*")
                .eq("chat_id", chat_id)
                .limit(1)
                .execute()
            )
            if r.data and len(r.data) > 0:
                row = r.data[0]
                return Conversation(
                    id=UUID(row["id"]),
                    chat_id=row["chat_id"],
                    account_id=row["account_id"],
                    user_id=UUID(row["user_id"]),
                    channel=row.get("channel", "whatsapp"),
                    created_at=datetime.fromisoformat(row["created_at"].replace("Z", "+00:00")),
                    updated_at=datetime.fromisoformat(row["updated_at"].replace("Z", "+00:00")),
                )

            insert = {
                "chat_id": chat_id,
                "account_id": account_id,
                "user_id": user_id,
                "channel": channel,
            }
            ins = self.supabase.table("conversations").insert(insert).execute()
            if not ins.data:
                return None
            row = ins.data[0]
            return Conversation(
                id=UUID(row["id"]),
                chat_id=row["chat_id"],
                account_id=row["account_id"],
                user_id=UUID(row["user_id"]),
                channel=row.get("channel", "whatsapp"),
                created_at=datetime.fromisoformat(row["created_at"].replace("Z", "+00:00")),
                updated_at=datetime.fromisoformat(row["updated_at"].replace("Z", "+00:00")),
            )
        except Exception as e:
            logger.exception("get_or_create_conversation failed: %s", e)
            return None

    def get_conversation_by_chat_id(self, chat_id: str) -> Optional[Conversation]:
        """Lookup conversation by chat_id. Returns None if not found."""
        if not chat_id:
            return None
        try:
            r = (
                self.supabase.table("conversations")
                .select("*")
                .eq("chat_id", chat_id)
                .limit(1)
                .execute()
            )
            if not r.data:
                return None
            row = r.data[0]
            return Conversation(
                id=UUID(row["id"]),
                chat_id=row["chat_id"],
                account_id=row["account_id"],
                user_id=UUID(row["user_id"]),
                channel=row.get("channel", "whatsapp"),
                created_at=datetime.fromisoformat(row["created_at"].replace("Z", "+00:00")),
                updated_at=datetime.fromisoformat(row["updated_at"].replace("Z", "+00:00")),
            )
        except Exception as e:
            logger.exception("get_conversation_by_chat_id failed: %s", e)
            return None

    def add_message(
        self,
        conversation_id: UUID,
        direction: MessageDirection,
        content: Optional[str] = None,
        content_type: MessageContentType = "text",
        metadata: Optional[dict] = None,
    ) -> Optional[ConversationMessage]:
        """Persist a message. Returns the created message or None."""
        try:
            insert = {
                "conversation_id": str(conversation_id),
                "direction": direction,
                "content": content or "",
                "content_type": content_type,
                "metadata": metadata or {},
            }
            r = self.supabase.table("conversation_messages").insert(insert).execute()
            if not r.data:
                return None
            row = r.data[0]
            return ConversationMessage(
                id=UUID(row["id"]),
                conversation_id=UUID(row["conversation_id"]),
                direction=row["direction"],
                content_type=row.get("content_type", "text"),
                content=row.get("content"),
                metadata=row.get("metadata", {}),
                created_at=datetime.fromisoformat(row["created_at"].replace("Z", "+00:00")),
            )
        except Exception as e:
            logger.exception("add_message failed: %s", e)
            return None

    def get_last_messages(
        self,
        conversation_id: UUID,
        limit: int = 10,
    ) -> list[dict]:
        """
        Return last N messages as dicts with direction, content, content_type, metadata, created_at.
        """
        try:
            r = (
                self.supabase.table("conversation_messages")
                .select("direction, content, content_type, metadata, created_at")
                .eq("conversation_id", str(conversation_id))
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
            if not r.data:
                return []
            return list(reversed(r.data))
        except Exception as e:
            logger.exception("get_last_messages failed: %s", e)
            return []

    def get_state(self, conversation_id: UUID) -> Optional[ConversationState]:
        """Load conversation state from conversations row. Returns None if not found (treat as idle)."""
        try:
            r = (
                self.supabase.table("conversations")
                .select("id, state, pending_memo_id, pending_artifact_ids, state_expires_at, updated_at")
                .eq("id", str(conversation_id))
                .limit(1)
                .execute()
            )
            if not r.data:
                return None
            row = r.data[0]
            return ConversationState(
                conversation_id=UUID(row["id"]),
                state=row.get("state", "idle"),
                pending_memo_id=UUID(row["pending_memo_id"]) if row.get("pending_memo_id") else None,
                pending_artifact_ids=row.get("pending_artifact_ids"),
                state_expires_at=(
                    datetime.fromisoformat(row["state_expires_at"].replace("Z", "+00:00"))
                    if row.get("state_expires_at")
                    else None
                ),
                updated_at=datetime.fromisoformat(row["updated_at"].replace("Z", "+00:00")),
            )
        except Exception as e:
            logger.exception("get_state failed: %s", e)
            return None

    def set_state(
        self,
        conversation_id: UUID,
        state: ConversationStateEnum,
        pending_memo_id: Optional[str] = None,
        pending_artifact_ids: Optional[dict] = None,
    ) -> None:
        """
        Upsert conversation state.
        Sets state_expires_at when state is waiting_*.
        """
        now = datetime.now(timezone.utc)
        expires_at = (now + timedelta(hours=STATE_TTL_HOURS)).isoformat() if state != "idle" else None

        data: dict = {
            "state": state,
            "state_expires_at": expires_at,
            "updated_at": now.isoformat(),
        }
        if pending_memo_id is not None:
            data["pending_memo_id"] = pending_memo_id
        if pending_artifact_ids is not None:
            data["pending_artifact_ids"] = pending_artifact_ids
        if state == "idle":
            data["pending_memo_id"] = None
            data["pending_artifact_ids"] = None

        try:
            self.supabase.table("conversations").update(data).eq(
                "id", str(conversation_id)
            ).execute()
        except Exception as e:
            logger.exception("set_state failed: %s", e)
            raise

    def is_state_expired(self, state: ConversationState) -> bool:
        """Return True if state has expired (past state_expires_at)."""
        if not state.state_expires_at:
            return False
        return datetime.now(timezone.utc) > state.state_expires_at
