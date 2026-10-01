"""A desktop call recording is tied to the call HubSpot logs for it, never processed twice."""

from datetime import datetime, timezone
from types import SimpleNamespace

from app.services.live_calls import linking
from app.services.live_calls.linking import (
    LINK_WINDOW_SECONDS,
    link_desktop_call,
    link_desktop_calls_for_contact,
    match_calls_to_memos,
)

T0 = 1_790_000_000  # epoch seconds


def _iso(epoch):
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()


def _call(cid, start, duration=None):
    return {"call_id": cid, "timestamp_ms": start * 1000, "duration_ms": None if duration is None else duration * 1000}


def _memo(mid, start, duration=0, contact="901"):
    return {"id": mid, "capture_started_at": _iso(start), "audio_duration": duration, "hubspot_contact_id": contact}


def test_matches_the_call_that_started_with_the_capture():
    assert match_calls_to_memos([_call("hs-1", T0 + 4, 300)], [_memo("m1", T0, 296)]) == {"hs-1": "m1"}


def test_nothing_outside_the_window():
    assert match_calls_to_memos([_call("hs-1", T0 + LINK_WINDOW_SECONDS + 1)], [_memo("m1", T0)]) == {}


def test_answered_call_beats_a_no_answer_redial_for_a_long_recording():
    calls = [_call("no-answer", T0, 0), _call("answered", T0 + 90, 300)]
    # The rep hit record at the first attempt and kept recording through the redial.
    assert match_calls_to_memos(calls, [_memo("m1", T0, 390)]) == {"answered": "m1"}


def test_two_recordings_two_calls_pair_up():
    calls = [_call("a", T0, 120), _call("b", T0 + 200, 60)]
    memos = [_memo("m-a", T0 + 2, 118), _memo("m-b", T0 + 201, 61)]
    assert match_calls_to_memos(calls, memos) == {"a": "m-a", "b": "m-b"}


def test_a_coin_flip_links_nothing():
    calls = [_call("a", T0 - 10), _call("b", T0 + 10)]
    assert match_calls_to_memos(calls, [_memo("m1", T0)]) == {}


def test_calls_or_memos_missing_times_are_skipped():
    assert match_calls_to_memos([{"call_id": "a", "timestamp_ms": None}], [_memo("m1", T0)]) == {}
    assert match_calls_to_memos([_call("a", T0)], [{"id": "m1", "capture_started_at": None}]) == {}


class _Query:
    def __init__(self, db, table):
        self.db, self.table = db, table
        self.filters, self.ins, self.nulls, self.gte_, self.neqs = {}, {}, set(), {}, {}
        self.payload = None

    def select(self, _cols):
        return self

    def update(self, payload):
        self.payload = payload
        return self

    def eq(self, col, val):
        self.filters[col] = val
        return self

    def in_(self, col, vals):
        self.ins[col] = {str(v) for v in vals}
        return self

    def is_(self, col, _null):
        self.nulls.add(col)
        return self

    def gte(self, col, val):
        self.gte_[col] = val
        return self

    def limit(self, _n):
        return self

    def or_(self, expression):
        # Only the shape linking uses: "<col>.is.null,<col>.neq.<value>".
        is_null, not_equal = expression.split(",")
        col = is_null.split(".")[0]
        self.neqs[col] = not_equal.split(".neq.")[1]
        return self

    def _rows(self):
        out = []
        for row in self.db.memos:
            if any(row.get(k) != v for k, v in self.filters.items()):
                continue
            if any(str(row.get(k)) not in v for k, v in self.ins.items()):
                continue
            if any(row.get(k) is not None for k in self.nulls):
                continue
            if any(row.get(k) is not None and row.get(k) == v for k, v in self.neqs.items()):
                continue
            if any(str(row.get(k) or "") < v for k, v in self.gte_.items()):
                continue
            out.append(row)
        return out

    def execute(self):
        rows = self._rows()
        if self.payload is not None:
            new_call = self.payload.get("hubspot_engagement_id")
            if any(r.get("hubspot_engagement_id") == new_call for r in self.db.memos):
                raise RuntimeError('duplicate key value violates unique constraint "idx_memos_hubspot_engagement_id_unique"')
            for row in rows:
                row.update(self.payload)
        return SimpleNamespace(data=rows)


class _DB:
    def __init__(self, memos):
        self.memos = memos

    def table(self, name):
        assert name == "memos"
        return _Query(self, name)


def _row(mid, start, duration, **over):
    return {
        "id": mid, "user_id": "rep-1", "source": "desktop", "interaction_kind": "call",
        "hubspot_contact_id": "901", "hubspot_engagement_id": None,
        "capture_status": "complete", "capture_started_at": _iso(start), "audio_duration": duration, **over,
    }


def _recent(offset=0):
    return int(datetime.now(timezone.utc).timestamp()) - 600 + offset


def test_contact_recordings_link_to_the_reps_desktop_memo():
    start = _recent()
    db = _DB([_row("m1", start, 300)])
    links = link_desktop_calls_for_contact(db, "rep-1", "901", [_call("hs-1", start + 3, 297)])
    assert links == {"hs-1": "m1"}
    assert db.memos[0]["hubspot_engagement_id"] == "hs-1"


