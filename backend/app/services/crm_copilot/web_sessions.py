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


_actor: dict[str, str] = {}
_sessions: dict[str, dict] = {}


def payload_from_turn(text: str, artifacts: dict | None = None) -> dict:
    coverage = (artifacts or {}).get("crm_coverage")
    body = {"text": text}
    if coverage in {"unavailable", "forbidden", "partial"}:
        body["envelope"] = {"items": [], "coverage": coverage}
    return body


def bind_ask_actor(user_id: str, company_id: str) -> None:
    _actor["user_id"] = user_id
    _actor["company_id"] = company_id


async def live_ask_loop(text: str):
    """Same copilot loop as WhatsApp. A failure leaves the turn pending."""
    import logging

    from app.deps import get_supabase
    from app.services.crm_copilot.loop import run_copilot_turn
    from app.services.crm_copilot.prompts import build_system_prompt
    from app.services.crm_copilot.tools import OPENAI_TOOLS, CopilotContext, execute_tool
    from app.services.llm.client import LLMClient

    user_id = _actor.get("user_id") or ""
    artifacts = _sessions.setdefault(user_id, {})
    try:
        result = await run_copilot_turn(
            text,
            artifacts=artifacts,
            llm=LLMClient(),
            execute=execute_tool,
            tools=OPENAI_TOOLS,
            system=build_system_prompt(artifacts),
            ctx=CopilotContext(supabase=get_supabase(), user_id=user_id, artifacts=artifacts),
        )
    except Exception:
        logging.getLogger(__name__).exception("ask loop failed")
        return None
    return payload_from_turn(result.text or "", artifacts)


def attach_read(turn: dict, envelope: dict) -> dict:
    """A finished read keeps its coverage. Forbidden is not an empty result."""
    coverage = envelope.get("coverage")
    items = envelope.get("items") or []
    count = len(items) if coverage == "complete" else 0
    return {**turn, "status": "completed", "coverage": coverage, "item_count": count}
