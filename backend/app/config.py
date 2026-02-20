"""
Application configuration from environment variables
"""

import os
from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import Optional
from pathlib import Path

# Calculate the path to the root .env file
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
ENV_FILE = ROOT_DIR / ".env"

class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # AI Services
    DEEPGRAM_API_KEY: Optional[str] = None  # Disabled: using Speechmatics only
    SPEECHMATICS_API_KEY: Optional[str] = None
    OPENROUTER_API_KEY: str
    EXTRACTION_MODEL: str = "x-ai/grok-4.1-fast"

    @field_validator("OPENROUTER_API_KEY")
    @classmethod
    def strip_openrouter_key(cls, v: str) -> str:
        """Strip whitespace and quotes that can break auth."""
        if not v:
            return v
        return v.strip().strip('"').strip("'")
    
    # Supabase
    SUPABASE_URL: str
    SUPABASE_SERVICE_ROLE_KEY: str
    
    # Application
    ENVIRONMENT: str = "development"
    FRONTEND_URL: str = "http://localhost:5173"

    # HubSpot OAuth (required for OAuth flow; private app flow does not use these)
    HUBSPOT_CLIENT_ID: Optional[str] = None
    HUBSPOT_CLIENT_SECRET: Optional[str] = None
    HUBSPOT_REDIRECT_URI: Optional[str] = None

    # JWT secret for signing OAuth state (prevents CSRF)
    JWT_SECRET: Optional[str] = None

    # WhatsApp (optional - app runs without these)
    WHATSAPP_ACCESS_TOKEN: Optional[str] = None
    WHATSAPP_PHONE_NUMBER_ID: Optional[str] = None
    WHATSAPP_VERIFY_TOKEN: Optional[str] = None
    
    @field_validator('SUPABASE_URL')
    @classmethod
    def validate_supabase_url(cls, v: str) -> str:
        """Validate SUPABASE_URL format"""
        if not v or not v.strip():
            raise ValueError(
                "SUPABASE_URL is empty. Please set it in your .env file. "
                "Format: https://your-project.supabase.co"
            )
        v = v.strip()
        if not v.startswith('http://') and not v.startswith('https://'):
            raise ValueError(
                f"SUPABASE_URL must start with http:// or https://. Got: {v[:20]}..."
            )
        return v
    
    @field_validator('SUPABASE_SERVICE_ROLE_KEY')
    @classmethod
    def validate_supabase_key(cls, v: str) -> str:
        """Validate SUPABASE_SERVICE_ROLE_KEY is not empty"""
        if not v or not v.strip():
            raise ValueError(
                "SUPABASE_SERVICE_ROLE_KEY is empty. Please set it in your .env file."
            )
        return v.strip()
    
    class Config:
        env_file = str(ENV_FILE)
        case_sensitive = True
        extra = "ignore"  # Ignore extra fields in .env


# Global settings instance
try:
    settings = Settings()
except Exception as e:
    import sys
    print(f"\n❌ Configuration Error: {e}\n", file=sys.stderr)
    print(f"Please check your .env file at: {ENV_FILE}", file=sys.stderr)
    print("Required variables:", file=sys.stderr)
    print("  - SUPABASE_URL (e.g., https://your-project.supabase.co)", file=sys.stderr)
    print("  - SUPABASE_SERVICE_ROLE_KEY", file=sys.stderr)
    print("  - SPEECHMATICS_API_KEY (or DEEPGRAM_API_KEY for batch)", file=sys.stderr)
    print("  - OPENROUTER_API_KEY", file=sys.stderr)
    sys.exit(1)


