from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.services.auth_session import (
    AccessTokenError,
    AccessTokenExpired,
    RefreshTokenReuseCache,
    classify_refresh_failure,
    user_id_from_access_token,
)


SECRET = "test-jwt-secret-for-auth-session-32b+"


def _token(*, sub="user-123", exp_delta=3600, secret=SECRET, aud="authenticated"):
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": sub,
            "aud": aud,
            "role": "authenticated",
            "iat": now,
            "exp": now + timedelta(seconds=exp_delta),
        },
        secret,
        algorithm="HS256",
    )


def test_oauth_client_id_bug_is_unavailable_not_a_dead_session():
    kind, status = classify_refresh_failure(
        "missing destination name oauth_client_id in *models.Session"
    )
    assert kind == "unavailable"
    assert status == 503


def test_network_and_timeouts_are_unavailable():
    assert classify_refresh_failure("ConnectTimeout")[1] == 503
    assert classify_refresh_failure("timed out talking to GoTrue")[1] == 503
    assert classify_refresh_failure("connection reset")[1] == 503


def test_gotrue_500_for_a_used_refresh_token_is_unavailable():
    kind, status = classify_refresh_failure("500 Internal Server Error: Invalid refresh_token")
    assert kind == "unavailable"
    assert status == 503
    assert classify_refresh_failure("unexpected_failure")[1] == 503


def test_invalid_or_expired_refresh_token_is_a_real_logout():
    kind, status = classify_refresh_failure("Invalid Refresh Token")
    assert kind == "expired"
    assert status == 401
    assert classify_refresh_failure("refresh_token_not_found")[1] == 401
    assert classify_refresh_failure("Expired refresh token")[1] == 401


def test_valid_access_token_returns_user_id():
    token = _token(sub="user-123")
    assert user_id_from_access_token(token, SECRET) == "user-123"


def test_expired_access_token_is_expired_not_invalid():
    token = _token(exp_delta=-10)
    with pytest.raises(AccessTokenExpired):
        user_id_from_access_token(token, SECRET, leeway_seconds=0)


def test_bad_signature_is_invalid():
    token = _token(secret="other-jwt-secret-for-auth-session-32b+")
    with pytest.raises(AccessTokenError):
        user_id_from_access_token(token, SECRET)


def test_reuse_cache_returns_the_same_tokens_within_ttl():
    cache = RefreshTokenReuseCache(ttl_seconds=30)
    cache.put(
        "old-refresh",
        {"access_token": "new-a", "refresh_token": "new-r", "expires_in": 3600},
        now=1_000.0,
    )
    hit = cache.get("old-refresh", now=1_020.0)
    assert hit["access_token"] == "new-a"
    assert hit["refresh_token"] == "new-r"
    assert cache.get("old-refresh", now=1_031.0) is None
    assert cache.get("some-other-token", now=1_020.0) is None
