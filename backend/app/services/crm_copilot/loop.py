from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional, Union

from app.config import settings
from app.services.crm_copilot.model_profile import request_extra
from app.services.crm_copilot.prompts import build_system_prompt, with_data_prompt
from app.services.crm_copilot.route import is_focus_switch, is_reset_command
from app.services.crm_copilot.tool_view import model_view
from app.services.crm_copilot.tools import (
    clear_focus,
    confirmation_required,
    data_tools_enabled,
    execute_tool,
    expire_stale_focus,
    tools_for,
    write_blocked,
)

logger = logging.getLogger(__name__)

MAX_HISTORY = 24
ESCALATE_AFTER_FAILURES = 2
COMPACT_KEEP = 6
COMPACT_TOOL_CHARS = 500

# Tools the user never needs to see as a step: bookkeeping, or the pause itself.
_SILENT_TOOLS = frozenset({"load_skill", "remember", "reset_session", "offer_user_choices"})
_DETAIL_KEYS = ("query", "name", "q", "email", "dealname", "subject")
EMPTY_ANSWER = "No he encontrado nada que responder. Prueba a preguntarlo de otra forma."
ROUND_LIMIT = "He llegado al límite de pasos para esta pregunta. Pídeme que continúe o acótala."


def step_event(name: str, args: dict, state: str) -> dict:
    """One visible step of a turn: which tool, what it was looking for (a search term, never
    an id), and whether it is running, done or failed. The UI turns `tool` into words."""
    detail = ""
    for key in _DETAIL_KEYS:
        value = (args or {}).get(key)
        if isinstance(value, str) and value.strip():
            detail = " ".join(value.split())[:60]
            break
    return {"tool": name, "state": state, "detail": detail}


@dataclass
class CopilotTurnResult:
    kind: str  # text | confirm | choices
    text: str
    state: str = "idle"
    artifacts: dict = field(default_factory=dict)
    list_sections: Optional[list] = None
    buttons: Optional[list] = None
    # Facts the turn read. The web transport validates citations against these.
    evidence: list = field(default_factory=list)
    coverages: list = field(default_factory=list)
    pending: Optional[dict] = None  # {tool, args, call_id} when kind == "confirm"
    envelopes: list = field(default_factory=list)  # [{coverage, n, n_analysed}] per tool read


EventSink = Callable[[dict], Union[None, Awaitable[None]]]


async def _emit(sink: Optional[EventSink], event: dict) -> None:
    if sink is None:
        return
    outcome = sink(event)
    if hasattr(outcome, "__await__"):
        await outcome


def _tool_summary(name: str, payload: Any) -> dict:
    """Only counts and coverage leave the loop as an event. Raw payloads never do."""
    ok = not (isinstance(payload, dict) and (payload.get("ok") is False or payload.get("error")))
    body = payload if isinstance(payload, dict) else {}
    return {"ok": ok, "coverage": body.get("coverage"), "n": body.get("n")}


# Some models write their tool call as text (DeepSeek's DSML) instead of a structured call. It is never an answer.
_TOOL_MARKUP = re.compile(r"<\s*[｜|]{1,2}\s*DSML|<\s*/?\s*(?:tool_call|function_calls|invoke)\b", re.I)
_MARKUP_PROBE = 12  # characters to read before deciding a streamed reply is text and not markup


def _is_tool_markup(text: Optional[str]) -> bool:
    return bool(text and _TOOL_MARKUP.search(text))


async def _call_llm(llm: Any, messages: list, tools: list, *, model: str, sink: Optional[EventSink], effort: str = "low"):
    """One model call. Streams text to the sink when the client supports it, holding back tool markup."""
    kwargs = dict(tools=tools, model=model, provider="openrouter", timeout=60.0)
    extra = request_extra(model, effort)
    if extra:
        kwargs["extra"] = extra
    if sink is not None and hasattr(llm, "chat_tools_stream"):
        final = None
        held, decided, hide = "", False, False
        async for kind, payload in llm.chat_tools_stream(messages, **kwargs):
            if kind == "delta":
                if hide:
                    continue
                if decided:
                    await _emit(sink, {"type": "content", "delta": payload})
                    continue
                held += payload
                if len(held.strip()) < _MARKUP_PROBE and held.lstrip().startswith("<"):
                    continue
                decided = True
                if _is_tool_markup(held):
                    hide = True
                    continue
                await _emit(sink, {"type": "content", "delta": held})
            elif kind == "final":
                final = payload
        if held and not decided and not _is_tool_markup(held):
            await _emit(sink, {"type": "content", "delta": held})
        if final is None:
            raise RuntimeError("model stream ended without a result")
        return final, True
    return await llm.chat_tools(messages, **kwargs), False


