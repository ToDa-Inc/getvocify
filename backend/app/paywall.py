"""Hard paywall for companies admin-flipped to require payment."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.config import settings
from app.services.auth_session import AccessTokenError, user_id_from_access_token
from app.services.billing.entitlement import is_paywalled
from app.services.billing.store import get_billing
from app.services.company import CompanyService, _missing_company_schema

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
            from app.deps import get_supabase

            user_id = user_id_from_access_token(token, settings.SUPABASE_JWT_SECRET or "")
            supabase = get_supabase()
            svc = CompanyService(supabase)
            membership = svc.get_membership(user_id)
            if not membership:
                return await call_next(request)
            company = svc.get_company(membership.company_id)
            billing = get_billing(supabase, membership.company_id)
        except AccessTokenError:
            return await call_next(request)
        except Exception as exc:
            if _missing_company_schema(exc):
                return await call_next(request)
            return await call_next(request)

        if is_paywalled(company, billing):
            return JSONResponse(
                status_code=403,
                content={"detail": "Payment required", "code": "PAYWALL"},
            )
        return await call_next(request)
