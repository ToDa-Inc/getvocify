"""Resolve primary CRM provider for memo flows (preview, match, extraction field specs)."""

from __future__ import annotations

from typing import Any, Optional, Tuple

from fastapi import HTTPException, status
from supabase import Client

from app.services.crm_providers import (
    AmbiguousPrimaryCRMError,
    UnsupportedCRMProviderError,
    build_crm_provider,
    resolve_sync_connection,
)
from app.services.hubspot.token_refresh import ensure_hubspot_connection_tokens_fresh


def get_memo_crm_or_none(supabase: Client, user_id: str) -> Tuple[Optional[Any], Optional[dict[str, Any]]]:
    """
    Returns (provider, connection_row) or (None, None) if no CRM.
    Raises HTTPException 400 if multiple CRMs connected without primary.
    """
    try:
        row = resolve_sync_connection(supabase, user_id)
    except AmbiguousPrimaryCRMError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.message,
        ) from e
    if not row:
        return None, None
    try:
        return build_crm_provider(supabase, row), row
    except UnsupportedCRMProviderError as e:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=str(e),
        ) from e


async def get_memo_crm_or_none_with_hubspot_refresh(
    supabase: Client, user_id: str
) -> Tuple[Optional[Any], Optional[dict[str, Any]]]:
    """
    Like get_memo_crm_or_none but refreshes HubSpot OAuth access tokens when stale.
    """
    try:
        row = resolve_sync_connection(supabase, user_id)
    except AmbiguousPrimaryCRMError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.message,
        ) from e
    if not row:
        return None, None
    if row.get("provider") == "hubspot":
        try:
            row = await ensure_hubspot_connection_tokens_fresh(supabase, row)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(e),
            ) from e
    try:
        return build_crm_provider(supabase, row), row
    except UnsupportedCRMProviderError as e:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=str(e),
        ) from e