_REASONING_KEYS = ("reasoning", "reasoning_details")


def _without_reasoning(messages: list) -> list:
    """Reasoning belongs to one model and one turn: replay it inside the turn, never across models or into history."""
    return [
        {k: v for k, v in m.items() if k not in _REASONING_KEYS} if isinstance(m, dict) and any(k in m for k in _REASONING_KEYS) else m
        for m in messages
    ]


def _with_hint(messages: list, hint: Optional[str]) -> list:
    """The hint rides on a copy of the last user message; the stored history is untouched."""
    if not hint:
        return messages
    for i in range(len(messages) - 1, -1, -1):
        msg = messages[i]
        if isinstance(msg, dict) and msg.get("role") == "user" and isinstance(msg.get("content"), str):
            return [*messages[:i], {**msg, "content": f"{msg['content']}\n\n{hint}"}, *messages[i + 1 :]]
    return messages


def _copilot(artifacts: dict) -> dict:
    return artifacts.setdefault("copilot", {})


def _trim(messages: list[dict], limit: int = MAX_HISTORY) -> list[dict]:
    """Keep the last `limit` messages, starting at a question: a tool result must never lose the call it answers."""
    if len(messages) <= limit:
        return messages
    start = len(messages) - limit
    while start < len(messages) and messages[start].get("role") != "user":
        start += 1
    return messages[start:] if start < len(messages) else messages[-limit:]


def _settle(messages: list[dict], start: int) -> list[dict]:
    """A finished question keeps its answer, not the lookups behind it: the next turn re-reads what it needs, and
    replaying old results costs tokens on every later call. A turn that began with a confirmation is left as is."""
    segment = messages[start:]
    if len(segment) < 2 or segment[0].get("role") != "user":
        return messages
    return [*messages[:start], segment[0], segment[-1]]


def _history(copilot: dict) -> list[dict]:
    messages = _trim(copilot.setdefault("messages", []))
    copilot["messages"] = _compact_messages(_without_reasoning(messages))
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
    return model_view(payload)


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
    target = ""
    if args.get("contact_id") and args.get("contact_id") == copilot.get("last_contact_id") and copilot.get("last_contact_name"):
        target = f" para {copilot['last_contact_name']}"
    if name == "create_note":
        body = str(args.get("body") or "").strip()
        return f"Nota{target}: {body}" if body else "Crear una nota en el CRM."
    if name == "create_task":
        subject = str(args.get("subject") or "").strip()
        return f"Tarea{target}: {subject}" if subject else "Crear una tarea en el CRM."
    if name == "create_contact":
        label = " ".join(
            str(args.get(k) or "") for k in ("firstname", "lastname", "email")
        ).strip()
        return f"Crear contacto: {label}" if label else "Crear un contacto en el CRM."
    if name == "create_deal":
        dealname = str(args.get("dealname") or "").strip()
        return f"Crear deal: {dealname}" if dealname else "Crear un deal en el CRM."
    preview = str(copilot.get("last_preview_text") or "").strip()
    if preview:
        return preview
    props = args.get("properties") if isinstance(args.get("properties"), dict) else {}
    if props:
        bits = ", ".join(f"{k}={v}" for k, v in list(props.items())[:5])
        target = args.get("object_type") or "registro"
        return f"Actualizar {target}: {bits}"
    return "Confirmar el cambio en el CRM."


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


LIMIT_NUDGE = (
    "You have no lookups left. Answer now from what the tools returned: say what you found and, plainly, "
    "what you could not determine. Do not promise to keep looking."
)
_EMPTY_ANSWER = {
    "es": EMPTY_ANSWER,
    "en": "I could not write the answer. Please ask again.",
}


async def _answer_when_empty(llm, prompt, *, model, sink, question, effort="low"):
    """A model sometimes ends a turn with no text at all. Ask once for the answer; never show a bare 'Done.'."""
    from app.services.crm_copilot.language import reply_language

    nudge = {"role": "user", "content": "Answer my question now with what the tools returned, in the language I wrote it in."}
    retry, streamed = await _call_llm(llm, [*prompt, nudge], [], model=model, sink=sink, effort=effort)
    text = (getattr(retry, "content", None) or "").strip()
    if text:
        return text, streamed
    return _EMPTY_ANSWER[reply_language(question) or "es"], False


