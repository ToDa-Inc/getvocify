from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from app.config import settings
from app.services.crm_copilot.prompts import build_system_prompt, with_data_prompt
from app.services.crm_copilot.route import is_focus_switch, is_reset_command
from app.services.crm_copilot.tools import (
    clear_focus,
    confirmation_required,
    data_tools_enabled,
    execute_tool,
    expire_stale_focus,
    tools_for,
    write_blocked,
)

MAX_HISTORY = 24
COMPACT_KEEP = 6
COMPACT_TOOL_CHARS = 500


@dataclass
class CopilotTurnResult:
    kind: str  # text | confirm | choices
    text: str
    state: str = "idle"
    artifacts: dict = field(default_factory=dict)
    list_sections: Optional[list] = None
    buttons: Optional[list] = None


def _copilot(artifacts: dict) -> dict:
    return artifacts.setdefault("copilot", {})


def _history(copilot: dict) -> list[dict]:
    messages = copilot.setdefault("messages", [])
    if len(messages) > MAX_HISTORY:
        messages = messages[-MAX_HISTORY:]
    copilot["messages"] = _compact_messages(messages)
    return copilot["messages"]


def _compact_messages(messages: list[dict]) -> list[dict]:
    if len(messages) <= COMPACT_KEEP:
        return messages
    cutoff = len(messages) - COMPACT_KEEP
    out = []
    for i, msg in enumerate(messages):
        if i < cutoff and msg.get("role") == "tool":
            content = str(msg.get("content") or "")
            if len(content) > COMPACT_TOOL_CHARS:
                msg = {**msg, "content": content[:COMPACT_TOOL_CHARS] + "…"}
        out.append(msg)
    return out


def _dump(payload: Any) -> str:
    return json.dumps(payload, default=str, ensure_ascii=False)[:8000]


def _is_hollow_preview(text: str) -> bool:
    body = re.sub(r"actualizar or no actualizar\.?", "", text or "", flags=re.I)
    compact = " ".join(body.split()).lower()
    return compact in {"", "contacto", "solo contacto", "contacto solo contacto"}


def _should_save_as_note(name: str, args: dict, copilot: dict) -> bool:
    if name != "apply_write":
        return False
    props = args.get("properties") if isinstance(args.get("properties"), dict) else {}
    if props:
        return False
    if copilot.get("has_field_updates"):
        return False
    return _is_hollow_preview(copilot.get("last_preview_text") or "") or copilot.get("has_field_updates") is False


def _note_args_from_session(args: dict, copilot: dict) -> dict:
    extraction = copilot.get("extraction") or {}
    summary = ""
    if isinstance(extraction, dict):
        summary = str(extraction.get("summary") or "").strip()
    preview = str(copilot.get("last_preview_text") or "").strip()
    if not summary and preview and not _is_hollow_preview(preview):
        summary = preview
    out: dict[str, Any] = {"body": (summary or "Seguimiento")[:1500]}
    contact_id = args.get("contact_id") or copilot.get("last_contact_id")
    deal_id = args.get("deal_id") or copilot.get("last_deal_id")
    if contact_id:
        out["contact_id"] = contact_id
    if deal_id:
        out["deal_id"] = deal_id
    return out


def _confirm_text(name: str, args: dict, copilot: dict) -> str:
    args = args or {}
    if name == "create_note":
        body = str(args.get("body") or "").strip()
        return f"Nota: {body}" if body else "Crear una nota en HubSpot."
    if name == "create_task":
        subject = str(args.get("subject") or "").strip()
        return f"Tarea: {subject}" if subject else "Crear una tarea en HubSpot."
    if name == "create_contact":
        label = " ".join(
            str(args.get(k) or "") for k in ("firstname", "lastname", "email")
        ).strip()
        return f"Crear contacto: {label}" if label else "Crear un contacto en HubSpot."
    if name == "create_deal":
        dealname = str(args.get("dealname") or "").strip()
        return f"Crear deal: {dealname}" if dealname else "Crear un deal en HubSpot."
    preview = str(copilot.get("last_preview_text") or "").strip()
    if preview:
        return preview
    props = args.get("properties") if isinstance(args.get("properties"), dict) else {}
    if props:
        bits = ", ".join(f"{k}={v}" for k, v in list(props.items())[:5])
        target = args.get("object_type") or "registro"
        return f"Actualizar {target}: {bits}"
    return "Confirmar escritura en HubSpot."


