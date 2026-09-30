"""HUBSPOT_READ_ONLY: an environment that may read HubSpot but never write to it.

Set on a backend that works on a customer's real portal for testing (staging sharing a
production connection): every request to api.hubapi.com that is not a read is answered here
with a 423 and never leaves the process. Reads are GET/HEAD, searches (`POST .../search`),
batch reads (`POST .../batch/read`) and the OAuth token refresh. The guard sits in the HTTP
transport of every client that can write to HubSpot (the shared HubSpotClient, the meeting
writer and the handoff owner writer), so a new write path through them is covered too.
"""

from __future__ import annotations

import logging
from typing import Optional
from urllib.parse import urlsplit

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

BLOCKED_STATUS = 423
MESSAGE = "HubSpot is read-only in this environment (HUBSPOT_READ_ONLY): nothing was written."
_READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_READ_POST_SUFFIXES = ("/search", "/batch/read")


def enabled() -> bool:
    return bool(getattr(settings, "HUBSPOT_READ_ONLY", False))


def is_write(method: str, url: str) -> bool:
    """True for a request that would change something in HubSpot."""
    parts = urlsplit(str(url))
    if not (parts.hostname or "").endswith("hubapi.com"):
        return False
    method = (method or "").upper()
    if method in _READ_METHODS:
        return False
    path = parts.path.rstrip("/")
    if path.startswith("/oauth/"):
        return False  # the token refresh keeps reads working; it changes nothing in the portal
    if method == "POST" and path.endswith(_READ_POST_SUFFIXES):
        return False
    return True


def _blocked(request: httpx.Request) -> httpx.Response:
    logger.warning("HubSpot write blocked (HUBSPOT_READ_ONLY): %s %s", request.method, request.url.path)
    return httpx.Response(
        BLOCKED_STATUS,
        json={"status": "error", "category": "READ_ONLY", "message": MESSAGE},
        request=request,
    )


class _SyncGuard(httpx.BaseTransport):
    def __init__(self, inner: httpx.BaseTransport):
        self._inner = inner

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        if enabled() and is_write(request.method, str(request.url)):
            return _blocked(request)
        return self._inner.handle_request(request)

    def close(self) -> None:
        self._inner.close()


class _AsyncGuard(httpx.AsyncBaseTransport):
    def __init__(self, inner: httpx.AsyncBaseTransport):
        self._inner = inner

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if enabled() and is_write(request.method, str(request.url)):
            return _blocked(request)
        return await self._inner.handle_async_request(request)

    async def aclose(self) -> None:
        await self._inner.aclose()


def sync_transport(inner: Optional[httpx.BaseTransport] = None) -> Optional[httpx.BaseTransport]:
    """The transport for a sync client: the guard when HUBSPOT_READ_ONLY is on, else `inner`
    unchanged (None keeps httpx's default transport, exactly as before)."""
    if not enabled():
        return inner
    return _SyncGuard(inner or httpx.HTTPTransport())


def async_transport(inner: Optional[httpx.AsyncBaseTransport] = None) -> Optional[httpx.AsyncBaseTransport]:
    if not enabled():
        return inner
    return _AsyncGuard(inner or httpx.AsyncHTTPTransport())
