"""F05.05: «no te ha respondido, vuelve a llamar». Deterministic, read from the CRM, behind a company flag."""

from __future__ import annotations

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-hoy-no-reply")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-hoy-no-reply")

import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import today as today_api
from app.config import settings
from app.deps import get_membership, get_supabase
from app.services import feature_flags
from app.services.company import Membership
from app.services.hoy import assigned as assigned_mod
from app.services.hoy.assigned import connection_assigned_fetch
from app.services.hoy.no_reply import (
    NO_REPLY_FLAG,
    Activity,
    collect_no_reply,
    no_reply_signal,
    refresh_no_reply,
)
from app.services.hoy.reasons import reason
from app.services.hoy.signals import Signal, rank_cards

MADRID = "Europe/Madrid"
NOW = datetime(2026, 9, 26, 8, 0, tzinfo=timezone.utc)
REP = "rep@acme.com"
COMPANY = "co-1"
USER = "user-a"
CONNECTION = {"id": "crm-A", "provider": "hubspot", "access_token": "tok", "status": "connected", "company_id": COMPANY}


def _days_ago(days: int, hour: int = 9) -> datetime:
    return (NOW - timedelta(days=days)).replace(hour=hour, minute=0)


def _out(at: datetime, *, id: str = "e1", subject: str | None = "Propuesta Q4") -> Activity:
    return Activity(kind="email_out", at=at, id=id, subject=subject, by_rep=True)


def _talked(days: int = 20) -> Activity:
    return Activity(kind="call", at=_days_ago(days), id="c0")


# --- the rule -------------------------------------------------------------------------------


def test_ten_local_days_after_an_unanswered_follow_up_is_a_card():
    signal = no_reply_signal("42", [_talked(), _out(_days_ago(10))], now=NOW, tz_name=MADRID, connection_id="crm-A")
    assert signal is not None
    assert signal.type == "no_reply"
    assert signal.contact_id == "42"
    assert signal.connection_id == "crm-A"
    assert signal.payload["email_date"] == "2026-09-16"
    assert signal.payload["subject"] == "Propuesta Q4"
    assert signal.dedupe_key == "no_reply:42:2026-09-16"


def test_nine_days_is_not_yet_a_card():
    assert no_reply_signal("42", [_talked(), _out(_days_ago(9))], now=NOW, tz_name=MADRID) is None


def test_days_are_counted_on_the_company_calendar_not_as_a_timedelta():
    sent = datetime(2026, 9, 1, 21, 30, tzinfo=timezone.utc)  # 23:30 in Madrid
    now = datetime(2026, 9, 10, 22, 30, tzinfo=timezone.utc)  # 00:30 on the 11th in Madrid
    talked = Activity(kind="memo", at=sent - timedelta(days=2), id="m0")
    madrid = no_reply_signal("42", [talked, _out(sent)], now=now, tz_name=MADRID)
    utc = no_reply_signal("42", [talked, _out(sent)], now=now, tz_name="UTC")
    assert madrid is not None and madrid.payload["email_date"] == "2026-09-01"
    assert utc is None


@pytest.mark.parametrize("kind", ["email_in", "call", "meeting", "memo"])
def test_anything_after_the_email_means_there_is_nothing_to_chase(kind):
    later = Activity(kind=kind, at=_days_ago(4), id="x")
    assert no_reply_signal("42", [_talked(), _out(_days_ago(12)), later], now=NOW, tz_name=MADRID) is None


def test_the_last_outgoing_email_is_the_one_that_counts():
    recent = [_talked(25), _out(_days_ago(15), id="e1"), _out(_days_ago(5), id="e2")]
    assert no_reply_signal("42", recent, now=NOW, tz_name=MADRID) is None
    older = [_talked(25), _out(_days_ago(20), id="e1"), _out(_days_ago(12), id="e2", subject="Segundo")]
    signal = no_reply_signal("42", older, now=NOW, tz_name=MADRID)
    assert signal is not None
    assert signal.payload["email_id"] == "e2"
    assert signal.payload["subject"] == "Segundo"


def test_a_cold_email_without_any_earlier_conversation_is_not_a_follow_up():
    assert no_reply_signal("42", [_out(_days_ago(12))], now=NOW, tz_name=MADRID) is None


