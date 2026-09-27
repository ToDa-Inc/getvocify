"""F16: reviewed approval writes crm_state into contact_priority_context (E4/E12/E13)."""

from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-queue-approval-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-queue-approval-32")

from app.services.feature_flags import clear_cache
from app.services.memo_approval import _write_confirmed_queue_state


class _Table:
    def __init__(self, store, name):
        self.store, self.name = store, name
        self.filters: dict = {}
        self._update = None
        self._select = False

    def select(self, *_a):
        self._select = True
        return self

    def update(self, payload):
        self._update = payload
        return self

    def eq(self, key, value):
        self.filters[key] = value
        return self

    def limit(self, *_a):
        return self

    def execute(self):
        if self.name == "company_feature_flags":
            return SimpleNamespace(data=self.store.get("flags") or [])
        if self.name == "crm_configurations":
            return SimpleNamespace(data=[self.store["config"]])
        if self.name == "contact_priority_context":
            if self._update is not None:
                for row in self.store["context"]:
                    if (
                        row["company_id"] == self.filters.get("company_id")
                        and row["connection_id"] == self.filters.get("connection_id")
                        and row["contact_id"] == self.filters.get("contact_id")
                        and (row.get("deal_id") or "") == (self.filters.get("deal_id") or "")
                    ):
                        row["payload"] = self._update["payload"]
                return SimpleNamespace(data=None)
            return SimpleNamespace(data=[
                row for row in self.store["context"]
                if row["company_id"] == self.filters.get("company_id")
                and row["connection_id"] == self.filters.get("connection_id")
                and row["contact_id"] == self.filters.get("contact_id")
            ])
        return SimpleNamespace(data=[])


class _DB:
    def __init__(self):
        self.store = {
            "flags": [
                {"flag": "CRM_STATE_EXIT_ENABLED", "enabled": True},
                {"flag": "DEAL_STAGE_CONFIRM_ENABLED", "enabled": True},
            ],
            "config": {
                "queue_state_source": "deal_stage",
                "queue_booked_states": ["appointmentscheduled"],
                "queue_ended_states": ["closedlost"],
            },
            "context": [{
                "company_id": "co-1",
                "connection_id": "conn-1",
                "contact_id": "42",
                "deal_id": "",
                "payload": {"contacted": True},
            }],
        }

    def table(self, name):
        return _Table(self.store, name)


def test_reviewed_confirmed_stage_updates_priority_cache():
    clear_cache()
    db = _DB()
    _write_confirmed_queue_state(
        db,
        company_id="co-1",
        connection_id="conn-1",
        provider="hubspot",
        contact_id="42",
        extraction={"dealStage": "appointmentscheduled", "raw_extraction": {"dealstage": "appointmentscheduled"}},
        skip_deal=False,
    )
    assert db.store["context"][0]["payload"]["crm_state"] == "appointmentscheduled"


def test_skip_deal_does_not_write_in_deal_mode():
    clear_cache()
    db = _DB()
    _write_confirmed_queue_state(
        db,
        company_id="co-1",
        connection_id="conn-1",
        provider="hubspot",
        contact_id="42",
        extraction={"raw_extraction": {"dealstage": "appointmentscheduled"}},
        skip_deal=True,
    )
    assert "crm_state" not in db.store["context"][0]["payload"]


def test_flag_off_does_not_write():
    clear_cache()
    db = _DB()
    db.store["flags"] = []
    _write_confirmed_queue_state(
        db,
        company_id="co-1",
        connection_id="conn-1",
        provider="hubspot",
        contact_id="42",
        extraction={"raw_extraction": {"dealstage": "appointmentscheduled"}},
        skip_deal=False,
    )
    assert "crm_state" not in db.store["context"][0]["payload"]