async def _enforce_numbers(text, streamed, *, facts, question, llm, prompt, model, sink, effort="low"):
    """Every figure must come from a tool. One rewrite, then drop what is still unverified."""
    from app.services.crm_copilot.grounding import drop_sentences_with, unverified_numbers

    blob = "\n".join(facts)
    bad = unverified_numbers(text, blob, question)
    if not bad:
        return text, streamed
    await _emit(sink, {"type": "content_reset"})
    correction = (
        f"Estas cifras no salen de las herramientas: {', '.join(bad)}. "
        "Reescribe la respuesta usando solo cifras devueltas por las herramientas."
    )
    try:
        retry, _ = await _call_llm(
            llm, [*prompt, {"role": "assistant", "content": text}, {"role": "user", "content": correction}],
            [], model=model, sink=sink, effort=effort,
        )
        text = (getattr(retry, "content", None) or "").strip()
    except Exception:  # the rewrite failed: what is verified still stands, what is not is dropped below
        logger.warning("number rewrite failed; dropping the unverified sentences", exc_info=True)
    bad = unverified_numbers(text, blob, question)
    if bad:
        text = drop_sentences_with(text, bad)
        await _emit(sink, {"type": "content_reset"})
        streamed = False
    text = text or "No puedo confirmar esas cifras con los datos disponibles."
    return text, streamed


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
    on_step: Optional[Callable[[dict], None]] = None,
    on_event: Optional[EventSink] = None,
    model: Optional[str] = None,
    fallback_model: Optional[str] = None,
    verify_numbers: bool = False,
    answer_hint: Optional[str] = None,
    effort: str = "low",
    retry_empty: bool = False,
    with_data: bool = True,
) -> CopilotTurnResult:
    execute = execute or execute_tool

    def report(name: str, args: dict, state: str) -> None:
        if on_step is None or name in _SILENT_TOOLS:
            return
        try:
            on_step(step_event(name, args, state))
        except Exception:
            pass  # progress is best-effort; it never breaks the turn

    # `is None`, not `or`: an empty session dict is still the caller's dict and must receive the updates.
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
    turn_start = len(messages)
    data_tools = data_tools_enabled(ctx)
    tools = tools_for(tools, data_tools=data_tools)
    system_text = system or build_system_prompt(artifacts)
    if data_tools and with_data:  # the web assistant brings its own routing and passes with_data=False
        system_text = with_data_prompt(system_text)
    rounds = max_rounds if max_rounds is not None else settings.CRM_COPILOT_MAX_ROUNDS
    model = model or settings.CRM_COPILOT_MODEL
    evidence: list = []
    coverages: list = []
    envelopes: list = []
    facts: list = []

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

    total_rounds = max(1, rounds)
    failed_lookups = 0
    for round_index in range(total_rounds):
        await _emit(on_event, {"type": "state", "state": "understanding"})
        prompt = [{"role": "system", "content": system_text}, *_with_hint(messages, answer_hint)]
        round_tools = tools
        if round_index == total_rounds - 1 and total_rounds > 1:  # out of lookups: answer with what was found
            prompt = [*prompt, {"role": "user", "content": LIMIT_NUDGE}]
            round_tools = []
        try:
            result, streamed = await _call_llm(llm, prompt, round_tools, model=model, sink=on_event, effort=effort)
        except Exception as exc:
            if not fallback_model or fallback_model == model:
                raise
            logger.warning("Ask model %s failed (%s); using fallback %s", model, str(exc)[:200], fallback_model)
            model = fallback_model
            prompt = _without_reasoning(prompt)
            result, streamed = await _call_llm(llm, prompt, round_tools, model=model, sink=on_event, effort=effort)
        tool_calls = list(getattr(result, "tool_calls", None) or [])
        if not tool_calls and _is_tool_markup(getattr(result, "content", None)):
            logger.warning("Ask model %s wrote a tool call as text; asking again", model)
            if fallback_model and fallback_model != model:
                model, prompt = fallback_model, _without_reasoning(prompt)
            result, streamed = await _call_llm(llm, prompt, round_tools, model=model, sink=on_event, effort=effort)
            tool_calls = list(getattr(result, "tool_calls", None) or [])
            if not tool_calls and _is_tool_markup(getattr(result, "content", None)):
                result.content = ""
        if not tool_calls:
            text = (getattr(result, "content", None) or "").strip()
            if not text and not retry_empty:
                text = EMPTY_ANSWER
            elif not text:
                text, streamed = await _answer_when_empty(llm, prompt, model=model, sink=on_event, question=user_text, effort=effort)
            if verify_numbers and facts:
                text, streamed = await _enforce_numbers(
                    text, streamed, facts=facts, question=user_text, llm=llm, prompt=prompt,
                    model=model, sink=on_event, effort=effort,
                )
            if not streamed:
                await _emit(on_event, {"type": "content", "delta": text})
            messages.append({"role": "assistant", "content": text})
            copilot["messages"] = _without_reasoning(_trim(_settle(messages, turn_start)))
            artifacts["copilot"] = copilot
            return CopilotTurnResult(
                kind="text", text=text, state="idle", artifacts=artifacts,
                evidence=evidence, coverages=coverages, envelopes=envelopes,
            )

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
            call_id = tc.get("id") or ""
            await _emit(on_event, {"type": "tool_start", "call_id": call_id, "tool": name})
            report(name, args, "running")
            payload = await execute(name, args, ctx)
            await _emit(on_event, {"type": "tool_result", "call_id": call_id, "tool": name, **_tool_summary(name, payload)})
            report(name, args, "error" if isinstance(payload, dict) and bool(payload.get("error")) and payload.get("ok") is not True else "done")
            if isinstance(payload, dict) and payload.get("ok") is False:
                failed_lookups += 1
                if failed_lookups >= ESCALATE_AFTER_FAILURES and effort != "high":  # the question is harder than it looked
                    logger.info("Ask turn escalated to high effort after %d failed lookups", failed_lookups)
                    effort = "high"
            if isinstance(payload, dict):
                evidence.extend(item for item in (payload.get("evidence") or []) if isinstance(item, dict))
                if payload.get("coverage"):
                    coverages.append(payload["coverage"])
                    envelopes.append({k: payload.get(k) for k in ("coverage", "n", "n_analysed", "unit", "period_days", "period_defaulted")})
                facts.append(json.dumps(payload, default=str, ensure_ascii=False))
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
            copilot["messages"] = _without_reasoning(_trim(messages))
            artifacts["copilot"] = copilot
            if kind == "choices":
                choices = list(args.get("choices") or [])
                copilot["choices"] = choices
                prompt = str(args.get("prompt") or "Which one?")
                await _emit(on_event, {"type": "content", "delta": prompt})
                return CopilotTurnResult(
                    kind="choices",
                    text=prompt,
                    state="waiting_retarget",
                    artifacts=artifacts,
                    list_sections=_choice_sections(choices),
                    evidence=evidence,
                    coverages=coverages,
                )
            copilot["pending_tool"] = name
            copilot["pending_args"] = args
            copilot["pending_id"] = tc.get("id")
            confirm_text = _confirm_text(name, args, copilot)
            await _emit(on_event, {"type": "content", "delta": confirm_text})
            return CopilotTurnResult(
                kind="confirm",
                text=confirm_text,
                state="waiting_approval",
                artifacts=artifacts,
                evidence=evidence,
                coverages=coverages,
                pending={"tool": name, "args": args, "call_id": tc.get("id")},
            )

    artifacts["copilot"] = copilot
    return CopilotTurnResult(
        kind="text",
        text=ROUND_LIMIT,
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
        if contact.get("name"):
            copilot["last_contact_name"] = contact["name"]
        if contact.get("url"):
            copilot["last_contact_url"] = contact["url"]
    contacts = payload.get("contacts")
    if isinstance(contacts, list) and len(contacts) == 1 and isinstance(contacts[0], dict):
        hit = contacts[0]
        if hit.get("id"):
            copilot["last_contact_id"] = hit["id"]
            if hit.get("name"):
                copilot["last_contact_name"] = hit["name"]
        if hit.get("url"):
            copilot["last_contact_url"] = hit["url"]
    if any(copilot.get(k) for k in ("last_contact_id", "last_deal_id")):
        copilot["focus_at"] = datetime.now(timezone.utc).isoformat()
