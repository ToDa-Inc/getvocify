"""Deterministic adherence. Unknown is not a miss, and a zero denominator stays empty."""

from __future__ import annotations

_ALLOWED = {"met", "missed", "unknown", "not_applicable"}


def compute_adherence(statuses: list[str]) -> dict:
    unknown_status = [status for status in statuses if status not in _ALLOWED]
    if unknown_status:
        raise ValueError(f"estado de criterio desconocido: {unknown_status[0]}")
    met = statuses.count("met")
    missed = statuses.count("missed")
    unknown = statuses.count("unknown")
    not_applicable = statuses.count("not_applicable")
    applicable = met + missed
    possible = applicable + unknown
    return {
        "met_steps": met,
        "missed_steps": missed,
        "applicable_steps": applicable,
        "unknown_steps": unknown,
        "not_applicable_steps": not_applicable,
        "adherence": None if applicable == 0 else met / applicable,
        "coverage": None if possible == 0 else applicable / possible,
    }


def aggregate_adherence(parts: list[dict]) -> dict:
    """Sum the counts. Do not average the percentages."""
    statuses: list[str] = []
    for part in parts:
        statuses += ["met"] * part["met_steps"]
        statuses += ["missed"] * part["missed_steps"]
        statuses += ["unknown"] * part["unknown_steps"]
        statuses += ["not_applicable"] * part["not_applicable_steps"]
    return compute_adherence(statuses)
