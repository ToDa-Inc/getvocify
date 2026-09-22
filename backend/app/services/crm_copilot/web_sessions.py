"""Web Ask turns. Repeating a client turn id does not run the operation twice."""

from __future__ import annotations

import json


class TurnConflict(Exception):
    pass


class UncertainOperation(Exception):
    pass


def _encode_completed_body(turn: dict) -> str:
    payload: dict = {"__vocify_turn__": 1, "text": turn.get("text") or ""}
    for key in ("coverage", "item_count", "choices", "confirmation"):
        value = turn.get(key)
        if value is not None:
            payload[key] = value
    return json.dumps(payload, ensure_ascii=False)


def _turn_from_row(row: dict) -> dict:
    status = row.get("status") or "pending"
    body = row.get("body") or ""
    turn = {
        "conversation_id": row.get("conversation_id"),
        "turn_id": row.get("id"),
        "status": status,
        "client_turn_id": row.get("client_turn_id"),
        "text": body,
    }
    if status != "completed":
        return turn
    if body.startswith("{"):
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            return turn
        if payload.get("__vocify_turn__"):
            turn["text"] = payload.get("text") or ""
            for key in ("coverage", "item_count", "choices", "confirmation"):
                if key in payload:
                    turn[key] = payload[key]
    return turn


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
        replayed = bool(row.get("replayed"))
        turn_id = row.get("turn_id")
        if replayed and turn_id:
            loaded = self.get_turn(
                user_id=user_id,
                conversation_id=conversation_id,
                turn_id=turn_id,
            )
            if loaded:
                return {**loaded, "replayed": True}
        return {
            "conversation_id": conversation_id,
            "turn_id": turn_id,
            "status": "pending",
            "client_turn_id": client_turn_id,
            "text": row.get("body") or text,
            "replayed": False,
        }

    def persist_turn(self, *, user_id, conversation_id, turn_id, turn: dict) -> None:
        if turn.get("status") != "completed":
            return
        (
            self.supabase.table("copilot_web_turns")
            .update({"status": "completed", "body": _encode_completed_body(turn)})
            .eq("id", turn_id)
            .eq("user_id", user_id)
            .eq("conversation_id", conversation_id)
            .execute()
        )

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
        return _turn_from_row(rows[0])

    def get_turn_by_operation(self, *, user_id, conversation_id, operation_id):
        result = (
            self.supabase.table("copilot_web_turns")
            .select("id,conversation_id,client_turn_id,status,body,user_id")
            .eq("user_id", user_id)
            .eq("conversation_id", conversation_id)
            .eq("status", "completed")
            .execute()
        )
        rows = list(getattr(result, "data", None) or [])
        for row in rows:
            turn = _turn_from_row(row)
            confirmation = turn.get("confirmation") or {}
            if confirmation.get("operation_id") == operation_id:
                return turn
        return None


def proposed_operation_from_turn(turn: dict, operation_id: str) -> dict | None:
    confirmation = turn.get("confirmation") or {}
    if confirmation.get("operation_id") != operation_id:
        return None
    applied = bool(confirmation.get("applied"))
    return {
        "operation_id": confirmation["operation_id"],
        "revision": confirmation["revision"],
        "contact_id": confirmation["contact_id"],
        "applied": applied,
        "status": "succeeded" if applied else "proposed",
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


def public_answer(text: str) -> str:
    """Drop tool-call lines. A normal sentence stays as it was."""
    import re

    kept = []
    for line in (text or "").splitlines():
        stripped = line.strip()
        if re.search(r"^(tool_call|function_call|call_id)\b", stripped, re.I):
            continue
        kept.append(line)
    return "\n".join(kept).strip()


def public_choices(artifacts: dict | None, *, kind: str = "text") -> list[dict] | None:
    if kind != "choices":
        return None
    copilot = (artifacts or {}).get("copilot") or {}
    rows = []
    for choice in list(copilot.get("choices") or [])[:10]:
        cid = str(choice.get("id") or "").strip()
        label = str(choice.get("label") or "").strip()
        if not cid or not label:
            continue
        rows.append({"id": cid, "label": label})
    return rows or None


def payload_from_turn(text: str, artifacts: dict | None = None, *, kind: str = "text") -> dict:
    coverage = (artifacts or {}).get("crm_coverage")
    body = {"text": public_answer(text)}
    if coverage in {"unavailable", "forbidden", "partial"}:
        body["envelope"] = {"items": [], "coverage": coverage}
    choices = public_choices(artifacts, kind=kind)
    if choices:
        body["choices"] = choices
    if kind == "confirm":
        copilot = (artifacts or {}).get("copilot") or {}
        args = copilot.get("pending_args") or {}
        contact_id = args.get("contact_id") or args.get("contactId")
        operation_id = copilot.get("pending_id")
        if contact_id and operation_id:
            body["confirmation"] = {
                "operation_id": operation_id,
                "revision": int(copilot.get("revision") or 1),
                "contact_id": contact_id,
            }
    return body


def bind_ask_actor(user_id: str, company_id: str) -> None:
    _actor["user_id"] = user_id
    _actor["company_id"] = company_id


async def live_ask_loop(text: str, confirm: bool | None = None):
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
            confirm=confirm,
            ctx=CopilotContext(supabase=get_supabase(), user_id=user_id, artifacts=artifacts),
        )
    except Exception:
        logging.getLogger(__name__).exception("ask loop failed")
        return None
    return payload_from_turn(result.text or "", artifacts, kind=result.kind)


def attach_read(turn: dict, envelope: dict) -> dict:
    """A finished read keeps its coverage. Forbidden is not an empty result."""
    coverage = envelope.get("coverage")
    items = envelope.get("items") or []
    count = len(items) if coverage == "complete" else 0
    return {**turn, "status": "completed", "coverage": coverage, "item_count": count}
