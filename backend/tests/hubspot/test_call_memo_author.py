"""A HubSpot call's memo: whose it is, that a second click finds it, and that a call under 30s is kept as no
answer instead of transcribed (2026-10-28: a manager's clicks filed a rep's calls under the manager, and the
rep's own click then hit the unique index as a 500 the browser read as "Failed to fetch")."""

import asyncio

import pytest

from app.services.hubspot import auto_sync, call_processor
from app.services.hubspot.call_processor import CallMemoElsewhere, existing_call_memo_id
from app.services.hubspot.calls import is_short_call, list_recent_recordings, short_call_outcome


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, db, table):
        self.db, self.table, self.filters, self.single_row, self.payload = db, table, [], False, None
        self.op = "select"

    def select(self, *_a, **_k):
        return self

    def eq(self, key, value):
        self.filters.append((key, str(value)))
        return self

    def limit(self, *_a):
        return self

    def single(self):
        self.single_row = True
        return self

    def insert(self, row):
        self.op, self.payload = "insert", row
        return self

    def update(self, row):
        self.op, self.payload = "update", row
        return self

    def _matches(self, row):
        return all(str(row.get(k)) == v for k, v in self.filters)

    def execute(self):
        rows = self.db.rows.setdefault(self.table, [])
        if self.op == "insert":
            if any(r.get("hubspot_engagement_id") == self.payload.get("hubspot_engagement_id") for r in rows):
                raise RuntimeError('duplicate key value violates unique constraint (23505)')
            row = {"id": f"memo-{len(rows) + 1}", **self.payload}
            rows.append(row)
            return _Result([row])
        if self.op == "update":
            for row in rows:
                if self._matches(row):
                    row.update(self.payload)
            return _Result([])
        found = [r for r in rows if self._matches(r)]
        return _Result(found[0] if self.single_row and found else found)


class FakeDb:
    def __init__(self, memos=None):
        self.rows = {"memos": list(memos or [])}

    def table(self, name):
        return _Query(self, name)


@pytest.fixture
def companies(monkeypatch):
    company_of = {"toni": "acme", "dani": "acme", "eve": "other"}
    monkeypatch.setattr(
        "app.services.company.get_company_id_for_user", lambda _db, uid: company_of.get(uid)
    )


@pytest.fixture
def hubspot(monkeypatch):
    """A call with no associations and no desktop recording; `props` is what HubSpot holds for it."""
    state = {"props": {"hs_call_duration": "386000", "hs_call_recording_url": "https://rec"}}

    async def associations(_client, _cid):
        return [], []

    async def engagement(_client, cid):
        return {"id": cid, "properties": state["props"]}

    monkeypatch.setattr(call_processor, "get_call_associations", associations)
    monkeypatch.setattr(call_processor, "get_call_engagement", engagement)
    monkeypatch.setattr(call_processor, "with_author_company", lambda _db, row: row)
    monkeypatch.setattr(call_processor, "pin_playbook_on_row", lambda _db, row: row)
    return state


@pytest.fixture
def background(monkeypatch):
    started = []

    async def run(memo_id, user_id, *_a, **_k):
        started.append((memo_id, user_id))

    monkeypatch.setattr(call_processor, "process_hubspot_call_background", run)
    return started


def test_the_calls_memo_is_found_whoever_on_the_team_it_is_filed_under(companies):
    db = FakeDb([{"id": "m1", "user_id": "dani", "company_id": "acme", "hubspot_engagement_id": "c1"}])
    assert existing_call_memo_id(db, "dani", "c1") == "m1"
    assert existing_call_memo_id(db, "toni", "c1") == "m1"
    assert existing_call_memo_id(db, "toni", "c2") is None


def test_a_memo_in_another_workspace_is_not_handed_out(companies):
    db = FakeDb([{"id": "m1", "user_id": "eve", "company_id": "other", "hubspot_engagement_id": "c1"}])
    with pytest.raises(CallMemoElsewhere):
        existing_call_memo_id(db, "toni", "c1")


