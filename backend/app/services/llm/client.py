"""
LLM client for chat completions.
Single entry point for OpenRouter and future providers.
"""

import json
import logging
import re
from typing import Optional

import httpx

from app.config import settings

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
        payload = {
            "model": model or self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if response_format:
            payload["response_format"] = response_format

        last_error: Optional[Exception] = None
        use_response_format = response_format
        for attempt in range(MAX_RETRIES + 1):
            try:
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
                if attempt < MAX_RETRIES:
                    logger.warning("LLM request failed (attempt %d/%d): %s", attempt + 1, MAX_RETRIES + 1, e)
        raise Exception(f"LLM request failed: {last_error}") from last_error

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
        return self._extract_json(content)
