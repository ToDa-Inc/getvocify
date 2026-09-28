"""Head of Sales: reps[].coaching_focus from the rep-coaching engine, period-only and tolerant."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-team-focus-32-chars")

from datetime import datetime, timedelta, timezone

from app.services.team_insights.aggregate import team_adherence
from app.services.coaching.rep_focus import coaching_focus_by_user
from tests.reporting.fake_db import FakeDB
from tests.team_insights.test_head_of_sales_phase_two import CURRENT, PREVIOUS

COMPANY = "77777777-7777-7777-7777-777777777777"
ANA = "88888888-8888-8888-8888-888888888888"
LUIS = "66666666-6666-6666-6666-666666666666"
NOW = datetime(2026, 9, 24, 10, 0, tzinfo=timezone.utc)  # Thursday; previous week = Sep 14-20
STEPS = [{"step_id": "open", "label": "Apertura"}, {"step_id": "pain", "label": "Dolor"}]
REPS = [{"userId": ANA, "name": "Ana", "salesRole": "sdr"}, {"userId": LUIS, "name": "Luis", "salesRole": "sdr"}]


def _memo(memo_id, user, statuses, days_ago, *, motion="discovery", **over):
    at = (NOW - timedelta(days=days_ago)).isoformat()
    obs = [{"step_id": k, "label": k, "status": v} for k, v in statuses.items()]
    memo = {
        "id": memo_id, "user_id": user, "company_id": COMPANY, "sales_motion_key": motion,
        "screening_outcome": "connected", "audio_duration": 90, "capture_started_at": at, "created_at": at,
        "extraction": {"summary": "x", "intelligence": {"playbook_observations": obs}},
    }
    memo.update(over)
    return memo


def _db(memos, *, published=True):
    return FakeDB({
        "memos": memos,
        "playbooks": [{"id": "pb", "company_id": COMPANY, "sales_motion_key": "discovery", "active_version_id": "v"}],
        "playbook_versions": [{"id": "v", "playbook_id": "pb", "status": "published" if published else "draft",
                               "steps": STEPS, "entries": []}],
    })


def _missing_open(user, prefix, days_ago=7):
    # 3 conversations last week, "open" missing in all of them
    return [_memo(f"{prefix}{i}", user, {"open": "missed", "pain": "met"}, days_ago) for i in range(3)]


def test_focus_is_the_step_missed_most_last_week():
    focus = coaching_focus_by_user(_db(_missing_open(ANA, "a")), COMPANY, REPS, now=NOW)
    assert focus[ANA] == {"step_id": "open", "label": "Apertura", "rate": 0.0}
    assert focus[LUIS] is None


def test_current_week_and_older_weeks_do_not_change_the_focus():
    memos = _missing_open(ANA, "a") + [
        _memo("now", ANA, {"open": "met"}, 1),  # this week
        _memo("old", ANA, {"pain": "missed"}, 14),  # two weeks ago
    ]
    focus = coaching_focus_by_user(_db(memos), COMPANY, REPS, now=NOW)
    assert focus[ANA]["step_id"] == "open"


def test_non_conversations_do_not_count():
    memos = [_memo(f"v{i}", ANA, {"open": "missed"}, 7, screening_outcome="voicemail") for i in range(3)]
    assert coaching_focus_by_user(_db(memos), COMPANY, REPS, now=NOW)[ANA] is None


def test_no_published_playbook_means_no_focus():
    assert coaching_focus_by_user(_db(_missing_open(ANA, "a"), published=False), COMPANY, REPS, now=NOW)[ANA] is None


def test_read_failure_is_null_not_an_error():
    db = _db(_missing_open(ANA, "a"))
    db.fail_tables = {"memos"}
    assert coaching_focus_by_user(db, COMPANY, REPS, now=NOW) == {ANA: None, LUIS: None}


def _both_published_db(memos):
    db = _db(memos)
    db.tables["playbooks"].append(
        {"id": "pb2", "company_id": COMPANY, "sales_motion_key": "closing", "active_version_id": "v2"}
    )
    db.tables["playbook_versions"].append(
        {"id": "v2", "playbook_id": "pb2", "status": "published", "steps": STEPS, "entries": []}
    )
    return db


def test_general_rep_flow_is_resolved_over_eight_weeks_with_a_published_playbook():
    from app.services.coaching import rep_coaching_reads as reads
    from app.services.coaching.rep_focus import flow_window_start, rep_focus, rows_of, previous_week_start
    from app.services.team_insights.aggregate import madrid_week_bounds

    # Closing interactions five weeks ago outweigh one discovery interaction last week.
    memos = [_memo(f"c{i}", ANA, {"open": "met"}, 35, motion="closing") for i in range(3)]
    memos.append(_memo("d", ANA, {"open": "met"}, 7))
    db = _both_published_db(memos)
    week_start = madrid_week_bounds(now=NOW)[0]
    rows = rows_of(reads.load_memos(db, COMPANY, [ANA], start=flow_window_start(week_start)))
    found = rep_focus(
        rows, None, lambda motion: reads.load_published_playbook(db, COMPANY, motion),
        prev_start=previous_week_start(week_start), week_start=week_start,
    )
    assert found["motion"] == "closing"


def test_general_rep_with_only_one_published_flow_uses_it():
    memos = [_memo(f"d{i}", ANA, {"open": "missed", "pain": "met"}, 7) for i in range(3)]
    db = _db(memos)  # only discovery published; the rep has no interactions in closing
    focus = coaching_focus_by_user(db, COMPANY, [{"userId": ANA, "name": "Ana"}], now=NOW)
    assert focus[ANA]["step_id"] == "open"


def test_team_adherence_adds_the_field_only_with_a_period():
    kwargs = dict(role="owner", parts=[], playbook_present=False, sample_size=0, reps=REPS,
                  activity_period_start=CURRENT.start, activity_period_end=CURRENT.end,
                  coaching_focus_by_user={ANA: {"step_id": "open", "label": "Apertura", "rate": 0.0}})
    without = team_adherence(**kwargs)
    assert all("coaching_focus" not in rep for rep in without["reps"])
    with_period = team_adherence(**kwargs, previous_period_start=PREVIOUS.start, previous_period_end=PREVIOUS.end)
    by_id = {rep["userId"]: rep["coaching_focus"] for rep in with_period["reps"]}
    assert by_id == {ANA: {"step_id": "open", "label": "Apertura", "rate": 0.0}, LUIS: None}
