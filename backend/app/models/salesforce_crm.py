"""API models for Salesforce CRM routes."""

from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class SalesforceConnectionOut(BaseModel):
    id: UUID
    user_id: UUID
    provider: str = "salesforce"
    status: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str
