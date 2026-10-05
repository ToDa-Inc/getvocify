"""
Application configuration from environment variables
"""

import json
import os
import tempfile
from datetime import date
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
    DEEPGRAM_API_KEY: Optional[str] = None
    SPEECHMATICS_API_KEY: Optional[str] = None
    # File STT (HubSpot recordings, uploads, WhatsApp). Live copilot stays Speechmatics WS.
    STT_PROVIDER: str = "deepgram"
    # Realtime language when the client sends `multi`. Must be an ISO code (`es`, `en`, …).
    # `auto` is batch-only — eu2 rejects wss://…/v2/auto with HTTP 404.
    SPEECHMATICS_RT_LANGUAGE: Optional[str] = None
    # Live calls also stream to the other provider (Speechmatics or Deepgram) in parallel; both
    # transcripts and their speed go to the logs to compare.
    LIVE_COMPARE_STT: bool = False
    # Tries one provider (speechmatics, deepgram, mai) on every live call instead of the profile's rule.
    LIVE_STT_PROVIDER: Optional[str] = None
    # Vercel AI Gateway: MAI-Transcribe-2-Streaming for live calls.
    AI_GATEWAY_API_KEY: Optional[str] = None

    # LLM provider routing: openrouter | vertex_ai
    LLM_PROVIDER: str = "openrouter"
    OPENROUTER_API_KEY: Optional[str] = None
    # CRM note, field extraction, fill/update decisions, transcript repair.
    # Not used for live copilot (COPILOT_MODEL) or the STT engine.
    EXTRACTION_MODEL: str = "google/gemini-3.5-flash-lite"
    # Live call objection copilot (OpenRouter chat; abortable stream)
    # Note: gemini-3.6-flash has mandatory reasoning (~4s TTFT) — too slow for live coaching.
    # Gemini Live (3.1 Flash Live) is Google Live API only (not OpenRouter) and needs AI Studio key.
    # DeepSeek V4.1 Flash thinks by default (~540 hidden tokens); suggest.py turns that off.
    COPILOT_MODEL: str = "deepseek/deepseek-v4.1-flash"
    # Live help's reasoning effort. Empty means "minimal" (Gemini Flash-Lite refuses "none");
    # "none" for models that think before their first word even at "minimal" (GPT-6 Luna).
    COPILOT_REASONING_EFFORT: Optional[str] = None
    # OpenRouter provider pinned for COPILOT_MODEL (e.g. "Cerebras"); unset, OpenRouter picks the fastest.
    COPILOT_PROVIDER: Optional[str] = None
    # Live help's line from an OpenAI-compatible provider directly (e.g. Together), with OpenRouter
    # (COPILOT_MODEL) as the backup: it starts when the direct one has not written in COPILOT_HEDGE_MS, or fails.
    COPILOT_DIRECT_URL: Optional[str] = None
    COPILOT_DIRECT_API_KEY: Optional[str] = None
    COPILOT_DIRECT_MODEL: Optional[str] = None
    COPILOT_HEDGE_MS: int = 600
    # WhatsApp CRM copilot (tool loop). Not the live-call lite model.
    CRM_COPILOT_MODEL: str = "google/gemini-3.8-flash"
    CRM_COPILOT_MAX_ROUNDS: int = 8
    # Ask (web + WhatsApp): team metrics, conversations, objections, priorities and Pipedrive reads.
    ASK_VOCIFY_DATA_TOOLS_ENABLED: bool = False
    # Team view: weekly playbook adherence per rep (GET /team/adherence/trend). Owner/admin only.
    TEAM_ADHERENCE_TREND_ENABLED: bool = False
    # Team view: named competitor mentions in objections card and team weekly report. Owner/admin only.
    TEAM_COMPETITORS_ENABLED: bool = False
    # Web Ask: «¿a quién llamo hoy?» returns the priority contacts with a Call action. Needs the data tools.
    ASK_CALL_ACTIONS_ENABLED: bool = False
    # Web Ask keeps going until the question is answered; the last round is always a plain answer.
    ASK_MAX_ROUNDS: int = 32
    # Effort per question (crm_copilot/effort.py): lookups run at low, analysis at high. Off means always low.
    ASK_EFFORT_ROUTING: bool = True
    # Web Ask only (see crm_copilot/model_profile.py). Empty ASK_MODEL means CRM_COPILOT_MODEL; the fallback runs
    # once if the first call fails. DeepSeek V4.1 Flash runs with low-effort reasoning (model_profile).
    ASK_MODEL: Optional[str] = "deepseek/deepseek-v4.1-flash"
    ASK_FALLBACK_MODEL: Optional[str] = "google/gemini-3.8-flash"
    # Cheap second pass after deterministic name repair. Not the CRM extractor.
    TRANSCRIPT_SANITIZE_LLM: bool = True
    TRANSCRIPT_SANITIZE_MODEL: str = "google/gemini-3.5-flash-lite"
    # After file STT, pick one of the user's selected languages. Lite is enough.
    STT_LANGUAGE_DETECT_MODEL: str = "google/gemini-3.5-flash-lite"

    # Fast System One structured classification (CRM enums, language triage)
    USE_JEV_CLASSIFIER: bool = True
    JEV_MODEL: str = "typesafe/jev-1.13"
    JEV_TIMEOUT_SEC: float = 4.0

    # Vertex AI (enterprise path: ISO 27001 + SOC 2, Madrid region)
    GOOGLE_CLOUD_PROJECT: str = "pro-sylph-501508-g5"
    GOOGLE_CLOUD_LOCATION: str = "europe-southwest1"
    VERTEX_AI_MODEL: str = "gemini-2.5-flash"

    @field_validator("STT_PROVIDER")
    @classmethod
    def validate_stt_provider(cls, v: str) -> str:
        allowed = {"deepgram", "speechmatics"}
        normalized = (v or "deepgram").strip().lower()
        if normalized not in allowed:
            raise ValueError(
                f"STT_PROVIDER must be one of {sorted(allowed)}, got {v!r}"
            )
        return normalized

    @field_validator("DEEPGRAM_API_KEY")
    @classmethod
    def strip_deepgram_key(cls, v: Optional[str]) -> Optional[str]:
        if v is None or not v:
            return None
        return v.strip().strip('"').strip("'")

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
    # Project Settings > API > JWT Secret. REQUIRED: app.api.auth.validate_startup_config
    # refuses to start without it. deps.get_user_id verifies access JWTs locally
    # with this secret (signature + expiry) so a GoTrue blip is not a logout.
    SUPABASE_JWT_SECRET: Optional[str] = None
    
    # Application
    ENVIRONMENT: str = "development"
    FRONTEND_URL: str = "http://localhost:5173"
    RESEND_API_KEY: Optional[str] = None
    RESEND_FROM_EMAIL: Optional[str] = None
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
    # Never write to HubSpot from this backend (staging on a customer's real portal):
    # app/services/hubspot/read_only.py answers every non-read request with a 423.
    HUBSPOT_READ_ONLY: bool = False
    HUBSPOT_APP_ID: Optional[str] = None

    # Salesforce Connected App (OAuth Web Server flow)
    SALESFORCE_CLIENT_ID: Optional[str] = None
    SALESFORCE_CLIENT_SECRET: Optional[str] = None
    SALESFORCE_REDIRECT_URI: Optional[str] = None
    # login.salesforce.com (prod) or test.salesforce.com (sandbox)
    SALESFORCE_LOGIN_BASE: str = "https://login.salesforce.com"

    # Pipedrive Marketplace app (OAuth)
    PIPEDRIVE_CLIENT_ID: Optional[str] = None
    PIPEDRIVE_CLIENT_SECRET: Optional[str] = None
    PIPEDRIVE_REDIRECT_URI: Optional[str] = None

    # JWT secret for signing the HubSpot/Salesforce/Pipedrive OAuth "state" param
    # (prevents CSRF and, more importantly, prevents forging a state that
    # names a different user_id - see validate_startup_config below).
    # REQUIRED despite the type hint: validate_startup_config refuses to
    # start the app without a real value.
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

    # Twilio outbound calling. Caller ID is always the user's own verified
    # number, so no Twilio number is rented and no regulatory bundle applies.
    TWILIO_ACCOUNT_SID: Optional[str] = None
    TWILIO_AUTH_TOKEN: Optional[str] = None
    TWILIO_API_KEY_SID: Optional[str] = None
    TWILIO_API_KEY_SECRET: Optional[str] = None
    TWILIO_TWIML_APP_SID: Optional[str] = None
    # Ireland (IE1) accounts must hit api.{edge}.{region}.twilio.com.
    # US1 is the SDK default when both are unset.
    TWILIO_EDGE: Optional[str] = None
    TWILIO_REGION: Optional[str] = None
    # AEPD Circular 1/2023: the prospect must be told at the start of the call
    # that it is being recorded, and why. Played to the called party only.
    TWILIO_RECORDING_ANNOUNCEMENT: Optional[str] = None
    TWILIO_ANNOUNCEMENT_LANGUAGE: str = "es-ES"
    # Default country code for national numbers coming from CRM contact fields.
    CALLING_DEFAULT_COUNTRY_CODE: str = "34"
    # Play the AEPD recording disclosure to the called party before bridging.
    # Off by default; flip on per environment. The whisper route stays mounted.
    CALLING_RECORDING_ANNOUNCEMENT_ENABLED: bool = False
    # Spain: Orden TDF/149/2025 art. 9 bars +34 6/7 mobiles for commercial
    # calls; +34 400 cannot receive the verification call. Global because it is
    # law for every tenant, not a plan feature. See docs/telephony/DECISION.md.
    CALLING_ES_CLI_GATE_ENABLED: bool = True
    # Already-verified Spanish mobiles stop dialing from this Europe/Madrid date
    # (Resolución SETID 14-04-2026, apartado sexto).
    CALLING_ES_MOBILE_CALL_BLOCK_FROM: date = date(2026, 10, 17)
    # Lifetime of the signed recording URL handed to HubSpot.
    CALL_RECORDING_URL_TTL_SECONDS: int = 3600
    # Follow-up drafts; overridable per company (company_feature_flags). Off does not block
    # extraction; sent means mail-client handoff.
    FOLLOWUP_ENABLED: bool = True
    # Daily report email, per company. The report is still generated and listed in the bell when off.
    REPORTING_DAILY_EMAIL_ENABLED: bool = False
    # Deal stage chosen by the rep on memo review; accepting a meeting no longer moves it. Per company.
    DEAL_STAGE_CONFIRM_ENABLED: bool = False
    # CRM tasks from C04 commitments, with Hoy's text and due date. Per company.
    COMMITMENT_TASKS_ENABLED: bool = False
    # Reports (F13.04 / F15.05), per company. Weekly personal report, Friday 18:00 local.
    REPORTING_WEEKLY_ENABLED: bool = False
    # Weekly team report by email for owner/admin, from the same aggregate as the team panel.
    REPORTING_TEAM_ENABLED: bool = False
    # Bell also lists what Vocify did on its own (CRM writes, meeting stage moves) and why.
    NOTIFICATIONS_ACTIVITY_ENABLED: bool = False
    INTELLIGENCE_WORKER_PUBLISH: bool = False
    # Interest, objections and commitments from the transcript, once per extraction.
    INTELLIGENCE_EXTRACT_ENABLED: bool = False
    # C04 v4: named competitors + one observation per playbook step (coaching, adherence,
    # missed steps, checklist). Per company via company_feature_flags; off until its evals pass.
    PLAYBOOK_OBSERVATIONS_ENABLED: bool = False
    # Hoy card «no te ha respondido»: reads the rep's CRM emails. HubSpot needs sales-email-read.
    HOY_NO_REPLY_ENABLED: bool = False
    # One-click confirm in Hoy after CRM auto-approve (stage and/or meeting). Per company.
    HOY_CONFIRMATIONS_ENABLED: bool = False
    # Accepted F14 meetings with starts_at today in Hoy. Per company.
    HOY_MEETINGS_ENABLED: bool = False
    # Rep workspace (F16): /dashboard becomes the rep's home. Per company.
    REP_WORKSPACE_ENABLED: bool = False
    # Pre-call brief v2: hook, why, say and playbook progress label from C04. Per company.
    BRIEF_V2_ENABLED: bool = False
    # Lista 3 (roles, flujos SDR/AE y Head of Sales). All per company, off by default.
    # T1: company_members.sales_role/handoff_ae_user_id/visibility, exposed via /company and /auth/me.
    SALES_ROLES_ENABLED: bool = False
    # The AI tags a memo `internal` when extraction reports customerPresent=false. Per company,
    # off until real transcripts are checked; a manual retag to `internal` works either way.
    INTERNAL_DETECTION_ENABLED: bool = False
    # T3: SDR->AE handoff on meeting booked (deal_handoffs).
    HANDOFF_ENABLED: bool = False
    # T3: writes the CRM owner (deal/contact) to the AE on handoff.
    HANDOFF_CRM_OWNER_ENABLED: bool = False
    # T5: Hoy lead tiers (callback_no_answer, stale_hot, never_contacted) and heat score.
    HOY_LEAD_TIERS_ENABLED: bool = False
    # T6: Hoy AE section (deals in progress) with pre-meeting brief.
    HOY_AE_DEALS_ENABLED: bool = False
    # T8: follow-up sent from Vocify via Resend instead of mailto.
    FOLLOWUP_SEND_ENABLED: bool = False
    # T8: follow-up instructions tailored per flow (discovery/closing) plus sales_strategy.
    FOLLOWUP_BY_FLOW_ENABLED: bool = False
    # T9: Head of Sales onboarding wizard on first login.
    ONBOARDING_WIZARD_ENABLED: bool = False
    # T10: scoring credit for objections handled (objection_handling criterion).
    SCORING_OBJECTION_CREDIT_ENABLED: bool = False
    # T10: debrief v2 (flow, missed steps, phrases, highlights, progress).
    DEBRIEF_V2_ENABLED: bool = False
    # Coaching v1: one-line coaching message (focus) in the rep's own daily/weekly reports.
    COACHING_MESSAGES_ENABLED: bool = False
    # T11: Playbook tab with the week's best interactions per flow.
    PLAYBOOK_TAB_ENABLED: bool = False
    # T12: daily/weekly reports split by sales_role section.
    REPORTING_BY_FLOW_ENABLED: bool = False
    # T12: bell adds tasks (Hoy) and feedback (ready briefs) sections.
    BELL_TASKS_ENABLED: bool = False
    # T13: /dashboard becomes the Head of Sales' team home.
    MANAGER_HOME_ENABLED: bool = False
    # T14: Recall.ai meeting bot (needs RECALL_API_KEY).
    RECALL_BOT_ENABLED: bool = False
    # Lista 4 T2: SDR's Hoy in Tareas/Seguimiento/Nuevos, follow-ups on a cadence per stopper.
    HOY_SDR_SECTIONS_ENABLED: bool = False
    # Lista 4 T3: the brief adds a «gancho de empresa» line from another contact of the same company.
    BRIEF_COMPANY_HOOK_ENABLED: bool = False
    # Lista 4 T4: after the call, Hoy's panel walks proposal -> outcome -> follow-up -> next,
    # and the company's deal_creation_rule decides when a contact without a deal gets one.
    AFTER_CALL_FLOW_ENABLED: bool = False
    # Playbooks v2, per company. V2: the new list/document/single-box UI. ROUTING: the call-type
    # catalog, the "when it applies" rules, rule-based pinning and "change type" on a recording.
    PLAYBOOK_V2_ENABLED: bool = False
    PLAYBOOK_ROUTING_ENABLED: bool = False
    # Playbooks v2, per company. QUALIFICATION: C04 v7 reads "what has to come out of the call"
    # criteria and the company's own objections, and the score is built from three blocks
    # (steps, qualification, objections) instead of steps alone.
    PLAYBOOK_QUALIFICATION_ENABLED: bool = False
    # Recall.ai dashboard > API keys. Unset -> POST /meetings/bot returns 503.
    RECALL_API_KEY: Optional[str] = None
    # Recall's per-region API host (https://{region}.recall.ai). Our workspace is in the EU
    # region (Frankfurt); regions are separate accounts, so the key only works there.
    RECALL_REGION: str = "eu-central-1"
    # Recall webhook signing secret (Svix-style, prefixed "whsec_"), from the Recall
    # dashboard's webhook settings. Unset -> POST /webhooks/recall accepts unsigned
    # requests with a warning (dev only), same as UNIPILE_WEBHOOK_SECRET.
    RECALL_WEBHOOK_SECRET: Optional[str] = None
    # OAuth clients for connecting a rep's calendar (Recall Calendar V2). Our own apps: the
    # refresh token is handed to Recall, which keeps the calendar synced. Unset -> that
    # provider is not offered. Redirect URI: {BACKEND_PUBLIC_URL}/api/v1/calendar/{provider}/callback
    GOOGLE_CALENDAR_CLIENT_ID: Optional[str] = None
    GOOGLE_CALENDAR_CLIENT_SECRET: Optional[str] = None
    MICROSOFT_CALENDAR_CLIENT_ID: Optional[str] = None
    MICROSOFT_CALENDAR_CLIENT_SECRET: Optional[str] = None
    INTELLIGENCE_MODEL: str = "google/gemini-3.8-flash"
    # Output cap on every OpenRouter call (see providers/openrouter.py). A long call reading
    # (every rep turn listed) plus a v8 verdict stays well under it.
    LLM_MAX_OUTPUT_TOKENS: int = 16000
    # C04 v8: how much each pass may reason ("low" | "medium" | "high"; None = the model's
    # default). Reasoning tokens are most of a Gemini call's cost.
    INTELLIGENCE_READING_EFFORT: Optional[str] = None
    INTELLIGENCE_JUDGE_EFFORT: Optional[str] = None
    # Step 1 (CRM note and fields): how much the model reasons before writing. None = the model's
    # default. A reasoning model left at its default makes the rep wait for the note.
    EXTRACTION_REASONING_EFFORT: Optional[str] = None
    # None used to fall through to EXTRACTION_MODEL (lite). Follow-ups need the CRM model.
    FOLLOWUP_MODEL: Optional[str] = "google/gemini-3.8-flash"

    CALLING_PROVIDER: str = "twilio"
    TELNYX_API_KEY: Optional[str] = None
    TELNYX_PUBLIC_KEY: Optional[str] = None
    TELNYX_CONNECTION_ID: Optional[str] = None
    TELNYX_CALL_CONTROL_APP_ID: Optional[str] = None
    TELNYX_OUTBOUND_VOICE_PROFILE_ID: Optional[str] = None
    # Public WAV Telnyx fetches for parked-leg ringback. Defaults to
    # `{BACKEND_PUBLIC_URL}/static/call-ringback.wav`.
    TELNYX_RINGBACK_URL: Optional[str] = None
    # Hang parked ringback if PSTN never bridges. 0 disables (tests).
    TELNYX_RING_WATCHDOG_SECS: int = 35

    # Unipile (optional - for WhatsApp via Unipile instead of Meta)
    UNIPILE_API_KEY: Optional[str] = None
    UNIPILE_BASE_URL: str = "https://api23.unipile.com:15349"
    # Per-webhook secret from the Unipile dashboard (Webhooks > your endpoint) or
    # the "GET webhook" API response. Verifies the `unipile-signature` header so
    # only genuine Unipile events are processed - without it, anyone who finds
    # the webhook URL can POST fake WhatsApp messages.
    UNIPILE_WEBHOOK_SECRET: Optional[str] = None

    # Cost ledger (usage_events). STT is billed by audio time, so cost = seconds x rate.
    # Rates are list prices (speechmatics.com/pricing); override here if the contract differs.
    # A provider/mode with no rate is recorded unpriced (NULL), never guessed.
    USAGE_LEDGER_ENABLED: bool = True
    STT_RATE_SPEECHMATICS_REALTIME_ENHANCED_USD_HR: Optional[float] = 0.43
    STT_RATE_SPEECHMATICS_REALTIME_STANDARD_USD_HR: Optional[float] = 0.24
    STT_RATE_SPEECHMATICS_BATCH_ENHANCED_USD_HR: Optional[float] = 0.40
    STT_RATE_SPEECHMATICS_BATCH_STANDARD_USD_HR: Optional[float] = 0.24
    STT_RATE_DEEPGRAM_BATCH_USD_HR: Optional[float] = None
    # Unverified whether Speechmatics bills each channel of a multi-channel session separately.
    STT_BILL_PER_CHANNEL: bool = False

    # Metrics (optional - required for Grafana Cloud Metrics Endpoint integration)
    METRICS_TOKEN: Optional[str] = None  # Bearer token; if set, /metrics requires Authorization

    # Error tracking (optional - app runs without it, just with no alerting).
    # Get a DSN free at sentry.io (new project > Python > FastAPI).
    SENTRY_DSN: Optional[str] = None
    SENTRY_TRACES_SAMPLE_RATE: float = 0.1

    # Internal admin console. Unset = admin routes return 503; app still boots.
    MASTER_KEY: Optional[str] = None

    # Stripe workspace billing (optional — app boots without it; checkout returns 503).
    STRIPE_SECRET_KEY: Optional[str] = None
    STRIPE_PUBLISHABLE_KEY: Optional[str] = None
    STRIPE_WEBHOOK_SECRET: Optional[str] = None
    STRIPE_PRICE_STARTER_MONTHLY: Optional[str] = None
    STRIPE_PRICE_PRO_MONTHLY: Optional[str] = None
    STRIPE_PRICE_STARTER_YEARLY: Optional[str] = None
    STRIPE_PRICE_PRO_YEARLY: Optional[str] = None
    
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


