from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from app.config import settings
from app.services.crm_copilot.prompts import build_system_prompt
from app.services.crm_copilot.tools import confirmation_required, execute_tool

MAX_HISTORY = 24


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
        copilot["messages"] = messages[-MAX_HISTORY:]
    return copilot["messages"]


def _dump(payload: Any) -> str:
    return json.dumps(payload, default=str, ensure_ascii=False)[:8000]


def _confirm_text(name: str, args: dict, copilot: dict) -> str:
    preview = copilot.get("last_preview_text")
    if preview:
        return f"{preview}\n\nActualizar or No actualizar."
    compact = json.dumps(args, default=str, ensure_ascii=False)[:800]
    return f"Write `{name}`?\n{compact}\n\nActualizar or No actualizar."


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
    artifacts = artifacts or {}
    copilot = _copilot(artifacts)
    messages = _history(copilot)
    system_text = system or build_system_prompt(artifacts)
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
            if name == "offer_user_choices":
                pause = ("choices", name, args, tc)
                break
            if confirmation_required(name):
                pause = ("confirm", name, args, tc)
                break
            payload = await execute(name, args, ctx)
            _touch_session(copilot, payload)
            if name == "preview_write" and isinstance(payload, dict):
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
