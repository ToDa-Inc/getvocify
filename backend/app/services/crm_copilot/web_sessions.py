"""Web Ask turns. Repeating a client turn id does not run the operation twice."""

from __future__ import annotations

import json


class TurnConflict(Exception):
    pass


class UncertainOperation(Exception):
    pass


# WhatsApp session plumbing: the web has a New chat button, and its prompt carries what the skills said.
WEB_HIDDEN_TOOLS = frozenset({"load_skill", "remember", "reset_session"})
# The Vocify-data tools (flag ASK_VOCIFY_DATA_TOOLS_ENABLED) serve WhatsApp; the web assistant has richer ones.
from app.services.crm_copilot.tools import ASK_DATA_TOOLS as _WHATSAPP_DATA_TOOLS  # noqa: E402
_STORED_KEYS = (
    "question", "coverage", "item_count", "choices", "confirmation", "call_targets", "steps",
    "evidence", "coverage_note", "memory", "cards",
)


def _encode_completed_body(turn: dict) -> str:
    payload: dict = {"__vocify_turn__": 1, "text": turn.get("text") or ""}
    for key in _STORED_KEYS:
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
    if row.get("created_at"):
        turn["created_at"] = row["created_at"]
    if status not in ("completed", "failed"):
        turn["question"] = body
        return turn
    if body.startswith("{"):
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            return turn
        if payload.get("__vocify_turn__"):
            turn["text"] = payload.get("text") or ""
            for key in _STORED_KEYS:
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
        status = turn.get("status")
        if status not in ("completed", "failed"):
            return
        (
            self.supabase.table("copilot_web_turns")
            .update({"status": status, "body": _encode_completed_body(turn)})
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

    def list_turns(self, *, user_id, conversation_id=None):
        query = (
            self.supabase.table("copilot_web_turns")
            .select("id,conversation_id,client_turn_id,status,body,created_at")
            .eq("user_id", user_id)
        )
        if conversation_id:
            query = query.eq("conversation_id", conversation_id)
        rows = list(getattr(query.limit(500).execute(), "data", None) or [])
        rows.sort(key=lambda row: str(row.get("created_at") or ""))
        return [_turn_from_row(row) for row in rows]

    def delete_conversation(self, *, user_id, conversation_id):
        (
            self.supabase.table("copilot_web_turns")
            .delete()
            .eq("user_id", user_id)
            .eq("conversation_id", conversation_id)
            .execute()
        )

    def delete_all(self, *, user_id):
        self.supabase.table("copilot_web_turns").delete().eq("user_id", user_id).execute()

    def latest_memory(self, *, user_id, conversation_id):
        for turn in reversed(self.list_turns(user_id=user_id, conversation_id=conversation_id)):
            if turn.get("status") == "completed" and turn.get("memory"):
                return turn["memory"]
        return None

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
    operation = {
        "operation_id": confirmation["operation_id"],
        "revision": confirmation["revision"],
        "contact_id": confirmation["contact_id"],
        "applied": applied,
    }
    for key in ("tool", "args"):
        if key in confirmation:
            operation[key] = confirmation[key]
    if confirmation.get("cancelled"):
        return {**operation, "status": "cancelled"}
    if applied:
        return {**operation, "status": "succeeded"}
    state = confirmation.get("state")
    return {**operation, "status": state if state in ("failed", "uncertain") else "proposed"}


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
        "question": text,
        "replayed": False,
    }
    store[key] = turn
    return turn


def cancel_operation(
    operation: dict,
    *,
    operation_id: str,
) -> dict:
    if operation.get("operation_id") != operation_id:
        raise TurnConflict("operación distinta")
    if operation.get("status") == "cancelled":
        return {**operation, "replayed": True}
    return {**operation, "status": "cancelled", "replayed": False}


def confirm_operation(
    operation: dict,
    *,
    operation_id: str,
    revision: int,
    contact_id: str,
) -> dict:
    if operation.get("status") == "cancelled":
        raise TurnConflict("operación cancelada")
    if operation.get("status") == "uncertain":
        raise UncertainOperation("reconciliar antes de repetir")
    if operation.get("operation_id") != operation_id or operation.get("revision") != revision:
        raise TurnConflict("operación o revisión distinta")
    if operation.get("contact_id") != contact_id:
        raise TurnConflict("el contacto cambió")
    if operation.get("applied"):
        return {**operation, "replayed": True}
    return {**operation, "applied": True, "status": "succeeded", "replayed": False}


_sessions: dict[tuple[str, str], dict] = {}
_MEMORY_KEYS = (
    "last_contact_id", "last_contact_name", "last_company_id", "last_deal_id", "last_contact_url", "last_deal_url",
    "memo_id", "memory", "focus_at", "pending_tool", "pending_args", "pending_id", "choices",
)


def session_for(user_id: str, conversation_id: str) -> dict:
    """Working memory is per conversation. It lives here while the process is up."""
    return _sessions.setdefault((user_id, conversation_id or ""), {})


