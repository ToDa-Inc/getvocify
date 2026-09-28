"""Lista 4 T2 (E8): the cadence read off stored memos - followup_at, rep_outcome, the refresh
and Próximos. Flag off (cadence None) keeps the old going_cold/objection_open path."""

from datetime import datetime, timedelta, timezone

from app.services.hoy.materialize import fresh_signals, read_hoy_memos, refresh_hoy_signals
from app.services.hoy.upcoming import upcoming_followups

from tests.hoy.test_materialize import _FakeSupabase

NOW = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)
DAY_END = datetime(2026, 9, 24, 21, 59, tzinfo=timezone.utc)


def _memo(memo_id="memo-1", contact="42", *, days_ago=8, intelligence=None, **extra):
    at = (NOW - timedelta(days=days_ago)).isoformat()
    return {
        "id": memo_id,
        "user_id": "user-a",
        "hubspot_contact_id": contact,
        "capture_started_at": at,
        "created_at": at,
        "extraction": {"contactName": "Marina", "companyName": "Acme", "intelligence": intelligence or {}},
        **extra,
    }


PRICE = {"interest": "high", "objections": [{"state": "open", "category": "price", "quote": "Está caro"}]}


def test_flag_off_keeps_the_old_objection_signal():
    signals = fresh_signals([_memo(intelligence=PRICE)], now=NOW, day_end=DAY_END)
    assert [signal.type for signal in signals] == ["objection_open"]


def test_cadence_turns_the_same_memo_into_a_followup_once_due():
    assert [s.type for s in fresh_signals([_memo(intelligence=PRICE)], now=NOW, day_end=DAY_END, cadence={})] == ["followup_due"]
    assert fresh_signals([_memo(intelligence=PRICE, days_ago=1)], now=NOW, day_end=DAY_END, cadence={}) == []


def test_the_stored_followup_at_decides_and_a_bad_value_is_ignored():
    later = (NOW + timedelta(days=3)).isoformat()
    assert fresh_signals([_memo(intelligence=PRICE, followup_at=later)], now=NOW, day_end=DAY_END, cadence={}) == []
    earlier = (NOW - timedelta(days=1)).isoformat()
    soon = _memo(intelligence=PRICE, days_ago=1, followup_at=earlier)
    assert [s.type for s in fresh_signals([soon], now=NOW, day_end=DAY_END, cadence={})] == ["followup_due"]
    broken = _memo(intelligence=PRICE, followup_at="not a date")
    assert [s.type for s in fresh_signals([broken], now=NOW, day_end=DAY_END, cadence={})] == ["followup_due"]


def test_a_disqualified_memo_produces_no_followup():
    for outcome in ("not_interested", "disqualified"):
        memo = _memo(intelligence=PRICE, days_ago=40, rep_outcome=outcome)
        assert fresh_signals([memo], now=NOW, day_end=DAY_END, cadence={}) == []


def test_heat_still_rides_on_the_followup_with_lead_tiers():
    signals = fresh_signals([_memo(intelligence=PRICE)], now=NOW, day_end=DAY_END, cadence={}, lead_tiers_enabled=True)
    assert signals[0].type == "followup_due"
    assert isinstance(signals[0].payload["heat"], int)


class _NoFollowupColumns(_FakeSupabase):
    """A database before migration 062: selecting the new memo columns fails."""

    def table(self, name):
        query = super().table(name)
        original = query.select

        def select(columns="*", *args, **kwargs):
            if name == "memos" and "followup_at" in columns:
                raise RuntimeError('column memos.followup_at does not exist')
            return original(columns, *args, **kwargs)

        query.select = select
        return query


def test_reading_memos_before_the_migration_falls_back_to_the_old_columns():
    supabase = _NoFollowupColumns({"memos": [_memo(intelligence=PRICE)]})
    rows = read_hoy_memos(supabase, company_id="co-1", user_id="user-a", with_followup=True)
    assert [row["id"] for row in rows] == ["memo-1"]


