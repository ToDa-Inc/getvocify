"""Validate Salesforce connection (token + API access)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from .client import SalesforceClient
from .exceptions import SalesforceError


@dataclass
class SalesforceValidationResult:
    valid: bool
    organization_id: Optional[str] = None
    error: Optional[str] = None


class SalesforceValidationService:
    def __init__(self, client: SalesforceClient) -> None:
        self.client = client

    async def validate(self) -> SalesforceValidationResult:
        try:
            limits = await self.client.get("/limits")
            if not isinstance(limits, dict):
                return SalesforceValidationResult(valid=False, error="Unexpected limits response")
            await self.client.get("/sobjects/Opportunity/describe")
            return SalesforceValidationResult(valid=True, organization_id=None)
        except SalesforceError as e:
            return SalesforceValidationResult(valid=False, error=e.message)
        except Exception as e:
            return SalesforceValidationResult(valid=False, error=str(e))
