"""
Dependency injection for FastAPI routes
"""

from fastapi import Depends, HTTPException, status, Header
from supabase import create_client, Client
from app.config import settings
from typing import Optional
import threading


# Singleton Supabase client (thread-safe)
_supabase_client: Optional[Client] = None
_supabase_lock = threading.Lock()


def get_supabase() -> Client:
    """
    Get Supabase client instance (singleton pattern).
    
    Creates client once and reuses it for all requests.
    Thread-safe initialization.
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
    
    return _supabase_client


def get_user_id(
    authorization: Optional[str] = Header(None, alias="Authorization"),
    supabase: Client = Depends(get_supabase)
) -> str:
    """
    Extract user ID from Authorization header by verifying JWT with Supabase.
    On expired token, returns 401 - frontend should refresh and retry.
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
        response = supabase.auth.get_user(token)
        
        if hasattr(response, "user") and response.user:
            return str(response.user.id)
        
        if isinstance(response, dict) and "user" in response:
            return str(response["user"]["id"])
            
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
        )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authorization token. Please sign in again.",
        )


