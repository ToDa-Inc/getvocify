"""Validate Pipedrive connection (token + deal fields)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from .client import PipedriveClient, unwrap_data
from .exceptions import PipedriveError


@dataclass
class PipedriveValidationResult:
    valid: bool
    user: Optional[dict[str, Any]] = None
    error: Optional[str] = None


class PipedriveValidationService:
    def __init__(self, client: PipedriveClient) -> None:
        self.client = client

    async def validate(self) -> PipedriveValidationResult:
        try:
            me = unwrap_data(await self.client.get("/users/me", version="v1"))
            if not isinstance(me, dict) or not me.get("id"):
                return PipedriveValidationResult(valid=False, error="Unexpected users/me response")
            fields = await self.client.get("/dealFields", params={"limit": 1})
            data = unwrap_data(fields)
            if data is None:
                return PipedriveValidationResult(valid=False, error="Unexpected dealFields response")
            return PipedriveValidationResult(valid=True, user=me)
        except PipedriveError as e:
            return PipedriveValidationResult(valid=False, error=e.message)
        except Exception as e:
            return PipedriveValidationResult(valid=False, error=str(e))
