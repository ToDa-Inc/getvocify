"""OpenRouter LLM provider."""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

import httpx

from app.config import settings
from app.logging_config import DOMAIN_LLM, log_domain
from app.metrics import inc_llm_request, inc_pipeline_error
from app.services.llm.base import BaseLLMProvider
from app.services.llm.compliance import get_compliance_info
from app.services.llm.stream import ToolStreamAccumulator
from app.services.llm.shared import (
    extract_json,
    log_json_failed,
    log_json_parsed,
)

logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_TIMEOUT = 45.0
MAX_RETRIES = 2
PROVIDER_NAME = "openrouter"
# Streaming turns retry only before the first byte: rate limits and upstream hiccups, never a 4xx of ours.
STREAM_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
STREAM_RETRY_DELAYS = (0.6, 1.8)


@dataclass
class ChatToolsResult:
    content: Optional[str]
    tool_calls: list = field(default_factory=list)
    raw_message: dict = field(default_factory=dict)


def parse_tool_calls(message: dict) -> list[dict]:
    out: list[dict] = []
    for tc in message.get("tool_calls") or []:
        fn = tc.get("function") or {}
        args = fn.get("arguments") or {}
        if isinstance(args, str):
            try:
                args = json.loads(args) if args.strip() else {}
            except json.JSONDecodeError:
                args = {"_raw": args}
        if not isinstance(args, dict):
            args = {"value": args}
        out.append({"id": str(tc.get("id") or ""), "name": str(fn.get("name") or ""), "arguments": args})
    return out


def openrouter_call_meta(data: dict, *, requested_model: str) -> dict:
    """What actually served the call — OpenRouter may echo a routed model id."""
    usage = data.get("usage") if isinstance(data, dict) else None
    if not isinstance(usage, dict):
        usage = {}
    model = None
    if isinstance(data, dict):
        model = data.get("model")
    return {
        "model": model or requested_model,
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
    }


class EmptyModelResponse(ValueError):
    def __init__(self) -> None:
        super().__init__("Empty model response")


