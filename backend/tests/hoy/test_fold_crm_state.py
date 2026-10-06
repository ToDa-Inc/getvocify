"""E11: fold_context keeps the last crm_state when a CRM state read omits the key."""

from __future__ import annotations

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-fold-crm-state-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-fold-crm-state-32")

from app.services.hoy.context import fold_context

COMPANY = "co-1"
MEMBERS = [{"user_id": "u-1", "email": "ana@vocify.test", "name": "Ana"}]


def test_missing_crm_state_key_preserves_previous():
    previous = fold_context(
        company_id=COMPANY,
        pages=[{
            "connection_id": "crm-A",
            "coverage": "complete",
            "observed_at": "2026-09-22T09:00:00Z",
            "items": [{
                "contact_id": "42",
                "owner_email": "ana@vocify.test",
                "crm_state": "appointmentscheduled",
                "contacted": True,
            }],
        }],
        members=MEMBERS,
    )
    assert previous[0]["payload"]["crm_state"] == "appointmentscheduled"

    folded = fold_context(
        company_id=COMPANY,
        pages=[{
            "connection_id": "crm-A",
            "coverage": "partial",
            "observed_at": "2026-09-22T10:00:00Z",
            "items": [{
                "contact_id": "42",
                "owner_email": "ana@vocify.test",
                "contacted": True,
            }],
        }],
        members=MEMBERS,
        previous=previous,
    )
    assert folded[0]["payload"]["crm_state"] == "appointmentscheduled"


def test_present_crm_state_overwrites_previous():
    previous = [{
        "company_id": COMPANY,
        "connection_id": "crm-A",
        "contact_id": "42",
        "deal_id": "",
        "owner_user_id": "u-1",
        "owner_ambiguous": False,
        "coverage": "complete",
        "history_complete": True,
        "observed_at": "t0",
        "payload": {"crm_state": "appointmentscheduled"},
    }]
    folded = fold_context(
        company_id=COMPANY,
        pages=[{
            "connection_id": "crm-A",
            "coverage": "complete",
            "observed_at": "t1",
            "items": [{
                "contact_id": "42",
                "owner_email": "ana@vocify.test",
                "crm_state": "qualifiedtobuy",
            }],
        }],
        members=MEMBERS,
        previous=previous,
    )
    assert folded[0]["payload"]["crm_state"] == "qualifiedtobuy"
