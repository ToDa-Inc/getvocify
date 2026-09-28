"""Lista 4 T2 (E7): GET /today's SDR sections - Tareas, Seguimiento, Nuevos - each with its
own cap, behind HOY_SDR_SECTIONS_ENABLED. Flag off is exactly the old response."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.api import today as today_api
from app.services import feature_flags as feature_flags_mod
from app.services.hoy.sections import SDR_FOLLOWUPS_CAP, SDR_NEW_CAP, SDR_TASKS_CAP
from app.services.hoy.signals import DEFAULT_LIMIT, never_contacted_signal

from tests.hoy.test_cadence_materialize import PRICE, _memo
from tests.hoy.test_materialize import _FakeSupabase
from tests.hoy.test_today_sections import _Supabase, _client, _flags, _isolate

NOW = datetime(2026, 9, 27, 10, 0, tzinfo=timezone.utc)


def _row(n: int, type_: str, **payload) -> dict:
    return {
        "id": f"sig-{type_}-{n}", "company_id": "co-1", "user_id": "sdr-1", "connection_id": "",
        "contact_id": f"{type_}-{n}", "deal_id": None, "memo_id": f"memo-{type_}-{n}", "type": type_,
        "dedupe_key": f"{type_}:{n}", "payload": payload, "status": "pending", "version": 1,
    }


def _commitment(n: int) -> dict:
    return _row(n, "commitment_due", kind="call", origin="rep_promise", text="Llamar",
                due_at=(NOW - timedelta(hours=1)).isoformat())


def _followup(n: int) -> dict:
    return _row(n, "followup_due", stopper="price", interest="high", days_since=8, category="price",
                quote="Está caro", touch_at=(NOW - timedelta(days=8)).isoformat(),
                due_at=(NOW - timedelta(days=1)).isoformat())


def _cold(n: int) -> dict:
    return _row(n, "going_cold", interest="high", days_silent=12)


def _get(store, monkeypatch, *, sales_role="sdr", new=0, user_id="sdr-1"):
    monkeypatch.setattr(today_api, "_now", lambda: NOW)
    asked: dict = {}

    def fake_never_contacted(_supabase, **kwargs):
        asked.update(kwargs)
        return [never_contacted_signal(contact_id=f"new-{i}", connection_id="crm-A") for i in range(new)]

    monkeypatch.setattr(today_api, "_never_contacted_for_rep", fake_never_contacted)
    today_api.set_today_tasks(lambda _company: ([], "complete"))
    try:
        body = _client(store, user_id=user_id, sales_role=sales_role).get("/api/v1/today").json()
    finally:
        today_api.set_today_tasks(None)
        feature_flags_mod.clear_cache()
    return body, asked


def test_sdr_sections_split_by_kind_with_independent_caps(monkeypatch):
    _isolate()
    store = _Supabase()
    store.tables["company_feature_flags"] = _flags(HOY_SDR_SECTIONS_ENABLED=True)
    store.tables["action_signals"] = [_commitment(i) for i in range(25)] + [_followup(i) for i in range(9)]
    body, asked = _get(store, monkeypatch, new=12)
    sections = body["sections"]
    assert set(sections) == {"tasks", "followups", "new"}
    assert len(sections["tasks"]) == SDR_TASKS_CAP == 20
    assert len(sections["followups"]) == SDR_FOLLOWUPS_CAP == 7
    assert len(sections["new"]) == SDR_NEW_CAP == 10
    assert {item["type"] for item in sections["tasks"]} == {"commitment_due"}
    assert {item["type"] for item in sections["followups"]} == {"followup_due"}
    assert {item["type"] for item in sections["new"]} == {"never_contacted"}
    assert body["sections_folded"] == {"tasks": 5, "followups": 2, "new": 2}
    # The new leads are asked for up to their own cap, not the old global 7.
    assert asked["limit"] == SDR_NEW_CAP
    # `items` keeps its old shape and cap for anything still reading it.
    assert len(body["items"]) == DEFAULT_LIMIT
    assert body["folded_count"] == 25 + 9 + 12 - DEFAULT_LIMIT


def test_new_leads_never_vanish_behind_many_hot_contacts(monkeypatch):
    _isolate()
    store = _Supabase()
    store.tables["company_feature_flags"] = _flags(HOY_SDR_SECTIONS_ENABLED=True)
    store.tables["action_signals"] = [_followup(i) for i in range(30)]
    body, _ = _get(store, monkeypatch, new=3)
    assert len(body["sections"]["followups"]) == 7
    assert [item["contact_id"] for item in body["sections"]["new"]] == ["new-0", "new-1", "new-2"]


def test_followup_reason_is_worded_server_side(monkeypatch):
    _isolate()
    store = _Supabase()
    store.tables["company_feature_flags"] = _flags(HOY_SDR_SECTIONS_ENABLED=True)
    store.tables["action_signals"] = [_followup(0)]
    body, _ = _get(store, monkeypatch)
    item = body["sections"]["followups"][0]
    assert item["reason"] == "Le interesó; frenó por precio (hace 8 días)."
    assert item["detail"] == "Está caro"
    assert item["id"] == "sig-followup_due-0"


def test_flag_on_hides_the_signals_the_cadence_replaces(monkeypatch):
    _isolate()
    store = _Supabase()
    store.tables["company_feature_flags"] = _flags(HOY_SDR_SECTIONS_ENABLED=True)
    store.tables["action_signals"] = [_cold(0), _row(1, "objection_open", category="price", quote="x",
                                                      touch_at=NOW.isoformat()), _followup(2)]
    body, _ = _get(store, monkeypatch)
    assert [item["type"] for item in body["items"]] == ["followup_due"]


def test_flag_off_is_the_old_response(monkeypatch):
    _isolate()
    store = _Supabase()
    store.tables["company_feature_flags"] = _flags(HOY_SDR_SECTIONS_ENABLED=False)
    store.tables["action_signals"] = [_cold(0), _followup(1)] + [_commitment(i) for i in range(10)]
    body, asked = _get(store, monkeypatch, new=5)
    assert "sections" not in body and "sections_folded" not in body
    assert "followup_due" not in {item["type"] for item in body["items"]}
    assert len(body["items"]) == DEFAULT_LIMIT
    # Without lead tiers the never-contacted read does not even run.
    assert asked == {}


def test_an_ae_never_gets_sdr_sections(monkeypatch):
    _isolate()
    store = _Supabase()
    store.tables["company_feature_flags"] = _flags(HOY_SDR_SECTIONS_ENABLED=True, HOY_AE_DEALS_ENABLED=True)
    store.tables["action_signals"] = [dict(_cold(0), user_id="ae-1")]
    body, asked = _get(store, monkeypatch, sales_role="ae", user_id="ae-1")
    assert set(body["sections"]) == {"calls", "meetings", "deals"}
    assert [item["type"] for item in body["items"]] == ["going_cold"]
    assert asked == {}


def test_general_and_sdr_with_the_ae_deals_flag_keep_their_role_sections_too(monkeypatch):
    _isolate()
    store = _Supabase()
    store.tables["company_feature_flags"] = _flags(HOY_SDR_SECTIONS_ENABLED=True, HOY_AE_DEALS_ENABLED=True)
    store.tables["action_signals"] = [_followup(0)]
    body, _ = _get(store, monkeypatch)
    assert set(body["sections"]) == {"calls", "tasks", "followups", "new"}
    _isolate()
    store.tables["action_signals"] = [dict(_followup(0), user_id="gen-1")]
    body, _ = _get(store, monkeypatch, sales_role=None, user_id="gen-1")
    assert set(body["sections"]) == {"calls", "meetings", "deals", "tasks", "followups", "new"}


# --- GET /today/upcoming -----------------------------------------------------------


def _upcoming(store, monkeypatch, *, sales_role="sdr", lang="es"):
    monkeypatch.setattr(today_api, "_now", lambda: NOW)
    feature_flags_mod.clear_cache()
    try:
        client = _client(store, user_id="user-a", sales_role=sales_role)
        return client.get("/api/v1/today/upcoming", headers={"Accept-Language": lang}).json()
    finally:
        feature_flags_mod.clear_cache()


def _upcoming_store(**flags):
    memo = _memo(intelligence=PRICE, days_ago=2)
    memo["capture_started_at"] = memo["created_at"] = (NOW - timedelta(days=2)).isoformat()
    return _FakeSupabase({
        "memos": [memo],
        "company_feature_flags": _flags(REP_WORKSPACE_ENABLED=True, **flags),
    })


def test_upcoming_lists_future_followups_with_the_flag(monkeypatch):
    rows = _upcoming(_upcoming_store(HOY_SDR_SECTIONS_ENABLED=True), monkeypatch)
    assert [(row["kind"], row["text"]) for row in rows] == [("followup", "Seguimiento · frenó por precio")]
    assert rows[0]["due_at"] == (NOW + timedelta(days=5)).isoformat()
    rows = _upcoming(_upcoming_store(HOY_SDR_SECTIONS_ENABLED=True), monkeypatch, lang="en")
    assert rows[0]["text"] == "Follow-up · stalled on price"


def test_upcoming_without_the_flag_or_for_an_ae_has_no_followups(monkeypatch):
    assert _upcoming(_upcoming_store(HOY_SDR_SECTIONS_ENABLED=False), monkeypatch) == []
    assert _upcoming(_upcoming_store(HOY_SDR_SECTIONS_ENABLED=True), monkeypatch, sales_role="ae") == []
