"""LLM provider router — config-driven backend selection."""

from typing import Optional

from app.config import settings
from app.services.llm.base import BaseLLMProvider
from app.services.llm.providers.openrouter import OpenRouterProvider

_VERTEX_PROVIDER: Optional[BaseLLMProvider] = None

_NOT_IMPLEMENTED = frozenset({"nextbit", "bedrock"})


def _resolve_provider(
    name: str,
    *,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> BaseLLMProvider:
    if name in _NOT_IMPLEMENTED:
        raise ValueError(
            f"LLM provider '{name}' is not implemented in v1. "
            f"Use 'openrouter' or 'vertex_ai'."
        )

    if name == "openrouter":
        # Custom credentials/model need a dedicated instance (not shared cache).
        if api_key is not None or model is not None:
            return OpenRouterProvider(api_key=api_key, model=model)
        return OpenRouterProvider()

    if name == "vertex_ai":
        global _VERTEX_PROVIDER
        if _VERTEX_PROVIDER is None:
            from app.services.llm.providers.vertex_ai import VertexAIProvider

            _VERTEX_PROVIDER = VertexAIProvider()
        return _VERTEX_PROVIDER

    raise ValueError(f"Unknown LLM provider: {name}")


class LLMRouter:
    """Single entry point for LLM requests; delegates to configured provider."""

    def __init__(
        self,
        provider_name: Optional[str] = None,
        *,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        self._provider_name = provider_name or settings.LLM_PROVIDER
        self._api_key = api_key
        self._default_model = model
        self._provider = _resolve_provider(
            self._provider_name,
            api_key=api_key,
            model=model,
        )

    @property
    def provider_name(self) -> str:
        return self._provider_name

    def get_active_compliance_info(self) -> dict:
        """Compliance profile of the active provider for vendor assessment."""
        return self._provider.compliance_info()

    def _active_provider(self, provider: Optional[str]) -> BaseLLMProvider:
        if provider is None:
            return self._provider
        return _resolve_provider(
            provider,
            api_key=self._api_key if provider == "openrouter" else None,
            model=self._default_model if provider == "openrouter" else None,
        )

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
        active = self._active_provider(provider)
        return await active.chat(
            messages,
            model=model or self._default_model,
            temperature=temperature,
            response_format=response_format,
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
        active = self._active_provider(provider)
        return await active.chat_json(
            messages,
            model=model or self._default_model,
            temperature=temperature,
            timeout=timeout,
            max_retries=max_retries,
        )