class OpenRouterProvider(BaseLLMProvider):
    """OpenRouter chat completions API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        self.api_key = api_key or settings.OPENROUTER_API_KEY
        self.model = model or settings.EXTRACTION_MODEL
        self.last_call_meta: dict = {}

    @property
    def provider_name(self) -> str:
        return PROVIDER_NAME

    def compliance_info(self) -> dict:
        return get_compliance_info(PROVIDER_NAME)

    async def _complete(
        self,
        messages: list[dict],
        *,
        model: Optional[str] = None,
        temperature: float = 0.0,
        response_format: Optional[dict] = None,
        timeout: Optional[float] = None,
        max_retries: Optional[int] = None,
        tools: Optional[list] = None,
        extra: Optional[dict] = None,
        allow_empty_content: bool = False,
    ) -> dict:
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
            # Without a cap OpenRouter reserves the model's whole output window (65k on Gemini)
            # against the account balance, so a low balance fails calls that need a few k.
            "max_tokens": settings.LLM_MAX_OUTPUT_TOKENS,
        }
        if response_format:
            payload["response_format"] = response_format
        if tools:
            payload["tools"] = tools
        if extra:
            payload.update(extra)

        last_error: Optional[Exception] = None
        use_response_format = response_format
        model_used = model or self.model
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
                full_text = " ".join(str(m.get("content", "")) for m in messages)
                request_preview = full_text[:600] + "..." if len(full_text) > 600 else full_text
                logger.info(
                    "LLM request",
                    extra=log_domain(
                        DOMAIN_LLM,
                        "request_preview",
                        provider=PROVIDER_NAME,
                        model=model_used,
                        request_preview=request_preview,
                    ),
                )
                t0 = time.perf_counter()
                req_payload = {k: v for k, v in payload.items() if k != "response_format"}
                if use_response_format:
                    req_payload["response_format"] = use_response_format
                async with httpx.AsyncClient(timeout=request_timeout) as client:
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
                    if resp.status_code == 400 and use_response_format and attempt < retries:
                        logger.warning(
                            "LLM 400 (model may not support response_format), retrying without it"
                        )
                        use_response_format = None
                        continue
                    resp.raise_for_status()
                    data = resp.json()
                    message = data["choices"][0]["message"]
                    content = message.get("content")
                    if content is None and not allow_empty_content:
                        raise EmptyModelResponse()
                    elapsed_ms = (time.perf_counter() - t0) * 1000
                    self.last_call_meta = openrouter_call_meta(data, requested_model=model_used)
                    usage = self.last_call_meta
                    inc_llm_request("success", PROVIDER_NAME, usage.get("model") or model_used)
                    logger.info(
                        "LLM chat success",
                        extra=log_domain(
                            DOMAIN_LLM,
                            "chat_success",
                            provider=PROVIDER_NAME,
                            model=usage.get("model") or model_used,
                            duration_ms=round(elapsed_ms, 2),
                            prompt_tokens=usage.get("prompt_tokens"),
                            output_tokens=usage.get("completion_tokens"),
                            content_len=len(content) if content else 0,
                        ),
                    )
                    return message
            except (httpx.HTTPStatusError, httpx.RequestError, KeyError, EmptyModelResponse) as e:
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
                        logger.error(
                            "OpenRouter %s: %s",
                            e.response.status_code,
                            e.response.text[:200] if e.response.text else str(e),
                        )
                    if e.response.status_code == 401:
                        logger.error(
                            "401 = Invalid/disabled key or OAuth expired. "
                            "Try: 1) Create new key at openrouter.ai/keys 2) Remove quotes/whitespace from .env"
                        )
                if attempt >= retries:
                    inc_llm_request("failure", PROVIDER_NAME, model_used or self.model)
                    inc_pipeline_error(DOMAIN_LLM, "chat")
                if attempt < retries:
                    logger.warning(
                        "LLM request failed (attempt %d/%d): %s",
                        attempt + 1,
                        retries + 1,
                        e,
                    )

        if isinstance(last_error, EmptyModelResponse):
            raise last_error
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
        message = await self._complete(
            messages,
            model=model,
            temperature=temperature,
            response_format=response_format,
            timeout=timeout,
            max_retries=max_retries,
        )
        content = message.get("content")
        if content is None:
            raise ValueError("Empty model response")
        return content

    async def chat_tools(
        self,
        messages: list[dict],
        *,
        tools: list,
        model: Optional[str] = None,
        temperature: float = 0.0,
        timeout: Optional[float] = None,
        max_retries: Optional[int] = None,
        extra: Optional[dict] = None,
    ) -> ChatToolsResult:
        message = await self._complete(
            messages,
            model=model,
            temperature=temperature,
            timeout=timeout,
            max_retries=max_retries,
            tools=tools,
            extra=extra,
            allow_empty_content=True,
        )
        return ChatToolsResult(
            content=message.get("content"),
            tool_calls=parse_tool_calls(message),
            raw_message=message,
        )

    async def chat_tools_stream(
        self,
        messages: list[dict],
        *,
        tools: list,
        model: Optional[str] = None,
        temperature: float = 0.0,
        timeout: Optional[float] = None,
        extra: Optional[dict] = None,
    ):
        """Yield ("delta", text) as text arrives, then ("final", ChatToolsResult).

        No retry once bytes flow: a half-streamed answer cannot be replayed. A failure before
        the first byte raises like `chat_tools`.
        """
        if not self.api_key or not str(self.api_key).strip():
            raise Exception("LLM request failed: OPENROUTER_API_KEY is not set.")
        model_used = model or self.model
        payload = {"model": model_used, "messages": messages, "temperature": temperature, "stream": True}
        if tools:
            payload["tools"] = tools
        if extra:
            payload.update(extra)
        acc = ToolStreamAccumulator()
        t0 = time.perf_counter()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": settings.FRONTEND_URL,
            "X-Title": "Vocify",
        }
        attempts = len(STREAM_RETRY_DELAYS) + 1
        for attempt in range(attempts):
            streaming = False
            try:
                async with httpx.AsyncClient(timeout=timeout if timeout is not None else DEFAULT_TIMEOUT) as client:
                    async with client.stream("POST", OPENROUTER_URL, headers=headers, json=payload) as resp:
                        if resp.status_code >= 400:
                            body = (await resp.aread()).decode("utf-8", "replace")
                            detail = body[:200]
                            try:
                                detail = json.loads(body).get("error", {}).get("message") or detail
                            except (ValueError, AttributeError):
                                pass
                            if resp.status_code in STREAM_RETRY_STATUS and attempt < attempts - 1:
                                logger.warning("LLM stream %s, retrying (%d/%d): %s", resp.status_code, attempt + 1, attempts - 1, detail)
                                await asyncio.sleep(STREAM_RETRY_DELAYS[attempt])
                                continue
                            inc_llm_request("failure", PROVIDER_NAME, model_used)
                            raise Exception(f"LLM request failed: {resp.status_code} {detail}")
                        streaming = True
                        async for line in resp.aiter_lines():
                            if not line.startswith("data:"):
                                continue
                            data = line[5:].strip()
                            if not data or data == "[DONE]":
                                continue
                            try:
                                chunk = json.loads(data)
                            except ValueError:
                                continue
                            delta = acc.feed(chunk)
                            if delta:
                                yield "delta", delta
                break
            except httpx.RequestError as e:
                # A connection that fails before any bytes is safe to retry; a half-read answer is not.
                if not streaming and attempt < attempts - 1:
                    await asyncio.sleep(STREAM_RETRY_DELAYS[attempt])
                    continue
                inc_llm_request("failure", PROVIDER_NAME, model_used)
                raise Exception(f"LLM request failed: {type(e).__name__} {e}") from e
        message = acc.message()
        self.last_call_meta = {
            "model": acc.model or model_used,
            "prompt_tokens": (acc.usage or {}).get("prompt_tokens"),
            "completion_tokens": (acc.usage or {}).get("completion_tokens"),
            "total_tokens": (acc.usage or {}).get("total_tokens"),
        }
        inc_llm_request("success", PROVIDER_NAME, self.last_call_meta["model"])
        logger.info(
            "LLM stream success",
            extra=log_domain(
                DOMAIN_LLM,
                "chat_stream_success",
                provider=PROVIDER_NAME,
                model=self.last_call_meta["model"],
                duration_ms=round((time.perf_counter() - t0) * 1000, 2),
            ),
        )
        yield "final", ChatToolsResult(
            content=message.get("content"),
            tool_calls=parse_tool_calls(message),
            raw_message=message,
        )

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