# Known-insecure placeholder from .env.example. This repo is public, so this
# exact string is public too - if it's ever live in a real deployment, JWT_SECRET
# provides no security at all. See validate_startup_config below.
_INSECURE_JWT_SECRET_PLACEHOLDER = "your-super-secret-key-change-in-production"


def validate_startup_config() -> None:
    """
    Fail the app's boot, not a user's OAuth connect click, if JWT_SECRET is
    missing or still the publicly-known placeholder. Same pattern as
    app.services.crm_updates.validate_startup_config and
    app.api.auth.validate_startup_config - call from app.main's startup_event
    before the app is marked ready for traffic.

    JWT_SECRET signs the OAuth "state" param for the HubSpot, Salesforce,
    and Pipedrive connect flows (hubspot/oauth.py, salesforce/oauth.py,
    pipedrive/oauth.py).
    That state carries a user_id, and the callback trusts it to decide whose
    crm_connections row to overwrite with the tokens from whatever CRM account
    just completed the OAuth consent screen. Anyone who knows this secret can
    forge a state for an arbitrary user_id, connect their own CRM account
    through the real consent flow, and have our callback silently store their
    tokens under someone else's account - every future sync for that victim
    would then write into the attacker's CRM instead of the victim's.
    """
    if not settings.JWT_SECRET:
        raise RuntimeError(
            "JWT_SECRET is not configured. It signs the OAuth 'state' param for "
            "HubSpot/Salesforce/Pipedrive connect flows - without it, that state can't be "
            "trusted, and every CRM connect attempt will fail anyway (see "
            "oauth_enabled() in hubspot/oauth.py, salesforce/oauth.py, pipedrive/oauth.py). "
            "Set it to a random value, e.g. `openssl rand -hex 32`. Refusing to start."
        )
    if settings.JWT_SECRET.strip() == _INSECURE_JWT_SECRET_PLACEHOLDER:
        raise RuntimeError(
            "JWT_SECRET is set to the placeholder value documented in "
            ".env.example. This repo is public, so that value is public too - "
            "it provides no security. Generate a real secret, e.g. "
            "`openssl rand -hex 32`. Refusing to start."
        )


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


