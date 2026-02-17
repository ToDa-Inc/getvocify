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
        for attempt in range(MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                    resp = await client.post(
                        OPENROUTER_URL,
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json",
                            "HTTP-Referer": settings.FRONTEND_URL,
                            "X-Title": "Vocify",
                        },
                        json=payload,
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    content = data["choices"][0]["message"]["content"]
                    if content is None:
                        raise ValueError("Empty model response")
                    return content
            except (httpx.HTTPStatusError, httpx.RequestError, KeyError) as e:
                last_error = e
                if attempt < MAX_RETRIES:
                    logger.warning("LLM request failed (attempt %d/%d): %s", attempt + 1, MAX_RETRIES + 1, e)
        raise Exception(f"LLM request failed: {last_error}") from last_error

    async def chat_json(
        self,
        messages: list[dict],
        *,
        model: Optional[str] = None,
        temperature: float = 0.0,
    ) -> dict:
        """
        Chat with JSON response. Parses content and returns dict.
        Falls back to extracting JSON from markdown blocks if needed.
        """
        content = await self.chat(
            messages,
            model=model,
            temperature=temperature,
            response_format={"type": "json_object"},
        )
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
            if match:
                return json.loads(match.group(1))
            raise ValueError("Failed to parse JSON from LLM response") from None
