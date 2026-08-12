"""
Application configuration from environment variables
"""

import json
import os
import tempfile
from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import Optional
from pathlib import Path

# Paths: project root and backend dir (backend runs with cwd=backend)
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
BACKEND_DIR = ROOT_DIR / "backend"
ENV_FILE = ROOT_DIR / ".env"
# On Railway: use ONLY env vars (ignore .env files). Local: load .env for dev.
_ON_RAILWAY = bool(os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("RAILWAY_SERVICE_NAME"))
ENV_FILES = [] if _ON_RAILWAY else [str(BACKEND_DIR / ".env"), str(ENV_FILE)]


def _bootstrap_gcp_credentials_from_env() -> None:
    """Write GOOGLE_APPLICATION_CREDENTIALS_JSON to a temp file for ADC (Railway)."""
    creds_json = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_JSON")
    if creds_json and not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        try:
            json.loads(creds_json)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"GOOGLE_APPLICATION_CREDENTIALS_JSON is not valid JSON: {e}"
            ) from e
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w") as f:
            f.write(creds_json)
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = path


_bootstrap_gcp_credentials_from_env()


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # AI Services
    DEEPGRAM_API_KEY: Optional[str] = None  # BACKLOG: Speechmatics only (real-time + batch)
    SPEECHMATICS_API_KEY: Optional[str] = None

    # LLM provider routing: openrouter | vertex_ai
    LLM_PROVIDER: str = "openrouter"
    OPENROUTER_API_KEY: Optional[str] = None
    EXTRACTION_MODEL: str = "x-ai/grok-4.1-fast"
    # Live call objection copilot (OpenRouter chat; abortable stream)
    # Note: gemini-3.6-flash has mandatory reasoning (~4s TTFT) — too slow for live coaching.
    # Gemini Live (3.1 Flash Live) is Google Live API only (not OpenRouter) and needs AI Studio key.
    COPILOT_MODEL: str = "google/gemini-2.5-flash-lite"

    # Vertex AI (enterprise path: ISO 27001 + SOC 2, Madrid region)
    GOOGLE_CLOUD_PROJECT: str = "pro-sylph-501508-g5"
    GOOGLE_CLOUD_LOCATION: str = "europe-southwest1"
    VERTEX_AI_MODEL: str = "gemini-2.5-flash"

    @field_validator("LLM_PROVIDER")
    @classmethod
    def validate_llm_provider(cls, v: str) -> str:
        allowed = {"openrouter", "vertex_ai"}
        normalized = (v or "").strip().lower()
        if normalized not in allowed:
            raise ValueError(
                f"LLM_PROVIDER must be one of {sorted(allowed)}, got {v!r}"
            )
        return normalized

    @field_validator("OPENROUTER_API_KEY")
    @classmethod
    def strip_openrouter_key(cls, v: Optional[str]) -> Optional[str]:
        """Strip whitespace and quotes that can break auth."""
        if v is None or not v:
            return None
        return v.strip().strip('"').strip("'")
    
    # Supabase
    SUPABASE_URL: str
    SUPABASE_SERVICE_ROLE_KEY: str
    # Anon/publishable key for Auth (login/refresh). Falls back to service role if unset.
    SUPABASE_ANON_KEY: Optional[str] = None
    # Project Settings > API > JWT Secret. Lets the backend verify the signature
    # of a Supabase-issued access token locally (e.g. to identify a user from an
    # already-expired token during the GoTrue refresh bypass) without trusting
    # unverified claims. Optional: falls back to unverified decode if unset, but
    # setting this closes a theoretical spoofing gap in that fallback path.
    SUPABASE_JWT_SECRET: Optional[str] = None
    
    # Application
    ENVIRONMENT: str = "development"
    FRONTEND_URL: str = "http://localhost:5173"
    # Public URL of this backend — used for Speechmatics callback notifications.
    # Set to https://api.getvocify.com in production, or your ngrok URL locally.
    BACKEND_PUBLIC_URL: str = "https://api.getvocify.com"

    # Logging (extensive visibility: logic, AI, LLM, Speechmatics, HubSpot)
    LOG_LEVEL: str = "INFO"  # DEBUG, INFO, WARNING, ERROR
    LOG_JSON: bool = False  # True for production log aggregators (Datadog, etc.)

    # HubSpot OAuth (required for OAuth flow; private app flow does not use these)
    HUBSPOT_CLIENT_ID: Optional[str] = None
    HUBSPOT_CLIENT_SECRET: Optional[str] = None
    HUBSPOT_REDIRECT_URI: Optional[str] = None

    # Salesforce Connected App (OAuth Web Server flow)
    SALESFORCE_CLIENT_ID: Optional[str] = None
    SALESFORCE_CLIENT_SECRET: Optional[str] = None
    SALESFORCE_REDIRECT_URI: Optional[str] = None
    # login.salesforce.com (prod) or test.salesforce.com (sandbox)
    SALESFORCE_LOGIN_BASE: str = "https://login.salesforce.com"

    # JWT secret for signing OAuth state (prevents CSRF)
    JWT_SECRET: Optional[str] = None

    # WhatsApp (optional - app runs without these)
    WHATSAPP_ACCESS_TOKEN: Optional[str] = None
    WHATSAPP_PHONE_NUMBER_ID: Optional[str] = None
    WHATSAPP_VERIFY_TOKEN: Optional[str] = None
    # Meta App Secret (App Dashboard > Settings > Basic). Used to verify the
    # X-Hub-Signature-256 header on incoming webhooks - without it, anyone who
    # discovers the webhook URL can POST fake WhatsApp messages that get
    # processed (fake CRM syncs, wasted LLM credits, spoofed sender numbers).
    WHATSAPP_APP_SECRET: Optional[str] = None

    # Unipile (optional - for WhatsApp via Unipile instead of Meta)
    UNIPILE_API_KEY: Optional[str] = None
    UNIPILE_BASE_URL: str = "https://api23.unipile.com:15349"
    # Per-webhook secret from the Unipile dashboard (Webhooks > your endpoint) or
    # the "GET webhook" API response. Verifies the `unipile-signature` header so
    # only genuine Unipile events are processed - without it, anyone who finds
    # the webhook URL can POST fake WhatsApp messages.
    UNIPILE_WEBHOOK_SECRET: Optional[str] = None

    # Metrics (optional - required for Grafana Cloud Metrics Endpoint integration)
    METRICS_TOKEN: Optional[str] = None  # Bearer token; if set, /metrics requires Authorization

    # Error tracking (optional - app runs without it, just with no alerting).
    # Get a DSN free at sentry.io (new project > Python > FastAPI).
    SENTRY_DSN: Optional[str] = None
    SENTRY_TRACES_SAMPLE_RATE: float = 0.1
    
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
        env_file = ENV_FILES
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
    print("  - SPEECHMATICS_API_KEY", file=sys.stderr)
    print("  - OPENROUTER_API_KEY (when LLM_PROVIDER=openrouter)", file=sys.stderr)
    sys.exit(1)


