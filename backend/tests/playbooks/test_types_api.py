"""Settings → Tipos with types by channel: add a type with a name and a channel, edit its channels and
recognition sentence, say whether detection is on, and how each type did in the last 30 days."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.api import playbooks as playbooks_api
from app.config import settings
from app.services import feature_flags
from app.services.playbooks.repository import InMemoryPlaybookRepository
from tests.playbooks.test_rules_api import _client, _clean  # noqa: F401  (autouse fixture)

CALL_RULE = {"role": "any", "channels": ["call"], "contact": "any", "deal_stages": []}


@pytest.fixture
def by_channel(monkeypatch):
    flags = {"TYPE_BY_CHANNEL_ENABLED": True, "INTELLIGENCE_CALL_READING_ENABLED": True, "PLAYBOOK_ROUTING_ENABLED": True}
    monkeypatch.setattr(feature_flags, "global_value", lambda flag: flags.get(flag, bool(getattr(settings, flag, False))))
    return flags


def test_a_type_is_added_with_a_name_and_a_channel_and_no_role(by_channel):
    store = InMemoryPlaybookRepository()
    response = _client(store).post(
        "/api/v1/playbooks/types",
        json={"type_key": "inbound_lead", "name": "Lead inbound", "channels": ["call"], "recognize": "Pidió que le llamáramos."},
    )
    assert response.status_code == 200
    row = store.list_types("co-1")["inbound_lead"]
    assert row["label"] == "Lead inbound" and row["applies_to"] == CALL_RULE
    assert row["recognize"] == "Pidió que le llamáramos."
    assert response.json()["details"]["inbound_lead"]["channels"] == ["call"]


def test_a_type_needs_a_channel(by_channel):
    response = _client().post("/api/v1/playbooks/types", json={"type_key": "x", "name": "X"})
    assert response.status_code == 422 and response.json()["detail"] == {"code": "channel_required"}


def test_a_role_in_a_given_rule_is_dropped(by_channel):
    store = InMemoryPlaybookRepository()
    rule = {"role": "sdr", "channels": ["call"], "contact": "inbound", "deal_stages": []}
    _client(store).post("/api/v1/playbooks/types", json={"type_key": "inb", "name": "Inbound", "applies_to": rule})
    assert store.list_types("co-1")["inb"]["applies_to"] == {**rule, "role": "any"}


def test_the_channels_name_and_sentence_are_edited_and_the_crm_condition_is_kept(by_channel):
    store = InMemoryPlaybookRepository()
    store.add_type("co-1", "inb", "Inbound", label="Inbound",
                   applies_to={"role": "sdr", "channels": ["call"], "contact": "inbound", "deal_stages": []})
    response = _client(store).patch(
        "/api/v1/playbooks/inb/type", json={"channels": ["call", "meeting"], "label": "Lead entrante", "recognize": ""},
    )
    assert response.status_code == 200
    row = store.list_types("co-1")["inb"]
    assert row["applies_to"] == {"role": "any", "channels": ["call", "meeting"], "contact": "inbound", "deal_stages": []}
    assert row["label"] == "Lead entrante" and row["recognize"] is None


def test_editing_an_unknown_type_is_404_and_a_member_is_403(by_channel):
    assert _client().patch("/api/v1/playbooks/ghost/type", json={"label": "X"}).status_code == 404
    store = InMemoryPlaybookRepository({"co-1": {"discovery": "published"}})
    assert _client(store, role="member").patch("/api/v1/playbooks/discovery/type", json={"label": "X"}).status_code == 403


def test_the_list_says_each_types_channels_and_whether_detection_is_on(by_channel, monkeypatch):
    store = InMemoryPlaybookRepository({"co-1": {"discovery": "published", "closing": "missing"}})
    body = _client(store).get("/api/v1/playbooks").json()
    assert body["details"]["discovery"]["channels"] == ["call"]
    assert body["details"]["closing"]["channels"] == ["meeting"]
    assert body["type_detection"] == {"by_channel": True, "call_reading": True}
    by_channel["INTELLIGENCE_CALL_READING_ENABLED"] = False
    feature_flags.clear_cache()
    assert _client(store).get("/api/v1/playbooks").json()["type_detection"] == {"by_channel": False, "call_reading": False}


def test_without_the_flag_the_list_is_unchanged(monkeypatch):
    monkeypatch.setattr(settings, "SALES_ROLES_ENABLED", False)
    store = InMemoryPlaybookRepository({"co-1": {"discovery": "published"}})
    body = _client(store).get("/api/v1/playbooks").json()
    assert "type_detection" not in body and "channels" not in body["details"]["discovery"]


def test_a_rep_sees_every_type_whatever_their_role(by_channel, monkeypatch):
    monkeypatch.setattr(settings, "SALES_ROLES_ENABLED", True)
    store = InMemoryPlaybookRepository({"co-1": {"discovery": "published", "closing": "published"}})
    body = _client(store, role="member", sales_role="sdr").get("/api/v1/playbooks").json()
    assert set(body["motions"]) == {"discovery", "closing"}


# --- the recognition sentence, drafted --------------------------------------------------------------

def test_vocify_drafts_a_recognition_sentence_from_the_name(by_channel, monkeypatch):
    seen = {}

    async def fake(messages):
        seen["prompt"] = messages[-1]["content"]
        return {"recognize": "  El cliente ya vio el producto y pide precio.  "}

    monkeypatch.setattr(playbooks_api, "_ask_recognize", fake)
    response = _client().post("/api/v1/playbooks/types/recognize", json={"name": "Negociación", "channels": ["meeting"]})
    assert response.json() == {"recognize": "El cliente ya vio el producto y pide precio."}
    assert "Negociación" in seen["prompt"] and "meeting" in seen["prompt"]


def test_a_failed_draft_is_no_sentence(by_channel, monkeypatch):
    async def broken(_messages):
        raise TimeoutError

    monkeypatch.setattr(playbooks_api, "_ask_recognize", broken)
    assert _client().post("/api/v1/playbooks/types/recognize", json={"name": "X", "channels": ["call"]}).json() == {"recognize": None}


# --- how each type did ------------------------------------------------------------------------------

class _MemoRows:
    def __init__(self, rows):
        self.rows, self.filters = rows, []

    def table(self, name):
        if name == "company_feature_flags":
            return _Empty()
        assert name == "memos"
        return self

    def select(self, *_a, **_k):
        return self

    def eq(self, column, value):
        self.filters.append(("eq", column, value))
        return self

    def gte(self, column, value):
        self.filters.append(("gte", column, value))
        return self

    def limit(self, *_a):
        return self

    def execute(self):
        return type("R", (), {"data": self.rows})()


class _Empty:
    def select(self, *_a, **_k):
        return self

    def eq(self, *_a, **_k):
        return self

    def execute(self):
        return type("R", (), {"data": []})()


def test_stats_count_each_types_interactions_and_how_many_a_person_corrected(by_channel):
    rows = [
        {"sales_motion_key": "cold", "pipeline_meta": {"playbook_pin": {"source": "reading"}}},
        {"sales_motion_key": "cold", "pipeline_meta": {"playbook_pin": {"source": "manual", "changed_from": "inbound_lead"}}},
        {"sales_motion_key": "cold", "pipeline_meta": {"playbook_pin": {"source": "manual", "picked": "during_call"}}},
        {"sales_motion_key": "inbound_lead", "pipeline_meta": None},
        {"sales_motion_key": None, "pipeline_meta": {}},
    ]
    db = _MemoRows(rows)
    client = _client()
    client.app.dependency_overrides[playbooks_api.get_supabase] = lambda: db
    body = client.get("/api/v1/playbooks/type-stats").json()
    assert body == {"days": 30, "types": {"cold": {"count": 3, "corrected": 1}, "inbound_lead": {"count": 1, "corrected": 0}}}
    since = next(value for op, column, value in db.filters if op == "gte" and column == "created_at")
    assert datetime.fromisoformat(since) < datetime.now(timezone.utc) - timedelta(days=29)
    assert ("eq", "company_id", "co-1") in db.filters


def test_the_types_by_channel_endpoints_do_not_exist_without_the_flag():
    store = InMemoryPlaybookRepository({"co-1": {"discovery": "published"}})
    client = _client(store)
    assert client.patch("/api/v1/playbooks/discovery/type", json={"label": "X"}).status_code == 404
    assert client.post("/api/v1/playbooks/types/recognize", json={"name": "X", "channels": ["call"]}).status_code == 404
    assert client.get("/api/v1/playbooks/type-stats").status_code == 404
