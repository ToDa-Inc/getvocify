"""The meeting-booked stage is saved and read with the rest of the CRM configuration."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-meetings-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-meetings-32")

import asyncio

from app.models.crm_config import CRMConfigurationRequest
from app.services import company as company_service
from app.services.crm_config import CRMConfigurationService

CONN = "00000000-0000-0000-0000-0000000000c1"
CONFIG_ID = "00000000-0000-0000-0000-0000000000f1"


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, store, table):
        self.store, self.table, self.payload, self.mode = store, table, None, "select"

    def select(self, *_a, **_k):
        return self

    def eq(self, *_a):
        return self

    def single(self):
        return self

    def upsert(self, payload, on_conflict=None):
        del on_conflict
        self.mode, self.payload = "upsert", payload
        return self

    def execute(self):
        if self.table == "crm_connections":
            return _Result({"id": CONN})
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


def test_meeting_stage_round_trips_and_defaults_to_none(monkeypatch):
    monkeypatch.setattr(company_service, "get_company_id_for_user", lambda *_a: "co-1")
    supabase = _Supabase()
    svc = CRMConfigurationService(supabase)

    unset = asyncio.run(svc.save_configuration("u-1", CONN, _request()))
    assert unset.meeting_booked_stage_id is None
    assert supabase.store["row"]["meeting_booked_stage_id"] is None

    saved = asyncio.run(svc.save_configuration(
        "u-1", CONN, _request(meeting_booked_pipeline_id="default", meeting_booked_stage_id="appointmentscheduled"),
    ))
    assert saved.meeting_booked_stage_id == "appointmentscheduled"
    read = asyncio.run(svc.get_configuration("u-1", connection_id=CONN))
    assert read.meeting_booked_pipeline_id == "default"
    assert read.meeting_booked_stage_id == "appointmentscheduled"


def test_a_stage_without_its_pipeline_is_not_saved(monkeypatch):
    monkeypatch.setattr(company_service, "get_company_id_for_user", lambda *_a: "co-1")
    supabase = _Supabase()
    asyncio.run(CRMConfigurationService(supabase).save_configuration(
        "u-1", CONN, _request(meeting_booked_stage_id="appointmentscheduled"),
    ))
    assert supabase.store["row"]["meeting_booked_stage_id"] is None
    assert supabase.store["row"]["meeting_booked_pipeline_id"] is None
