"""D9: the atomic claim that stops two concurrent requests from both sending the same
reviewed follow-up, plus the "from" sanitization and the per-rep rate limit."""

import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-followup-32b+")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-followup-32b+")

import pytest

from app.services import followup_send as svc

NOW = datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)


class FakeQuery:
    """The same PostgREST-ish fake as test_followup_service.py's, plus `neq`: the OR filter
    claim_send writes needs it to express "not already claimed/sent for this revision"."""

    def __init__(self, rows):
        self.rows, self.filters, self.ors, self.patch, self.n = rows, [], None, None, None

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
        matched = [r for r in self.rows if self._match(r)]
        if self.patch is not None:
            for row in matched:
                row.update(self.patch)
            return SimpleNamespace(data=[dict(r) for r in matched if self._match(r)])
        return SimpleNamespace(data=[dict(r) for r in matched[: self.n or None]])


class FakeClient:
    def __init__(self, tables):
        self.tables = tables

    def table(self, name):
        return FakeQuery(self.tables[name])


def memo_row(**overrides):
    return {"id": "m1", "followup": {"status": "ready", "subject": "Caso", "body": "Hola"}, **overrides}


def client_for(memo):
    return FakeClient({"memos": [memo]})


def test_claim_send_wins_a_fresh_revision():
    memo = memo_row()
    claim, followup = svc.claim_send(client_for(memo), "m1", memo["followup"], "hash-a", "run-1", NOW)
    assert claim == "claimed"
    assert followup["vocify_send_state"] == "sending"
    assert followup["vocify_send_run_id"] == "run-1"
    assert memo["followup"]["vocify_send_hash"] == "hash-a"


def test_a_second_claim_for_the_same_fresh_revision_is_busy():
    memo = memo_row()
    client = client_for(memo)
    first, _ = svc.claim_send(client, "m1", memo["followup"], "hash-a", "run-1", NOW)
    assert first == "claimed"

    second, followup = svc.claim_send(client, "m1", memo["followup"], "hash-a", "run-2", NOW)
    assert second == "busy"
    assert followup["vocify_send_run_id"] == "run-1", "the loser is told about the winner's claim"


def test_a_second_claim_for_a_different_revision_is_free_to_win():
    memo = memo_row()
    client = client_for(memo)
    svc.claim_send(client, "m1", memo["followup"], "hash-a", "run-1", NOW)

    claim, followup = svc.claim_send(client, "m1", memo["followup"], "hash-b", "run-2", NOW)
    assert claim == "claimed"
    assert followup["vocify_send_hash"] == "hash-b"


def test_a_stale_sending_claim_can_be_reclaimed():
    stale_started = (NOW - svc.SEND_STALE - timedelta(seconds=1)).isoformat()
    memo = memo_row(followup={
        "status": "ready", "vocify_send_hash": "hash-a", "vocify_send_state": "sending",
        "vocify_send_run_id": "dead-run", "vocify_sending_started_at": stale_started,
    })
    claim, followup = svc.claim_send(client_for(memo), "m1", memo["followup"], "hash-a", "run-2", NOW)
    assert claim == "claimed"
    assert followup["vocify_send_run_id"] == "run-2"


def test_a_fresh_sending_claim_cannot_be_reclaimed():
    fresh_started = (NOW - timedelta(seconds=5)).isoformat()
    memo = memo_row(followup={
        "status": "ready", "vocify_send_hash": "hash-a", "vocify_send_state": "sending",
        "vocify_send_run_id": "live-run", "vocify_sending_started_at": fresh_started,
    })
    claim, _ = svc.claim_send(client_for(memo), "m1", memo["followup"], "hash-a", "run-2", NOW)
    assert claim == "busy"


def test_a_failed_claim_can_be_reclaimed_immediately():
    memo = memo_row(followup={
        "status": "ready", "vocify_send_hash": "hash-a", "vocify_send_state": "failed",
        "vocify_send_run_id": "dead-run", "vocify_sending_started_at": NOW.isoformat(),
    })
    claim, _ = svc.claim_send(client_for(memo), "m1", memo["followup"], "hash-a", "run-2", NOW)
    assert claim == "claimed"


def test_finish_send_is_ignored_once_the_run_no_longer_owns_the_claim():
    memo = memo_row(followup={
        "status": "ready", "vocify_send_hash": "hash-a", "vocify_send_state": "sending",
        "vocify_send_run_id": "other-run",
    })
    client = client_for(memo)
    svc.finish_send(client, "m1", "run-1", {"status": "sent", "vocify_send_state": "sent"})
    assert memo["followup"]["vocify_send_state"] == "sending", "not this call's claim to finish"


def test_finish_send_writes_when_it_owns_the_claim():
    memo = memo_row(followup={
        "status": "ready", "vocify_send_hash": "hash-a", "vocify_send_state": "sending",
        "vocify_send_run_id": "run-1",
    })
    client = client_for(memo)
    svc.finish_send(client, "m1", "run-1", {"status": "sent", "vocify_send_state": "sent"})
    assert memo["followup"]["vocify_send_state"] == "sent"


def test_display_name_is_sanitized_and_quoted(monkeypatch):
    captured = {}

    class FakeResendClient:
        async def send_email(self, *_args, **kwargs):
            captured.update(kwargs)
            return {"id": "email-1"}

    monkeypatch.setattr(svc, "get_resend_client", lambda: FakeResendClient())
    monkeypatch.setattr("app.config.settings.RESEND_FROM_EMAIL", "hello@getvocify.com", raising=False)

    import asyncio

    outcome = asyncio.run(svc.send_followup_email(
        to="marina@tenes.io", subject="Caso", body="Hola",
        rep_name='Lu"cía\r\n <admin@evil.com>, Pérez;', rep_email="lucia@acme.com",
        idempotency_key="key-1",
    ))
    assert outcome["ok"] is True
    # <, >, ", , and ; are stripped (they could break out of the display-name/address pair
    # or inject another address), and the whole name is quoted.
    assert captured["from_email"] == '"Lucía admin@evil.com Pérez vía Vocify" <hello@getvocify.com>'


def test_subject_crlf_is_collapsed_to_one_line(monkeypatch):
    captured = {}

    class FakeResendClient:
        async def send_email(self, _to, subject, *_args, **kwargs):
            captured["subject"] = subject
            return {"id": "email-1"}

    monkeypatch.setattr(svc, "get_resend_client", lambda: FakeResendClient())

    import asyncio

    asyncio.run(svc.send_followup_email(
        to="marina@tenes.io", subject="Caso\r\nBcc: attacker@evil.com", body="Hola",
        rep_name="Lucía", rep_email="lucia@acme.com", idempotency_key="key-1",
    ))
    assert captured["subject"] == "Caso Bcc: attacker@evil.com"
    assert "\r" not in captured["subject"] and "\n" not in captured["subject"]


def test_rate_limited_caps_sends_per_rep_per_hour():
    svc.reset_rate_limit()
    for _ in range(svc.RATE_LIMIT_MAX):
        assert svc.rate_limited("rep-1", now=NOW) is False
    assert svc.rate_limited("rep-1", now=NOW) is True
    assert svc.rate_limited("rep-2", now=NOW) is False, "the cap is per rep"
    svc.reset_rate_limit()


def test_rate_limit_window_slides():
    svc.reset_rate_limit()
    for _ in range(svc.RATE_LIMIT_MAX):
        svc.rate_limited("rep-1", now=NOW)
    later = NOW + svc.RATE_LIMIT_WINDOW + timedelta(seconds=1)
    assert svc.rate_limited("rep-1", now=later) is False, "old sends have aged out"
    svc.reset_rate_limit()
