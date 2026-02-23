"""
Centralized logging for full visibility across the Vocify backend.

Provides structured logging with:
- Correlation IDs (from webhooks) propagated across all services
- Domain/service/phase tags for easy filtering in log aggregators
- Consistent extra dict format for JSON output
- Timing helpers for pipeline visibility

Usage:
    from app.logging_config import get_logger, log_domain, with_timing

    logger = get_logger(__name__)
    logger.info("transcription_started", extra=log_domain("speechmatics", "job", job_id=jid))
    with with_timing(logger, "transcription_complete", "speechmatics", job_id=jid):
        result = await transcribe(...)
"""

import logging
import time
from contextlib import contextmanager
from typing import Any, Optional

from app.webhook_context import get_correlation_id


# Domain constants for consistent filtering
DOMAIN_TRANSCRIPTION = "transcription"
DOMAIN_EXTRACTION = "extraction"
DOMAIN_LLM = "llm"
DOMAIN_HUBSPOT = "hubspot"
DOMAIN_WHATSAPP = "whatsapp"
DOMAIN_WEBHOOK = "webhook"
DOMAIN_MEMO = "memo"
DOMAIN_API = "api"
DOMAIN_RECOVERY = "recovery"
DOMAIN_GLOSSARY = "glossary"
DOMAIN_STORAGE = "storage"
DOMAIN_UNIPILE = "unipile"


def _merge_extra(**kwargs: Any) -> dict[str, Any]:
    """Merge correlation_id with extra kwargs for structured logging."""
    extra = dict(kwargs)
    cid = get_correlation_id()
    if cid:
        extra["correlation_id"] = cid
    return extra


def log_domain(
    domain: str,
    phase: str,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Build extra dict with domain, phase, and correlation_id.
    Use for consistent structured log filtering.
    """
    out = _merge_extra(**kwargs)
    out["domain"] = domain
    out["phase"] = phase
    return out


def get_logger(name: str) -> logging.Logger:
    """Get a logger. Uses standard Python logging; config is set at startup."""
    return logging.getLogger(name)


@contextmanager
def with_timing(
    logger: logging.Logger,
    phase: str,
    domain: str,
    *,
    level: int = logging.INFO,
    **extra_fields: Any,
):
    """
    Context manager to log start, measure duration, and log completion.
    Yields a dict that callers can update with result metadata.
    """
    start = time.perf_counter()
    ctx: dict[str, Any] = dict(extra_fields)
    ctx["domain"] = domain
    ctx["phase"] = f"{phase}_started"
    logger.log(level, f"{domain} {phase} started", extra=_merge_extra(**ctx))

    try:
        yield ctx
        elapsed_ms = (time.perf_counter() - start) * 1000
        ctx["phase"] = f"{phase}_complete"
        ctx["duration_ms"] = round(elapsed_ms, 2)
        logger.log(
            level,
            f"{domain} {phase} complete in {elapsed_ms:.0f}ms",
            extra=_merge_extra(**ctx),
        )
    except Exception as e:
        elapsed_ms = (time.perf_counter() - start) * 1000
        ctx["phase"] = f"{phase}_failed"
        ctx["duration_ms"] = round(elapsed_ms, 2)
        ctx["error"] = str(e)
        logger.exception(
            f"{domain} {phase} failed after {elapsed_ms:.0f}ms: {e}",
            extra=_merge_extra(**ctx),
        )
        raise


def configure_logging(
    level: str = "INFO",
    json_format: bool = False,
) -> None:
    """
    Configure root logging. Call from main.py startup.
    Set LOG_LEVEL and LOG_JSON in config.
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    root = logging.getLogger()

    if root.handlers:
        for h in root.handlers[:]:
            root.removeHandler(h)

    handler = logging.StreamHandler()

    if json_format:
        import json

        class JsonFormatter(logging.Formatter):
            def format(self, record: logging.LogRecord) -> str:
                log_obj: dict[str, Any] = {
                    "timestamp": self.formatTime(record, self.datefmt),
                    "level": record.levelname,
                    "logger": record.name,
                    "message": record.getMessage(),
                }
                if record.exc_info:
                    log_obj["exception"] = self.formatException(record.exc_info)
                # Merge extra from record
                for k, v in record.__dict__.items():
                    if k not in (
                        "name",
                        "msg",
                        "args",
                        "created",
                        "filename",
                        "funcName",
                        "levelname",
                        "levelno",
                        "lineno",
                        "module",
                        "msecs",
                        "pathname",
                        "process",
                        "processName",
                        "relativeCreated",
                        "stack_info",
                        "exc_info",
                        "exc_text",
                        "thread",
                        "threadName",
                        "message",
                        "taskName",
                    ) and v is not None:
                        try:
                            json.dumps(v)  # ensure serializable
                            log_obj[k] = v
                        except (TypeError, ValueError):
                            log_obj[k] = str(v)
                return json.dumps(log_obj)

        handler.setFormatter(JsonFormatter())
    else:
        # Include extra fields (domain, phase, extracted_fields, etc.) in dev format
        _EXTRA_SKIP = {
            "name", "msg", "args", "created", "filename", "funcName",
            "levelname", "levelno", "lineno", "module", "msecs", "pathname",
            "process", "processName", "relativeCreated", "stack_info",
            "exc_info", "exc_text", "thread", "threadName", "message", "taskName",
        }

        class DevFormatter(logging.Formatter):
            def format(self, record: logging.LogRecord) -> str:
                base = super().format(record)
                extras = []
                for k, v in record.__dict__.items():
                    if k not in _EXTRA_SKIP and v is not None:
                        try:
                            val = str(v) if not isinstance(v, (dict, list)) else repr(v)
                            if len(val) > 500:
                                val = val[:497] + "..."
                            extras.append(f"{k}={val}")
                        except Exception:
                            pass
                if extras:
                    base += " | " + " ".join(extras)
                return base

        handler.setFormatter(
            DevFormatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")
        )

    root.addHandler(handler)
    root.setLevel(numeric_level)
