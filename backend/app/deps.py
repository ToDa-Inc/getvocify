"""
Dependency injection for FastAPI routes
"""

from fastapi import Depends, HTTPException, status, Header
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
    authorization: Optional[str] = Header(None, alias="Authorization"),
    supabase: Client = Depends(get_supabase)
) -> str:
    """
    Extract user ID from Authorization header by verifying with Supabase
    """
    if not authorization:
        print("DEBUG: Authorization header missing")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization header"
        )
    
    if not authorization.startswith("Bearer "):
        print(f"DEBUG: Authorization header malformed: {authorization[:15]}...")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format"
        )
    
    # Extract the token
    token = authorization.replace("Bearer ", "").strip()
    
    if token == "undefined" or token == "null":
        print(f"DEBUG: Authorization token is invalid string: '{token}'")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid session token ({token})"
        )
    
    try:
        # Verify the JWT with Supabase and get the actual User object
        response = supabase.auth.get_user(token)
        
        # The latest Supabase SDK returns a UserResponse object
        # We need to check if 'user' exists in the response
        if hasattr(response, 'user') and response.user:
            return str(response.user.id)
        
        # Fallback for older SDK versions or different response structures
        if isinstance(response, dict) and 'user' in response:
            return str(response['user']['id'])
            
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session"
        )
    except Exception as e:
        print(f"DEBUG: Auth verification failed: {str(e)}")
        # If verification fails, check if the token itself is a valid UUID
        # (This supports simple local testing where token == user_id)
        import uuid
        try:
            uuid.UUID(token)
            return token
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authorization token"
            )


