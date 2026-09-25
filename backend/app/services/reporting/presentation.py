"""Render persisted snapshot metrics for email and in-app read paths."""

from __future__ import annotations

UNAVAILABLE_ES = "No disponible"


def metric_display(value: int | float | None, *, unavailable: str = UNAVAILABLE_ES) -> str:
    return unavailable if value is None else str(value)


def snapshot_metric_cells(snapshot: dict, *, unavailable: str = UNAVAILABLE_ES) -> dict[str, str]:
    metrics = snapshot.get("metrics") or {}
    return {
        "attempts": str(int(metrics.get("attempts") or 0)),
        "connected_calls": str(int(metrics.get("connected_calls") or 0)),
        "meetings_agreed": str(int(metrics.get("meetings_agreed") or 0)),
        "deals_won": metric_display(metrics.get("deals_won"), unavailable=unavailable),
        "adherence": metric_display(metrics.get("adherence"), unavailable=unavailable),
    }


def example_memo_paths(snapshot: dict) -> list[str]:
    examples = snapshot.get("examples") or []
    return [f"/dashboard/memos/{memo_id}" for memo_id in examples if memo_id]


def email_html_for_snapshot(snapshot: dict, *, report_id: str, app_origin: str = "https://app.getvocify.com") -> str:
    cells = snapshot_metric_cells(snapshot)
    report_href = f"{app_origin.rstrip('/')}/dashboard/reports/{report_id}"
    rows = "".join(
        f"<tr><th>{label}</th><td>{cells[key]}</td></tr>"
        for label, key in (
            ("Intentos", "attempts"),
            ("Conversaciones", "connected_calls"),
            ("Reuniones acordadas", "meetings_agreed"),
            ("Cierres", "deals_won"),
            ("Adherencia", "adherence"),
        )
    )
    links = "".join(f'<li><a href="{app_origin.rstrip("/")}{path}">{path}</a></li>' for path in example_memo_paths(snapshot))
    examples_block = f"<ul>{links}</ul>" if links else ""
    coaching = snapshot.get("coaching")
    coaching_block = f"<p>{coaching}</p>" if isinstance(coaching, str) and coaching.strip() else ""
    return (
        f"<p><a href=\"{report_href}\">Ver informe</a></p>"
        f"<table>{rows}</table>"
        f"{coaching_block}"
        f"{examples_block}"
    )
