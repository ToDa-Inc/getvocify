"""
The live transcription service: the same code as the API, serving only live call audio.

Run apart from the API (its own Railway service, `uvicorn app.live_main:app`) so nothing the
API does - dashboard pages, memo processing, background jobs, blocking database calls - can
ever pause the audio of a call in progress. It has no session of its own: clients authenticate
with a ticket from the API (POST /api/v1/transcription/ticket), sent as the first message.
"""

from fastapi import FastAPI

from app.config import settings
from app.logging_config import configure_logging
from app.observability import init_sentry

configure_logging(level=settings.LOG_LEVEL, json_format=settings.LOG_JSON)
init_sentry()

from app.api.transcription import live_router  # noqa: E402  (after logging is configured)

app = FastAPI(title="Vocify Live", description="Live call transcription", version="0.1.0")
app.include_router(live_router)


@app.on_event("startup")
async def startup_event() -> None:
    # Tickets are signed with JWT_SECRET: without it no call could start, so fail the deploy.
    from app.config import validate_startup_config

    validate_startup_config()


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "live"}
