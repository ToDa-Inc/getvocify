"""Stream objection coaching suggestions via OpenRouter."""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator, Optional

import httpx

from app.config import settings
from app.services.copilot.context import SuggestContext
from app.services.copilot.grounding import SuggestGrounding, finalize_suggest_result
from app.services.copilot.prompts import MEETING_LINE_MAX, build_user_prompt, system_prompt_for
from app.services.llm.shared import extract_json

logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
# Live help can't wait for long hidden reasoning, but some models (gemini-3.5-flash-lite) refuse
# to switch it off and fail every request with "Reasoning is mandatory". Ask for the least instead;
# models that don't reason ignore it.
LIVE_REASONING = {"reasoning": {"effort": "minimal"}}


def _resolve_model(explicit: Optional[str] = None) -> str:
    return (
        (explicit or "").strip()
        or (settings.COPILOT_MODEL or "").strip()
        or "deepseek/deepseek-v4.1-flash"
    )


def _empty_suggestion(message: str = "") -> dict[str, Any]:
    return {
        "is_objection": False,
        "objection_type": "none",
        "urgency": "low",
        "say_this": message or "Stay with them — ask one clarifying question about their current process.",
        "why_it_works": "Keeps momentum without forcing an objection frame.",
        "next_question": "What does your process look like today when this comes up?",
        "dont_say": "Don't pitch harder if they haven't objected yet.",
    }


async def stream_objection_suggestion(
    *,
    transcript_window: str,
    latest_turn: str,
    product_context: Optional[str] = None,
    language: str = "auto",
    call_mode: str = "speakerphone",
    speaker_role: str = "unknown",
    model: Optional[str] = None,
    grounding: Optional[SuggestGrounding] = None,
    context: Optional[SuggestContext] = None,
    company_knowledge: Optional[dict[str, Any]] = None,
    contact_history: Optional[str] = None,
) -> AsyncIterator[dict[str, Any]]:
    del context  # threaded for grounding/session wiring; prompts unchanged without CRM load
    """
    Yields dict events:
      {"type": "token", "text": "..."}
      {"type": "result", "suggestion": {...}, "model": "...", "latency_ms": int}
      {"type": "error", "message": "..."}
    """
    api_key = settings.OPENROUTER_API_KEY
    if not api_key or not str(api_key).strip():
        yield {"type": "error", "message": "OPENROUTER_API_KEY is not set"}
        return

    model_used = _resolve_model(model)
    messages = [
        {"role": "system", "content": system_prompt_for(call_mode)},
        {
            "role": "user",
            "content": build_user_prompt(
                transcript_window=transcript_window,
                latest_turn=latest_turn,
                product_context=product_context,
                language=language,
                call_mode=call_mode,
                speaker_role=speaker_role,
                playbook_snapshot=grounding.playbook_snapshot if grounding else None,
                company_knowledge=company_knowledge,
                contact_history=contact_history,
            ),
        },
    ]

    payload = {
        "model": model_used,
        "messages": messages,
        "temperature": 0.35,
        "stream": True,
        "response_format": {"type": "json_object"},
        **LIVE_REASONING,
    }

    import time

    t0 = time.perf_counter()
    assembled = ""

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(45.0, connect=10.0)) as client:
            async with client.stream(
                "POST",
                OPENROUTER_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": settings.FRONTEND_URL,
                    "X-Title": "Vocify Call Copilot",
                },
                json=payload,
            ) as resp:
                if resp.status_code == 400:
                    # Some models reject response_format — retry without stream framing once
                    body = await resp.aread()
                    logger.warning("Copilot stream 400, falling back non-stream: %s", body[:300])
                    async for event in _fallback_non_stream(
                        client=client,
                        api_key=api_key,
                        model_used=model_used,
                        messages=messages,
                        t0=t0,
                        call_mode=call_mode,
                        grounding=grounding,
                        latest_turn=latest_turn,
                    ):
                        yield event
                    return

                if resp.status_code >= 400:
                    body = await resp.aread()
                    yield {
                        "type": "error",
                        "message": f"OpenRouter {resp.status_code}: {body[:240].decode(errors='ignore')}",
                    }
                    return

                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    if line.startswith(":"):
                        continue
                    if not line.startswith("data: "):
                        continue
                    data = line[6:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    delta = (choices[0].get("delta") or {}).get("content")
                    if delta:
                        assembled += delta
                        yield {"type": "token", "text": delta}

        suggestion = _suggestion_for_mode(assembled, call_mode)
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        finalized = finalize_suggest_result(
            call_mode=call_mode,
            suggestion=suggestion,
            grounding=grounding,
            latest_turn=latest_turn,
        )
        yield {
            "type": "result",
            "model": model_used,
            "latency_ms": elapsed_ms,
            **finalized,
        }
    except Exception as e:
        logger.exception("Copilot suggest failed")
        yield {"type": "error", "message": str(e) or type(e).__name__}


async def _fallback_non_stream(
    *,
    client: httpx.AsyncClient,
    api_key: str,
    model_used: str,
    messages: list[dict],
    t0: float,
    call_mode: str,
    grounding: Optional[SuggestGrounding] = None,
    latest_turn: str = "",
) -> AsyncIterator[dict[str, Any]]:
    import time

    payload = {
        "model": model_used,
        "messages": messages,
        "temperature": 0.35,
        **LIVE_REASONING,
    }
    resp = await client.post(
        OPENROUTER_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": settings.FRONTEND_URL,
            "X-Title": "Vocify Call Copilot",
        },
        json=payload,
    )
    if resp.status_code >= 400:
        yield {"type": "error", "message": f"OpenRouter {resp.status_code}: {resp.text[:240]}"}
        return
    data = resp.json()
    content = data["choices"][0]["message"]["content"] or ""
    if content:
        yield {"type": "token", "text": content}
    suggestion = _suggestion_for_mode(content, call_mode)
    finalized = finalize_suggest_result(
        call_mode=call_mode,
        suggestion=suggestion,
        grounding=grounding,
        latest_turn=latest_turn,
    )
    yield {
        "type": "result",
        "model": model_used,
        "latency_ms": int((time.perf_counter() - t0) * 1000),
        **finalized,
    }


