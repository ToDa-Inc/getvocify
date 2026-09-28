"""An approved memo remembers which CRM contact and deal it landed on."""

from __future__ import annotations

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-memo-links-32b")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-memo-links-32b")

from app.services.hubspot.types import SyncResult
from app.services.memo_approval import crm_links_update


def test_a_web_memo_gets_the_contact_and_deal_it_synced_to():
    result = SyncResult(memo_id="m", success=True, contact_id="42", deal_id="D7")
    assert crm_links_update({}, result) == {"hubspot_contact_id": "42", "hubspot_deal_id": "D7"}


def test_a_call_memo_keeps_the_contact_it_was_recorded_on():
    result = SyncResult(memo_id="m", success=True, contact_id="99", deal_id="D7")
    memo = {"hubspot_contact_id": "42", "hubspot_deal_id": None}
    assert crm_links_update(memo, result) == {"hubspot_deal_id": "D7"}


def test_a_sync_without_ids_changes_nothing():
    assert crm_links_update({}, SyncResult(memo_id="m", success=True)) == {}
