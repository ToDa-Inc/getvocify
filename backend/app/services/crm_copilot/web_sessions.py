"""Web Ask turns. Repeating a client turn id does not run the operation twice."""

from __future__ import annotations


class TurnConflict(Exception):
    pass


class UncertainOperation(Exception):
    pass


class SupabaseAskStore:
    def __init__(self, supabase):
        self.supabase = supabase

    def save_turn(self, *, user_id, company_id, conversation_id, client_turn_id, text):
        result = self.supabase.rpc(
            "save_ask_turn",
            {
                "p_company": company_id,
                "p_user": user_id,
                "p_conversation": conversation_id,
                "p_client_turn": client_turn_id,
                "p_text": text,
            },
        ).execute()
        rows = list(getattr(result, "data", None) or [])
        row = rows[0] if rows else {}
        return {
            "conversation_id": conversation_id,
            "turn_id": row.get("turn_id"),
            "status": "pending",
            "client_turn_id": client_turn_id,
            "text": row.get("body") or text,
        }

    def get_turn(self, *, user_id, conversation_id, turn_id):
        result = (
            self.supabase.table("copilot_web_turns")
            .select("id,conversation_id,client_turn_id,status,body,user_id")
            .eq("id", turn_id)
            .eq("user_id", user_id)
            .eq("conversation_id", conversation_id)
            .limit(1)
            .execute()
        )
        rows = list(getattr(result, "data", None) or [])
        if not rows:
            return None
        row = rows[0]
        return {
            "conversation_id": row.get("conversation_id"),
            "turn_id": row.get("id"),
            "status": row.get("status") or "pending",
            "client_turn_id": row.get("client_turn_id"),
            "text": row.get("body") or "",
        }


def accept_turn(store: dict, *, conversation_id: str, client_turn_id: str, text: str) -> dict:
    key = (conversation_id, client_turn_id)
    existing = store.get(key)
    if existing:
        return {**existing, "replayed": True}
    turn = {
        "conversation_id": conversation_id,
        "turn_id": f"turn-{len(store) + 1}",
        "status": "pending",
        "client_turn_id": client_turn_id,
        "text": text,
        "replayed": False,
    }
    store[key] = turn
    return turn


def confirm_operation(
    operation: dict,
    *,
    operation_id: str,
    revision: int,
    contact_id: str,
) -> dict:
    if operation.get("status") == "uncertain":
        raise UncertainOperation("reconciliar antes de repetir")
    if operation.get("operation_id") != operation_id or operation.get("revision") != revision:
        raise TurnConflict("operación o revisión distinta")
    if operation.get("contact_id") != contact_id:
        raise TurnConflict("el contacto cambió")
    if operation.get("applied"):
        return {**operation, "replayed": True}
    return {**operation, "applied": True, "status": "succeeded", "replayed": False}


def attach_read(turn: dict, envelope: dict) -> dict:
    """A finished read keeps its coverage. Forbidden is not an empty result."""
    coverage = envelope.get("coverage")
    items = envelope.get("items") or []
    count = len(items) if coverage == "complete" else 0
    return {**turn, "status": "completed", "coverage": coverage, "item_count": count}
