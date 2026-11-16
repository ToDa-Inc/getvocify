"""The desktop app's log, sent by the app itself so a rep never has to copy anything: on start (which carries what
happened before a freeze or crash) and every 30 minutes. One file per rep and platform, replaced each time, in a
private bucket only Vocify reads."""

from __future__ import annotations

import asyncio
import logging
from typing import Literal

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from supabase import Client

from app.deps import get_supabase, get_user_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/desktop", tags=["desktop"])

DESKTOP_LOGS_BUCKET = "desktop-logs"
MAX_LOG_CHARS = 512 * 1024


class DesktopLog(BaseModel):
    platform: Literal["win32", "darwin"]
    version: str = Field(..., max_length=40)
    log: str = Field(..., max_length=MAX_LOG_CHARS)


@router.post("/diagnostics", status_code=status.HTTP_204_NO_CONTENT)
async def save_desktop_log(
    body: DesktopLog,
    user_id: str = Depends(get_user_id),
    supabase: Client = Depends(get_supabase),
) -> None:
    head = f"# Vocify {body.version} ({body.platform}), user {user_id}\n"
    try:
        await asyncio.to_thread(
            supabase.storage.from_(DESKTOP_LOGS_BUCKET).upload,
            path=f"{user_id}/{body.platform}.log",
            file=(head + body.log).encode("utf-8"),
            file_options={"content-type": "text/plain; charset=utf-8", "upsert": "true"},
        )
    except Exception:
        # The app tries again on its next send; a failed upload never bothers the rep.
        logger.exception("Desktop log for %s not stored", user_id)