def test_an_email_older_than_the_lookback_no_longer_asks_for_a_call():
    assert no_reply_signal("42", [_talked(40), _out(_days_ago(31))], now=NOW, tz_name=MADRID) is None


def test_a_future_commitment_suppresses_the_card():
    activities = [_talked(), _out(_days_ago(12))]
    assert no_reply_signal("42", activities, now=NOW, tz_name=MADRID, future_commitment=True) is None


def test_a_contact_without_emails_has_no_card():
    assert no_reply_signal("42", [_talked()], now=NOW, tz_name=MADRID) is None
    assert no_reply_signal("42", [], now=NOW, tz_name=MADRID) is None


# --- reason and ranking ---------------------------------------------------------------------


def _no_reply(contact: str = "42", subject: str | None = "Propuesta Q4", email_at: datetime | None = None) -> Signal:
    at = email_at or _days_ago(12)
    return Signal(
        type="no_reply",
        contact_id=contact,
        deal_id=None,
        source_memo_id="",
        due_at=None,
        payload={"email_at": at.isoformat(), "email_date": "2026-09-14", "subject": subject, "email_id": "e1"},
        dedupe_key=f"no_reply:{contact}:2026-09-14",
        connection_id="crm-A",
    )


def test_the_reason_names_the_date_and_the_subject_in_both_languages():
    assert reason(_no_reply(), lang="es") == "Le escribiste el 14 sep («Propuesta Q4») y no ha respondido."
    assert reason(_no_reply(), lang="en") == 'You emailed on Sep 14 ("Propuesta Q4") and got no reply.'
    assert reason(_no_reply(subject=None), lang="es") == "Le escribiste el 14 sep y no ha respondido."
    assert reason(_no_reply(subject=None), lang="en") == "You emailed on Sep 14 and got no reply."
    long = reason(_no_reply(subject="x" * 90), lang="es")
    assert "«" + "x" * 59 + "…»" in long


def test_one_card_per_contact_and_no_reply_leads_over_going_cold():
    cold = Signal(
        type="going_cold",
        contact_id="42",
        deal_id=None,
        source_memo_id="memo-1",
        due_at=None,
        payload={"interest": "high", "days_silent": 14},
        dedupe_key="cold:memo-1",
        connection_id="crm-A",
    )
    cards, folded = rank_cards([cold, _no_reply()], now=NOW)
    assert folded == 0
    assert len(cards) == 1
    assert cards[0].primary.type == "no_reply"
    assert [item.type for item in cards[0].supporting] == ["going_cold"]


def test_no_reply_ranks_between_a_due_commitment_and_going_cold_across_contacts():
    commitment = Signal(
        type="commitment_due",
        contact_id="1",
        deal_id=None,
        source_memo_id="m",
        due_at=NOW,
        payload={"kind": "call", "origin": "prospect_request", "text": "llamar"},
        dedupe_key="commitment:m",
    )
    cold = Signal(
        type="going_cold",
        contact_id="3",
        deal_id=None,
        source_memo_id="m3",
        due_at=None,
        payload={"interest": "high", "days_silent": 30},
        dedupe_key="cold:m3",
    )
    newer = _no_reply("2", email_at=_days_ago(10))
    older = _no_reply("4", email_at=_days_ago(20))
    cards, _ = rank_cards([cold, newer, commitment, older], now=NOW)
    assert [card.primary.contact_id for card in cards] == ["1", "4", "2", "3"]


# --- HubSpot read ---------------------------------------------------------------------------


def _email(id, at, *, owner="o1", direction="EMAIL", subject="Propuesta Q4", status="SENT"):
    return {
        "id": id,
        "properties": {
            "hs_timestamp": at.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "hs_email_subject": subject,
            "hs_email_direction": direction,
            "hubspot_owner_id": owner,
            "hs_email_status": status,
        },
    }


def _engagement(id, at):
    return {"id": id, "properties": {"hs_timestamp": at.strftime("%Y-%m-%dT%H:%M:%S.000Z")}}


