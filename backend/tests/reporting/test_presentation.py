"""F13: email HTML and API read paths expose the same persisted metric cells."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-presentation-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-presentation-32")

from app.api.reports import public_report
from app.services.reporting.presentation import email_html_for_snapshot, snapshot_metric_cells


SNAPSHOT = {
    "metrics": {
        "attempts": 2,
        "connected_calls": 1,
        "meetings_agreed": 1,
        "deals_won": None,
        "adherence": None,
    },
    "coverage": {"crm_outcomes": "unavailable"},
    "examples": ["memo-1", "memo-2"],
    "coaching": None,
}


def test_email_html_and_public_report_share_the_same_metric_cells():
    row = {
        "id": "report-1",
        "revision": 1,
        "scope": "self",
        "period_start": "2026-09-21T22:00:00Z",
        "report_type": "daily",
        "snapshot": SNAPSHOT,
    }
    api_cells = snapshot_metric_cells(public_report(row)["snapshot"])
    html = email_html_for_snapshot(SNAPSHOT, report_id="report-1")
    assert api_cells["connected_calls"] == "1"
    assert api_cells["deals_won"] == "No disponible"
    assert api_cells["connected_calls"] in html
    assert api_cells["meetings_agreed"] in html
    assert "/dashboard/memos/memo-1" in html
    assert "/dashboard/reports/report-1" in html


def test_empty_period_email_has_no_coaching_and_no_invented_close():
    empty = {
        "metrics": {
            "attempts": 0,
            "connected_calls": 0,
            "meetings_agreed": 0,
            "deals_won": None,
            "adherence": None,
        },
        "coverage": {"crm_outcomes": "unavailable"},
        "examples": [],
        "coaching": None,
    }
    html = email_html_for_snapshot(empty, report_id="report-empty")
    cells = snapshot_metric_cells(empty)
    assert cells["attempts"] == "0"
    assert cells["deals_won"] == "No disponible"
    assert "memo-" not in html
    assert empty["coaching"] is None
    assert "Strength" not in html
    assert "Mejora" not in html
