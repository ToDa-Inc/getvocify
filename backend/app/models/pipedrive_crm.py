"""API models for Pipedrive CRM routes."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class PipedriveConnectionOut(BaseModel):
    id: UUID
    user_id: UUID
    provider: str = "pipedrive"
    status: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str
