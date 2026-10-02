"""Error tracking shared by the API and the live transcription service."""

import logging

from app.config import settings


def init_sentry() -> None:
    """Optional: a no-op if SENTRY_DSN isn't set or the package isn't installed. Without it,
    the only way to learn about a production failure is a customer complaint or the logs."""
    if not settings.SENTRY_DSN:
        return
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
