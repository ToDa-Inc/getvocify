"""A call linked to a CRM contact is named after the CRM's contact and company, not as the transcript read them."""

from __future__ import annotations

import asyncio
import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-crm-identity-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-crm-identity-32")

from app.api import crm as crm_api
from app.services import crm_identity as identity


def _run(coro):
    return asyncio.run(coro)


def _context(monkeypatch, result=None, error=None, delay=0.0):
    calls = []

    async def fake(contact_id, supabase, user_id):
        calls.append((contact_id, user_id))
        if delay:
            await asyncio.sleep(delay)
        if error:
            raise error
        return result

    monkeypatch.setattr(crm_api, "get_contact_context_for_extension", fake)
    return calls


def test_identity_is_the_crm_contact_name_company_and_email(monkeypatch):
    calls = _context(
        monkeypatch,
        {"contactId": "7", "contactName": " Jonathan Vega Díaz ", "companyName": "SeQura", "contactEmail": "j@sequra.com", "contactPhone": "+34"},
    )
    got = _run(identity.crm_identity(object(), "rep-1", "7"))
    assert got == {"contactName": "Jonathan Vega Díaz", "companyName": "SeQura", "contactEmail": "j@sequra.com"}
    assert calls == [("7", "rep-1")]


def test_identity_keeps_only_what_the_crm_has(monkeypatch):
    _context(monkeypatch, {"contactName": "Ana Ruiz", "companyName": None, "contactEmail": "  "})
    assert _run(identity.crm_identity(object(), "rep-1", "7")) == {"contactName": "Ana Ruiz"}


def test_no_contact_asks_nobody(monkeypatch):
    calls = _context(monkeypatch, {"contactName": "Ana Ruiz"})
    assert _run(identity.crm_identity(object(), "rep-1", None)) == {}
    assert calls == []


def test_a_crm_that_fails_or_is_slow_names_nothing(monkeypatch):
    _context(monkeypatch, error=RuntimeError("HubSpot is down"))
    assert _run(identity.crm_identity(object(), "rep-1", "7")) == {}
    monkeypatch.setattr(identity, "TIMEOUT_S", 0.01)
    _context(monkeypatch, {"contactName": "Ana Ruiz"}, delay=0.5)
    assert _run(identity.crm_identity(object(), "rep-1", "7")) == {}


def test_the_crm_wins_over_the_transcript_and_a_missing_value_keeps_it():
    read = {"contactName": "Jonatán", "companyName": "Secura", "contactEmail": None, "summary": "s"}
    named = identity.with_crm_identity(read, {"contactName": "Jonathan Vega Díaz", "companyName": "SeQura"})
    assert named == {"contactName": "Jonathan Vega Díaz", "companyName": "SeQura", "contactEmail": None, "summary": "s"}
    assert identity.with_crm_identity(read, {}) == read
    assert read["contactName"] == "Jonatán"  # the input is not changed
