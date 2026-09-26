"""Resend transport for report delivery (idempotency key only in headers)."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
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


def report_resend_sender(
    resend_client: ReportResendClient | None,
    *,
    to: str,
    subject: str,
    html: str,
    from_email: str | None = None,
) -> ResendReportSender | None:
    if resend_client is None:
        return None
    return ResendReportSender(
        resend_client,
        to=to,
        subject=subject,
        html=html,
        from_email=from_email,
    )


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

    def _send_blocking(self, key: str):
        return asyncio.run(
            self._client.send_email(
                self._to,
                self._subject,
                self._html,
                from_email=self._from_email,
                idempotency_key=key,
            )
        )

    def send(self, key: str) -> None:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            in_loop = False
        else:
            in_loop = True
        try:
            if in_loop:
                # asyncio.run cannot nest inside the server's loop; give the send its own loop.
                with ThreadPoolExecutor(max_workers=1) as pool:
                    result = pool.submit(self._send_blocking, key).result()
            else:
                result = self._send_blocking(key)
        except httpx.TimeoutException as exc:
            raise TimeoutError(str(exc)) from exc
        remote_id = result.get("id") if isinstance(result, dict) else None
        if remote_id:
            self._remote[key] = str(remote_id)

    def reconcile(self, key: str) -> str | None:
        return self._remote.get(key)
