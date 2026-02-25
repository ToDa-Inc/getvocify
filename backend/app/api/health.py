"""
Health check endpoint
"""

from fastapi import APIRouter, Depends
from app.deps import get_supabase
from app.config import settings
from app.services.recovery import RecoveryService
from supabase import Client

router = APIRouter()


@router.get("/health")
async def health_check():
    """Health check endpoint. openrouter_key shows if env is loaded (prefix only, safe to expose)."""
    key = getattr(settings, "OPENROUTER_API_KEY", None) or ""
    k = str(key).strip()
    return {
        "status": "ok",
        "service": "vocify-backend",
        "openrouter_key": f"{k[:12]}...len={len(k)}" if len(k) > 10 else "MISSING_OR_EMPTY",
    }


@router.post("/health/recover-stuck-memos")
async def recover_stuck_memos(
    supabase: Client = Depends(get_supabase),
):
    """
    Recover stuck memo processing tasks.
    
    Finds memos stuck in transcribing/extracting states for >5 minutes
    and re-queues them for processing.
    
    This endpoint can be called:
    - On server startup (via startup event)
    - Periodically via cron
    - Manually via admin dashboard
    """
    recovery_service = RecoveryService(supabase)
    result = await recovery_service.recover_all_stuck_memos()
    
    return {
        "status": "completed",
        **result,
    }


