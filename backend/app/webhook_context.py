"""
Webhook request context for correlation ID propagation.
Set at webhook entry, read anywhere downstream for structured logging.
"""

from contextvars import ContextVar
from typing import Optional

webhook_correlation_id: ContextVar[Optional[str]] = ContextVar(
    "webhook_correlation_id", default=None
)


def get_correlation_id() -> Optional[str]:
    """Return current correlation ID for log extra."""
    return webhook_correlation_id.get()


def log_extra(**kwargs) -> dict:
    """Build log extra dict with correlation_id when available."""
    cid = get_correlation_id()
    out = dict(kwargs)
    if cid:
        out["correlation_id"] = cid
    return out