class FakeHubSpot:
    """Routes the batch/search requests the reader sends. Any per-contact GET fails the test."""

    def __init__(self):
        self.owners = [{"id": "o1", "email": REP}, {"id": "o2", "email": "other@acme.com"}]
        self.outbound: list[dict] = []
        self.email_contacts: dict[str, list[str]] = {}
        self.contacts: dict[str, dict] = {}
        self.assoc: dict[str, dict[str, list[str]]] = {"emails": {}, "calls": {}, "meetings": {}}
        self.objects: dict[str, dict[str, dict]] = {"emails": {}, "calls": {}, "meetings": {}}
        self.requests: list[dict] = []
        self.fail: dict[str, dict] = {}
        self.page_size: int | None = None

    def __call__(self, request: dict) -> dict:
        self.requests.append(request)
        path = request["path"]
        for prefix, failure in self.fail.items():
            if path.startswith(prefix):
                return failure
        body = request.get("json") or {}
        if path == "/crm/v3/owners":
            return {"results": self.owners}
        if path == "/crm/v3/objects/emails/search":
            owners = set()
            for flt in body["filterGroups"][0]["filters"]:
                if flt["propertyName"] == "hubspot_owner_id":
                    owners = set(flt["values"])
            rows = [row for row in self.outbound if row["properties"]["hubspot_owner_id"] in owners]
            size = self.page_size or body["limit"]
            start = int(body.get("after") or 0)
            page = rows[start:start + size]
            out: dict = {"results": page}
            if start + size < len(rows):
                out["paging"] = {"next": {"after": str(start + size)}}
            return out
        if path == "/crm/v4/associations/emails/contacts/batch/read":
            results = []
            for item in body["inputs"]:
                targets = self.email_contacts.get(item["id"]) or []
                if targets:
                    results.append({"from": {"id": item["id"]}, "to": [{"toObjectId": int(cid)} for cid in targets]})
            return {"results": results}
        if path == "/crm/v3/objects/contacts/batch/read":
            results = []
            for item in body["inputs"]:
                contact = self.contacts.get(item["id"])
                if contact is not None:
                    results.append({"id": item["id"], "properties": contact})
            return {"results": results}
        if path.startswith("/crm/v4/associations/contacts/") and path.endswith("/batch/read"):
            kind = path.split("/")[5]
            results = []
            for item in body["inputs"]:
                ids = self.assoc[kind].get(item["id"]) or []
                if ids:
                    results.append({"from": {"id": item["id"]}, "to": [{"toObjectId": int(oid)} for oid in ids]})
            return {"results": results}
        if path.startswith("/crm/v3/objects/") and path.endswith("/batch/read"):
            kind = path.split("/")[4]
            return {"results": [self.objects[kind][item["id"]] for item in body["inputs"] if item["id"] in self.objects[kind]]}
        raise AssertionError(f"unexpected request {request['method']} {path}")


def _scenario() -> FakeHubSpot:
    """42: unanswered 12 days. 43: replied in the thread. 44: reassigned. 45: cold outreach. 9: no contact."""
    hs = FakeHubSpot()
    hs.outbound = [
        _email("901", _days_ago(12)),
        _email("902", _days_ago(14)),
        _email("903", _days_ago(11)),
        _email("904", _days_ago(13)),
        _email("909", _days_ago(15)),
        _email("950", _days_ago(12), owner="o2"),
    ]
    hs.email_contacts = {"901": ["42"], "902": ["43"], "903": ["44"], "904": ["45"], "950": ["46"]}
    hs.contacts = {
        "42": {"firstname": "Marina", "lastname": "López", "hubspot_owner_id": "o1"},
        "43": {"firstname": "Pablo", "lastname": "", "hubspot_owner_id": "o1"},
        "44": {"firstname": "Ana", "lastname": "", "hubspot_owner_id": "o2"},
        "45": {"firstname": "Luis", "lastname": "", "hubspot_owner_id": ""},
        "46": {"firstname": "Otro", "lastname": "", "hubspot_owner_id": "o2"},
    }
    hs.assoc["emails"] = {"42": ["901"], "43": ["902", "1002"], "44": ["903"], "45": ["904"]}
    hs.assoc["calls"] = {"42": ["701"], "43": ["702"], "44": ["703"]}
    hs.objects["emails"] = {
        "1002": _email("1002", _days_ago(10), direction="INCOMING_EMAIL", owner="", subject="RE: Propuesta Q4"),
    }
    hs.objects["calls"] = {
        "701": _engagement("701", _days_ago(20)),
        "702": _engagement("702", _days_ago(20)),
        "703": _engagement("703", _days_ago(20)),
    }
    return hs


