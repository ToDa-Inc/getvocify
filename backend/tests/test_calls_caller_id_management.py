from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.calls import (
    CallerIdPatchRequest,
    get_calling_config,
    patch_caller_id,
    remove_caller_id,
)
from tests.test_telephony_caller_id import fake_supabase


@pytest.mark.asyncio
async def test_patch_sets_default_and_returns_list():
    supabase, _ = fake_supabase(
        [
            {
                "user_id": "user-1",
                "phone_number": "+34910000000",
                "status": "verified",
                "label": "Oficina",
                "is_default": False,
                "verified_at": "2026-01-01T00:00:00Z",
            }
        ]
    )
    result = await patch_caller_id(
        phone_number="+34 910 000 000",
        body=CallerIdPatchRequest(isDefault=True),
        supabase=supabase,
        user_id="user-1",
    )
    assert result["callerIds"][0]["isDefault"] is True


@pytest.mark.asyncio
async def test_patch_pending_default_is_400():
    supabase, store = fake_supabase(
        [
            {
                "user_id": "user-1",
                "phone_number": "+34910000000",
                "status": "pending",
                "label": None,
                "is_default": False,
                "verified_at": None,
            }
        ]
    )
    with pytest.raises(HTTPException) as exc:
        await patch_caller_id(
            phone_number="+34910000000",
            body=CallerIdPatchRequest(isDefault=True),
            supabase=supabase,
            user_id="user-1",
        )
    assert exc.value.status_code == 400
    assert store[0]["is_default"] is False


@pytest.mark.asyncio
async def test_patch_unknown_number_is_404():
    supabase, _ = fake_supabase([])
    with pytest.raises(HTTPException) as exc:
        await patch_caller_id(
            phone_number="+34910000000",
            body=CallerIdPatchRequest(label="X"),
            supabase=supabase,
            user_id="user-1",
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_missing_is_404_and_deletes_nothing():
    supabase, store = fake_supabase(
        [
            {
                "user_id": "user-2",
                "phone_number": "+34910000000",
                "status": "verified",
                "label": None,
                "is_default": False,
                "verified_at": None,
            }
        ]
    )
    with pytest.raises(HTTPException) as exc:
        await remove_caller_id(
            phone_number="+34910000000",
            supabase=supabase,
            user_id="user-1",
        )
    assert exc.value.status_code == 404
    assert len(store) == 1


@pytest.mark.asyncio
async def test_delete_own_number():
    supabase, store = fake_supabase(
        [
            {
                "user_id": "user-1",
                "phone_number": "+34910000000",
                "status": "verified",
                "label": None,
                "is_default": False,
                "verified_at": None,
            }
        ]
    )
    result = await remove_caller_id(
        phone_number="+34910000000",
        supabase=supabase,
        user_id="user-1",
    )
    assert result == {"ok": True}
    assert store == []


@pytest.mark.asyncio
async def test_config_includes_settings_url_when_disabled():
    with patch("app.api.calls.telephony_configured", return_value=False):
        result = await get_calling_config(supabase=MagicMock(), user_id="user-1")
    assert result["enabled"] is False
    assert result["settingsUrl"].endswith("/dashboard/settings#caller-id")
