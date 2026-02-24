"""
LLM client for chat completions.
Single entry point for OpenRouter and future providers.
"""

import json
import logging
import re
import time
from typing import Optional

import httpx

from app.config import settings
from app.logging_config import log_domain, DOMAIN_LLM
from app.metrics import inc_llm_request, inc_pipeline_error

logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_TIMEOUT = 45.0
MAX_RETRIES = 2


class LLMClient:
    """
    Low-level LLM client for chat completions.
    Used by ExtractionService, WhatsApp message generation, validation, etc.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        self.api_key = api_key or settings.OPENROUTER_API_KEY
        self.model = model or settings.EXTRACTION_MODEL

    async def chat(
        self,
        messages: list[dict],
        *,
        model: Optional[str] = None,
        temperature: float = 0.0,
        response_format: Optional[dict] = None,
    ) -> str:
        """
        Send chat completion request. Returns raw content string.

        Args:
            messages: [{"role": "system/user/assistant", "content": "..."}]
            model: Override default model
            temperature: 0 for deterministic, higher for creative
            response_format: e.g. {"type": "json_object"} for structured output
        """
        api_key = self.api_key
        if not api_key or not str(api_key).strip():
            raise Exception(
                "LLM request failed: OPENROUTER_API_KEY is not set. "
                "Add it to .env (get a key at openrouter.ai/keys)"
            )

        payload = {
            "model": model or self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if response_format:
            payload["response_format"] = response_format

        last_error: Optional[Exception] = None
        use_response_format = response_format
        model_used = model or self.model
        for attempt in range(MAX_RETRIES + 1):
            try:
                input_chars = sum(len(str(m.get("content", ""))) for m in messages)
                logger.info(
                    "🤖 LLM chat attempt",
                    extra=log_domain(DOMAIN_LLM, "chat_attempt", model=model_used, attempt=attempt + 1, max_attempts=MAX_RETRIES + 1, input_chars=input_chars, message_count=len(messages)),
                )
                full_text = " ".join(str(m.get("content", "")) for m in messages)
                request_preview = full_text[:600] + "..." if len(full_text) > 600 else full_text
                logger.info(
                    "📤 LLM request",
                    extra=log_domain(
                        DOMAIN_LLM,
                        "request_preview",
                        model=model_used,
                        request_preview=request_preview,
                    ),
                )
                t0 = time.perf_counter()
                req_payload = {k: v for k, v in payload.items() if k != "response_format"}
                if use_response_format:
                    req_payload["response_format"] = use_response_format
                async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                    resp = await client.post(
                        OPENROUTER_URL,
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json",
                            "HTTP-Referer": settings.FRONTEND_URL,
                            "X-Title": "Vocify",
                        },
                        json=req_payload,
                    )
                    if resp.status_code == 400 and use_response_format and attempt < MAX_RETRIES:
                        logger.warning("LLM 400 (model may not support response_format), retrying without it")
                        use_response_format = None
                        continue
                    resp.raise_for_status()
                    data = resp.json()
                    content = data["choices"][0]["message"]["content"]
                    if content is None:
                        raise ValueError("Empty model response")
                    elapsed_ms = (time.perf_counter() - t0) * 1000
                    usage = data.get("usage", {})
                    inc_llm_request("success", model_used)
                    logger.info(
                        "✅ LLM chat success",
                        extra=log_domain(
                            DOMAIN_LLM,
                            "chat_success",
                            model=model_used,
                            duration_ms=round(elapsed_ms, 2),
                            prompt_tokens=usage.get("prompt_tokens"),
                            output_tokens=usage.get("total_tokens"),
                            content_len=len(content) if content else 0,
                        ),
                    )
                    if logger.isEnabledFor(logging.DEBUG) and content:
                        logger.debug(
                            "LLM response preview",
                            extra=log_domain(DOMAIN_LLM, "content_preview", content_preview=content[:100] if content else ""),
                        )
                    return content
            except (httpx.HTTPStatusError, httpx.RequestError, KeyError) as e:
                last_error = e
                if isinstance(e, httpx.HTTPStatusError) and e.response is not None:
                    try:
                        body = e.response.json()
                        err_detail = body.get("error", {}).get("message", body.get("message", str(body)))
                        logger.error(
                            "OpenRouter %s: %s (model=%s)",
                            e.response.status_code,
                            err_detail,
                            model or self.model,
                        )
                    except Exception:
                        logger.error("OpenRouter %s: %s", e.response.status_code, e.response.text[:200] if e.response.text else str(e))
                    if e.response.status_code == 401:
                        logger.error(
                            "401 = Invalid/disabled key or OAuth expired. "
                            "Try: 1) Create new key at openrouter.ai/keys 2) Remove quotes/whitespace from .env"
                        )
                if attempt >= MAX_RETRIES:
                    inc_llm_request("failure", model_used or self.model)
                    inc_pipeline_error(DOMAIN_LLM, "chat")
                if attempt < MAX_RETRIES:
                    logger.warning("LLM request failed (attempt %d/%d): %s", attempt + 1, MAX_RETRIES + 1, e)

        err_msg = str(last_error) if last_error else "Unknown error"
        if not err_msg.strip():
            err_msg = type(last_error).__name__ if last_error else "Unknown"
        if isinstance(last_error, httpx.HTTPStatusError) and last_error.response is not None:
            try:
                body = last_error.response.json()
                api_err = body.get("error", {}).get("message") or body.get("message")
                if api_err:
                    err_msg = f"{last_error.response.status_code} {api_err}"
            except Exception:
                if last_error.response.text:
                    err_msg = f"{last_error.response.status_code} {last_error.response.text[:200]}"
        elif isinstance(last_error, httpx.RequestError):
            err_msg = err_msg or f"{type(last_error).__name__} (network/timeout?)"
        raise Exception(f"LLM request failed: {err_msg}") from last_error

    def _extract_json(self, content: str) -> dict:
        """
        Extract JSON from LLM response. Handles markdown blocks, preamble text, etc.
        """
        content = content.strip()
        # 1. Direct parse
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # 2. Markdown code block: ```json ... ``` or ``` ... ```
        # Use greedy match so nested braces are captured correctly
        match = re.search(r"```(?:json)?\s*(\{[\s\S]*\})\s*```", content, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        # 3. Find first { and last } - many models wrap JSON in text
        start = content.find("{")
        end = content.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidate = content[start : end + 1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                # Try fixing common LLM quirks: trailing commas, single quotes
                fixed = re.sub(r",\s*}", "}", candidate)
                fixed = re.sub(r",\s*]", "]", fixed)
                try:
                    return json.loads(fixed)
                except json.JSONDecodeError:
                    pass

        raise ValueError("Failed to parse JSON from LLM response")

    async def chat_json(
        self,
        messages: list[dict],
        *,
        model: Optional[str] = None,
        temperature: float = 0.0,
    ) -> dict:
        """
        Chat with JSON response. Parses content and returns dict.
        Falls back to extracting JSON from markdown blocks or text-wrapped JSON.
        """
        content = await self.chat(
            messages,
            model=model,
            temperature=temperature,
            response_format={"type": "json_object"},
        )
        try:
            parsed = self._extract_json(content)
            logger.debug(
                "LLM JSON parsed",
                extra=log_domain(DOMAIN_LLM, "json_parsed", keys=list(parsed.keys()) if isinstance(parsed, dict) else []),
            )
            return parsed
        except ValueError as e:
            logger.warning(
                "LLM JSON extraction failed",
                extra=log_domain(DOMAIN_LLM, "json_failed", error=str(e), content_preview=content[:200] if content else ""),
            )
            raise
