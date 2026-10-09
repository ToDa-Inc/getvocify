"""COACHING_MESSAGES_ENABLED: snapshot.coaching of the rep's own reports, and its HTML escaping."""

import os
from datetime import datetime, timezone

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-coaching-msgs-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-coaching-msgs-32")

import pytest

from app.services import feature_flags
from app.services.reporting.daily_snapshot import ensure_self_daily_report
from app.services.reporting.periodic import ensure_self_weekly_report
from app.services.reporting.presentation import email_html_for_snapshot
from tests.reporting.fake_db import FakeDB

MADRID = "Europe/Madrid"
COMPANY = "88888888-8888-8888-8888-888888888888"
REP = "99999999-9999-9999-9999-999999999999"
THURSDAY = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)
FRIDAY_1805 = datetime(2026, 9, 25, 16, 5, tzinfo=timezone.utc)
STEPS = [{"step_id": "open", "label": "Apertura"}, {"step_id": "pain", "label": "Dolor"}]


@pytest.fixture(autouse=True)
def fresh_flags():
    feature_flags.clear_cache()
    yield
    feature_flags.clear_cache()


def _memo(memo_id, at, statuses):
    return {
        "id": memo_id, "company_id": COMPANY, "user_id": REP, "sales_motion_key": "discovery",
        "screening_outcome": "connected", "audio_duration": 90, "interaction_kind": "call",
        "capture_started_at": at, "created_at": at,
        "extraction": {"summary": "x", "intelligence": {"playbook_observations": [
            {"step_id": k, "label": k, "status": v, "quote": "SECRET"} for k, v in statuses.items()]}},
    }


def _db(memos, *, on: bool):
    flags = [{"company_id": COMPANY, "flag": "REPORTING_WEEKLY_ENABLED", "enabled": True}]
    if on:
        flags.append({"company_id": COMPANY, "flag": "COACHING_MESSAGES_ENABLED", "enabled": True})
    return FakeDB({
        "memos": memos, "reports": [], "report_notifications": [], "team_outcome_observations": [],
        "interaction_patterns": [], "report_preferences": [], "brief_preferences": [],
        "company_feature_flags": flags,
        "company_members": [{"id": "m1", "company_id": COMPANY, "user_id": REP, "role": "member",
                             "status": "active", "sales_role": "sdr"}],
        "playbooks": [{"id": "pb", "company_id": COMPANY, "sales_motion_key": "discovery", "active_version_id": "v"}],
        "playbook_versions": [{"id": "v", "playbook_id": "pb", "status": "published", "steps": STEPS, "entries": []}],
    })


# previous week (Sep 14-18): "open" missed in 3 conversations -> focus "Apertura"
PREV = [_memo(f"p{i}", f"2026-09-1{5 + i}T09:00:00+00:00", {"open": "missed", "pain": "met"}) for i in range(3)]
TODAY = [
    _memo("t1", "2026-09-24T08:00:00+00:00", {"open": "missed", "pain": "met"}),
    _memo("t2", "2026-09-24T09:00:00+00:00", {"open": "met", "pain": "met"}),
]


def test_daily_flag_on_fills_the_line():
    db = _db(PREV + TODAY, on=True)
    ensure_self_daily_report(db, company_id=COMPANY, user_id=REP, timezone=MADRID, now=THURSDAY)
    coaching = db.tables["reports"][0]["snapshot"]["coaching"]
    assert coaching == "Lo mejor de hoy: Dolor en 2 de 2. Tu foco esta semana: Apertura (hoy 1 de 2)."
    assert "SECRET" not in coaching


def test_daily_flag_off_keeps_coaching_none():
    db = _db(PREV + TODAY, on=False)
    ensure_self_daily_report(db, company_id=COMPANY, user_id=REP, timezone=MADRID, now=THURSDAY)
    assert db.tables["reports"][0]["snapshot"]["coaching"] is None