def test_a_second_click_on_a_teammates_call_returns_its_memo_instead_of_failing(companies, hubspot, background):
    db = FakeDb([{"id": "m1", "user_id": "dani", "company_id": "acme", "hubspot_engagement_id": "c1",
                  "status": "pending_review"}])
    result = asyncio.run(call_processor.enqueue_hubspot_call_process(db, "toni", "c1", "token"))
    assert result["memo_id"] == "m1"
    assert result["processing_started"] is False
    assert len(db.rows["memos"]) == 1
    assert background == []


def test_a_long_call_is_transcribed_under_the_rep_it_is_filed_for(companies, hubspot, background):
    db = FakeDb()
    result = asyncio.run(call_processor.enqueue_hubspot_call_process(db, "toni", "c1", "token"))
    assert result["created"] is True and result["processing_started"] is True
    assert db.rows["memos"][0]["user_id"] == "toni"


@pytest.mark.parametrize("ms", ["2000", "26000", "29900"])
def test_a_call_under_30s_is_kept_as_no_answer_and_never_transcribed(companies, hubspot, background, ms):
    hubspot["props"] = {"hs_call_duration": ms, "hs_call_recording_url": "https://rec"}
    db = FakeDb()
    result = asyncio.run(call_processor.enqueue_hubspot_call_process(db, "toni", "c1", "token"))
    memo = db.rows["memos"][0]
    assert background == []
    assert result["status"] == "pending_review"
    assert memo["screening_outcome"] == "no_response"
    assert memo["status"] == "pending_review"
    assert memo["audio_duration"] == int(ms) / 1000


def test_a_call_the_rep_marks_as_voicemail_is_kept_as_that(companies, hubspot, background):
    db = FakeDb()
    asyncio.run(call_processor.enqueue_hubspot_call_process(db, "toni", "c1", "token", unanswered="voicemail"))
    assert db.rows["memos"][0]["screening_outcome"] == "voicemail"
    assert background == []


def test_marking_does_not_overwrite_a_call_already_read(companies, hubspot, background):
    db = FakeDb([{"id": "m1", "user_id": "toni", "company_id": "acme", "hubspot_engagement_id": "c1",
                  "status": "approved", "screening_outcome": "connected"}])
    result = asyncio.run(call_processor.enqueue_hubspot_call_process(db, "toni", "c1", "token", unanswered="no_response"))
    assert result["status"] == "approved"
    assert db.rows["memos"][0]["screening_outcome"] == "connected"


def test_short_means_known_and_under_30s():
    assert is_short_call({"hs_call_duration": "29000"}) is True
    assert is_short_call({"hs_call_duration": "30000"}) is False
    assert is_short_call({"hs_call_duration": "0"}) is False  # unknown length: the transcript decides
    assert is_short_call({}) is False
    assert short_call_outcome({"hs_call_status": "COMPLETED"}) == "no_response"


# --- the recording webhook -------------------------------------------------------------------------------

EVENT = {"subscriptionType": "engagement.propertyChange", "propertyName": "hs_call_recording_url",
         "propertyValue": "https://rec", "portalId": 1, "objectId": 9}


@pytest.fixture
def webhook(monkeypatch):
    state = {"auto": False, "pref": False, "ms": "5000", "enqueued": []}

    async def fresh(_db, conn):
        return conn

    async def props(_token, _cid):
        return {"hs_call_duration": state["ms"]}

    async def user(*_a, **_k):
        return "toni"

    async def enqueue(_db, user_id, call_id, _token):
        state["enqueued"].append((user_id, call_id))
        return {"memo_id": "m1", "status": "pending_review"}

    monkeypatch.setattr(auto_sync, "find_hubspot_connection_for_portal", lambda *_a: {"id": "conn", "access_token": "t"})
    monkeypatch.setattr(auto_sync, "auto_sync_enabled_for_connection", lambda *_a: state["auto"])
    monkeypatch.setattr(auto_sync, "read_crm_call_recordings_preference", lambda *_a: state["pref"])
    monkeypatch.setattr("app.services.hubspot.token_refresh.ensure_hubspot_connection_tokens_fresh", fresh)
    monkeypatch.setattr(auto_sync, "call_properties", props)
    monkeypatch.setattr(auto_sync, "resolve_user_for_hubspot_call", user)
    monkeypatch.setattr("app.services.hubspot.call_processor.enqueue_hubspot_call_process", enqueue)
    return state


