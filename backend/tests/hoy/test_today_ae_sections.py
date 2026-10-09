"""Lista 4 T8 (E13, E16): GET /today's blocks for the AE (Demos de hoy, Tareas, Seguimiento)
and the General (the same plus Nuevos), behind HOY_SDR_SECTIONS_ENABLED - the cadence for the
AE, including handed-off contacts the AE has not talked to yet. Flag off is unchanged."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.api import today as today_api
from app.services import feature_flags as feature_flags_mod
from app.services.hoy.materialize import handoff_followup_signals, refresh_hoy_signals
from app.services.hoy.sections import DEMOS_CAP, hoy_sections
from app.services.hoy.signals import DEFAULT_LIMIT, never_contacted_signal
from app.services.hoy.upcoming import upcoming_handoff_followups

from tests.hoy.test_cadence_materialize import PRICE
from tests.hoy.test_materialize import _FakeSupabase
from tests.hoy.test_today_sections import _Supabase, _client, _flags, _isolate

NOW = datetime(2026, 9, 27, 10, 0, tzinfo=timezone.utc)
DAY_END = datetime(2026, 9, 27, 21, 59, tzinfo=timezone.utc)


def _row(n: int, type_: str, user_id: str = "ae-1", **payload) -> dict:
    return {
        "id": f"sig-{type_}-{n}", "company_id": "co-1", "user_id": user_id, "connection_id": "",
        "contact_id": f"{type_}-{n}", "deal_id": None, "memo_id": f"memo-{type_}-{n}", "type": type_,
        "dedupe_key": f"{type_}:{n}", "payload": payload, "status": "pending", "version": 1,
    }


def _commitment(n: int, **kw) -> dict:
    return _row(n, "commitment_due", kind="email", origin="rep_promise", text="Enviar propuesta",
                due_at=(NOW - timedelta(hours=1)).isoformat(), **kw)


def _followup(n: int, **kw) -> dict:
    return _row(n, "followup_due", stopper="price", interest="high", days_since=8, category="price",
                quote="Está caro", touch_at=(NOW - timedelta(days=8)).isoformat(),
                due_at=(NOW - timedelta(days=1)).isoformat(), **kw)


def _meeting(n: int, hour: int, **kw) -> dict:
    starts = NOW.replace(hour=hour).isoformat()
    row = _row(n, "meeting_today", starts_at=starts, precision="time", **kw)
    row["dedupe_key"] = f"meeting_today:handoff:h-{n}"
    return row


def _get(store, monkeypatch, *, sales_role="ae", user_id="ae-1", new=0):
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


def _store(*rows, **flags) -> _Supabase:
    store = _Supabase()
    store.tables["company_feature_flags"] = _flags(**flags)
    store.tables["action_signals"] = list(rows)
    return store


# --- the split, pure -------------------------------------------------------------------


def test_the_ae_split_puts_meetings_in_demos_by_start_time_and_drops_prospecting():
    items = [
        {"type": "commitment_due", "contact_id": "a"},
        {"type": "meeting_today", "contact_id": "late", "due_at": "2026-09-27T16:00:00+02:00"},
        {"type": "followup_due", "contact_id": "f"},
        {"type": "meeting_today", "contact_id": "early", "due_at": "2026-09-27T09:00:00Z"},
        {"type": "never_contacted", "contact_id": "n"},
        {"type": "no_reply", "contact_id": "r"},
        {"type": "manual_task", "contact_id": "t"},
    ]
    sections, folded = hoy_sections(items, "ae")
    assert list(sections) == ["tasks", "followups", "demos"]
    assert [item["contact_id"] for item in sections["demos"]] == ["early", "late"]
    # A loose CRM task has no block: the rep's home never paints it (E7/E13).
    assert [item["contact_id"] for item in sections["tasks"]] == ["a", "r"]
    assert [item["contact_id"] for item in sections["followups"]] == ["f"]
    assert folded == {"tasks": 0, "followups": 0, "demos": 0}


def test_the_general_split_has_all_four_and_the_sdr_keeps_meetings_in_tasks():
    items = [{"type": "meeting_today", "contact_id": "m", "due_at": NOW.isoformat()},
             {"type": "never_contacted", "contact_id": "n"}]
    for role in (None, "general"):
        sections, _ = hoy_sections(items, role)
        assert list(sections) == ["tasks", "followups", "demos", "new"]
        assert [i["contact_id"] for i in sections["demos"]] == ["m"]
        assert [i["contact_id"] for i in sections["new"]] == ["n"]
    sections, _ = hoy_sections(items, "sdr")
    assert list(sections) == ["tasks", "followups", "new"]
    assert [i["contact_id"] for i in sections["tasks"]] == ["m"]


def test_demos_have_their_own_cap():
    items = [{"type": "meeting_today", "contact_id": str(i), "due_at": NOW.isoformat()} for i in range(25)]
    sections, folded = hoy_sections(items, "ae")
    assert len(sections["demos"]) == DEMOS_CAP == 20
    assert folded["demos"] == 5


# --- GET /today ---------------------------------------------------------------------------


def test_ae_gets_demos_tasks_and_followups_and_no_deals_block(monkeypatch):
    _isolate()
    store = _store(
        _commitment(0), _followup(1), _meeting(2, 15), _meeting(3, 8),
        HOY_SDR_SECTIONS_ENABLED=True, HOY_MEETINGS_ENABLED=True, HOY_AE_DEALS_ENABLED=True,
    )
    body, asked = _get(store, monkeypatch)
    sections = body["sections"]
    assert set(sections) == {"tasks", "followups", "demos"}
    assert [item["type"] for item in sections["tasks"]] == ["commitment_due"]
    assert [item["type"] for item in sections["followups"]] == ["followup_due"]
    assert [item["contact_id"] for item in sections["demos"]] == ["meeting_today-3", "meeting_today-2"]
    assert body["sections_folded"] == {"tasks": 0, "followups": 0, "demos": 0}
    # Never prospecting for an AE: the never-contacted read does not even run.
    assert asked == {}
    # `items` keeps its old shape for anything still reading it.
    assert len(body["items"]) == 4


def test_ae_cadence_hides_the_signals_it_replaces(monkeypatch):
    _isolate()
    cold = dict(_row(0, "going_cold", interest="high", days_silent=12))
    objection = _row(1, "objection_open", category="price", quote="x", touch_at=NOW.isoformat())
    store = _store(cold, objection, _followup(2), HOY_SDR_SECTIONS_ENABLED=True)
    body, _ = _get(store, monkeypatch)
    assert [item["type"] for item in body["items"]] == ["followup_due"]


def test_general_gets_all_four_blocks(monkeypatch):
    _isolate()
    rows = [_commitment(0, user_id="gen-1"), _followup(1, user_id="gen-1"), _meeting(2, 11, user_id="gen-1")]
    store = _store(*rows, HOY_SDR_SECTIONS_ENABLED=True, HOY_MEETINGS_ENABLED=True, HOY_AE_DEALS_ENABLED=True)
    for role in (None, "general"):
        _isolate()
        body, asked = _get(store, monkeypatch, sales_role=role, user_id="gen-1", new=12)
        sections = body["sections"]
        assert set(sections) == {"tasks", "followups", "demos", "new"}
        assert [item["type"] for item in sections["demos"]] == ["meeting_today"]
        assert len(sections["new"]) == 10
        assert body["sections_folded"]["new"] == 2
        assert asked["limit"] == 10


def test_sdr_is_unchanged_and_its_meeting_today_stays_a_task(monkeypatch):
    _isolate()
    rows = [_commitment(0, user_id="sdr-1"), _meeting(1, 11, user_id="sdr-1")]
    store = _store(*rows, HOY_SDR_SECTIONS_ENABLED=True, HOY_MEETINGS_ENABLED=True, HOY_AE_DEALS_ENABLED=True)
    body, _ = _get(store, monkeypatch, sales_role="sdr", user_id="sdr-1")
    assert set(body["sections"]) == {"calls", "tasks", "followups", "new"}
    assert {item["type"] for item in body["sections"]["tasks"]} == {"commitment_due", "meeting_today"}


def test_a_handoff_meeting_is_a_demo_named_from_the_sdr_memo(monkeypatch):
    _isolate()
    store = _store(
        dict(_meeting(0, 12), contact_id="42", memo_id="sdr-memo"),
        HOY_SDR_SECTIONS_ENABLED=True, HOY_MEETINGS_ENABLED=True, HANDOFF_ENABLED=True,
    )
    store.tables["deal_handoffs"] = [{
        "id": "h-0", "company_id": "co-1", "connection_id": "crm-A", "contact_id": "42", "deal_id": "d1",
        "sdr_user_id": "sdr-1", "ae_user_id": "ae-1", "status": "active",
        "meeting_starts_at": NOW.replace(hour=12).isoformat(),
    }]
    store.tables["memos"] = [{
        "id": "sdr-memo", "company_id": "co-1", "user_id": "sdr-1", "hubspot_contact_id": "42",
        "extraction": {"contactName": "Marina", "companyName": "Acme"},
    }]
    seen: dict = {}

    def fake_refresh_meeting_today(_supabase, **kwargs):
        seen.update(kwargs)
        return 0

    monkeypatch.setattr(today_api, "refresh_meeting_today", fake_refresh_meeting_today)
    body, _ = _get(store, monkeypatch)
    demo = body["sections"]["demos"][0]
    assert demo["contact_id"] == "42"
    assert demo["contact_name"] == "Marina"
    assert [row["id"] for row in seen["handoffs"]] == ["h-0"]


def test_the_ae_refresh_gets_the_cadence_the_handoffs_and_no_lead_tiers(monkeypatch):
    _isolate()
    store = _store(HOY_SDR_SECTIONS_ENABLED=True, HANDOFF_ENABLED=True)
    store.tables["deal_handoffs"] = [{
        "id": "h-0", "company_id": "co-1", "connection_id": "crm-A", "contact_id": "42",
        "sdr_user_id": "sdr-1", "ae_user_id": "ae-1", "status": "active",
    }]
    store.tables["memos"] = [{"id": "sdr-memo", "company_id": "co-1", "user_id": "sdr-1", "hubspot_contact_id": "42"}]
    seen: dict = {}

    def fake_refresh(_supabase, **kwargs):
        seen.update(kwargs)
        return 0

    monkeypatch.setattr(today_api, "_now", lambda: NOW)
    monkeypatch.setattr(today_api, "refresh_hoy_signals", fake_refresh)
    try:
        _client(store).get("/api/v1/today")
    finally:
        feature_flags_mod.clear_cache()
    assert seen["cadence"] == {}
    assert seen["lead_tiers_enabled"] is False
    assert [row["id"] for row in seen["handoffs"]] == ["h-0"]
    assert [row["id"] for row in seen["handoff_memos"]] == ["sdr-memo"]


def test_with_the_sections_on_a_closed_handoff_deal_still_closes_the_handoff(monkeypatch):
    _isolate()
    store = _store(HOY_SDR_SECTIONS_ENABLED=True, HOY_AE_DEALS_ENABLED=True, HANDOFF_ENABLED=True)
    store.tables["deal_handoffs"] = [{
        "company_id": "co-1", "connection_id": "crm-A", "contact_id": "42", "deal_id": "d1",
        "sdr_user_id": "sdr-1", "ae_user_id": "ae-1", "status": "active",
    }]
    store.tables["crm_connections"] = [{
        "id": "crm-A", "company_id": "co-1", "status": "connected", "provider": "hubspot",
        "access_token": "tok", "metadata": {},
    }]

    def fake_fetch(request):
        if request["path"] == "/crm/v3/objects/tasks/search":
            return {"results": []}
        return {"results": [{"id": "d1", "properties": {"dealstage": "closedwon"}}]}

    monkeypatch.setattr(today_api, "_now", lambda: NOW)
    today_api.set_today_fetch(fake_fetch)
    try:
        body = _client(store).get("/api/v1/today").json()
    finally:
        today_api.set_today_fetch(None)
        feature_flags_mod.clear_cache()
    assert set(body["sections"]) == {"tasks", "followups", "demos"}
    assert store.tables["deal_handoffs"][0]["status"] == "closed"


def test_flag_off_the_ae_keeps_the_old_response(monkeypatch):
    _isolate()
    store = _store(dict(_row(0, "going_cold", interest="high", days_silent=12)), _followup(1),
                   HOY_SDR_SECTIONS_ENABLED=False, HOY_AE_DEALS_ENABLED=True)
    body, asked = _get(store, monkeypatch)
    assert set(body["sections"]) == {"calls", "meetings", "deals"}
    assert "sections_folded" not in body
    assert [item["type"] for item in body["items"]] == ["going_cold"]
    assert asked == {}
    _isolate()
    store.tables["company_feature_flags"] = _flags(HOY_SDR_SECTIONS_ENABLED=False)
    body, _ = _get(store, monkeypatch)
    assert "sections" not in body
    assert len(body["items"]) <= DEFAULT_LIMIT


# --- the AE's cadence on handed-off contacts ----------------------------------------------


def _sdr_memo(contact="42", *, intelligence=PRICE, user_id="sdr-1", memo_id="sdr-memo", days_ago=10, **extra):
    at = (NOW - timedelta(days=days_ago)).isoformat()
    return {
        "id": memo_id, "user_id": user_id, "hubspot_contact_id": contact, "capture_started_at": at,
        "created_at": at, "extraction": {"contactName": "Marina", "companyName": "Acme", "intelligence": intelligence},
        **extra,
    }


def _handoff(contact="42", *, meeting_days_ago=8, **extra):
    return {
        "id": "h-1", "company_id": "co-1", "connection_id": "crm-A", "contact_id": contact, "deal_id": "d1",
        "sdr_user_id": "sdr-1", "ae_user_id": "ae-1", "status": "active",
        "meeting_starts_at": (NOW - timedelta(days=meeting_days_ago)).isoformat() if meeting_days_ago is not None else None,
        "created_at": (NOW - timedelta(days=10)).isoformat(),
        **extra,
    }


def test_a_handed_off_contact_comes_back_on_the_sdr_stopper_counted_from_the_meeting():
    # SDR memo: price objection (7 days), booked. Meeting 8 days ago -> due yesterday.
    memo = _sdr_memo(rep_outcome="meeting_booked", followup_at=(NOW + timedelta(days=30)).isoformat())
    signals = handoff_followup_signals([_handoff()], [memo], own_contact_ids=set(), now=NOW, day_end=DAY_END, cadence={})
    assert [s.type for s in signals] == ["followup_due"]
    signal = signals[0]
    assert signal.due_at == NOW - timedelta(days=1)
    assert signal.payload["stopper"] == "price"
    assert signal.payload["handoff_id"] == "h-1"
    assert signal.deal_id == "d1"
    assert signal.source_memo_id == "sdr-memo"
    assert signal.dedupe_key == "followup:handoff:h-1:2026-09-26"
    # Meeting 3 days ago: the price wait has not run out yet.
    assert handoff_followup_signals([_handoff(meeting_days_ago=3)], [memo], own_contact_ids=set(), now=NOW, day_end=DAY_END, cadence={}) == []


def test_without_a_meeting_time_the_handoff_itself_starts_the_wait():
    signals = handoff_followup_signals([_handoff(meeting_days_ago=None)], [_sdr_memo()], own_contact_ids=set(), now=NOW, day_end=DAY_END, cadence={})
    assert signals[0].due_at == NOW - timedelta(days=10) + timedelta(days=7)


def test_the_ae_first_memo_takes_over_and_other_reps_memos_do_not_count():
    assert handoff_followup_signals([_handoff()], [_sdr_memo()], own_contact_ids={"42"}, now=NOW, day_end=DAY_END, cadence={}) == []
    stranger = _sdr_memo(user_id="sdr-2")
    assert handoff_followup_signals([_handoff()], [stranger], own_contact_ids=set(), now=NOW, day_end=DAY_END, cadence={}) == []
    unknown = _sdr_memo(intelligence={})
    assert handoff_followup_signals([_handoff()], [unknown], own_contact_ids=set(), now=NOW, day_end=DAY_END, cadence={}) == []


def test_refresh_persists_the_handoff_followup_and_retracts_it_once_the_ae_talks():
    supabase = _FakeSupabase({"memos": [], "action_signals": []})
    refresh_hoy_signals(
        supabase, company_id="co-1", user_id="ae-1", now=NOW, tz_name="Europe/Madrid", cadence={},
        handoffs=[_handoff()], handoff_memos=[_sdr_memo()],
    )
    rows = supabase.rows("action_signals")
    assert [(row["type"], row["dedupe_key"], row["status"]) for row in rows] == [
        ("followup_due", "followup:handoff:h-1:2026-09-26", "pending"),
    ]
    rows[0]["memo_id"] = "sdr-memo"
    ae_memo = {
        "id": "ae-memo", "user_id": "ae-1", "hubspot_contact_id": "42",
        "created_at": (NOW - timedelta(hours=2)).isoformat(), "extraction": {"intelligence": {"interest": "high"}},
    }
    supabase.rows("memos").append(ae_memo)
    refresh_hoy_signals(
        supabase, company_id="co-1", user_id="ae-1", now=NOW, tz_name="Europe/Madrid", cadence={},
        handoffs=[_handoff()], handoff_memos=[_sdr_memo()],
    )
    assert rows[0]["status"] == "resolved"


def test_an_unread_handoff_list_never_retracts_and_the_flag_off_never_produces():
    stored = {
        "id": "row-h", "company_id": "co-1", "user_id": "ae-1", "type": "followup_due", "status": "pending",
        "memo_id": "sdr-memo", "dedupe_key": "followup:handoff:h-1:2026-09-26",
    }
    supabase = _FakeSupabase({"memos": [], "action_signals": [dict(stored)]})
    refresh_hoy_signals(supabase, company_id="co-1", user_id="ae-1", now=NOW, tz_name="Europe/Madrid", cadence={},
                        handoffs=None, handoff_memos=[_sdr_memo()])
    refresh_hoy_signals(supabase, company_id="co-1", user_id="ae-1", now=NOW, tz_name="Europe/Madrid", cadence={},
                        handoffs=[_handoff()], handoff_memos=None)
    assert supabase.rows("action_signals")[0]["status"] == "pending"
    empty = _FakeSupabase({"memos": [], "action_signals": []})
    refresh_hoy_signals(empty, company_id="co-1", user_id="ae-1", now=NOW, tz_name="Europe/Madrid", cadence=None,
                        handoffs=[_handoff()], handoff_memos=[_sdr_memo()])
    assert empty.rows("action_signals") == []


def test_the_ae_own_followups_use_the_cadence_too():
    ae_memo = {
        "id": "ae-memo", "user_id": "ae-1", "hubspot_contact_id": "77",
        "created_at": (NOW - timedelta(days=8)).isoformat(),
        "extraction": {"intelligence": PRICE},
    }
    supabase = _FakeSupabase({"memos": [ae_memo], "action_signals": []})
    refresh_hoy_signals(supabase, company_id="co-1", user_id="ae-1", now=NOW, tz_name="Europe/Madrid", cadence={},
                        handoffs=[], handoff_memos=[])
    assert [row["type"] for row in supabase.rows("action_signals")] == ["followup_due"]


def test_upcoming_lists_a_handed_off_followup_before_its_date():
    rows = upcoming_handoff_followups(
        [_handoff(meeting_days_ago=3)], [_sdr_memo()], own_contact_ids=set(), now=NOW, tz_name="Europe/Madrid",
    )
    assert [(row["kind"], row["contact_name"], row["text"]) for row in rows] == [
        ("followup", "Marina", "Seguimiento · frenó por precio"),
    ]
    assert rows[0]["due_at"] == (NOW - timedelta(days=3) + timedelta(days=7)).isoformat()
    assert upcoming_handoff_followups(
        [_handoff(meeting_days_ago=3)], [_sdr_memo()], own_contact_ids={"42"}, now=NOW, tz_name="Europe/Madrid",
    ) == []


def test_upcoming_endpoint_lists_the_ae_followups_with_the_flag(monkeypatch):
    memo = {
        "id": "ae-memo", "user_id": "user-a", "hubspot_contact_id": "77",
        "created_at": (NOW - timedelta(days=2)).isoformat(), "capture_started_at": (NOW - timedelta(days=2)).isoformat(),
        "extraction": {"contactName": "Luis", "intelligence": PRICE},
    }
    store = _FakeSupabase({
        "memos": [memo],
        "company_feature_flags": _flags(REP_WORKSPACE_ENABLED=True, HOY_SDR_SECTIONS_ENABLED=True),
    })
    monkeypatch.setattr(today_api, "_now", lambda: NOW)
    feature_flags_mod.clear_cache()
    try:
        rows = _client(store, user_id="user-a", sales_role="ae").get("/api/v1/today/upcoming").json()
    finally:
        feature_flags_mod.clear_cache()
    assert [(row["kind"], row["contact_name"]) for row in rows] == [("followup", "Luis")]
