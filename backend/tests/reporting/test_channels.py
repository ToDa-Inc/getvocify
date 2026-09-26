"""Reports count conversations per channel: calls, meetings and visits."""

import os
from datetime import datetime, timezone

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-report-channels-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-report-channels-32")

import pytest

from app.services import feature_flags
from app.services.reporting.channels import interaction_channels
from app.services.reporting.daily_snapshot import ensure_self_daily_report
from app.services.reporting.periodic import ensure_team_weekly_report
from app.services.reporting.presentation import email_html_for_snapshot, summary_line
from app.services.reporting.weekly import weekly_self_snapshot, week_bounds
from tests.reporting.fake_db import FakeDB

UTC = timezone.utc
MADRID = "Europe/Madrid"
START = datetime(2026, 9, 22, 0, 0, tzinfo=UTC)
END = datetime(2026, 9, 23, 0, 0, tzinfo=UTC)
AT = "2026-09-22T10:00:00+00:00"
COMPANY = "88888888-8888-8888-8888-888888888888"
REP = "99999999-9999-9999-9999-999999999999"
ADMIN = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


@pytest.fixture(autouse=True)
def fresh_flags():
    feature_flags.clear_cache()
    yield
    feature_flags.clear_cache()


def _memo(memo_id: str, *, at: str = AT, user_id: str = REP, **fields) -> dict:
    return {
        "id": memo_id,
        "company_id": COMPANY,
        "user_id": user_id,
        "capture_started_at": at,
        "created_at": at,
        "extraction": {},
        **fields,
    }


def _channels(memos):
    return interaction_channels(memos, start=START, end=END)


def test_each_channel_counts_its_conversations():
    memos = [
        _memo("dialer", source="vocify_call", screening_outcome="connected"),
        _memo("hubspot", source="hubspot_call"),
        _memo("upload", source_type="voice_memo"),
        _memo("desktop", source="desktop", interaction_kind="meeting"),
        _memo("visit-1", source="whatsapp", interaction_kind="visit"),
        _memo("visit-2", source="whatsapp"),
    ]
    assert _channels(memos) == {"call": 3, "meeting": 1, "visit": 2}


def test_voicemail_and_no_answer_never_count():
    memos = [
        _memo("vm", source="vocify_call", screening_outcome="voicemail"),
        _memo("na", source="vocify_call", screening_outcome="no_response"),
    ]
    assert _channels(memos) == {"call": 0, "meeting": 0, "visit": 0}


def test_a_dialer_call_without_screening_yet_does_not_count():
    memos = [
        _memo("transcribing", source="vocify_call", screening_outcome=None, status="processing"),
        _memo("failed", source="vocify_call", screening_outcome=None, status="failed"),
    ]
    assert _channels(memos) == {"call": 0, "meeting": 0, "visit": 0}


class _RecordingQuery:
    def __init__(self, log: list):
        self.log = log

    def __getattr__(self, name):
        def record(*args, **_kwargs):
            self.log.append((name, *args))
            return self

        return record

    def execute(self):
        from types import SimpleNamespace

        return SimpleNamespace(data=[])


class _RecordingDB:
    def __init__(self):
        self.log: list = []

    def table(self, name):
        self.log.append(("table", name))
        return _RecordingQuery(self.log)


@pytest.mark.parametrize("member_ids", [[REP], []])
def test_the_team_memo_read_is_bounded_by_the_period(member_ids):
    from app.services.reporting.channels import load_team_channel_memos

    db = _RecordingDB()
    assert load_team_channel_memos(db, COMPANY, member_ids, start=START, end=END) == []
    gte = [entry for entry in db.log if entry[0] == "gte"]
    lt = [entry for entry in db.log if entry[0] == "lt"]
    assert gte == [("gte", "created_at", START.isoformat())]
    assert len(lt) == 1 and lt[0][1] == "created_at" and lt[0][2] > END.isoformat()


def test_a_voice_note_is_not_a_conversation():
    assert _channels([_memo("note", interaction_kind="voice_note")]) == {"call": 0, "meeting": 0, "visit": 0}


def test_a_legacy_whatsapp_row_without_kind_counts_as_a_visit():
    assert _channels([_memo("old", source="whatsapp", interaction_kind=None)])["visit"] == 1


def test_memos_outside_the_period_are_not_counted():
    memos = [_memo("before", at="2026-09-21T23:59:00+00:00", source="whatsapp")]
    assert _channels(memos)["visit"] == 0


def _snapshot(channels, *, meetings_agreed=1, scope="self", report_type=None):
    snap = {
        "scope": scope,
        "metrics": {"attempts": 0, "connected_calls": 0, "meetings_agreed": meetings_agreed, "channels": channels},
    }
    if report_type:
        snap["report_type"] = report_type
    return snap


def test_summary_names_each_channel_and_the_agreed_meetings():
    line = summary_line(_snapshot({"call": 3, "meeting": 1, "visit": 2}))
    assert line == "Hoy: 3 llamadas · 1 reunión · 2 visitas. 1 reunión acordada."


def test_a_channel_with_zero_does_not_appear():
    line = summary_line(_snapshot({"call": 0, "meeting": 0, "visit": 1}, meetings_agreed=2))
    assert line == "Hoy: 1 visita. 2 reuniones acordadas."


def test_singular_and_plural():
    line = summary_line(_snapshot({"call": 1, "meeting": 2, "visit": 0}, meetings_agreed=0))
    assert line == "Hoy: 1 llamada · 2 reuniones. 0 reuniones acordadas."