def test_the_webhook_keeps_a_short_call_as_no_answer_whatever_the_switches(webhook):
    assert asyncio.run(auto_sync.handle_hubspot_recording_events(None, [EVENT])) == (1, 0)
    assert webhook["enqueued"] == [("toni", "9")]


def test_the_webhook_still_leaves_a_long_call_to_the_button_when_auto_sync_is_off(webhook):
    webhook["ms"] = "386000"
    assert asyncio.run(auto_sync.handle_hubspot_recording_events(None, [EVENT])) == (0, 1)
    assert webhook["enqueued"] == []


# --- the recent calls search --------------------------------------------------------------------------


class _Search:
    def __init__(self, pages):
        self.pages, self.bodies = pages, []

    async def post(self, _path, data):
        self.bodies.append(data)
        return self.pages[len(self.bodies) - 1]


def _call(n):
    return {"id": str(n), "properties": {"hs_call_recording_url": "https://rec", "hs_timestamp": str(1_800_000_000_000 - n)}}


def test_a_busy_day_is_read_past_the_first_hubspot_page_for_the_teams_owners():
    client = _Search([
        {"results": [_call(n) for n in range(100)], "paging": {"next": {"after": "100"}}},
        {"results": [_call(n) for n in range(100, 130)]},
    ])
    items = asyncio.run(list_recent_recordings(client, limit=200, owner_ids=["1", "2"], since_ms=123))
    assert len(items) == 130
    filters = client.bodies[0]["filterGroups"][0]["filters"]
    assert {"propertyName": "hubspot_owner_id", "operator": "IN", "values": ["1", "2"]} in filters
    assert {"propertyName": "hs_timestamp", "operator": "GTE", "value": "123"} in filters
    assert client.bodies[1]["after"] == "100"


def test_the_old_newest_20_still_reads_one_page():
    client = _Search([{"results": [_call(n) for n in range(20)], "paging": {"next": {"after": "20"}}}])
    assert len(asyncio.run(list_recent_recordings(client, limit=20))) == 20
    assert len(client.bodies) == 1


# --- the Transcribe / mark endpoints ------------------------------------------------------------------

from fastapi import HTTPException  # noqa: E402

from app.api import crm  # noqa: E402


@pytest.fixture
def endpoint(monkeypatch):
    state = {"author": "toni", "filed": None, "enqueued": []}

    async def engagement(_client, _cid):
        return {"properties": {"hs_call_recording_url": "https://rec", "hubspot_owner_id": "36995373"}}

    async def author(*_a):
        return state["author"]

    async def enqueue(_db, user_id, call_id, _token, *, unanswered=None):
        state["enqueued"].append((user_id, call_id, unanswered))
        return {"memo_id": "m1", "status": "transcribing"}

    monkeypatch.setattr(crm, "get_hubspot_client_from_connection", lambda *_a: object())
    monkeypatch.setattr(crm, "_hubspot_access_token", lambda *_a: "token")
    monkeypatch.setattr(crm, "get_call_engagement", engagement)
    monkeypatch.setattr(crm, "_call_author_user_id", author)
    monkeypatch.setattr(crm, "call_memo_row", lambda *_a: state["filed"])
    monkeypatch.setattr(crm, "enqueue_hubspot_call_process", enqueue)
    return state


def test_a_manager_s_click_files_the_call_under_the_rep_who_made_it(endpoint):
    asyncio.run(crm._start_hubspot_call("c1", None, "dani"))
    assert endpoint["enqueued"] == [("toni", "c1", None)]


def test_a_rep_s_click_on_a_call_filed_under_a_teammate_says_so(endpoint):
    endpoint["filed"] = {"id": "m1", "user_id": "dani"}
    with pytest.raises(HTTPException) as err:
        asyncio.run(crm._start_hubspot_call("c1", None, "toni"))
    assert err.value.status_code == 409
    assert err.value.detail["code"] == "filed_under_teammate"
    assert endpoint["enqueued"] == []


def test_marking_passes_the_outcome_through(endpoint):
    asyncio.run(crm._start_hubspot_call("c1", None, "toni", unanswered="voicemail"))
    assert endpoint["enqueued"] == [("toni", "c1", "voicemail")]
