"""
Application configuration from environment variables
"""

import os
from pydantic_settings import BaseSettings
from typing import Optional
from pathlib import Path

# Calculate the path to the root .env file
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
ENV_FILE = ROOT_DIR / ".env"

class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # AI Services
    DEEPGRAM_API_KEY: str
    SPEECHMATICS_API_KEY: Optional[str] = None
    OPENROUTER_API_KEY: str
    EXTRACTION_MODEL: str = "openai/gpt-5-mini"
    
    # Supabase
    SUPABASE_URL: str
    SUPABASE_SERVICE_ROLE_KEY: str
    
    # Application
    ENVIRONMENT: str = "development"
    FRONTEND_URL: str = "http://localhost:5173"
    
    class Config:
        env_file = str(ENV_FILE)
        case_sensitive = True
        extra = "ignore"  # Ignore extra fields in .env


# Global settings instance
settings = Settings()


