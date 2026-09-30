"""Hoy reads only the rep's own CRM tasks, and loose CRM tasks never inflate a block's
"N más" (the rep's home does not paint them). Found with a real portal: 300 open tasks
across the team gave an SDR «Información incompleta» and «280 más» over an empty Hoy."""

from __future__ import annotations

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-rep-task-scope")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-rep-task-scope")

from app.api import today as today_api  # noqa: E402
from app.services.hoy.scheduler import collect_open_tasks, task_request  # noqa: E402
from app.services.hoy.sections import hoy_sections  # noqa: E402


def _owner_filters(request: dict) -> list[dict]:
    filters = request["json"]["filterGroups"][0]["filters"]
    return [f for f in filters if f["propertyName"] == "hubspot_owner_id"]


def test_task_request_filters_by_owner_when_known():
    assert _owner_filters(task_request("hubspot", None, "77")) == [
        {"propertyName": "hubspot_owner_id", "operator": "EQ", "value": "77"}
    ]
    assert _owner_filters(task_request("hubspot", None)) == []


def test_collect_open_tasks_passes_the_owner_on_every_page():
    asked: list[dict] = []
    pages = iter([
        {"results": [{"id": "1", "properties": {"hs_task_status": "NOT_STARTED"}}], "paging": {"next": {"after": "2"}}},
        {"results": [{"id": "2", "properties": {"hs_task_status": "NOT_STARTED"}}]},
    ])

    def fetch(request):
        asked.append(request)
        return next(pages)

    tasks, coverage = collect_open_tasks("hubspot", fetch, connection_id="c", owner_id="77")
    assert [t["remote_id"] for t in tasks] == ["1", "2"]
    assert coverage == "complete"
    assert all(_owner_filters(r) for r in asked)


def test_read_tasks_uses_the_reps_cached_owner(monkeypatch):
    asked: list[dict] = []
    monkeypatch.setattr(today_api, "_FETCH", lambda request: asked.append(request) or {"results": []})
    connection = {"id": "c", "provider": "hubspot", "metadata": {"hubspot_owners": {"sdr-1": "77"}}}

    today_api._read_tasks(connection, "sdr-1")
    assert _owner_filters(asked[-1])[0]["value"] == "77"

    # Owner not known yet: the old whole-portal read, not an empty Hoy.
    today_api._read_tasks(connection, "someone-else")
    assert _owner_filters(asked[-1]) == []


def test_loose_crm_tasks_get_no_block_and_no_folded_count():
    items = [{"type": "manual_task", "contact_id": str(i)} for i in range(300)]
    items.append({"type": "commitment_due", "contact_id": "c"})
    for role in ("sdr", "ae", "general"):
        sections, folded = hoy_sections(items, role)
        assert [i["contact_id"] for i in sections["tasks"]] == ["c"]
        assert sum(folded.values()) == 0


# --- assigned contacts through the owner cache ------------------------------------------

from app.services.hoy.assigned import collect_assigned  # noqa: E402
from app.services.hoy.context import maybe_refresh_assigned_context  # noqa: E402


def _portal_fetch(asked: list[dict]):
    """One owner (id 77, the rep's real work email) owning two contacts."""
    def fetch(request: dict) -> dict:
        asked.append(request)
        if request["path"] == "/crm/v3/owners":
            return {"results": [{"id": "77", "email": "alvaro@motordeventas.io"}]}
        return {"results": [
            {"id": "1", "properties": {"firstname": "Lead", "lastname": "Uno", "hubspot_owner_id": "77"}},
            {"id": "2", "properties": {"firstname": "Lead", "lastname": "Dos", "hubspot_owner_id": "77"}},
        ]}
    return fetch