def _choice_sections(choices: list[dict]) -> list[dict]:
    rows = []
    for choice in choices[:10]:
        cid = str(choice.get("id") or "")[:200]
        if not cid:
            continue
        rows.append({"id": cid, "title": str(choice.get("label") or cid)[:24]})
    return [{"title": "Opciones", "rows": rows}] if rows else []


def _assistant_raw(result: Any, tool_calls: list[dict]) -> dict:
    raw = getattr(result, "raw_message", None)
    if isinstance(raw, dict) and (raw.get("tool_calls") or raw.get("content") is not None):
        return raw
    return {
        "role": "assistant",
        "content": getattr(result, "content", None),
        "tool_calls": [
            {
                "id": tc["id"],
                "type": "function",
                "function": {
                    "name": tc["name"],
                    "arguments": json.dumps(tc.get("arguments") or {}),
                },
            }
            for tc in tool_calls
        ],
    }


async def run_copilot_turn(
    user_text: str,
    *,
    artifacts: dict,
    llm: Any,
    execute: Optional[Callable] = None,
    tools: list,
    system: Optional[str] = None,
    confirm: Optional[bool] = None,
    selected_choice: Optional[str] = None,
    ctx: Any = None,
    max_rounds: Optional[int] = None,
) -> CopilotTurnResult:
    execute = execute or execute_tool
    artifacts = artifacts if artifacts is not None else {}
    if is_reset_command(user_text) and confirm is None:
        artifacts["copilot"] = {"messages": []}
        return CopilotTurnResult(
            kind="text",
            text="Listo. Sesión nueva — dime un contacto o lo que quieras hacer.",
            state="idle",
            artifacts=artifacts,
        )
    copilot = _copilot(artifacts)
    expire_stale_focus(copilot)
    if is_focus_switch(user_text) and confirm is None and not selected_choice:
        clear_focus(copilot)
    messages = _history(copilot)
    data_tools = data_tools_enabled(ctx)
    tools = tools_for(tools, data_tools=data_tools)
    system_text = system or build_system_prompt(artifacts)
    if data_tools:
        system_text = with_data_prompt(system_text)
    rounds = max_rounds if max_rounds is not None else settings.CRM_COPILOT_MAX_ROUNDS

    if confirm is True and copilot.get("pending_tool"):
        payload = await execute(copilot["pending_tool"], copilot.get("pending_args") or {}, ctx)
        messages.append(
            {
                "role": "tool",
                "tool_call_id": copilot.get("pending_id") or "pending",
                "content": _dump(payload),
            }
        )
        copilot.pop("pending_tool", None)
        copilot.pop("pending_args", None)
        copilot.pop("pending_id", None)
        copilot.pop("last_preview_text", None)
        _touch_session(copilot, payload)
    elif confirm is False and copilot.get("pending_tool"):
        messages.append(
            {
                "role": "tool",
                "tool_call_id": copilot.get("pending_id") or "pending",
                "content": _dump({"ok": False, "error": "user declined"}),
            }
        )
        copilot.pop("pending_tool", None)
        copilot.pop("pending_args", None)
        copilot.pop("pending_id", None)
        copilot.pop("last_preview_text", None)
    elif selected_choice:
        messages.append({"role": "user", "content": f"Selected: {selected_choice}"})
        copilot["choices"] = []
    else:
        if copilot.get("pending_tool"):
            copilot.pop("pending_tool", None)
            copilot.pop("pending_args", None)
            copilot.pop("pending_id", None)
        messages.append({"role": "user", "content": user_text})

    for _ in range(max(1, rounds)):
        result = await llm.chat_tools(
            [{"role": "system", "content": system_text}, *messages],
            tools=tools,
            model=settings.CRM_COPILOT_MODEL,
            provider="openrouter",
            extra={"reasoning": {"effort": "low"}},
            timeout=60.0,
        )
        tool_calls = list(getattr(result, "tool_calls", None) or [])
        if not tool_calls:
            text = (getattr(result, "content", None) or "").strip() or "Done."
            messages.append({"role": "assistant", "content": text})
            copilot["messages"] = messages[-MAX_HISTORY:]
            artifacts["copilot"] = copilot
            return CopilotTurnResult(kind="text", text=text, state="idle", artifacts=artifacts)

        messages.append(_assistant_raw(result, tool_calls))
        pause = None
        for tc in tool_calls:
            name = tc.get("name") or ""
            args = tc.get("arguments") if isinstance(tc.get("arguments"), dict) else {}
            if name == "reset_session":
                artifacts["copilot"] = {"messages": []}
                return CopilotTurnResult(
                    kind="text",
                    text="Listo. Sesión nueva — dime un contacto o lo que quieras hacer.",
                    state="idle",
                    artifacts=artifacts,
                )
            if name == "offer_user_choices":
                pause = ("choices", name, args, tc)
                break
            if confirmation_required(name):
                blocked = await write_blocked(name, ctx)
                if blocked is not None:
                    messages.append(
                        {"role": "tool", "tool_call_id": tc.get("id") or "", "content": _dump(blocked)}
                    )
                    continue
                if _should_save_as_note(name, args, copilot):
                    name = "create_note"
                    args = _note_args_from_session(args, copilot)
                pause = ("confirm", name, args, tc)
                break
            payload = await execute(name, args, ctx)
            _touch_session(copilot, payload)
            if name == "preview_write" and isinstance(payload, dict):
                if payload.get("error") == "no_field_updates" or payload.get("has_field_updates") is False:
                    copilot["has_field_updates"] = False
                    copilot.pop("last_preview_text", None)
                else:
                    copilot["has_field_updates"] = True
                    copilot["last_preview_text"] = str(payload.get("preview_text") or payload.get("summary") or "")[:1500]
                if payload.get("memo_id"):
                    copilot["memo_id"] = payload["memo_id"]
            messages.append(
                {"role": "tool", "tool_call_id": tc.get("id") or "", "content": _dump(payload)}
            )

        if pause:
            kind, name, args, tc = pause
            copilot["messages"] = messages[-MAX_HISTORY:]
            artifacts["copilot"] = copilot
            if kind == "choices":
                choices = list(args.get("choices") or [])
                copilot["choices"] = choices
                prompt = str(args.get("prompt") or "Which one?")
                return CopilotTurnResult(
                    kind="choices",
                    text=prompt,
                    state="waiting_retarget",
                    artifacts=artifacts,
                    list_sections=_choice_sections(choices),
                )
            copilot["pending_tool"] = name
            copilot["pending_args"] = args
            copilot["pending_id"] = tc.get("id")
            return CopilotTurnResult(
                kind="confirm",
                text=_confirm_text(name, args, copilot),
                state="waiting_approval",
                artifacts=artifacts,
            )

    artifacts["copilot"] = copilot
    return CopilotTurnResult(
        kind="text",
        text="I hit the tool-call limit. Ask me to continue.",
        state="idle",
        artifacts=artifacts,
    )


