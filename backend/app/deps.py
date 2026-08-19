"""
Dependency injection for FastAPI routes
"""

from fastapi import HTTPException, status, Header
from supabase import create_client, Client
from app.config import settings
from app.services.auth_session import (
    AccessTokenError,
    AccessTokenExpired,
    user_id_from_access_token,
)
from typing import Optional
import threading


# Singleton Supabase client (thread-safe)
_supabase_client: Optional[Client] = None
_supabase_auth_client: Optional[Client] = None
_supabase_lock = threading.Lock()


def _ensure_service_role_auth(client: Client) -> Client:
    """
    Keep the DB singleton on service_role.

    supabase-py listens for SIGNED_IN and swaps PostgREST Authorization to the
    user JWT. Any later insert then hits RLS (42501 on crm_updates, etc.).
    """
    service_header = f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}"
    headers = client.options.headers
    if headers is None:
        client.options.headers = {"Authorization": service_header}
    else:
        current = headers.get("Authorization")
        if current != service_header:
            headers["Authorization"] = service_header
    # Force PostgREST/storage clients to rebuild with the service key
    client._postgrest = None
    client._storage = None
    client._functions = None
    return client


def get_supabase() -> Client:
    """
    Get Supabase client instance (singleton pattern).
    
    Creates client once and reuses it for all requests.
    Thread-safe initialization. Uses service role for DB access.
    """
    global _supabase_client
    
    if _supabase_client is None:
        with _supabase_lock:
            # Double-check pattern
            if _supabase_client is None:
                try:
                    _supabase_client = create_client(
                        settings.SUPABASE_URL,
                        settings.SUPABASE_SERVICE_ROLE_KEY
                    )
                except Exception as e:
                    error_msg = str(e)
                    # Check for DNS/connection errors
                    if "nodename nor servname" in error_msg or "not known" in error_msg:
                        raise RuntimeError(
                            f"Failed to connect to Supabase. DNS resolution failed for URL: {settings.SUPABASE_URL}\n"
                            f"Please verify:\n"
                            f"  1. SUPABASE_URL is correct in your .env file\n"
                            f"  2. The URL is accessible from your network\n"
                            f"  3. The URL format is: https://your-project.supabase.co\n"
                            f"Error: {error_msg}"
                        )
                    raise RuntimeError(
                        f"Failed to initialize Supabase client: {error_msg}\n"
                        f"Please check your SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env"
                    )
    
    return _ensure_service_role_auth(_supabase_client)


def get_supabase_auth() -> Client:
    """
    Supabase client for Auth endpoints (login / refresh).

    Prefer the anon key: GoTrue refresh with the service-role key often returns
    opaque 500s for invalid/rotated refresh tokens. Falls back to service role.
    """
    global _supabase_auth_client

    if _supabase_auth_client is not None:
        return _supabase_auth_client

    with _supabase_lock:
        if _supabase_auth_client is not None:
            return _supabase_auth_client

        anon = getattr(settings, "SUPABASE_ANON_KEY", None) or ""
        key = str(anon).strip() or settings.SUPABASE_SERVICE_ROLE_KEY
        if not key:
            raise RuntimeError(
                "Missing Supabase auth key. Set SUPABASE_ANON_KEY or SUPABASE_SERVICE_ROLE_KEY."
            )
        _supabase_auth_client = create_client(settings.SUPABASE_URL, key)
        return _supabase_auth_client


def get_user_id(
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> str:
    """
    Extract user ID from the Bearer access JWT.

    Verified locally with SUPABASE_JWT_SECRET (signature + expiry). A GoTrue
    blip must not look like "this session died" — that used to 401 every API
    call and make clients wipe stored refresh tokens.
    Expired JWT → 401 so the client can refresh. Invalid JWT → 401.
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization header. Please sign in to get an access token.",
        )
    
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format",
        )
    
    token = authorization.replace("Bearer ", "").strip()
    
    if not token or token in ("undefined", "null"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session token",
        )

    try:
        return user_id_from_access_token(token, settings.SUPABASE_JWT_SECRET or "")
    except AccessTokenExpired:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
        )
    except AccessTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authorization token. Please sign in again.",
        )