def test_the_owner_cache_matches_a_member_whose_email_differs_from_the_crm():
    asked: list[dict] = []
    page = collect_assigned(
        "hubspot", _portal_fetch(asked), connection_id="c", observed_at="2026-09-30T10:00:00Z",
        member_emails={"toni+alvaro@gmail.com"}, owner_overrides={"77": "toni+alvaro@gmail.com"},
    )
    assert [item["owner_email"] for item in page["items"]] == ["toni+alvaro@gmail.com"] * 2
    search = asked[-1]["json"]["filterGroups"][0]["filters"][0]
    assert search == {"propertyName": "hubspot_owner_id", "operator": "IN", "values": ["77"]}


def test_without_the_cache_a_different_email_still_matches_nobody():
    asked: list[dict] = []
    page = collect_assigned(
        "hubspot", _portal_fetch(asked), connection_id="c", observed_at="2026-09-30T10:00:00Z",
        member_emails={"toni+alvaro@gmail.com"},
    )
    assert page["items"] == []


class _NoWrites:
    def table(self, _name):
        return self

    def upsert(self, *_a, **_k):
        return self

    def delete(self):
        return self

    def eq(self, *_a):
        return self

    def in_(self, *_a):
        return self

    def execute(self):
        return None


def test_refresh_assigns_the_contacts_to_the_cached_member():
    connection = {
        "id": "c", "provider": "hubspot", "access_token": "t",
        "metadata": {"hubspot_owners": {"sdr-1": "77", "gone": "88"}},
    }
    members = [{"user_id": "sdr-1", "email": "toni+alvaro@gmail.com"}]
    rows, hint = maybe_refresh_assigned_context(
        _NoWrites(), "co", connection, [], members,
        observed_at="2026-09-30T10:00:00Z", fetch_factory=lambda _c: _portal_fetch([]),
    )
    assert hint is None
    assert {row["owner_user_id"] for row in rows} == {"sdr-1"}
    assert len(rows) == 2


# --- never-contacted cards carry the CRM name -------------------------------------------

from app.services.hoy.assigned import parse_assigned_page  # noqa: E402
from app.services.hoy.materialize import never_contacted_signals  # noqa: E402
from app.services.hoy.priority import rank_candidates  # noqa: E402


def test_a_never_contacted_card_is_named_from_the_crm_read():
    page = parse_assigned_page(
        "hubspot",
        {"results": [
            {"id": "1", "properties": {"firstname": "Marta", "lastname": "Ruiz", "hubspot_owner_id": "77"}},
            {"id": "2", "properties": {"email": "solo@email.com", "hubspot_owner_id": "77"}},
        ]},
        connection_id="c", observed_at="2026-09-30T10:00:00Z",
    )
    assert [item["contact_name"] for item in page["items"]] == ["Marta Ruiz", "solo@email.com"]
    candidates = [
        {**item, "connection_id": "c", "coverage": "complete"} for item in page["items"]
    ]
    from datetime import datetime, timezone

    ranked = rank_candidates(candidates, datetime(2026, 9, 30, tzinfo=timezone.utc))
    signals = never_contacted_signals(ranked, touched_contact_ids=set())
    assert sorted(signal.payload.get("contact_name") for signal in signals) == ["Marta Ruiz", "solo@email.com"]


# --- the brief's open-task read is the rep's too ------------------------------------------

def test_the_brief_reads_only_the_reps_crm_tasks(monkeypatch):
    from app.api import briefs as briefs_api

    asked: list[dict] = []
    connection = {"id": "c", "provider": "hubspot", "metadata": {"hubspot_owners": {"sdr-1": "77"}}}
    monkeypatch.setattr(today_api, "_connection", lambda _s, _company: connection)
    monkeypatch.setattr(today_api, "_FETCH", lambda request: asked.append(request) or {
        "results": [{"id": "9", "properties": {"hs_task_status": "NOT_STARTED", "hs_task_subject": "Llamar"}}],
    })
    monkeypatch.setattr(briefs_api, "_TASKS", None)
    briefs_api._open_crm_task(None, "co", "contact-1", "sdr-1")
    assert _owner_filters(asked[-1])[0]["value"] == "77"
