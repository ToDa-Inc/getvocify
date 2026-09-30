"""Hoy reads only the rep's own CRM tasks, and loose CRM tasks never inflate a block's
"N más" (the rep's home does not paint them). Found with a real portal: 300 open tasks
across the team gave an SDR «Información incompleta» and «280 más» over an empty Hoy."""

from __future__ import annotations

from app.api import today as today_api
from app.services.hoy.scheduler import collect_open_tasks, task_request
from app.services.hoy.sections import hoy_sections


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
