"""Stream objection coaching suggestions via OpenRouter."""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator, Optional

import httpx

from app.config import settings
from app.services.copilot.prompts import SYSTEM_PROMPT, build_user_prompt
from app.services.llm.shared import extract_json

logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def _resolve_model(explicit: Optional[str] = None) -> str:
    return (
        (explicit or "").strip()
        or (settings.COPILOT_MODEL or "").strip()
        or "google/gemini-2.5-flash-lite"
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
) -> AsyncIterator[dict[str, Any]]:
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
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": build_user_prompt(
                transcript_window=transcript_window,
                latest_turn=latest_turn,
                product_context=product_context,
                language=language,
                call_mode=call_mode,
                speaker_role=speaker_role,
            ),
        },
    ]

    payload = {
        "model": model_used,
        "messages": messages,
        "temperature": 0.35,
        "stream": True,
        "response_format": {"type": "json_object"},
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

        suggestion = _parse_suggestion(assembled)
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        yield {
            "type": "result",
            "suggestion": suggestion,
            "model": model_used,
            "latency_ms": elapsed_ms,
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
) -> AsyncIterator[dict[str, Any]]:
    import time

    payload = {
        "model": model_used,
        "messages": messages,
        "temperature": 0.35,
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
    suggestion = _parse_suggestion(content)
    yield {
        "type": "result",
        "suggestion": suggestion,
        "model": model_used,
        "latency_ms": int((time.perf_counter() - t0) * 1000),
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
    }
