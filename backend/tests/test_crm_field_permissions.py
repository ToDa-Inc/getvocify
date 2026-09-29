"""Fields AI can fill per sales role and per person, on top of the company's CRM config."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-field-perms-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-field-perms-32")

import asyncio
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.services import crm_field_permissions as perms
from app.services.company import CompanyService, Membership
from app.services.crm_config import CRMConfigurationService

CONN = "00000000-0000-0000-0000-0000000000c1"
CONFIG_ID = "00000000-0000-0000-0000-0000000000f1"
SDR = "00000000-0000-0000-0000-0000000000a1"
AE = "00000000-0000-0000-0000-0000000000a2"
HOS = "00000000-0000-0000-0000-0000000000a3"
GENERAL = "00000000-0000-0000-0000-0000000000a4"

COMPANY_CONFIG = {
    "id": CONFIG_ID,
    "connection_id": CONN,
    "default_pipeline_id": "sales",
    "default_pipeline_name": "Sales Pipeline",
    "default_stage_id": "new",
    "default_stage_name": "New",
    "allowed_deal_fields": ["dealname", "amount", "closedate", "total_employees"],
    "allowed_contact_fields": ["firstname", "lastname", "email", "phone"],
    "allowed_company_fields": ["name", "domain"],
    "allowed_line_item_fields": ["name", "quantity", "price"],
    "auto_create_contacts": True,
    "auto_create_companies": False,
    "auto_sync_hubspot_calls": True,
}


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, db, table):
        self.db, self.table = db, table
        self.filters: list = []
        self.mode, self.payload, self.single_row = "select", None, False

    def select(self, *_a, **_k):
        return self

    def eq(self, col, val):
        self.filters.append(lambda r, c=col, v=val: str(r.get(c)) == str(v))
        return self

    def in_(self, col, vals):
        vals = [str(v) for v in vals]
        self.filters.append(lambda r, c=col: str(r.get(c)) in vals)
        return self

    def single(self):
        self.single_row = True
        return self

    def upsert(self, payload, on_conflict=None):
        self.mode, self.payload, self.on_conflict = "upsert", payload, on_conflict
        return self

    def delete(self):
        self.mode = "delete"
        return self

    def _rows(self):
        return [r for r in self.db.setdefault(self.table, []) if all(f(r) for f in self.filters)]

    def execute(self):
        rows = self.db.setdefault(self.table, [])
        if self.mode == "upsert":
            keys = [k.strip() for k in self.on_conflict.split(",")]
            for row in rows:
                if all(str(row.get(k)) == str(self.payload.get(k)) for k in keys):
                    row.update(self.payload)
                    return _Result([row])
            rows.append(dict(self.payload))
            return _Result([rows[-1]])
        if self.mode == "delete":
            gone = self._rows()
            self.db[self.table] = [r for r in rows if r not in gone]
            return _Result(gone)
        found = self._rows()
        if self.single_row:
            return _Result(found[0] if found else None)
        return _Result(found)


class _Supabase:
    def __init__(self):
        self.db: dict = {"crm_configurations": [dict(COMPANY_CONFIG)], perms.TABLE: []}

    def table(self, name):
        return _Query(self.db, name)


MEMBERSHIPS = {
    SDR: Membership(id="m1", company_id="co-1", user_id=SDR, role="member", status="active", sales_role="sdr"),
    AE: Membership(id="m2", company_id="co-1", user_id=AE, role="member", status="active", sales_role="ae"),
    HOS: Membership(id="m3", company_id="co-1", user_id=HOS, role="owner", status="active"),
    GENERAL: Membership(id="m4", company_id="co-1", user_id=GENERAL, role="member", status="active"),
}


@pytest.fixture
def supabase(monkeypatch):
    monkeypatch.setattr(CompanyService, "get_membership", lambda _self, uid: MEMBERSHIPS.get(uid))
    monkeypatch.setattr(CompanyService, "sales_roles_enabled", lambda _self, _cid: True)
    return _Supabase()


def _save(supabase, scope, key, **fields):
    return perms.save_permission(
        supabase, company_id="co-1", connection_id=CONN, scope=scope, scope_key=key,
        fields=fields, updated_by=HOS,
    )


def _config(supabase, user_id, **kwargs):
    return asyncio.run(CRMConfigurationService(supabase).get_configuration(user_id, CONN, **kwargs))


def test_role_lists_replace_the_company_lists_only_for_that_role(supabase):
    _save(supabase, "role", "sdr", allowed_deal_fields=["dealname"], allowed_contact_fields=["phone", "jobtitle"])

    sdr = _config(supabase, SDR)
    assert sdr.allowed_deal_fields == ["dealname"]
    assert sdr.allowed_contact_fields == ["phone", "jobtitle"]
    # Not set for the role -> company list.
    assert sdr.allowed_company_fields == ["name", "domain"]

    ae = _config(supabase, AE)
    assert ae.allowed_deal_fields == COMPANY_CONFIG["allowed_deal_fields"]


def test_everything_but_the_field_lists_stays_company_wide(supabase):
    _save(supabase, "role", "sdr", allowed_deal_fields=["dealname"])
    sdr = _config(supabase, SDR)
    assert sdr.default_pipeline_id == "sales"
    assert sdr.default_stage_id == "new"
    assert sdr.auto_sync_hubspot_calls is True
    assert sdr.auto_create_companies is False


def test_person_wins_over_role_per_object(supabase):
    _save(supabase, "role", "ae", allowed_deal_fields=["dealname", "amount"], allowed_contact_fields=["email"])
    _save(supabase, "member", AE, allowed_deal_fields=["amount", "price_per_fte_eur"])

    ae = _config(supabase, AE)
    assert ae.allowed_deal_fields == ["amount", "price_per_fte_eur"]
    assert ae.allowed_contact_fields == ["email"]


def test_empty_list_means_none_not_the_defaults(supabase):
    _save(supabase, "role", "sdr", allowed_deal_fields=[])
    assert _config(supabase, SDR).allowed_deal_fields == []


def test_rep_without_type_uses_general_and_head_of_sales_uses_company(supabase):
    _save(supabase, "role", "general", allowed_deal_fields=["dealname"])
    assert _config(supabase, GENERAL).allowed_deal_fields == ["dealname"]
    assert _config(supabase, HOS).allowed_deal_fields == COMPANY_CONFIG["allowed_deal_fields"]


def test_fields_for_reads_the_memo_authors_lists(supabase):
    _save(supabase, "role", "sdr", allowed_deal_fields=["dealname"])
    assert _config(supabase, HOS, fields_for=SDR).allowed_deal_fields == ["dealname"]


def test_company_fields_only_ignores_overrides(supabase):
    _save(supabase, "member", SDR, allowed_deal_fields=["dealname"])
    assert _config(supabase, SDR, company_fields_only=True).allowed_deal_fields == COMPANY_CONFIG["allowed_deal_fields"]


def test_role_lists_off_when_sales_roles_flag_is_off(supabase, monkeypatch):
    monkeypatch.setattr(CompanyService, "sales_roles_enabled", lambda _self, _cid: False)
    _save(supabase, "role", "sdr", allowed_deal_fields=["dealname"])
    _save(supabase, "member", AE, allowed_deal_fields=["amount"])
    assert _config(supabase, SDR).allowed_deal_fields == COMPANY_CONFIG["allowed_deal_fields"]
    # A person's own lists do not depend on sales roles.
    assert _config(supabase, AE).allowed_deal_fields == ["amount"]


def test_lookup_failure_falls_back_to_company_lists(supabase, monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError('relation "crm_field_permissions" does not exist')

    monkeypatch.setattr(perms, "_rows_for", boom)
    assert _config(supabase, SDR).allowed_deal_fields == COMPANY_CONFIG["allowed_deal_fields"]


def test_all_inherit_removes_the_row_and_lists_are_cleaned(supabase):
    saved = _save(supabase, "role", "sdr", allowed_deal_fields=[" dealname ", "dealname", "", "amount"])
    assert saved["allowed_deal_fields"] == ["dealname", "amount"]
    assert len(supabase.db[perms.TABLE]) == 1

    _save(supabase, "role", "sdr")
    assert supabase.db[perms.TABLE] == []


def test_list_permissions_groups_roles_and_members(supabase):
    _save(supabase, "role", "ae", allowed_deal_fields=["amount"])
    _save(supabase, "member", SDR, allowed_contact_fields=["phone"])
    out = perms.list_permissions(supabase, connection_id=CONN)
    assert out["roles"]["ae"]["allowed_deal_fields"] == ["amount"]
    assert out["roles"]["sdr"] is None
    assert out["members"][SDR]["allowed_contact_fields"] == ["phone"]


def test_invalid_scopes_are_rejected(supabase):
    with pytest.raises(HTTPException):
        _save(supabase, "role", "manager", allowed_deal_fields=["x"])
    with pytest.raises(HTTPException):
        _save(supabase, "team", "x", allowed_deal_fields=["x"])


def test_editor_reads_company_lists_for_managers_only(supabase):
    assert perms.edits_company_fields(supabase, HOS) is True
    assert perms.edits_company_fields(supabase, SDR) is False


def test_migration_is_service_role_only_and_unique_per_scope():
    sql = (Path(__file__).resolve().parents[1] / "migrations" / "065_crm_field_permissions.sql").read_text()
    assert "UNIQUE (connection_id, scope, scope_key)" in sql
    assert "ENABLE ROW LEVEL SECURITY" in sql
    assert "REVOKE ALL ON crm_field_permissions FROM authenticated" in sql
