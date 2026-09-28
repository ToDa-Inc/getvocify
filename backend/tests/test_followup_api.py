"""GET/POST follow-up: a manager may read, only the author may hand off."""

import os
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-followup-32b+")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-followup-32b+")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import followup as followup_api
from app.config import settings
from app.deps import get_membership, get_supabase, get_user_id
from app.services import feature_flags
from app.services import followup as followup_service
from app.services import followup_send
from app.services.company import Membership
from app.services.followup_send import claim_send, send_hash

AUTHOR = "11111111-1111-1111-1111-111111111111"
MANAGER = "22222222-2222-2222-2222-222222222222"
MEMO_ID = "33333333-3333-3333-3333-333333333333"
EXTRACTION = {
    "summary": "Resumen",
    "contactName": "Marina",
    "contactEmail": "marina@tenes.io",
    "contactPhone": "+34 600 111 222",
}
SAMPLE_A = "Hola Marina, te paso el resumen de lo que vimos esta mañana."
SAMPLE_B = "Buenas, Jorge. Como quedamos, te cuento los tres puntos que me pediste."


def pasted(text):
    return {"text": text, "source": "pasted"}


class MemosQuery:
    """A single-row PostgREST-ish fake for the memos table, so claim_send's atomic claim
    (an UPDATE whose WHERE only matches an unclaimed/stale/failed row, confirmed by a
    read-by-PK afterwards - PostgREST re-applies the filter to RETURNING) behaves for real,
    instead of the unconditional always-applies mock the other tables use here."""

    def __init__(self, store: "Store"):
        self.store = store
        self.filters: list[tuple[str, str]] = []
        self.ors = None
        self.patch = None
        self.n = None

    def select(self, *_a, **_k):
        return self

    def eq(self, column, value):
        self.filters.append((column, str(value)))
        return self

    def or_(self, expression):
        self.ors = expression
        return self

    def limit(self, n, *_a, **_k):
        self.n = n
        return self

    def update(self, patch):
        self.patch = patch
        return self

    @staticmethod
    def _value(row, column):
        if "->>" in column:
            base, key = column.split("->>", 1)
            value = (row.get(base) or {}).get(key)
        else:
            value = row.get(column)
        return None if value is None else str(value)

    def _condition(self, row, cond):
        column, op, value = cond.split(".", 2)
        current = self._value(row, column)
        if op == "is" and value == "null":
            return current is None
        if op == "lt":
            return current is not None and current < value
        if op == "neq":
            return current != value
        if op == "eq":
            return current == value
        raise NotImplementedError(cond)

    def _match(self, row):
        if any(self._value(row, c) != v for c, v in self.filters):
            return False
        return not self.ors or any(self._condition(row, c) for c in self.ors.split(","))

    def execute(self):
        row = self.store.memo
        matched = self._match(row)
        if self.patch is not None:
            if matched:
                row.update(self.patch)
                if "followup" in self.patch:
                    self.store.followup = self.patch["followup"]
            # PostgREST re-applies the PATCH filter to RETURNING: a write that makes the
            # row stop matching (e.g. it is no longer the freshest claim) comes back empty.
            return SimpleNamespace(data=[dict(row)] if matched and self._match(row) else [])
        return SimpleNamespace(data=[dict(row)] if matched else [])


class Store:
    def __init__(self, flags=()):
        self.memo: dict = {}
        self.followup = None
        self.samples = ["hola"]
        self.flags = list(flags)

    def table(self, name):
        if name == "memos":
            return MemosQuery(self)
        query = MagicMock()
        if name == "user_profiles":
            query.execute.return_value = SimpleNamespace(data=[{"writing_samples": list(self.samples)}])
            def update(patch):
                self.samples = patch["writing_samples"]
                return query
            query.update.side_effect = update
        if name == "company_feature_flags":
            query.execute.return_value = SimpleNamespace(data=list(self.flags))
        query.eq.return_value = query
        query.limit.return_value = query
        query.select.return_value = query
        return query


@pytest.fixture(autouse=True)
def fresh_flags(monkeypatch):
    feature_flags.clear_cache()
    followup_send.reset_rate_limit()
    monkeypatch.setattr(settings, "FOLLOWUP_ENABLED", True)
    yield
    feature_flags.clear_cache()
    followup_send.reset_rate_limit()