def _collect(hs, **kwargs):
    return collect_no_reply(
        kwargs.pop("provider", "hubspot"),
        hs,
        connection_id="crm-A",
        observed_at="2026-09-26T08:00:00Z",
        rep_email=kwargs.pop("rep_email", REP),
        now=NOW,
        tz_name=MADRID,
        **kwargs,
    )


def _by_contact(envelope):
    return {item["contact_id"]: item for item in envelope["items"]}


def test_hubspot_read_scopes_to_the_rep_and_batches_every_lookup():
    hs = _scenario()
    envelope = _collect(hs)
    assert envelope["coverage"] == "complete"
    items = _by_contact(envelope)
    assert set(items) == {"42", "43", "45"}
    assert items["42"]["contact_name"] == "Marina López"
    kinds_43 = sorted(activity.kind for activity in items["43"]["activities"])
    assert kinds_43 == ["call", "email_in", "email_out"]
    paths = [request["path"] for request in hs.requests]
    assert not any("/objects/contacts/4" in path for path in paths)
    assert len(paths) <= 10


def test_hubspot_read_ends_in_one_signal_for_the_unanswered_contact():
    envelope = _collect(_scenario())
    signals = [
        signal
        for item in envelope["items"]
        if (signal := no_reply_signal(item["contact_id"], item["activities"], now=NOW, tz_name=MADRID))
    ]
    assert [signal.contact_id for signal in signals] == ["42"]


def test_an_expired_token_and_a_missing_scope_are_different_coverage():
    hs = _scenario()
    hs.fail = {"/crm/v3/objects/emails/search": {"error_kind": "401"}}
    expired = _collect(hs)
    hs.fail = {"/crm/v3/objects/emails/search": {"error_kind": "403"}}
    forbidden = _collect(hs)
    assert (expired["coverage"], expired["reason"], expired["items"]) == ("unavailable", "auth_expired", [])
    assert (forbidden["coverage"], forbidden["reason"], forbidden["items"]) == ("forbidden", "email_scope_missing", [])


def test_a_failed_later_batch_is_not_an_empty_inbox():
    hs = _scenario()
    hs.fail = {"/crm/v3/objects/emails/batch/read": {"error_kind": "403"}}
    envelope = _collect(hs)
    assert envelope["coverage"] == "forbidden"
    assert envelope["items"] == []


def test_the_search_cursor_is_followed_and_a_page_cap_is_partial():
    hs = _scenario()
    hs.page_size = 2
    followed = _collect(hs)
    assert followed["coverage"] == "complete"
    assert set(_by_contact(followed)) == {"42", "43", "45"}
    capped = _collect(hs, max_pages=1)
    assert capped["coverage"] == "partial"


def test_an_object_cap_drops_the_unread_contact_and_is_partial():
    hs = _scenario()
    envelope = _collect(hs, max_objects=1)
    assert envelope["coverage"] == "partial"
    assert "43" not in _by_contact(envelope)


def test_a_rep_without_a_hubspot_owner_is_unavailable_not_empty():
    envelope = _collect(_scenario(), rep_email="nobody@acme.com")
    assert (envelope["coverage"], envelope["reason"]) == ("unavailable", "owner_not_found")


def test_pipedrive_email_coverage_is_unavailable_without_calling_the_crm():
    def fetch(_request):
        raise AssertionError("Pipedrive has no email read")

    envelope = _collect(fetch, provider="pipedrive")
    assert (envelope["coverage"], envelope["reason"], envelope["items"]) == (
        "unavailable",
        "not_available_for_pipedrive",
        [],
    )


def test_a_429_waits_retry_after_capped_and_then_reads(monkeypatch):
    waits: list[float] = []
    monkeypatch.setattr(assigned_mod, "_sleep", waits.append)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/crm/v3/owners":
            return httpx.Response(200, json={"results": [{"id": "o1", "email": REP}]})
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "60"}, json={})
        return httpx.Response(200, json={"results": []})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    envelope = _collect(connection_assigned_fetch(CONNECTION, client=client))
    assert waits == [10.0]
    assert envelope["coverage"] == "complete"
    assert envelope["items"] == []


