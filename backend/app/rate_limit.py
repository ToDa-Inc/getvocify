"""
Shared rate limiter for abuse-prone public endpoints (login, signup, token
refresh). Without this, those endpoints have zero protection against
brute-force/credential-stuffing or signup-spam bots.

Degrades to a no-op if slowapi isn't installed, so a missing optional
dependency never takes the whole API down.
"""

import logging

logger = logging.getLogger(__name__)

try:
    from slowapi import Limiter
    from slowapi.util import get_remote_address

    limiter = Limiter(key_func=get_remote_address)
    RATE_LIMITING_ENABLED = True
except ImportError:
    logger.warning("slowapi not installed - rate limiting on auth endpoints is disabled")
    RATE_LIMITING_ENABLED = False

    class _NoopLimiter:
        def limit(self, *_args, **_kwargs):
            def decorator(func):
                return func
            return decorator

    limiter = _NoopLimiter()