def seed_session(user_id: str, conversation_id: str, memory: dict | None) -> None:
    """Restore memory from the last stored turn. A live session is never overwritten."""
    key = (user_id, conversation_id or "")
    if key in _sessions or not isinstance(memory, dict) or not memory:
        return
    _sessions[key] = {"copilot": dict(memory)}


def memory_snapshot(artifacts: dict) -> dict:
    """What survives a restart: recent messages, the focused record, and any pending operation."""
    copilot = (artifacts or {}).get("copilot") or {}
    snap = {k: copilot[k] for k in _MEMORY_KEYS if copilot.get(k) is not None}
    from app.services.crm_copilot.loop import _trim

    snap["messages"] = _trim(list(copilot.get("messages") or []))  # the same window the model sees live, cut at a question
    return snap


def public_answer(text: str) -> str:
    """Drop tool-call lines and filler openers/closers ("¡Claro!", "Si necesitas algo
    más…"). Every sentence with content stays exactly as it was."""
    import re

    from app.services.text_guard import strip_chat_filler

    kept = []
    for line in (text or "").splitlines():
        stripped = line.strip()
        if re.search(r"^(tool_call|function_call|call_id)\b", stripped, re.I):
            continue
        kept.append(line)
    return strip_chat_filler("\n".join(kept).strip())


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
        contact_id = args.get("contact_id") or args.get("contactId") or copilot.get("last_contact_id")
        operation_id = copilot.get("pending_id")
        if contact_id and operation_id:
            body["confirmation"] = {
                "operation_id": operation_id,
                "revision": int(copilot.get("revision") or 1),
                "contact_id": contact_id,
            }
            if copilot.get("pending_tool"):
                # Server side only: what the confirm will run. The public turn never shows these.
                body["confirmation"]["tool"] = copilot["pending_tool"]
                body["confirmation"]["args"] = args
    return body


def bind_ask_actor(
    user_id: str,
    company_id: str,
    role: str = "member",
    conversation_id: str | None = None,
    *,
    progress_key: tuple | None = None,
    visibility: str | None = None,
    sales_role: str | None = None,
) -> None:
    """Read synchronously by live_ask_loop before its first await, so concurrent requests never see
    each other's actor. progress_key is where the loop reports its steps while a POST is still running."""
    from app.services.crm_copilot.actor import AskActor, bind_actor

    _actor.update(user_id=user_id, company_id=company_id, conversation_id=conversation_id or "", progress_key=progress_key)
    bind_actor(
        AskActor(
            user_id=user_id, company_id=company_id, role=role, conversation_id=conversation_id,
            progress_key=progress_key, visibility=visibility, sales_role=sales_role,
        )
    )


# The last bound actor as a plain dict. The request-scoped truth is actor.current_actor(); this mirror
# exists for callers that only need to see who was bound last.
_actor: dict = {}

# Live progress of turns still running in this process: (user, conversation, client_turn_id)
# -> {"steps": [...], "at": monotonic}. Bounded so a crashed turn never leaks.
_PROGRESS: dict[tuple, dict] = {}
_PROGRESS_MAX = 500
_PROGRESS_TTL_S = 600.0


def progress_start(key: tuple) -> None:
    import time

    now = time.monotonic()
    for stale in [k for k, v in _PROGRESS.items() if now - v["at"] > _PROGRESS_TTL_S]:
        _PROGRESS.pop(stale, None)
    while len(_PROGRESS) >= _PROGRESS_MAX:
        _PROGRESS.pop(next(iter(_PROGRESS)))
    _PROGRESS[key] = {"steps": [], "at": now}


def progress_step(key: tuple | None, step: dict) -> None:
    """A running step appends; its done/error event updates that same step in place."""
    entry = _PROGRESS.get(key) if key else None
    if entry is None:
        return
    steps = entry["steps"]
    if step.get("state") != "running":
        for existing in reversed(steps):
            if existing["tool"] == step["tool"] and existing["state"] == "running":
                existing["state"] = step["state"]
                return
    steps.append(dict(step))


def progress_get(key: tuple) -> dict | None:
    entry = _PROGRESS.get(key)
    return {"steps": [dict(step) for step in entry["steps"]]} if entry else None


def progress_end(key: tuple) -> None:
    _PROGRESS.pop(key, None)


def session_key(user_id: str, conversation_id: str) -> str:
    """Memory per conversation: a new conversation in the app starts clean."""
    return f"{user_id}:{conversation_id}" if conversation_id else user_id


def _as_list(value) -> list:
    return list(value) if isinstance(value, (list, tuple)) else []