def test_a_429_that_never_clears_is_unavailable(monkeypatch):
    monkeypatch.setattr(assigned_mod, "_sleep", lambda _seconds: None)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/crm/v3/owners":
            return httpx.Response(200, json={"results": [{"id": "o1", "email": REP}]})
        return httpx.Response(429, json={})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    envelope = _collect(connection_assigned_fetch(CONNECTION, client=client))
    assert (envelope["coverage"], envelope["reason"]) == ("unavailable", "rate_limited")


# --- persistence and reconcile ---------------------------------------------------------------


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, store: "FakeSupabase", name: str):
        self.store = store
        self.name = name
        self.filters: list = []
        self.op = "select"
        self.values: dict | None = None
        self.ignore = False

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, column, value):
        self.filters.append((column, lambda v, value=value: v == value))
        return self

    def in_(self, column, values):
        allowed = set(values)
        self.filters.append((column, lambda v: v in allowed))
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def upsert(self, values, on_conflict=None, ignore_duplicates=False):
        self.op, self.values, self.ignore = "upsert", values, ignore_duplicates
        self.conflict = [part.strip() for part in (on_conflict or "").split(",") if part.strip()]
        return self

    def update(self, values):
        self.op, self.values = "update", values
        return self

    def _match(self, row):
        return all(test(row.get(column)) for column, test in self.filters)

    def execute(self):
        rows = self.store.tables.setdefault(self.name, [])
        if self.op == "select":
            return _Result([dict(row) for row in rows if self._match(row)])
        if self.op == "update":
            hit = [row for row in rows if self._match(row)]
            for row in hit:
                row.update(self.values)
            return _Result([dict(row) for row in hit])
        values = self.values if isinstance(self.values, list) else [self.values]
        written = []
        for value in values:
            clash = next((row for row in rows if all(row.get(key) == value.get(key) for key in self.conflict)), None)
            if clash is not None:
                if not self.ignore:
                    clash.update(value)
                continue
            row = {"id": str(uuid.uuid4()), "version": 1, **value}
            rows.append(row)
            written.append(dict(row))
        return _Result(written)


class FakeSupabase:
    def __init__(self):
        self.tables: dict[str, list[dict]] = {"action_signals": [], "memos": [], "company_feature_flags": [], "crm_connections": []}

    def table(self, name):
        return _Query(self, name)


def _refresh(store, hs, now=NOW):
    return refresh_no_reply(
        store,
        company_id=COMPANY,
        user_id=USER,
        rep_email=REP,
        connection=CONNECTION,
        fetch=hs,
        now=now,
        tz_name=MADRID,
    )


def _signals(store, status=None):
    rows = [row for row in store.tables["action_signals"] if row["type"] == "no_reply"]
    return [row for row in rows if status is None or row["status"] == status]


def test_refresh_writes_one_pending_card_and_a_reply_resolves_it():
    store, hs = FakeSupabase(), _scenario()
    result = _refresh(store, hs)
    assert result["coverage"] == "complete"
    [row] = _signals(store)
    assert row["status"] == "pending"
    assert row["contact_id"] == "42"
    assert row["dedupe_key"] == "no_reply:42:2026-09-14"
    assert row["connection_id"] == "crm-A"
    assert row["payload"]["contact_name"] == "Marina López"

    _refresh(store, hs)
    assert len(_signals(store)) == 1

    hs.assoc["emails"]["42"] = ["901", "1042"]
    hs.objects["emails"]["1042"] = _email("1042", _days_ago(1), direction="INCOMING_EMAIL", owner="")
    _refresh(store, hs)
    [row] = _signals(store)
    assert row["status"] == "resolved"
    assert row["previous_status"] == "pending"
    assert row["version"] == 2


def test_a_dismissed_card_stays_dismissed_after_the_next_run():
    store, hs = FakeSupabase(), _scenario()
    _refresh(store, hs)
    store.tables["action_signals"][0]["status"] = "dismissed"
    _refresh(store, hs)
    [row] = _signals(store)
    assert row["status"] == "dismissed"


