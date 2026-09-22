"""Resend transport for report delivery (idempotency key only in headers)."""

from __future__ import annotations

import asyncio
from typing import Any, Protocol

import httpx


class ReportResendClient(Protocol):
    async def send_email(
        self,
        to: str,
        subject: str,
        html: str,
        from_email: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]: ...


class ResendReportSender:
    def __init__(
        self,
        client: ReportResendClient,
        *,
        to: str,
        subject: str,
        html: str,
        from_email: str | None = None,
    ):
        self._client = client
        self._to = to
        self._subject = subject
        self._html = html
        self._from_email = from_email
        self._remote: dict[str, str] = {}

    def send(self, key: str) -> None:
        try:
            result = asyncio.run(
                self._client.send_email(
                    self._to,
                    self._subject,
                    self._html,
                    from_email=self._from_email,
                    idempotency_key=key,
                )
            )
        except httpx.TimeoutException as exc:
            raise TimeoutError(str(exc)) from exc
        remote_id = result.get("id") if isinstance(result, dict) else None
        if remote_id:
            self._remote[key] = str(remote_id)

    def reconcile(self, key: str) -> str | None:
        return self._remote.get(key)