def test_refresh_with_cadence_persists_the_followup_and_leaves_old_objections_alone():
    supabase = _FakeSupabase({
        "memos": [_memo(intelligence=PRICE)],
        "action_signals": [{
            "id": "row-obj", "company_id": "co-1", "user_id": "user-a", "type": "objection_open",
            "status": "pending", "memo_id": "memo-1", "dedupe_key": "objection:memo-1:price",
        }],
    })
    written = refresh_hoy_signals(supabase, company_id="co-1", user_id="user-a", now=NOW, tz_name="Europe/Madrid", cadence={})
    assert written == 1
    rows = supabase.rows("action_signals")
    followup = next(row for row in rows if row["type"] == "followup_due")
    assert followup["dedupe_key"] == "followup:memo-1"
    assert followup["payload"]["stopper"] == "price"
    # Hidden on read while the flag is on, still pending so turning the flag off restores it.
    assert next(row for row in rows if row["id"] == "row-obj")["status"] == "pending"


def test_refresh_with_cadence_retracts_a_followup_once_a_newer_call_supersedes_it():
    supabase = _FakeSupabase({
        "memos": [_memo(intelligence=PRICE), _memo("memo-2", days_ago=0, intelligence={"interest": "high"})],
        "action_signals": [{
            "id": "row-f", "company_id": "co-1", "user_id": "user-a", "type": "followup_due",
            "status": "pending", "memo_id": "memo-1", "dedupe_key": "followup:memo-1",
        }],
    })
    refresh_hoy_signals(supabase, company_id="co-1", user_id="user-a", now=NOW, tz_name="Europe/Madrid", cadence={})
    assert next(row for row in supabase.rows("action_signals") if row["id"] == "row-f")["status"] == "resolved"


def test_a_dismissed_followup_is_never_resurrected():
    supabase = _FakeSupabase({
        "memos": [_memo(intelligence=PRICE)],
        "action_signals": [{
            "id": "row-f", "company_id": "co-1", "user_id": "user-a", "type": "followup_due",
            "status": "dismissed", "memo_id": "memo-1", "dedupe_key": "followup:memo-1",
        }],
    })
    assert refresh_hoy_signals(supabase, company_id="co-1", user_id="user-a", now=NOW, tz_name="Europe/Madrid", cadence={}) == 0


# --- Próximos ---------------------------------------------------------------------


def test_a_future_followup_shows_in_upcoming_with_its_date_and_stopper():
    rows = upcoming_followups([_memo(intelligence=PRICE, days_ago=2)], now=NOW, tz_name="Europe/Madrid")
    assert len(rows) == 1
    row = rows[0]
    assert row["kind"] == "followup"
    assert row["memo_id"] == "memo-1"
    assert row["contact_id"] == "42"
    assert row["contact_name"] == "Marina"
    assert row["text"] == "Seguimiento · frenó por precio"
    assert row["due_at"] == (NOW - timedelta(days=2) + timedelta(days=7)).isoformat()
    assert row["crm_task_id"] is None
    en = upcoming_followups([_memo(intelligence=PRICE, days_ago=2)], now=NOW, tz_name="Europe/Madrid", lang="en")
    assert en[0]["text"] == "Follow-up · stalled on price"


def test_upcoming_skips_due_beyond_window_closed_and_committed_contacts():
    due_today = _memo("m1", "1", intelligence=PRICE, days_ago=7)
    beyond = _memo("m2", "2", intelligence={"interest": "low"}, days_ago=1)
    closed = _memo("m3", "3", intelligence=PRICE, days_ago=2, rep_outcome="disqualified")
    committed = _memo("m4", "4", days_ago=2, intelligence={
        **PRICE,
        "commitments": [{"kind": "call", "origin": "rep_promise", "text": "Llamar", "due_at": (NOW + timedelta(days=2)).isoformat()}],
    })
    rows = upcoming_followups([due_today, beyond, closed, committed], now=NOW, tz_name="Europe/Madrid")
    assert rows == []


def test_upcoming_uses_company_overrides_and_the_rep_date():
    rows = upcoming_followups([_memo(intelligence=PRICE, days_ago=2)], now=NOW, tz_name="Europe/Madrid", overrides={"price": 4})
    assert rows[0]["due_at"] == (NOW + timedelta(days=2)).isoformat()
    picked = (NOW + timedelta(days=5)).isoformat()
    rows = upcoming_followups([_memo(intelligence={"interest": "none"}, days_ago=1, followup_at=picked)], now=NOW, tz_name="Europe/Madrid")
    assert rows[0]["due_at"] == picked
    assert rows[0]["text"] == "Seguimiento"