def _touch_session(copilot: dict, payload: Any) -> None:
    if not isinstance(payload, dict):
        return
    for src, dest in (
        ("contact_id", "last_contact_id"),
        ("id", "last_contact_id"),
        ("company_id", "last_company_id"),
        ("deal_id", "last_deal_id"),
        ("contact_url", "last_contact_url"),
        ("url", "last_contact_url"),
        ("deal_url", "last_deal_url"),
        ("memo_id", "memo_id"),
    ):
        val = payload.get(src)
        if val and (src != "id" or payload.get("object") == "contact" or payload.get("email") is not None or payload.get("firstname") is not None):
            if src == "id" and dest == "last_contact_id" and payload.get("object") not in (None, "contact"):
                continue
            if src == "url" and payload.get("object") == "deal":
                copilot["last_deal_url"] = val
                continue
            copilot[dest] = val
    contact = payload.get("contact")
    if isinstance(contact, dict) and contact.get("id"):
        copilot["last_contact_id"] = contact["id"]
        if contact.get("url"):
            copilot["last_contact_url"] = contact["url"]
    contacts = payload.get("contacts")
    if isinstance(contacts, list) and len(contacts) == 1 and isinstance(contacts[0], dict):
        hit = contacts[0]
        if hit.get("id"):
            copilot["last_contact_id"] = hit["id"]
        if hit.get("url"):
            copilot["last_contact_url"] = hit["url"]
    if any(copilot.get(k) for k in ("last_contact_id", "last_deal_id")):
        copilot["focus_at"] = datetime.now(timezone.utc).isoformat()
