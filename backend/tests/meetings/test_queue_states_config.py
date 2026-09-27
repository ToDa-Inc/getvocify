"""F16 CRM configuration: queue state fields round-trip and Pipedrive forces deal_stage."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-queue-states-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-queue-states-32")

import asyncio

from app.models.crm_config import CRMConfigurationRequest
from app.services import company as company_service
from app.services.crm_config import CRMConfigurationService
from app.services.feature_flags import clear_cache

CONN = "00000000-0000-0000-0000-0000000000c1"
CONFIG_ID = "00000000-0000-0000-0000-0000000000f1"


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, store, table):
        self.store, self.table, self.payload, self.mode = store, table, None, "select"
        self._eqs: dict = {}

    def select(self, *_a, **_k):
        return self

    def eq(self, key, value):
        self._eqs[key] = value
        return self

    def single(self):
        return self

    def limit(self, *_a):
        return self

    def upsert(self, payload, on_conflict=None):
        del on_conflict
        self.mode, self.payload = "upsert", payload
        return self

    def execute(self):
        if self.table == "crm_connections":
            return _Result({"id": CONN, "provider": self.store.get("provider", "hubspot")})
        if self.table == "company_feature_flags":
            return _Result(self.store.get("flags") or [])
        if self.mode == "upsert":
            row = {**self.payload, "id": CONFIG_ID, "created_at": "t", "updated_at": "t"}
            self.store["row"] = row
            return _Result([row])
        return _Result(self.store.get("row"))


class _Supabase:
    def __init__(self):
        self.store: dict = {}

    def table(self, name):
        return _Query(self.store, name)


def _request(**overrides) -> CRMConfigurationRequest:
    base = {
        "default_pipeline_id": "default",
        "default_pipeline_name": "Sales",
        "default_stage_id": "new",
        "default_stage_name": "New",
    }
    base.update(overrides)
    return CRMConfigurationRequest(**base)


def test_queue_states_round_trip_and_queue_states_enabled(monkeypatch):
    clear_cache()
    monkeypatch.setattr(company_service, "get_company_id_for_user", lambda *_a: "co-1")
    supabase = _Supabase()
    supabase.store["flags"] = [
        {"flag": "CRM_STATE_EXIT_ENABLED", "enabled": True},
        {"flag": "DEAL_STAGE_CONFIRM_ENABLED", "enabled": True},
    ]
    svc = CRMConfigurationService(supabase)
    saved = asyncio.run(svc.save_configuration(
        "u-1",
        CONN,
        _request(
            queue_state_source="lead_status",
            queue_booked_states=["CONNECTED", "CONNECTED"],
            queue_ended_states=["CONNECTED", "UNQUALIFIED"],
        ),
    ))
    assert saved.queue_state_source == "lead_status"
    assert saved.queue_booked_states == ["CONNECTED"]
    assert saved.queue_ended_states == ["UNQUALIFIED"]
    assert saved.queue_states_enabled is True
    assert supabase.store["row"]["queue_booked_states"] == ["CONNECTED"]


def test_pipedrive_forces_deal_stage(monkeypatch):
    clear_cache()
    monkeypatch.setattr(company_service, "get_company_id_for_user", lambda *_a: "co-1")
    supabase = _Supabase()
    supabase.store["provider"] = "pipedrive"
    asyncio.run(CRMConfigurationService(supabase).save_configuration(
        "u-1",
        CONN,
        _request(queue_state_source="lead_status", queue_booked_states=["3"]),
    ))
    assert supabase.store["row"]["queue_state_source"] == "deal_stage"
