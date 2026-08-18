"""
Authentication API endpoints

Handles user signup, login, and profile management.
Users are created in Supabase Auth and then a profile is created in user_profiles table.
"""

import logging
import re
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field
from uuid import UUID
from typing import Optional, List

from app.config import settings
from app.deps import get_supabase, get_supabase_auth, get_user_id
from app.rate_limit import limiter
from supabase import Client


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def normalize_phone_for_lookup(phone: Optional[str]) -> Optional[str]:
    """Canonical E.164-ish phone for WhatsApp lookup."""
    if phone is None:
        return None
    digits = re.sub(r"\D", "", phone)
    if not digits:
        return None
    return f"+{digits}"


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class SignupRequest(BaseModel):
    """Signup request"""
    email: EmailStr
    password: str = Field(..., min_length=8, description="Password must be at least 8 characters")
    full_name: str
    company_name: Optional[str] = None


class LoginRequest(BaseModel):
    """Login request"""
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    """User response"""
    id: str
    email: str
    full_name: Optional[str] = None
    company_name: Optional[str] = None
    avatar_url: Optional[str] = None
    phone: Optional[str] = None
    auto_create_contact_company: bool = False
    product_context: Optional[str] = None
    stt_languages: List[str] = Field(default_factory=lambda: ["es"])
    created_at: str


class UpdateProfileRequest(BaseModel):
    """Profile update request"""
    full_name: Optional[str] = None
    company_name: Optional[str] = None
    avatar_url: Optional[str] = None
    phone: Optional[str] = None
    auto_create_contact_company: Optional[bool] = None
    product_context: Optional[str] = Field(default=None, max_length=8000)
    stt_languages: Optional[List[str]] = None


def _user_response(user_id: str, email: str, profile: dict) -> UserResponse:
    from app.services.session_entities import normalize_stt_languages

    return UserResponse(
        id=user_id,
        email=email,
        full_name=profile.get("full_name"),
        company_name=profile.get("company_name"),
        avatar_url=profile.get("avatar_url"),
        phone=profile.get("phone"),
        auto_create_contact_company=bool(profile.get("auto_create_contact_company", False)),
        product_context=profile.get("product_context") or "",
        stt_languages=normalize_stt_languages(profile.get("stt_languages")),
        created_at=profile.get("created_at", ""),
    )


class AuthResponse(BaseModel):
    """Auth response with user and tokens"""
    user: UserResponse
    access_token: str
    refresh_token: str


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.post("/signup", response_model=AuthResponse)
@limiter.limit("5/hour")
async def signup(
    request: Request,
    body: SignupRequest,
    supabase: Client = Depends(get_supabase),
    auth_client: Client = Depends(get_supabase_auth),
):
    """
    Sign up a new user.
    
    Creates:
    1. User in Supabase Auth (auth.users)
    2. Profile in user_profiles table
    
    Returns:
        User data and authentication tokens
    """
    try:
        # Auth only on the anon client — never sign_up on the service-role DB client
        # (supabase-py replaces Authorization with the user JWT on SIGNED_IN).
        auth_response = auth_client.auth.sign_up({
            "email": body.email,
            "password": body.password,
        })
        
        if not auth_response.user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to create user account",
            )
        
        user_id = str(auth_response.user.id)
        access_token = auth_response.session.access_token if auth_response.session else ""
        refresh_token = auth_response.session.refresh_token if auth_response.session else ""
        
        # Create user profile in user_profiles table
        profile_data = {
            "id": user_id,
            "full_name": body.full_name,
            "company_name": body.company_name,
        }
        
        profile_result = supabase.table("user_profiles").insert(profile_data).execute()
        
        if not profile_result.data:
            # If profile creation fails, we should clean up the auth user
            # But for MVP, we'll just raise an error
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="User created but failed to create profile",
            )
        
        profile = profile_result.data[0]
        
        return AuthResponse(
            user=_user_response(user_id, body.email, profile),
            access_token=access_token,
            refresh_token=refresh_token,
        )
        
    except Exception as e:
        error_msg = str(e)
        
        # Handle Supabase auth errors
        if "User already registered" in error_msg or "already exists" in error_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User with this email already exists",
            )
        
        # Re-raise HTTP exceptions
        if isinstance(e, HTTPException):
            raise
        
        # Generic error
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Signup failed: {error_msg}",
        )