async def live_ask_loop(text: str, confirm: bool | None = None, on_event=None):
    """Same copilot loop as WhatsApp. A failure returns None so the turn can fail."""
    import logging

    from app.config import settings
    from app.deps import get_supabase
    from app.services.crm_copilot.call_actions import public_call_targets
    from app.services.crm_copilot import model_profile
    from app.services.crm_copilot.actor import current_actor
    from app.services.crm_copilot.effort import LOW, choose_effort
    from app.services.crm_copilot.grounding import coverage_note, resolve_evidence, strip_trailing_offer
    from app.services.crm_copilot.intel_tools import intel_tools_for, team_roster
    from app.services.crm_copilot.language import answer_hint, reply_language
    from app.services.crm_copilot.loop import run_copilot_turn
    from app.services.crm_copilot.prompts import build_system_prompt
    from app.services.crm_copilot.tools import OPENAI_TOOLS, CopilotContext, execute_tool
    from app.services.llm.client import LLMClient

    actor = current_actor()
    artifacts = session_for(actor.user_id, actor.conversation_id or "")
    kwargs = {"on_event": on_event} if on_event is not None else {}
    ctx = CopilotContext(
        supabase=get_supabase(),
        user_id=actor.user_id,
        artifacts=artifacts,
        conversation_id=actor.conversation_id,
        actor=actor,
    )
    progress_key = actor.progress_key
    steps: list[dict] = []

    def on_step(step: dict) -> None:
        progress_step(progress_key, step)
        if step.get("state") == "running":
            steps.append(dict(step))
        else:
            for existing in reversed(steps):
                if existing["tool"] == step["tool"] and existing["state"] == "running":
                    existing["state"] = step["state"]
                    break

    team = team_roster(ctx, actor) if actor.is_team_reader else None
    effort = await choose_effort(text) if settings.ASK_EFFORT_ROUTING and confirm is None else LOW
    try:
        result = await run_copilot_turn(
            text,
            artifacts=artifacts,
            llm=LLMClient(),
            execute=execute_tool,
            tools=[*(t for t in OPENAI_TOOLS if t["function"]["name"] not in WEB_HIDDEN_TOOLS | _WHATSAPP_DATA_TOOLS), *intel_tools_for(actor)],
            system=build_system_prompt(artifacts, web=True, manager=actor.is_team_reader, tz=actor.timezone, team=team),
            confirm=confirm,
            ctx=ctx,
            model=model_profile.ask_model(),
            fallback_model=model_profile.ask_fallback_model(),
            verify_numbers=True,
            max_rounds=settings.ASK_MAX_ROUNDS,
            effort=effort,
            retry_empty=True,
            with_data=False,
            answer_hint=answer_hint(reply_language(text)),
            on_step=on_step,
            **kwargs,
        )
    except Exception:
        logging.getLogger(__name__).exception("ask loop failed")
        return None
    body = payload_from_turn(result.text or "", artifacts, kind=result.kind)
    answer, used = resolve_evidence(strip_trailing_offer(body["text"]), _as_list(getattr(result, "evidence", None)))
    body["text"] = answer
    if used:
        body["evidence"] = used
    note = coverage_note(_as_list(getattr(result, "envelopes", None)))
    if note:
        body["coverage_note"] = note
    body["memory"] = memory_snapshot(artifacts)
    if steps:
        body["steps"] = steps
    targets = public_call_targets(ctx, kind=result.kind)
    if targets:
        body["call_targets"] = targets
    if result.kind == "text" and ctx.cards:
        body["cards"] = list(ctx.cards)
    return body


async def execute_stored_operation(operation: dict) -> dict:
    """Run exactly what the user was shown, then report what happened. Never assume success."""
    from app.deps import get_supabase
    from app.services.crm_copilot import tools as copilot_tools
    from app.services.crm_copilot.actor import current_actor

    actor = current_actor()
    tool, args = operation.get("tool"), operation.get("args") or {}
    artifacts = session_for(actor.user_id, actor.conversation_id or "")
    ctx = copilot_tools.CopilotContext(
        supabase=get_supabase(),
        user_id=actor.user_id,
        artifacts=artifacts,
        conversation_id=actor.conversation_id,
        actor=actor,
    )
    result = await copilot_tools.execute_tool(tool, args, ctx)
    body = result if isinstance(result, dict) else {}
    error = body.get("error")
    failed = bool(error) or body.get("ok") is False
    _close_pending(artifacts, operation.get("operation_id"), result)
    if not failed:
        url = body.get("url") or body.get("contact_url") or body.get("deal_url")
        return {"status": "succeeded", "applied": True, **({"url": url} if url else {})}
    lowered = str(error or "").lower()
    if "timeout" in lowered or "timed out" in lowered:
        return {"status": "uncertain", "applied": False}
    return {"status": "failed", "applied": False}


def _close_pending(artifacts: dict, operation_id: str | None, result) -> None:
    """The write is settled. The model's next turn must see its result, and cannot re-run it."""
    copilot = artifacts.setdefault("copilot", {})
    call_id = copilot.get("pending_id") or operation_id
    messages = copilot.setdefault("messages", [])
    if call_id and any(
        tc.get("id") == call_id for m in messages if m.get("role") == "assistant" for tc in (m.get("tool_calls") or [])
    ):
        messages.append({"role": "tool", "tool_call_id": call_id, "content": json.dumps(result, default=str)[:2000]})
    for key in ("pending_tool", "pending_args", "pending_id", "last_preview_text"):
        copilot.pop(key, None)


def attach_read(turn: dict, envelope: dict) -> dict:
    """A finished read keeps its coverage. Forbidden is not an empty result."""
    coverage = envelope.get("coverage")
    items = envelope.get("items") or []
    count = len(items) if coverage == "complete" else 0
    return {**turn, "status": "completed", "coverage": coverage, "item_count": count}
