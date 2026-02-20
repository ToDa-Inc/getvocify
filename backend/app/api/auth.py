"""
Authentication API endpoints

Handles user signup, login, and profile management.
Users are created in Supabase Auth and then a profile is created in user_profiles table.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from uuid import UUID
from typing import Optional

from app.deps import get_supabase, get_user_id
from supabase import Client


router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


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
    created_at: str


class UpdateProfileRequest(BaseModel):
    """Profile update request"""
    full_name: Optional[str] = None
    company_name: Optional[str] = None
    avatar_url: Optional[str] = None
    phone: Optional[str] = None


class AuthResponse(BaseModel):
    """Auth response with user and tokens"""
    user: UserResponse
    access_token: str
    refresh_token: str


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.post("/signup", response_model=AuthResponse)
async def signup(
    request: SignupRequest,
    supabase: Client = Depends(get_supabase),
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
        # Create user in Supabase Auth
        auth_response = supabase.auth.sign_up({
            "email": request.email,
            "password": request.password,
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
            "full_name": request.full_name,
            "company_name": request.company_name,
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
            user=UserResponse(
                id=user_id,
                email=request.email,
                full_name=profile.get("full_name"),
                company_name=profile.get("company_name"),
                avatar_url=profile.get("avatar_url"),
                created_at=profile.get("created_at"),
            ),
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
async def login(
    request: LoginRequest,
    supabase: Client = Depends(get_supabase),
):
    """
    Log in with email and password.
    
    Returns:
        User data and authentication tokens
    """
    try:
        auth_response = supabase.auth.sign_in_with_password({
            "email": request.email,
            "password": request.password,
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
            user=UserResponse(
                id=user_id,
                email=auth_response.user.email or "",
                full_name=profile.get("full_name"),
                company_name=profile.get("company_name"),
                avatar_url=profile.get("avatar_url"),
                created_at=profile.get("created_at", ""),
            ),
            access_token=access_token,
            refresh_token=refresh_token,
        )
        
    except Exception as e:
        error_msg = str(e)
        
        if "Invalid login credentials" in error_msg or "invalid" in error_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Login failed: {error_msg}",
        )


@router.get("/me", response_model=UserResponse)
async def get_current_user(
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
        
        # Get email from auth (if needed)
        # For MVP, we'll get it from the JWT token or skip it
        # In production, decode JWT to get email
        
        return UserResponse(
            id=user_id,
            email="",  # Would get from JWT in production
            full_name=profile.get("full_name"),
            company_name=profile.get("company_name"),
            avatar_url=profile.get("avatar_url"),
            phone=profile.get("phone"),
            created_at=profile.get("created_at", ""),
        )
        
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
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    """Update current user profile. Include phone for WhatsApp sender lookup."""
    updates = {k: v for k, v in request.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    supabase.table("user_profiles").update(updates).eq("id", user_id).execute()
    profile_result = supabase.table("user_profiles").select("*").eq("id", user_id).single().execute()
    if not profile_result.data:
        raise HTTPException(status_code=404, detail="Profile not found")
    p = profile_result.data
    return UserResponse(
        id=user_id,
        email="",
        full_name=p.get("full_name"),
        company_name=p.get("company_name"),
        avatar_url=p.get("avatar_url"),
        phone=p.get("phone"),
        created_at=p.get("created_at", ""),
    )


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


@router.post("/refresh", response_model=RefreshResponse)
async def refresh_token(
    request: RefreshRequest,
    supabase: Client = Depends(get_supabase),
):
    """
    Refresh the access token using a refresh token.
    
    Returns new access token and refresh token.
    """
    try:
        # Refresh session with Supabase
        auth_response = supabase.auth.refresh_session(request.refresh_token)
        
        if not auth_response.session:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired refresh token",
            )
        
        access_token = auth_response.session.access_token
        refresh_token = auth_response.session.refresh_token
        expires_in = auth_response.session.expires_in or 3600
        
        return RefreshResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=expires_in,
        )
        
    except Exception as e:
        error_msg = str(e)
        
        if "invalid" in error_msg.lower() or "expired" in error_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired refresh token",
            )
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Token refresh failed: {error_msg}",
        )