@router.post("/login", response_model=AuthResponse)
@limiter.limit("10/minute")
async def login(
    request: Request,
    body: LoginRequest,
    supabase: Client = Depends(get_supabase),
    auth_client: Client = Depends(get_supabase_auth),
):
    """
    Log in with email and password.
    
    Returns:
        User data and authentication tokens
    """
    try:
        # Auth only on the anon client — never sign_in on the service-role DB client
        # (supabase-py replaces Authorization with the user JWT on SIGNED_IN → RLS 42501).
        auth_response = auth_client.auth.sign_in_with_password({
            "email": body.email,
            "password": body.password,
        })
        
        if not auth_response.user or not auth_response.session:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )
        
        user_id = str(auth_response.user.id)
        access_token = auth_response.session.access_token
        refresh_token = auth_response.session.refresh_token
        
        # Get user profile (0 rows OK, we'll create; single() throws PGRST116 if no row)
        profile_result = supabase.table("user_profiles").select("*").eq("id", user_id).limit(1).execute()
        profile_data_list = (profile_result.data if profile_result else None) or []
        
        if not profile_data_list:
            # Profile doesn't exist - create it
            profile_data = {
                "id": user_id,
                "full_name": None,
                "company_name": None,
            }
            supabase.table("user_profiles").insert(profile_data).execute()
            profile = profile_data
        else:
            profile = profile_data_list[0]
        
        return AuthResponse(
            user=_user_response(user_id, auth_response.user.email or "", profile),
            access_token=access_token,
            refresh_token=refresh_token,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e)
        logger.warning("Login failed for %s: %s", body.email, error_msg[:200])
        if "Invalid login credentials" in error_msg or "invalid" in error_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )
        if "Email not confirmed" in error_msg or "email_not_confirmed" in error_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Please confirm your email before logging in. Check your inbox.",
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Login failed: {error_msg}",
        )


def _bearer_token_from_request(request: Request) -> Optional[str]:
    auth_header = request.headers.get("Authorization") or ""
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
        return token or None
    return None


@router.get("/me", response_model=UserResponse)
async def get_current_user(
    request: Request,
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    """
    Get current authenticated user.
    
    Returns:
        User profile data
    """
    try:
        # Get user profile
        profile_result = supabase.table("user_profiles").select("*").eq("id", user_id).single().execute()
        
        if not profile_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User profile not found",
            )
        
        profile = profile_result.data
        # Token already authenticated by get_user_id; decode claims for email only.
        email = _email_from_access_token(_bearer_token_from_request(request)) or ""
        
        return _user_response(user_id, email, profile)
        
    except Exception as e:
        error_str = str(e)
        if "no rows" in error_str.lower() or "PGRST116" in error_str:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User profile not found",
            )
        raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to get user: {error_str}",
        )


