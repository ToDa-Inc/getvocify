"""
FastAPI application entry point
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.webhook_context import set_correlation_id
from app.config import settings
from app.api.router import api_router
from app.logging_config import configure_logging
import asyncio

# Configure logging first for full backend visibility
configure_logging(
    level=settings.LOG_LEVEL,
    json_format=settings.LOG_JSON,
)


class TimeoutMiddleware(BaseHTTPMiddleware):
    """
    Middleware to add request timeouts.
    
    - 90s for /approve (full HubSpot sync: company, contact, deal, associations)
    - No timeout: transcription, upload, re-extract, webhooks
    - 30s for all other endpoints
    """
    
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        
        # Skip timeout for transcription, upload, re-extract, webhooks, metrics (can run long or need fast response)
        if (
            "/transcription" in path
            or "/memos/upload" in path
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

# Correlation ID middleware - propagate X-Request-ID or generate one for all requests
class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        import uuid
        cid = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:12]}"
        set_correlation_id(cid)
        response = await call_next(request)
        response.headers["X-Request-ID"] = cid
        return response


app.add_middleware(CorrelationIdMiddleware)
# Timeout middleware (30s for most endpoints, except transcription/upload)
app.add_middleware(TimeoutMiddleware)

# CORS middleware (localhost + 127.0.0.1 - some browsers send different origin)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.FRONTEND_URL,
        "http://localhost:5173",
        "http://localhost:8080",
        "http://localhost:8081",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8080",
        "http://127.0.0.1:3000",
        # Chrome extension origins (any extension ID)
        "chrome-extension://*",
    ],
    allow_origin_regex=r"chrome-extension://.*|http://192\.168\.\d+\.\d+:\d+|http://127\.0\.0\.1:\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(api_router)

# Prometheus metrics (optional - app runs without it if package missing)
try:
    from prometheus_fastapi_instrumentator import Instrumentator
    Instrumentator().instrument(app).expose(app)
except ImportError:
    pass  # Run without metrics if package not installed


@app.on_event("startup")
async def startup_event():
    """
    Startup event handler.
    Recovers stuck memo processing tasks on server startup.
    """
    logger = logging.getLogger(__name__)
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


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "Vocify API",
        "version": "0.1.0",
        "status": "running"
    }


