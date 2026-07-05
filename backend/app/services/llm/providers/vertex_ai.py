"""Google Vertex AI (Gemini) LLM provider via google-genai SDK."""

import asyncio
import logging
import time
from typing import Optional

from google import genai
from google.genai import types

from app.config import settings
from app.logging_config import DOMAIN_LLM, log_domain
from app.metrics import inc_llm_request, inc_pipeline_error
from app.services.llm.base import BaseLLMProvider
from app.services.llm.compliance import get_compliance_info
from app.services.llm.shared import (
    extract_json,
    log_json_failed,
    log_json_parsed,
    to_gemini_contents,
)

logger = logging.getLogger(__name__)

PROVIDER_NAME = "vertex_ai"
MAX_RETRIES = 2
DEFAULT_TIMEOUT = 45.0


class VertexAIProvider(BaseLLMProvider):
    """Vertex AI Gemini models (europe-southwest1 / Madrid by default)."""

    def __init__(self, model: Optional[str] = None) -> None:
        project = settings.GOOGLE_CLOUD_PROJECT
        location = settings.GOOGLE_CLOUD_LOCATION
        if not project or not str(project).strip():
            raise ValueError(
                "GOOGLE_CLOUD_PROJECT is required when LLM_PROVIDER=vertex_ai"
            )
        self._client = genai.Client(
            vertexai=True,
            project=project,
            location=location,
        )
        self._model_name = model or settings.VERTEX_AI_MODEL

    @property
    def provider_name(self) -> str:
        return PROVIDER_NAME

    def compliance_info(self) -> dict:
        return get_compliance_info(PROVIDER_NAME)

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
        model_used = model or self._model_name
        json_mode = bool(
            response_format and response_format.get("type") == "json_object"
        )
        system_instruction, contents = to_gemini_contents(messages)

        config_kwargs: dict = {"temperature": temperature}
        if system_instruction:
            config_kwargs["system_instruction"] = system_instruction
        if json_mode:
            config_kwargs["response_mime_type"] = "application/json"

        config = types.GenerateContentConfig(**config_kwargs)

        last_error: Optional[Exception] = None
        retries = MAX_RETRIES if max_retries is None else max_retries
        request_timeout = timeout if timeout is not None else DEFAULT_TIMEOUT
        for attempt in range(retries + 1):
            try:
                input_chars = sum(len(str(m.get("content", ""))) for m in messages)
                logger.info(
                    "LLM chat attempt",
                    extra=log_domain(
                        DOMAIN_LLM,
                        "chat_attempt",
                        provider=PROVIDER_NAME,
                        model=model_used,
                        attempt=attempt + 1,
                        max_attempts=retries + 1,
                        input_chars=input_chars,
                        message_count=len(messages),
                    ),
                )
                t0 = time.perf_counter()
                coro = self._client.aio.models.generate_content(
                    model=model_used,
                    contents=contents,
                    config=config,
                )
                response = await asyncio.wait_for(coro, timeout=request_timeout)
                content = response.text
                if content is None or not str(content).strip():
                    raise ValueError("Empty model response")
                elapsed_ms = (time.perf_counter() - t0) * 1000
                inc_llm_request("success", PROVIDER_NAME, model_used)
                logger.info(
                    "LLM chat success",
                    extra=log_domain(
                        DOMAIN_LLM,
                        "chat_success",
                        provider=PROVIDER_NAME,
                        model=model_used,
                        duration_ms=round(elapsed_ms, 2),
                        content_len=len(content),
                    ),
                )
                return content
            except Exception as e:
                last_error = e
                logger.error(
                    "Vertex AI error (model=%s): %s",
                    model_used,
                    e,
                )
                if attempt >= retries:
                    inc_llm_request("failure", PROVIDER_NAME, model_used)
                    inc_pipeline_error(DOMAIN_LLM, "chat")
                if attempt < retries:
                    logger.warning(
                        "LLM request failed (attempt %d/%d): %s",
                        attempt + 1,
                        retries + 1,
                        e,
                    )

        err_msg = str(last_error) if last_error else "Unknown error"
        raise Exception(f"LLM request failed: {err_msg}") from last_error

    async def chat_json(
        self,
        messages: list[dict],
        *,
        model: Optional[str] = None,
        temperature: float = 0.0,
        timeout: Optional[float] = None,
        max_retries: Optional[int] = None,
    ) -> dict:
        content = await self.chat(
            messages,
            model=model,
            temperature=temperature,
            response_format={"type": "json_object"},
            timeout=timeout,
            max_retries=max_retries,
        )
        try:
            parsed = extract_json(content)
            log_json_parsed(parsed)
            return parsed
        except ValueError as e:
            log_json_failed(str(e), content)
            raise
