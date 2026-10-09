"""F13.04 / F15.05: the email opens with one deterministic sentence and shows the same cells as the page."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-presentation-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-presentation-32")

from app.services.reporting.presentation import (
    email_html_for_snapshot,
    email_subject,
    snapshot_metric_cells,
    summary_line,
)


def _snap(*, connected=8, meetings=2, scope="self", report_type="daily", **extra):
    return {
        "scope": scope,
        "report_type": report_type,
        "metrics": {
            "attempts": 12,
            "connected_calls": connected,
            "meetings_agreed": meetings,
            "deals_won": None,
            "adherence": None,
        },
        "coverage": {"crm_outcomes": "unavailable"},
        "examples": [],
        "coaching": None,
        **extra,
    }


def test_summary_sentences_follow_the_spec_copy():
    assert summary_line(_snap()) == "Hoy: 8 llamadas conectadas y 2 reuniones acordadas."
    assert summary_line(_snap(report_type="weekly")) == "Esta semana: 8 llamadas conectadas y 2 reuniones acordadas."
    assert (
        summary_line(_snap(scope="team", report_type="weekly"))
        == "Tu equipo esta semana: 8 llamadas conectadas y 2 reuniones acordadas."
    )


def test_summary_uses_singular_for_one():
    assert summary_line(_snap(connected=1, meetings=1)) == "Hoy: 1 llamada conectada y 1 reunión acordada."


def test_subjects_by_report_type_and_scope():
    assert email_subject(_snap()) == "Tu resumen de actividad"
    assert email_subject(_snap(report_type="weekly")) == "Tu semana en Vocify"
    assert email_subject(_snap(scope="team", report_type="weekly")) == "Tu equipo esta semana"


def test_adherence_with_steps_reads_as_steps_of_applicable():
    snap = _snap(scope="team", report_type="weekly", adherence_steps={"met": 18, "applicable": 24})
    snap["metrics"]["adherence"] = 0.75
    assert snapshot_metric_cells(snap)["adherence"] == "18 de 24 pasos"


def test_adherence_without_steps_is_unavailable():
    assert snapshot_metric_cells(_snap(adherence_steps=None))["adherence"] == "No disponible"


def test_weekly_email_has_sentence_table_objections_and_link_but_no_chart():
    snap = _snap(
        report_type="weekly",
        objections=[{"name": "price", "count": 3, "resolved": 1, "open": 2, "unknown": 0}],
        series=[{"date": "2026-09-21", "connected_calls": 2, "meetings_agreed": 1, "covered": True}],
    )
    html = email_html_for_snapshot(snap, report_id="weekly-1")
    assert "Esta semana: 8 llamadas conectadas y 2 reuniones acordadas." in html
    assert "/dashboard/reports/weekly-1" in html
    assert "Precio" in html
    assert "<svg" not in html
    assert "<img" not in html


def test_unavailable_objections_are_not_rendered_as_an_empty_table():
    html = email_html_for_snapshot(_snap(report_type="weekly", objections=None), report_id="weekly-1")
    assert "Objeciones" not in html


def _cell(state, met=0, applicable=0, sample_limited=False):
    return {"state": state, "met": met, "applicable": applicable, "sample_limited": sample_limited}


TREND = {
    "weeks": ["2026-08-31", "2026-09-07", "2026-09-14", "2026-09-21"],
    "team": [_cell("gap"), _cell("scored", 6, 10), _cell("unscored"), _cell("scored", 9, 12)],
    "reps": [
        {"name": "Ana <Rep>", "weeks": [_cell("gap"), _cell("scored", 6, 10), _cell("unscored"),
                                        _cell("scored", 4, 5, True)]},
    ],
}


def test_team_email_shows_weekly_adherence_per_rep_with_gaps_and_small_samples():
    html = email_html_for_snapshot(_snap(scope="team", report_type="weekly", adherence_trend=TREND), report_id="t-1")
    assert "Adherencia por semana" in html
    assert "<th>31 ago</th><th>7 sept</th><th>14 sept</th><th>21 sept</th>" in html
    assert "<tr><th>Equipo</th><td>—</td><td>6 de 10</td><td>Sin puntuar</td><td>9 de 12</td></tr>" in html
    assert "<th>Ana &lt;Rep&gt;</th>" in html
    assert "<td>4 de 5*</td>" in html
    assert "* Menos de cinco conversaciones puntuadas: sin conclusión." in html


def test_team_email_without_trend_has_no_adherence_by_week_block():
    html = email_html_for_snapshot(_snap(scope="team", report_type="weekly"), report_id="t-1")
    assert "Adherencia por semana" not in html


def test_daily_email_keeps_its_table_and_link():
    html = email_html_for_snapshot(_snap(), report_id="daily-1")
    assert "Hoy: 8 llamadas conectadas y 2 reuniones acordadas." in html
    assert "Reuniones acordadas" in html
    assert "/dashboard/reports/daily-1" in html