def client_for(user_id: str, memo: dict, store: Store) -> TestClient:
    store.memo = memo
    app = FastAPI()
    app.include_router(followup_api.router)
    app.include_router(followup_api.listing)
    app.dependency_overrides[get_supabase] = lambda: store
    app.dependency_overrides[get_user_id] = lambda: user_id
    followup_api._require_readable_memo = lambda *_a, **_k: memo
    return TestClient(app)


def ready_memo():
    return {
        "id": MEMO_ID,
        "user_id": AUTHOR,
        "transcript": "Marina: hola",
        "extraction": EXTRACTION,
        "screening_outcome": None,
        "followup": {"status": "ready", "subject": "Caso", "body": "Hola Marina, te paso el caso."},
    }


def test_manager_reads_the_draft_and_cannot_hand_it_off():
    memo = ready_memo()
    store = Store()
    reader = client_for(MANAGER, memo, store)
    got = reader.get(f"/api/v1/memos/{MEMO_ID}/followup")
    assert got.status_code == 200
    assert got.json()["status"] == "ready"
    assert got.json()["subject"] == "Caso"
    denied = reader.post(
        f"/api/v1/memos/{MEMO_ID}/followup",
        json={"action": "sent", "channel": "email", "subject": "Caso", "body": "Hola Marina, te paso el caso."},
    )
    assert denied.status_code == 403
    assert store.followup is None


def test_author_handoff_is_sent_and_an_unready_draft_conflicts():
    memo = ready_memo()
    store = Store()
    author = client_for(AUTHOR, memo, store)
    sent = author.post(
        f"/api/v1/memos/{MEMO_ID}/followup",
        json={"action": "sent", "channel": "email", "subject": "", "body": "Hola Marina, te paso el caso."},
    )
    assert sent.status_code == 200
    body = sent.json()
    assert body["status"] == "sent"
    assert body["channel"] == "email"
    assert "entregado" not in body.get("body", "").lower()
    assert store.followup["status"] == "sent"

    pending = {**memo, "followup": {"status": "generating"}}
    again = client_for(AUTHOR, pending, Store())
    conflict = again.post(
        f"/api/v1/memos/{MEMO_ID}/followup",
        json={"action": "sent", "channel": "email", "body": "Hola"},
    )
    assert conflict.status_code == 409


def test_missing_draft_without_a_running_generation_is_unavailable():
    memo = {
        "id": MEMO_ID,
        "user_id": AUTHOR,
        "transcript": "   ",
        "extraction": EXTRACTION,
        "followup": None,
    }
    got = client_for(AUTHOR, memo, Store()).get(f"/api/v1/memos/{MEMO_ID}/followup")
    assert got.status_code == 200
    assert got.json()["status"] == "unavailable"
    assert UUID(MEMO_ID)


def pending_memo(company_id: str) -> dict:
    return {**ready_memo(), "company_id": company_id, "followup": None}


def test_followup_off_for_the_company_the_get_does_not_schedule(monkeypatch):
    started = []

    async def fake_ensure(_supabase, memo_id, **_kwargs):
        started.append(memo_id)

    monkeypatch.setattr(followup_service, "ensure_followup", fake_ensure)
    off = Store(flags=[{"company_id": "co-off", "flag": "FOLLOWUP_ENABLED", "enabled": False}])
    got = client_for(AUTHOR, pending_memo("co-off"), off).get(f"/api/v1/memos/{MEMO_ID}/followup")
    assert got.json()["status"] == "unavailable"
    assert started == []

    on = client_for(AUTHOR, pending_memo("co-on"), Store()).get(f"/api/v1/memos/{MEMO_ID}/followup")
    assert on.json()["status"] == "generating", "no company row: the safety net works as today"