def test_a_failed_read_does_not_resolve_what_was_there():
    store, hs = FakeSupabase(), _scenario()
    _refresh(store, hs)
    hs.fail = {"/crm/v3/objects/emails/search": {"error_kind": "403"}}
    result = _refresh(store, hs)
    assert result["coverage"] == "forbidden"
    [row] = _signals(store)
    assert row["status"] == "pending"


def test_a_partial_read_inserts_what_it_proved_and_resolves_nothing():
    store, hs = FakeSupabase(), _scenario()
    store.tables["action_signals"].append({
        "id": "old",
        "company_id": COMPANY,
        "user_id": USER,
        "connection_id": "crm-A",
        "contact_id": "77",
        "type": "no_reply",
        "dedupe_key": "no_reply:77:2026-09-10",
        "status": "pending",
        "version": 1,
        "payload": {},
    })
    hs.page_size = 1
    result = refresh_no_reply(
        store,
        company_id=COMPANY,
        user_id=USER,
        rep_email=REP,
        connection=CONNECTION,
        fetch=hs,
        now=NOW,
        tz_name=MADRID,
        max_pages=1,
    )
    assert result["coverage"] == "partial"
    statuses = {row["contact_id"]: row["status"] for row in _signals(store)}
    assert statuses == {"77": "pending", "42": "pending"}


def test_a_reassigned_contact_resolves_the_card():
    store, hs = FakeSupabase(), _scenario()
    _refresh(store, hs)
    hs.contacts["42"]["hubspot_owner_id"] = "o2"
    _refresh(store, hs)
    [row] = _signals(store)
    assert row["status"] == "resolved"


def test_a_later_vocify_memo_or_a_future_commitment_suppresses_the_card():
    store, hs = FakeSupabase(), _scenario()
    store.tables["memos"] = [{
        "id": "memo-9",
        "company_id": COMPANY,
        "hubspot_contact_id": "42",
        "created_at": _days_ago(3).isoformat(),
        "extraction": {},
    }]
    _refresh(store, hs)
    assert _signals(store) == []

    store.tables["memos"] = [{
        "id": "memo-8",
        "company_id": COMPANY,
        "hubspot_contact_id": "42",
        "created_at": _days_ago(20).isoformat(),
        "extraction": {"intelligence": {"commitments": [{
            "kind": "call",
            "origin": "prospect_request",
            "text": "Llamar en dos semanas",
            "due_at": (NOW + timedelta(days=2)).isoformat(),
        }]}},
    }]
    _refresh(store, hs)
    assert _signals(store) == []


def test_an_earlier_vocify_memo_counts_as_the_prior_conversation():
    store, hs = FakeSupabase(), _scenario()
    store.tables["memos"] = [{
        "id": "memo-7",
        "company_id": COMPANY,
        "hubspot_contact_id": "45",
        "created_at": _days_ago(20).isoformat(),
        "extraction": {},
    }]
    _refresh(store, hs)
    assert {row["contact_id"] for row in _signals(store)} == {"42", "45"}


def test_pipedrive_refresh_is_unavailable_and_writes_nothing():
    store = FakeSupabase()
    result = refresh_no_reply(
        store,
        company_id=COMPANY,
        user_id=USER,
        rep_email=REP,
        connection={**CONNECTION, "provider": "pipedrive"},
        fetch=lambda _request: (_ for _ in ()).throw(AssertionError("no call")),
        now=NOW,
        tz_name=MADRID,
    )
    assert (result["coverage"], result["reason"]) == ("unavailable", "not_available_for_pipedrive")
    assert store.tables["action_signals"] == []


# --- GET /today behind the flag ---------------------------------------------------------------