def test_daily_without_conversations_has_no_line():
    voicemail = {**TODAY[0], "screening_outcome": "voicemail"}
    db = _db(PREV + [voicemail], on=True)
    ensure_self_daily_report(db, company_id=COMPANY, user_id=REP, timezone=MADRID, now=THURSDAY)
    assert db.tables["reports"][0]["snapshot"]["coaching"] is None


def test_weekly_flag_on_reports_last_focus_and_new_one():
    # reported week Sep 21-25: opening improves to 1 of 4, still the repeated failure
    week = [_memo(f"w{i}", f"2026-09-2{2 + i}T09:00:00+00:00",
                  {"open": "met" if i == 0 else "missed", "pain": "met"}) for i in range(4)]
    db = _db(PREV + week, on=True)
    ensure_self_weekly_report(db, company_id=COMPANY, user_id=REP, timezone=MADRID, now=FRIDAY_1805)
    coaching = db.tables["reports"][0]["snapshot"]["coaching"]
    assert coaching == "Foco de la semana pasada: Apertura 0%→25%. Nuevo foco: Apertura."


def test_weekly_flag_off_keeps_coaching_none():
    week = [_memo("w0", "2026-09-22T09:00:00+00:00", {"open": "met"})]
    db = _db(PREV + week, on=False)
    ensure_self_weekly_report(db, company_id=COMPANY, user_id=REP, timezone=MADRID, now=FRIDAY_1805)
    assert db.tables["reports"][0]["snapshot"]["coaching"] is None


def test_coaching_text_is_html_escaped_in_the_email():
    snapshot = {"scope": "self", "report_type": "daily", "metrics": {}, "coaching": "<script>alert(1)</script> & <b>x</b>"}
    html = email_html_for_snapshot(snapshot, report_id="r1")
    assert "<script>" not in html and "<b>x</b>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt; &amp; &lt;b&gt;x&lt;/b&gt;" in html


def test_example_links_are_escaped_too():
    snapshot = {"scope": "self", "report_type": "daily", "metrics": {}, "examples": ['x"><script>']}
    assert "<script>" not in email_html_for_snapshot(snapshot, report_id="r1")


def test_flag_defaults_off_and_reaches_the_client():
    from app.config import Settings
    from app.services.feature_flags import CLIENT_FLAGS

    assert Settings.model_fields["COACHING_MESSAGES_ENABLED"].default is False
    assert "COACHING_MESSAGES_ENABLED" in CLIENT_FLAGS


def test_daily_looks_up_existing_report_before_computing_coaching(monkeypatch):
    from app.services.reporting import daily_snapshot

    calls: list[str] = []
    real_existing = daily_snapshot._existing_report_id

    def existing(*args, **kwargs):
        calls.append("existing")
        return real_existing(*args, **kwargs)

    def coaching(*args, **kwargs):
        calls.append("coaching")
        return None

    monkeypatch.setattr(daily_snapshot, "_existing_report_id", existing)
    monkeypatch.setattr(daily_snapshot, "self_daily_coaching", coaching)
    db = _db(PREV + TODAY, on=True)
    ensure_self_daily_report(db, company_id=COMPANY, user_id=REP, timezone=MADRID, now=THURSDAY)
    assert calls == ["existing", "coaching"]


def test_coaching_line_reads_the_same_eight_week_flow_window_as_the_tab():
    from app.services.coaching.rep_focus import flow_window_start
    from app.services.reporting import coaching_line
    from app.services.team_insights.aggregate import madrid_week_bounds

    old = _memo("old", "2026-08-05T09:00:00+00:00", {"open": "met"})  # ~7 weeks before THURSDAY
    db = _db([old] + PREV + TODAY, on=True)
    reference = THURSDAY
    rows, _role, _playbook_for, _prev, week_start = coaching_line._context(
        db, COMPANY, REP, reference=reference, since=reference
    )
    assert week_start == madrid_week_bounds(now=reference)[0]
    assert "old" in {r["memo_id"] for r in rows}
    assert flow_window_start(week_start).isoformat() <= old["created_at"]