def test_rep_saves_up_to_three_trimmed_samples_and_reads_them_back():
    store = Store()
    store.samples = ["aprendido"]
    rep = client_for(AUTHOR, ready_memo(), store)
    saved = rep.put("/api/v1/writing-samples", json={"samples": [f"  {SAMPLE_A}  ", "", SAMPLE_B]})
    assert saved.status_code == 200
    assert saved.json() == {"samples": [SAMPLE_A, SAMPLE_B]}
    assert store.samples == ["aprendido", pasted(SAMPLE_A), pasted(SAMPLE_B)]
    assert rep.get("/api/v1/writing-samples").json() == {"samples": [SAMPLE_A, SAMPLE_B]}


@pytest.mark.parametrize("samples", [[SAMPLE_A] * 4, ["Muy corto"], ["x" * 1501]])
def test_a_fourth_or_badly_sized_sample_is_rejected_and_nothing_changes(samples):
    store = Store()
    store.samples = ["aprendido", pasted(SAMPLE_A)]
    before = list(store.samples)
    rejected = client_for(AUTHOR, ready_memo(), store).put("/api/v1/writing-samples", json={"samples": samples})
    assert rejected.status_code == 422
    assert store.samples == before


def test_an_oversized_sample_is_rejected_by_the_model_before_anything_is_read():
    store = Store()
    store.samples = ["aprendido"]
    rejected = client_for(AUTHOR, ready_memo(), store).put("/api/v1/writing-samples", json={"samples": ["x" * 5001]})
    assert rejected.status_code == 422
    assert isinstance(rejected.json()["detail"], list), "pydantic rejected it, not clean_pasted"
    assert store.samples == ["aprendido"]


def test_a_full_sample_with_surrounding_spaces_still_fits():
    store = Store()
    full = "x" * 1500
    saved = client_for(AUTHOR, ready_memo(), store).put("/api/v1/writing-samples", json={"samples": [f"   {full}\n\n"]})
    assert saved.json() == {"samples": [full]}


def test_emptying_removes_pasted_and_keeps_learned():
    store = Store()
    store.samples = ["aprendido", pasted(SAMPLE_A)]
    cleared = client_for(AUTHOR, ready_memo(), store).put("/api/v1/writing-samples", json={"samples": []})
    assert cleared.json() == {"samples": []}
    assert store.samples == ["aprendido"]


def test_an_edit_after_pasting_keeps_the_pasted_samples():
    store = Store()
    store.samples = [pasted(SAMPLE_A)]
    edited = "Marina, adjunto la propuesta que te comenté. Nos vemos el jueves. Un abrazo."
    client_for(AUTHOR, ready_memo(), store).post(
        f"/api/v1/memos/{MEMO_ID}/followup",
        json={"action": "sent", "channel": "email", "subject": "Caso", "body": edited},
    )
    assert store.samples == [pasted(SAMPLE_A), edited]


COMPANY_ID = "co-1"
SEND_BODY = "Hola Marina, te confirmo el jueves a las once."


def send_client_for(user_id: str, memo: dict, store: Store) -> TestClient:
    store.memo = memo
    app = FastAPI()
    app.include_router(followup_api.router)
    app.dependency_overrides[get_supabase] = lambda: store
    app.dependency_overrides[get_user_id] = lambda: user_id
    app.dependency_overrides[get_membership] = lambda: Membership(
        id="mem-1", company_id=COMPANY_ID, user_id=user_id, role="member", status="active",
    )
    followup_api._require_readable_memo = lambda *_a, **_k: memo
    return TestClient(app)


@pytest.fixture(autouse=True)
def stub_send_and_note(monkeypatch):
    """API-level tests only exercise the endpoint's own behaviour (auth, idempotency,
    flag-gating); the Resend call and the CRM note each have their own module tests."""
    calls = {"sent": [], "note": []}

    async def fake_send(**kwargs):
        calls["sent"].append(kwargs)
        return {"ok": True, "email_id": "email-1"}

    async def fake_note(_supabase, _memo, body):
        calls["note"].append(body)
        return {"status": "done", "provider": "hubspot", "note_id": "note-1"}

    monkeypatch.setattr(followup_api, "send_followup_email", fake_send)
    monkeypatch.setattr(followup_api, "log_followup_note", fake_note)
    monkeypatch.setattr(followup_api, "rep_identity", lambda *_a, **_k: ("Lucía Pérez", "lucia@acme.com"))
    return calls