@pytest.fixture
def today_store(monkeypatch):
    store = FakeSupabase()
    store.tables["crm_connections"] = [dict(CONNECTION)]
    hs = _scenario()
    built: list[dict] = []

    def factory(connection):
        built.append(connection)
        return hs

    feature_flags.clear_cache()
    today_api.reset_no_reply_runs()
    today_api.set_today_tasks(lambda _company: ([], "complete"))
    today_api.set_no_reply_fetch(factory)
    today_api.set_no_reply_rep_email(lambda _supabase, _company, _user: REP)
    monkeypatch.setattr(today_api, "_CLOCK", [NOW])
    try:
        yield store, hs, built
    finally:
        today_api.set_today_tasks(None)
        today_api.set_no_reply_fetch(None)
        today_api.set_no_reply_rep_email(None)
        today_api.reset_no_reply_runs()
        feature_flags.clear_cache()


def _client(store):
    app = FastAPI()
    app.include_router(today_api.router)
    app.dependency_overrides[get_membership] = lambda: Membership(
        id="m", company_id=COMPANY, user_id=USER, role="member", status="active",
    )
    app.dependency_overrides[get_supabase] = lambda: store
    return TestClient(app)


def test_flag_off_today_is_unchanged_and_reads_no_email(today_store, monkeypatch):
    store, _hs, built = today_store
    monkeypatch.setattr(settings, NO_REPLY_FLAG, False)
    body = _client(store).get("/api/v1/today").json()
    assert built == []
    assert set(body["coverage"]) == {"intelligence", "crm_tasks"}
    assert body["items"] == []
    assert body["pulse"] == 0


def test_flag_on_for_the_company_shows_the_card_and_reports_email_coverage(today_store, monkeypatch):
    store, hs, built = today_store
    monkeypatch.setattr(settings, NO_REPLY_FLAG, False)
    store.tables["company_feature_flags"] = [{"company_id": COMPANY, "flag": NO_REPLY_FLAG, "enabled": True}]
    client = _client(store)
    body = client.get("/api/v1/today").json()
    assert body["coverage"]["crm_emails"] == "complete"
    [item] = body["items"]
    assert item["type"] == "no_reply"
    assert item["contact_id"] == "42"
    assert item["contact_name"] == "Marina López"
    assert item["reason"] == "Le escribiste el 14 sep («Propuesta Q4») y no ha respondido."
    assert item["id"]

    requests = len(hs.requests)
    again = client.get("/api/v1/today").json()
    assert len(hs.requests) == requests
    assert again["coverage"]["crm_emails"] == "complete"
    assert len(built) == 1


def test_after_an_hour_the_read_runs_behind_the_response_and_a_reply_clears_the_card(today_store, monkeypatch):
    store, hs, _built = today_store
    monkeypatch.setattr(settings, NO_REPLY_FLAG, True)
    client = _client(store)
    assert [item["type"] for item in client.get("/api/v1/today").json()["items"]] == ["no_reply"]

    hs.assoc["emails"]["42"] = ["901", "1042"]
    hs.objects["emails"]["1042"] = _email("1042", _days_ago(0, hour=7), direction="INCOMING_EMAIL", owner="")
    monkeypatch.setattr(today_api, "_CLOCK", [NOW + timedelta(minutes=59)])
    assert [item["type"] for item in client.get("/api/v1/today").json()["items"]] == ["no_reply"]
    assert _signals(store, "pending")

    monkeypatch.setattr(today_api, "_CLOCK", [NOW + timedelta(hours=1)])
    client.get("/api/v1/today")
    assert [row["status"] for row in _signals(store)] == ["resolved"]
    assert client.get("/api/v1/today").json()["items"] == []


def test_flag_on_with_a_missing_scope_keeps_the_list_and_says_it_is_incomplete(today_store, monkeypatch):
    store, hs, _built = today_store
    monkeypatch.setattr(settings, NO_REPLY_FLAG, True)
    hs.fail = {"/crm/v3/objects/emails/search": {"error_kind": "403"}}
    body = _client(store).get("/api/v1/today").json()
    assert body["coverage"]["crm_emails"] == "forbidden"
    assert body["pulse"] is None


def test_flag_on_with_pipedrive_says_email_is_unavailable(today_store, monkeypatch):
    store, _hs, built = today_store
    monkeypatch.setattr(settings, NO_REPLY_FLAG, True)
    store.tables["crm_connections"] = [{**CONNECTION, "provider": "pipedrive"}]
    body = _client(store).get("/api/v1/today").json()
    assert body["coverage"]["crm_emails"] == "unavailable"
    assert body["pulse"] is None
    assert built == []