def test_no_conversations_says_so():
    line = summary_line(_snapshot({"call": 0, "meeting": 0, "visit": 0}, meetings_agreed=0))
    assert line == "Hoy: sin conversaciones. 0 reuniones acordadas."


def test_weekly_and_team_use_their_period_wording():
    channels = {"call": 2, "meeting": 0, "visit": 1}
    assert summary_line(_snapshot(channels, report_type="weekly")) == (
        "Esta semana: 2 llamadas · 1 visita. 1 reunión acordada."
    )
    assert summary_line(_snapshot(channels, scope="team", report_type="weekly")) == (
        "Tu equipo esta semana: 2 llamadas · 1 visita. 1 reunión acordada."
    )


def test_an_old_snapshot_without_channels_keeps_the_previous_text():
    snap = {"scope": "self", "metrics": {"connected_calls": 2, "meetings_agreed": 1}}
    assert summary_line(snap) == "Hoy: 2 llamadas conectadas y 1 reunión acordada."
    assert "<th>Conversaciones</th><td>2</td>" in email_html_for_snapshot(snap, report_id="r1")


def test_the_email_conversations_row_uses_the_same_breakdown():
    html = email_html_for_snapshot(_snapshot({"call": 3, "meeting": 1, "visit": 2}), report_id="r1")
    assert "<th>Conversaciones</th><td>3 llamadas · 1 reunión · 2 visitas</td>" in html
    assert "<p>Hoy: 3 llamadas · 1 reunión · 2 visitas. 1 reunión acordada.</p>" in html


def _db(memos, **extra) -> FakeDB:
    tables = {
        "memos": memos,
        "reports": [],
        "report_notifications": [],
        "team_outcome_observations": [],
        "interaction_patterns": [],
        "report_preferences": [],
        "brief_preferences": [],
        "company_feature_flags": [],
        "company_members": [],
    }
    tables.update(extra)
    return FakeDB(tables)


def test_the_daily_report_counts_visits():
    db = _db([
        _memo("visit-1", source="whatsapp", interaction_kind="visit"),
        _memo("call-1", source="vocify_call", screening_outcome="connected", interaction_kind="call"),
    ])
    ensure_self_daily_report(
        db, company_id=COMPANY, user_id=REP, timezone=MADRID, now=datetime(2026, 9, 22, 16, 0, tzinfo=UTC),
    )
    snap = db.tables["reports"][0]["snapshot"]
    assert snap["metrics"]["channels"] == {"call": 1, "meeting": 0, "visit": 1}
    assert snap["metrics"]["attempts"] == 1
    assert snap["metrics"]["connected_calls"] == 1
    assert summary_line(snap) == "Hoy: 1 llamada · 1 visita. 0 reuniones acordadas."


def test_the_weekly_personal_snapshot_counts_visits():
    now = datetime(2026, 9, 25, 16, 5, tzinfo=UTC)
    start, end = week_bounds(now, MADRID)
    snap = weekly_self_snapshot(
        memos=[_memo("visit-1", source="whatsapp"), _memo("visit-2", source="whatsapp")],
        pattern_rows=[],
        period_start=start,
        period_end=end,
        timezone=MADRID,
        generated_at=now,
        outcomes={"coverage": "unavailable"},
    )
    assert snap["metrics"]["channels"] == {"call": 0, "meeting": 0, "visit": 2}


EMPTY_PANEL = {
    "parts": [],
    "playbook_present": True,
    "sample_size": 0,
    "activity_rows": [],
    "pattern_rows": [],
    "reps": [{"userId": REP, "name": "Ana Rep"}],
    "review": [],
    "outcome_observations": [],
    "outcome_user_id": None,
}


def _team_db(memos):
    return _db(
        memos,
        company_feature_flags=[{"company_id": COMPANY, "flag": "REPORTING_TEAM_ENABLED", "enabled": True}],
        company_members=[
            {"company_id": COMPANY, "user_id": REP, "role": "member", "status": "active"},
            {"company_id": COMPANY, "user_id": ADMIN, "role": "admin", "status": "active"},
        ],
    )


def test_a_team_week_with_only_visits_still_gets_its_report():
    db = _team_db([_memo("visit-1", at="2026-09-23T10:00:00+00:00", source="whatsapp", interaction_kind="visit")])
    report_id = ensure_team_weekly_report(
        db, company_id=COMPANY, user_id=ADMIN, timezone=MADRID, now=datetime(2026, 9, 25, 16, 5, tzinfo=UTC),
        load_inputs=lambda _s, _c: dict(EMPTY_PANEL),
    )
    assert report_id
    snap = db.tables["reports"][0]["snapshot"]
    assert snap["metrics"]["channels"] == {"call": 0, "meeting": 0, "visit": 1}
    assert snap["metrics"]["attempts"] == 0
    assert summary_line(snap) == "Tu equipo esta semana: 1 visita. 0 reuniones acordadas."


def test_a_failed_team_memo_read_sends_the_report_without_channels():
    db = _team_db([])
    db.fail_tables.add("memos")
    panel = {**EMPTY_PANEL, "activity_rows": [
        {"observed_at": "2026-09-23T10:00:00+00:00", "screening": "connected", "meeting_agreed": False},
    ]}
    ensure_team_weekly_report(
        db, company_id=COMPANY, user_id=ADMIN, timezone=MADRID, now=datetime(2026, 9, 25, 16, 5, tzinfo=UTC),
        load_inputs=lambda _s, _c: dict(panel),
    )
    snap = db.tables["reports"][0]["snapshot"]
    assert "channels" not in snap["metrics"]
    assert summary_line(snap) == "Tu equipo esta semana: 1 llamada conectada y 0 reuniones acordadas."
