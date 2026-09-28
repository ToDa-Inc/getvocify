"""T12: bell "Feedback" - ready briefs past their highlight time, not yet seen (brief_seen)."""

import os
from datetime import datetime, timezone

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-bell-feedback-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-bell-feedback-32")

from app.services.coaching import brief_preferences
from app.services.reporting.feedback import load_unseen_feedback, mark_feedback_seen, unseen_feedback
from tests.reporting.fake_db import FakeDB

UTC = timezone.utc
COMPANY = "88888888-8888-8888-8888-888888888888"
USER = "99999999-9999-9999-9999-999999999999"
NOW = datetime(2026, 9, 25, 16, 0, tzinfo=UTC)

IMMEDIATE = {"highlight_mode": "immediate", "delay_minutes": None, "end_of_day": None, "timezone": "Europe/Madrid"}


def _brief(memo_id, *, status="ready", revision_seq=1, created_at="2026-09-25T10:00:00+00:00"):
    return {
        "memo_id": memo_id,
        "input_revision": "r1",
        "revision_seq": revision_seq,
        "status": status,
        "body": {},
        "created_at": created_at,
    }


def test_unseen_feedback_keeps_only_ready_past_highlight_and_unseen():
    rows = [
        _brief("m-ready"),
        _brief("m-pending", status="pending"),
        _brief("m-future", created_at="2026-09-25T15:59:00+00:00"),
    ]
    items = unseen_feedback(rows, seen_memo_ids={"m-future"}, now=NOW, preference=IMMEDIATE)
    assert [item["memo_id"] for item in items] == ["m-ready"]


def test_only_the_latest_revision_of_a_memo_counts():
    rows = [_brief("m-1", revision_seq=1, status="pending"), _brief("m-1", revision_seq=2, status="ready")]
    items = unseen_feedback(rows, seen_memo_ids=set(), now=NOW, preference=IMMEDIATE)
    assert [item["memo_id"] for item in items] == ["m-1"]


def test_deferred_preference_delays_when_it_counts():
    deferred = {"highlight_mode": "deferred", "delay_minutes": 30, "end_of_day": None, "timezone": "Europe/Madrid"}
    rows = [_brief("m-1", created_at="2026-09-25T15:45:00+00:00")]
    assert unseen_feedback(rows, seen_memo_ids=set(), now=NOW, preference=deferred) == []
    later = NOW.replace(hour=16, minute=16)
    items = unseen_feedback(rows, seen_memo_ids=set(), now=later, preference=deferred)
    assert [item["memo_id"] for item in items] == ["m-1"]


def test_load_unseen_feedback_joins_memos_briefs_and_seen(monkeypatch):
    monkeypatch.setattr(brief_preferences, "read_preference", lambda user_id: IMMEDIATE)
    db = FakeDB({
        "memos": [
            {"id": "m-mine", "company_id": COMPANY, "user_id": USER, "created_at": "2026-09-25T09:00:00+00:00"},
            {"id": "m-other-user", "company_id": COMPANY, "user_id": "someone-else", "created_at": "2026-09-25T09:00:00+00:00"},
        ],
        "post_interaction_briefs": [_brief("m-mine"), _brief("m-other-user")],
        "brief_seen": [],
    })
    items = load_unseen_feedback(db, user_id=USER, company_id=COMPANY, now=NOW)
    assert [item["memo_id"] for item in items] == ["m-mine"]


def test_load_unseen_feedback_excludes_already_seen():
    db = FakeDB({
        "memos": [{"id": "m-1", "company_id": COMPANY, "user_id": USER, "created_at": "2026-09-25T09:00:00+00:00"}],
        "post_interaction_briefs": [_brief("m-1")],
        "brief_seen": [{"user_id": USER, "memo_id": "m-1", "seen_at": "2026-09-25T10:00:00+00:00"}],
    })
    assert load_unseen_feedback(db, user_id=USER, company_id=COMPANY, now=NOW) == []


def test_load_unseen_feedback_is_none_when_a_source_fails():
    db = FakeDB({"memos": [], "post_interaction_briefs": [], "brief_seen": []}, fail_tables=("memos",))
    assert load_unseen_feedback(db, user_id=USER, company_id=COMPANY, now=NOW) is None


def test_mark_feedback_seen_upserts_and_is_idempotent():
    db = FakeDB({"brief_seen": []})
    mark_feedback_seen(db, user_id=USER, memo_id="m-1", now=NOW)
    mark_feedback_seen(db, user_id=USER, memo_id="m-1", now=NOW)
    assert len(db.tables["brief_seen"]) == 1