def _parse_suggestion(raw: str) -> dict[str, Any]:
    if not raw or not raw.strip():
        return _empty_suggestion()
    try:
        parsed = extract_json(raw)
    except ValueError:
        return _empty_suggestion(raw.strip()[:280])

    return {
        "is_objection": bool(parsed.get("is_objection", False)),
        "objection_type": str(parsed.get("objection_type") or "none"),
        "urgency": str(parsed.get("urgency") or "low"),
        "say_this": str(parsed.get("say_this") or "").strip()
        or _empty_suggestion()["say_this"],
        "why_it_works": str(parsed.get("why_it_works") or "").strip(),
        "next_question": str(parsed.get("next_question") or "").strip(),
        "dont_say": str(parsed.get("dont_say") or "").strip(),
        "evidence_refs": _parse_evidence_refs(parsed.get("evidence_refs")),
        "source_id": str(parsed.get("source_id") or "").strip() or None,
    }


# The model is asked for MEETING_LINE_MAX characters; a line tied to the call runs a little
# longer, and silencing it withdrew a card the rep was already reading. Only rambling is dropped.
MEETING_LINE_SHOW_MAX = 160

MEETING_OBJECTION_TYPES = {"price", "timing", "authority", "competitor", "status_quo", "trust", "question", "other"}


def silent_suggestion() -> dict[str, Any]:
    """No help: what live help answers when there is nothing worth saying."""
    return {
        "is_objection": False,
        "objection_type": "none",
        "urgency": "low",
        "say_this": "",
        "why_it_works": "",
        "next_question": "",
        "dont_say": "",
        "evidence_refs": [],
        "source_id": None,
    }


def meeting_suggestion(raw: str) -> dict[str, Any]:
    """Meetings show help only for a clear objection with one short line; anything else stays silent."""
    try:
        parsed = extract_json(raw) if raw and raw.strip() else None
    except ValueError:
        parsed = None
    if not isinstance(parsed, dict) or parsed.get("is_objection") is not True:
        return silent_suggestion()
    objection_type = str(parsed.get("objection_type") or "").strip()
    say_this = " ".join(str(parsed.get("say_this") or "").split())
    if objection_type not in MEETING_OBJECTION_TYPES or not say_this or len(say_this) > MEETING_LINE_SHOW_MAX:
        return silent_suggestion()
    next_question = " ".join(str(parsed.get("next_question") or "").split())
    return {
        "is_objection": True,
        "objection_type": objection_type,
        "urgency": str(parsed.get("urgency") or "low"),
        "say_this": say_this,
        "why_it_works": str(parsed.get("why_it_works") or "").strip(),
        "next_question": next_question if len(next_question) <= MEETING_LINE_SHOW_MAX else "",
        "dont_say": str(parsed.get("dont_say") or "").strip(),
        # Read by finalize_suggest_result: a playbook answer needs both.
        "evidence_refs": _parse_evidence_refs(parsed.get("evidence_refs")),
        "source_id": str(parsed.get("source_id") or "").strip() or None,
    }


def _suggestion_for_mode(raw: str, call_mode: str) -> dict[str, Any]:
    return meeting_suggestion(raw) if call_mode == "meeting" else _parse_suggestion(raw)


def _parse_evidence_refs(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    refs: list[str] = []
    for item in raw:
        text = str(item or "").strip()
        if text:
            refs.append(text)
    return refs
