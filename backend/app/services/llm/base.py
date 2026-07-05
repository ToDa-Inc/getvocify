"""Abstract LLM provider interface."""

from abc import ABC, abstractmethod
from typing import Optional


class LLMProviderError(Exception):
    """Structured LLM provider error (normalized across backends)."""

    def __init__(
        self,
        provider: str,
        message: str,
        *,
        status_code: Optional[int] = None,
    ) -> None:
        self.provider = provider
        self.status_code = status_code
        super().__init__(message)


class BaseLLMProvider(ABC):
    """Every LLM backend must implement this contract."""

    @abstractmethod
    async def chat(
        self,
        messages: list[dict],
        *,
        model: Optional[str] = None,
        temperature: float = 0.0,
        response_format: Optional[dict] = None,
        timeout: Optional[float] = None,
        max_retries: Optional[int] = None,
    ) -> str:
        """Send chat completion, return raw string content."""
        ...

    @abstractmethod
    async def chat_json(
        self,
        messages: list[dict],
        *,
        model: Optional[str] = None,
        temperature: float = 0.0,
        timeout: Optional[float] = None,
        max_retries: Optional[int] = None,
    ) -> dict:
        """Chat with JSON response, parse and return dict."""
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable name for logging/metrics: 'openrouter', 'vertex_ai', etc."""
        ...

    @abstractmethod
    def compliance_info(self) -> dict:
        """Compliance profile for vendor assessment."""
        ...
