"""
Dependency injection for FastAPI routes
"""

from fastapi import Depends, HTTPException, status
from supabase import create_client, Client
from app.config import settings
from typing import Optional


def get_supabase() -> Client:
    """Get Supabase client instance"""
    return create_client(
        settings.SUPABASE_URL,
        settings.SUPABASE_SERVICE_ROLE_KEY
    )


def get_user_id(
    authorization: Optional[str] = None
) -> str:
    """
    Extract user ID from Authorization header
    
    For MVP, we'll use a simple token format.
    In production, this should validate JWT tokens from Supabase Auth.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header"
        )
    
    # TODO: Validate JWT token and extract user_id
    # For now, return a placeholder
    token = authorization.replace("Bearer ", "")
    
    # In production: decode JWT, verify signature, extract user_id
    # For MVP: assume token is user_id (temporary)
    return token


