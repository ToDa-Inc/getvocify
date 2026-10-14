"""Hard paywall for companies admin-flipped to require payment."""

from __future__ import annotations

import asyncio
import logging

from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.config import settings
from app.services.auth_session import AccessTokenError, user_id_from_access_token
from app.services.billing.entitlement import is_paywalled
from app.services.billing.store import get_billing
from app.services.company import CompanyService, _missing_company_schema
from app.services.ttl_cache import TtlCache

logger = logging.getLogger(__name__)

# Runs before every authenticated /api call. The lookup goes to the threadpool so a slow Supabase reply
# delays only this request, never the event loop every other request shares; past the budget the request
# goes through, as it already does when the lookup fails. Only "not paywalled" is cached: someone who just
# paid is never held back by a stale entry, and a company flipped to paywalled is locked within the TTL.
LOOKUP_BUDGET_S = 5.0
_open_users: TtlCache[bool] = TtlCache(60.0)

_EXACT = frozenset({"/health", "/metrics", "/openapi.json", "/docs", "/redoc"})
_PREFIXES = (
    "/webhooks",
    "/api/v1/auth",
    "/api/v1/billing",
    "/api/v1/admin",
    "/api/v1/company/invites/preview",
    "/api/v1/company/invites/accept",
    "/static",
)


def path_is_exempt(path: str) -> bool:
    if path in _EXACT:
        return True
    return any(path == prefix or path.startswith(prefix + "/") for prefix in _PREFIXES)


class PaywallMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if request.method == "OPTIONS" or path_is_exempt(request.url.path):
            return await call_next(request)
        if not request.url.path.startswith("/api/"):
            return await call_next(request)

        auth = request.headers.get("Authorization") or ""
        if not auth.lower().startswith("bearer "):
            return await call_next(request)
        token = auth.split(" ", 1)[1].strip()
        if not token:
            return await call_next(request)

        try:
            user_id = user_id_from_access_token(token, settings.SUPABASE_JWT_SECRET or "")
        except AccessTokenError:
            return await call_next(request)
        if _open_users.get(user_id):
            return await call_next(request)

        try:
            locked = await asyncio.wait_for(run_in_threadpool(_paywalled, user_id), LOOKUP_BUDGET_S)
        except asyncio.TimeoutError:
            logger.warning("paywall lookup over %.0f s; letting the request through", LOOKUP_BUDGET_S)
            return await call_next(request)
        except Exception as exc:
            if not _missing_company_schema(exc):
                logger.warning("paywall lookup failed; letting the request through: %s", exc)
            return await call_next(request)

        if locked:
            return JSONResponse(
                status_code=403,
                content={"detail": "Payment required", "code": "PAYWALL"},
            )
        _open_users.put(user_id, True)
        return await call_next(request)


def _paywalled(user_id: str) -> bool:
    from app.deps import get_supabase

    supabase = get_supabase()
    svc = CompanyService(supabase)
    membership = svc.get_membership(user_id)
    if not membership:
        return False
    company = svc.get_company(membership.company_id)
    billing = get_billing(supabase, membership.company_id)
    return is_paywalled(company, billing)