def test_send_is_404_when_the_flag_is_off():
    store = Store()
    resp = send_client_for(AUTHOR, ready_memo(), store).post(
        f"/api/v1/memos/{MEMO_ID}/followup/send",
        json={"to": "marina@tenes.io", "subject": "Caso", "body": SEND_BODY},
    )
    assert resp.status_code == 404


def test_send_requires_the_memos_own_author(stub_send_and_note):
    store = Store(flags=[{"company_id": COMPANY_ID, "flag": "FOLLOWUP_SEND_ENABLED", "enabled": True}])
    resp = send_client_for(MANAGER, ready_memo(), store).post(
        f"/api/v1/memos/{MEMO_ID}/followup/send",
        json={"to": "marina@tenes.io", "subject": "Caso", "body": SEND_BODY},
    )
    assert resp.status_code == 403
    assert stub_send_and_note["sent"] == []


def test_send_conflicts_when_the_draft_is_not_ready(stub_send_and_note):
    store = Store(flags=[{"company_id": COMPANY_ID, "flag": "FOLLOWUP_SEND_ENABLED", "enabled": True}])
    pending = {**ready_memo(), "followup": {"status": "generating"}}
    resp = send_client_for(AUTHOR, pending, store).post(
        f"/api/v1/memos/{MEMO_ID}/followup/send",
        json={"to": "marina@tenes.io", "subject": "Caso", "body": SEND_BODY},
    )
    assert resp.status_code == 409
    assert stub_send_and_note["sent"] == []


