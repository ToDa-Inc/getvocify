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
from app.services.auth_session import (
    RefreshTokenReuseCache,
    claims_for_refresh_bypass,
    classify_refresh_failure,
    should_reissue_on_gotrue_bug,
)
from supabase import Client

_refresh_reuse = RefreshTokenReuseCache(ttl_seconds=30)


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
    # Expired access JWT. Used only when GoTrue refresh hits oauth_client_id.
    # Must verify with SUPABASE_JWT_SECRET — never trust an unsigned payload.
    access_token: Optional[str] = None


class RefreshResponse(BaseModel):
    """Refresh token response"""
    access_token: str
    refresh_token: str
    expires_in: int = 3600


def _decode_access_token_claims(access_token: Optional[str]) -> Optional[dict]:
    """Read claims from a Supabase access token. Signature-verified; not used for authorization."""
    if not access_token or access_token in ("undefined", "null"):
        return None
    if not settings.SUPABASE_JWT_SECRET:
        return None
    try:
        import jwt as pyjwt

        return pyjwt.decode(
            access_token,
            settings.SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            options={"verify_exp": False},
            audience="authenticated",
        )
    except Exception as e:
        logger.warning("Access token decode failed: %s", e)
        return None


def _email_from_access_token(access_token: Optional[str]) -> Optional[str]:
    claims = _decode_access_token_claims(access_token)
    if not claims:
        return None
    email = claims.get("email")
    if isinstance(email, str) and "@" in email:
        return email
    meta = claims.get("user_metadata") or {}
    meta_email = meta.get("email") if isinstance(meta, dict) else None
    if isinstance(meta_email, str) and "@" in meta_email:
        return meta_email
    return None


def validate_startup_config() -> None:
    """
    Fail the app's boot, not a user's /auth/refresh request, if this module is
    misconfigured. Call from app.main's startup_event, before the app is
    marked ready for traffic - same pattern as
    crm_updates.validate_startup_config for CRM_UPDATES_LEGACY_PENDING_CUTOFF.

    SUPABASE_JWT_SECRET verifies access JWTs on every authenticated request
    (see deps.get_user_id). Without it, that check has no basis. It's not
    optional — treat it the same as any other credential this app can't
    run safely without.
    """
    if not settings.SUPABASE_JWT_SECRET:
        raise RuntimeError(
            "SUPABASE_JWT_SECRET is not configured. This is required so that "
            "/auth/refresh can verify (signature + expiry) any token it uses "
            "to decide whose session to touch. Refusing to start."
        )


def _session_still_active(user_id: str, session_id: Optional[str]) -> bool:
    """True if auth.sessions still has this row, or if we cannot query it."""
    if not session_id:
        return True
    try:
        admin = get_supabase()
        result = (
            admin.postgrest.schema("auth")
            .from_("sessions")
            .select("id, user_id")
            .eq("id", session_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        return bool(result.data)
    except Exception as e:
        logger.warning("auth.sessions lookup failed during refresh reissue: %s", e)
        return True


def _reissue_session_for_verified_claims(claims: dict) -> RefreshResponse:
    """
    GoTrue refresh_session cannot scan oauth_client_id. Login still works.
    Re-issue only for a signature-verified access JWT (expiry ignored).
    """
    admin = get_supabase()
    user_id = claims.get("sub")
    resolved_email = (claims.get("email") or "").strip() or None
    session_id = claims.get("session_id")

    if not _session_still_active(str(user_id or ""), session_id):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    if not resolved_email and user_id:
        try:
            user_resp = admin.auth.admin.get_user_by_id(user_id)
            user = getattr(user_resp, "user", None) or user_resp
            resolved_email = getattr(user, "email", None)
            if not resolved_email and isinstance(user, dict):
                resolved_email = user.get("email")
        except Exception as e:
            logger.warning("Admin get_user_by_id failed during refresh reissue: %s", e)

    if not resolved_email:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Auth service temporarily unreachable. Please try again.",
        )

    try:
        link = admin.auth.admin.generate_link({"type": "magiclink", "email": resolved_email})
        props = getattr(link, "properties", None)
        email_otp = getattr(props, "email_otp", None) if props else None
        hashed = getattr(props, "hashed_token", None) if props else None
        if not email_otp and not hashed:
            raise RuntimeError("generate_link returned no otp")

        auth_client = get_supabase_auth()
        if email_otp:
            verified = auth_client.auth.verify_otp(
                {"email": resolved_email, "token": email_otp, "type": "magiclink"}
            )
        else:
            verified = auth_client.auth.verify_otp(
                {"token_hash": hashed, "type": "magiclink"}
            )

        session = getattr(verified, "session", None)
        if not session:
            raise RuntimeError("verify_otp returned no session")

        logger.warning(
            "Supabase refresh broken (oauth_client_id); re-issued session via verified JWT for %s",
            resolved_email,
        )
        return RefreshResponse(
            access_token=session.access_token,
            refresh_token=session.refresh_token,
            expires_in=session.expires_in or 3600,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Refresh reissue failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Auth service temporarily unreachable. Please try again.",
        ) from e


@router.post("/refresh", response_model=RefreshResponse)
@limiter.limit("60/minute")
async def refresh_token(
    request: Request,
    body: RefreshRequest,
    supabase: Client = Depends(get_supabase_auth),
):
    """
    Rotate the access JWT using a refresh token.

    401 = refresh token is dead. 503 = Auth unreachable (keep stored tokens).

    If GoTrue hits the oauth_client_id platform bug, we may re-issue a session
    only from a signature-verified access JWT (expired is OK). That is not the
    Aug 2026 hole, which decoded tokens with verify_signature=False.
    """
    token = (body.refresh_token or "").strip()
    if not token or token in ("undefined", "null"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    with _refresh_reuse.lock_for(token):
        cached = _refresh_reuse.get(token)
        if cached:
            return RefreshResponse(
                access_token=cached["access_token"],
                refresh_token=cached["refresh_token"],
                expires_in=int(cached.get("expires_in") or 3600),
            )

        try:
            auth_response = supabase.auth.refresh_session(token)

            if not auth_response.session:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or expired refresh token",
                )

            payload = {
                "access_token": auth_response.session.access_token,
                "refresh_token": auth_response.session.refresh_token,
                "expires_in": auth_response.session.expires_in or 3600,
            }
            _refresh_reuse.put(token, payload)
            return RefreshResponse(
                access_token=payload["access_token"],
                refresh_token=payload["refresh_token"],
                expires_in=int(payload["expires_in"]),
            )

        except HTTPException:
            raise
        except Exception as e:
            error_msg = str(e)
            kind, http_status = classify_refresh_failure(error_msg)
            if should_reissue_on_gotrue_bug(error_msg):
                claims = claims_for_refresh_bypass(
                    body.access_token, settings.SUPABASE_JWT_SECRET or ""
                )
                if claims:
                    issued = _reissue_session_for_verified_claims(claims)
                    _refresh_reuse.put(
                        token,
                        {
                            "access_token": issued.access_token,
                            "refresh_token": issued.refresh_token,
                            "expires_in": issued.expires_in,
                        },
                    )
                    return issued
                logger.error(
                    "Token refresh unavailable (%s) and no verified access token: %s",
                    kind,
                    error_msg,
                )
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Auth service temporarily unreachable. Please try again.",
                )
            if http_status == 503:
                logger.warning("Token refresh unavailable (%s): %s", kind, error_msg)
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Auth service temporarily unreachable. Please try again.",
                )
            logger.warning("Token refresh rejected: %s", error_msg)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired refresh token",
            )

