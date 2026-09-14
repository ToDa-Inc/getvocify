from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.hubspot_recordings import get_authenticated_recording


class _FakeQuery:
    def __init__(self, row):
        self._row = row

    def select(self, *_a, **_k):
        return self

    def eq(self, *_a, **_k):
        return self

    def limit(self, *_a, **_k):
        return self

    def execute(self):
        return SimpleNamespace(data=[self._row] if self._row else [])


def _supabase(row):
    client = MagicMock()
    client.table.return_value = _FakeQuery(row)
    return client


ROW = {
    "recording_path": "calls/CA123.wav",
    "hubspot_hub_id": "147506535",
}


@pytest.mark.asyncio
async def test_hubspot_ready_probe_without_query_params_returns_url():
    with patch(
        "app.api.hubspot_recordings.StorageService.signed_call_recording_url",
        return_value="https://signed.example/ca123.wav",
    ):
        result = await get_authenticated_recording(
            "CA123",
            externalAccountId="",
            appId="",
            supabase=_supabase(ROW),
        )
    assert result == {"authenticatedUrl": "https://signed.example/ca123.wav"}


@pytest.mark.asyncio
async def test_matching_external_account_id_returns_url():
    with patch(
        "app.api.hubspot_recordings.StorageService.signed_call_recording_url",
        return_value="https://signed.example/ca123.wav",
    ):
        result = await get_authenticated_recording(
            "CA123",
            externalAccountId="147506535",
            appId="31731417",
            supabase=_supabase(ROW),
        )
    assert result["authenticatedUrl"].endswith("ca123.wav")


@pytest.mark.asyncio
async def test_wrong_external_account_id_is_forbidden():
    with pytest.raises(HTTPException) as exc:
        await get_authenticated_recording(
            "CA123",
            externalAccountId="999",
            appId="31731417",
            supabase=_supabase(ROW),
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_missing_recording_is_not_found():
    with pytest.raises(HTTPException) as exc:
        await get_authenticated_recording(
            "CAmissing",
            externalAccountId="147506535",
            supabase=_supabase(None),
        )
    assert exc.value.status_code == 404
