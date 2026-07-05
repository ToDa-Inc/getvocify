"""
LLM client for chat completions.
Backward-compatible wrapper around LLMRouter.
"""

from typing import Optional

from app.services.llm.router import LLMRouter


class LLMClient:
    """
    Low-level LLM client for chat completions.
    Used by ExtractionService, WhatsApp message generation, validation, etc.
    Routes to the configured provider via LLMRouter.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        self.router = LLMRouter(api_key=api_key, model=model)
        self._override_model = model

    async def chat(
        self,
        messages: list[dict],
        *,
        model: Optional[str] = None,
        temperature: float = 0.0,
        response_format: Optional[dict] = None,
        provider: Optional[str] = None,
        timeout: Optional[float] = None,
        max_retries: Optional[int] = None,
    ) -> str:
        return await self.router.chat(
            messages,
            model=model or self._override_model,
            temperature=temperature,
            response_format=response_format,
            provider=provider,
            timeout=timeout,
            max_retries=max_retries,
        )

    async def chat_json(
        self,
        messages: list[dict],
        *,
        model: Optional[str] = None,
        temperature: float = 0.0,
        provider: Optional[str] = None,
        timeout: Optional[float] = None,
        max_retries: Optional[int] = None,
    ) -> dict:
        return await self.router.chat_json(
            messages,
            model=model or self._override_model,
            temperature=temperature,
            provider=provider,
            timeout=timeout,
            max_retries=max_retries,
        )
