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

    @property
    def last_call_meta(self) -> dict:
        return self.router.last_call_meta

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
        reasoning_effort: Optional[str] = None,
    ) -> dict:
        return await self.router.chat_json(
            messages,
            model=model or self._override_model,
            temperature=temperature,
            provider=provider,
            timeout=timeout,
            max_retries=max_retries,
            reasoning_effort=reasoning_effort,
        )

    async def chat_tools(
        self,
        messages: list[dict],
        *,
        tools: list,
        model: Optional[str] = None,
        temperature: float = 0.0,
        provider: Optional[str] = None,
        timeout: Optional[float] = None,
        max_retries: Optional[int] = None,
        extra: Optional[dict] = None,
    ):
        return await self.router.chat_tools(
            messages,
            tools=tools,
            model=model or self._override_model,
            temperature=temperature,
            provider=provider,
            timeout=timeout,
            max_retries=max_retries,
            extra=extra,
        )

    async def chat_tools_stream(
        self,
        messages: list[dict],
        *,
        tools: list,
        model: Optional[str] = None,
        temperature: float = 0.0,
        provider: Optional[str] = None,
        timeout: Optional[float] = None,
        extra: Optional[dict] = None,
    ):
        async for item in self.router.chat_tools_stream(
            messages,
            tools=tools,
            model=model or self._override_model,
            temperature=temperature,
            provider=provider,
            timeout=timeout,
            extra=extra,
        ):
            yield item