@router.patch("/me", response_model=UserResponse)
async def update_profile(
    request: UpdateProfileRequest,
    http_request: Request,
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    """Update current user profile. Include phone for WhatsApp sender lookup."""
    updates = {k: v for k, v in request.model_dump(exclude_none=True).items()}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    if "phone" in updates:
        normalized_phone = normalize_phone_for_lookup(updates.get("phone"))
        updates["phone"] = normalized_phone
    if "stt_languages" in updates:
        from app.services.session_entities import normalize_stt_languages

        updates["stt_languages"] = normalize_stt_languages(updates.get("stt_languages"))
    supabase.table("user_profiles").update(updates).eq("id", user_id).execute()
    profile_result = supabase.table("user_profiles").select("*").eq("id", user_id).single().execute()
    if not profile_result.data:
        raise HTTPException(status_code=404, detail="Profile not found")
    p = profile_result.data
    email = _email_from_access_token(_bearer_token_from_request(http_request)) or ""
    return _user_response(user_id, email, p)


@router.post("/logout")
async def logout(
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    """
    Log out the current user.
    
    Invalidates the session on the server side.
    Frontend should also clear tokens from localStorage.
    """
    try:
        # Supabase doesn't have a server-side logout endpoint
        # The JWT token will expire naturally
        # For now, we just return success
        # Frontend will clear tokens from localStorage
        return {"success": True, "message": "Logged out successfully"}
    except Exception as e:
        # Don't fail logout even if there's an error
        return {"success": True, "message": "Logged out successfully"}


class RefreshRequest(BaseModel):
    """Refresh token request"""
    refresh_token: str


class RefreshResponse(BaseModel):
    """Refresh token response"""
    access_token: str
    refresh_token: str
    expires_in: int = 3600


def validate_startup_config() -> None:
    """
    Fail the app's boot, not a user's /auth/refresh request, if this module is
    misconfigured. Call from app.main's startup_event, before the app is
    marked ready for traffic - same pattern as
    crm_updates.validate_startup_config for CRM_UPDATES_LEGACY_PENDING_CUTOFF.

    SUPABASE_JWT_SECRET security-gates the GoTrue "oauth_client_id" bug
    handling below (see refresh_token): without it, that code path used to
    fall back to trusting an unverified, client-supplied token to decide who
    gets a new session. It's not "optional but recommended" - treat it the
    same as any other credential this app can't run safely without.
    """
    if not settings.SUPABASE_JWT_SECRET:
        raise RuntimeError(
            "SUPABASE_JWT_SECRET is not configured. This is required so that "
            "/auth/refresh can verify (signature + expiry) any token it uses "
            "to decide whose session to touch. Refusing to start."
        )


@router.post("/refresh", response_model=RefreshResponse)
@limiter.limit("30/minute")
async def refresh_token(
    request: Request,
    body: RefreshRequest,
    supabase: Client = Depends(get_supabase_auth),
):
    """
    Refresh the access token using a refresh token.

    Returns new access token and refresh token.
    Uses the anon-key auth client when available (more reliable than service role).

    If GoTrue itself is broken (the "oauth_client_id" platform bug - see
    https://github.com/supabase/supabase/issues/39394), this fails the refresh
    cleanly (401) instead of re-issuing a session. There used to be an admin
    magiclink bypass here that resolved *who* to re-issue a session for from a
    client-supplied access_token. It was removed: there is no Admin API or
    exposed table that lets us independently confirm that access_token
    belongs to the *same* session as the refresh_token that failed - Supabase
    only exposes that binding via the refresh_session call itself, which is
    exactly what's broken. Trusting a second, unrelated token to pick whose
    session to touch is a forgeable/replayable identity check, not a real
    one. Forcing a clean re-login is the safe failure mode until Supabase
    fixes their infrastructure (Project Settings → Infrastructure → Upgrade,
    or a support ticket).
    """
    token = (body.refresh_token or "").strip()
    if not token or token in ("undefined", "null"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    try:
        auth_response = supabase.auth.refresh_session(token)

        if not auth_response.session:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired refresh token",
            )

        access_token = auth_response.session.access_token
        new_refresh = auth_response.session.refresh_token
        expires_in = auth_response.session.expires_in or 3600

        return RefreshResponse(
            access_token=access_token,
            refresh_token=new_refresh,
            expires_in=expires_in,
        )

    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e)
        lower = error_msg.lower()

        # Transient network to Supabase — do not treat as expired session
        if any(s in lower for s in ("timed out", "timeout", "connecttimeout", "connection", "network")):
            logger.warning("Token refresh unreachable: %s", error_msg)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Auth service temporarily unreachable. Please try again.",
            )

        # Known Supabase Auth platform bug (see docstring above) — no safe way
        # to identify the caller independently of the broken call, so fail
        # clean instead of guessing. Logged at ERROR (not just observability -
        # every occurrence is a forced re-login) so frequency is visible.
        if "oauth_client_id" in lower or "unexpected_failure" in lower:
            logger.error(
                "Supabase Auth refresh broken (oauth_client_id) — no safe bypass "
                "available, forcing re-login — %s",
                error_msg,
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session expired due to a Supabase Auth platform issue. Please sign in again.",
            )

        # GoTrue often returns 500 for already-used / invalid refresh tokens
        auth_failure = any(
            s in lower
            for s in (
                "invalid",
                "expired",
                "refresh_token",
                "refresh token",
                "not found",
                "unauthorized",
                "forbidden",
            )
        )
        if not auth_failure and "500" in lower and "token" in lower:
            auth_failure = True
        if auth_failure:
            logger.warning("Token refresh rejected: %s", error_msg)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired refresh token",
            )

        logger.exception("Token refresh failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Token refresh failed: {error_msg}",
        )