def test_send_delivers_via_resend_logs_the_crm_note_and_records_the_sent_hand_off(stub_send_and_note):
    store = Store(flags=[{"company_id": COMPANY_ID, "flag": "FOLLOWUP_SEND_ENABLED", "enabled": True}])
    resp = send_client_for(AUTHOR, ready_memo(), store).post(
        f"/api/v1/memos/{MEMO_ID}/followup/send",
        json={"to": "marina@tenes.io", "subject": "Caso", "body": SEND_BODY},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert (body["status"], body["channel"]) == ("sent", "vocify_email")
    assert stub_send_and_note["sent"] == [{
        "to": "marina@tenes.io", "subject": "Caso", "body": SEND_BODY,
        "rep_name": "Lucía Pérez", "rep_email": "lucia@acme.com",
        "idempotency_key": stub_send_and_note["sent"][0]["idempotency_key"],
    }]
    assert stub_send_and_note["note"] == [SEND_BODY]
    assert store.followup["channel"] == "vocify_email"
    assert store.followup["crm_note"] == {"status": "done", "provider": "hubspot", "note_id": "note-1"}


def test_resending_the_same_reviewed_body_is_a_no_op(stub_send_and_note):
    store = Store(flags=[{"company_id": COMPANY_ID, "flag": "FOLLOWUP_SEND_ENABLED", "enabled": True}])
    client = send_client_for(AUTHOR, ready_memo(), store)
    payload = {"to": "marina@tenes.io", "subject": "Caso", "body": SEND_BODY}
    first = client.post(f"/api/v1/memos/{MEMO_ID}/followup/send", json=payload)
    assert first.status_code == 200

    sent_memo = {**ready_memo(), "followup": store.followup}
    again = send_client_for(AUTHOR, sent_memo, store).post(f"/api/v1/memos/{MEMO_ID}/followup/send", json=payload)
    assert again.status_code == 200
    assert len(stub_send_and_note["sent"]) == 1, "same subject+body: nothing sent a second time"
    assert len(stub_send_and_note["note"]) == 1


def test_an_edited_body_sends_again(stub_send_and_note):
    store = Store(flags=[{"company_id": COMPANY_ID, "flag": "FOLLOWUP_SEND_ENABLED", "enabled": True}])
    client = send_client_for(AUTHOR, ready_memo(), store)
    payload = {"to": "marina@tenes.io", "subject": "Caso", "body": SEND_BODY}
    client.post(f"/api/v1/memos/{MEMO_ID}/followup/send", json=payload)

    sent_memo = {**ready_memo(), "followup": store.followup}
    edited = {**payload, "body": SEND_BODY + " Un saludo."}
    again = send_client_for(AUTHOR, sent_memo, store).post(f"/api/v1/memos/{MEMO_ID}/followup/send", json=edited)
    assert again.status_code == 200
    assert len(stub_send_and_note["sent"]) == 2, "an edited revision is sent again"


def test_a_resend_failure_is_a_502_and_marks_the_claim_failed_not_sent(monkeypatch):
    async def failing_send(**_kwargs):
        return {"ok": False, "error": "resend_not_configured"}

    monkeypatch.setattr(followup_api, "send_followup_email", failing_send)
    monkeypatch.setattr(followup_api, "rep_identity", lambda *_a, **_k: ("Lucía Pérez", "lucia@acme.com"))
    store = Store(flags=[{"company_id": COMPANY_ID, "flag": "FOLLOWUP_SEND_ENABLED", "enabled": True}])
    resp = send_client_for(AUTHOR, ready_memo(), store).post(
        f"/api/v1/memos/{MEMO_ID}/followup/send",
        json={"to": "marina@tenes.io", "subject": "Caso", "body": SEND_BODY},
    )
    assert resp.status_code == 502
    assert store.followup["vocify_send_state"] == "failed"
    assert store.followup["status"] == "ready", "never marked as sent when Resend failed"


def test_send_refuses_when_the_rep_has_no_email_on_file(monkeypatch):
    monkeypatch.setattr(followup_api, "rep_identity", lambda *_a, **_k: ("Lucía Pérez", None))
    store = Store(flags=[{"company_id": COMPANY_ID, "flag": "FOLLOWUP_SEND_ENABLED", "enabled": True}])
    resp = send_client_for(AUTHOR, ready_memo(), store).post(
        f"/api/v1/memos/{MEMO_ID}/followup/send",
        json={"to": "marina@tenes.io", "subject": "Caso", "body": SEND_BODY},
    )
    assert resp.status_code == 422
    assert store.followup is None, "refused before any claim was written"


def test_a_send_already_claimed_by_another_request_is_not_repeated(stub_send_and_note):
    """The core of the concurrency fix: simulate the race deterministically by having
    another request's claim land first (exactly what the endpoint itself calls), then
    drive the HTTP request and check it never touches Resend."""
    store = Store(flags=[{"company_id": COMPANY_ID, "flag": "FOLLOWUP_SEND_ENABLED", "enabled": True}])
    memo = ready_memo()
    store.memo = memo
    revision = send_hash("Caso", SEND_BODY)
    from datetime import datetime, timezone

    claim, _ = claim_send(store, MEMO_ID, memo.get("followup") or {}, revision, "other-run", datetime.now(timezone.utc))
    assert claim == "claimed"

    resp = send_client_for(AUTHOR, memo, store).post(
        f"/api/v1/memos/{MEMO_ID}/followup/send",
        json={"to": "marina@tenes.io", "subject": "Caso", "body": SEND_BODY},
    )
    assert resp.status_code == 200
    assert stub_send_and_note["sent"] == [], "another request already owns this exact revision"
    assert stub_send_and_note["note"] == []


def test_a_failed_crm_note_is_retried_without_resending_the_email(stub_send_and_note):
    store = Store(flags=[{"company_id": COMPANY_ID, "flag": "FOLLOWUP_SEND_ENABLED", "enabled": True}])
    client = send_client_for(AUTHOR, ready_memo(), store)
    payload = {"to": "marina@tenes.io", "subject": "Caso", "body": SEND_BODY}
    client.post(f"/api/v1/memos/{MEMO_ID}/followup/send", json=payload)
    assert store.followup["crm_note"]["status"] == "done"

    # Simulate the note having failed on the first attempt: the retry must repair the
    # note without ever calling send_followup_email again.
    store.followup["crm_note"] = {"status": "failed", "reason": "error"}
    sent_memo = {**ready_memo(), "followup": store.followup}
    again = send_client_for(AUTHOR, sent_memo, store).post(f"/api/v1/memos/{MEMO_ID}/followup/send", json=payload)
    assert again.status_code == 200
    assert len(stub_send_and_note["sent"]) == 1, "the email itself is never resent"
    assert len(stub_send_and_note["note"]) == 2, "the note is retried"
    assert store.followup["crm_note"]["status"] == "done"