def test_only_the_reps_own_desktop_call_memos_are_candidates():
    start = _recent()
    db = _DB([
        _row("other-rep", start, 300, user_id="rep-2"),
        _row("not-desktop", start, 300, source="hubspot_call"),
        _row("a-meeting", start, 300, interaction_kind="meeting"),
        _row("other-contact", start, 300, hubspot_contact_id="555"),
        _row("already-linked", start, 300, hubspot_engagement_id="hs-old"),
        _row("still-recording", start, 300, capture_status="recording"),
    ])
    assert link_desktop_calls_for_contact(db, "rep-1", "901", [_call("hs-1", start, 300)]) == {}


def test_recorder_uploads_without_capture_status_link():
    start = _recent()
    db = _DB([_row("upload", start, 300, capture_status=None)])
    assert link_desktop_calls_for_contact(db, "rep-1", "901", [_call("hs-1", start + 2, 300)]) == {"hs-1": "upload"}


def test_a_call_that_already_has_a_memo_is_left_alone():
    start = _recent()
    db = _DB([_row("m1", start, 300), _row("hubspot-memo", start, 300, source="hubspot_call", hubspot_engagement_id="hs-1")])
    assert link_desktop_calls_for_contact(db, "rep-1", "901", [_call("hs-1", start, 300)]) == {}
    assert db.memos[0]["hubspot_engagement_id"] is None


def test_lost_race_on_the_unique_index_is_skipped():
    start = _recent()
    db = _DB([_row("m1", start, 300)])
    original = linking._calls_with_memos
    try:
        linking._calls_with_memos = lambda *_a, **_k: set()
        db.memos.append(_row("late", start - 9999, 1, source="hubspot_call", hubspot_engagement_id="hs-1"))
        assert link_desktop_calls_for_contact(db, "rep-1", "901", [_call("hs-1", start, 300)]) == {}
    finally:
        linking._calls_with_memos = original


def test_single_call_link_for_the_processing_path_and_db_errors_never_raise():
    start = _recent()
    db = _DB([_row("m1", start, 300)])
    assert link_desktop_call(db, "rep-1", _call("hs-1", start + 2, 300), ["901", "902"]) == "m1"

    class _Broken:
        def table(self, _):
            raise RuntimeError("db down")

    assert link_desktop_call(_Broken(), "rep-1", _call("hs-2", start), ["901"]) is None
    assert link_desktop_calls_for_contact(_Broken(), "rep-1", "901", [_call("hs-2", start)]) == {}


async def test_hubspot_processing_reuses_the_desktop_memo(monkeypatch):
    from app.services.hubspot import call_processor

    async def associations(_client, _cid):
        return [], ["901"]

    async def engagement(_client, cid):
        return {"id": cid, "properties": {"hs_timestamp": str(start * 1000), "hs_call_duration": "300000"}}

    start = _recent()
    db = _DB([_row("m1", start, 300)])
    monkeypatch.setattr(call_processor, "get_call_associations", associations)
    monkeypatch.setattr(call_processor, "get_call_engagement", engagement)
    monkeypatch.setattr(call_processor, "HubSpotClient", lambda *_a, **_k: object())

    memo_id, created = await call_processor.initiate_hubspot_call_memo(db, "rep-1", "hs-9", "token")
    assert (memo_id, created) == ("m1", False)
    assert db.memos[0]["hubspot_engagement_id"] == "hs-9"


async def test_hubspot_processing_survives_a_failed_engagement_read(monkeypatch):
    from app.services.hubspot import call_processor

    async def associations(_client, _cid):
        return [], ["901"]

    async def engagement(_client, _cid):
        raise RuntimeError("HubSpot 500")

    monkeypatch.setattr(call_processor, "get_call_associations", associations)
    monkeypatch.setattr(call_processor, "get_call_engagement", engagement)
    monkeypatch.setattr(call_processor, "HubSpotClient", lambda *_a, **_k: object())
    monkeypatch.setattr(call_processor, "pin_playbook_on_row", lambda _sb, row: row)
    monkeypatch.setattr(call_processor, "with_author_company", lambda _sb, row: row)

    inserted = []

    class _Store(_DB):
        def table(self, name):
            q = super().table(name)
            q.insert = lambda row: SimpleNamespace(execute=lambda: (inserted.append(row), SimpleNamespace(data=[{"id": "new"}]))[1])
            return q

    memo_id, created = await call_processor.initiate_hubspot_call_memo(_Store([]), "rep-1", "hs-9", "token")
    assert (memo_id, created) == ("new", True)
    assert inserted[0]["hubspot_engagement_id"] == "hs-9"


async def test_recordings_list_links_on_contact_pages_only(monkeypatch):
    from app.api import crm

    seen = []

    async def recordings(_client, object_type, record_id):
        return [_call("hs-1", T0)]

    async def present(_user, _sb, items, _author):
        return items

    monkeypatch.setattr(crm, "get_hubspot_client_from_connection", lambda *_a: object())
    monkeypatch.setattr(crm, "list_recordings_for_record", recordings)
    monkeypatch.setattr(crm, "_present_recordings", present)
    monkeypatch.setattr(crm, "link_desktop_calls_for_contact", lambda _sb, user, contact, items: seen.append((user, contact)))

    await crm._recordings_for_record("rep-1", object(), "contacts", "901")
    await crm._recordings_for_record("rep-1", object(), "deals", "55")
    assert seen == [("rep-1", "901")]
