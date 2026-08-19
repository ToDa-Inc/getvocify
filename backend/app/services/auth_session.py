"""
Vocify Auth session policy.

Access JWTs stay short-lived (Supabase default ~1h). Refresh tokens keep the
user signed in for weeks. Callers must not treat Auth outages or refresh-token
reuse races as "this person logged out."
"""

from __future__ import annotations

import hashlib
import threading
import time
from typing import Any, Optional

import jwt as pyjwt


class AccessTokenError(Exception):
    """Token is missing, forged, or not a Vocify access JWT."""


class AccessTokenExpired(AccessTokenError):
    """Signature ok, clock says it is expired — client should refresh."""


def classify_refresh_failure(error_msg: str) -> tuple[str, int]:
    """
    Map a GoTrue / network error to (kind, http_status).

    expired/401 — the refresh token itself is dead; clients may sign the user out.
    unavailable/503 — try again later; keep stored refresh tokens.
    """
    lower = (error_msg or "").lower()

    if any(
        s in lower
        for s in ("timed out", "timeout", "connecttimeout", "connection", "network")
    ):
        return "unavailable", 503

    if "oauth_client_id" in lower:
        return "unavailable", 503

    # Opaque GoTrue 500s include already-used refresh tokens (reuse race) and
    # platform bugs. Neither is "this user logged out."
    if "unexpected_failure" in lower or "500" in lower:
        return "unavailable", 503

    auth_failure = any(
        s in lower
        for s in (
            "invalid",
            "expired",
            "refresh_token_not_found",
            "refresh_token",
            "refresh token",
            "not found",
            "unauthorized",
            "forbidden",
        )
    )
    if auth_failure:
        return "expired", 401
    return "unavailable", 503


def should_reissue_on_gotrue_bug(error_msg: str) -> bool:
    """Only the known GoTrue Session.oauth_client_id scan bug may use the reissue path."""
    return "oauth_client_id" in (error_msg or "").lower()


def claims_for_refresh_bypass(access_token: Optional[str], secret: str) -> Optional[dict[str, str]]:
    """
    Identify who a broken GoTrue refresh may re-issue for.

    Signature is verified. Expiry is not: the access JWT is often already expired,
    which is why the client is refreshing. A token that does not verify is ignored
    (the Aug 2026 hole was decode-without-verify).
    """
    if not access_token or access_token in ("undefined", "null") or not secret:
        return None
    try:
        claims = pyjwt.decode(
            access_token,
            secret,
            algorithms=["HS256"],
            audience="authenticated",
            options={"verify_exp": False},
            leeway=30,
        )
    except pyjwt.InvalidTokenError:
        return None
    sub = claims.get("sub")
    if not sub:
        return None
    email = claims.get("email")
    if not isinstance(email, str) or "@" not in email:
        meta = claims.get("user_metadata") or {}
        meta_email = meta.get("email") if isinstance(meta, dict) else None
        email = meta_email if isinstance(meta_email, str) else ""
    session_id = claims.get("session_id")
    out = {"sub": str(sub), "email": email if isinstance(email, str) else ""}
    if session_id:
        out["session_id"] = str(session_id)
    return out


def user_id_from_access_token(
    token: str,
    secret: str,
    *,
    leeway_seconds: int = 30,
) -> str:
    """Verify a Supabase access JWT locally. Does not call GoTrue."""
    if not token or token in ("undefined", "null"):
        raise AccessTokenError("missing token")
    if not secret:
        raise AccessTokenError("missing jwt secret")
    try:
        claims = pyjwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            audience="authenticated",
            leeway=leeway_seconds,
        )
    except pyjwt.ExpiredSignatureError as e:
        raise AccessTokenExpired("expired") from e
    except pyjwt.InvalidTokenError as e:
        raise AccessTokenError(str(e)) from e

    sub = claims.get("sub")
    if not sub:
        raise AccessTokenError("missing sub")
    return str(sub)


def _token_key(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class RefreshTokenReuseCache:
    """
    If two tabs refresh the same token at once, return the first success
    instead of asking GoTrue to rotate twice (which revokes the session).
    """

    def __init__(self, ttl_seconds: float = 30):
        self._ttl = ttl_seconds
        self._items: dict[str, tuple[float, dict[str, Any]]] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    def lock_for(self, token: str) -> threading.Lock:
        key = _token_key(token)
        with self._guard:
            lock = self._locks.get(key)
            if lock is None:
                lock = threading.Lock()
                self._locks[key] = lock
            return lock

    def get(self, token: str, now: Optional[float] = None) -> Optional[dict[str, Any]]:
        key = _token_key(token)
        stamp = now if now is not None else time.monotonic()
        with self._guard:
            item = self._items.get(key)
            if not item:
                return None
            expires_at, payload = item
            if stamp >= expires_at:
                self._items.pop(key, None)
                return None
            return dict(payload)

    def put(
        self,
        old_token: str,
        payload: dict[str, Any],
        now: Optional[float] = None,
    ) -> None:
        key = _token_key(old_token)
        stamp = now if now is not None else time.monotonic()
        with self._guard:
            self._items[key] = (stamp + self._ttl, dict(payload))
