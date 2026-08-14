"""
FastAPI application entry point
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.webhook_context import set_correlation_id, get_correlation_id
from app.config import settings
from app.api.router import api_router
from app.logging_config import configure_logging
from app.rate_limit import limiter, RATE_LIMITING_ENABLED
import asyncio

# Configure logging first for full backend visibility
configure_logging(
    level=settings.LOG_LEVEL,
    json_format=settings.LOG_JSON,
)

# Error tracking (optional - no-op if SENTRY_DSN isn't set, or if the package
# isn't installed). Without this, the only way to learn about a production
# failure is a customer complaint or manually grepping logs.
if settings.SENTRY_DSN:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration

        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            environment=settings.ENVIRONMENT,
            integrations=[
                StarletteIntegration(),
                FastApiIntegration(),
                LoggingIntegration(level=logging.WARNING, event_level=logging.ERROR),
            ],
            traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
            # Voice memo transcripts/CRM data are sensitive - never attach request bodies/PII
            send_default_pii=False,
        )
        logging.getLogger(__name__).info("Sentry error tracking initialized (env=%s)", settings.ENVIRONMENT)
    except ImportError:
        logging.getLogger(__name__).warning("SENTRY_DSN set but sentry-sdk not installed; skipping")


class TimeoutMiddleware(BaseHTTPMiddleware):
    """
    Middleware to add request timeouts.
    
    - 90s for /approve (full HubSpot sync: company, contact, deal, associations)
    - No timeout: transcription, upload, re-extract, webhooks
    - 30s for all other endpoints
    """
    
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        
        # Skip timeout for transcription, upload, upload-transcript, re-extract, webhooks, metrics
        if (
            "/transcription" in path
            or "/copilot" in path
            or "/memos/upload" in path
            or "/upload-transcript" in path
            or "/re-extract" in path
            or "/webhooks" in path
            or path == "/metrics"
        ):
            return await call_next(request)
        
        # 90s for approve (HubSpot sync can be slow: schema, search, create/update)
        timeout = 90.0 if "/approve" in path else 30.0
        
        try:
            response = await asyncio.wait_for(call_next(request), timeout=timeout)
            return response
        except asyncio.TimeoutError:
            return JSONResponse(
                status_code=504,
                content={"detail": f"Request timeout after {int(timeout)}s"}
            )


app = FastAPI(
    title="Vocify API",
    description="Voice to CRM in 60 seconds",
    version="0.1.0",
)

# Rate limiting (login/signup/refresh - see app/rate_limit.py). No-op if slowapi
# isn't installed.
app.state.limiter = limiter
if RATE_LIMITING_ENABLED:
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Correlation ID middleware - propagate X-Request-ID or generate one for all requests
class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        import uuid
        cid = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:12]}"
        set_correlation_id(cid)
        # Also store on request.state (backed by the shared ASGI scope, not a
        # contextvar): BaseHTTPMiddleware runs call_next in a separate anyio
        # task, so a truly unhandled exception bubbles up and gets handled by
        # ServerErrorMiddleware back in the *parent* task, where the contextvar
        # set above was never visible. request.state survives that boundary.
        request.state.correlation_id = cid
        response = await call_next(request)
        response.headers["X-Request-ID"] = cid
        return response


class MetricsAuthMiddleware(BaseHTTPMiddleware):
    """
    Optional Bearer auth for /metrics. Required for Grafana Cloud Metrics Endpoint
    (which mandates auth). If METRICS_TOKEN is set, requests without valid token get 401.
    """
    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/metrics" and settings.METRICS_TOKEN:
            auth = request.headers.get("Authorization") or ""
            expected = f"Bearer {settings.METRICS_TOKEN}"
            if auth.strip() != expected:
                return Response(status_code=401, content="Unauthorized")
        return await call_next(request)


app.add_middleware(MetricsAuthMiddleware)
app.add_middleware(CorrelationIdMiddleware)
# Timeout middleware (30s for most endpoints, except transcription/upload)
app.add_middleware(TimeoutMiddleware)

# CORS middleware
_frontend_url = settings.FRONTEND_URL.rstrip("/")
_cors_origins = [
    _frontend_url,
    "http://localhost:5173",
    "http://localhost:8080",
    "http://localhost:8081",
    "http://localhost:3000",
    # Production
    "https://getvocify.com",
    "https://www.getvocify.com",
    "https://app.getvocify.com",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o for o in _cors_origins if o],  # drop empty strings
    allow_origin_regex=r"chrome-extension://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """
    Last-resort handler for anything that isn't an HTTPException.

    Without this, FastAPI's default handling still returns a generic 500 but
    drops the X-Request-ID header (CorrelationIdMiddleware never gets to set it
    because the exception skips the rest of its dispatch) - exactly the
    requests support most needs to correlate with backend logs. This also
    guarantees Sentry (when configured) sees every unhandled exception even if
    something upstream already touched the response.
    """
    cid = getattr(request.state, "correlation_id", None) or get_correlation_id()
    logger = logging.getLogger("app.unhandled_exception")
    logger.exception(
        "Unhandled exception in %s %s",
        request.method,
        request.url.path,
        extra={"correlation_id": cid, "path": request.url.path, "method": request.method},
    )
    if settings.SENTRY_DSN:
        try:
            import sentry_sdk
            sentry_sdk.capture_exception(exc)
        except ImportError:
            pass
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "request_id": cid},
        headers={"X-Request-ID": cid} if cid else None,
    )


# Include API routes
app.include_router(api_router)

# Prometheus metrics (optional - app runs without it if package missing)
try:
    from prometheus_fastapi_instrumentator import Instrumentator
    Instrumentator().instrument(app).expose(app)
except ImportError:
    pass  # Run without metrics if package not installed


async def _refresh_crm_updates_stale_pending_gauge():
    """
    Every 5 minutes, count crm_updates rows still 'pending' past their TTL
    and publish it as a gauge. Runs forever in the background - errors are
    swallowed per-iteration (metrics.set_crm_updates_stale_pending already
    does this too) so a transient DB hiccup doesn't kill the loop or the app.
    """
    from app.deps import get_supabase
    from app.metrics import set_crm_updates_stale_pending
    from app.services.crm_updates import CRMUpdatesService

    logger = logging.getLogger(__name__)
    supabase = get_supabase()
    crm_updates_service = CRMUpdatesService(supabase)
    while True:
        try:
            count = await crm_updates_service.count_stale_pending()
            set_crm_updates_stale_pending(count)
            if count > 0:
                # ERROR, not WARNING: Sentry's LoggingIntegration here is
                # configured with event_level=logging.ERROR (see the
                # sentry_sdk.init call above) - only ERROR+ becomes an
                # actual Sentry issue, WARNING only attaches as a breadcrumb
                # nobody sees unless another event fires first. This is
                # currently the ONLY place this gauge is "consulted" in
                # practice: there's no Grafana/Railway dashboard wired to
                # the raw /metrics endpoint (prometheus_fastapi_instrumentator
                # only exposes it for scraping, nothing scrapes it today).
                # If Grafana/Railway metrics ever get set up, this can drop
                # back to a plain gauge-only signal.
                logger.error(
                    "⏳ crm_updates has stale pending rows past TTL",
                    extra={"domain": "crm_updates", "phase": "stale_pending_check", "count": count},
                )
        except Exception as e:
            logger.exception(
                "❌ Failed to refresh crm_updates stale pending gauge",
                extra={"domain": "crm_updates", "phase": "stale_pending_check", "error": str(e)},
            )
        await asyncio.sleep(5 * 60)


@app.on_event("startup")
async def startup_event():
    """
    Startup event handler.
    Recovers stuck memo processing tasks on server startup, and starts the
    periodic crm_updates stale-pending gauge refresh.
    """
    logger = logging.getLogger(__name__)

    # Deliberately NOT inside the try/except below: misconfiguration of
    # either of these must fail the deploy at boot (visible in Railway's
    # deploy logs, no traffic served) rather than surface later as a 500 on
    # whichever real request hits it first, or worse - a security check that
    # silently degrades.
    # - CRM_UPDATES_LEGACY_PENDING_CUTOFF: see CRMUpdatesService.
    #   is_action_already_done's "WHERE this fires" note for the reasoning.
    # - SUPABASE_JWT_SECRET: gates whether /auth/refresh can verify a token
    #   before using it to decide whose session to touch. See auth.py's
    #   refresh_token docstring.
    # - JWT_SECRET: signs the HubSpot/Salesforce OAuth "state" param. See
    #   config.py's validate_startup_config docstring.
    from app.services.crm_updates import validate_startup_config
    validate_startup_config()

    from app.api.auth import validate_startup_config as validate_auth_startup_config
    validate_auth_startup_config()

    from app.config import validate_startup_config as validate_jwt_secret_config
    validate_jwt_secret_config()

    try:
        from app.deps import get_supabase
        from app.services.recovery import RecoveryService

        supabase = get_supabase()
        recovery_service = RecoveryService(supabase)
        result = await recovery_service.recover_all_stuck_memos()

        if result["found"] > 0:
            logger.info(
                "🔄 Startup recovery complete",
                extra={
                    "domain": "recovery",
                    "phase": "startup",
                    "found": result["found"],
                    "recovered": result["recovered"],
                },
            )
    except Exception as e:
        logger.exception(
            "❌ Startup recovery failed",
            extra={"domain": "recovery", "phase": "startup", "error": str(e)},
        )

    asyncio.create_task(_refresh_crm_updates_stale_pending_gauge())


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "Vocify API",
        "version": "0.1.0",
        "status": "running"
    }


