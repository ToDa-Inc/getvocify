"""T12: bell "Tareas" - pending Hoy signals read straight from action_signals."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-bell-tasks-32bb")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-bell-tasks-32bb")

from app.services.reporting.tasks import load_pending_tasks, pending_tasks
from tests.reporting.fake_db import FakeDB

COMPANY = "88888888-8888-8888-8888-888888888888"
USER = "99999999-9999-9999-9999-999999999999"
OTHER = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


def _signal(signal_id, *, type_="commitment_due", status="pending", user_id=USER, updated_at="2026-09-25T10:00:00+00:00"):
    return {
        "id": signal_id,
        "company_id": COMPANY,
        "user_id": user_id,
        "type": type_,
        "status": status,
        "contact_id": "contact-1",
        "memo_id": "memo-1",
        "updated_at": updated_at,
        "created_at": updated_at,
    }


def test_only_pending_commitment_and_callback_types_are_kept():
    rows = [
        _signal("s-1", type_="commitment_due"),
        _signal("s-2", type_="callback_no_answer"),
        _signal("s-3", type_="going_cold"),
        _signal("s-4", type_="commitment_due", status="done"),
    ]
    items = pending_tasks(rows)
    assert [item["id"] for item in items] == ["s-1", "s-2"]
    assert items[0]["reason"]
    assert items[1]["reason"] != items[0]["reason"]


def test_most_recently_updated_first_and_capped():
    rows = [_signal(f"s-{i}", updated_at=f"2026-09-2{i}T10:00:00+00:00") for i in range(9)]
    items = pending_tasks(rows)
    assert len(items) == 8
    assert items[0]["id"] == "s-8"


def test_load_pending_tasks_is_scoped_to_company_and_user():
    db = FakeDB({"action_signals": [
        _signal("s-mine"),
        _signal("s-other-user", user_id=OTHER),
    ]})
    items = load_pending_tasks(db, user_id=USER, company_id=COMPANY)
    assert [item["id"] for item in items] == ["s-mine"]


def test_load_pending_tasks_is_none_when_the_table_cannot_be_read():
    db = FakeDB({"action_signals": [_signal("s-1")]}, fail_tables=("action_signals",))
    assert load_pending_tasks(db, user_id=USER, company_id=COMPANY) is None
